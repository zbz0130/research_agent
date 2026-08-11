from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
import re
from threading import RLock
from time import perf_counter
from uuid import UUID

from app.config import Settings
from app.evidence_schemas import (
    ClaimEvidenceReview,
    ClaimEvidenceLink,
    ClaimRecord,
    EvidenceLedger,
)
from app.research_schemas import (
    AnalysisCreate,
    AnalysisJob,
    AnalysisResult,
    AnalysisStageTiming,
    AnalysisSummary,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    ConceptNodeUpdate,
    EvidenceCard,
    EvidenceLocator,
    EvolutionItem,
    ExplanationResult,
    InnovationCandidate,
    PaperRecord,
    ResearchBrief,
    ResearchGapCandidate,
    SearchQueryPlan,
    GraphOperation,
    GraphPatch,
    GraphPatchCreate,
    GraphMetadataUpdate,
)
from app.storage import storage
from app.services.graph_service import GraphConflict, graph_service
from app.services.research_orchestration import research_orchestrator
from app.services.research_providers import (
    ArxivSearchProvider,
    DemoSearchProvider,
    ExplanationProvider,
    OpenAICompatibleExplanationProvider,
    ProviderUnavailable,
    RuleBasedExplanationProvider,
    SearchProvider,
    SemanticScholarProvider,
)


logger = logging.getLogger(__name__)


class AnalysisNotFound(KeyError):
    pass


class EvidenceLinkNotFound(KeyError):
    pass


@dataclass(frozen=True)
class EvidenceMatch:
    card: EvidenceCard
    score: float
    overlap_count: int
    matched_terms: list[str]
    relation: str
    origin: str
    match_strength: str


