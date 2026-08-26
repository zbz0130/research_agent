"""Explicit prior-art checks for research ideas.

The concept-analysis pipeline is intentionally broad and explanatory.  This
service is a separate, bounded workflow whose result can be shown as a
``needs_review`` prior-art signal.  It does not claim to prove novelty: the
search is limited to the configured paper provider's title/abstract/metadata
surface, and the lexical comparison is deliberately transparent.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone

from app.config import Settings
from app.research_schemas import (
    EvidenceCard,
    EvidenceLocator,
    IdeaCheckCreate,
    IdeaCheckResult,
    IdeaCheckReview,
    InnovationCandidate,
    NoveltyCheck,
    PaperRecord,
    RelatedWorkSummary,
)
from app.services.research_providers import (
    ArxivSearchProvider,
    DemoSearchProvider,
    ProviderUnavailable,
    SearchProvider,
    SemanticScholarProvider,
)
from app.storage import storage


_QUERY_SPLIT_RE = re.compile(r"[\r\n。！？?!；;。]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}")
_STOP_WORDS = {
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "the",
    "using",
    "use",
    "method",
    "methods",
    "approach",
    "研究",
    "方法",
    "一种",
    "用于",
    "以及",
    "以及对",
}


class IdeaCheckNotFound(KeyError):
    """Raised when a persisted prior-art check cannot be found."""


class IdeaCheckService:
    """Run a small, explainable prior-art check and persist its result."""

    def check(self, payload: IdeaCheckCreate, settings: Settings) -> IdeaCheckResult:
        query_terms = _build_query_terms(payload.idea)
        warnings: list[str] = [
            "本检查仅覆盖当前 Provider 的标题、摘要和公开元数据，不构成穷尽式 prior-art、专利新颖性或法律结论。",
            "相似性由透明的词项重叠启发式辅助排序，仍需人工核对全文、方法细节和实验条件。",
        ]
        if settings.paper_provider == "arxiv":
            warnings.append(
                "本次直接查询 arXiv，但仍受检索词、返回数量和标题/摘要范围限制，不能证明不存在同类工作。"
            )
        else:
            warnings.append(
                "本次没有单独调用 arXiv 检索接口；如果要声称‘未发现 arXiv 同类工作’，还需要额外的 arXiv 查询和引用网络核验。"
            )

        provider = self._provider(settings)
        papers: list[PaperRecord] = []
        fallback_used = provider.name == "demo"
        if fallback_used:
            warnings.append("当前使用演示资料；演示资料不能作为正式科学证据引用。")

        for query in query_terms:
            try:
                papers.extend(provider.search(query, payload.max_papers))
            except ProviderUnavailable as exc:
                if not settings.demo_mode or fallback_used:
                    if not papers:
                        raise
                    warnings.append(f"检索词“{query}”未完成：{exc}")
                    continue
                # Demo mode is deliberately transparent: keep the result usable
                # while making the provider switch visible to the caller.
                warnings.append(f"{exc} 已切换到演示资料；演示资料不能作为正式科学证据引用。")
                provider = DemoSearchProvider()
                fallback_used = True
                papers.extend(provider.search(query, payload.max_papers))

        papers = _dedupe_papers(papers)[: payload.max_papers]
        scored = [(_similarity(payload.idea, paper), paper) for paper in papers]
        scored.sort(key=lambda item: item[0][0], reverse=True)

        evidence = _build_evidence(scored)
        related_work_summaries = _build_related_work_summaries(scored, evidence)
        novelty = _assess_novelty(scored, query_terms)
        current_conclusion = _conclusion_for(novelty.level, bool(papers))
        alternative_ideas = _build_alternatives(payload.idea, papers, novelty.level)
        validation_steps = [
            "核对最高相关论文的全文、方法、数据集和实验条件。",
            "用候选想法的中英文同义词、缩写和领域术语重复检索。",
            "将候选与最相似工作做明确的基线、对照或边界条件比较。",
        ]
        if not papers:
            validation_steps.insert(0, "先确认检索 Provider 可用，并补充更具体的领域关键词。")

        result = IdeaCheckResult(
            idea=payload.idea,
            project_id=payload.project_id,
            search_terms=query_terms,
            arxiv_status=(
                "checked"
                if settings.paper_provider == "arxiv" and not fallback_used
                else "indirect_metadata"
                if any(paper.arxiv_id for paper in papers)
                else "not_checked"
            ),
            papers=papers,
            evidence=evidence,
            related_work_summaries=related_work_summaries,
            novelty=novelty,
            similarity_level=novelty.level,
            similarity_reason=novelty.reason,
            current_conclusion=current_conclusion,
            confidence=novelty.confidence,
            manual_review_status="needs_review",
            alternative_ideas=alternative_ideas,
            validation_steps=validation_steps,
            warnings=warnings,
        )
        return storage.save_idea_check(result)

    def get(self, check_id: str) -> IdeaCheckResult:
        result = storage.get_idea_check(check_id)
        if result is None:
            raise IdeaCheckNotFound(check_id)
        return result

    def list(self) -> list[IdeaCheckResult]:
        return storage.list_idea_checks()

    def review(self, check_id: str, payload: IdeaCheckReview) -> IdeaCheckResult:
        """Persist a human review without changing the scoped search result."""

        result = self.get(check_id)
        reviewed = result.model_copy(
            update={
                "manual_review_status": payload.status,
                "review_note": payload.note,
                "reviewed_by": payload.reviewer,
                "reviewed_at": datetime.now(timezone.utc),
            }
        )
        return storage.save_idea_check(reviewed)

    @staticmethod
    def _provider(settings: Settings) -> SearchProvider:
        if not getattr(settings, "paper_enabled", True):
            raise ProviderUnavailable("论文检索 Provider 已在设置中关闭。", provider=settings.paper_provider)
        if settings.paper_provider == "demo":
            return DemoSearchProvider()
        if settings.paper_provider == "arxiv":
            return ArxivSearchProvider(endpoint=getattr(settings, "paper_base_url", None))
        if settings.paper_provider == "semantic_scholar":
            api_key = settings.paper_api_key.get_secret_value() if settings.paper_api_key else None
            return SemanticScholarProvider(
                api_key=api_key,
                endpoint=getattr(settings, "paper_base_url", None),
            )
        raise ProviderUnavailable(f"未支持的论文检索 Provider：{settings.paper_provider}")


def _build_query_terms(idea: str) -> list[str]:
    """Build at most three bounded queries, preserving the user's wording."""

    normalized = " ".join(idea.split())
    fragments = [fragment.strip() for fragment in _QUERY_SPLIT_RE.split(normalized) if fragment.strip()]
    base = fragments[0] if fragments else normalized
    candidates = [
        normalized[:320],
        base[:240],
        f"{base[:200]} prior work limitations future work"[:280],
    ]
    terms: list[str] = []
    for candidate in candidates:
        candidate = " ".join(candidate.split()).strip()
        if candidate and candidate not in terms:
            terms.append(candidate)
    return terms[:3]


