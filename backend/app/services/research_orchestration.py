"""Bounded multi-agent orchestration for research-mode analyses.

The first WishForge version does not pretend that X, Zhihu, Reddit or paper
full text are always available.  Instead it makes the workflow explicit:

* a community agent finds exploratory pain-point signals;
* a model agent proposes hypotheses;
* an academic agent extracts limitations/future-work signals;
* a synthesis agent combines them into low-confidence candidates.

Every branch returns an :class:`AgentRun` record.  Missing providers are
represented as a failed/skipped run with a warning, rather than silently being
treated as evidence that a research direction is novel.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import re
from collections.abc import Callable
from typing import Any, Protocol, Sequence
from uuid import uuid4

import httpx

from app.config import Settings
from app.research_schemas import (
    AgentRun,
    CommunitySignal,
    EvidenceCard,
    FutureWorkSignal,
    InnovationCandidate,
    PaperRecord,
    ResearchBrief,
)
from app.services.research_providers import (
    ExplanationProvider,
    ProviderUnavailable,
    SearchProvider,
)


class CommunityProvider(Protocol):
    """Read-only boundary for an explicitly configured community platform."""

    name: str

    def search(
        self,
        concept: str,
        limit: int,
        *,
        query_terms: Sequence[str] = (),
    ) -> list[CommunitySignal]:
        ...


class DemoCommunityProvider:
    """Deterministic community fixtures for local demos and acceptance tests."""

    name = "demo_community"

    def search(
        self,
        concept: str,
        limit: int,
        *,
        query_terms: Sequence[str] = (),
    ) -> list[CommunitySignal]:
        text = concept.lower()
        if any(token in text for token in ("attention", "注意力", "kv cache", "kv缓存", "paged")):
            signals = [
                CommunitySignal(
                    id="demo-community-attention-x",
                    platform="x",
                    title="Long-context attention is still expensive",
                    summary="工程实践者反复讨论长上下文推理中的显存、延迟和缓存碎片问题。",
                    pain_point="上下文变长后，KV cache 占用和请求间调度开销会快速增加。",
                    open_question="能否根据请求难度和 token 重要性动态管理缓存，而不牺牲答案质量？",
                    url="https://x.com/search?q=long%20context%20attention",
                    confidence="low",
                ),
                CommunitySignal(
                    id="demo-community-zhihu-attention",
                    platform="知乎",
                    title="为什么长文本注意力优化难以复现",
                    summary="讨论常见的优化方法在不同硬件、序列长度和 batch 设置下收益不稳定。",
                    pain_point="论文中的吞吐提升不一定能在真实服务负载中复现。",
                    open_question="如何建立跨硬件、跨负载的统一评测协议？",
                    url="https://www.zhihu.com/search?type=content&q=长文本注意力",
                    confidence="low",
                ),
                CommunitySignal(
                    id="demo-community-reddit-kv",
                    platform="reddit",
                    title="KV-cache quality versus memory trade-off",
                    summary="用户关注压缩、淘汰 KV cache 后长程依赖和生成质量的变化。",
                    pain_point="降低显存通常会引入质量退化，且退化边界缺少统一解释。",
                    open_question="哪些 token 或层对长程任务最重要，能否用可解释指标预测？",
                    url="https://www.reddit.com/r/LocalLLaMA/search/?q=kv%20cache",
                    confidence="low",
                ),
            ]
        elif any(token in text for token in ("lora", "低秩", "微调")):
            signals = [
                CommunitySignal(
                    id="demo-community-lora-x",
                    platform="x",
                    title="Rank selection remains a practical LoRA question",
                    summary="工程讨论集中在不同任务和层是否需要不同 rank。",
                    pain_point="固定 rank 难以兼顾参数量、训练速度和任务效果。",
                    open_question="能否在训练中根据梯度或任务难度自动分配 rank？",
                    url="https://x.com/search?q=LoRA%20rank",
                    confidence="low",
                ),
                CommunitySignal(
                    id="demo-community-lora-reddit",
                    platform="reddit",
                    title="PEFT reproducibility across quantization settings",
                    summary="用户报告量化配置和数据配方变化会影响参数高效微调结果。",
                    pain_point="相同 LoRA 配置在不同基础模型和量化设置下表现不一致。",
                    open_question="怎样设计可复现的 rank、量化与数据配方报告？",
                    url="https://www.reddit.com/r/LocalLLaMA/search/?q=LoRA",
                    confidence="low",
                ),
            ]
        else:
            slug = hashlib.sha1(concept.encode("utf-8")).hexdigest()[:10]
            signals = [
                CommunitySignal(
                    id=f"demo-community-{slug}",
                    platform="other",
                    title=f"关于“{concept}”的探索性讨论信号",
                    summary="演示 Provider 生成的社区痛点占位记录，接入真实社区检索后应替换。",
                    pain_point=f"“{concept}”的适用边界、失败条件和可复现路径仍需梳理。",
                    open_question="哪些具体条件会使该方法失效？",
                    url="https://example.com/wishforge/community-demo",
                    confidence="low",
                )
            ]
        return signals[:limit]


_DEFAULT_HACKER_NEWS_API = "https://hacker-news.firebaseio.com/v0"
_DEFAULT_X_API = "https://api.x.com/2"
_DEFAULT_REDDIT_API = "https://oauth.reddit.com"
_COMMUNITY_TIMEOUT_SECONDS = 8.0
_HN_SCAN_LIMIT = 72
_QUERY_STOP_WORDS = {
    "about", "and", "are", "based", "for", "from", "into", "method", "methods",
    "model", "models", "of", "the", "this", "that", "using", "with",
}


def _strip_html(value: object, *, limit: int = 1200) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:limit].rstrip()


def _community_query_terms(concept: str, query_terms: Sequence[str]) -> list[str]:
    """Retain only compact terms that can be sent to a public community API."""

    values = [*query_terms, concept]
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").replace('"', " ").split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized[:240])
        if len(unique) >= 3:
            break
    return unique


def _community_tokens(values: Sequence[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokens(value))
    return {token for token in tokens if token not in _QUERY_STOP_WORDS}


def _checked_json(
    request_get: Callable[..., Any],
    url: str,
    *,
    provider: str,
    label: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
) -> Any:
    """Request bounded JSON without putting credentials in public errors."""

    try:
        response = request_get(
            url,
            headers=headers,
            params=params,
            timeout=_COMMUNITY_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(
            f"{label} 连接失败：{exc.__class__.__name__}。请检查网络后重试。",
            provider=provider,
        ) from exc
    status_code = int(getattr(response, "status_code", 200))
    if not 200 <= status_code < 300:
        raise ProviderUnavailable(
            f"{label} 请求失败（HTTP {status_code}）。请检查该平台的访问权限、配额或 Token。",
            provider=provider,
        )
    try:
        return response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderUnavailable(
            f"{label} 返回了无法识别的数据，未把它当作社区信号。",
            provider=provider,
        ) from exc


class HackerNewsCommunityProvider:
    """Read the public Hacker News API without a credential or scraping."""

    name = "hacker_news"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        request_get: Callable[..., Any] = httpx.get,
    ) -> None:
        self.base_url = (base_url or _DEFAULT_HACKER_NEWS_API).rstrip("/")
        self._request_get = request_get

    def _get(self, path: str) -> Any:
        return _checked_json(
            self._request_get,
            f"{self.base_url}/{path.lstrip('/')}",
            provider=self.name,
            label="Hacker News 公共 API",
        )

    def search(
        self,
        concept: str,
        limit: int,
        *,
        query_terms: Sequence[str] = (),
    ) -> list[CommunitySignal]:
        terms = _community_query_terms(concept, query_terms)
        tokens = _community_tokens(terms)
        if not tokens:
            return []
        story_ids = self._get("newstories.json")
        if not isinstance(story_ids, list):
            raise ProviderUnavailable(
                "Hacker News 公共 API 返回的故事列表格式无效。",
                provider=self.name,
            )
        candidate_ids = [item for item in story_ids if isinstance(item, int)][: _HN_SCAN_LIMIT]

        def load_story(story_id: int) -> dict[str, Any] | None:
            try:
                item = self._get(f"item/{story_id}.json")
            except ProviderUnavailable:
                return None
            return item if isinstance(item, dict) else None

        stories: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="wishforge-hn") as executor:
            for item in executor.map(load_story, candidate_ids):
                if item and item.get("type") == "story" and not item.get("deleted") and not item.get("dead"):
                    stories.append(item)

        ranked: list[tuple[int, int, CommunitySignal]] = []
        for story in stories:
            title = _strip_html(story.get("title"), limit=500)
            body = _strip_html(story.get("text"), limit=1500)
            haystack = f"{title} {body}".casefold()
            title_text = title.casefold()
            matched = sorted(token for token in tokens if token in haystack)
            title_matches = [token for token in matched if token in title_text]
            if not title_matches and len(matched) < 2:
                continue
            story_id = story.get("id")
            if not isinstance(story_id, int):
                continue
            score = int(story.get("score") or 0)
            comments = int(story.get("descendants") or 0)
            created = story.get("time")
            observed_at = (
                datetime.fromtimestamp(created, tz=timezone.utc)
                if isinstance(created, (int, float))
                else _now()
            )
            excerpt = body or "帖子未提供正文；请打开来源和评论核对具体上下文。"
            signal = CommunitySignal(
                id=f"hacker-news-{story_id}",
                platform="hacker_news",
                title=title or f"Hacker News story {story_id}",
                summary=(
                    f"Hacker News 公开讨论，{score} 分、{comments} 条评论。{excerpt}"
                )[:5000],
                pain_point=(
                    f"该帖与检索词 {', '.join(matched[:6]) or '相关'} 存在文本匹配；"
                    "具体问题需打开原帖与评论人工核验。"
                ),
                open_question="讨论中的实践约束、失败条件和可复现证据是什么？",
                url=f"https://news.ycombinator.com/item?id={story_id}",
                observed_at=observed_at,
                confidence="low",
            )
            ranked.append((len(title_matches) * 3 + len(matched), score + comments, signal))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[: max(1, min(limit, 12))]]


class XCommunityProvider:
    """Read recent X posts through the official bearer-token endpoint."""

    name = "x"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        *,
        request_get: Callable[..., Any] = httpx.get,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or _DEFAULT_X_API).rstrip("/")
        self._request_get = request_get

    def search(
        self,
        concept: str,
        limit: int,
        *,
        query_terms: Sequence[str] = (),
    ) -> list[CommunitySignal]:
        if not self.api_key:
            raise ProviderUnavailable(
                "X 社区检索需要在“社区检索”槽位配置 Bearer Token。",
                provider=self.name,
            )
        terms = _community_query_terms(concept, query_terms)
        query = " OR ".join(f'({term})' for term in terms[:3])
        if not query:
            return []
        payload = _checked_json(
            self._request_get,
            f"{self.base_url}/tweets/search/recent",
            provider=self.name,
            label="X 最近帖子搜索",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={
                "query": query,
                "max_results": max(10, min(limit, 100)),
                "sort_order": "relevancy",
                "tweet.fields": "created_at,public_metrics,lang",
            },
        )
        posts = payload.get("data", []) if isinstance(payload, dict) else []
        signals: list[CommunitySignal] = []
        for post in posts:
            if not isinstance(post, dict) or not post.get("id"):
                continue
            text = _strip_html(post.get("text"), limit=2200)
            post_id = str(post["id"])
            metrics = post.get("public_metrics") if isinstance(post.get("public_metrics"), dict) else {}
            engagement = int(metrics.get("like_count") or 0) + int(metrics.get("reply_count") or 0)
            signals.append(
                CommunitySignal(
                    id=f"x-{post_id}",
                    platform="x",
                    title=(text[:150] or f"X post {post_id}"),
                    summary=(f"X 公开帖子（互动 {engagement}）：{text}" if text else "X 公开帖子，请打开来源核对上下文。"),
                    pain_point="该帖子是与当前主题相关的公开讨论，具体主张尚未核验。",
                    open_question="该讨论反映的问题能否用论文、数据或最小实验复现？",
                    url=f"https://x.com/i/web/status/{post_id}",
                    observed_at=_now(),
                    confidence="low",
                )
            )
        return signals[:limit]


class RedditCommunityProvider:
    """Read Reddit search results only through its OAuth Data API endpoint."""

    name = "reddit"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        *,
        request_get: Callable[..., Any] = httpx.get,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or _DEFAULT_REDDIT_API).rstrip("/")
        self._request_get = request_get

    def search(
        self,
        concept: str,
        limit: int,
        *,
        query_terms: Sequence[str] = (),
    ) -> list[CommunitySignal]:
        if not self.api_key:
            raise ProviderUnavailable(
                "Reddit 社区检索需要在“社区检索”槽位配置 OAuth Bearer Token。",
                provider=self.name,
            )
        terms = _community_query_terms(concept, query_terms)
        query = " OR ".join(terms[:3])
        if not query:
            return []
        payload = _checked_json(
            self._request_get,
            f"{self.base_url}/search",
            provider=self.name,
            label="Reddit OAuth 搜索",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "WishForge/0.2 community-signal-reader",
            },
            params={"q": query, "sort": "relevance", "limit": max(1, min(limit, 25)), "type": "link"},
        )
        children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
        signals: list[CommunitySignal] = []
        for child in children:
            item = child.get("data") if isinstance(child, dict) else None
            if not isinstance(item, dict) or not item.get("id"):
                continue
            post_id = str(item["id"])
            title = _strip_html(item.get("title"), limit=500)
            body = _strip_html(item.get("selftext"), limit=1800)
            subreddit = _strip_html(item.get("subreddit"), limit=100)
            score = int(item.get("score") or 0)
            comments = int(item.get("num_comments") or 0)
            permalink = str(item.get("permalink") or "")
            created = item.get("created_utc")
            observed_at = (
                datetime.fromtimestamp(created, tz=timezone.utc)
                if isinstance(created, (int, float))
                else _now()
            )
            signals.append(
                CommunitySignal(
                    id=f"reddit-{post_id}",
                    platform="reddit",
                    title=title or f"Reddit post {post_id}",
                    summary=(
                        f"r/{subreddit or 'unknown'} 公开讨论，{score} 分、{comments} 条评论。"
                        f" {body or '请打开来源核对完整讨论。'}"
                    )[:5000],
                    pain_point="该帖子反映社区中的实践问题；它不是经同行评审的科学证据。",
                    open_question="该问题是否能被公开数据、基线对照或论文全文证据复现？",
                    url=f"https://www.reddit.com{permalink}" if permalink.startswith("/") else None,
                    observed_at=observed_at,
                    confidence="low",
                )
            )
        return signals[:limit]


def _community_provider(settings: Settings) -> CommunityProvider:
    if not getattr(settings, "community_enabled", True):
        raise ProviderUnavailable(
            "社区检索 Provider 已在设置中关闭。",
            provider=getattr(settings, "community_provider", "unknown"),
        )
    provider = str(getattr(settings, "community_provider", "hacker_news")).strip().lower()
    base_url = getattr(settings, "community_base_url", None)
    api_key = getattr(settings, "community_api_key", None)
    secret = api_key.get_secret_value() if api_key is not None else None
    if provider == "demo":
        return DemoCommunityProvider()
    if provider in {"hacker_news", "hackernews", "hn"}:
        return HackerNewsCommunityProvider(base_url)
    if provider == "x":
        return XCommunityProvider(secret, base_url)
    if provider == "reddit":
        return RedditCommunityProvider(secret, base_url)
    if provider in {"zhihu", "知乎"}:
        raise ProviderUnavailable(
            "知乎没有在本应用中配置可用的合规 API 连接器；不会进行未授权抓取。",
            provider="zhihu",
        )
    raise ProviderUnavailable(
        f"未配置可用的社区 Provider：{provider}。可使用 hacker_news、x、reddit 或 demo。",
        provider=provider,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(started: datetime, completed: datetime) -> int:
    return max(0, int((completed - started).total_seconds() * 1000))


def _tokens(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {token for token in normalized.split() if len(token) >= 3}


def _heuristic_model_ideas(
    concept: str,
    papers: Sequence[PaperRecord],
    evidence: Sequence[EvidenceCard],
) -> list[InnovationCandidate]:
    """Transparent fallback for when no compatible brainstorm model is set."""

    normalized = concept.lower()
    nearest = [paper.title for paper in papers[:3]]
    evidence_ids = [item.id for item in evidence[:4]]
    if "attention" in normalized or "注意力" in concept or "kv cache" in normalized:
        return [
            InnovationCandidate(
                title="按请求难度和 token 重要性自适应管理长上下文 KV cache",
                problem="长上下文服务的 KV cache 会造成显存压力、碎片和质量—内存权衡。",
                mechanism="使用轻量重要性估计，在分页缓存基础上动态决定保留、压缩或淘汰的 token。",
                nearest_work=nearest,
                novelty_level="L2",
                confidence="low",
                feasibility="medium",
                rationale="社区信号和摘要级论文线索都指向缓存管理与质量退化的边界，但组合机制仍需完整 prior-art 核验。",
                validation_steps=[
                    "与标准 KV cache、PagedAttention 和固定压缩策略比较",
                    "在不同上下文长度、并发度和任务类型下记录延迟、峰值显存和质量",
                    "消融重要性估计、压缩比例和淘汰策略的额外开销",
                ],
                warning="模型/规则生成的候选，不是已确认的新颖成果。",
                source_type="model_generated",
                evidence_ids=evidence_ids,
            )
        ]
    if "lora" in normalized or "低秩" in concept or "微调" in concept:
        return [
            InnovationCandidate(
                title="按层和任务难度动态分配 LoRA rank",
                problem="固定 rank 难以同时适应不同层、不同任务和不同量化配置。",
                mechanism="依据训练信号或任务难度动态增加、冻结或回收各层低秩容量。",
                nearest_work=nearest,
                novelty_level="L2",
                confidence="low",
                feasibility="medium",
                rationale="已有 LoRA、AdaLoRA 等方向提供了近邻工作，差异必须通过术语扩展和全文核验确认。",
                validation_steps=[
                    "与固定 rank LoRA、AdaLoRA、QLoRA 和全量微调比较",
                    "报告效果、可训练参数、显存、训练时间和 rank 变化轨迹",
                    "按任务难度分组并做 rank 分配策略消融",
                ],
                warning="模型/规则生成的候选，不是已确认的新颖成果。",
                source_type="model_generated",
                evidence_ids=evidence_ids,
            )
        ]
    related = "；".join(item.claim for item in evidence[:2]) or concept
    return [
        InnovationCandidate(
            title=f"针对 {concept} 的失败条件设计可解释自适应机制",
            problem=f"{concept} 的适用边界和失败条件尚未被当前摘要级资料充分覆盖。",
            mechanism=f"围绕已观察到的线索（{related[:180]}）定义可解释指标，并在边界条件下动态调整方法。",
            nearest_work=nearest,
            novelty_level="L4",
            confidence="low",
            feasibility="low",
            rationale="这是未验证的模型脑暴方向，需要进一步检索同义表达、反例和实验条件。",
            validation_steps=[
                "扩展中文、英文和缩写检索词，并检查引用网络",
                "先定义基线、对照、变量和可量化指标",
                "使用小规模数据做可复现实验，记录失败案例",
            ],
            warning="模型/规则生成的候选，不是已确认的新颖成果。",
            source_type="model_generated",
            evidence_ids=evidence_ids,
        )
    ]


def _future_work_signals(
    concept: str,
    papers: Sequence[PaperRecord],
    evidence: Sequence[EvidenceCard],
) -> list[FutureWorkSignal]:
    signals: list[FutureWorkSignal] = []
    evidence_by_paper = {item.paper_id: item for item in evidence}
    for paper in papers:
        card = evidence_by_paper.get(paper.id)
        text = f"{paper.title} {paper.abstract}".lower()
        hint = any(
            token in text
            for token in (
                "future work",
                "limitation",
                "trade-off",
                "challenge",
                "remain",
                "discuss",
                "open question",
                "限制",
                "未来",
                "挑战",
                "权衡",
            )
        )
        if not hint and not (
            card
            and set(card.evidence_types or [card.evidence_type])
            & {"limitation", "future_work"}
        ):
            continue
        excerpt = (card.excerpt if card else paper.abstract[:800]).strip()
        # The current provider only supplies abstracts.  Keep the section as
        # ``abstract_signal`` even when the wording hints at a limitation;
        # claiming a Discussion/Limitations section would overstate the
        # evidence until a full-text parser is connected.
        section = "abstract_signal"
        signals.append(
            FutureWorkSignal(
                paper_id=paper.id,
                paper_title=paper.title,
                section=section,
                claim=(
                    f"论文《{paper.title}》的摘要级资料提示“{concept}”仍有待核验的限制、权衡或后续方向。"
                ),
                excerpt=excerpt,
                evidence_id=card.id if card else None,
                locator=card.locator if card else None,
                confidence="low" if paper.source_kind == "demo" else "medium",
            )
        )
    return signals[:12]


def _candidate_from_future_signal(signal: FutureWorkSignal) -> InnovationCandidate:
    return InnovationCandidate(
        title=f"核验《{signal.paper_title}》的摘要级限制边界",
        problem=signal.claim,
        mechanism="围绕论文指出的限制条件设计对照实验，并将边界条件作为可观测变量。",
        nearest_work=[signal.paper_title],
        novelty_level="L2",
        confidence="low",
        feasibility="medium",
        rationale="方向来自论文摘要级限制/Discussion 线索；只有阅读全文和复现实验后才能判断研究空白。",
        validation_steps=[
            "打开原文 Discussion、Limitations、Conclusion 和 Supplementary 核对原意",
            "复现论文基线，再单独改变其限制条件",
            "报告效果、成本和失败案例，避免把边界观察写成普遍结论",
        ],
        warning="摘要级 Future Work 信号，尚未完成全文核验。",
        source_type="paper_future_work",
        evidence_ids=[signal.evidence_id] if signal.evidence_id else [],
    )


def _candidate_from_community_signal(signal: CommunitySignal) -> InnovationCandidate:
    return InnovationCandidate(
        title=f"把社区痛点转成可复现实验：{signal.title}",
        problem=signal.pain_point or signal.summary,
        mechanism=signal.open_question or "将痛点拆成明确变量、基线和评价指标。",
        nearest_work=[],
        novelty_level="L3",
        confidence="low",
        feasibility="medium",
        rationale="社区信号用于发现问题，不是科学证据；需要回到论文、数据和实验进行验证。",
        validation_steps=[
            "记录平台、链接、时间和原始上下文，并人工排除广告或个体偏见",
            "检索该痛点的学术术语、同义词和反例",
            "设计最小可复现实验验证痛点是否稳定存在",
        ],
        warning="社区信号未经科学核验，不能作为论文结论或新颖性证明。",
        source_type="community_signal",
    )


def _model_brainstorm(
    concept: str,
    papers: Sequence[PaperRecord],
    evidence: Sequence[EvidenceCard],
    explanation_provider: ExplanationProvider | None,
    language: str = "zh-CN",
) -> tuple[list[InnovationCandidate], str, list[str]]:
    """Use a configured model's optional brainstorm method, with a clear fallback."""

    brainstorm = getattr(explanation_provider, "brainstorm", None)
    if callable(brainstorm):
        try:
            ideas = brainstorm(concept, papers, evidence, language)
            if ideas:
                ideas = [
                    item.model_copy(
                        update={
                            "source_type": "model_generated",
                            "confidence": "low",
                            "warning": item.warning
                            or "模型生成的待验证候选，不是已确认的新颖成果。",
                            "evidence_ids": item.evidence_ids or [
                                evidence_item.id for evidence_item in evidence
                            ],
                        }
                    )
                    for item in ideas[:3]
                ]
                return ideas, getattr(explanation_provider, "name", "model"), []
        except ProviderUnavailable as exc:
            return (
                _heuristic_model_ideas(concept, papers, evidence),
                "heuristic_fallback",
                [f"模型脑暴 Provider 不可用，已使用透明启发式回退：{exc}"],
            )
    return (
        _heuristic_model_ideas(concept, papers, evidence),
        "heuristic_fallback",
        ["当前解释 Provider 没有独立脑暴接口，已使用透明启发式回退。"],
    )


