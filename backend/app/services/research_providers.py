import json
import logging
import re
import hashlib
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from collections.abc import Callable, Sequence
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx

from app.research_schemas import (
    AtomicClaimDraft,
    CommunitySignal,
    EvidenceCard,
    EvolutionItem,
    ExplanationResult,
    FutureWorkSignal,
    InnovationCandidate,
    PaperRecord,
    ReproducibilityCheck,
    ResearchGapCandidate,
    ResearchLimitation,
    SearchQueryPlan,
)


logger = logging.getLogger(__name__)


class ProviderUnavailable(RuntimeError):
    """Raised when an external provider cannot be reached or understood."""

    code = "provider_unavailable"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        provider: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.code
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds

    def public_detail(self) -> dict[str, str | float | None]:
        """Return stable metadata without exposing provider internals or keys.

        Callers still render ``str(exc)`` for backwards compatibility, while
        API layers that need a structured error can use this method instead of
        attempting to parse a human-facing message.
        """

        return {
            "code": self.code,
            "provider": self.provider,
            "message": str(self),
            "retry_after_seconds": self.retry_after_seconds,
        }


class ProviderRateLimited(ProviderUnavailable):
    """A bounded, actionable Semantic Scholar rate-limit failure."""

    def __init__(
        self,
        *,
        api_key_configured: bool,
        retries_attempted: int,
        waited_seconds: float,
        max_wait_seconds: float,
        retry_after_seconds: float | None,
        stopped_by_wait_cap: bool = False,
    ) -> None:
        self.api_key_configured = api_key_configured
        self.retries_attempted = retries_attempted
        self.waited_seconds = waited_seconds
        self.max_wait_seconds = max_wait_seconds
        self.stopped_by_wait_cap = stopped_by_wait_cap

        message_parts = ["Semantic Scholar 请求过于频繁，已被限流（HTTP 429）。"]
        if api_key_configured:
            message_parts.append(
                "当前已配置论文检索 API Key，但仍受到服务端速率或配额限制；请稍后重试并检查该 Key 的配额。"
            )
        else:
            message_parts.append(
                "当前为匿名/未配置论文检索 API Key 的请求，公开额度较低；"
                "可在设置页填写论文检索 Key（WISHFORGE_PAPER_API_KEY）后再试。"
            )
        if retry_after_seconds is not None:
            message_parts.append(
                f"服务端建议至少等待 {_format_wait_seconds(retry_after_seconds)} 后再请求。"
            )
        if retries_attempted:
            message_parts.append(
                f"客户端已按退避策略重试 {retries_attempted} 次，累计等待 {_format_wait_seconds(waited_seconds)}。"
            )
        if stopped_by_wait_cap:
            message_parts.append(
                f"为避免长时间阻塞，本次最多等待 {_format_wait_seconds(max_wait_seconds)}，"
                "因此没有在服务端要求的等待时间之前再次请求。"
            )
        message_parts.append(
            "仅在启用演示模式时，系统才会回退到演示资料；演示资料不能作为正式科学证据引用。"
        )
        super().__init__(
            "".join(message_parts),
            code="provider_rate_limited",
            provider="semantic_scholar",
            retry_after_seconds=retry_after_seconds,
        )


def _format_wait_seconds(seconds: float) -> str:
    """Format a delay compactly for a Chinese user-facing provider message."""

    value = float(seconds)
    if value.is_integer():
        return f"{int(value)} 秒"
    return f"{value:.1f} 秒"


def _parse_retry_after(value: str | None) -> float | None:
    """Parse an RFC Retry-After value as a non-negative number of seconds.

    Semantic Scholar normally returns an integer number of seconds, but HTTP
    also permits an IMF-fixdate. Invalid values are intentionally ignored and
    fall back to the local exponential backoff rather than causing a parsing
    failure that masks the original rate-limit response.
    """

    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


class SearchProvider(Protocol):
    name: str

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        ...


class ExplanationProvider(Protocol):
    name: str

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        ...


class BrainstormProvider(Protocol):
    """Optional model capability used by the research-mode brainstorm agent."""

    name: str

    def brainstorm(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        language: str,
    ) -> list[InnovationCandidate]:
        ...


class SynthesisProvider(Protocol):
    """Optional model capability for combining the three research branches."""

    name: str

    def synthesize_research(
        self,
        concept: str,
        community_signals: Sequence[CommunitySignal],
        model_ideas: Sequence[InnovationCandidate],
        future_work_signals: Sequence[FutureWorkSignal],
    ) -> tuple[str, list[InnovationCandidate]]:
        ...