class ResearchService:
    """Orchestrates the first concept-to-evidence analysis pipeline."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, AnalysisJob] = {}
        self._lock = RLock()
        # Tests and local callers can clear the store while an async job is
        # still finishing a provider call.  A generation token prevents that
        # stale worker from writing a graph or analysis row into the next run.
        self._generation = 0
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="wishforge-analysis")

    def create(self, payload: AnalysisCreate, settings: Settings) -> AnalysisJob:
        job = AnalysisJob(
            concept=payload.concept,
            level=payload.level,
            audience=payload.audience,
            project_id=payload.project_id,
        )
        with self._lock:
            generation = self._generation
            self._jobs[job.id] = job
            storage.save_analysis(job)
        self._executor.submit(self._run, job.id, payload, settings, generation)
        return job.model_copy(deep=True)

    def get(self, job_id: UUID) -> AnalysisJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                job = storage.get_analysis(str(job_id))
                if job is None:
                    raise AnalysisNotFound(job_id)
                self._jobs[job.id] = job
            self._sync_deleted_graph_snapshot_locked(job)
            return job.model_copy(deep=True)

    def review_evidence_link(
        self,
        job_id: UUID,
        claim_id: str,
        evidence_id: str,
        payload: ClaimEvidenceReview,
    ) -> AnalysisJob:
        """Persist a researcher's verdict on one claim-to-evidence edge."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                job = storage.get_analysis(str(job_id))
                if job is None:
                    raise AnalysisNotFound(job_id)
                self._jobs[job.id] = job
            if job.result is None or job.result.evidence_ledger is None:
                raise EvidenceLinkNotFound((claim_id, evidence_id))

            reviewed_at = datetime.now(timezone.utc)
            reviewed_claims: list[ClaimRecord] = []
            found = False
            for claim in job.result.evidence_ledger.claims:
                if claim.id != claim_id:
                    reviewed_claims.append(claim)
                    continue
                links: list[ClaimEvidenceLink] = []
                for link in claim.evidence_links:
                    if link.evidence_id != evidence_id:
                        links.append(link)
                        continue
                    found = True
                    links.append(
                        link.model_copy(
                            update={
                                "relation": payload.relation,
                                "origin": "manual",
                                "verification_status": "reviewed",
                                "review_note": payload.review_note,
                                "reviewed_by": payload.reviewed_by,
                                "reviewed_at": reviewed_at,
                            }
                        )
                    )
                reviewed_count = sum(link.verification_status == "reviewed" for link in links)
                scope = re.sub(
                    r"人工确认\s+\d+/\d+",
                    f"人工确认 {reviewed_count}/{len(links)}",
                    claim.scope,
                )
                reviewed_claims.append(claim.model_copy(update={"evidence_links": links, "scope": scope}))

            if not found:
                raise EvidenceLinkNotFound((claim_id, evidence_id))

            card_relation = {
                "supports": "supports",
                "qualifies": "qualified_support",
                "contradicts": "contradicts",
                "background": "background",
            }[payload.relation]
            reviewed_evidence = [
                card.model_copy(
                    update={
                        "relation": card_relation,
                        "verification_status": "reviewed",
                        "review_note": payload.review_note,
                        "reviewed_by": payload.reviewed_by,
                        "reviewed_at": reviewed_at,
                    }
                )
                if card.id == evidence_id
                else card
                for card in job.result.evidence
            ]
            ledger = _ledger_with_metrics(
                job.result.evidence_ledger.model_copy(update={"claims": reviewed_claims})
            )
            job.result = job.result.model_copy(
                update={"evidence": reviewed_evidence, "evidence_ledger": ledger}
            )
            storage.save_analysis(job)
            return job.model_copy(deep=True)

    def list(self) -> list[AnalysisSummary]:
        with self._lock:
            jobs = storage.list_analyses()
            self._jobs = {job.id: job for job in jobs}
            return [
                AnalysisSummary(
                    id=job.id,
                    concept=job.concept,
                    level=job.level,
                    project_id=job.project_id,
                    status=job.status,
                    progress=job.progress,
                    message=job.message,
                    created_at=job.created_at,
                )
                for job in jobs
            ]

    def _load_job_locked(self, job_id: UUID) -> AnalysisJob:
        """Load a job while the caller holds ``self._lock``."""

        job = self._jobs.get(job_id)
        if job is None:
            job = storage.get_analysis(str(job_id))
            if job is None:
                raise AnalysisNotFound(job_id)
            self._jobs[job.id] = job
        self._sync_deleted_graph_snapshot_locked(job)
        return job

    def _sync_deleted_graph_snapshot_locked(self, job: AnalysisJob) -> None:
        """Downgrade a cached saved snapshot whose library row was removed."""

        if job.result is None or job.result.graph_save_state != "saved":
            return
        saved_graph_id = job.result.saved_graph_id or job.result.graph.id
        if storage.get_graph(saved_graph_id) is not None:
            return
        transient_graph = job.result.graph.model_copy(update={"save_state": "transient"})
        job.result = job.result.model_copy(
            update={
                "graph": transient_graph,
                "graph_save_state": "transient",
                "saved_graph_id": None,
            }
        )
        self._jobs[job.id] = job

    def get_analysis_graph(self, job_id: UUID) -> ConceptGraph:
        """Return the graph snapshot embedded in an analysis result.

        This endpoint intentionally reads from the analysis document rather
        than ``concept_graphs`` so transient graphs remain available after a
        process restart and before the user elects to save them.
        """

        with self._lock:
            job = self._load_job_locked(job_id)
            if job.result is None:
                raise AnalysisNotFound(job_id)
            return job.result.graph.model_copy(deep=True)

    def update_analysis_graph_metadata(
        self,
        job_id: UUID,
        payload: GraphMetadataUpdate,
    ) -> ConceptGraph:
        """Edit metadata on a transient analysis graph with version checking."""

        with self._lock:
            job = self._load_job_locked(job_id)
            if job.result is None:
                raise AnalysisNotFound(job_id)
            graph = job.result.graph
            expected_version = payload.base_version or graph.version
            if expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {expected_version}, current {graph.version}"
                )
            candidate = graph.model_copy(deep=True)
            changes = payload.model_dump(exclude_unset=True, exclude={"base_version"})
            if "root_id" in changes and changes["root_id"] not in {
                node.id for node in candidate.nodes
            }:
                raise GraphConflict("root_id 必须指向图中的现有节点")
            for key, value in changes.items():
                setattr(candidate, key, value)
            candidate.version += 1
            candidate.updated_at = datetime.now(timezone.utc)
            # Metadata edits in the analysis view never promote the graph.
            candidate.save_state = "transient"
            candidate.source_analysis_id = str(job_id)
            candidate = ConceptGraph.model_validate(candidate.model_dump())
            job.result = job.result.model_copy(
                update={
                    "graph": candidate,
                    "graph_save_state": "transient",
                    "saved_graph_id": None,
                }
            )
            storage.save_analysis(job)
            self._jobs[job.id] = job
            return candidate.model_copy(deep=True)

    def save_analysis_graph(
        self,
        job_id: UUID,
        *,
        expected_version: int | None = None,
        name: str | None = None,
    ) -> ConceptGraph:
        """Promote an embedded analysis graph into the saved graph library.

        The graph ID is stable across retries, so calling this method more than
        once is idempotent and never creates duplicate graph rows.
        """

        with self._lock:
            job = self._load_job_locked(job_id)
            if job.result is None:
                raise AnalysisNotFound(job_id)
            graph = job.result.graph
            if expected_version is not None and expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {expected_version}, current {graph.version}"
                )

            # A retry after the graph was saved (or after a user edited the
            # saved copy through GraphPatch) must not overwrite those durable
            # edits with the older analysis snapshot.  Reuse the existing row
            # and refresh the analysis snapshot instead.
            existing = storage.get_graph(graph.id)
            if existing is not None:
                if expected_version is not None and expected_version != existing.version:
                    raise GraphConflict(
                        f"graph version changed: expected {expected_version}, current {existing.version}"
                    )
                if name is not None and name != existing.name:
                    existing = graph_service.update_metadata(
                        existing.id,
                        GraphMetadataUpdate(name=name, base_version=existing.version),
                    )
                job.result = job.result.model_copy(
                    update={
                        "graph": existing,
                        "graph_save_state": "saved",
                        "saved_graph_id": existing.id,
                    }
                )
                storage.save_analysis(job)
                self._jobs[job.id] = job
                return existing.model_copy(deep=True)

            candidate = graph.model_copy(deep=True)
            if name is not None:
                candidate.name = name
            candidate.source_analysis_id = str(job_id)
            candidate.save_state = "saved"
            saved = graph_service.save(candidate)
            job.result = job.result.model_copy(
                update={
                    "graph": saved,
                    "graph_save_state": "saved",
                    "saved_graph_id": saved.id,
                }
            )
            storage.save_analysis(job)
            self._jobs[job.id] = job
            return saved.model_copy(deep=True)

    def mark_saved_graph_deleted(self, graph_id: str) -> None:
        """Refresh cached analysis snapshots after a library graph is deleted.

        ``Storage.delete_graph`` updates durable analysis JSON in the same
        transaction as the graph deletion.  A running process may still have
        the old ``AnalysisJob`` in ``_jobs``, however; update those cached
        objects immediately so the next GET does not briefly report a graph
        that no longer exists in the saved gallery.
        """

        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.result is None:
                    continue
                graph = job.result.graph
                if graph.id != graph_id and job.result.saved_graph_id != graph_id:
                    continue
                transient_graph = graph.model_copy(update={"save_state": "transient"})
                job.result = job.result.model_copy(
                    update={
                        "graph": transient_graph,
                        "graph_save_state": "transient",
                        "saved_graph_id": None,
                    }
                )
                self._jobs[job_id] = job

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._jobs.clear()
        graph_service.clear()
        storage.clear_research()

    def propose_node_explanation(
        self,
        graph_id: str,
        node_id: str,
        settings: Settings,
        audience: str = "beginner",
        language: str = "zh-CN",
    ) -> tuple[GraphPatch, list[str]]:
        """Create an Agent GraphPatch containing a concise node explanation.

        The explanation is deliberately proposed, not written directly to the
        graph. A user must approve the patch through the normal review API.
        """

        graph = graph_service.get(graph_id)
        node = next((item for item in graph.nodes if item.id == node_id), None)
        if node is None:
            raise AnalysisNotFound(node_id)
        provider = _explanation_provider(settings)
        warnings: list[str] = []
        if (
            settings.explanation_provider in {"openai", "openai_compatible"}
            and not settings.explanation_api_key
        ):
            warnings.append("未配置解释模型 API Key，本次节点解释使用规则回退，不是外部模型回答。")
        related_papers: list[PaperRecord] = []
        related_evidence: list[EvidenceCard] = []
        # A graph node stores evidence IDs, while the graph itself deliberately
        # stays lightweight.  Recover the originating analysis document when
        # available so the explanation provider sees the same evidence that
        # is shown in the analysis view; imported/manual graphs simply use an
        # empty evidence set and are labelled as such below.
        for job in storage.list_analyses():
            if job.result is None or job.result.graph.id != graph_id:
                continue
            related_evidence = [
                card for card in job.result.evidence if card.id in set(node.evidence_ids)
            ]
            paper_ids = {card.paper_id for card in related_evidence}
            related_papers = [paper for paper in job.result.papers if paper.id in paper_ids]
            break
        if node.evidence_ids and not related_evidence:
            warnings.append("该节点的证据卡无法从当前分析记录恢复，解释仅基于节点文本。")
        try:
            explanation = provider.explain(
                node.label,
                related_papers,
                related_evidence,
                audience,
                language,
            )
        except ProviderUnavailable as exc:
            if not settings.demo_mode:
                raise
            logger.warning("Node explanation provider failed; using rule fallback: %s", exc)
            warnings.append("解释模型没有返回可用的核心内容，本次节点解释已使用规则回退。")
            provider = RuleBasedExplanationProvider()
            explanation = provider.explain(
                node.label,
                related_papers,
                related_evidence,
                audience,
                language,
            )
        warnings.extend(explanation.model_output_warnings)
        summary = explanation.one_sentence
        if explanation.intuitive:
            summary = f"{summary} {explanation.intuitive}"
        summary = summary[:5000]
        patch = GraphPatchCreate(
            actor="agent",
            base_version=graph.version,
            reason="Agent 为节点生成简洁解释，等待用户批准后写入节点说明",
            translation_mode="model"
            if provider.name not in {"rule_based", "rule_based_fallback", "demo"}
            else "heuristic",
            source_request=f"为节点“{node.label}”生成面向 {audience} 的简洁解释",
            warnings=warnings,
            operations=[
                GraphOperation(
                    op="update_node",
                    node_id=node.id,
                    updates=ConceptNodeUpdate(summary=summary),
                )
            ],
        )
        return graph_service.create_patch(graph_id, patch), warnings

    def _run(
        self,
        job_id: UUID,
        payload: AnalysisCreate,
        settings: Settings,
        generation: int | None = None,
    ) -> None:
        pipeline_started = perf_counter()
        stage_started = pipeline_started
        current_stage: tuple[str, str] | None = None
        stage_timings: list[AnalysisStageTiming] = []

        def transition(stage: str, label: str, progress: int, message: str) -> None:
            nonlocal current_stage, stage_started
            now = perf_counter()
            if current_stage is not None:
                stage_timings.append(
                    AnalysisStageTiming(
                        stage=current_stage[0],
                        label=current_stage[1],
                        duration_ms=max(0, round((now - stage_started) * 1000)),
                    )
                )
            current_stage = (stage, label)
            stage_started = now
            self._update(
                job_id,
                generation=generation,
                status="running",
                progress=progress,
                message=message,
                current_stage=stage,
                stage_timings=list(stage_timings),
            )

        def finish_current_stage() -> None:
            nonlocal current_stage, stage_started
            if current_stage is None:
                return
            now = perf_counter()
            stage_timings.append(
                AnalysisStageTiming(
                    stage=current_stage[0],
                    label=current_stage[1],
                    duration_ms=max(0, round((now - stage_started) * 1000)),
                )
            )
            current_stage = None
            stage_started = now

        try:
            if generation is None:
                with self._lock:
                    generation = self._generation
            if not self._is_generation_current(generation):
                return
            transition("query_planning", "检索词规划", 8, "正在理解概念并规划检索角度")
            warnings: list[str] = []
            search_terms: list[str] = []
            retrieval_queries: list[SearchQueryPlan] = []
            search_provider = _search_provider(settings)
            explanation_provider = _explanation_provider(settings)
            if (
                settings.explanation_provider in {"openai", "openai_compatible"}
                and not settings.explanation_api_key
            ):
                warnings.append("未配置解释模型 API Key，本次使用规则回退解释。")
            if payload.level == "quick":
                papers = []
                warnings.append("快速解释模式未检索论文，结论需要自行核验。")
            else:
                multi_planner = getattr(explanation_provider, "plan_search_queries", None)
                single_planner = getattr(explanation_provider, "plan_search_query", None)
                retrieval_queries = [SearchQueryPlan(query=payload.concept, purpose="core")]
                if callable(multi_planner):
                    try:
                        retrieval_queries = multi_planner(payload.concept, payload.language)
                    except ProviderUnavailable as exc:
                        warnings.append(str(exc))
                        warnings.append("已使用用户原始输入继续检索，中文概念可能需要改用英文术语重试。")
                elif callable(single_planner):
                    try:
                        retrieval_queries = [
                            SearchQueryPlan(
                                query=single_planner(payload.concept, payload.language),
                                purpose="core",
                            )
                        ]
                    except ProviderUnavailable as exc:
                        warnings.append(str(exc))
                        warnings.append("已使用用户原始输入继续检索，中文概念可能需要改用英文术语重试。")
                retrieval_queries = _dedupe_query_plan(retrieval_queries)[:3]
                transition(
                    "initial_paper_search",
                    "首轮 arXiv 检索",
                    22,
                    f"已规划 {len(retrieval_queries)} 个首轮检索角度，准备查询 {search_provider.name}",
                )
                paper_groups: list[list[PaperRecord]] = []
                retrieval_interrupted = False
                per_query_limit = min(
                    12,
                    max(2, math.ceil(payload.max_papers / max(1, len(retrieval_queries))) * 2),
                )
                for index, query_item in enumerate(retrieval_queries):
                    query = query_item.query
                    search_terms.append(query)
                    progress = 25 + round((index / max(1, len(retrieval_queries))) * 20)
                    self._update(
                        job_id,
                        generation=generation,
                        progress=progress,
                        message=(
                            f"首轮检索 {index + 1}/{len(retrieval_queries)}："
                            f"{query}"
                        ),
                        current_stage="initial_paper_search",
                        stage_timings=list(stage_timings),
                    )
                    try:
                        paper_groups.append(search_provider.search(query, per_query_limit))
                    except ProviderUnavailable as exc:
                        retrieval_interrupted = True
                        if not settings.demo_mode and index == 0:
                            raise
                        warnings.append(str(exc))
                        if search_provider.name != "demo" and settings.demo_mode:
                            warnings.append("已切换到演示资料；演示资料不应当作为正式科学证据引用。")
                            search_provider = DemoSearchProvider()
                            paper_groups.append(search_provider.search(query, per_query_limit))
                initial_papers = _merge_paper_groups(paper_groups, payload.max_papers)

                feedback_planner = getattr(explanation_provider, "plan_followup_queries", None)
                if initial_papers and callable(feedback_planner):
                    transition(
                        "feedback_query_planning",
                        "基于首轮摘要扩展检索词",
                        38,
                        f"正在从 {len(initial_papers)} 篇首轮论文中识别方法族和应用场景",
                    )
                    feedback_queries: list[SearchQueryPlan] = []
                    try:
                        feedback_queries = feedback_planner(
                            payload.concept,
                            initial_papers,
                            retrieval_queries,
                            payload.language,
                        )
                    except ProviderUnavailable as exc:
                        warnings.append(str(exc))
                        warnings.append("补充检索词规划失败；将尝试可追溯关键词规则。")
                    if not feedback_queries:
                        feedback_queries = RuleBasedExplanationProvider().plan_followup_queries(
                            payload.concept,
                            initial_papers,
                            retrieval_queries,
                            payload.language,
                        )
                        if feedback_queries:
                            warnings.append(
                                "摘要反馈模型未生成可用查询，已使用可追溯关键词规则补充检索词。"
                            )
                    feedback_queries = [
                        item.model_copy(update={"phase": "feedback"})
                        for item in _dedupe_query_plan(feedback_queries)
                        if item.query.casefold()
                        not in {query.query.casefold() for query in retrieval_queries}
                    ][:3]
                    if feedback_queries:
                        transition(
                            "feedback_paper_search",
                            "第二轮 arXiv 补充检索",
                            42,
                            f"已发现 {len(feedback_queries)} 个补充术语，开始第二轮检索",
                        )
                        feedback_limit = min(
                            12,
                            max(2, math.ceil(payload.max_papers / len(feedback_queries)) * 2),
                        )
                        for index, query_item in enumerate(feedback_queries):
                            search_terms.append(query_item.query)
                            self._update(
                                job_id,
                                generation=generation,
                                progress=42 + round((index / max(1, len(feedback_queries))) * 8),
                                message=(
                                    f"补充检索 {index + 1}/{len(feedback_queries)}：{query_item.query}"
                                ),
                                current_stage="feedback_paper_search",
                                stage_timings=list(stage_timings),
                            )
                            try:
                                paper_groups.append(
                                    search_provider.search(query_item.query, feedback_limit)
                                )
                            except ProviderUnavailable as exc:
                                retrieval_interrupted = True
                                warnings.append(str(exc))
                        retrieval_queries.extend(feedback_queries)
                    else:
                        warnings.append(
                            "首轮摘要未产生通过校验的补充检索词；本次未执行摘要反馈检索。"
                        )
                papers = _merge_paper_groups(paper_groups, payload.max_papers)
                if not papers:
                    if retrieval_interrupted:
                        warnings.append(
                            "论文检索因 Provider 限流或不可用而未完成，不能据此判断没有相关论文；"
                            "请根据上方 Provider 提示稍后重试、配置论文检索 API Key 或切换数据源。"
                        )
                    else:
                        warnings.append("检索没有返回论文，请尝试补充英文关键词或切换数据源。")

            transition(
                "evidence_extraction",
                "摘要证据抽取",
                52,
                f"正在从 {len(papers)} 篇论文摘要中提取分类证据",
            )
            evidence = _build_evidence(payload.concept, papers)
            transition(
                "explanation_generation",
                "分层解释生成",
                70,
                f"正在等待解释模型阅读 {len(papers)} 篇摘要并生成分层解释",
            )
            try:
                explanation = explanation_provider.explain(
                    payload.concept,
                    papers,
                    evidence,
                    payload.audience,
                    payload.language,
                )
            except ProviderUnavailable as exc:
                if not settings.demo_mode:
                    raise
                logger.warning("Explanation provider failed; using rule fallback: %s", exc)
                warnings.append("解释模型没有返回可用的核心内容，本次已使用规则回退解释。")
                explanation_provider = RuleBasedExplanationProvider()
                explanation = explanation_provider.explain(
                    payload.concept,
                    papers,
                    evidence,
                    payload.audience,
                    payload.language,
                )

            explanation, evidence = _augment_evidence_from_claim_quotes(
                explanation,
                papers,
                evidence,
            )
            explanation = _soften_unverified_strong_language(explanation)
            # Keep the explanation auditable even when a compatible model omits
            # the optional links or returns an ID that is not part of this run.
            evidence_ids = {item.id for item in evidence}
            linked_ids = [item_id for item_id in explanation.evidence_ids if item_id in evidence_ids]
            explanation = explanation.model_copy(update={"evidence_ids": linked_ids})
            explanation = _normalize_evolution_provenance(explanation, papers, evidence)

            transition(
                "concept_graph",
                "概念树与证据账本",
                86,
                "正在构建概念树并逐条匹配主张与证据",
            )
            if not self._is_generation_current(generation):
                return
            graph = _build_graph(
                payload.concept,
                papers,
                evidence,
                explanation,
                project_id=payload.project_id,
                graph_name=payload.graph_name,
            )
            # Keep the generated graph inside the analysis snapshot only.  It
            # becomes a durable graph-library row after the user confirms the
            # save action through ``POST /analyses/{id}/graph/save``.
            graph = graph.model_copy(
                update={
                    "source_analysis_id": str(job_id),
                    "save_state": "transient",
                    "source_scope": "metadata_abstract",
                }
            )
            evidence_ledger = _build_evidence_ledger(
                str(job_id),
                explanation,
                evidence,
                papers,
            )
            with self._lock:
                if generation != self._generation:
                    return
            innovation_candidates: list[InnovationCandidate] = []
            research_brief: ResearchBrief | None = None
            if payload.level == "research":
                # Research mode is intentionally a bounded fan-out: community
                # signals, model/heuristic brainstorming and paper limitation
                # extraction run concurrently, then a synthesis record joins
                # them.  A branch failure is surfaced inside the brief rather
                # than turning a missing community connector into a false
                # novelty claim.
                transition(
                    "research_agents",
                    "研究 Agent 综合",
                    90,
                    "三个研究 Agent 并行寻找痛点、脑暴和 Future Work",
                )
                baseline_candidates = _build_innovation_candidates(
                    payload.concept, papers, explanation
                )
                research_brief = research_orchestrator.run(
                    payload.concept,
                    papers,
                    evidence,
                    search_provider,
                    settings,
                    explanation_provider=explanation_provider,
                    language=payload.language,
                    existing_candidates=baseline_candidates,
                )
                innovation_candidates = research_brief.innovation_candidates
                warnings.extend(research_brief.warnings)
            finish_current_stage()
            total_duration_ms = max(0, round((perf_counter() - pipeline_started) * 1000))
            result = AnalysisResult(
                id=str(job_id),
                concept=payload.concept,
                level=payload.level,
                audience=payload.audience,
                provider=f"search={search_provider.name}; explanation={explanation_provider.name}",
                warnings=warnings,
                search_terms=search_terms,
                retrieval_queries=retrieval_queries,
                retrieval_scope=(
                    "摘要和论文元数据；先执行核心检索，再根据首轮摘要补充方法族、同义词和应用场景查询。"
                    if payload.level != "quick"
                    else "未检索论文"
                ),
                papers=papers,
                evidence=evidence,
                explanation=explanation,
                graph=graph,
                graph_save_state="transient",
                saved_graph_id=None,
                innovation_candidates=innovation_candidates,
                novelty_note=(
                    "在当前 Provider、关键词、时间和返回数量范围内未发现直接等价工作的候选，不能据此证明全球不存在相似研究。"
                    if payload.level == "research"
                    else None
                ),
                research_brief=research_brief,
                evidence_ledger=evidence_ledger,
                stage_timings=stage_timings,
                total_duration_ms=total_duration_ms,
            )
            self._update(
                job_id,
                generation=generation,
                status="completed",
                progress=100,
                message=f"分析完成，总耗时 {total_duration_ms / 1000:.1f} 秒",
                current_stage=None,
                stage_timings=stage_timings,
                result=result,
                completed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001 - job must expose failure to the UI
            finish_current_stage()
            self._update(
                job_id,
                generation=generation,
                status="failed",
                progress=100,
                message="分析失败",
                current_stage=None,
                stage_timings=stage_timings,
                error=str(exc),
                completed_at=datetime.now(timezone.utc),
            )

    def _is_generation_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    def _update(self, job_id: UUID, *, generation: int | None = None, **changes: object) -> None:
        with self._lock:
            if generation is not None and generation != self._generation:
                return
            job = self._jobs.get(job_id)
            if job is not None:
                for key, value in changes.items():
                    setattr(job, key, value)
                storage.save_analysis(job)


def _search_provider(settings: Settings) -> SearchProvider:
    if settings.paper_provider == "demo":
        return DemoSearchProvider()
    if settings.paper_provider == "arxiv":
        return ArxivSearchProvider()
    if settings.paper_provider == "semantic_scholar":
        api_key = settings.paper_api_key.get_secret_value() if settings.paper_api_key else None
        return SemanticScholarProvider(api_key=api_key)
    raise ProviderUnavailable(f"未支持的论文检索 Provider：{settings.paper_provider}")


def _explanation_provider(settings: Settings) -> ExplanationProvider:
    if settings.explanation_provider == "rule_based":
        return RuleBasedExplanationProvider()
    if settings.explanation_provider in {"openai", "openai_compatible"}:
        if not settings.explanation_api_key:
            return RuleBasedExplanationProvider()
        return OpenAICompatibleExplanationProvider(
            api_key=settings.explanation_api_key.get_secret_value(),
            base_url=settings.explanation_base_url,
            model=settings.explanation_model,
            timeout=settings.explanation_timeout_seconds,
        )
    raise ProviderUnavailable(f"未支持的解释 Provider：{settings.explanation_provider}")


def _build_evidence(concept: str, papers: list[PaperRecord]) -> list[EvidenceCard]:
    """Keep multi-label sentence candidates for later claim-driven alignment."""

    cards: list[EvidenceCard] = []
    for paper in papers:
        if not paper.abstract:
            continue
        sentences = _split_abstract_sentences(paper.abstract)
        candidates: list[tuple[str, list[str], str]] = []
        seen_sentences: set[str] = set()
        for sentence in sentences:
            normalized_sentence = _normalize_quote(sentence)
            if not normalized_sentence or normalized_sentence in seen_sentences:
                continue
            evidence_types = _classify_abstract_sentence_types(sentence)
            if not evidence_types:
                continue
            seen_sentences.add(normalized_sentence)
            primary_type = _primary_evidence_type(evidence_types)
            candidates.append((sentence, evidence_types, primary_type))
        if not candidates:
            excerpt = " ".join(sentences[:2]) or paper.abstract.strip()
            candidates.append((excerpt, ["context"], "context"))

        for excerpt, evidence_types, evidence_type in candidates[:8]:
            labels = {
                "definition": "定义",
                "mechanism": "机制或方法",
                "result": "实验结果",
                "limitation": "限制或成本",
                "future_work": "未解决问题或未来工作",
                "context": "背景",
            }
            label = "、".join(labels[item] for item in evidence_types)
            cards.append(
                EvidenceCard(
                    paper_id=paper.id,
                    claim=f"《{paper.title}》的摘要提供了与“{concept}”相关的{label}线索。",
                    excerpt=excerpt,
                    location="abstract",
                    locator=EvidenceLocator(kind="abstract", url=paper.url),
                    evidence_type=evidence_type,
                    evidence_types=evidence_types,
                    relation=("background" if evidence_type == "context" else "unclear"),
                    confidence="low" if paper.source_kind == "demo" else "medium",
                    verification_status="unverified",
                    source_url=paper.url,
                )
            )
    return cards


def _build_evidence_ledger(
    analysis_id: str,
    explanation: ExplanationResult,
    evidence: list[EvidenceCard],
    papers: list[PaperRecord],
) -> EvidenceLedger:
    """Create claim-driven links whose labels keep matching and review separate."""
    evidence_by_id = {card.id: card for card in evidence}
    paper_by_id = {paper.id: paper for paper in papers}
    claims: list[ClaimRecord] = []

    def add_claim(
        text: str,
        claim_type: str,
        *,
        preferred_evidence_ids: list[str] | None = None,
        preferred_paper_ids: list[str] | None = None,
        evidence_quotes: list[str] | None = None,
        allowed_evidence_types: set[str] | None = None,
        scope_context: str = "",
        hypothesis: bool = False,
        next_action: str = "人工核对原文和适用边界",
    ) -> None:
        text = text.strip()
        if not text:
            return
        matches = _match_claim_evidence(
            text,
            claim_type,
            evidence,
            paper_by_id,
            preferred_evidence_ids or [],
            preferred_paper_ids or [],
            evidence_quotes or [],
            allowed_evidence_types,
        )
        links = [
            ClaimEvidenceLink(
                evidence_id=match.card.id,
                relation=("background" if hypothesis else match.relation),
                note=(
                    f"系统校验：{'+'.join(match.card.evidence_types or [match.card.evidence_type])} 类型，"
                    f"重合词项 {match.overlap_count} 个，匹配分 {match.score:.2f}；"
                    "仅依据摘要，尚未人工确认关联"
                ),
                origin=match.origin,
                match_strength=match.match_strength,
                match_score=round(match.score, 4),
                matched_terms=match.matched_terms[:20],
                evidence_scope="abstract",
                verification_status="unverified",
            )
            for match in matches
        ]
        status, confidence = _claim_status_from_links(links, hypothesis=hypothesis)
        scope = _system_claim_scope(
            links,
            preferred_paper_ids or [],
            scope_context=scope_context,
        )
        claims.append(
            ClaimRecord(
                text=text,
                claim_type=claim_type,
                status=status,
                confidence=confidence,
                scope=scope,
                evidence_links=links,
                next_action=next_action,
            )
        )

    if explanation.claims:
        for draft in explanation.claims:
            add_claim(
                draft.text,
                draft.claim_type,
                preferred_evidence_ids=draft.evidence_ids,
                preferred_paper_ids=draft.paper_ids,
                evidence_quotes=draft.evidence_quotes,
                scope_context=(draft.scope if not draft.paper_ids else ""),
                next_action=(
                    "核对论文原文中的指标、基准和实验条件"
                    if draft.claim_type == "result"
                    else "核对论文原文中的方法定义、假设和适用条件"
                ),
            )
    else:
        # Compatibility path for stored results and older compatible models.
        add_claim(
            explanation.one_sentence,
            "definition",
            preferred_evidence_ids=explanation.evidence_ids,
            scope_context="通用定义",
            next_action="核对定义是否适用于当前任务和读者场景",
        )
        add_claim(
            explanation.technical,
            "mechanism",
            preferred_evidence_ids=explanation.evidence_ids,
            scope_context="兼容旧解释结果",
            next_action="回到论文方法部分，确认机制、假设和计算条件",
        )
        if explanation.evolution_items:
            for item in explanation.evolution_items[:12]:
                year_prefix = f"{item.year}：" if item.year else ""
                add_claim(
                    f"{year_prefix}{item.title}——{item.summary}",
                    "evolution",
                    preferred_evidence_ids=item.evidence_ids,
                    preferred_paper_ids=item.paper_ids,
                    scope_context="相关工作时间线",
                    next_action="核对时间线、论文版本和摘要中的实际贡献",
                )
        else:
            for item in explanation.evolution[:12]:
                add_claim(item, "evolution", next_action="核对时间线和论文版本关系")

    rejected_limitations = 0
    for item in explanation.research_limitations[:12]:
        source_papers = set(item.paper_ids)
        valid_limitation_ids = [
            evidence_id
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].paper_id in source_papers
            and set(evidence_by_id[evidence_id].evidence_types or [evidence_by_id[evidence_id].evidence_type])
            & {"limitation", "future_work"}
            and _has_explicit_negative_outcome(evidence_by_id[evidence_id].excerpt)
        ]
        if item.explicitness != "explicit" or not valid_limitation_ids:
            rejected_limitations += 1
            continue
        limitation_scope = f"对象：{item.target}"
        if item.condition:
            limitation_scope += f"；条件：{item.condition}"
        limitation_scope += f"；后果：{item.consequence}"
        add_claim(
            item.text,
            "limitation",
            preferred_evidence_ids=valid_limitation_ids,
            preferred_paper_ids=item.paper_ids,
            allowed_evidence_types={"limitation", "future_work"},
            scope_context=limitation_scope,
            next_action="阅读全文确认限制的条件、实验设置和作者原始表述",
        )

    if not explanation.claims and not explanation.research_limitations:
        for item in explanation.limitations[:12]:
            add_claim(item, "limitation", next_action="确认限制出现的实验条件和适用边界")

    for item in explanation.research_gap_candidates[:12]:
        add_claim(
            item.text,
            "research_gap",
            preferred_evidence_ids=item.evidence_ids,
            preferred_paper_ids=item.paper_ids,
            scope_context=item.scope,
            hypothesis=True,
            next_action="扩大检索范围，尝试证伪该研究空白候选",
        )

    warnings: list[str] = []
    if not evidence:
        warnings.append("本次分析没有可用证据卡；解释和相关概念只能作为模型/规则假设。")
    elif all(card.verification_status != "reviewed" for card in evidence):
        warnings.append("当前所有主张—证据关联均未人工确认；摘要关联不等于论文结论已核验。")
    if any(paper.source_kind == "demo" for paper in papers):
        warnings.append("账本中包含演示资料；演示资料不能作为正式论文证据引用。")
    if rejected_limitations:
        warnings.append(
            f"有 {rejected_limitations} 条限制候选缺少同论文的明确限制证据，未进入研究局限账本。"
        )
    unlinked_count = sum(1 for claim in claims if not claim.evidence_links)
    if unlinked_count:
        warnings.append(f"有 {unlinked_count} 条主张没有通过严格证据校验，已明确保留为无摘要关联。")
    ledger = EvidenceLedger(
        analysis_id=analysis_id,
        claims=claims,
        evidence_count=len(evidence),
        warnings=warnings,
    )
    return _ledger_with_metrics(ledger)


