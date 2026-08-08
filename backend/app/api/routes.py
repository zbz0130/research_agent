from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.research_schemas import (
    AnalysisCreate,
    AnalysisJob,
    AnalysisSummary,
    ConceptGraph,
    GraphPatch,
    GraphPatchCreate,
    GraphMetadataUpdate,
    NodeExplanationCreate,
)
from app.schemas import ApiKeyStatusResponse, HealthResponse, Project, ProjectCreate
from app.services.graph_service import GraphConflict, GraphNotFound, graph_service
from app.services.project_service import project_service
from app.services.research_service import AnalysisNotFound, research_service
from app.services.settings_service import api_key_slots

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.version)


@router.get("/settings/api-keys", response_model=ApiKeyStatusResponse, tags=["settings"])
def api_key_status(settings: Settings = Depends(get_settings)) -> ApiKeyStatusResponse:
    """Expose configuration status without ever returning a raw API key."""

    return ApiKeyStatusResponse(slots=list(api_key_slots(settings)))


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
