from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.config import Settings, get_settings
from app.evidence_schemas import ClaimEvidenceReview, EvidenceLedger
from app.experiment_schemas import ExperimentPlan, ExperimentPlanRequest, ExperimentPlanReview
from app.research_schemas import (
    AnalysisCreate,
    AnalysisJob,
    AnalysisSummary,
    AnalysisGraphSaveResponse,
    ConceptGraph,
    GraphCreate,
    GraphAgentPatchCreate,
    GraphPatch,
    GraphPatchCreate,
    GraphMetadataUpdate,
    GraphLayoutUpdate,
    GraphNodeDetail,
    GraphSaveRequest,
    GraphCompareCreate,
    GraphCompareResult,
    GraphSubsetResult,
    IdeaCheckReview,
    IdeaCheckCreate,
    IdeaCheckResult,
    NodeExplanationCreate,
    OverviewCreate,
    OverviewExpandRequest,
    OverviewJob,
    OverviewRetryDirectionRequest,
    OverviewSaveRequest,
    OverviewSaveResponse,
    ResearchBrief,
)
from app.schemas import (
    ApiKeyStatusResponse,
    ApiKeyUpdate,
    HealthResponse,
    Project,
    ProjectCreate,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResponse,
    ProviderRuntimeSlotUpdate,
    ProviderSlotId,
    RuntimeProviderSettings,
    RuntimeProviderSettingsUpdate,
)
from app.services.graph_service import GraphConflict, GraphNotFound, graph_service
from app.services.graph_agent_patch_service import graph_agent_patch_service
from app.services.project_service import project_service
from app.services.research_service import (
    AnalysisNotFound,
    EvidenceLinkNotFound,
    research_service,
)
from app.services.idea_service import IdeaCheckNotFound, idea_service
from app.services.overview_service import (
    OverviewNotFound,
    OverviewUnavailable,
    overview_service,
)
from app.services.research_providers import ProviderUnavailable
from app.services.settings_service import (
    api_key_status as build_api_key_status,
    runtime_provider_status,
    test_provider_connection,
    update_api_keys,
    update_provider_slot,
    update_runtime_provider_settings,
)
from app.services.experiment_service import experiment_service
from app.storage import storage

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


@router.get("/settings/runtime", response_model=RuntimeProviderSettings, tags=["settings"])
def runtime_settings_status(settings: Settings = Depends(get_settings)) -> RuntimeProviderSettings:
    """Expose non-secret model endpoint settings for the local settings UI."""

    return runtime_provider_status(settings)


@router.patch("/settings/runtime", response_model=RuntimeProviderSettings, tags=["settings"])
def update_runtime_settings(
    payload: RuntimeProviderSettingsUpdate,
    settings: Settings = Depends(get_settings),
) -> RuntimeProviderSettings:
    """Change model provider, model name, proxy URL, or demo mode in memory."""

    return update_runtime_provider_settings(settings, payload)


@router.patch(
    "/settings/providers/{slot_id}",
    response_model=RuntimeProviderSettings,
    tags=["settings"],
)
def update_provider_settings(
    slot_id: ProviderSlotId,
    payload: ProviderRuntimeSlotUpdate,
    settings: Settings = Depends(get_settings),
) -> RuntimeProviderSettings:
    """Update one purpose-specific provider's non-secret runtime settings."""

    return update_provider_slot(settings, slot_id, payload)


