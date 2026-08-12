from __future__ import annotations

"""Asynchronous, bounded research-direction Overview orchestration.

Overview is a staged and auditable pipeline: deterministic taxonomy planning,
provider-backed per-direction retrieval, explicit split/keep/merge/discard
decisions, bounded open-arXiv section reading, graph validation and statistics.
The worker names describe responsibilities; this implementation does not claim
that a language model or several independent model agents ran when they did
not.  Every section-reading failure falls back to an explicitly labelled
abstract summary.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import math
import re
from threading import RLock
import time
from uuid import UUID

from app.research_schemas import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EvidenceCard,
    EvidenceLocator,
    GraphNodeDetail,
    GraphNodeVisual,
    OverviewCreate,
    OverviewExpandRequest,
    OverviewJob,
    OverviewDirectionAudit,
    OverviewAgentRun,
    OverviewMetricLegend,
    OverviewResult,
    OverviewRetryDirectionRequest,
    OverviewSaveRequest,
    PaperReadingSummary,
    PaperRecord,
)
from app.services.graph_service import GraphConflict, graph_service
from app.services.overview_pipeline import (
    DirectionExpansionAgent,
    DirectionPipelineResult,
    DirectionPlan,
    DirectionResearchAgent,
    OpenArxivSectionReader,
    TopicTaxonomyPlanner,
    DirectionResearchCoordinator,
    build_search_provider,
)
from app.services.research_service import AnalysisNotFound, research_service
from app.services.research_service import _explanation_provider
from app.services.research_providers import ProviderUnavailable
from app.config import get_settings
from app.storage import storage


class OverviewNotFound(KeyError):
    pass


class OverviewUnavailable(ValueError):
    pass


def _safe_error_category(exc: Exception) -> str:
    """Return a bounded error class label without persisting provider text."""

    name = type(exc).__name__
    return name[:200] if name else "OverviewError"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _agent_run(
    *,
    role: str,
    status: str,
    execution_mode: str,
    provider: str,
    started_at: datetime,
    started_perf: float,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    model: str | None = None,
    operation: str = "initial",
    direction_key: str | None = None,
    input_paper_count: int = 0,
    output_paper_count: int = 0,
    query_count: int = 0,
    summary: str = "",
    warnings: list[str] | None = None,
    error_type: str | None = None,
) -> OverviewAgentRun:
    """Finish one safe audit record without retaining request/secret material."""

    completed_at = completed_at or _utcnow()
    return OverviewAgentRun(
        role=role,
        status=status,
        execution_mode=execution_mode,
        provider=provider or "unavailable",
        model=model,
        operation=operation,
        direction_key=direction_key,
        input_paper_count=input_paper_count,
        output_paper_count=output_paper_count,
        query_count=query_count,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=(
            max(0, duration_ms)
            if duration_ms is not None
            else max(0, round((time.perf_counter() - started_perf) * 1000))
        ),
        summary=summary,
        warnings=(warnings or [])[:20],
        error_type=error_type,
    )


def _provider_model_name(provider: object) -> str | None:
    """Expose the configured model identifier, never provider credentials."""

    value = getattr(provider, "model", None)
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:300] or None


class OverviewService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wishforge-overview")
        self._coordinators: dict[UUID, DirectionResearchCoordinator] = {}
        self._generation = 0
        # A thread cannot survive a process restart.  Make abandoned work
        # explicit instead of leaving a durable job permanently "running".
        storage.mark_unfinished_overviews_interrupted()

    def create(
        self,
        analysis_id: UUID,
        payload: OverviewCreate,
        *,
        settings=None,
    ) -> OverviewJob:
        self._eligible_analysis(analysis_id)
        existing = storage.list_overviews(str(analysis_id))
        if not payload.force_regenerate:
            reusable = next(
                (
                    item
                    for item in existing
                    if item.status in {"queued", "running", "partial", "succeeded"}
                ),
                None,
            )
            if reusable is not None:
                return reusable.model_copy(deep=True)

        job = OverviewJob(analysis_id=analysis_id, request=payload)
        with self._lock:
            generation = self._generation
            storage.save_overview(job)
        # Capture the request's live Settings object before the worker crosses
        # the thread boundary.  This preserves process-memory API-key/model
        # changes made on the settings page and also keeps FastAPI dependency
        # overrides deterministic in tests; no secret is serialized to the
        # durable Overview job.
        runtime_settings = settings or get_settings()
        self._executor.submit(self._run, job.id, generation, runtime_settings)
        return job.model_copy(deep=True)

    def get(self, overview_id: UUID) -> OverviewJob:
        job = storage.get_overview(str(overview_id))
        if job is None:
            raise OverviewNotFound(overview_id)
        return job.model_copy(deep=True)

    def list(self, analysis_id: UUID | None = None) -> list[OverviewJob]:
        """List durable Overview history, newest first."""

        jobs = storage.list_overviews(str(analysis_id) if analysis_id else None)
        return [job.model_copy(deep=True) for job in jobs]

    def mark_saved_graph_deleted(self, graph_id: str) -> None:
        """Keep Overview history reusable after its graph-library copy is removed."""

        storage.mark_overview_graph_deleted(graph_id)

    def expand(self, overview_id: UUID, payload: OverviewExpandRequest) -> OverviewJob:
        with self._lock:
            job = storage.get_overview(str(overview_id))
            if job is None or job.result is None:
                raise OverviewNotFound(overview_id)
            if job.status not in {"succeeded", "partial"}:
                raise GraphConflict("研究方向图尚未生成完成")
            graph = job.result.graph
            if payload.expected_version is not None and payload.expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {payload.expected_version}, current {graph.version}"
                )
            target = next((node for node in graph.nodes if node.id == payload.node_id), None)
            if target is None or target.role != "direction":
                raise GraphConflict("只能展开研究方向节点")
            depths = _node_depths(graph)
            target_depth = depths.get(target.id, 99)
            if target_depth >= job.request.max_depth:
                raise GraphConflict("该方向已经达到最大细分深度")
            latest_audit = _latest_direction_audit(job.result.direction_audits, target.id)
            if latest_audit is None:
                latest_audit = _inferred_direction_audit(
                    job.result,
                    target,
                    depth=target_depth,
                )
            external_outcome = None
            external_decision = None
            external_papers: list[PaperRecord] = []
            expansion_runs: list[OverviewAgentRun] = []
            if latest_audit is not None:
                coordinator = self._coordinator_for(job.id, latest_audit.provider)
                if coordinator is not None:
                    research_started_at = _utcnow()
                    research_started_perf = time.perf_counter()
                    plan = DirectionPlan(
                        key=f"{latest_audit.direction_key}-expand-{target_depth + 1}",
                        label=target.label,
                        definition=target.explanation or latest_audit.definition,
                        boundary=latest_audit.boundary,
                        query_terms=tuple(latest_audit.queries[:6]),
                        match_terms=tuple(latest_audit.match_terms[:80]),
                        seed_paper_ids=tuple(target.paper_ids[:80]),
                    )
                    seeds = [
                        paper for paper in job.result.papers
                        if paper.id in set(target.paper_ids)
                    ]
                    external_outcome = DirectionResearchAgent(coordinator.search).run(
                        plan,
                        seeds,
                        paper_limit=job.request.papers_per_direction,
                    )
                    external_decision = DirectionExpansionAgent().decide(
                        [plan], [external_outcome]
                    )[0][0]
                    external_papers = _novel_papers(
                        job.result.papers,
                        external_outcome.papers,
                        limit=max(
                            0,
                            job.request.max_total_papers - len(job.result.papers),
                        ),
                    )
                    expansion_runs.append(_agent_run(
                        role="direction_research_worker",
                        status="failed" if external_outcome.error else "succeeded",
                        execution_mode="provider_search",
                        provider=external_outcome.provider_name,
                        started_at=external_outcome.started_at or research_started_at,
                        started_perf=research_started_perf,
                        completed_at=external_outcome.completed_at,
                        duration_ms=external_outcome.duration_ms,
                        operation="expand",
                        direction_key=latest_audit.direction_key,
                        input_paper_count=len(seeds),
                        output_paper_count=len(external_outcome.papers),
                        query_count=len(plan.query_terms),
                        summary=(
                            f"按需展开方向“{target.label}”；边界筛选后保留 "
                            f"{len(external_outcome.papers)} 篇，本次新增 {len(external_papers)} 篇。"
                        ),
                        warnings=(["按需方向检索失败。"] if external_outcome.error else []),
                        error_type="DirectionSearchError" if external_outcome.error else None,
                    ))
                else:
                    unavailable_audit = latest_audit.model_copy(
                        update={
                            "operation": "expand",
                            "parent_node_id": target.id,
                            "depth": target_depth + 1,
                            "provider": "unavailable",
                            "query_scope": "unavailable",
                            "returned_count": 0,
                            "accepted_count": 0,
                            "accepted_paper_ids": [],
                            "decision": "discard",
                            "decision_reason": "后台无法安全重建该论文检索 Provider。",
                            "error": "论文检索 Provider 不可重建；未借用解释或实验 API Key。",
                            "created_at": datetime.now(timezone.utc),
                        }
                    )
                    result = job.result.model_copy(
                        update={
                            "direction_audits": [
                                *job.result.direction_audits,
                                unavailable_audit,
                            ],
                            "agent_runs": [
                                *job.result.agent_runs,
                                _agent_run(
                                    role="direction_research_worker",
                                    status="skipped",
                                    execution_mode="retained_analysis",
                                    provider="unavailable",
                                    started_at=_utcnow(),
                                    started_perf=time.perf_counter(),
                                    operation="expand",
                                    direction_key=latest_audit.direction_key,
                                    input_paper_count=len(target.paper_ids),
                                    query_count=len(latest_audit.queries),
                                    summary="按需展开未执行：后台无法安全重建论文检索 Provider。",
                                    warnings=["未借用解释、社区或实验用途的 API Key。"],
                                ),
                            ],
                            "warnings": list(dict.fromkeys([
                                *job.result.warnings,
                                "按需展开未执行：论文检索 Provider 无法在后台安全重建。",
                            ]))[:40],
                        }
                    )
                    job = job.model_copy(
                        update={
                            "status": "partial",
                            "result": result,
                            "version": job.version + 1,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                    storage.save_overview(job)
                    return job.model_copy(deep=True)
            direct_papers = [
                node
                for edge in graph.edges
                if edge.source == target.id
                for node in graph.nodes
                if node.id == edge.target and node.role == "paper"
            ]
            if not direct_papers:
                raise GraphConflict("该方向已经细分，或没有可继续归类的论文叶节点")

            candidate = graph.model_copy(deep=True)
            new_readings, new_section_evidence = _read_pipeline_papers(
                external_papers,
                defaultdict(list),
                max_workers=4,
            )
            new_readings_by_id = {reading.paper_id: reading for reading in new_readings}
            for paper in external_papers:
                paper_node = _paper_node(
                    paper,
                    new_readings_by_id[paper.id],
                    new_readings_by_id[paper.id].section_evidence,
                )
                candidate.nodes.append(paper_node)
                direct_papers.append(paper_node)
            paper_ids = {node.id for node in direct_papers}
            candidate.edges = [
                edge
                for edge in candidate.edges
                if not (edge.source == target.id and edge.target in paper_ids)
            ]
            groups: dict[str, list[ConceptNode]] = defaultdict(list)
            for paper_node in direct_papers:
                key, label = _refinement_bucket(paper_node)
                groups[f"{key}|{label}"].append(paper_node)
            # Even one paper can be made explicit as a method route.  This is
            # a structural refinement, not a claim that a broad literature
            # family has been established.
            for index, (key_label, members) in enumerate(groups.items()):
                key, label = key_label.split("|", 1)
                node_id = _unique_node_id(candidate, f"{target.id}-{key}-{index}")
                evidence_ids = list(dict.fromkeys(
                    evidence_id for member in members for evidence_id in member.evidence_ids
                ))
                candidate.nodes.append(
                    ConceptNode(
                        id=node_id,
                        label=label,
                        summary=f"按 {len(members)} 篇当前检索论文的方法线索细分。",
                        explanation="这是基于标题和摘要关键词形成的局部细分，需要人工核验方向边界。",
                        node_type="direction",
                        role="direction",
                        paper_ids=[member.paper_id for member in members if member.paper_id],
                        evidence_ids=evidence_ids,
                        confidence="low",
                        visual=_direction_visual(members),
                    )
                )
                candidate.edges.append(
                    ConceptEdge(
                        source=target.id,
                        target=node_id,
                        relation="is_a",
                        confidence="low",
                        source_kind="keyword",
                        explanation="依据当前论文标题和摘要关键词形成的细分。",
                    )
                )
                for member in members:
                    candidate.edges.append(
                        ConceptEdge(
                            source=node_id,
                            target=member.id,
                            relation="supports",
                            confidence=member.confidence,
                            source_kind="keyword",
                            evidence_ids=member.evidence_ids,
                            explanation="论文摘要与该细分方向的关键词和问题描述相符。",
                        )
                    )
            candidate.version += 1
            candidate.updated_at = datetime.now(timezone.utc)
            candidate = ConceptGraph.model_validate(candidate.model_dump())
            warnings = list(job.result.warnings)
            note = (
                "按需展开已对该方向执行专属外部检索，并结合标题/摘要关键词细分；方向边界仍需人工核验。"
                if external_outcome is not None
                else "当前 Provider 无法安全重建，按需展开仅重排已有论文；方向边界仍需人工核验。"
            )
            if note not in warnings:
                warnings.append(note)
            result = job.result.model_copy(
                update={
                    "graph": candidate,
                    "papers": [*job.result.papers, *external_papers],
                    "paper_readings": [*job.result.paper_readings, *new_readings],
                    "evidence": [*job.result.evidence, *new_section_evidence],
                    "direction_audits": [
                        *job.result.direction_audits,
                        *(_single_outcome_audit(
                            external_outcome,
                            external_decision,
                            direction_node_id=target.id,
                            parent_node_id=target.id,
                            depth=target_depth + 1,
                            operation="expand",
                            existing_paper_ids={paper.id for paper in job.result.papers},
                        ) if external_outcome and external_decision else []),
                    ],
                    "agent_runs": [*job.result.agent_runs, *expansion_runs][:300],
                    "warnings": warnings[:40],
                    "direction_count": sum(node.role == "direction" for node in candidate.nodes),
                    "paper_count": sum(node.role == "paper" for node in candidate.nodes),
                }
            )
            job = job.model_copy(
                update={
                    "status": "partial" if external_outcome and external_outcome.error else job.status,
                    "result": result,
                    "version": job.version + 1,
                    "updated_at": datetime.now(timezone.utc),
                    "save_state": "transient",
                    "saved_graph_id": None,
                }
            )
            storage.save_overview(job)
            return job.model_copy(deep=True)

    def retry_direction(
        self,
        overview_id: UUID,
        direction_key: str,
        payload: OverviewRetryDirectionRequest,
    ) -> OverviewJob:
        """Retry only the latest failed attempt for ``direction_key``."""

        with self._lock:
            job = storage.get_overview(str(overview_id))
            if job is None or job.result is None:
                raise OverviewNotFound(overview_id)
            if job.status not in {"succeeded", "partial"}:
                raise GraphConflict("研究方向图尚未生成完成")
            graph = job.result.graph
            if payload.expected_version is not None and payload.expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {payload.expected_version}, current {graph.version}"
                )
            failed = next(
                (
                    item
                    for item in reversed(job.result.direction_audits)
                    if item.direction_key == direction_key and item.error
                ),
                None,
            )
            if failed is None:
                raise GraphConflict("该方向没有可重试的失败记录")
            analysis = self._eligible_analysis(job.analysis_id)
            assert analysis.result is not None
            coordinator = self._coordinator_for(job.id, failed.provider)
            if coordinator is None:
                retry_started_at = _utcnow()
                retry_started_perf = time.perf_counter()
                attempt = failed.model_copy(
                    update={
                        "operation": "retry",
                        "provider": "unavailable",
                        "query_scope": "unavailable",
                        "returned_count": 0,
                        "accepted_count": 0,
                        "accepted_paper_ids": [],
                        "decision": "discard",
                        "decision_reason": "后台无法安全重建该论文检索 Provider。",
                        "error": "论文检索 Provider 不可重建；未借用解释或实验 API Key。",
                        "created_at": datetime.now(timezone.utc),
                    }
                )
                result = job.result.model_copy(
                    update={
                        "direction_audits": [*job.result.direction_audits, attempt],
                        "agent_runs": [
                            *job.result.agent_runs,
                            _agent_run(
                                role="direction_research_worker",
                                status="skipped",
                                execution_mode="retained_analysis",
                                provider="unavailable",
                                started_at=retry_started_at,
                                started_perf=retry_started_perf,
                                operation="retry",
                                direction_key=failed.direction_key,
                                input_paper_count=len(failed.seed_paper_ids),
                                query_count=len(failed.queries),
                                summary="失败方向重试未执行：后台无法安全重建论文检索 Provider。",
                                warnings=["未借用解释、社区或实验用途的 API Key。"],
                            ),
                        ][:300],
                        "warnings": list(dict.fromkeys([
                            *job.result.warnings,
                            "失败方向重试未执行：论文检索 Provider 无法在后台安全重建。",
                        ]))[:40],
                    }
                )
                job = job.model_copy(
                    update={
                        "result": result,
                        "version": job.version + 1,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                storage.save_overview(job)
                return job.model_copy(deep=True)

            plan = DirectionPlan(
                key=failed.direction_key,
                label=failed.label,
                definition=failed.definition,
                boundary=failed.boundary,
                query_terms=tuple(failed.queries),
                match_terms=tuple(failed.match_terms),
                seed_paper_ids=tuple(failed.seed_paper_ids),
            )
            paper_by_id = {
                paper.id: paper
                for paper in [*analysis.result.papers, *job.result.papers]
            }
            seeds = [paper_by_id[item] for item in plan.seed_paper_ids if item in paper_by_id]
            retry_started_at = _utcnow()
            retry_started_perf = time.perf_counter()
            outcome = DirectionResearchAgent(coordinator.search).run(
                plan,
                seeds[: job.request.papers_per_direction],
                paper_limit=job.request.papers_per_direction,
            )
            decision = DirectionExpansionAgent().decide([plan], [outcome])[0][0]
            existing_ids = {paper.id for paper in job.result.papers}
            new_papers = _novel_papers(
                job.result.papers,
                outcome.papers,
                limit=max(0, job.request.max_total_papers - len(job.result.papers)),
            )
            new_readings, new_section_evidence = _read_pipeline_papers(
                new_papers,
                defaultdict(list),
                max_workers=4,
            )
            candidate = graph.model_copy(deep=True)
            reading_by_id = {item.paper_id: item for item in new_readings}
            parent_id = failed.direction_node_id
            if not parent_id or not any(node.id == parent_id for node in candidate.nodes):
                parent_id = candidate.root_id
            for paper in new_papers:
                paper_node = _paper_node(
                    paper,
                    reading_by_id[paper.id],
                    reading_by_id[paper.id].section_evidence,
                )
                if any(node.id == paper_node.id for node in candidate.nodes):
                    continue
                candidate.nodes.append(paper_node)
                candidate.edges.append(
                    ConceptEdge(
                        source=parent_id,
                        target=paper_node.id,
                        relation="supports",
                        confidence=paper_node.confidence,
                        source_kind="keyword",
                        evidence_ids=paper_node.evidence_ids,
                        explanation="失败方向重试后，经专属检索和边界关键词审查接纳。",
                    )
                )
            if new_papers:
                candidate.version += 1
                candidate.updated_at = datetime.now(timezone.utc)
                _apply_recency(candidate.nodes)
                _refresh_direction_visuals(candidate.nodes, candidate.edges)
                candidate = ConceptGraph.model_validate(candidate.model_dump())
            audit = _single_outcome_audit(
                outcome,
                decision,
                direction_node_id=parent_id,
                parent_node_id=failed.parent_node_id,
                depth=failed.depth,
                operation="retry",
                existing_paper_ids=existing_ids,
            )
            audits = [*job.result.direction_audits, *audit]
            status = "partial" if _has_unresolved_audit_errors(audits) else "succeeded"
            result = job.result.model_copy(
                update={
                    "graph": candidate,
                    "papers": [*job.result.papers, *new_papers],
                    "paper_readings": [*job.result.paper_readings, *new_readings],
                    "evidence": [*job.result.evidence, *new_section_evidence],
                    "direction_audits": audits,
                    "agent_runs": [
                        *job.result.agent_runs,
                        _agent_run(
                            role="direction_research_worker",
                            status="failed" if outcome.error else "succeeded",
                            execution_mode="provider_search",
                            provider=outcome.provider_name,
                            started_at=outcome.started_at or retry_started_at,
                            started_perf=retry_started_perf,
                            completed_at=outcome.completed_at,
                            duration_ms=outcome.duration_ms,
                            operation="retry",
                            direction_key=failed.direction_key,
                            input_paper_count=len(seeds),
                            output_paper_count=len(outcome.papers),
                            query_count=len(plan.query_terms),
                            summary=(
                                f"重试方向“{failed.label}”；筛选后保留 {len(outcome.papers)} 篇，"
                                f"本次新增 {len(new_papers)} 篇。"
                            ),
                            warnings=(["方向重试检索失败。"] if outcome.error else []),
                            error_type="DirectionSearchError" if outcome.error else None,
                        ),
                    ][:300],
                    "paper_count": sum(node.role == "paper" for node in candidate.nodes),
                }
            )
            job = job.model_copy(
                update={
                    "status": status,
                    "error": None if status == "succeeded" else job.error,
                    "result": result,
                    "version": job.version + 1,
                    "save_state": "transient",
                    "saved_graph_id": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            storage.save_overview(job)
            return job.model_copy(deep=True)

    def node_detail(self, overview_id: UUID, node_id: str) -> GraphNodeDetail:
        job = self.get(overview_id)
        if job.result is None:
            raise OverviewNotFound(overview_id)
        node = next((item for item in job.result.graph.nodes if item.id == node_id), None)
        if node is None:
            raise OverviewNotFound(node_id)
        paper_ids = set(node.paper_ids)
        if node.paper_id:
            paper_ids.add(node.paper_id)
        evidence_ids = set(node.evidence_ids)
        evidence = [item for item in job.result.evidence if item.id in evidence_ids]
        paper_ids.update(item.paper_id for item in evidence)
        warnings: list[str] = []
        if node.summary_level == "abstract_only":
            warnings.append("该节点内容来自摘要级资料，不能视为已经阅读全文。")
        elif node.summary_level == "arxiv_sections":
            warnings.append("章节证据来自开放 PDF 文本层抽取，章节边界和摘录尚未人工核验。")
        return GraphNodeDetail(
            node=node,
            papers=[item for item in job.result.papers if item.id in paper_ids],
            evidence=evidence,
            related_edges=[
                edge
                for edge in job.result.graph.edges
                if edge.source == node_id or edge.target == node_id
            ],
            warnings=warnings,
        )

    def _coordinator_for(
        self,
        overview_id: UUID,
        provider_name: str,
    ) -> DirectionResearchCoordinator | None:
        coordinator = self._coordinators.get(overview_id)
        if coordinator is not None:
            return coordinator
        provider = build_search_provider(provider_name)
        if provider is None:
            return None
        coordinator = DirectionResearchCoordinator(
            provider,
            max_concurrency=4,
            minimum_interval_seconds=3.0 if provider.name == "arxiv" else 0.0,
        )
        self._coordinators[overview_id] = coordinator
        return coordinator

    def save(self, overview_id: UUID, payload: OverviewSaveRequest) -> OverviewJob:
        with self._lock:
            job = storage.get_overview(str(overview_id))
            if job is None or job.result is None:
                raise OverviewNotFound(overview_id)
            if job.status not in {"succeeded", "partial"}:
                raise GraphConflict("研究方向图尚未生成完成")
            graph = job.result.graph
            if payload.expected_version is not None and payload.expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {payload.expected_version}, current {graph.version}"
                )
            existing = storage.get_graph(graph.id)
            if existing is None:
                candidate = graph.model_copy(deep=True)
                if payload.name is not None:
                    candidate.name = payload.name
                candidate.save_state = "saved"
                saved = graph_service.save(candidate)
            else:
                # Overview may have been expanded or direction-retried after a
                # previous save.  Replace the library snapshot with the newest
                # semantic graph under CAS instead of silently returning the
                # stale copy.  Keep its version monotonic even when the
                # transient job and saved copy evolved independently.
                semantic_changed = (
                    graph.nodes != existing.nodes
                    or graph.edges != existing.edges
                    or graph.description != existing.description
                    or graph.source_scope != existing.source_scope
                    or graph.warnings != existing.warnings
                )
                desired_name = payload.name or graph.name
                if semantic_changed or desired_name != existing.name:
                    candidate = graph.model_copy(
                        deep=True,
                        update={
                            "name": desired_name,
                            "save_state": "saved",
                            "version": max(graph.version, existing.version + 1),
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                    if not storage.update_graph_if_version(candidate, existing.version):
                        latest = storage.get_graph(graph.id)
                        raise GraphConflict(
                            "研究方向图保存版本已变化，请刷新后重试"
                            + (f"（当前 v{latest.version}）" if latest else "")
                        )
                    graph_service.invalidate(graph.id)
                    saved = graph_service.get(graph.id)
                else:
                    saved = existing
            result = job.result.model_copy(update={"graph": saved})
            job = job.model_copy(
                update={
                    "result": result,
                    "save_state": "saved",
                    "saved_graph_id": saved.id,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            storage.save_overview(job)
            return job.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._coordinators.clear()

    def _eligible_analysis(self, analysis_id: UUID):
        try:
            analysis = research_service.get(analysis_id)
        except AnalysisNotFound as exc:
            raise OverviewNotFound(analysis_id) from exc
        if analysis.status != "completed" or analysis.result is None:
            raise OverviewUnavailable("分析尚未完成，不能生成研究方向图")
        if analysis.level not in {"literature", "research"}:
            raise OverviewUnavailable("快速解释模式不生成研究方向图")
        academic = [
            paper
            for paper in analysis.result.papers
            if paper.source_kind in {"academic", "demo"}
        ]
        if not academic:
            raise OverviewUnavailable("当前分析没有可用于研究方向图的有效学术论文")
        return analysis

    def _run(self, overview_id: UUID, generation: int, settings=None) -> None:
        validation_started_at: datetime | None = None
        validation_started_perf: float | None = None
        try:
            self._update(
                overview_id,
                generation,
                status="running",
                stage="direction_planning",
                progress=8,
                message="正在从主题、既有检索词和论文摘要规划候选研究方向",
            )
            job = self.get(overview_id)
            analysis = self._eligible_analysis(job.analysis_id)
            assert analysis.result is not None
            seed_papers = [
                paper
                for paper in analysis.result.papers
                if paper.source_kind in {"academic", "demo"}
            ][: job.request.max_total_papers]
            prior_queries = [
                *analysis.result.search_terms,
                *(item.query for item in analysis.result.retrieval_queries),
            ]
            taxonomy = TopicTaxonomyPlanner()
            plans: list[DirectionPlan] = []
            planner_mode = "deterministic_rule_fallback"
            planner_warning: str | None = None
            agent_runs: list[OverviewAgentRun] = []
            explanation_provider = _explanation_provider(settings or get_settings())
            model_planner = getattr(explanation_provider, "plan_research_directions", None)
            if callable(model_planner):
                model_started_at = _utcnow()
                model_started_perf = time.perf_counter()
                try:
                    raw_directions = model_planner(
                        analysis.result.concept,
                        seed_papers,
                        prior_queries,
                        max_directions=job.request.max_directions,
                    )
                    plans = taxonomy.validate_model_plans(
                        raw_directions,
                        seed_papers,
                        max_directions=job.request.max_directions,
                    )
                    if plans:
                        planner_mode = f"model:{explanation_provider.name}"
                        agent_runs.append(_agent_run(
                            role="topic_taxonomy_planner",
                            status="succeeded",
                            execution_mode="model",
                            provider=explanation_provider.name,
                            model=_provider_model_name(explanation_provider),
                            started_at=model_started_at,
                            started_perf=model_started_perf,
                            input_paper_count=len(seed_papers),
                            query_count=len(prior_queries[:12]),
                            summary=f"模型规划并通过服务端边界校验的候选方向：{len(plans)} 个。",
                        ))
                    else:
                        planner_warning = "研究方向规划模型返回内容未通过边界校验，已使用规则回退。"
                        agent_runs.append(_agent_run(
                            role="topic_taxonomy_planner",
                            status="failed",
                            execution_mode="model",
                            provider=explanation_provider.name,
                            model=_provider_model_name(explanation_provider),
                            started_at=model_started_at,
                            started_perf=model_started_perf,
                            input_paper_count=len(seed_papers),
                            query_count=len(prior_queries[:12]),
                            summary="模型请求完成，但没有产生可接纳的有界方向计划。",
                            warnings=[planner_warning],
                            error_type="ModelOutputValidationError",
                        ))
                except Exception as exc:  # a model failure must not erase a deterministic result
                    planner_warning = "研究方向规划模型不可用或输出无效，已使用规则回退。"
                    agent_runs.append(_agent_run(
                        role="topic_taxonomy_planner",
                        status="failed",
                        execution_mode="model",
                        provider=explanation_provider.name,
                        model=_provider_model_name(explanation_provider),
                        started_at=model_started_at,
                        started_perf=model_started_perf,
                        input_paper_count=len(seed_papers),
                        query_count=len(prior_queries[:12]),
                        summary="模型方向规划未完成。",
                        warnings=[planner_warning],
                            error_type=_safe_error_category(exc),
                    ))
            if not plans:
                fallback_started_at = _utcnow()
                fallback_started_perf = time.perf_counter()
                plans = taxonomy.plan(
                    analysis.result.concept,
                    seed_papers,
                    prior_queries,
                    max_directions=job.request.max_directions,
                )
                fallback_mode = (
                    "deterministic_rule_fallback"
                    if callable(model_planner)
                    else "deterministic_rule"
                )
                planner_mode = fallback_mode
                fallback_warnings = [planner_warning] if planner_warning else []
                if not callable(model_planner):
                    fallback_warnings.append("当前解释 Provider 不支持研究方向模型规划；直接执行确定性规则。")
                agent_runs.append(_agent_run(
                    role="topic_taxonomy_planner",
                    status="succeeded",
                    execution_mode=fallback_mode,
                    provider="wishforge_taxonomy_rules",
                    started_at=fallback_started_at,
                    started_perf=fallback_started_perf,
                    input_paper_count=len(seed_papers),
                    query_count=len(prior_queries[:12]),
                    summary=f"确定性分类规则生成 {len(plans)} 个候选方向。",
                    warnings=fallback_warnings,
                ))
            self._update(
                overview_id,
                generation,
                stage="direction_research",
                progress=20,
                message=f"正在并行调研 {len(plans)} 个候选方向（共享 Provider，最多并发 4）",
            )
            provider = build_search_provider(analysis.result.provider)
            if provider is None:
                research_started_at = _utcnow()
                research_started_perf = time.perf_counter()
                pipeline = _seed_only_direction_pipeline(
                    plans,
                    seed_papers,
                    papers_per_direction=job.request.papers_per_direction,
                    max_total_papers=job.request.max_total_papers,
                )
                pipeline.warnings.append(
                    "当前分析 Provider 无法在后台安全重建（可能需要论文专用 API Key）；"
                    "Overview 未发起方向级外部检索，仅使用原分析论文。"
                )
                agent_runs.append(_agent_run(
                    role="direction_research_coordinator",
                    status="partial",
                    execution_mode="retained_analysis",
                    provider="seed_only",
                    started_at=research_started_at,
                    started_perf=research_started_perf,
                    input_paper_count=len(seed_papers),
                    output_paper_count=len(pipeline.papers),
                    query_count=sum(len(plan.query_terms) for plan in plans),
                    summary="无法安全重建外部论文 Provider；仅协调原分析保留论文。",
                    warnings=[pipeline.warnings[-1]],
                ))
            else:
                interval = 3.0 if provider.name == "arxiv" else 0.0
                coordinator = DirectionResearchCoordinator(
                    provider,
                    max_concurrency=4,
                    minimum_interval_seconds=interval,
                )
                with self._lock:
                    self._coordinators[job.id] = coordinator
                research_started_at = _utcnow()
                research_started_perf = time.perf_counter()
                pipeline = coordinator.research(
                    plans,
                    seed_papers,
                    papers_per_direction=job.request.papers_per_direction,
                    max_total_papers=job.request.max_total_papers,
                )
                failed_directions = sum(bool(outcome.error) for outcome in pipeline.outcomes)
                agent_runs.append(_agent_run(
                    role="direction_research_coordinator",
                    status="partial" if pipeline.partial else "succeeded",
                    execution_mode="provider_search",
                    provider=provider.name,
                    started_at=research_started_at,
                    started_perf=research_started_perf,
                    input_paper_count=len(seed_papers),
                    output_paper_count=len(pipeline.papers),
                    query_count=sum(len(plan.query_terms) for plan in plans),
                    summary=(
                        f"共享 Provider 协调 {len(pipeline.outcomes)} 个方向工作器；"
                        f"{failed_directions} 个方向失败，保留 {len(pipeline.papers)} 篇去重论文。"
                    ),
                    warnings=pipeline.warnings,
                ))
                decision_by_key = pipeline.decision_by_key()
                for outcome in pipeline.outcomes:
                    worker_started_at = outcome.started_at or research_started_at
                    decision = decision_by_key.get(outcome.plan.key)
                    agent_runs.append(_agent_run(
                        role="direction_research_worker",
                        status="failed" if outcome.error else "succeeded",
                        execution_mode="provider_search",
                        provider=outcome.provider_name,
                        started_at=worker_started_at,
                        started_perf=research_started_perf,
                        completed_at=outcome.completed_at,
                        duration_ms=outcome.duration_ms,
                        direction_key=outcome.plan.key,
                        input_paper_count=len(outcome.plan.seed_paper_ids),
                        output_paper_count=len(outcome.papers),
                        query_count=len(outcome.plan.query_terms),
                        summary=(
                            f"方向“{outcome.plan.label}”返回 {outcome.retrieved_count} 条，"
                            f"边界筛选后保留 {len(outcome.papers)} 篇；"
                            f"决策为 {decision.decision if decision else '未生成'}。"
                        ),
                        warnings=(["方向专属检索失败；已保留其他成功方向。"] if outcome.error else []),
                        error_type="DirectionSearchError" if outcome.error else None,
                    ))
            self._update(
                overview_id,
                generation,
                stage="direction_expansion",
                progress=45,
                message=(
                    "正在审查方向边界并记录 split / keep / merge / discard 决策"
                ),
            )
            evidence_by_paper = _evidence_by_paper(analysis.result)
            self._update(
                overview_id,
                generation,
                stage="paper_reading",
                progress=56,
                message="正在读取论文；开放 arXiv PDF 优先，失败时明确退回摘要级",
            )
            reading_started_at = _utcnow()
            reading_started_perf = time.perf_counter()
            readings, section_evidence = _read_pipeline_papers(
                pipeline.papers,
                evidence_by_paper,
                max_workers=4,
            )
            reading_failures = sum(
                any("失败" in warning or "超时" in warning for warning in reading.warnings)
                for reading in readings
            )
            section_count = sum(reading.summary_level == "arxiv_sections" for reading in readings)
            agent_runs.append(_agent_run(
                role="paper_reading",
                status="partial" if reading_failures else "succeeded",
                execution_mode="document_parser",
                provider="open_arxiv_pdf_and_abstract_reader",
                started_at=reading_started_at,
                started_perf=reading_started_perf,
                input_paper_count=len(pipeline.papers),
                output_paper_count=len(readings),
                summary=(
                    f"读取 {len(readings)} 篇论文；{section_count} 篇使用开放 arXiv PDF 章节，"
                    f"其余明确保持摘要级。"
                ),
                warnings=(
                    [f"{reading_failures} 篇论文的 PDF/读取工作器失败或超时，已保留摘要级结果。"]
                    if reading_failures else []
                ),
            ))
            self._update(
                overview_id,
                generation,
                stage="direction_validation",
                progress=76,
                message="正在核对论文归属、证据范围、叶节点和有向无环结构",
            )
            result = _build_overview_result(
                job,
                analysis.result,
                pipeline=pipeline,
                readings=readings,
                section_evidence=section_evidence,
            )
            synthesis_mode = "deterministic_rule_fallback"
            synthesis_warning: str | None = None
            model_synthesizer = getattr(
                explanation_provider, "synthesize_research_overview", None
            )
            if callable(model_synthesizer):
                synthesis_started_at = _utcnow()
                synthesis_started_perf = time.perf_counter()
                try:
                    synthesis = model_synthesizer(
                        analysis.result.concept,
                        [
                            {
                                "key": plan.key,
                                "label": plan.label,
                                "definition": plan.definition,
                                "boundary": plan.boundary,
                            }
                            for plan in plans
                        ],
                        [
                            {
                                "paper_id": reading.paper_id,
                                "problem": reading.problem,
                                "method": reading.method,
                                "how_it_works": reading.how_it_works,
                                "summary_level": reading.summary_level,
                            }
                            for reading in readings
                        ],
                    )
                    if not _usable_overview_synthesis(synthesis, plans):
                        raise ValueError("模型综合结果没有可安全采用的展示字段")
                    result = _apply_overview_synthesis(result, synthesis, plans)
                    synthesis_mode = f"model:{explanation_provider.name}"
                    agent_runs.append(_agent_run(
                        role="overview_synthesis",
                        status="succeeded",
                        execution_mode="model",
                        provider=explanation_provider.name,
                        model=_provider_model_name(explanation_provider),
                        started_at=synthesis_started_at,
                        started_perf=synthesis_started_perf,
                        input_paper_count=len(readings),
                        output_paper_count=result.paper_count,
                        summary="模型仅综合已验证图结构的标题与展示说明，未新增论文或证据。",
                    ))
                except Exception as exc:  # keep the validated rule graph on model failure
                    synthesis_warning = "研究方向综合模型不可用或输出无效，已使用规则回退。"
                    agent_runs.append(_agent_run(
                        role="overview_synthesis",
                        status="failed",
                        execution_mode="model",
                        provider=explanation_provider.name,
                        model=_provider_model_name(explanation_provider),
                        started_at=synthesis_started_at,
                        started_perf=synthesis_started_perf,
                        input_paper_count=len(readings),
                        output_paper_count=result.paper_count,
                        summary="模型展示文案综合未完成；图结构保持已验证的规则结果。",
                        warnings=[synthesis_warning],
                        error_type=_safe_error_category(exc),
                    ))
            if synthesis_mode == "deterministic_rule_fallback":
                fallback_started_at = _utcnow()
                fallback_started_perf = time.perf_counter()
                fallback_mode = (
                    "deterministic_rule_fallback"
                    if callable(model_synthesizer)
                    else "deterministic_rule"
                )
                synthesis_mode = fallback_mode
                fallback_warnings = [synthesis_warning] if synthesis_warning else []
                if not callable(model_synthesizer):
                    fallback_warnings.append("当前解释 Provider 不支持 Overview 模型综合；保留确定性展示文案。")
                agent_runs.append(_agent_run(
                    role="overview_synthesis",
                    status="succeeded",
                    execution_mode=fallback_mode,
                    provider="wishforge_overview_rules",
                    started_at=fallback_started_at,
                    started_perf=fallback_started_perf,
                    input_paper_count=len(readings),
                    output_paper_count=result.paper_count,
                    summary="保留由已验证方向、论文摘要和章节证据生成的确定性展示文案。",
                    warnings=fallback_warnings,
                ))
            provenance_warnings = [
                f"TopicTaxonomyPlannerAgent={planner_mode}；OverviewSynthesisAgent={synthesis_mode}。",
                *([planner_warning] if planner_warning else []),
                *([synthesis_warning] if synthesis_warning else []),
            ]
            result = result.model_copy(
                update={
                    "warnings": list(dict.fromkeys([
                        *result.warnings,
                        *provenance_warnings,
                    ]))[:40],
                    "agent_runs": agent_runs,
                    "graph": result.graph.model_copy(
                        update={
                            "warnings": list(dict.fromkeys([
                                *result.graph.warnings,
                                *provenance_warnings,
                            ]))[:30]
                        }
                    ),
                }
            )
            # A usable partial result is persisted before the final validation
            # pass.  If a later validator fails, successful directions remain
            # inspectable instead of being erased by one local failure.
            if pipeline.partial:
                self._update(
                    overview_id,
                    generation,
                    status="partial",
                    stage="direction_validation",
                    progress=84,
                    message="部分方向检索失败；已保留成功方向，正在完成一致性检查",
                    result=result,
                    save_state="transient",
                )
            validation_started_at = _utcnow()
            validation_started_perf = time.perf_counter()
            _validate_direction_graph(result.graph, job.request.max_depth)
            agent_runs.append(_agent_run(
                role="direction_validation",
                status="succeeded",
                execution_mode="validation",
                provider="wishforge_graph_validator",
                started_at=validation_started_at,
                started_perf=validation_started_perf,
                input_paper_count=len(readings),
                output_paper_count=result.paper_count,
                summary=(
                    f"完成方向归属结果、证据范围、论文叶节点与 DAG 一致性检查；"
                    f"确认 {result.direction_count} 个方向和 {result.paper_count} 个论文叶节点。"
                ),
                warnings=(
                    ["部分方向检索失败，但成功方向的图结构通过一致性检查。"]
                    if pipeline.partial else []
                ),
            ))
            result = result.model_copy(update={"agent_runs": agent_runs})
            self._update(
                overview_id,
                generation,
                status="partial" if pipeline.partial else "succeeded",
                stage="completed",
                progress=100,
                message=(
                    f"研究方向图{'部分' if pipeline.partial else ''}生成："
                    f"{result.direction_count} 个方向，{result.paper_count} 篇论文"
                ),
                result=result,
                save_state="transient",
                updated_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001 - durable job exposes failures
            current = storage.get_overview(str(overview_id))
            if current is not None and current.result is not None:
                warnings = list(current.result.warnings)
                error_category = _safe_error_category(exc)
                warnings.append(f"最终一致性检查失败：{error_category}。")
                runs = list(current.result.agent_runs)
                if validation_started_at is not None and validation_started_perf is not None:
                    runs.append(_agent_run(
                        role="direction_validation",
                        status="failed",
                        execution_mode="validation",
                        provider="wishforge_graph_validator",
                        started_at=validation_started_at,
                        started_perf=validation_started_perf,
                        input_paper_count=len(current.result.paper_readings),
                        output_paper_count=current.result.paper_count,
                        summary="最终图结构一致性检查未通过；已保留先前可检查的部分结果。",
                        warnings=["最终图结构一致性检查未通过。"],
                        error_type=error_category,
                    ))
                partial_result = current.result.model_copy(
                    update={"warnings": warnings[:40], "agent_runs": runs[:300]}
                )
                self._update(
                    overview_id,
                    generation,
                    status="partial",
                    stage="completed",
                    progress=100,
                    message="研究方向图仅部分完成；可检查已成功结果后重试",
                    result=partial_result,
                    error=f"最终一致性检查失败：{error_category}。",
                    updated_at=datetime.now(timezone.utc),
                )
                return
            self._update(
                overview_id,
                generation,
                status="failed",
                progress=100,
                message="研究方向图生成失败",
                error=f"研究方向图生成失败：{_safe_error_category(exc)}。",
                updated_at=datetime.now(timezone.utc),
            )

    def _update(self, overview_id: UUID, generation: int, **changes: object) -> None:
        with self._lock:
            if generation != self._generation:
                return
            job = storage.get_overview(str(overview_id))
            if job is None:
                return
            if "updated_at" not in changes:
                changes["updated_at"] = datetime.now(timezone.utc)
            job = job.model_copy(update=changes)
            storage.save_overview(job)


def _build_overview_result(
    job: OverviewJob,
    analysis_result,
    *,
    pipeline: DirectionPipelineResult | None = None,
    readings: list[PaperReadingSummary] | None = None,
    section_evidence: list[EvidenceCard] | None = None,
) -> OverviewResult:
    request = job.request
    evidence_by_paper = _evidence_by_paper(analysis_result)
    if pipeline is None:
        seed_papers = [
            paper
            for paper in analysis_result.papers
            if paper.source_kind in {"academic", "demo"}
        ][: request.max_total_papers]
        plans = TopicTaxonomyPlanner().plan(
            analysis_result.concept,
            seed_papers,
            [*analysis_result.search_terms, *(item.query for item in analysis_result.retrieval_queries)],
            max_directions=request.max_directions,
        )
        pipeline = _seed_only_direction_pipeline(
            plans,
            seed_papers,
            papers_per_direction=request.papers_per_direction,
            max_total_papers=request.max_total_papers,
        )
    papers = pipeline.papers[: request.max_total_papers]
    readings = readings or [
        _read_paper_abstract(paper, evidence_by_paper[paper.id]) for paper in papers
    ]
    section_evidence = list(section_evidence or _section_evidence_from_readings(readings, papers))
    for card in section_evidence:
        evidence_by_paper[card.paper_id].append(card)
    reading_by_id = {reading.paper_id: reading for reading in readings}
    paper_by_id = {paper.id: paper for paper in papers}
    plan_by_key = pipeline.plan_by_key()
    decisions = [
        decision
        for decision in pipeline.decisions
        if decision.decision in {"split", "keep"} and decision.paper_ids
    ][: request.max_directions]

    graph_id = f"overview-{job.id}"
    root_id = "overview-root"
    root = ConceptNode(
        id=root_id,
        label=analysis_result.concept,
        summary=f"基于本次方向级检索保留的 {len(papers)} 篇学术论文生成研究方向概览。",
        explanation=(
            "方向由主题分类规划器提出，再由方向专属检索和可审计边界规则筛选；"
            "这不是完整学科分类，也没有把规则执行伪装成模型 Agent。"
        ),
        node_type="concept",
        role="root",
        paper_ids=[paper.id for paper in papers],
        evidence_ids=[card.id for card in analysis_result.evidence],
        confidence="medium" if len(papers) >= 4 else "low",
        visual=GraphNodeVisual(radius=46, heat_score=1, activity_score=1),
    )
    nodes = [root]
    edges: list[ConceptEdge] = []
    section_count = sum(reading.summary_level == "arxiv_sections" for reading in readings)
    warnings = [
        (
            f"Overview 使用 {pipeline.provider_name} 对每个候选方向执行了专属检索；"
            "这是当前 Provider、检索词与数量上限内的范围，不代表全网完整覆盖。"
            if pipeline.provider_name not in {"seed_only", "unavailable"}
            else "Overview 仅使用原分析论文，没有完成方向级外部检索；方向覆盖范围有限。"
        ),
        (
            f"{section_count}/{len(readings)} 篇论文成功抽取开放 arXiv PDF 章节；"
            "其余论文明确使用摘要级总结。PDF 文本抽取未进行 OCR，章节边界需人工核验。"
        ),
        "当前图不是完整引用网络，而是基于方向检索、论文元数据、摘要/开放章节和规则审查生成的研究关系图。",
        "方向规划、检索协调和细分判断是可审计的确定性工作器；本次未声称启动多个语言模型 Agent。",
        *pipeline.warnings,
        *pipeline.audit_lines(),
    ]
    for reading in readings:
        warnings.extend(
            f"论文[{reading.title}]：{warning}" for warning in reading.warnings
            if "失败" in warning
        )
    warnings = list(dict.fromkeys(warnings))[:40]
    if any(paper.source == "demo" or paper.source_kind == "demo" for paper in papers):
        warnings.append("演示资料不应当作为正式科学证据引用。")

    kept_paper_ids: set[str] = set()
    direction_node_ids: dict[str, str] = {}
    for direction_index, decision in enumerate(decisions):
        key = decision.direction_key
        plan = plan_by_key[key]
        group = [
            paper_by_id[paper_id]
            for paper_id in decision.paper_ids
            if paper_id in paper_by_id and paper_id in reading_by_id
        ][: request.papers_per_direction]
        if not group:
            continue
        direction_id = f"direction-{direction_index}-{_slug(key)}"
        direction_node_ids[key] = direction_id
        paper_nodes_for_visual = [_paper_node(paper, reading_by_id[paper.id], evidence_by_paper[paper.id]) for paper in group]
        direction_node = ConceptNode(
            id=direction_id,
            label=plan.label,
            summary=f"当前检索范围内包含 {len(group)} 篇论文。",
            explanation=(
                f"{plan.definition} 边界：{plan.boundary} "
                f"细分决策：{decision.decision}，{decision.reason}"
            ),
            node_type="direction",
            role="direction",
            paper_ids=[paper.id for paper in group],
            evidence_ids=list(dict.fromkeys(card.id for paper in group for card in evidence_by_paper[paper.id])),
            confidence="medium" if len(group) >= 2 else "low",
            visual=_direction_visual(paper_nodes_for_visual),
        )
        nodes.append(direction_node)
        edges.append(
            ConceptEdge(
                source=root_id,
                target=direction_id,
                relation="is_a",
                confidence="low",
                source_kind="keyword",
                explanation=(
                    f"候选方向检索词：{' | '.join(plan.query_terms)}。"
                    f"方向审查决定：{decision.decision}。"
                ),
            )
        )
        subgroups = {
            subkey: [paper_by_id[item] for item in ids if item in paper_by_id]
            for subkey, ids in decision.subgroups.items()
        }
        for sub_index, subkey in enumerate(
            sorted(
                subgroups,
                key=lambda item: (
                    -len(subgroups[item]),
                    decision.subgroup_labels.get(item, item),
                ),
            )
        ):
            subpapers = subgroups[subkey]
            if not subpapers:
                continue
            sub_id = f"{direction_id}-sub-{sub_index}-{_slug(subkey)}"
            subpaper_nodes = [
                node for node in paper_nodes_for_visual if node.paper_id in {paper.id for paper in subpapers}
            ]
            subnode = ConceptNode(
                id=sub_id,
                label=decision.subgroup_labels.get(subkey, "代表论文"),
                summary=f"由 {len(subpapers)} 篇当前范围论文支撑的论文路线。",
                explanation=(
                    "该路线由论文标题、摘要和已抽取章节的有限关键词归类；"
                    f"父方向的审计决策为 {decision.decision}，边界与命名仍需研究者复核。"
                ),
                node_type="direction",
                role="direction",
                paper_ids=[paper.id for paper in subpapers],
                evidence_ids=list(dict.fromkeys(card.id for paper in subpapers for card in evidence_by_paper[paper.id])),
                confidence="medium" if len(subpapers) >= 2 else "low",
                visual=_direction_visual(subpaper_nodes),
            )
            nodes.append(subnode)
            edges.append(
                ConceptEdge(
                    source=direction_id,
                    target=sub_id,
                    relation="is_a",
                    confidence="low",
                    source_kind="keyword",
                    explanation=(
                        "依据方向内的方法、问题或应用关键词形成。"
                        if decision.decision == "split"
                        else "为确保论文保持叶节点而建立的代表论文层，不声称这是独立研究方向。"
                    ),
                )
            )
            for paper in subpapers:
                paper_node = next(node for node in paper_nodes_for_visual if node.paper_id == paper.id)
                if paper.id in kept_paper_ids:
                    continue
                kept_paper_ids.add(paper.id)
                nodes.append(paper_node)
                edges.append(
                    ConceptEdge(
                        source=sub_id,
                        target=paper_node.id,
                        relation="supports",
                        confidence=paper_node.confidence,
                        source_kind="keyword",
                        evidence_ids=paper_node.evidence_ids,
                        explanation=(
                            "论文经该方向专属检索/种子归属与边界关键词审查后接纳；"
                            f"阅读范围为 {paper_node.summary_level}。"
                        ),
                    )
                )

    _apply_recency(nodes)
    _refresh_direction_visuals(nodes, edges)

    graph = ConceptGraph(
        id=graph_id,
        project_id=None,
        name=f"{analysis_result.concept} 研究方向图",
        description="基于当前分析论文标题、摘要和证据卡生成的有界研究方向 Overview。",
        root_id=root_id,
        graph_kind="research_direction",
        source_analysis_id=analysis_result.id,
        source_scope=(
            "arxiv_sections"
            if any(reading.summary_level == "arxiv_sections" for reading in readings)
            else "metadata_abstract"
        ),
        save_state="transient",
        generation_id=str(job.id),
        warnings=warnings[:30],
        layout_algorithm="breadthfirst",
        nodes=nodes,
        edges=edges,
    )
    legend = OverviewMetricLegend(
        heat_sources=["当前方向论文数", "当前方向较新论文比例", "可用引用数"],
    )
    overview_evidence = [
        card for card in analysis_result.evidence if card.paper_id in kept_paper_ids
    ]
    overview_evidence.extend(
        card for card in (section_evidence or []) if card.paper_id in kept_paper_ids
    )
    overview_evidence = list({card.id: card for card in overview_evidence}.values())
    return OverviewResult(
        graph=graph,
        papers=[paper for paper in papers if paper.id in kept_paper_ids],
        paper_readings=[reading for reading in readings if reading.paper_id in kept_paper_ids],
        evidence=overview_evidence,
        direction_audits=_pipeline_audits(
            pipeline,
            direction_node_ids=direction_node_ids,
            operation="initial",
        ),
        legend=legend,
        warnings=warnings,
        direction_count=sum(node.role == "direction" for node in nodes),
        paper_count=len(kept_paper_ids),
    )


def _apply_overview_synthesis(
    result: OverviewResult,
    payload: dict[str, object],
    plans: list[DirectionPlan],
) -> OverviewResult:
    """Apply only presentation text from an untrusted synthesis response."""

    if not isinstance(payload, dict):
        return result
    graph = result.graph.model_copy(deep=True)
    title = " ".join(str(payload.get("title") or "").split())[:200]
    if title:
        graph.name = title
    root_text = str(payload.get("root_explanation") or "").strip()[:5000]
    if root_text:
        root = next((node for node in graph.nodes if node.id == graph.root_id), None)
        if root is not None:
            root.explanation = root_text
    direction_text = payload.get("direction_explanations")
    plan_labels = {plan.key: plan.label for plan in plans}
    if isinstance(direction_text, dict):
        for key, explanation in direction_text.items():
            if key not in plan_labels or not isinstance(explanation, str):
                continue
            target = next(
                (
                    node for node in graph.nodes
                    if node.role == "direction" and node.label == plan_labels[key]
                ),
                None,
            )
            if target is not None and explanation.strip():
                target.explanation = explanation.strip()[:5000]
    extra_warnings = [
        " ".join(item.split())[:2000]
        for item in payload.get("warnings", [])[:8]
        if isinstance(item, str) and item.strip()
    ] if isinstance(payload.get("warnings"), list) else []
    graph = ConceptGraph.model_validate(graph.model_dump())
    return result.model_copy(
        update={
            "graph": graph,
            "warnings": list(dict.fromkeys([*result.warnings, *extra_warnings]))[:40],
        }
    )


def _usable_overview_synthesis(
    payload: object,
    plans: list[DirectionPlan],
) -> bool:
    """Return whether an untrusted model response has any bounded usable text."""

    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("title"), str) and payload["title"].strip():
        return True
    if (
        isinstance(payload.get("root_explanation"), str)
        and payload["root_explanation"].strip()
    ):
        return True
    explanations = payload.get("direction_explanations")
    if not isinstance(explanations, dict):
        return False
    allowed = {plan.key for plan in plans}
    return any(
        key in allowed and isinstance(value, str) and value.strip()
        for key, value in explanations.items()
    )


def _section_evidence_from_readings(
    readings: list[PaperReadingSummary],
    papers: list[PaperRecord],
) -> list[EvidenceCard]:
    """Collect section excerpts already attached by the bounded PDF reader."""

    allowed = {paper.id for paper in papers}
    by_id: dict[str, EvidenceCard] = {}
    for reading in readings:
        if reading.paper_id not in allowed:
            continue
        for card in reading.section_evidence:
            by_id[card.id] = card
    return list(by_id.values())


def _pipeline_audits(
    pipeline: DirectionPipelineResult,
    *,
    direction_node_ids: dict[str, str],
    operation: str,
) -> list[OverviewDirectionAudit]:
    """Persist one structured, secret-free record for every direction run."""

    decisions = pipeline.decision_by_key()
    audits: list[OverviewDirectionAudit] = []
    for outcome in pipeline.outcomes:
        plan = outcome.plan
        decision = decisions[plan.key]
        audits.append(
            OverviewDirectionAudit(
                operation=operation,
                direction_key=plan.key,
                direction_node_id=direction_node_ids.get(plan.key),
                label=plan.label,
                definition=plan.definition,
                boundary=plan.boundary,
                provider=outcome.provider_name,
                query_scope=(
                    "retained_analysis"
                    if outcome.provider_name == "seed_only"
                    else "unavailable"
                    if outcome.provider_name == "unavailable"
                    else "external_provider"
                ),
                queries=list(plan.query_terms),
                match_terms=list(plan.match_terms),
                seed_paper_ids=list(plan.seed_paper_ids),
                returned_count=outcome.retrieved_count,
                accepted_count=len(outcome.papers),
                rejected_count=outcome.rejected_count,
                truncated_count=outcome.truncated_count,
                accepted_paper_ids=[paper.id for paper in outcome.papers],
                decision=decision.decision,
                decision_reason=decision.reason,
                merge_target=decision.merge_target,
                error=outcome.error,
            )
        )
    return audits


def _latest_direction_audit(
    audits: list[OverviewDirectionAudit],
    node_id: str,
) -> OverviewDirectionAudit | None:
    return next(
        (item for item in reversed(audits) if item.direction_node_id == node_id),
        None,
    )


def _inferred_direction_audit(
    result: OverviewResult,
    node: ConceptNode,
    *,
    depth: int,
) -> OverviewDirectionAudit:
    """Build a conservative query scope for legacy/child direction nodes."""

    ancestors: list[OverviewDirectionAudit] = []
    parents = {
        edge.target: edge.source
        for edge in result.graph.edges
        if edge.relation in {"is_a", "part_of"}
    }
    current = parents.get(node.id)
    while current:
        match = _latest_direction_audit(result.direction_audits, current)
        if match is not None:
            ancestors.append(match)
            break
        current = parents.get(current)
    base = ancestors[0] if ancestors else None
    query = " ".join(node.label.split())[:160]
    match_terms = tuple(
        dict.fromkeys(
            [
                *(base.match_terms if base else []),
                *(
                    token.casefold()
                    for token in re.findall(r"[a-z][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", node.label)
                ),
            ]
        )
    )[:80]
    return OverviewDirectionAudit(
        direction_key=f"node-{_slug(node.id)}",
        direction_node_id=node.id,
        parent_node_id=parents.get(node.id),
        label=node.label,
        definition=node.explanation or node.summary,
        boundary=(base.boundary if base else "仅接纳与该方向标签和父方向边界相符的论文。"),
        depth=max(1, min(3, depth)),
        provider=base.provider if base else "unavailable",
        query_scope="unavailable",
        queries=[query],
        match_terms=list(match_terms),
        seed_paper_ids=list(node.paper_ids),
        accepted_paper_ids=list(node.paper_ids),
        accepted_count=len(node.paper_ids),
        decision="keep",
        decision_reason="从当前方向节点及最近可审计祖先构造的按需展开检索范围。",
    )


def _single_outcome_audit(
    outcome,
    decision,
    *,
    direction_node_id: str,
    parent_node_id: str | None,
    depth: int,
    operation: str,
    existing_paper_ids: set[str],
) -> list[OverviewDirectionAudit]:
    plan = outcome.plan
    accepted_ids = [paper.id for paper in outcome.papers]
    duplicate_count = sum(item in existing_paper_ids for item in accepted_ids)
    return [
        OverviewDirectionAudit(
            operation=operation,
            direction_key=plan.key,
            direction_node_id=direction_node_id,
            parent_node_id=parent_node_id,
            label=plan.label,
            definition=plan.definition,
            boundary=plan.boundary,
            depth=depth,
            provider=outcome.provider_name,
            query_scope="retained_analysis" if outcome.provider_name == "seed_only" else "external_provider",
            queries=list(plan.query_terms),
            match_terms=list(plan.match_terms),
            seed_paper_ids=list(plan.seed_paper_ids),
            returned_count=outcome.retrieved_count,
            accepted_count=len(outcome.papers),
            rejected_count=outcome.rejected_count,
            truncated_count=outcome.truncated_count,
            duplicate_count=duplicate_count,
            accepted_paper_ids=accepted_ids,
            decision=decision.decision,
            decision_reason=decision.reason,
            merge_target=decision.merge_target,
            error=outcome.error,
        )
    ]


def _paper_identity(paper: PaperRecord) -> str:
    if paper.doi:
        return f"doi:{paper.doi.casefold().strip()}"
    if paper.arxiv_id:
        return f"arxiv:{re.sub(r'v\d+$', '', paper.arxiv_id.casefold())}"
    if paper.canonical_id:
        return f"canonical:{paper.canonical_id.casefold().strip()}"
    title = re.sub(r"[^a-z0-9]+", " ", paper.title.casefold()).strip()
    return f"title:{title or paper.id.casefold()}"


def _novel_papers(
    existing: list[PaperRecord],
    candidates: list[PaperRecord],
    *,
    limit: int,
) -> list[PaperRecord]:
    known = {_paper_identity(paper) for paper in existing}
    novel: list[PaperRecord] = []
    for paper in candidates:
        identity = _paper_identity(paper)
        if identity in known:
            continue
        known.add(identity)
        novel.append(paper)
        if len(novel) >= limit:
            break
    return novel


def _has_unresolved_audit_errors(audits: list[OverviewDirectionAudit]) -> bool:
    latest: dict[str, OverviewDirectionAudit] = {}
    for audit in audits:
        latest[audit.direction_key] = audit
    return any(item.error for item in latest.values())


def _read_paper_abstract(paper: PaperRecord, evidence) -> PaperReadingSummary:
    sentences = _sentences(paper.abstract)
    problem = _first_matching(sentences, ("problem", "challenge", "limitation", "difficult", "cost", "问题", "挑战", "限制"))
    method = _first_matching(sentences, ("we propose", "we present", "we introduce", "method", "framework", "approach", "提出", "方法", "框架"))
    how = _first_matching(sentences, ("by ", "through", "using", "based on", "via ", "通过", "利用", "基于"))
    if not problem:
        problem = sentences[0] if sentences else "摘要未提供足够信息来确认论文解决的具体问题。"
    if not method:
        method = sentences[1] if len(sentences) > 1 else f"摘要仅表明论文围绕“{paper.title}”开展研究。"
    if not how:
        how = sentences[2] if len(sentences) > 2 else "摘要未提供足够的实现细节，需要阅读方法章节后确认。"
    limitation = _first_matching(sentences, ("limitation", "future work", "remain", "however", "限制", "未来工作", "仍然"))
    warnings = []
    if not paper.abstract:
        warnings.append("没有可用摘要，问题、方法和实现方式只能根据标题保守描述。")
    warnings.append("当前仅阅读摘要，未验证论文正文。")
    return PaperReadingSummary(
        paper_id=paper.id,
        title=paper.title,
        year=paper.year,
        source_url=paper.url,
        problem=problem[:3000],
        method=method[:4000],
        how_it_works=how[:4000],
        limitations=limitation[:3000] if limitation else None,
        summary_level="abstract_only",
        source_sections=["Abstract"] if paper.abstract else [],
        evidence_ids=[card.id for card in evidence],
        confidence="medium" if paper.abstract else "low",
        warnings=warnings,
    )


def _evidence_by_paper(analysis_result) -> defaultdict[str, list]:
    evidence_by_paper: defaultdict[str, list] = defaultdict(list)
    for card in analysis_result.evidence:
        evidence_by_paper[card.paper_id].append(card)
    return evidence_by_paper


def _read_pipeline_papers(
    papers: list[PaperRecord],
    evidence_by_paper,
    *,
    max_workers: int = 4,
) -> tuple[list[PaperReadingSummary], list[EvidenceCard]]:
    """Read papers in parallel while keeping deterministic result order."""

    if not papers:
        return [], []
    reader = OpenArxivSectionReader()

    def read_one(paper: PaperRecord) -> PaperReadingSummary:
        abstract = _read_paper_abstract(paper, evidence_by_paper[paper.id])
        section_result = reader.read(paper)
        if not section_result.attempted or not section_result.sections:
            warnings = list(abstract.warnings)
            warnings.extend(section_result.warnings)
            return abstract.model_copy(update={"warnings": list(dict.fromkeys(warnings))[:20]})
        section_evidence = _section_evidence_cards(
            paper,
            section_result.sections,
            pdf_url=section_result.pdf_url,
        )
        return _read_paper_sections(
            paper,
            evidence_by_paper[paper.id],
            section_result.sections,
            list(section_result.warnings),
            section_evidence=section_evidence,
        )

    by_id: dict[str, PaperReadingSummary] = {}
    workers = max(1, min(4, max_workers, len(papers)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="wishforge-paper-read") as pool:
        futures = {pool.submit(read_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                by_id[paper.id] = future.result()
            except Exception as exc:  # keep an abstract result on any local failure
                fallback = _read_paper_abstract(paper, evidence_by_paper[paper.id])
                warning = f"论文读取工作器失败，已退回摘要级：{_safe_error_category(exc)}。"
                by_id[paper.id] = fallback.model_copy(
                    update={"warnings": [*fallback.warnings, warning[:1000]][:20]}
                )
    ordered = [by_id[paper.id] for paper in papers if paper.id in by_id]
    return ordered, _section_evidence_from_readings(ordered, papers)


def _read_paper_sections(
    paper: PaperRecord,
    evidence,
    sections: dict[str, str],
    warnings: list[str],
    *,
    section_evidence: list[EvidenceCard] | None = None,
) -> PaperReadingSummary:
    """Create a conservative chapter-level card from extracted PDF text.

    This is sentence selection, not generative interpretation.  Extracted PDF
    text remains unverified. Section evidence cards are created separately by
    :func:`_section_evidence_cards` so their locator and source URL remain
    distinct from the original abstract ledger.
    """

    introduction = _sentences(sections.get("Introduction", ""))
    method_text = " ".join(
        sections.get(name, "") for name in ("Method", "Experiment") if sections.get(name)
    )
    method_sentences = _sentences(method_text)
    discussion = _sentences(
        " ".join(
            sections.get(name, "") for name in ("Discussion", "Conclusion") if sections.get(name)
        )
    )
    problem = _first_matching(
        introduction,
        ("problem", "challenge", "limitation", "bottleneck", "difficult", "cost", "问题", "挑战", "限制"),
    ) or (introduction[0] if introduction else "Introduction 未提供可可靠抽取的问题陈述。")
    method = _first_matching(
        [*introduction, *method_sentences],
        ("we propose", "we present", "we introduce", "our method", "our approach", "framework", "提出", "方法", "框架"),
    ) or (method_sentences[0] if method_sentences else "Method 章节未提供可可靠抽取的方法陈述。")
    how = _first_matching(
        method_sentences,
        ("by ", "through", "using", "based on", "via ", "consists", "comprises", "通过", "利用", "基于", "包含"),
    ) or (method_sentences[1] if len(method_sentences) > 1 else "章节文本未提供足够的实现细节。")
    limitation = _first_matching(
        discussion,
        ("limitation", "future work", "remain", "however", "限制", "未来工作", "仍然"),
    )
    present_sections = [name for name in ("Introduction", "Method", "Experiment", "Discussion", "Conclusion") if sections.get(name)]
    warnings = list(dict.fromkeys([
        *warnings,
        "章节级摘要来自开放 arXiv PDF 的文本层和句子抽取，未由模型解释，也未人工核验。",
    ]))
    return PaperReadingSummary(
        paper_id=paper.id,
        title=paper.title,
        year=paper.year,
        source_url=paper.url,
        problem=problem[:3000],
        method=method[:4000],
        how_it_works=how[:4000],
        limitations=limitation[:3000] if limitation else None,
        summary_level="arxiv_sections",
        source_sections=present_sections,
        evidence_ids=[card.id for card in [*evidence, *(section_evidence or [])]],
        section_evidence=section_evidence or [],
        confidence="medium" if {"Introduction", "Method"}.issubset(sections) else "low",
        warnings=warnings[:20],
    )


def _section_evidence_cards(
    paper: PaperRecord,
    sections: dict[str, str],
    *,
    pdf_url: str | None,
) -> list[EvidenceCard]:
    """Create bounded, explicitly unverified evidence cards from PDF text.

    The parser does not know stable page numbers after text extraction, so the
    locator records only the detected section and canonical arXiv PDF URL.  A
    short exact excerpt is retained; no page or paragraph position is invented.
    """

    cards: list[EvidenceCard] = []
    type_by_section = {
        "Introduction": "context",
        "Method": "mechanism",
        "Experiment": "result",
        "Discussion": "limitation",
        "Conclusion": "context",
    }
    for section_name in ("Introduction", "Method", "Experiment", "Discussion", "Conclusion"):
        sentences = _sentences(sections.get(section_name, ""))
        if not sentences:
            continue
        excerpt = " ".join(sentences[:2])[:1800]
        cards.append(
            EvidenceCard(
                id=f"overview-section-{_slug(paper.id)}-{_slug(section_name)}",
                paper_id=paper.id,
                claim=f"从开放 arXiv PDF 的 {section_name} 文本层抽取，尚未人工核验。",
                excerpt=excerpt,
                location=section_name,
                locator=EvidenceLocator(kind="section", section=section_name, url=pdf_url),
                evidence_type=type_by_section[section_name],
                evidence_types=[type_by_section[section_name]],
                relation="background",
                confidence="low",
                verification_status="unverified",
                source_url=pdf_url,
            )
        )
    return cards


def _seed_only_direction_pipeline(
    plans,
    seed_papers: list[PaperRecord],
    *,
    papers_per_direction: int,
    max_total_papers: int,
) -> DirectionPipelineResult:
    """Use retained papers when a background provider cannot be rebuilt."""

    class SeedProvider:
        name = "seed_only"

        def search(self, concept: str, limit: int) -> list[PaperRecord]:
            return []

    pipeline = DirectionResearchCoordinator(
        SeedProvider(),
        max_concurrency=4,
        minimum_interval_seconds=0.0,
    ).research(
        plans,
        seed_papers,
        papers_per_direction=papers_per_direction,
        max_total_papers=max_total_papers,
    )
    return pipeline


def _paper_node(paper: PaperRecord, reading: PaperReadingSummary, evidence) -> ConceptNode:
    return ConceptNode(
        id=f"paper-{_slug(paper.id)}",
        label=paper.title,
        summary=f"{reading.problem} {reading.method}"[:5000],
        explanation=f"问题：{reading.problem}\n方法：{reading.method}\n怎么做：{reading.how_it_works}"[:5000],
        node_type="paper",
        role="paper",
        paper_id=paper.id,
        paper_ids=[paper.id],
        year=paper.year,
        citation_count=paper.citation_count,
        source_url=paper.url,
        source_sections=reading.source_sections,
        summary_level=reading.summary_level,
        problem_summary=reading.problem,
        method_summary=reading.method,
        how_it_works=reading.how_it_works,
        limitations_summary=reading.limitations,
        confidence=reading.confidence,
        evidence_ids=list(dict.fromkeys([
            *reading.evidence_ids,
            *(card.id for card in evidence),
        ])),
        visual=GraphNodeVisual(radius=18),
    )


def _direction_visual(paper_nodes: list[ConceptNode]) -> GraphNodeVisual:
    if not paper_nodes:
        return GraphNodeVisual(radius=28)
    recencies = [node.visual.recency_score for node in paper_nodes]
    citations = [node.citation_count or 0 for node in paper_nodes]
    paper_count_score = min(1.0, len(paper_nodes) / 8)
    recent_ratio = sum(score >= 0.5 for score in recencies) / len(recencies)
    citation_score = math.log1p(sum(citations)) / math.log1p(max(1, sum(citations), 100))
    available = [(0.35, paper_count_score, "当前方向论文数"), (0.25, recent_ratio, "较新论文比例")]
    if any(citations):
        available.append((0.20, citation_score, "可用引用数"))
    weight = sum(item[0] for item in available)
    heat = sum(item[0] * item[1] for item in available) / weight
    heat = max(0.0, min(1.0, heat))
    return GraphNodeVisual(
        radius=28 + 36 * math.sqrt(heat),
        heat_score=heat,
        activity_score=heat,
        heat_source=[item[2] for item in available],
    )


def _apply_recency(nodes: list[ConceptNode]) -> None:
    papers = [node for node in nodes if node.role == "paper"]
    years = [node.year for node in papers if node.year is not None]
    if not years:
        for node in papers:
            node.visual.recency_score = 0.5
        return
    low, high = min(years), max(years)
    for node in papers:
        score = 0.5 if node.year is None else (node.year - low) / max(1, high - low)
        node.visual.recency_score = max(0.0, min(1.0, score))
        node.visual.radius = 14 + 8 * node.visual.recency_score


def _refresh_direction_visuals(
    nodes: list[ConceptNode], edges: list[ConceptEdge]
) -> None:
    node_by_id = {node.id: node for node in nodes}
    children = defaultdict(list)
    for edge in edges:
        children[edge.source].append(edge.target)

    def descendant_papers(node_id: str, seen: set[str] | None = None) -> list[ConceptNode]:
        seen = set() if seen is None else seen
        if node_id in seen:
            return []
        seen.add(node_id)
        found: list[ConceptNode] = []
        for child_id in children[node_id]:
            child = node_by_id[child_id]
            if child.role == "paper":
                found.append(child)
            else:
                found.extend(descendant_papers(child_id, seen))
        return found

    for node in nodes:
        if node.role == "direction":
            unique = {paper.id: paper for paper in descendant_papers(node.id)}
            node.visual = _direction_visual(list(unique.values()))


def _refinement_bucket(node: ConceptNode) -> tuple[str, str]:
    text = f"{node.label} {node.problem_summary or ''} {node.method_summary or ''}".casefold()
    rules = (
        ("systems", "系统与效率路线", ("efficien", "cache", "memory", "latency", "system", "效率", "缓存")),
        ("learning", "训练与优化路线", ("train", "learn", "optimiz", "fine-tun", "训练", "优化")),
        ("evaluation", "评测与应用路线", ("evaluat", "benchmark", "application", "评测", "应用")),
        ("architecture", "机制与架构路线", ("architect", "framework", "mechanism", "model", "架构", "机制")),
    )
    score, key, label = max(
        ((sum(text.count(term) for term in terms), key, label) for key, label, terms in rules),
        key=lambda item: item[0],
    )
    return (key, label) if score else ("paper_route", "该论文的方法路线")


def _validate_direction_graph(graph: ConceptGraph, max_depth: int) -> None:
    if graph.graph_kind != "research_direction":
        raise ValueError("Overview 必须生成 research_direction 图")
    depths = _node_depths(graph)
    if len(depths) != len(graph.nodes):
        raise ValueError("研究方向图存在孤立节点或循环")
    outgoing = defaultdict(list)
    for edge in graph.edges:
        outgoing[edge.source].append(edge.target)
    for node in graph.nodes:
        if node.role == "paper" and outgoing[node.id]:
            raise ValueError("论文只能位于叶节点")
        if node.role == "paper" and not node.paper_id:
            raise ValueError("论文叶节点必须关联 paper_id")
        if node.role == "direction" and depths[node.id] > max_depth:
            raise ValueError("研究方向图超过最大细分深度")
        if not 0 <= node.visual.heat_score <= 1 or not 0 <= node.visual.recency_score <= 1:
            raise ValueError("图视觉分数必须位于 0..1")


def _node_depths(graph: ConceptGraph) -> dict[str, int]:
    children = defaultdict(list)
    indegree = defaultdict(int)
    for edge in graph.edges:
        children[edge.source].append(edge.target)
        indegree[edge.target] += 1
    depths = {graph.root_id: 0}
    queue = [graph.root_id]
    visited = set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for child in children[current]:
            depths[child] = max(depths.get(child, 0), depths[current] + 1)
            indegree[child] -= 1
            if indegree[child] <= 0:
                queue.append(child)
    return depths


def _sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    return [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+|(?<=[。！？])", normalized) if item.strip()]


def _first_matching(sentences: list[str], terms: tuple[str, ...]) -> str:
    for sentence in sentences:
        if any(term in sentence.casefold() for term in terms):
            return sentence
    return ""


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    if normalized:
        return normalized[:80]
    return f"node-{abs(hash(value)) & 0xFFFFFFFF:x}"


def _unique_node_id(graph: ConceptGraph, base: str) -> str:
    known = {node.id for node in graph.nodes}
    candidate = _slug(base)
    index = 2
    while candidate in known:
        candidate = f"{_slug(base)}-{index}"
        index += 1
    return candidate


overview_service = OverviewService()
