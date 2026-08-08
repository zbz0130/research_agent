from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import Settings, get_settings
from app.research_schemas import (
    AnalysisCreate,
    AnalysisJob,
    AnalysisSummary,
    ConceptGraph,
    GraphPatch,
    GraphPatchCreate,
    GraphMetadataUpdate,
    GraphCompareCreate,
    GraphCompareResult,
    GraphSubsetResult,
    IdeaCheckCreate,
    IdeaCheckResult,
    NodeExplanationCreate,
    ResearchBrief,
)
from app.schemas import ApiKeyStatusResponse, ApiKeyUpdate, HealthResponse, Project, ProjectCreate
from app.services.graph_service import GraphConflict, GraphNotFound, graph_service
from app.services.project_service import project_service
from app.services.research_service import AnalysisNotFound, research_service
from app.services.idea_service import IdeaCheckNotFound, idea_service
from app.services.research_providers import ProviderUnavailable
from app.services.settings_service import api_key_status as build_api_key_status, update_api_keys

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.version)


@router.get("/settings/api-keys", response_model=ApiKeyStatusResponse, tags=["settings"])
def api_key_status(settings: Settings = Depends(get_settings)) -> ApiKeyStatusResponse:
    """Expose configuration status without ever returning a raw API key."""

    return build_api_key_status(settings)


@router.patch("/settings/api-keys", response_model=ApiKeyStatusResponse, tags=["settings"])
def update_api_key_status(
    payload: ApiKeyUpdate,
    settings: Settings = Depends(get_settings),
) -> ApiKeyStatusResponse:
    """Set or clear provider credentials for the current API process.

    The response contains only masked status.  Runtime values are lost on
    restart; use environment variables or a secret manager for persistent
    deployment configuration.
    """

    return update_api_keys(settings, payload)


@router.get("/projects", response_model=list[Project], tags=["projects"])
def list_projects() -> list[Project]:
    return project_service.list()


@router.post(
    "/projects",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(payload: ProjectCreate) -> Project:
    return project_service.create(payload)


@router.post(
    "/analyses",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["research"],
)
def create_analysis(
    payload: AnalysisCreate,
    settings: Settings = Depends(get_settings),
) -> AnalysisJob:
    return research_service.create(payload, settings)


@router.get("/analyses", response_model=list[AnalysisSummary], tags=["research"])
def list_analyses() -> list[AnalysisSummary]:
    return research_service.list()


@router.get("/analyses/{analysis_id}", response_model=AnalysisJob, tags=["research"])
def get_analysis(analysis_id: UUID) -> AnalysisJob:
    try:
        return research_service.get(analysis_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务不存在") from exc


@router.get(
    "/analyses/{analysis_id}/research-brief",
    response_model=ResearchBrief,
    tags=["research"],
)
def get_research_brief(analysis_id: UUID) -> ResearchBrief:
    """Return the auditable multi-agent result for a completed research run."""

    try:
        job = research_service.get(analysis_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务不存在") from exc
    if job.result is None or job.result.research_brief is None:
        raise HTTPException(status_code=404, detail="该分析没有可用的 Research Brief")
    return job.result.research_brief


@router.post("/ideas/check", response_model=IdeaCheckResult, tags=["research"])
def check_idea(
    payload: IdeaCheckCreate,
    settings: Settings = Depends(get_settings),
) -> IdeaCheckResult:
    """Run a bounded, explicit prior-art triage for a research idea."""

    try:
        return idea_service.check(payload, settings)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/ideas/checks", response_model=list[IdeaCheckResult], tags=["research"])
def list_idea_checks() -> list[IdeaCheckResult]:
    return idea_service.list()


@router.get("/ideas/checks/{check_id}", response_model=IdeaCheckResult, tags=["research"])
def get_idea_check(check_id: str) -> IdeaCheckResult:
    try:
        return idea_service.get(check_id)
    except IdeaCheckNotFound as exc:
        raise HTTPException(status_code=404, detail="想法查重记录不存在") from exc


@router.get("/graphs/{graph_id}", response_model=ConceptGraph, tags=["graphs"])
def get_graph(graph_id: str) -> ConceptGraph:
    try:
        return graph_service.get(graph_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc


@router.patch("/graphs/{graph_id}", response_model=ConceptGraph, tags=["graphs"])
def update_graph_metadata(graph_id: str, payload: GraphMetadataUpdate) -> ConceptGraph:
    try:
        return graph_service.update_metadata(graph_id, payload)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/graphs", response_model=list[ConceptGraph], tags=["graphs"])
def list_graphs(project_id: UUID | None = None) -> list[ConceptGraph]:
    return graph_service.list(project_id=project_id)


@router.post("/graphs/compare", response_model=GraphCompareResult, tags=["graphs"])
def compare_graphs(payload: GraphCompareCreate) -> GraphCompareResult:
    try:
        return graph_service.compare(payload)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="参与比较的概念图不存在") from exc


@router.get("/graphs/{graph_id}/subset", response_model=GraphSubsetResult, tags=["graphs"])
def get_graph_subset(
    graph_id: str,
    node_ids: str = Query(..., description="逗号分隔的节点 ID"),
    include_ancestors: bool = True,
) -> GraphSubsetResult:
    requested = [value.strip() for value in node_ids.split(",") if value.strip()]
    try:
        return graph_service.subset(
            graph_id,
            requested,
            include_ancestors=include_ancestors,
        )
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/graphs/{graph_id}/patches", response_model=GraphPatch, tags=["graphs"])
def create_graph_patch(graph_id: str, payload: GraphPatchCreate) -> GraphPatch:
    try:
        return graph_service.create_patch(graph_id, payload)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/graphs/{graph_id}/patches", response_model=list[GraphPatch], tags=["graphs"])
def list_graph_patches(graph_id: str) -> list[GraphPatch]:
    try:
        return graph_service.list_patches(graph_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc


@router.post(
    "/graphs/{graph_id}/nodes/{node_id}/explanation-patch",
    response_model=GraphPatch,
    tags=["graphs"],
)
def propose_node_explanation(
    graph_id: str,
    node_id: str,
    payload: NodeExplanationCreate,
    settings: Settings = Depends(get_settings),
) -> GraphPatch:
    try:
        patch, _warnings = research_service.propose_node_explanation(
            graph_id,
            node_id,
            settings,
            audience=payload.audience,
            language=payload.language,
        )
        return patch
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="节点不存在") from exc
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/graphs/{graph_id}/patches/{patch_id}/apply", response_model=GraphPatch, tags=["graphs"])
def apply_graph_patch(graph_id: str, patch_id: str) -> GraphPatch:
    try:
        return graph_service.apply_patch(graph_id, patch_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图或修改提案不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/graphs/{graph_id}/patches/{patch_id}/reject", response_model=GraphPatch, tags=["graphs"])
def reject_graph_patch(graph_id: str, patch_id: str) -> GraphPatch:
    try:
        return graph_service.reject_patch(graph_id, patch_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图或修改提案不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