class ArxivSearchProvider:
    """Search arXiv's public Atom API and normalize entries into papers.

    Each call requests one small relevance-sorted page.  When an analysis uses
    more than one retrieval angle, the instance spaces calls so the public
    endpoint is not hit in a tight loop.
    """

    name = "arxiv"
    endpoint = "https://export.arxiv.org/api/query"
    _ATOM = "{http://www.w3.org/2005/Atom}"
    _ARXIV = "{http://arxiv.org/schemas/atom}"

    def __init__(
        self,
        timeout: float = 30.0,
        minimum_interval_seconds: float = 3.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self._sleep = sleep
        self._clock = clock
        self._last_request_started_at: float | None = None

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        query_text = " ".join(concept.replace('"', " ").split())
        if not query_text:
            return []
        params = {
            "search_query": f'all:"{query_text}"',
            "start": 0,
            "max_results": max(1, min(limit, 12)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        if self._last_request_started_at is not None:
            elapsed = self._clock() - self._last_request_started_at
            remaining = self.minimum_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_started_at = self._clock()
        try:
            response = httpx.get(
                self.endpoint,
                params=params,
                headers={"User-Agent": "WishForge/0.1 (research concept explorer)"},
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"arXiv 暂时不可用：{exc}", provider=self.name
            ) from exc

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ProviderUnavailable(
                "arXiv 返回了无法解析的 Atom 响应。", provider=self.name
            ) from exc

        records: list[PaperRecord] = []
        for entry in root.findall(f"{self._ATOM}entry"):
            record = self._parse_entry(entry)
            if record is not None:
                records.append(record)
        return records[:limit]

    def _parse_entry(self, entry: ET.Element) -> PaperRecord | None:
        entry_url = self._text(entry, "id")
        title = self._clean_text(self._text(entry, "title"))
        if not entry_url or "/abs/" not in entry_url or not title:
            # arXiv represents some API errors as an Atom entry.  Do not turn
            # that entry into a fake academic paper.
            return None

        raw_id = entry_url.rstrip("/").rsplit("/abs/", 1)[-1]
        version_match = re.search(r"(v\d+)$", raw_id)
        version = version_match.group(1) if version_match else None
        canonical_arxiv_id = raw_id[: -len(version)] if version else raw_id
        published = self._text(entry, "published")
        year: int | None = None
        if published and re.match(r"^\d{4}", published):
            year = int(published[:4])

        authors = [
            self._clean_text(self._text(author, "name"))
            for author in entry.findall(f"{self._ATOM}author")
        ]
        authors = [author for author in authors if author]
        alternate_url = entry_url.replace("http://", "https://", 1)
        for link in entry.findall(f"{self._ATOM}link"):
            if link.attrib.get("rel") == "alternate" and link.attrib.get("href"):
                alternate_url = link.attrib["href"].replace("http://", "https://", 1)
                break

        primary_category = entry.find(f"{self._ARXIV}primary_category")
        category = primary_category.attrib.get("term") if primary_category is not None else None
        journal_ref = self._clean_text(entry.findtext(f"{self._ARXIV}journal_ref") or "")
        doi = self._clean_text(entry.findtext(f"{self._ARXIV}doi") or "") or None
        abstract = self._clean_text(self._text(entry, "summary"))

        return PaperRecord(
            id=f"arxiv:{raw_id}",
            canonical_id=f"arxiv:{canonical_arxiv_id}",
            provider_id=raw_id,
            arxiv_id=canonical_arxiv_id,
            version=version,
            title=title,
            authors=authors,
            year=year,
            venue=journal_ref or (f"arXiv:{category}" if category else "arXiv"),
            abstract=abstract,
            url=alternate_url,
            doi=doi,
            citation_count=None,
            source=self.name,
            source_kind="academic",
            access_type="open_access",
            retrieved_at=datetime.now(timezone.utc),
        )

    def _text(self, element: ET.Element, name: str) -> str:
        return element.findtext(f"{self._ATOM}{name}") or ""

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())


class SemanticScholarProvider:
    name = "semantic_scholar"

    # A retrieval task should not tie up its worker for tens of seconds just
    # because a public API is saturated. These values mean one initial request
    # plus at most two retries, with no more than three seconds of deliberate
    # waiting in total. Constructor parameters keep the policy testable while
    # retaining safe bounded defaults for production callers.
    _DEFAULT_MAX_RETRIES = 2
    _DEFAULT_BACKOFF_SECONDS = 0.5
    _DEFAULT_MAX_RETRY_WAIT_SECONDS = 3.0

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 20.0,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = _DEFAULT_BACKOFF_SECONDS,
        max_retry_wait_seconds: float = _DEFAULT_MAX_RETRY_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries 不能小于 0")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds 不能小于 0")
        if max_retry_wait_seconds < 0:
            raise ValueError("max_retry_wait_seconds 不能小于 0")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_retry_wait_seconds = max_retry_wait_seconds
        self._sleep = sleep

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        headers = {"User-Agent": "WishForge/0.1"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        params = {
            "query": concept,
            "limit": limit,
            "fields": "paperId,title,abstract,authors,year,venue,url,openAccessPdf,citationCount,externalIds",
        }
        total_wait_seconds = 0.0
        last_retry_after_seconds: float | None = None
        response: httpx.Response | None = None

        # Retry HTTP 429 only. Transport failures and 4xx/5xx responses keep
        # their existing fail-fast behavior so we do not amplify an outage.
        for retry_index in range(self.max_retries + 1):
            try:
                response = httpx.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f"Semantic Scholar 暂时不可用：{exc}") from exc

            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                break

            last_retry_after_seconds = _parse_retry_after(response.headers.get("Retry-After"))
            if retry_index >= self.max_retries:
                raise ProviderRateLimited(
                    api_key_configured=bool(self.api_key),
                    retries_attempted=retry_index,
                    waited_seconds=total_wait_seconds,
                    max_wait_seconds=self.max_retry_wait_seconds,
                    retry_after_seconds=last_retry_after_seconds,
                )

            # Retry-After is a server-imposed lower bound. We therefore take
            # the larger of it and our exponential backoff, never silently
            # retry before the value supplied by the service.
            exponential_delay = self.retry_backoff_seconds * (2**retry_index)
            delay = max(last_retry_after_seconds or 0.0, exponential_delay)
            if total_wait_seconds + delay > self.max_retry_wait_seconds:
                raise ProviderRateLimited(
                    api_key_configured=bool(self.api_key),
                    retries_attempted=retry_index,
                    waited_seconds=total_wait_seconds,
                    max_wait_seconds=self.max_retry_wait_seconds,
                    retry_after_seconds=last_retry_after_seconds,
                    stopped_by_wait_cap=True,
                )
            if delay:
                self._sleep(delay)
                total_wait_seconds += delay

        # A loop exit at this point always has a non-429 response. The guard
        # is kept explicit so later maintenance cannot accidentally turn an
        # exhausted rate-limit path into an empty-paper result.
        if response is None or response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise ProviderRateLimited(
                api_key_configured=bool(self.api_key),
                retries_attempted=self.max_retries,
                waited_seconds=total_wait_seconds,
                max_wait_seconds=self.max_retry_wait_seconds,
                retry_after_seconds=last_retry_after_seconds,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Semantic Scholar 暂时不可用：{exc}") from exc

        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailable("Semantic Scholar 返回了无法解析的响应。") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data", []), list):
            raise ProviderUnavailable("Semantic Scholar 返回格式不符合预期。")

        records: list[PaperRecord] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            external_ids = item.get("externalIds") or {}
            open_access = item.get("openAccessPdf") or {}
            records.append(
                PaperRecord(
                    id=item.get("paperId") or external_ids.get("DOI") or item.get("title", "unknown"),
                    provider_id=item.get("paperId"),
                    canonical_id=external_ids.get("DOI") or item.get("paperId"),
                    arxiv_id=external_ids.get("ArXiv"),
                    title=item.get("title") or "未命名论文",
                    authors=[author.get("name", "") for author in item.get("authors", []) if author.get("name")],
                    year=item.get("year"),
                    venue=item.get("venue") or None,
                    abstract=item.get("abstract") or "",
                    url=item.get("url") or open_access.get("url"),
                    doi=external_ids.get("DOI"),
                    citation_count=item.get("citationCount"),
                    source=self.name,
                    source_kind="academic",
                    access_type="open_access" if open_access.get("url") else "abstract_only",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        return records


class DemoSearchProvider:
    """Small transparent fixture so the first version works without credentials."""

    name = "demo"

    _fixtures = {
        "paged_attention": [
            PaperRecord(
                id="demo-vllm-paged-attention",
                title="vLLM: Easy, Fast, and Cheap LLM Serving with PagedAttention",
                authors=["Woosuk Kwon", "Zongyu Li"],
                year=2023,
                venue="ACM SOSP",
                abstract=(
                    "The paper presents vLLM, a high-throughput serving system for large language models. "
                    "PagedAttention manages the key-value cache as fixed-size pages, borrowing the idea of virtual memory "
                    "to reduce fragmentation and support efficient sharing during generation. "
                    "The authors report improved serving throughput while discussing scheduling and memory trade-offs."
                ),
                url="https://arxiv.org/abs/2309.06180",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
            PaperRecord(
                id="demo-kv-cache-compression",
                title="Efficient KV Cache Compression for Long-Context Language Model Serving",
                authors=["WishForge demo fixture"],
                year=2024,
                venue="arXiv",
                abstract=(
                    "This fixture represents work on reducing key-value cache memory for long-context generation. "
                    "It highlights a common limitation: compression can lower memory use but may affect answer quality, "
                    "so sequence length, latency and accuracy should be evaluated together."
                ),
                url="https://arxiv.org/",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
        "attention": [
            PaperRecord(
                id="demo-attention-vaswani",
                title="Attention Is All You Need",
                authors=["Ashish Vaswani", "Noam Shazeer"],
                year=2017,
                venue="NeurIPS",
                abstract=(
                    "The paper introduces the Transformer, an architecture based entirely on attention mechanisms. "
                    "Self-attention connects tokens in a sequence and avoids recurrence, enabling parallel training. "
                    "The authors report strong machine translation results while discussing computational trade-offs."
                ),
                url="https://arxiv.org/abs/1706.03762",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
            PaperRecord(
                id="demo-attention-flash",
                title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
                authors=["Tri Dao", "Daniel Y. Fu"],
                year=2022,
                venue="NeurIPS",
                abstract=(
                    "FlashAttention computes exact attention with an IO-aware tiled algorithm. "
                    "The work targets the memory movement bottleneck of standard attention and reports faster training "
                    "and lower memory use without changing the mathematical attention operation."
                ),
                url="https://arxiv.org/abs/2205.14135",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
        "lora": [
            PaperRecord(
                id="demo-lora-original",
                title="LoRA: Low-Rank Adaptation of Large Language Models",
                authors=["Edward J. Hu", "Yelong Shen"],
                year=2021,
                venue="ICLR",
                abstract=(
                    "LoRA freezes pretrained model weights and injects trainable low-rank matrices into Transformer layers. "
                    "The approach substantially reduces trainable parameters while maintaining competitive task quality. "
                    "The authors discuss rank selection and the limits of transferring a single adaptation across tasks."
                ),
                url="https://arxiv.org/abs/2106.09685",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
    }

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        normalized = re.sub(r"[^a-z0-9]+", " ", concept.lower()).strip()
        aliases = {
            "paged_attention": {"pagedattention", "paged attention", "分页注意力", "分页机制", "kv cache", "kv缓存", "键值缓存"},
            "attention": {"注意力", "注意力机制", "self attention", "自注意力"},
            "lora": {"低秩适配", "低秩微调", "参数高效微调", "qlora"},
        }
        for key, papers in self._fixtures.items():
            if key in normalized or key in concept.lower() or any(
                alias in concept.lower() for alias in aliases.get(key, set())
            ):
                return papers[:limit]
        slug = re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")
        if not slug:
            slug = f"concept-{hashlib.sha1(concept.encode('utf-8')).hexdigest()[:10]}"
        return [
            PaperRecord(
                id=f"demo-{slug}",
                title=f"关于“{concept}”的示例研究资料",
                year=None,
                abstract=(
                    f"这是 WishForge 的演示资料占位项，用于展示“{concept}”的证据卡和概念图流程。"
                    "它不是实际论文，接入真实检索 Provider 后会被替换。"
                ),
                url=None,
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            )
        ][:limit]


class RuleBasedExplanationProvider:
    name = "rule_based_fallback"

    def plan_search_query(self, concept: str, language: str) -> str:
        """Return the original term when no model is available to translate it."""

        return " ".join(concept.split())

    def plan_search_queries(self, concept: str, language: str) -> list[SearchQueryPlan]:
        """Keep one honest angle when no model can translate neighboring terms."""

        return [SearchQueryPlan(query=self.plan_search_query(concept, language), purpose="core")]

    def plan_followup_queries(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        existing_queries: Sequence[SearchQueryPlan],
        language: str,
    ) -> list[SearchQueryPlan]:
        """Extract a few visible method-family terms without inventing synonyms."""

        corpus = " ".join(f"{paper.title} {paper.abstract}" for paper in papers).casefold()
        existing = {item.query.casefold() for item in existing_queries}
        candidates: list[tuple[str, str]] = []
        if "evict" in corpus or "eviction" in corpus:
            candidates.append(("KV cache eviction", "method_family"))
        if "prun" in corpus or "critical token" in corpus:
            candidates.append(("KV cache token pruning", "method_family"))
        if "quantiz" in corpus:
            candidates.append(("KV cache quantization", "method_family"))
        if "low-rank" in corpus or "low rank" in corpus or "latent" in corpus:
            candidates.append(("low rank KV cache", "method_family"))
        if "reasoning" in corpus:
            candidates.append(("KV cache reasoning models", "application"))
        if "code" in corpus and "agent" in corpus:
            candidates.append(("KV cache agentic coding", "application"))
        source_ids = [paper.id for paper in papers[:6]]
        planned: list[SearchQueryPlan] = []
        for query, purpose in candidates:
            if query.casefold() in existing:
                continue
            planned.append(
                SearchQueryPlan(
                    query=query,
                    purpose=purpose,
                    phase="feedback",
                    derived_from_paper_ids=source_ids,
                )
            )
            if len(planned) >= 3:
                break
        return planned

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        evidence_text = evidence[0].excerpt if evidence else "当前还没有可用的文献证据。"
        related = _related_terms(concept, papers)
        evidence_by_paper: dict[str, list[str]] = {}
        for card in evidence:
            evidence_by_paper.setdefault(card.paper_id, []).append(card.id)
        evolution_items = [
            EvolutionItem(
                year=paper.year,
                title=paper.title,
                summary="该论文摘要构成当前检索范围内的一条演变线索，具体贡献仍需核对原文。",
                paper_ids=[paper.id],
                evidence_ids=evidence_by_paper.get(paper.id, [])[:3],
            )
            for paper in sorted(papers[:5], key=lambda item: (item.year is None, item.year or 9999))
        ]
        paper_by_id = {paper.id: paper for paper in papers}
        claims: list[AtomicClaimDraft] = []
        if evidence:
            claims.append(
                AtomicClaimDraft(
                    claim_type="definition",
                    text=f"{concept} 是围绕当前论文摘要所描述问题的一类研究方法。",
                    paper_ids=[],
                    evidence_ids=[],
                    scope="规则回退的通用定义，尚无论文证据",
                )
            )
        else:
            claims.append(
                AtomicClaimDraft(
                    claim_type="definition",
                    text=f"{concept} 是一个需要通过后续文献检索核验的科研概念。",
                    paper_ids=[],
                    evidence_ids=[],
                    scope="通用知识，待检索核验",
                )
            )
        for card in evidence:
            card_types = set(card.evidence_types or [card.evidence_type])
            claim_type = (
                "result"
                if "result" in card_types
                else "mechanism"
                if "mechanism" in card_types
                else None
            )
            if claim_type is None:
                continue
            paper = paper_by_id.get(card.paper_id)
            claims.append(
                AtomicClaimDraft(
                    claim_type=claim_type,
                    text=f"《{paper.title if paper else card.paper_id}》摘要指出：{card.excerpt}",
                    paper_ids=[card.paper_id],
                    evidence_ids=[card.id],
                    evidence_quotes=[card.excerpt],
                    scope="摘要级线索",
                )
            )
        return ExplanationResult(
            one_sentence=f"{concept} 是一个需要结合具体问题和证据来理解的科研概念。",
            intuitive=(
                f"可以先把“{concept}”看成一种解决特定研究问题的思路。"
                "它的具体作用、优点和限制，需要结合论文中的实验条件来判断。"
            ),
            technical=(
                f"当前为 {audience} 生成的第一版解释：{evidence_text}"
                "详细机制会在接入解释模型后，根据证据卡进一步展开。"
            ),
            evolution=[f"{paper.year or '未标年份'}：{paper.title}" for paper in papers[:5]],
            evolution_items=evolution_items,
            claims=claims[:20],
            related_concepts=related,
            limitations=[
                "当前第一版主要使用摘要和元数据，不能替代对论文全文和实验细节的人工核验。",
                "规则回退解释不是模型生成结论，需等待解释模型配置后获得更丰富的分层说明。",
            ],
            scope_warnings=[
                "当前仅使用摘要和元数据，不能替代论文全文核验。",
                "当前为规则回退解释，原子主张仅用于演示证据链。",
            ],
            evidence_ids=[item.id for item in evidence],
        )


class OpenAICompatibleExplanationProvider:
    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 45.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def plan_search_query(self, concept: str, language: str) -> str:
        """Backward-compatible first query for callers that expect one phrase."""

        return self.plan_search_queries(concept, language)[0].query

    def plan_search_queries(self, concept: str, language: str) -> list[SearchQueryPlan]:
        """Generate two or three distinct, bounded arXiv retrieval angles."""

        prompt = f"""
请把用户输入的科研概念转换成 2 到 3 个适合 arXiv 标题/摘要检索的英文短语。
用户输入：{concept}
用户语言：{language}
检索角度最多各一个：
- core：该概念当前最标准的学术术语；
- foundational：早期或基础工作常用的标准术语；
- recent：近年相关工作常用的相邻标准术语。
只返回 JSON 对象：
{{"queries": [{{"query": "2 到 10 个英文单词", "purpose": "core"}}]}}。
不要加入 all:、布尔运算符、引号、解释、论文标题或年份。
不要只是在同一术语后添加 survey、recent、review 等修饰词；不同 query 必须能表达真实的术语差异。
如果没有可靠的相邻术语，只返回 core 一项，不要编造。
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "你负责生成保守、精确的英文学术检索词。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(_strip_code_fence(content))
            raw_queries = payload.get("queries") if isinstance(payload, dict) else None
            if not isinstance(raw_queries, list):
                raise ValueError("缺少 queries 字段")
            allowed_purposes = {"core", "foundational", "recent"}
            planned: list[SearchQueryPlan] = []
            seen: set[str] = set()
            for item in raw_queries[:3]:
                if not isinstance(item, dict):
                    continue
                query = item.get("query")
                purpose = item.get("purpose")
                if not isinstance(query, str) or purpose not in allowed_purposes:
                    continue
                query = " ".join(query.replace('"', " ").split())
                normalized = query.casefold()
                if not 2 <= len(query) <= 160 or normalized in seen:
                    continue
                seen.add(normalized)
                planned.append(SearchQueryPlan(query=query, purpose=purpose))
            if not planned:
                raise ValueError("queries 中没有有效检索词")
            return planned
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"检索词生成模型暂时不可用：{exc}") from exc

    def plan_followup_queries(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        existing_queries: Sequence[SearchQueryPlan],
        language: str,
    ) -> list[SearchQueryPlan]:
        """Use first-round abstracts to discover missing method-family terms."""

        paper_payload = "\n\n".join(
            f"[{paper.id}] {paper.title} ({paper.year or 'n.d.'})\n摘要：{paper.abstract}"
            for paper in papers[:10]
        )
        existing_payload = ", ".join(item.query for item in existing_queries)
        prompt = f"""
用户研究概念：{concept}
用户语言：{language}
首轮已使用检索词：{existing_payload}

首轮论文：
{paper_payload}

请从首轮论文标题和摘要中识别首轮关键词没有覆盖的方法族、同义术语或明确应用场景，
生成最多 3 个新的英文 arXiv 检索短语，用于第二轮补充检索。

要求：
1. query 必须是论文中出现或可由论文直接确认的标准学术术语，2 到 10 个英文单词；
2. 不得只是给原查询添加 survey、recent、review、future work 等修饰词；
3. 不得重复首轮查询；没有可靠扩展词时返回空数组；
4. purpose 只能是 method_family、application、foundational、recent；
5. derived_from_paper_ids 只能使用上方论文 ID，指出该术语来自哪些首轮论文。

只返回 JSON：
{{"queries": [{{"query": "KV cache eviction", "purpose": "method_family", "derived_from_paper_ids": ["paper-id"]}}]}}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "你负责从已检索论文中发现可追溯的补充学术检索词。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(_strip_code_fence(content))
            raw_queries = payload.get("queries") if isinstance(payload, dict) else None
            if not isinstance(raw_queries, list):
                raise ValueError("缺少 queries 字段")
            known_paper_ids = {paper.id for paper in papers}
            existing = {" ".join(item.query.casefold().split()) for item in existing_queries}
            allowed_purposes = {"method_family", "application", "foundational", "recent"}
            planned: list[SearchQueryPlan] = []
            seen = set(existing)
            for item in raw_queries[:3]:
                if not isinstance(item, dict):
                    continue
                query = item.get("query")
                purpose = item.get("purpose")
                source_ids = item.get("derived_from_paper_ids", [])
                if not isinstance(query, str) or purpose not in allowed_purposes:
                    continue
                query = " ".join(query.replace('"', " ").split())
                normalized = query.casefold()
                if not 2 <= len(query) <= 160 or normalized in seen:
                    continue
                valid_source_ids = [
                    paper_id for paper_id in source_ids if isinstance(paper_id, str) and paper_id in known_paper_ids
                ]
                if not valid_source_ids:
                    continue
                seen.add(normalized)
                planned.append(
                    SearchQueryPlan(
                        query=query,
                        purpose=purpose,
                        phase="feedback",
                        derived_from_paper_ids=valid_source_ids[:6],
                    )
                )
            return planned
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"补充检索词生成模型暂时不可用：{exc}") from exc

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        evidence_payload = "\n\n".join(
            f"[{item.id}] {item.claim}\n关系：{item.relation}\n原文：{item.excerpt}" for item in evidence[:12]
        )
        paper_payload = "\n\n".join(
            f"- {paper.title} ({paper.year or 'n.d.'}) [{paper.id}]\n摘要：{paper.abstract[:2400]}"
            for paper in papers[:10]
        )
        if papers:
            mode_instructions = f"""
这是“文献解释”模式。请阅读给出的论文摘要，围绕资料解释概念，不能声称读过论文全文。
演变过程必须按年份组织，并说明每项工作带来的概念或方法变化；不得编造资料中没有的年份。
evolution_items 中每项必须包含 year、title、summary、paper_ids、evidence_ids，并且 ID 只能来自下方资料。
相关概念应说明与主概念紧密相关的标准术语。只能把资料支持的内容写成事实；
证据不足时明确说证据不足。evidence_ids 只能使用下方出现的证据卡 ID。

claims 必须是原子主张数组：
- 每条只能表达一个可独立核验的事实，不能把多个论文、多个机制或机制与指标写在同一条；
- claim_type 只能是 definition、mechanism、result、evolution；
- 论文特定的 mechanism、result、evolution 每条只能使用一个 paper_id；
- mechanism 每条只能描述一个主要操作；键量化、值量化、token 保留等不同操作必须拆开；
- 数字、压缩率、速度和准确率必须单独写成 result，不能混入 mechanism；
- paper_ids 和 evidence_ids 必须来自下方资料；没有证据的通用定义允许 ID 为空，但必须在 scope 中说明。
- 论文特定主张必须在 evidence_quotes 中逐字复制 1 至 3 条摘要原句；禁止翻译、改写或拼接原句。
- “首次、首个、最优、保证、无损”等强表述只有在 evidence_quotes 原文明确出现对应含义时才能使用。

research_limitations 只允许写“当前研究方法、理论或实验本身”的局限，不得写系统或调研过程警告。
每项必须包含 text、limitation_kind、target、condition、consequence、paper_ids、evidence_ids、explicitness。
limitation_kind 只能是 method_limitation、failure_mode、tradeoff、applicability_boundary、evaluation_limitation、theoretical_limit。
只有摘要原文明确支持、能指出目标和负面后果的内容才可进入；没有明确研究局限时返回空数组。

“仅阅读摘要、检索数量有限”等放入 scope_warnings；代码和数据未核验放入 reproducibility_checks；
“当前范围可能缺少统一标准”等放入 research_gap_candidates，并明确限定为当前检索范围，不得声称整个领域不存在。

reproducibility_checks 中的 check_type 只能是以下五个英文值之一：
- code：代码、实现或源码是否公开；
- data：数据集、数据处理或数据可得性；
- environment：依赖、硬件、运行环境或随机种子；
- license：代码或数据许可证；
- benchmark：基准、指标或评测协议。
“not verified”“unknown”“unverified”是状态，不是 check_type；arXiv ID 只能放入 paper_ids。
无法判断类型时不要生成该条。合法示例：
{{"text": "需要确认论文是否公开训练代码。", "check_type": "code", "paper_ids": ["arxiv:xxxx.xxxxx"]}}

论文及摘要：
{paper_payload}

证据卡：
{evidence_payload}
""".strip()
        else:
            mode_instructions = """
这是“快速解释”模式，没有执行论文检索。请直接基于通用学术知识给出易懂、准确的说明，
不要伪造论文、证据 ID 或具体引用。evolution 可以概括方法思路的演进，但 evolution_items 必须为空数组；
claims 可包含无来源的原子定义或机制主张，但 paper_ids 和 evidence_ids 必须为空，并在 scope 标记“通用知识，待检索核验”。
research_limitations、research_gap_candidates、reproducibility_checks 必须为空；
scope_warnings 必须说明本次没有检索论文。limitations 和 evidence_ids 必须为空数组。
""".strip()
        prompt = f"""
你是 WishForge 的科研概念解释器。请解释“{concept}”。
目标读者：{audience}；语言：{language}。
输出要先直觉、后技术，避免不解释的术语堆砌。
{mode_instructions}

必须返回 JSON，字段为：one_sentence、intuitive、technical、evolution（字符串数组）、
evolution_items（对象数组，每项含 year、title、summary、paper_ids、evidence_ids）、
claims（原子主张对象数组，每项含 claim_type、text、paper_ids、evidence_ids、scope）、
其中论文特定主张还必须包含 evidence_quotes（从摘要逐字复制的字符串数组），
research_limitations（研究局限对象数组）、
research_gap_candidates（对象数组，每项含 text、scope、paper_ids、evidence_ids）、
reproducibility_checks（对象数组，每项含 text、check_type、paper_ids）、
scope_warnings（字符串数组）、related_concepts（字符串数组）、
limitations（兼容字段，字符串数组，仅复制 research_limitations 的 text）、evidence_ids（证据卡 ID 数组）。
不要返回 model_output_warnings；该字段由系统根据解析过程生成。
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名严谨、诚实、重视证据的科研教师。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("解释模型返回的 content 不是字符串。")
            return _parse_explanation_result(content)
        except httpx.HTTPError as exc:
            logger.warning("Explanation model request failed", exc_info=True)
            raise ProviderUnavailable("解释模型请求失败，未能获得可用解释。") from exc
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Explanation model response failed core validation", exc_info=True)
            raise ProviderUnavailable("解释模型返回内容缺少必要字段或无法解析。") from exc

    def brainstorm(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        language: str,
    ) -> list[InnovationCandidate]:
        """Ask the configured compatible model for explicitly unverified ideas.

        This is a separate method from ``explain`` so the service can expose
        which model call produced a candidate and can fall back to the
        deterministic heuristic without pretending the two are equivalent.
        """

        paper_payload = "\n".join(
            f"- {paper.title} ({paper.year or 'n.d.'})\n  摘要：{paper.abstract[:900]}"
            for paper in papers[:10]
        )
        evidence_payload = "\n".join(
            f"[{item.id}] {item.claim}\n原文：{item.excerpt[:900]}" for item in evidence[:10]
        )
        prompt = f"""
你是 WishForge 的科研创新脑暴 Agent。围绕“{concept}”提出最多 3 个可检验的研究候选。
语言：{language}。只能把论文资料支持的内容当作背景，所有候选都必须标记为未验证。
返回 JSON 对象，唯一字段为 candidates；其值是对象数组。每个对象必须包含：
title、problem、mechanism、nearest_work（字符串数组）、novelty_level（只能是 L0/L1/L2/L3/L4）、
confidence（只能是 high/medium/low，建议 low）、feasibility（low/medium/high）、rationale、
validation_steps（字符串数组）、warning（字符串）。不要声称“保证原创”或“arXiv 没有”。

论文资料：
{paper_payload or '无'}

证据卡：
{evidence_payload or '无'}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名严谨、保守、重视可复现性的科研方法专家。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("创新脑暴模型返回的 content 不是字符串。")
            payload = json.loads(_strip_code_fence(content))
            raw_candidates = payload.get("candidates") if isinstance(payload, dict) else None
            if not isinstance(raw_candidates, list):
                raise ProviderUnavailable("创新脑暴模型没有返回 candidates 数组。")
            candidates: list[InnovationCandidate] = []
            for item in raw_candidates[:3]:
                if not isinstance(item, dict):
                    continue
                candidate = InnovationCandidate.model_validate(item).model_copy(
                    update={
                        "source_type": "model_generated",
                        "confidence": "low",
                        "warning": item.get("warning")
                        or "模型生成的待验证候选，不是已确认的新颖成果。",
                        "evidence_ids": [evidence_item.id for evidence_item in evidence],
                    }
                )
                candidates.append(candidate)
            if not candidates:
                raise ProviderUnavailable("创新脑暴模型返回的候选无法通过结构校验。")
            return candidates
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"创新脑暴模型暂时不可用：{exc}") from exc

    def synthesize_research(
        self,
        concept: str,
        community_signals: Sequence[CommunitySignal],
        model_ideas: Sequence[InnovationCandidate],
        future_work_signals: Sequence[FutureWorkSignal],
    ) -> tuple[str, list[InnovationCandidate]]:
        """Synthesize bounded upstream artifacts into cautious candidates."""

        community_payload = "\n".join(
            f"- [{item.platform}] {item.title}\n  痛点：{item.pain_point}\n  问题：{item.open_question}"
            for item in community_signals[:8]
        )
        model_payload = "\n".join(
            f"- {item.title}\n  问题：{item.problem}\n  机制：{item.mechanism}"
            for item in model_ideas[:6]
        )
        future_payload = "\n".join(
            f"- {item.paper_title} [{item.section}]：{item.excerpt[:700]}"
            for item in future_work_signals[:8]
        )
        prompt = f"""
你是 WishForge 的研究综合 Agent。请综合以下三类输入，围绕“{concept}”生成最多 4 个
值得人工核验的创新候选。社区内容只能作为痛点信号，论文内容目前主要是摘要级线索。
不要声称全球唯一、保证原创或 arXiv 上不存在相同工作。
返回 JSON 对象，字段：summary（字符串）、candidates（对象数组）。candidates 每项必须包含：
title、problem、mechanism、nearest_work（字符串数组）、novelty_level（L0-L4）、confidence、
feasibility、rationale、validation_steps（字符串数组）、warning。

社区信号：
{community_payload or '无'}

模型脑暴：
{model_payload or '无'}

论文限制 / Future Work 线索：
{future_payload or '无'}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名保守、可审计的科研综述编辑。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("研究综合模型返回的 content 不是字符串。")
            payload = json.loads(_strip_code_fence(content))
            if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
                raise ProviderUnavailable("研究综合模型没有返回 candidates 数组。")
            candidates: list[InnovationCandidate] = []
            for item in payload["candidates"][:4]:
                if not isinstance(item, dict):
                    continue
                candidates.append(
                    InnovationCandidate.model_validate(item).model_copy(
                        update={
                            "source_type": "synthesis",
                            "confidence": "low",
                            "warning": item.get("warning")
                            or "综合模型生成的待验证候选，不是已确认的新颖成果。",
                        }
                    )
                )
            if not candidates:
                raise ProviderUnavailable("研究综合模型返回的候选无法通过结构校验。")
            summary = payload.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                summary = f"模型综合了社区、脑暴和论文 Future Work 线索，形成 {len(candidates)} 个待验证候选。"
            return summary.strip()[:4000], candidates
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"研究综合模型暂时不可用：{exc}") from exc


_EXPLANATION_CORE_FIELDS = ("one_sentence", "intuitive", "technical")
_EXPLANATION_STRING_LIST_FIELDS: dict[str, int] = {
    "evolution": 30,
    "scope_warnings": 12,
    "related_concepts": 30,
    "limitations": 20,
    "evidence_ids": 40,
}
_EXPLANATION_ITEM_FIELDS = {
    "evolution_items": (EvolutionItem, 12),
    "claims": (AtomicClaimDraft, 40),
    "research_limitations": (ResearchLimitation, 20),
    "research_gap_candidates": (ResearchGapCandidate, 20),
    "reproducibility_checks": (ReproducibilityCheck, 20),
}
_REPRODUCIBILITY_CHECK_TYPES = {"code", "data", "environment", "license", "benchmark"}
_EXPLANATION_FIELD_LABELS = {
    "evolution_items": "演变条目",
    "claims": "原子主张",
    "research_limitations": "研究局限",
    "research_gap_candidates": "研究空白候选",
    "reproducibility_checks": "复现检查",
    "evolution": "演变过程",
    "scope_warnings": "调研范围提醒",
    "related_concepts": "相关概念",
    "limitations": "兼容局限字段",
    "evidence_ids": "证据关联",
}


def _parse_explanation_result(content: str) -> ExplanationResult:
    """Parse model JSON without letting one malformed optional item erase the answer.

    Core prose remains strict: malformed or missing one-sentence, intuitive, or
    technical explanations still fail the response. Optional structured arrays
    are validated item by item. Unsafe entries are removed and surfaced as
    user-readable repair notes while valid claims and limitations survive.
    """

    payload = json.loads(_strip_code_fence(content))
    if not isinstance(payload, dict):
        raise ValueError("解释模型必须返回 JSON 对象")

    repaired: dict[str, object] = {
        field: payload.get(field) for field in _EXPLANATION_CORE_FIELDS
    }
    repair_warnings: list[str] = []

    for field, limit in _EXPLANATION_STRING_LIST_FIELDS.items():
        repaired[field] = _clean_model_string_list(
            payload.get(field, []),
            field=field,
            limit=limit,
            warnings=repair_warnings,
        )

    for field, (model_type, limit) in _EXPLANATION_ITEM_FIELDS.items():
        repaired[field] = _clean_model_item_list(
            payload.get(field, []),
            field=field,
            model_type=model_type,
            limit=limit,
            warnings=repair_warnings,
        )

    expected_fields = {
        *_EXPLANATION_CORE_FIELDS,
        *_EXPLANATION_STRING_LIST_FIELDS,
        *_EXPLANATION_ITEM_FIELDS,
        "model_output_warnings",
    }
    unknown_count = len(set(payload) - expected_fields)
    if unknown_count:
        repair_warnings.append(
            f"模型返回了 {unknown_count} 个未约定字段，系统已忽略；其他有效内容不受影响。"
        )
    repaired["model_output_warnings"] = repair_warnings[:20]
    return ExplanationResult.model_validate(repaired)


def _clean_model_string_list(
    value: object,
    *,
    field: str,
    limit: int,
    warnings: list[str],
) -> list[str]:
    label = _EXPLANATION_FIELD_LABELS[field]
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"模型返回的{label}不是数组，系统已忽略该部分。")
        return []
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    dropped = len(value) - len(cleaned)
    if len(cleaned) > limit:
        dropped += len(cleaned) - limit
        cleaned = cleaned[:limit]
    if dropped:
        warnings.append(f"模型返回的{label}中有 {dropped} 条格式不合格，系统已忽略。")
    return cleaned


def _clean_model_item_list(
    value: object,
    *,
    field: str,
    model_type: type,
    limit: int,
    warnings: list[str],
) -> list[dict[str, object]]:
    label = _EXPLANATION_FIELD_LABELS[field]
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"模型返回的{label}不是数组，系统已忽略该部分。")
        return []

    cleaned: list[dict[str, object]] = []
    dropped = max(0, len(value) - limit)
    normalized = 0
    model_fields = set(model_type.model_fields)
    for raw_item in value[:limit]:
        if not isinstance(raw_item, dict):
            dropped += 1
            continue
        candidate = {key: raw_item[key] for key in model_fields if key in raw_item}
        if field == "reproducibility_checks":
            candidate, changed = _normalize_reproducibility_check(candidate)
            if candidate is None:
                dropped += 1
                continue
            normalized += int(changed)
        try:
            cleaned.append(model_type.model_validate(candidate).model_dump())
        except (TypeError, ValueError, AttributeError):
            dropped += 1

    if normalized:
        warnings.append(f"模型返回的{label}中有 {normalized} 条类型已自动纠正。")
    if dropped:
        warnings.append(
            f"模型返回的{label}中有 {dropped} 条无法安全校验，已忽略；其他解释和主张仍然保留。"
        )
    return cleaned


def _normalize_reproducibility_check(
    item: dict[str, object],
) -> tuple[dict[str, object] | None, bool]:
    raw_type = item.get("check_type")
    normalized_type = raw_type.strip().casefold() if isinstance(raw_type, str) else ""
    changed = normalized_type not in _REPRODUCIBILITY_CHECK_TYPES

    paper_ids = item.get("paper_ids", [])
    if not isinstance(paper_ids, list):
        paper_ids = []
        changed = True
    clean_paper_ids = [value for value in paper_ids if isinstance(value, str) and value.strip()]
    if normalized_type.startswith("arxiv:"):
        clean_paper_ids.append(normalized_type)

    if normalized_type not in _REPRODUCIBILITY_CHECK_TYPES:
        text = item.get("text") if isinstance(item.get("text"), str) else ""
        normalized_type = _infer_reproducibility_check_type(f"{raw_type or ''} {text}") or ""
    if normalized_type not in _REPRODUCIBILITY_CHECK_TYPES:
        return None, changed

    return {
        "text": item.get("text"),
        "check_type": normalized_type,
        "paper_ids": list(dict.fromkeys(clean_paper_ids))[:3],
    }, changed


def _infer_reproducibility_check_type(text: str) -> str | None:
    normalized = text.casefold()
    keyword_groups = (
        ("license", ("license", "licence", "许可证", "授权协议")),
        ("benchmark", ("benchmark", "metric", "evaluation", "基准", "指标", "评测")),
        (
            "environment",
            ("environment", "dependency", "hardware", "random seed", "环境", "依赖", "硬件", "随机种子"),
        ),
        ("data", ("dataset", "training data", "test data", "数据集", "训练数据", "测试数据")),
        ("code", ("source code", "implementation", "repository", "代码", "源码", "实现")),
    )
    for check_type, keywords in keyword_groups:
        if any(keyword in normalized for keyword in keywords):
            return check_type
    return None


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


def _related_terms(concept: str, papers: Sequence[PaperRecord]) -> list[str]:
    known_terms = [
        "Self-Attention",
        "Cross-Attention",
        "Transformer",
        "FlashAttention",
        "LoRA",
        "参数高效微调",
        "长序列建模",
        "可复现性",
    ]
    haystack = " ".join([concept, *(paper.title for paper in papers)]).lower()
    matches = [term for term in known_terms if term.lower() in haystack]
    return matches[:8]