def _claim_status_from_links(
    links: list[ClaimEvidenceLink],
    *,
    hypothesis: bool = False,
) -> tuple[str, str]:
    if hypothesis:
        return "hypothesis", "low"
    if not links:
        return "unverified", "low"
    reviewed = [link for link in links if link.verification_status == "reviewed"]
    if any(link.relation == "contradicts" for link in reviewed):
        return "contradicted", "low"
    if not reviewed:
        return "unverified", "low"
    if len(reviewed) < len(links):
        return "partially_supported", "medium"
    if reviewed and all(link.relation == "supports" for link in reviewed):
        return "supported", "high"
    return "partially_supported", "medium"


def _system_claim_scope(
    links: list[ClaimEvidenceLink],
    preferred_paper_ids: list[str],
    *,
    scope_context: str = "",
) -> str:
    context = f"；范围：{scope_context}" if scope_context else ""
    if not links:
        if preferred_paper_ids:
            return f"指定论文摘要中未找到通过系统校验的证据{context}。"
        return f"通用知识或模型解释，尚无论文证据{context}。"
    direct = sum(link.relation == "supports" for link in links)
    qualified = sum(link.relation == "qualifies" for link in links)
    background = sum(link.relation == "background" for link in links)
    reviewed = sum(link.verification_status == "reviewed" for link in links)
    return (
        f"摘要级；{len(links)} 条系统校验关联（直接支持 {direct}、有条件支持 {qualified}、"
        f"背景 {background}）；人工确认 {reviewed}/{len(links)}{context}。"
    )


