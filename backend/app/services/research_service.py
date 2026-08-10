from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
import re
from threading import RLock
from time import perf_counter
from uuid import UUID

from app.config import Settings
from app.evidence_schemas import (
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
    SearchQueryPlan,
    GraphOperation,
    GraphPatch,
    GraphPatchCreate,
)
from app.storage import storage
from app.services.graph_service import graph_service
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
from app.services.research_orchestration import research_orchestrator


class AnalysisNotFound(KeyError):
    pass


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
            warnings.append(str(exc))
            provider = RuleBasedExplanationProvider()
            explanation = provider.explain(
                node.label,
                related_papers,
                related_evidence,
                audience,
                language,
            )
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
                if payload.level == "research":
                    # A small, bounded prior-art expansion. It is intentionally
                    # transparent and is not a claim of exhaustive novelty.
                    retrieval_queries.extend(
                        [
                            SearchQueryPlan(
                                query=f"{payload.concept} limitations future work",
                                purpose="limitations",
                            ),
                            SearchQueryPlan(
                                query=f"{payload.concept} efficient method comparison",
                                purpose="comparison",
                            ),
                        ]
                    )
                retrieval_queries = _dedupe_query_plan(retrieval_queries)[:5]
                transition(
                    "paper_search",
                    "arXiv 论文检索",
                    22,
                    f"已规划 {len(retrieval_queries)} 个检索角度，准备查询 {search_provider.name}",
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
                            f"正在通过 {search_provider.name} 检索 {index + 1}/{len(retrieval_queries)}："
                            f"{query}"
                        ),
                        current_stage="paper_search",
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
                warnings.append(str(exc))
                warnings.append("已使用规则回退解释；配置解释模型后可获得更完整的分层回答。")
                explanation_provider = RuleBasedExplanationProvider()
                explanation = explanation_provider.explain(
                    payload.concept,
                    papers,
                    evidence,
                    payload.audience,
                    payload.language,
                )

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
            evidence_ledger = _build_evidence_ledger(
                str(job_id),
                explanation,
                evidence,
                papers,
            )
            with self._lock:
                if generation != self._generation:
                    return
                graph_service.save(graph)
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
                    "摘要和论文元数据；研究模式额外检索限制、未来工作和方法对比词。"
                    if payload.level == "research"
                    else "摘要和论文元数据"
                ),
                papers=papers,
                evidence=evidence,
                explanation=explanation,
                graph=graph,
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
    """Extract a few typed, sentence-level clues from every abstract.

    The cards are deliberately smaller than the full abstract and retain the
    exact sentence text.  This lets later claim matching distinguish a result
    from a limitation instead of treating one generic paper card as support
    for every generated statement.
    """

    cards: list[EvidenceCard] = []
    for paper in papers:
        if not paper.abstract:
            continue
        sentences = _split_abstract_sentences(paper.abstract)
        typed_excerpts: dict[str, str] = {}
        for sentence in sentences:
            evidence_type = _classify_abstract_sentence(sentence)
            if evidence_type and evidence_type not in typed_excerpts:
                typed_excerpts[evidence_type] = sentence
            if len(typed_excerpts) >= 3:
                break
        if not typed_excerpts:
            typed_excerpts["context"] = " ".join(sentences[:2]) or paper.abstract.strip()

        for evidence_type, excerpt in typed_excerpts.items():
            label = {
                "definition": "定义",
                "mechanism": "机制或方法",
                "result": "实验结果",
                "limitation": "限制或成本",
                "future_work": "未解决问题或未来工作",
                "context": "背景",
            }[evidence_type]
            cards.append(
                EvidenceCard(
                    paper_id=paper.id,
                    claim=f"《{paper.title}》的摘要提供了与“{concept}”相关的{label}线索。",
                    excerpt=excerpt,
                    location="abstract",
                    locator=EvidenceLocator(kind="abstract", url=paper.url),
                    evidence_type=evidence_type,
                    relation=("background" if evidence_type == "context" else "qualified_support"),
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
    """Create a conservative claim-to-evidence view for an analysis.

    The first version often has abstract snippets rather than manually
    reviewed full text. Therefore a linked claim is not automatically called
    ``supported``: it remains ``unverified`` until the underlying evidence
    card is reviewed.
    """

    evidence_by_id = {card.id: card for card in evidence}
    paper_by_id = {paper.id: paper for paper in papers}
    claims: list[ClaimRecord] = []

    def claim_status(linked_ids: list[str], *, hypothesis: bool = False) -> tuple[str, str]:
        if hypothesis or not linked_ids:
            return ("hypothesis" if hypothesis else "unverified"), "low"
        linked_cards = [evidence_by_id[item] for item in linked_ids]
        if any(card.relation == "contradicts" for card in linked_cards):
            return "contradicted", "low"
        if any(card.relation == "qualified_support" for card in linked_cards):
            reviewed = any(card.verification_status == "reviewed" for card in linked_cards)
            return ("partially_supported", "medium") if reviewed else ("unverified", "low")
        reviewed_cards = [card for card in linked_cards if card.verification_status == "reviewed"]
        if len(reviewed_cards) == len(linked_cards):
            confidence = "high" if all(card.confidence == "high" for card in linked_cards) else "medium"
            return "supported", confidence
        if reviewed_cards:
            return "partially_supported", "medium" if any(card.confidence in {"high", "medium"} for card in reviewed_cards) else "low"
        return "unverified", "medium" if any(card.confidence == "medium" for card in linked_cards) else "low"

    def add_claim(
        text: str,
        claim_type: str,
        *,
        preferred_evidence_ids: list[str] | None = None,
        scope: str = "",
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
        )
        linked_ids = [card.id for card, _, _ in matches]
        hypothesis = hypothesis and not linked_ids
        status, confidence = claim_status(linked_ids, hypothesis=hypothesis)
        links: list[ClaimEvidenceLink] = []
        for card, score, overlap_count in matches:
            relation = {
                "supports": "supports",
                "contradicts": "contradicts",
                "qualified_support": "qualifies",
                "background": "background",
                "unclear": "background",
            }[card.relation]
            links.append(
                ClaimEvidenceLink(
                    evidence_id=card.id,
                    relation=relation,
                    note=(
                        f"自动匹配：{card.evidence_type} 类型，重合词项 {overlap_count} 个，"
                        f"相关度 {score:.2f}；摘要级，尚未全文核验"
                    ),
                )
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

    add_claim(
        explanation.one_sentence,
        "definition",
        preferred_evidence_ids=explanation.evidence_ids,
        next_action="核对定义是否适用于当前任务和读者场景",
    )
    add_claim(
        explanation.technical,
        "mechanism",
        preferred_evidence_ids=explanation.evidence_ids,
        next_action="回到论文方法部分，确认机制、假设和计算条件",
    )
    if explanation.evolution_items:
        for item in explanation.evolution_items[:12]:
            year_prefix = f"{item.year}：" if item.year else ""
            add_claim(
                f"{year_prefix}{item.title}——{item.summary}",
                "evolution",
                preferred_evidence_ids=item.evidence_ids,
                next_action="核对时间线、论文版本和摘要中的实际贡献",
            )
    else:
        for item in explanation.evolution[:12]:
            add_claim(item, "evolution", next_action="核对时间线和论文版本关系")
    for item in explanation.limitations[:12]:
        add_claim(item, "limitation", next_action="确认限制出现的实验条件和适用边界")
    for item in explanation.related_concepts[:12]:
        add_claim(
            f"“{item}”与当前概念存在值得继续核验的关联。",
            "related_concept",
            hypothesis=True,
            next_action="检索该关联的定义、关系类型和代表性论文",
        )

    linked_claim_count = sum(1 for claim in claims if claim.evidence_links)
    claim_total = len(claims)
    link_coverage = linked_claim_count / claim_total if claim_total else 0.0
    verified_claim_count = sum(
        1
        for claim in claims
        if claim.evidence_links and claim.status in {"supported", "partially_supported"}
    )
    verified_coverage = verified_claim_count / claim_total if claim_total else 0.0
    contradicted_claim_count = sum(1 for claim in claims if claim.status == "contradicted")
    warnings: list[str] = []
    if not evidence:
        warnings.append("本次分析没有可用证据卡；解释和相关概念只能作为模型/规则假设。")
    elif all(card.verification_status != "reviewed" for card in evidence):
        warnings.append("当前所有证据卡尚未完成人工全文核验，主张状态保持为未验证。")
    if any(paper.source_kind == "demo" for paper in papers):
        warnings.append("账本中包含演示资料；演示资料不能作为正式论文证据引用。")
    unlinked_count = sum(1 for claim in claims if not claim.evidence_links)
    if unlinked_count:
        warnings.append(f"有 {unlinked_count} 条主张没有达到自动匹配阈值，已明确保留为缺少证据。")
    return EvidenceLedger(
        analysis_id=analysis_id,
        claims=claims,
        evidence_count=len(evidence),
        linked_claim_count=linked_claim_count,
        coverage=round(link_coverage, 4),
        link_coverage=round(link_coverage, 4),
        verified_coverage=round(verified_coverage, 4),
        contradicted_claim_count=contradicted_claim_count,
        warnings=warnings,
    )


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
    return explanation.model_copy(update={"evolution_items": normalized})


def _split_abstract_sentences(abstract: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", abstract).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=[。！？])", normalized)
    return [part.strip() for part in parts if part.strip()]


_ABSTRACT_TYPE_PATTERNS: dict[str, tuple[str, ...]] = {
    "future_work": (
        "future work", "future research", "further work", "remains open",
        "open problem", "next step", "未来工作", "后续工作", "有待研究", "仍待解决",
    ),
    "limitation": (
        "limitation", "limited by", "trade-off", "tradeoff", "bottleneck",
        "overhead", "cost", "challenge", "drawback", "限制", "瓶颈", "开销", "代价", "挑战",
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


def _classify_abstract_sentence(sentence: str) -> str | None:
    """Classify one exact abstract sentence using visible keyword rules."""

    text = sentence.casefold()
    for evidence_type in ("future_work", "limitation", "result", "mechanism", "definition"):
        if any(token in text for token in _ABSTRACT_TYPE_PATTERNS[evidence_type]):
            return evidence_type
    return None


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
) -> list[tuple[EvidenceCard, float, int]]:
    """Rank at most three evidence cards and refuse low-relevance links."""

    claim_tokens = _match_tokens(claim_text)
    preferred = set(preferred_evidence_ids)
    compatibility = _TYPE_COMPATIBILITY.get(claim_type, {})
    ranked: list[tuple[EvidenceCard, float, int]] = []
    for card in evidence:
        paper = paper_by_id.get(card.paper_id)
        source_text = f"{paper.title if paper else ''} {card.excerpt}"
        overlap_count = len(claim_tokens & _match_tokens(source_text))
        type_score = compatibility.get(card.evidence_type, 0.0)
        preferred_bonus = 1.25 if card.id in preferred else 0.0
        # A model-provided ID is a useful hint, not permission to link an
        # unrelated card.  Without either text overlap or strong type fit, the
        # claim stays visibly unlinked.
        if overlap_count == 0 and preferred_bonus == 0:
            continue
        score = min(overlap_count, 8) * 0.42 + type_score + preferred_bonus
        threshold = 0.75 if claim_type == "related_concept" else 1.05
        if score >= threshold:
            ranked.append((card, score, overlap_count))
    ranked.sort(key=lambda item: (-item[1], -item[2], item[0].id))
    return ranked[:3]


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