@router.post(
    "/settings/providers/{slot_id}/test",
    response_model=ProviderConnectionTestResponse,
    tags=["settings"],
)
def test_provider_settings_connection(
    slot_id: ProviderSlotId,
    payload: ProviderConnectionTestRequest,
    settings: Settings = Depends(get_settings),
) -> ProviderConnectionTestResponse:
    """Safely validate a provider without exposing or transmitting its key.

    ``probe`` is opt-in and only checks bare HTTP reachability for an explicit
    Base URL; it never performs a paper search, model completion or experiment.
    """

    return test_provider_connection(settings, slot_id, probe=payload.probe)


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
    "/analyses/{analysis_id}/graph",
    response_model=ConceptGraph,
    tags=["research", "graphs"],
)
def get_analysis_graph(analysis_id: UUID) -> ConceptGraph:
    """Read a transient or saved graph embedded in an analysis snapshot."""

    try:
        return research_service.get_analysis_graph(analysis_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc


@router.patch(
    "/analyses/{analysis_id}/graph",
    response_model=ConceptGraph,
    tags=["research", "graphs"],
)
def update_analysis_graph(
    analysis_id: UUID,
    payload: GraphMetadataUpdate,
) -> ConceptGraph:
    """Edit analysis-graph metadata without promoting it to the graph library."""

    try:
        return research_service.update_analysis_graph_metadata(analysis_id, payload)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/graph/save",
    response_model=AnalysisGraphSaveResponse,
    tags=["research", "graphs"],
)
def save_analysis_graph(
    analysis_id: UUID,
    payload: GraphSaveRequest | None = None,
) -> AnalysisGraphSaveResponse:
    """Promote an analysis' transient graph after explicit user confirmation."""

    request = payload or GraphSaveRequest()
    try:
        graph = research_service.save_analysis_graph(
            analysis_id,
            expected_version=request.expected_version,
            name=request.name,
        )
        return AnalysisGraphSaveResponse(
            analysis_id=analysis_id,
            graph=graph,
            saved_graph_id=graph.id,
            graph_save_state="saved",
        )
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/analyses/{analysis_id}/graph/patches",
    response_model=list[GraphPatch],
    tags=["research", "graphs"],
)
def list_analysis_graph_patches(analysis_id: UUID) -> list[GraphPatch]:
    try:
        return research_service.list_analysis_graph_patches(analysis_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc


@router.post(
    "/analyses/{analysis_id}/graph/patches",
    response_model=GraphPatch,
    tags=["research", "graphs"],
)
def create_analysis_graph_patch(
    analysis_id: UUID, payload: GraphPatchCreate
) -> GraphPatch:
    try:
        return research_service.create_analysis_graph_patch(analysis_id, payload)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/graph/agent-patch",
    response_model=GraphPatch,
    tags=["research", "graphs"],
)
def create_analysis_agent_patch(
    analysis_id: UUID, payload: GraphAgentPatchCreate
) -> GraphPatch:
    try:
        return research_service.propose_analysis_agent_patch(analysis_id, payload)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/graph/nodes/{node_id}/explanation-patch",
    response_model=GraphPatch,
    tags=["research", "graphs"],
)
def create_analysis_node_explanation_patch(
    analysis_id: UUID,
    node_id: str,
    payload: NodeExplanationCreate,
    settings: Settings = Depends(get_settings),
) -> GraphPatch:
    try:
        return research_service.propose_analysis_node_explanation(
            analysis_id,
            node_id,
            settings,
            audience=payload.audience,
            language=payload.language,
        )
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或概念图节点不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/graph/patches/{patch_id}/apply",
    response_model=GraphPatch,
    tags=["research", "graphs"],
)
def apply_analysis_graph_patch(analysis_id: UUID, patch_id: str) -> GraphPatch:
    try:
        return research_service.apply_analysis_graph_patch(analysis_id, patch_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或修改提案不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/graph/patches/{patch_id}/reject",
    response_model=GraphPatch,
    tags=["research", "graphs"],
)
def reject_analysis_graph_patch(analysis_id: UUID, patch_id: str) -> GraphPatch:
    try:
        return research_service.reject_analysis_graph_patch(analysis_id, patch_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务或修改提案不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/overview",
    response_model=OverviewJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["research", "overviews"],
)
def create_overview(
    analysis_id: UUID,
    payload: OverviewCreate | None = None,
    settings: Settings = Depends(get_settings),
) -> OverviewJob:
    """Start (or reuse) a bounded asynchronous research-direction job."""

    try:
        return overview_service.create(
            analysis_id,
            payload or OverviewCreate(),
            settings=settings,
        )
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务不存在") from exc
    except OverviewUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/overviews",
    response_model=list[OverviewJob],
    tags=["research", "overviews"],
)
def list_overviews(analysis_id: UUID | None = None) -> list[OverviewJob]:
    """List durable Overview jobs so the UI can recover them after restart."""

    return overview_service.list(analysis_id)


@router.get(
    "/overviews/{overview_id}",
    response_model=OverviewJob,
    tags=["research", "overviews"],
)
def get_overview(overview_id: UUID) -> OverviewJob:
    """Poll one Overview, including its partial/final durable state."""

    try:
        return overview_service.get(overview_id)
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="研究方向图任务不存在") from exc


@router.get(
    "/overviews/{overview_id}/nodes/{node_id}",
    response_model=GraphNodeDetail,
    tags=["research", "overviews"],
)
def get_overview_node_detail(overview_id: UUID, node_id: str) -> GraphNodeDetail:
    """Inspect a transient Overview node, including PDF-section evidence."""

    try:
        return overview_service.node_detail(overview_id, node_id)
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="研究方向图任务或节点不存在") from exc