def _ledger_with_metrics(ledger: EvidenceLedger) -> EvidenceLedger:
    refreshed_claims: list[ClaimRecord] = []
    for claim in ledger.claims:
        status, confidence = _claim_status_from_links(
            claim.evidence_links,
            hypothesis=claim.claim_type in {"research_gap", "hypothesis"},
        )
        refreshed_claims.append(claim.model_copy(update={"status": status, "confidence": confidence}))

    claim_total = len(refreshed_claims)
    linked_claim_count = sum(bool(claim.evidence_links) for claim in refreshed_claims)
    direct_support_count = sum(
        any(link.relation == "supports" for link in claim.evidence_links)
        for claim in refreshed_claims
    )
    qualified_count = sum(
        bool(claim.evidence_links)
        and not any(link.relation == "supports" for link in claim.evidence_links)
        and any(link.relation == "qualifies" for link in claim.evidence_links)
        for claim in refreshed_claims
    )
    background_only_count = sum(
        bool(claim.evidence_links)
        and all(link.relation == "background" for link in claim.evidence_links)
        for claim in refreshed_claims
    )
    unlinked_count = claim_total - linked_claim_count
    verified_claim_count = sum(
        claim.status in {"supported", "partially_supported", "contradicted"}
        for claim in refreshed_claims
    )
    contradicted_count = sum(claim.status == "contradicted" for claim in refreshed_claims)
    warnings = [
        warning
        for warning in ledger.warnings
        if not warning.startswith("当前所有主张—证据关联")
        and "没有通过严格证据校验" not in warning
    ]
    if linked_claim_count and not any(
        link.verification_status == "reviewed"
        for claim in refreshed_claims
        for link in claim.evidence_links
    ):
        warnings.append("当前所有主张—证据关联均未人工确认；摘要关联不等于论文结论已核验。")
    if unlinked_count:
        warnings.append(f"有 {unlinked_count} 条主张没有通过严格证据校验，已明确保留为无摘要关联。")
    divisor = claim_total or 1
    return ledger.model_copy(
        update={
            "claims": refreshed_claims,
            "linked_claim_count": linked_claim_count,
            "coverage": round(linked_claim_count / divisor, 4),
            "link_coverage": round(linked_claim_count / divisor, 4),
            "verified_coverage": round(verified_claim_count / divisor, 4),
            "direct_support_claim_count": direct_support_count,
            "qualified_claim_count": qualified_count,
            "background_only_claim_count": background_only_count,
            "unlinked_claim_count": unlinked_count,
            "direct_support_coverage": round(direct_support_count / divisor, 4),
            "qualified_coverage": round(qualified_count / divisor, 4),
            "contradicted_claim_count": contradicted_count,
            "warnings": list(dict.fromkeys(warnings))[:30],
        }
    )