def _synthesize_candidates(
    concept: str,
    community: Sequence[CommunitySignal],
    model_ideas: Sequence[InnovationCandidate],
    future: Sequence[FutureWorkSignal],
    existing: Sequence[InnovationCandidate],
    synthesis_run_id: str | None = None,
) -> list[InnovationCandidate]:
    """Merge candidates while retaining provenance and avoiding duplicates."""

    candidates: list[InnovationCandidate] = []
    candidates.extend(model_ideas[:3])
    candidates.extend(_candidate_from_future_signal(item) for item in future[:2])
    candidates.extend(_candidate_from_community_signal(item) for item in community[:1])
    if not candidates:
        candidates.extend(existing[:3])

    unique: list[InnovationCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = " ".join(sorted(_tokens(candidate.title))) or candidate.title.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    # Give synthesis candidates a stable provenance marker without mutating
    # the upstream records returned by each branch.
    synthesis_run_id = synthesis_run_id or str(uuid4())
    return [
        item.model_copy(
            update={
                "source_agent_run_id": synthesis_run_id,
                "warning": item.warning
                or "综合 Agent 生成的待验证候选，不是已确认的新颖成果。",
            }
        )
        for item in unique[:6]
    ]


def _model_synthesis(
    concept: str,
    community: Sequence[CommunitySignal],
    model_ideas: Sequence[InnovationCandidate],
    future: Sequence[FutureWorkSignal],
    existing: Sequence[InnovationCandidate],
    explanation_provider: ExplanationProvider | None,
    synthesis_run_id: str,
) -> tuple[str, list[InnovationCandidate], str, list[str]]:
    """Use an optional compatible model for synthesis, with a deterministic fallback."""

    synthesize = getattr(explanation_provider, "synthesize_research", None)
    if callable(synthesize):
        try:
            summary, candidates = synthesize(concept, community, model_ideas, future)
            upstream_evidence_ids = list(
                dict.fromkeys(
                    [
                        item_id
                        for item in model_ideas
                        for item_id in item.evidence_ids
                    ]
                    + [item.evidence_id for item in future if item.evidence_id]
                )
            )
            candidates = [
                item.model_copy(
                    update={
                        "source_type": "synthesis",
                        "confidence": "low",
                        "source_agent_run_id": synthesis_run_id,
                        "evidence_ids": item.evidence_ids or upstream_evidence_ids,
                        "warning": item.warning
                        or "综合 Agent 生成的待验证候选，不是已确认的新颖成果。",
                    }
                )
                for item in candidates[:6]
            ]
            return summary, candidates, getattr(explanation_provider, "name", "model"), []
        except ProviderUnavailable as exc:
            fallback = _synthesize_candidates(
                concept, community, model_ideas, future, existing, synthesis_run_id
            )
            return (
                f"综合 Agent 模型不可用，已使用透明规则合并 {len(fallback)} 个待验证候选。",
                fallback,
                "research_synthesis_fallback",
                [f"综合模型 Provider 不可用，已回退规则合并：{exc}"],
            )
    fallback = _synthesize_candidates(
        concept, community, model_ideas, future, existing, synthesis_run_id
    )
    return (
        f"综合 Agent 合并了社区、模型脑暴和论文 Future Work 线索，形成 {len(fallback)} 个待验证候选。",
        fallback,
        "research_synthesis_fallback",
        ["当前解释 Provider 没有独立综合接口，已使用透明规则合并。"],
    )


def _check_arxiv(
    candidates: Sequence[InnovationCandidate],
    search_provider: SearchProvider,
    limit: int = 4,
) -> tuple[str, list[str], list[str], list[str]]:
    """Run bounded candidate searches and report scoped arXiv status.

    This is intentionally not a global guarantee.  A candidate is marked
    ``matched`` only when a returned paper carries an arXiv identifier or an
    arXiv URL and its title/abstract overlaps the candidate terms.
    """

    checked_terms: list[str] = []
    match_ids: list[str] = []
    warnings: list[str] = []
    successful = 0
    for candidate in candidates[:3]:
        query = candidate.title[:240]
        checked_terms.append(query)
        try:
            papers = search_provider.search(query, limit)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            warnings.append(f"arXiv/近邻检索未完成（{query}）：{exc}")
            continue
        successful += 1
        candidate_terms = _tokens(f"{candidate.title} {candidate.mechanism}")
        for paper in papers:
            paper_terms = _tokens(f"{paper.title} {paper.abstract}")
            overlap = len(candidate_terms & paper_terms)
            is_arxiv = bool(paper.arxiv_id or (paper.url and "arxiv.org" in paper.url.lower()) or paper.venue == "arXiv")
            if is_arxiv and overlap >= 2:
                if paper.id not in match_ids:
                    match_ids.append(paper.id)
                candidate.arxiv_status = "matched"
                if paper.id not in candidate.arxiv_match_paper_ids:
                    candidate.arxiv_match_paper_ids.append(paper.id)
    if not candidates:
        return "not_checked", checked_terms, match_ids, warnings
    if successful == 0:
        status = "unavailable"
    elif match_ids:
        status = "matched"
    else:
        status = "no_direct_match_in_scope"
        if not match_ids:
            warnings.append(
                "在当前 Provider、关键词和返回数量范围内未发现直接匹配的 arXiv 记录；这不是全网不存在的证明。"
            )
    warnings.append(
        "当前 arXiv 状态来自所选论文 Provider 返回的 arXiv 元数据或链接，不是独立穷尽式 arXiv API 核验。"
    )
    return status, checked_terms, match_ids, warnings


class ResearchOrchestrator:
    """Execute the three research branches concurrently and synthesize them."""

    def run(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        search_provider: SearchProvider,
        settings: Settings,
        existing_candidates: Sequence[InnovationCandidate] = (),
        explanation_provider: ExplanationProvider | None = None,
        language: str = "zh-CN",
        community_query_terms: Sequence[str] = (),
    ) -> ResearchBrief:
        started = _now()
        role_order = ["community", "model_brainstorm", "future_work"]
        placeholders = {
            role: AgentRun(role=role, status="queued", provider="pending") for role in role_order
        }

        def run_community() -> tuple[AgentRun, list[CommunitySignal], list[InnovationCandidate], list[FutureWorkSignal]]:
            run = placeholders["community"].model_copy(update={"status": "running", "started_at": _now()})
            try:
                provider = _community_provider(settings)
                terms = _community_query_terms(concept, community_query_terms)
                signals = provider.search(concept, 6, query_terms=terms)
                done = _now()
                is_demo = provider.name == "demo_community"
                run = run.model_copy(
                    update={
                        "status": "completed",
                        "provider": provider.name,
                        "query_terms": terms,
                        "output_ids": [item.id for item in signals],
                        "summary": f"从 {provider.name} 返回 {len(signals)} 条探索性社区信号。",
                        "warnings": [
                            "社区内容仅用于发现问题，未作为科学证据。",
                            *(["当前为演示社区 Provider。"] if is_demo else ["已读取实时公开社区内容；请打开来源并人工核验上下文。"]),
                        ],
                        "completed_at": done,
                        "duration_ms": _duration_ms(run.started_at or done, done),
                    }
                )
                # Keep community signals separate from generated candidates;
                # synthesis creates a clearly labelled candidate from them.
                return run, signals, [], []
            except Exception as exc:  # noqa: BLE001 - branch failures are isolated
                done = _now()
                run = run.model_copy(
                    update={
                        "status": "failed",
                        "provider": getattr(settings, "community_provider", "unknown"),
                        "error": str(exc),
                        "warnings": ["社区 Agent 失败；该失败不能解释为没有社区痛点。"],
                        "completed_at": done,
                        "duration_ms": _duration_ms(run.started_at or done, done),
                    }
                )
                return run, [], [], []

        def run_model() -> tuple[AgentRun, list[CommunitySignal], list[InnovationCandidate], list[FutureWorkSignal]]:
            run = placeholders["model_brainstorm"].model_copy(
                update={
                    "status": "running",
                    "started_at": _now(),
                    "provider": "heuristic_fallback",
                    "query_terms": [concept],
                }
            )
            try:
                ideas, provider_name, model_warnings = _model_brainstorm(
                    concept, papers, evidence, explanation_provider, language
                )
                done = _now()
                run = run.model_copy(
                    update={
                        "status": "completed",
                        "provider": provider_name,
                        "output_ids": [item.id for item in ideas],
                        "evidence_ids": [evidence_item.id for evidence_item in evidence],
                        "summary": f"生成 {len(ideas)} 个模型/规则脑暴候选。",
                        "warnings": model_warnings + [
                            "候选来自模型或透明启发式，未验证，不代表原创。",
                        ],
                        "completed_at": done,
                        "duration_ms": _duration_ms(run.started_at or done, done),
                    }
                )
                ideas = [item.model_copy(update={"source_agent_run_id": run.id}) for item in ideas]
                return run, [], ideas, []
            except Exception as exc:  # noqa: BLE001
                done = _now()
                return run.model_copy(
                    update={"status": "failed", "error": str(exc), "completed_at": done, "duration_ms": _duration_ms(run.started_at or done, done)}
                ), [], [], []

        def run_future() -> tuple[AgentRun, list[CommunitySignal], list[InnovationCandidate], list[FutureWorkSignal]]:
            run = placeholders["future_work"].model_copy(
                update={
                    "status": "running",
                    "started_at": _now(),
                    "provider": "abstract_evidence",
                    "query_terms": [
                        f"{concept} limitations",
                        f"{concept} future work",
                        f"{concept} discussion",
                    ],
                }
            )
            try:
                signals = _future_work_signals(concept, papers, evidence)
                done = _now()
                run = run.model_copy(
                    update={
                        "status": "completed",
                        "input_paper_ids": [paper.id for paper in papers],
                        "output_ids": [item.id for item in signals],
                        "evidence_ids": [item.evidence_id for item in signals if item.evidence_id],
                        "summary": f"从摘要级资料提取 {len(signals)} 条限制/后续工作线索。",
                        "warnings": [
                            "当前主要读取摘要和元数据；尚未声称已阅读 Discussion 全文。",
                            "需要人工打开原文核对 section、上下文和实验条件。",
                        ],
                        "completed_at": done,
                        "duration_ms": _duration_ms(run.started_at or done, done),
                    }
                )
                # Future-work signals are retained as first-class provenance;
                # synthesis derives candidates from them after all branches
                # complete.
                return run, [], [], signals
            except Exception as exc:  # noqa: BLE001
                done = _now()
                return run.model_copy(
                    update={"status": "failed", "error": str(exc), "completed_at": done, "duration_ms": _duration_ms(run.started_at or done, done)}
                ), [], [], []

        tasks = {"community": run_community, "model_brainstorm": run_model, "future_work": run_future}
        outputs: dict[str, tuple[AgentRun, list[CommunitySignal], list[InnovationCandidate], list[FutureWorkSignal]]] = {}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="wishforge-agent") as executor:
            future_map = {executor.submit(task): role for role, task in tasks.items()}
            for future in as_completed(future_map):
                role = future_map[future]
                try:
                    outputs[role] = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard
                    run = placeholders[role].model_copy(
                        update={"status": "failed", "error": str(exc), "warnings": ["Agent 未知错误。"]}
                    )
                    outputs[role] = (run, [], [], [])

        community: list[CommunitySignal] = []
        model_ideas: list[InnovationCandidate] = []
        future_signals: list[FutureWorkSignal] = []
        agent_runs: list[AgentRun] = []
        warnings: list[str] = []
        for role in role_order:
            run, community_items, model_items, future_items = outputs[role]
            agent_runs.append(run)
            community.extend(community_items)
            model_ideas.extend(model_items)
            future_signals.extend(future_items)
            warnings.extend(run.warnings)
            if run.error:
                role_label = {
                    "community": "社区",
                    "model_brainstorm": "模型脑暴",
                    "future_work": "论文 Future Work",
                }.get(role, role)
                warnings.append(f"{role_label} Agent 未完成：{run.error}")

        synthesis_run_id = str(uuid4())
        synthesis, candidates, synthesis_provider, synthesis_warnings = _model_synthesis(
            concept,
            community,
            model_ideas,
            future_signals,
            existing_candidates,
            explanation_provider,
            synthesis_run_id,
        )
        arxiv_status, arxiv_terms, arxiv_matches, arxiv_warnings = _check_arxiv(
            candidates, search_provider
        )
        warnings.extend(arxiv_warnings)
        for candidate in candidates:
            if candidate.arxiv_status == "not_checked":
                candidate.arxiv_status = (
                    "no_direct_match_in_scope" if arxiv_status in {"matched", "no_direct_match_in_scope"} else arxiv_status
                )

        synthesis_run = AgentRun(
            id=synthesis_run_id,
            role="synthesis",
            status="completed",
            provider=synthesis_provider,
            input_paper_ids=[paper.id for paper in papers],
            output_ids=[item.id for item in candidates],
            evidence_ids=[item.id for item in evidence],
            summary=(
                f"综合 {len(community)} 条社区信号、{len(model_ideas)} 个模型候选和 "
                f"{len(future_signals)} 条论文限制线索，形成 {len(candidates)} 个待验证候选。"
            ),
            warnings=synthesis_warnings + [
                "综合结果是探索性假设，必须经过全文检索、人工审阅和最小实验验证。",
                "arXiv 检查受限于当前 Provider、关键词和返回数量，不构成全网保证。",
            ],
            started_at=started,
            completed_at=_now(),
            duration_ms=_duration_ms(started, _now()),
        )
        agent_runs.append(synthesis_run)
        warnings.extend(synthesis_run.warnings)
        coverage = {
            "community_signals": 1.0 if community else 0.0,
            "model_brainstorm": 1.0 if model_ideas else 0.0,
            "paper_future_work": 1.0 if future_signals else 0.0,
            "arxiv_scope_check": 1.0 if arxiv_status in {"matched", "no_direct_match_in_scope"} else 0.0,
        }
        # ResearchBrief keeps the finer scoped states so the UI can
        # distinguish a bounded match from a bounded non-match.  Neither is a
        # global originality guarantee.
        brief_arxiv_status = arxiv_status
        synthesis = (
            f"{synthesis} 围绕“{concept}”的候选仍需全文核验、人工审阅和最小实验；"
            "它们不是已确认创新。"
        )
        return ResearchBrief(
            topic=concept,
            agent_runs=agent_runs,
            community_signals=community,
            model_ideas=model_ideas,
            future_work_signals=future_signals,
            innovation_candidates=candidates,
            synthesis=synthesis,
            arxiv_status=("not_checked" if not candidates else brief_arxiv_status),
            arxiv_checked_terms=arxiv_terms,
            arxiv_match_paper_ids=arxiv_matches,
            coverage=coverage,
            warnings=list(dict.fromkeys(warnings)),
        )


research_orchestrator = ResearchOrchestrator()