def _tokens(text: str) -> set[str]:
    """Extract simple, language-tolerant tokens for an explainable score."""

    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    tokens: set[str] = set()
    for value in _TOKEN_RE.findall(text):
        value = value.lower().strip("-_ ")
        if not value or value in _STOP_WORDS:
            continue
        tokens.add(value)
        # Chinese ideas and English paper titles frequently use different
        # segmentation.  Add adjacent bigrams so short Chinese concepts still
        # contribute to the transparent overlap score.
        if all("\u4e00" <= char <= "\u9fff" for char in value) and len(value) > 2:
            tokens.update(value[index : index + 2] for index in range(len(value) - 1))
    return tokens


def _similarity(idea: str, paper: PaperRecord) -> tuple[float, list[str]]:
    idea_terms = _tokens(idea)
    title_terms = _tokens(paper.title)
    paper_terms = _tokens(f"{paper.title} {paper.abstract}")
    overlap = idea_terms & paper_terms
    title_ratio = len(overlap & title_terms) / max(1, len(title_terms))
    idea_ratio = len(overlap) / max(1, len(idea_terms))
    score = min(1.0, 0.7 * title_ratio + 0.3 * idea_ratio) if idea_terms else 0.0
    # Preserve a few high-value technical phrases that tokenization would
    # otherwise split too aggressively.  An exact method phrase in both the
    # idea and title is a direct-prior-art signal, not a proof of equivalence.
    idea_norm = idea.lower().replace(" ", "")
    title_norm = paper.title.lower().replace(" ", "")
    body_norm = f"{paper.title} {paper.abstract}".lower().replace(" ", "")
    for phrase in ("pagedattention", "flashattention", "speculativedecoding", "lora"):
        if phrase in idea_norm and phrase in title_norm:
            score = max(score, 0.82)
            break
    if ("kvcache" in idea_norm or "键值缓存" in idea_norm) and (
        "kvcache" in body_norm or "key-valuecache" in body_norm
    ):
        score = max(score, 0.68)
    return round(score, 3), sorted(overlap)