def _has_explicit_negative_outcome(text: str) -> bool:
    normalized = text.casefold()
    signals = (
        "fails to", "failure", "degrad", "impossible", "cannot", "unable to",
        "information loss", "at the cost of", "incurs overhead", "suffers from",
        "struggle to", "struggles to", "performance drop", "performance loss",
        "undesired output", "neglect the", "remains a limitation", "is a limitation",
        "drawback", "bottleneck",
        "not been investigated", "little systematic guidance", "限制", "失败", "退化",
        "无法", "不可能", "丢失", "代价", "尚未研究", "缺乏系统",
    )
    return any(signal in normalized for signal in signals)


def _dedupe_papers(papers: list[PaperRecord]) -> list[PaperRecord]:
    """Collapse provider duplicates without hiding distinct same-title works."""

    seen: set[str] = set()
    unique: list[PaperRecord] = []
    for paper in papers:
        key = (paper.canonical_id or paper.doi or paper.provider_id or paper.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    return unique


def _dedupe_query_plan(items: list[SearchQueryPlan]) -> list[SearchQueryPlan]:
    seen: set[str] = set()
    unique: list[SearchQueryPlan] = []
    for item in items:
        key = " ".join(item.query.casefold().split())
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _merge_paper_groups(groups: list[list[PaperRecord]], limit: int) -> list[PaperRecord]:
    """Round-robin query result groups so the first angle cannot dominate."""

    merged: list[PaperRecord] = []
    seen: set[str] = set()
    index = 0
    while len(merged) < limit and any(index < len(group) for group in groups):
        for group in groups:
            if index >= len(group):
                continue
            paper = group[index]
            key = (paper.canonical_id or paper.doi or paper.provider_id or paper.title).strip().casefold()
            if key and key not in seen:
                seen.add(key)
                merged.append(paper)
                if len(merged) >= limit:
                    break
        index += 1
    return merged


def _augment_evidence_from_claim_quotes(
    explanation: ExplanationResult,
    papers: list[PaperRecord],
    evidence: list[EvidenceCard],
) -> tuple[ExplanationResult, list[EvidenceCard]]:
    """Re-scan cited abstracts and materialize exact model quotes as evidence cards."""

    paper_by_id = {paper.id: paper for paper in papers}
    cards = list(evidence)
    card_by_excerpt = {
        (card.paper_id, _normalize_quote(card.excerpt)): card for card in cards
    }
    normalized_claims = []
    missing_quotes = 0
    invalid_quotes = 0
    for draft in explanation.claims:
        quote_ids: list[str] = []
        validated_quotes: list[str] = []
        for quote in draft.evidence_quotes:
            quote_key = _normalize_quote(quote)
            if len(quote_key) < 12:
                invalid_quotes += 1
                continue
            matched = False
            for paper_id in draft.paper_ids:
                paper = paper_by_id.get(paper_id)
                if paper is None:
                    continue
                for sentence in _split_abstract_sentences(paper.abstract):
                    sentence_key = _normalize_quote(sentence)
                    if not (
                        quote_key == sentence_key
                        or (len(quote_key) >= 30 and quote_key in sentence_key)
                    ):
                        continue
                    card = card_by_excerpt.get((paper_id, sentence_key))
                    if card is None:
                        evidence_types = _classify_abstract_sentence_types(sentence) or ["context"]
                        primary_type = _primary_evidence_type(evidence_types)
                        card = EvidenceCard(
                            paper_id=paper_id,
                            claim=f"《{paper.title}》摘要中与原子主张逐字对应的原句。",
                            excerpt=sentence,
                            location="abstract",
                            locator=EvidenceLocator(kind="abstract", url=paper.url),
                            evidence_type=primary_type,
                            evidence_types=evidence_types,
                            relation="unclear",
                            confidence="low" if paper.source_kind == "demo" else "medium",
                            verification_status="unverified",
                            source_url=paper.url,
                        )
                        cards.append(card)
                        card_by_excerpt[(paper_id, sentence_key)] = card
                    quote_ids.append(card.id)
                    validated_quotes.append(sentence)
                    matched = True
                    break
                if matched:
                    break
            if not matched:
                invalid_quotes += 1
        if draft.paper_ids and not draft.evidence_quotes:
            missing_quotes += 1
        normalized_claims.append(
            draft.model_copy(
                update={
                    "evidence_ids": list(dict.fromkeys([*quote_ids, *draft.evidence_ids]))[:3],
                    "evidence_quotes": list(dict.fromkeys(validated_quotes))[:3],
                }
            )
        )

    model_warnings = list(explanation.model_output_warnings)
    if missing_quotes:
        model_warnings.append(
            f"有 {missing_quotes} 条论文特定主张未提供可逐字核对的摘要原句，系统不会仅凭证据 ID 建立强关联。"
        )
    if invalid_quotes:
        model_warnings.append(
            f"有 {invalid_quotes} 条模型给出的证据原句无法在指定论文摘要中定位，已忽略。"
        )
    return explanation.model_copy(
        update={
            "claims": normalized_claims,
            "model_output_warnings": model_warnings[:20],
        }
    ), cards


def _soften_unverified_strong_language(explanation: ExplanationResult) -> ExplanationResult:
    claims = [
        draft.model_copy(update={"text": _soften_text(draft.text, draft.evidence_quotes)})
        for draft in explanation.claims
    ]
    evolution_items = [
        item.model_copy(update={"summary": _soften_text(item.summary, [])})
        for item in explanation.evolution_items
    ]
    return explanation.model_copy(update={"claims": claims, "evolution_items": evolution_items})


def _soften_text(text: str, evidence_quotes: list[str]) -> str:
    source = " ".join(evidence_quotes).casefold()
    softened = text
    if not any(token in source for token in ("first", "首次", "首个")):
        softened = softened.replace("首次提出", "提出").replace("首次", "").replace("首个", "一种")
    if not any(token in source for token in ("guarantee", "guaranteed", "保证")):
        softened = softened.replace("理论保证", "理论分析")
    if not any(token in source for token in ("optimal", "state-of-the-art", "最优")):
        softened = softened.replace("最优", "较优")
    if not any(token in source for token in ("lossless", "无损")):
        softened = softened.replace("无损", "保持性能的")
    return re.sub(r"\s+", " ", softened).strip()


def _is_atomic_claim(draft: object) -> bool:
    """Reject obvious multi-operation claims instead of citing them as one fact."""

    text = getattr(draft, "text", "")
    if len(_split_abstract_sentences(text)) > 1:
        return False
    if getattr(draft, "claim_type", "") != "mechanism":
        return True
    normalized = text.casefold()
    operation_families = (
        ("quantiz", "量化"),
        ("compress", "压缩"),
        ("evict", "淘汰"),
        ("prun", "剪枝"),
        ("retain", "保留"),
        ("select", "选择"),
        ("predict", "预测"),
        ("cluster", "聚类"),
        ("merge", "合并"),
        ("project", "投影"),
        ("discard", "丢弃"),
        ("reduc", "缩减", "降维"),
        ("shar", "共享"),
        ("reorder", "重排"),
        ("calibrat", "校准"),
        ("factor", "分解", "svd"),
        ("threshold", "阈值"),
        ("protect", "保护"),
    )
    operation_count = sum(
        any(signal in normalized for signal in family)
        for family in operation_families
    )
    return operation_count <= 1


def _normalize_evolution_provenance(
    explanation: ExplanationResult,
    papers: list[PaperRecord],
    evidence: list[EvidenceCard],
) -> ExplanationResult:
    """Keep only timeline IDs from this run and derive an auditable fallback."""

    paper_by_id = {paper.id: paper for paper in papers}
    evidence_by_id = {card.id: card for card in evidence}
    title_to_id = {paper.title.casefold(): paper.id for paper in papers}
    evidence_by_paper: dict[str, list[str]] = {}
    for card in evidence:
        evidence_by_paper.setdefault(card.paper_id, []).append(card.id)

    normalized: list[EvolutionItem] = []
    for item in explanation.evolution_items[:12]:
        valid_paper_ids = [paper_id for paper_id in item.paper_ids if paper_id in paper_by_id]
        if not valid_paper_ids:
            matched_id = title_to_id.get(item.title.casefold())
            if matched_id:
                valid_paper_ids = [matched_id]
        if not valid_paper_ids:
            continue
        valid_evidence_ids = [
            evidence_id
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].paper_id in set(valid_paper_ids)
        ]
        if not valid_evidence_ids:
            for paper_id in valid_paper_ids:
                valid_evidence_ids.extend(evidence_by_paper.get(paper_id, []))
        source_paper = paper_by_id[valid_paper_ids[0]]
        normalized.append(
            item.model_copy(
                update={
                    "year": source_paper.year if source_paper.year is not None else item.year,
                    "paper_ids": valid_paper_ids[:3],
                    "evidence_ids": list(dict.fromkeys(valid_evidence_ids))[:3],
                }
            )
        )

    if not normalized:
        for paper in sorted(papers, key=lambda item: (item.year is None, item.year or 9999))[:8]:
            matching_line = next(
                (line for line in explanation.evolution if paper.title.casefold() in line.casefold()),
                None,
            )
            normalized.append(
                EvolutionItem(
                    year=paper.year,
                    title=paper.title,
                    summary=(
                        matching_line
                        or "该论文摘要构成当前检索范围内的一条方法演变线索；具体贡献需打开原文核对。"
                    ),
                    paper_ids=[paper.id],
                    evidence_ids=evidence_by_paper.get(paper.id, [])[:3],
                )
            )
    normalized.sort(key=lambda item: (item.year is None, item.year or 9999, item.title.casefold()))

    normalized_claims = []
    rejected_non_atomic_claims = 0
    for draft in explanation.claims[:40]:
        if not _is_atomic_claim(draft):
            rejected_non_atomic_claims += 1
            continue
        valid_paper_ids = [paper_id for paper_id in draft.paper_ids if paper_id in paper_by_id]
        if draft.claim_type in {"mechanism", "result", "evolution"}:
            valid_paper_ids = valid_paper_ids[:1]
        valid_evidence_ids = [
            evidence_id
            for evidence_id in draft.evidence_ids
            if evidence_id in evidence_by_id
            and (
                not valid_paper_ids
                or evidence_by_id[evidence_id].paper_id in set(valid_paper_ids)
            )
        ]
        if not valid_paper_ids and valid_evidence_ids:
            valid_paper_ids = list(
                dict.fromkeys(evidence_by_id[evidence_id].paper_id for evidence_id in valid_evidence_ids)
            )[:3]
        normalized_claims.append(
            draft.model_copy(
                update={
                    "paper_ids": valid_paper_ids,
                    "evidence_ids": valid_evidence_ids[:3],
                }
            )
        )

    normalized_limitations = []
    for item in explanation.research_limitations[:20]:
        valid_paper_ids = [paper_id for paper_id in item.paper_ids if paper_id in paper_by_id]
        valid_evidence_ids = [
            evidence_id
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].paper_id in set(valid_paper_ids)
            and set(
                evidence_by_id[evidence_id].evidence_types
                or [evidence_by_id[evidence_id].evidence_type]
            )
            & {"limitation", "future_work"}
            and _has_explicit_negative_outcome(evidence_by_id[evidence_id].excerpt)
        ]
        if not valid_paper_ids or not valid_evidence_ids:
            continue
        normalized_limitations.append(
            item.model_copy(
                update={
                    "paper_ids": valid_paper_ids[:3],
                    "evidence_ids": valid_evidence_ids[:3],
                }
            )
        )

    normalized_gaps = []
    for item in explanation.research_gap_candidates[:20]:
        valid_paper_ids = [paper_id for paper_id in item.paper_ids if paper_id in paper_by_id]
        valid_evidence_ids = [
            evidence_id
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
            and (
                not valid_paper_ids
                or evidence_by_id[evidence_id].paper_id in set(valid_paper_ids)
            )
        ]
        normalized_gaps.append(
            item.model_copy(
                update={
                    "paper_ids": valid_paper_ids[:3],
                    "evidence_ids": valid_evidence_ids[:3],
                }
            )
        )

    normalized_checks = [
        item.model_copy(
            update={
                "paper_ids": [
                    paper_id for paper_id in item.paper_ids if paper_id in paper_by_id
                ][:3]
            }
        )
        for item in explanation.reproducibility_checks[:20]
    ]
    limitation_candidate_ids = {
        card.id
        for card in evidence
        if set(card.evidence_types or [card.evidence_type])
        & {"limitation", "future_work"}
    }
    normalized_decisions = [
        item
        for item in explanation.limitation_decisions[:30]
        if item.evidence_id in limitation_candidate_ids
    ]
    scope_warnings = list(explanation.scope_warnings)
    materialized_gap_ids = {
        evidence_id
        for item in normalized_gaps
        for evidence_id in item.evidence_ids
    }
    recovered_gap_count = 0
    for decision in normalized_decisions:
        if decision.decision != "research_gap" or decision.evidence_id in materialized_gap_ids:
            continue
        card = evidence_by_id[decision.evidence_id]
        normalized_gaps.append(
            ResearchGapCandidate(
                text=decision.reason,
                scope="仅基于本次检索到的论文摘要，需扩大检索范围进一步验证。",
                paper_ids=[card.paper_id],
                evidence_ids=[card.id],
            )
        )
        materialized_gap_ids.add(card.id)
        recovered_gap_count += 1
    dropped_limitations = len(explanation.research_limitations) - len(normalized_limitations)
    if dropped_limitations:
        scope_warnings.append(
            f"有 {dropped_limitations} 条限制候选缺少同论文的明确限制证据，未纳入研究局限。"
        )
    if rejected_non_atomic_claims:
        scope_warnings.append(
            f"有 {rejected_non_atomic_claims} 条主张同时包含多个句子或机制操作，已拒绝进入主张账本。"
        )
    decided_ids = {item.evidence_id for item in normalized_decisions}
    missing_decisions = limitation_candidate_ids - decided_ids
    if missing_decisions:
        scope_warnings.append(
            f"有 {len(missing_decisions)} 张限制候选证据卡没有获得模型接受/拒绝裁决。"
        )
    accepted_limitation_ids = {
        item.evidence_id
        for item in normalized_decisions
        if item.decision == "limitation"
    }
    materialized_limitation_ids = {
        evidence_id
        for item in normalized_limitations
        for evidence_id in item.evidence_ids
    }
    missing_accepted_limitations = accepted_limitation_ids - materialized_limitation_ids
    if missing_accepted_limitations:
        scope_warnings.append(
            f"有 {len(missing_accepted_limitations)} 张已接受的局限证据未形成合格的结构化局限。"
        )
    if recovered_gap_count:
        scope_warnings.append(
            f"有 {recovered_gap_count} 条研究空白由已验证的候选裁决补全结构字段。"
        )
    return explanation.model_copy(
        update={
            "evolution_items": normalized,
            "claims": normalized_claims,
            "research_limitations": normalized_limitations,
            "research_gap_candidates": normalized_gaps,
            "reproducibility_checks": normalized_checks,
            "limitation_decisions": normalized_decisions,
            "scope_warnings": scope_warnings[:12],
        }
    )


