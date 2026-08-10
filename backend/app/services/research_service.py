from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import RLock
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
    AnalysisSummary,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    ConceptNodeUpdate,
    EvidenceCard,
    EvidenceLocator,
    ExplanationResult,
    InnovationCandidate,
    PaperRecord,
    ResearchBrief,
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
        try:
            if generation is None:
                with self._lock:
                    generation = self._generation
            if not self._is_generation_current(generation):
                return
            self._update(
                job_id,
                generation=generation,
                status="running",
                progress=8,
                message="正在理解概念并准备检索",
            )
            warnings: list[str] = []
            search_terms: list[str] = []
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
                planned_query = payload.concept
                planner = getattr(explanation_provider, "plan_search_query", None)
                if callable(planner):
                    try:
                        planned_query = planner(payload.concept, payload.language)
                    except ProviderUnavailable as exc:
                        warnings.append(str(exc))
                        warnings.append("已使用用户原始输入继续检索，中文概念可能需要改用英文术语重试。")
                query_plan = [planned_query]
                if payload.level == "research":
                    # A small, bounded prior-art expansion. It is intentionally
                    # transparent and is not a claim of exhaustive novelty.
                    query_plan.extend(
                        [
                            f"{payload.concept} limitations future work",
                            f"{payload.concept} efficient method comparison",
                        ]
                    )
                papers = []
                retrieval_interrupted = False
                for index, query in enumerate(query_plan):
                    search_terms.append(query)
                    progress = 25 + min(index * 8, 20)
                    self._update(
                        job_id,
                        generation=generation,
                        progress=progress,
                        message=f"正在通过 {search_provider.name} 检索：{query}",
                    )
                    try:
                        papers.extend(search_provider.search(query, payload.max_papers))
                    except ProviderUnavailable as exc:
                        retrieval_interrupted = True
                        if not settings.demo_mode and index == 0:
                            raise
                        warnings.append(str(exc))
                        if search_provider.name != "demo" and settings.demo_mode:
                            warnings.append("已切换到演示资料；演示资料不应当作为正式科学证据引用。")
                            search_provider = DemoSearchProvider()
                            papers.extend(search_provider.search(query, payload.max_papers))
                papers = _dedupe_papers(papers)
                papers = papers[: payload.max_papers]
                if not papers:
                    if retrieval_interrupted:
                        warnings.append(
                            "论文检索因 Provider 限流或不可用而未完成，不能据此判断没有相关论文；"
                            "请根据上方 Provider 提示稍后重试、配置论文检索 API Key 或切换数据源。"
                        )
                    else:
                        warnings.append("检索没有返回论文，请尝试补充英文关键词或切换数据源。")

            self._update(job_id, generation=generation, progress=52, message="正在生成段落级证据卡")
            evidence = _build_evidence(payload.concept, papers)
            self._update(job_id, generation=generation, progress=70, message="正在生成分层解释和概念关系")
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
            if not linked_ids and evidence:
                linked_ids = [item.id for item in evidence]
            explanation = explanation.model_copy(update={"evidence_ids": linked_ids})

            self._update(job_id, generation=generation, progress=86, message="正在构建概念树")
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
                self._update(
                    job_id,
                    generation=generation,
                    progress=90,
                    message="三个研究 Agent 并行寻找痛点、脑暴和 Future Work",
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
            result = AnalysisResult(
                id=str(job_id),
                concept=payload.concept,
                level=payload.level,
                audience=payload.audience,
                provider=f"search={search_provider.name}; explanation={explanation_provider.name}",
                warnings=warnings,
                search_terms=search_terms,
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
            )
            self._update(
                job_id,
                generation=generation,
                status="completed",
                progress=100,
                message="分析完成",
                result=result,
                completed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001 - job must expose failure to the UI
            self._update(
                job_id,
                generation=generation,
                status="failed",
                progress=100,
                message="分析失败",
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
    cards: list[EvidenceCard] = []
    for paper in papers:
        if not paper.abstract:
            continue
        sentences = [part.strip() for part in paper.abstract.replace("?", ".").split(".") if part.strip()]
        excerpt = " ".join(sentences[:3])
        evidence_type, claim = _classify_abstract_evidence(paper.title, excerpt, concept)
        cards.append(
            EvidenceCard(
                paper_id=paper.id,
                claim=claim,
                excerpt=excerpt,
                location="abstract",
                locator=EvidenceLocator(kind="abstract", url=paper.url),
                evidence_type=evidence_type,
                relation="background",
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
    claims: list[ClaimRecord] = []
    type_map = {
        "definition": "definition",
        "mechanism": "mechanism",
        "result": "result",
        "limitation": "limitation",
        "future_work": "research_gap",
        "context": "definition",
    }

    def valid_ids(ids: list[str]) -> list[str]:
        return [evidence_id for evidence_id in ids if evidence_id in evidence_by_id]

    def claim_status(linked_ids: list[str], *, hypothesis: bool = False) -> tuple[str, str]:
        if hypothesis or not linked_ids:
            return ("hypothesis" if hypothesis else "unverified"), "low"
        linked_cards = [evidence_by_id[item] for item in linked_ids]
        if any(card.relation == "contradicts" for card in linked_cards):
            return "contradicted", "low"
        if any(card.relation == "qualified_support" for card in linked_cards):
            reviewed = any(card.verification_status == "reviewed" for card in linked_cards)
            return "partially_supported", "medium" if reviewed else "low"
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
        evidence_ids: list[str],
        *,
        scope: str = "",
        hypothesis: bool = False,
        next_action: str = "人工核对原文和适用边界",
    ) -> None:
        text = text.strip()
        if not text:
            return
        linked_ids = valid_ids(evidence_ids)
        status, confidence = claim_status(linked_ids, hypothesis=hypothesis)
        links = [
            ClaimEvidenceLink(
                evidence_id=evidence_id,
                relation="background" if hypothesis else "supports",
                note=(
                    "模型/规则生成的待验证假设"
                    if hypothesis
                    else "该证据目前未完成全文级人工核验"
                ),
            )
            for evidence_id in linked_ids
        ]
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

    all_evidence_ids = [card.id for card in evidence]
    add_claim(
        explanation.one_sentence,
        "definition",
        explanation.evidence_ids or all_evidence_ids,
        next_action="核对定义是否适用于当前任务和读者场景",
    )
    add_claim(
        explanation.technical,
        "mechanism",
        explanation.evidence_ids or all_evidence_ids,
        next_action="回到论文方法部分，确认机制、假设和计算条件",
    )
    for index, item in enumerate(explanation.evolution[:12]):
        nearest = [evidence[index].id] if index < len(evidence) else all_evidence_ids
        add_claim(item, "evolution", nearest, next_action="核对时间线和论文版本关系")
    limitation_ids = [card.id for card in evidence if card.evidence_type == "limitation"] or all_evidence_ids
    for item in explanation.limitations[:12]:
        add_claim(item, "limitation", limitation_ids, next_action="确认限制出现的实验条件和适用边界")
    for item in explanation.related_concepts[:12]:
        add_claim(
            f"“{item}”与当前概念存在值得继续核验的关联。",
            "related_concept",
            [],
            hypothesis=True,
            next_action="检索该关联的定义、关系类型和代表性论文",
        )

    for card in evidence:
        claim_type = type_map.get(card.evidence_type, "definition")
        status = "contradicted" if card.relation == "contradicts" else "unverified"
        locator = card.location or (card.locator.kind if card.locator else "未知")
        relation = {
            "supports": "supports",
            "contradicts": "contradicts",
            "qualified_support": "qualifies",
            "background": "background",
        }.get(card.relation, "background")
        claims.append(
            ClaimRecord(
                text=card.claim,
                claim_type=claim_type,
                status=status,
                confidence=card.confidence,
                scope=f"来源：{card.paper_id}；位置：{locator}",
                evidence_links=[
                    ClaimEvidenceLink(
                        evidence_id=card.id,
                        relation=relation,
                        note="由证据卡直接抽取；当前通常仍是摘要级线索",
                    )
                ],
                next_action="打开来源并核对原文上下文",
            )
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


def _classify_abstract_evidence(title: str, excerpt: str, concept: str) -> tuple[str, str]:
    """Assign a transparent, deliberately modest label to an abstract snippet."""

    text = f"{title} {excerpt}".lower()
    if any(token in text for token in ("limitation", "trade-off", "bottleneck", "cost", "限制", "瓶颈")):
        return "limitation", f"摘要提到了“{concept}”相关方法的限制或成本线索。"
    if any(token in text for token in ("report", "result", "improv", "faster", "lower memory", "结果", "提升")):
        return "result", f"摘要报告了“{concept}”相关方法的结果或性能线索。"
    if any(token in text for token in ("introduc", "propos", "architecture", "mechanism", "algorithm", "机制", "算法")):
        return "mechanism", f"摘要描述了“{concept}”相关方法的机制或算法线索。"
    return "context", f"摘要提供了与“{concept}”相关的背景线索。"


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