@router.post(
    "/overviews/{overview_id}/expand",
    response_model=OverviewJob,
    tags=["research", "overviews"],
)
def expand_overview(
    overview_id: UUID,
    payload: OverviewExpandRequest,
    settings: Settings = Depends(get_settings),
) -> OverviewJob:
    """Refine one direction without widening the persisted paper scope."""

    try:
        return overview_service.expand(overview_id, payload, settings=settings)
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="研究方向图任务不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/overviews/{overview_id}/directions/{direction_key}/retry",
    response_model=OverviewJob,
    tags=["research", "overviews"],
)
def retry_overview_direction(
    overview_id: UUID,
    direction_key: str,
    payload: OverviewRetryDirectionRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> OverviewJob:
    """Retry one failed direction without regenerating successful peers."""

    try:
        return overview_service.retry_direction(
            overview_id,
            direction_key,
            payload or OverviewRetryDirectionRequest(),
            settings=settings,
        )
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="研究方向图任务或方向不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/overviews/{overview_id}/save",
    response_model=OverviewSaveResponse,
    tags=["research", "overviews", "graphs"],
)
def save_overview(
    overview_id: UUID,
    payload: OverviewSaveRequest | None = None,
) -> OverviewSaveResponse:
    """Promote a transient Overview into the shared saved graph library."""

    try:
        job = overview_service.save(overview_id, payload or OverviewSaveRequest())
    except OverviewNotFound as exc:
        raise HTTPException(status_code=404, detail="研究方向图任务不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    assert job.result is not None and job.saved_graph_id is not None
    return OverviewSaveResponse(
        overview_id=job.id,
        graph=job.result.graph,
        saved_graph_id=job.saved_graph_id,
        save_state="saved",
    )


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


@router.get(
    "/analyses/{analysis_id}/evidence-ledger",
    response_model=EvidenceLedger,
    tags=["research"],
)
def get_evidence_ledger(analysis_id: UUID) -> EvidenceLedger:
    """Return claim-level provenance for a completed analysis."""

    try:
        job = research_service.get(analysis_id)
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务不存在") from exc
    if job.result is None or job.result.evidence_ledger is None:
        raise HTTPException(status_code=404, detail="该分析没有可用的证据账本")
    return job.result.evidence_ledger


@router.patch(
    "/analyses/{analysis_id}/claims/{claim_id}/evidence/{evidence_id}/review",
    response_model=AnalysisJob,
    tags=["research"],
)
def review_claim_evidence(
    analysis_id: UUID,
    claim_id: str,
    evidence_id: str,
    payload: ClaimEvidenceReview,
) -> AnalysisJob:
    """Save one explicit human verdict without changing the source excerpt."""

    try:
        return research_service.review_evidence_link(
            analysis_id,
            claim_id,
            evidence_id,
            payload,
        )
    except AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail="分析任务不存在") from exc
    except EvidenceLinkNotFound as exc:
        raise HTTPException(status_code=404, detail="主张或证据关联不存在") from exc


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


@router.post("/ideas/checks/{check_id}/review", response_model=IdeaCheckResult, tags=["research"])
def review_idea_check(check_id: str, payload: IdeaCheckReview) -> IdeaCheckResult:
    """Record human review metadata for a prior-art triage result."""

    try:
        return idea_service.review(check_id, payload)
    except IdeaCheckNotFound as exc:
        raise HTTPException(status_code=404, detail="想法查重记录不存在") from exc


@router.post(
    "/experiments/plans",
    response_model=ExperimentPlan,
    status_code=status.HTTP_201_CREATED,
    tags=["experiments"],
)
def create_experiment_plan(payload: ExperimentPlanRequest) -> ExperimentPlan:
    """Draft a structured experiment plan; this endpoint never executes code."""

    plan = experiment_service.generate(payload)
    return storage.save_experiment_plan(plan)


@router.get("/experiments/plans", response_model=list[ExperimentPlan], tags=["experiments"])
def list_experiment_plans(project_id: UUID | None = None) -> list[ExperimentPlan]:
    return storage.list_experiment_plans(str(project_id) if project_id else None)


@router.get("/experiments/plans/{plan_id}", response_model=ExperimentPlan, tags=["experiments"])
def get_experiment_plan(plan_id: str) -> ExperimentPlan:
    plan = storage.get_experiment_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="实验方案不存在")
    return plan


@router.post(
    "/experiments/plans/{plan_id}/review",
    response_model=ExperimentPlan,
    tags=["experiments"],
)
def review_experiment_plan(plan_id: str, payload: ExperimentPlanReview) -> ExperimentPlan:
    plan = storage.get_experiment_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="实验方案不存在")
    reviewed = experiment_service.review(plan, payload)
    return storage.save_experiment_plan(reviewed)