def _dedupe_papers(papers: Iterable[PaperRecord]) -> list[PaperRecord]:
    seen: set[str] = set()
    unique: list[PaperRecord] = []
    for paper in papers:
        key = (paper.canonical_id or paper.doi or paper.provider_id or paper.id or paper.title).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    return unique


def _level_for(score: float, has_papers: bool) -> str:
    if not has_papers:
        return "L4"
    if score >= 0.75:
        return "L0"
    if score >= 0.50:
        return "L1"
    if score >= 0.20:
        return "L2"
    if score > 0:
        return "L3"
    return "L4"


def _assess_novelty(
    scored: list[tuple[tuple[float, list[str]], PaperRecord]], query_terms: list[str]
) -> NoveltyCheck:
    if not scored:
        return NoveltyCheck(
            level="L4",
            reason="当前 Provider 没有返回候选论文，无法判断与已有工作的相似性。",
            confidence="low",
            matched_paper_ids=[],
            compared_terms=query_terms,
            scope_note="当前只检查标题、摘要和公开元数据；没有结果不等于不存在相关工作。",
        )

    (score, terms), _paper = scored[0]
    level = _level_for(score, True)
    matched_ids = [paper.id for (pair, paper) in scored if pair[0] >= 0.18]
    if level == "L0":
        reason = "至少一篇候选论文与想法在技术短语和标题/摘要上直接匹配，应先按已有工作处理。"
    elif level == "L1":
        reason = "发现核心方法高度相似的工作，可能只是在应用场景或数据上不同。"
    elif level == "L2":
        reason = "发现部分组件或目标重叠，可能存在可区分的边界条件，但仍需全文核验。"
    elif level == "L3":
        reason = "发现相近问题或背景主题，但当前资料中的机制重合较弱。"
    else:
        reason = "检索到了资料，但当前词项检查没有确认直接等价的方法。"
    if terms:
        reason = f"{reason} 最高相关线索：{', '.join(terms[:8])}。"
    return NoveltyCheck(
        level=level,
        reason=reason,
        confidence="medium" if level in {"L1", "L2", "L3"} else "low",
        matched_paper_ids=matched_ids,
        compared_terms=query_terms,
        scope_note="仅依据当前 Provider 的标题、摘要和公开元数据；这不是穷尽式 prior-art、专利新颖性或法律结论。",
    )


def _conclusion_for(level: str, has_papers: bool) -> str:
    if not has_papers:
        return "当前检索没有足够候选，不能判断新颖性；请补充术语并人工复核。"
    if level in {"L0", "L1"}:
        return "存在直接或高度相似工作，应先明确差异化机制、适用边界和可验证实验。"
    if level == "L2":
        return "存在部分重叠线索，可能通过限定条件、数据或实验设计形成可区分方向。"
    if level == "L3":
        return "只发现问题或背景层面的相关资料，仍需沿引用网络和全文继续核验。"
    return "在当前有限检索范围内未发现直接等价工作，但这不是原创性证明。"