def _split_abstract_sentences(abstract: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", abstract).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=[。！？])", normalized)
    return [part.strip() for part in parts if part.strip()]


_ABSTRACT_TYPE_PATTERNS: dict[str, tuple[str, ...]] = {
    "future_work": (
        "future work", "future research", "further work", "remains open",
        "open problem", "next step", "not been investigated", "has not been investigated",
        "remains unexplored", "underexplored", "little systematic guidance",
        "未来工作", "后续工作", "有待研究", "仍待解决", "尚未研究", "缺乏系统指导",
    ),
    "limitation": (
        "limitation", "limited by", "trade-off", "tradeoff", "drawback",
        "fails to", "failure", "degrad", "completely ignored", "impossible",
        "cannot", "unable to", "discard", "information loss", "at the cost of",
        "incurs overhead", "suffers from", "struggle to", "struggles to",
        "performance drop", "performance loss", "undesired output", "neglect the",
        "限制", "失败", "退化", "无法", "丢失", "代价", "权衡", "性能下降",
    ),
    "result": (
        "we show", "we find", "we demonstrate", "results show", "outperform",
        "improve", "reduce", "faster", "lower memory", "accuracy", "结果", "提升", "降低", "优于",
    ),
    "mechanism": (
        "we propose", "we introduce", "we present", "architecture", "mechanism",
        "algorithm", "framework", "method", "approach", "通过", "提出", "机制", "算法", "框架", "方法",
    ),
    "definition": (
        "is a", "refers to", "defined as", "we study", "we investigate",
        "是一种", "是指", "定义为", "研究的是",
    ),
}