@router.post(
    "/graphs",
    response_model=ConceptGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
def create_graph(payload: GraphCreate) -> ConceptGraph:
    """Create an independent concept graph for manual/imported knowledge."""

    try:
        return graph_service.create(payload)
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/graphs/{graph_id}", response_model=ConceptGraph, tags=["graphs"])
def get_graph(graph_id: str) -> ConceptGraph:
    try:
        return graph_service.get(graph_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc


@router.get(
    "/graphs/{graph_id}/nodes/{node_id}",
    response_model=GraphNodeDetail,
    tags=["graphs"],
)
def get_graph_node_detail(graph_id: str, node_id: str) -> GraphNodeDetail:
    """Return one node together with its recoverable papers and evidence."""

    try:
        graph = graph_service.get(graph_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    node = next((item for item in graph.nodes if item.id == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail="概念图节点不存在")

    papers = []
    evidence = []
    warnings: list[str] = []
    evidence_ids = set(node.evidence_ids)
    paper_ids = set(node.paper_ids)
    if node.paper_id:
        paper_ids.add(node.paper_id)

    # A saved research-direction graph deliberately keeps its evidence corpus
    # in the durable Overview job.  ``generation_id`` is the stable provenance
    # link, so saving into the shared graph library does not duplicate or lose
    # PDF-section evidence.
    overview = None
    if graph.graph_kind == "research_direction" and graph.generation_id:
        try:
            overview = storage.get_overview(str(UUID(graph.generation_id)))
        except ValueError:
            overview = None
    if overview is not None and overview.result is not None:
        evidence = [item for item in overview.result.evidence if item.id in evidence_ids]
        paper_ids.update(item.paper_id for item in evidence)
        papers = [item for item in overview.result.papers if item.id in paper_ids]

    analysis = None
    if graph.source_analysis_id:
        analysis = storage.get_analysis(graph.source_analysis_id)
    if analysis is None:
        analysis = next(
            (
                item
                for item in storage.list_analyses()
                if item.result is not None and item.result.graph.id == graph.id
            ),
            None,
        )
    if analysis is not None and analysis.result is not None:
        analysis_evidence = [
            item for item in analysis.result.evidence
            if item.id in evidence_ids and item.id not in {card.id for card in evidence}
        ]
        evidence.extend(analysis_evidence)
        paper_ids.update(item.paper_id for item in evidence)
        paper_by_id = {item.id: item for item in papers}
        paper_by_id.update(
            (item.id, item) for item in analysis.result.papers if item.id in paper_ids
        )
        papers = list(paper_by_id.values())
    elif overview is None and (node.evidence_ids or node.paper_id or node.paper_ids):
        warnings.append("该节点的原始分析记录不可用，当前只能显示图快照中的说明。")
    if node.summary_level == "abstract_only":
        warnings.append("该节点内容来自摘要级资料，不能视为已经阅读全文。")
    elif node.summary_level == "arxiv_sections":
        warnings.append("章节证据来自开放 PDF 文本层抽取，章节边界和摘录尚未人工核验。")
    return GraphNodeDetail(
        node=node,
        papers=papers,
        evidence=evidence,
        related_edges=[
            edge for edge in graph.edges if edge.source == node_id or edge.target == node_id
        ],
        warnings=warnings,
    )


@router.patch("/graphs/{graph_id}/layout", response_model=ConceptGraph, tags=["graphs"])
def update_graph_layout(graph_id: str, payload: GraphLayoutUpdate) -> ConceptGraph:
    try:
        return graph_service.update_layout(graph_id, payload)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/graphs/{graph_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["graphs"])
def delete_graph(
    graph_id: str,
    expected_version: int | None = Query(default=None, ge=1),
) -> Response:
    """Delete a saved graph and its GraphPatch history."""

    try:
        graph_service.delete(graph_id, expected_version=expected_version)
        # The graph repository and the analysis service have separate
        # process-local caches.  SQLite already rewrites the durable snapshot
        # transactionally; this refresh prevents a warm server from serving
        # the stale ``saved`` state until its next restart.
        research_service.mark_saved_graph_deleted(graph_id)
        overview_service.mark_saved_graph_deleted(graph_id)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail="概念图不存在") from exc
    except GraphConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post(
    "/graphs/{graph_id}/agent-patch",
    response_model=GraphPatch,
    tags=["graphs"],
    summary="把自然语言图谱修改请求转换为待审批 Agent GraphPatch",
)
def propose_agent_graph_patch(
    graph_id: str,
    payload: GraphAgentPatchCreate,
) -> GraphPatch:
    """Translate a bounded natural-language request without mutating the graph.

    The returned patch is always ``actor=agent`` and ``status=proposed``.  A
    reviewer must call the normal ``apply`` or ``reject`` endpoint.  The
    service uses a transparent heuristic translator in this first version and
    records the original request plus warnings on the patch itself.
    """

    try:
        return graph_agent_patch_service.propose(graph_id, payload)
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
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
