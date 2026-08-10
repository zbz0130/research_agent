import json
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
    CommunitySignal,
    EvidenceCard,
    EvolutionItem,
    ExplanationResult,
    FutureWorkSignal,
    InnovationCandidate,
    PaperRecord,
    SearchQueryPlan,
)


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
            related_concepts=related,
            limitations=[
                "当前第一版主要使用摘要和元数据，不能替代对论文全文和实验细节的人工核验。",
                "规则回退解释不是模型生成结论，需等待解释模型配置后获得更丰富的分层说明。",
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

论文及摘要：
{paper_payload}

证据卡：
{evidence_payload}
""".strip()
        else:
            mode_instructions = """
这是“快速解释”模式，没有执行论文检索。请直接基于通用学术知识给出易懂、准确的说明，
不要伪造论文、证据 ID 或具体引用。evolution 可以概括方法思路的演进，但 evolution_items 必须为空数组；
limitations 中必须说明本次没有检索论文，回答需要后续文献核验。evidence_ids 必须为空数组。
""".strip()
        prompt = f"""
你是 WishForge 的科研概念解释器。请解释“{concept}”。
目标读者：{audience}；语言：{language}。
输出要先直觉、后技术，避免不解释的术语堆砌。
{mode_instructions}

必须返回 JSON，字段为：one_sentence、intuitive、technical、evolution（字符串数组）、
evolution_items（对象数组，每项含 year、title、summary、paper_ids、evidence_ids）、
related_concepts（字符串数组）、limitations（字符串数组）、evidence_ids（证据卡 ID 数组）。
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
            return ExplanationResult.model_validate_json(_strip_code_fence(content))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"解释模型暂时不可用：{exc}") from exc

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