def _classify_abstract_sentence_types(sentence: str) -> list[str]:
    """Return every applicable label instead of letting one keyword win."""
    text = sentence.casefold()
    return [
        evidence_type
        for evidence_type in ("future_work", "limitation", "result", "mechanism", "definition")
        if any(token in text for token in _ABSTRACT_TYPE_PATTERNS[evidence_type])
    ]


def _primary_evidence_type(evidence_types: list[str]) -> str:
    """Choose a display label while retaining all labels for matching."""
    for evidence_type in ("future_work", "mechanism", "result", "limitation", "definition", "context"):
        if evidence_type in evidence_types:
            return evidence_type
    return "context"


def _classify_abstract_sentence(sentence: str) -> str | None:
    """Compatibility wrapper used by older tests and callers."""
    evidence_types = _classify_abstract_sentence_types(sentence)
    return _primary_evidence_type(evidence_types) if evidence_types else None


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


_TOKEN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "using", "based",
    "一个", "一种", "相关", "当前", "概念", "存在", "值得", "继续", "核验", "论文", "摘要",
}


def _match_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.casefold()):
        if word in _TOKEN_STOPWORDS:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)]
                break
        tokens.add(word)
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if phrase in _TOKEN_STOPWORDS:
            continue
        max_width = min(4, len(phrase))
        for width in range(2, max_width + 1):
            tokens.update(phrase[index : index + width] for index in range(len(phrase) - width + 1))
    return tokens


_TYPE_COMPATIBILITY: dict[str, dict[str, float]] = {
    "definition": {"definition": 1.8, "context": 0.9},
    "mechanism": {"mechanism": 1.8, "result": 0.45},
    "result": {"result": 1.8, "mechanism": 0.35},
    "evolution": {"mechanism": 0.8, "result": 0.9, "context": 0.35},
    "limitation": {"limitation": 2.0, "future_work": 1.2},
    "research_gap": {"future_work": 2.0, "limitation": 0.8},
    "related_concept": {},
    "hypothesis": {},
}