def _build_alternatives(
    idea: str,
    papers: list[PaperRecord],
    level: str,
) -> list[InnovationCandidate]:
    """Offer one deliberately cautious differentiation direction.

    The endpoint is a prior-art check, not an idea generator.  This small
    alternative is therefore framed as a validation direction and carries a
    low-confidence disclaimer rather than being presented as a novel result.
    """

    if not papers:
        return []
    nearest = [paper.title for paper in papers[:3]]
    return [
        InnovationCandidate(
            title=f"在明确边界条件下验证：{idea[:90]}",
            problem="现有检索结果与候选想法存在一定重叠，需要找到能区分已有方法的适用边界。",
            mechanism="固定一个可量化的限制条件或失败场景，比较候选想法与最高相关工作的差异。",
            nearest_work=nearest,
            novelty_level=level,  # type: ignore[arg-type]
            confidence="low",
            feasibility="medium",
            rationale="这是由 prior-art 线索推导的探索性验证方向，不是已确认的原创创新。",
            validation_steps=[
                "选定一个最高相关工作作为可复现基线",
                "预先定义区分候选与基线的指标和对照",
                "先做小规模预实验，再决定是否扩大范围",
            ],
            warning="不能将此替代方向直接表述为原创成果。",
        )
    ]


def _build_evidence(
    scored: list[tuple[tuple[float, list[str]], PaperRecord]],
) -> list[EvidenceCard]:
    cards: list[EvidenceCard] = []
    for (score, terms), paper in scored:
        if not paper.abstract:
            continue
        sentences = [part.strip() for part in re.split(r"[.!?。！？]+", paper.abstract) if part.strip()]
        excerpt = " ".join(sentences[:3])
        overlap = ", ".join(terms[:8]) if terms else "检索主题"
        relation_note = "可能存在主题词项重叠" if score < 0.35 else "存在较强主题/机制词项重叠"
        cards.append(
            EvidenceCard(
                paper_id=paper.id,
                claim=f"该论文与候选想法{relation_note}（{overlap}）；这不是方法等价或原创性证明。",
                excerpt=excerpt,
                location="abstract",
                locator=EvidenceLocator(kind="abstract", url=paper.url),
                evidence_type="context",
                relation="background",
                confidence="low" if paper.source_kind == "demo" else "medium",
                verification_status="unverified",
                source_url=paper.url,
            )
        )
    return cards


def _build_related_work_summaries(
    scored: list[tuple[tuple[float, list[str]], PaperRecord]],
    evidence: list[EvidenceCard],
) -> list[RelatedWorkSummary]:
    """Create cautious, readable per-paper summaries from abstracts only."""

    evidence_by_paper: dict[str, list[str]] = {}
    for card in evidence:
        evidence_by_paper.setdefault(card.paper_id, []).append(card.id)

    summaries: list[RelatedWorkSummary] = []
    for (score, terms), paper in scored[:8]:
        sentences = [
            part.strip()
            for part in re.split(r"[.!?。！？；;]+", paper.abstract or "")
            if part.strip()
        ]
        problem = sentences[0] if sentences else "摘要未明确说明问题。"
        mechanism = sentences[1] if len(sentences) > 1 else "摘要未提供足够机制细节。"
        plain = (
            f"通俗说，这篇论文主要讨论“{problem[:700]}”。"
            f"摘要中的方法线索是“{mechanism[:900]}”。"
        )
        overlap = (
            f"与当前想法在“{', '.join(terms[:8])}”等词项或目标上有重叠；"
            "这不是方法等价证明。"
            if terms
            else "当前摘要没有提取到稳定的重叠词项。"
        )
        summaries.append(
            RelatedWorkSummary(
                paper_id=paper.id,
                paper_title=paper.title,
                what_problem=problem[:2000],
                core_mechanism=mechanism[:3000],
                plain_language_summary=plain[:4000],
                overlap_with_idea=overlap,
                possible_difference="摘要没有给出足够实验和实现细节，仍需打开原文核对差异。",
                summary_level="abstract_only",
                evidence_ids=evidence_by_paper.get(paper.id, []),
                verification_status="unverified",
                confidence="low" if paper.source_kind == "demo" or score < 0.5 else "medium",
            )
        )
    return summaries


idea_service = IdeaCheckService()
# Keep a descriptive alias for callers that prefer the explicit service name;
# the public route uses ``idea_service`` for consistency with the existing
# project/research service singletons.
idea_check_service = idea_service