def _match_claim_evidence(
    claim_text: str,
    claim_type: str,
    evidence: list[EvidenceCard],
    paper_by_id: dict[str, PaperRecord],
    preferred_evidence_ids: list[str],
    preferred_paper_ids: list[str] | None = None,
    evidence_quotes: list[str] | None = None,
    allowed_evidence_types: set[str] | None = None,
) -> list[EvidenceMatch]:
    """Rank evidence only after claim-type-specific hard validation."""

    claim_tokens = _match_tokens(claim_text)
    preferred = set(preferred_evidence_ids)
    preferred_papers = set(preferred_paper_ids or [])
    quotes = [_normalize_quote(quote) for quote in evidence_quotes or [] if _normalize_quote(quote)]
    compatibility = _TYPE_COMPATIBILITY.get(claim_type, {})
    ranked: list[EvidenceMatch] = []
    for card in evidence:
        if preferred_papers and card.paper_id not in preferred_papers:
            continue
        card_types = set(card.evidence_types or [card.evidence_type])
        if allowed_evidence_types and not card_types & allowed_evidence_types:
            continue
        excerpt_tokens = _match_tokens(card.excerpt)
        matched_terms = sorted(claim_tokens & excerpt_tokens)
        overlap_count = len(matched_terms)
        quote_match = any(
            quote == _normalize_quote(card.excerpt)
            or quote in _normalize_quote(card.excerpt)
            or _normalize_quote(card.excerpt) in quote
            for quote in quotes
        )
        if not _passes_claim_evidence_gate(
            claim_text,
            claim_type,
            card,
            overlap_count=overlap_count,
            preferred=card.id in preferred,
            quote_match=quote_match,
        ):
            continue
        type_score = max((compatibility.get(item, 0.0) for item in card_types), default=0.0)
        score = min(overlap_count, 8) * 0.42 + type_score
        if card.id in preferred:
            score += 0.3
        if quote_match:
            score += 2.0
        origin = (
            "model_quote"
            if quote_match
            else "model_hint_validated"
            if card.id in preferred
            else "automatic_match"
        )
        relation = _automatic_link_relation(
            claim_type,
            card,
            quote_match=quote_match,
            preferred=card.id in preferred,
        )
        strength = "strong" if quote_match or score >= 3.0 else "moderate" if score >= 2.0 else "weak"
        ranked.append(
            EvidenceMatch(
                card=card,
                score=score,
                overlap_count=overlap_count,
                matched_terms=matched_terms,
                relation=relation,
                origin=origin,
                match_strength=strength,
            )
        )
    ranked.sort(key=lambda item: (-item.score, -item.overlap_count, item.card.id))
    return ranked[:3]


def _passes_claim_evidence_gate(
    claim_text: str,
    claim_type: str,
    card: EvidenceCard,
    *,
    overlap_count: int,
    preferred: bool,
    quote_match: bool,
) -> bool:
    card_types = set(card.evidence_types or [card.evidence_type])
    claim_numbers = _extract_numbers(claim_text)
    evidence_numbers = _extract_numbers(card.excerpt)
    numbers_match = not claim_numbers or claim_numbers <= evidence_numbers
    if claim_type == "result":
        if quote_match:
            return numbers_match
        if "result" not in card_types:
            return False
        return numbers_match if claim_numbers else quote_match
    if claim_type == "mechanism":
        if claim_numbers and not numbers_match:
            return False
        if quote_match:
            return True
        return (
            "mechanism" in card_types
            and (quote_match or (preferred and overlap_count >= 2) or overlap_count >= 4)
        )
    if claim_type == "evolution":
        return (
            numbers_match
            and bool(card_types & {"mechanism", "result"})
            and (quote_match or (preferred and overlap_count >= 1))
        )
    if claim_type == "limitation":
        return (
            bool(card_types & {"limitation", "future_work"})
            and _has_explicit_negative_outcome(card.excerpt)
            and (quote_match or preferred or overlap_count >= 3)
        )
    if claim_type == "research_gap":
        return (quote_match or preferred) and bool(card_types & {"future_work", "limitation"})
    if claim_type == "definition":
        if quote_match:
            return True
        return overlap_count >= 2 and bool(card_types & {"definition", "context"})
    return False


def _automatic_link_relation(
    claim_type: str,
    card: EvidenceCard,
    *,
    quote_match: bool,
    preferred: bool,
) -> str:
    if claim_type in {"research_gap", "hypothesis"}:
        return "background"
    if quote_match:
        return "supports"
    if claim_type == "result" and _extract_numbers(card.excerpt):
        return "supports"
    if claim_type == "limitation" and preferred and _has_explicit_negative_outcome(card.excerpt):
        return "supports"
    return "qualifies"


def _extract_numbers(text: str) -> set[str]:
    return {
        value.lstrip("0") or "0"
        for value in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text.replace(",", ""))
    }


def _build_graph(
    concept: str,
    papers: list[PaperRecord],
    evidence: list[EvidenceCard],
    explanation: ExplanationResult,
    *,
    project_id: UUID | None = None,
    graph_name: str | None = None,
) -> ConceptGraph:
    root_id = "root"
    nodes = [
        ConceptNode(
            id=root_id,
            label=concept,
            summary=explanation.one_sentence,
            node_type="concept",
            evidence_ids=[card.id for card in evidence],
        )
    ]
    edges: list[ConceptEdge] = []
    sections = [
        ("definition", "是什么", explanation.one_sentence, "concept"),
        ("mechanism", "核心机制", explanation.technical, "method"),
        ("evidence", "文献证据", "从相关论文中提取的摘要级证据。", "paper"),
        ("limitations", "限制与空白", "；".join(explanation.limitations), "problem"),
    ]
    for node_id, label, summary, node_type in sections:
        nodes.append(ConceptNode(id=node_id, label=label, summary=summary, node_type=node_type))
        edges.append(ConceptEdge(source=root_id, target=node_id, relation="is_a"))

    for index, paper in enumerate(papers[:6]):
        paper_id = f"paper-{index}-{paper.id[:16]}"
        nodes.append(
            ConceptNode(
                id=paper_id,
                label=paper.title,
                summary=f"{paper.year or '未标年份'} · {paper.venue or paper.source}",
                node_type="paper",
                evidence_ids=[card.id for card in evidence if card.paper_id == paper.id],
            )
        )
        edges.append(ConceptEdge(source="evidence", target=paper_id, relation="supports"))

    for index, related in enumerate(explanation.related_concepts[:8]):
        related_id = f"related-{index}"
        nodes.append(ConceptNode(id=related_id, label=related, summary="相关概念，可继续展开。"))
        edges.append(ConceptEdge(source=root_id, target=related_id, relation="related_to"))
    return ConceptGraph(
        project_id=project_id,
        name=graph_name or f"{concept} 概念图",
        description="由概念分析结果生成的第一版证据关联图。",
        root_id=root_id,
        nodes=nodes,
        edges=edges,
    )


def _build_innovation_candidates(
    concept: str,
    papers: list[PaperRecord],
    explanation: ExplanationResult,
) -> list[InnovationCandidate]:
    """Generate deliberately cautious, evidence-aware first-pass ideas.

    This is a transparent heuristic fallback. A later research Agent can replace
    it with a model-backed proposal, while keeping the same candidate schema and
    novelty disclaimer.
    """

    normalized = concept.lower()
    if "attention" in normalized or "注意力" in concept:
        return [
            InnovationCandidate(
                title="面向长序列的注意力缓存自适应管理",
                problem="标准注意力在长序列场景中会带来较高的计算、显存或内存访问成本。",
                mechanism="根据上下文位置或 token 重要性，动态选择缓存、压缩或淘汰策略。",
                nearest_work=[paper.title for paper in papers[:3]],
                novelty_level="L2",
                confidence="low",
                feasibility="medium",
                rationale="现有资料反复讨论长序列效率问题，但当前候选需要进一步核对 FlashAttention、PagedAttention 和稀疏注意力相关工作。",
                validation_steps=[
                    "与标准 Attention、FlashAttention 和固定缓存策略比较",
                    "在不同序列长度下记录延迟、峰值显存和结果质量",
                    "对缓存重要性估计的额外开销做消融实验",
                ],
                warning="这是待检索的研究候选，不是已确认的新颖成果。",
            )
        ]
    if "lora" in normalized or "低秩" in concept or "微调" in concept:
        return [
            InnovationCandidate(
                title="按任务难度自适应调整低秩微调容量",
                problem="固定 rank 的参数高效微调可能无法同时适配简单任务和复杂任务。",
                mechanism="根据任务难度或训练信号动态分配不同层的低秩容量。",
                nearest_work=[paper.title for paper in papers[:3]],
                novelty_level="L2",
                confidence="low",
                feasibility="medium",
                rationale="已有 LoRA 及其扩展工作提供了基础，但自适应 rank、层选择和任务难度定义需要单独核验。",
                validation_steps=[
                    "与固定 rank 的 LoRA、全量微调和 QLoRA 比较",
                    "记录可训练参数量、效果、显存和训练时间",
                    "进行不同任务难度分组的消融实验",
                ],
                warning="候选可能与已有 AdaLoRA 等方法接近，必须先完成相似工作核验。",
            )
        ]
    related = explanation.related_concepts[0] if explanation.related_concepts else concept
    return [
        InnovationCandidate(
            title=f"将 {related} 的方法用于 {concept} 的限制场景",
            problem=f"现有“{concept}”研究中的适用边界和失败条件还需要更多验证。",
            mechanism=f"借鉴“{related}”中的机制，针对一个明确的限制条件设计可复现实验。",
            nearest_work=[paper.title for paper in papers[:3]],
            novelty_level="L4",
            confidence="low",
            feasibility="low",
            rationale="当前只是基于概念关系生成的探索性假设，尚未完成完整的 prior-art 检索。",
            validation_steps=[
                "先检索该组合的中英文术语和同义表达",
                "确定基线、对照和可量化指标",
                "使用小规模数据进行可行性预实验",
            ],
            warning="不能将此候选直接表述为原创创新点。",
        )
    ]


research_service = ResearchService()
