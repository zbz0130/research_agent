import json
import logging
import re
import hashlib
import html
import math
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    LimitationDecision,
    ModelCallTrace,
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
    _DEFAULT_MAX_RETRIES = 2
    _DEFAULT_RETRY_BACKOFF_SECONDS = 0.6
    _DEFAULT_MAX_RETRY_WAIT_SECONDS = 3.0
    _RETRYABLE_STATUS_CODES = {
        httpx.codes.TOO_MANY_REQUESTS,
        httpx.codes.INTERNAL_SERVER_ERROR,
        httpx.codes.BAD_GATEWAY,
        httpx.codes.SERVICE_UNAVAILABLE,
        httpx.codes.GATEWAY_TIMEOUT,
    }

    def __init__(
        self,
        timeout: float = 30.0,
        minimum_interval_seconds: float = 3.0,
        *,
        endpoint: str | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS,
        max_retry_wait_seconds: float = _DEFAULT_MAX_RETRY_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_retries < 0 or retry_backoff_seconds < 0 or max_retry_wait_seconds < 0:
            raise ValueError("arXiv 重试参数不能小于 0")
        self.timeout = timeout
        # An explicit proxy endpoint is optional; retaining the class default
        # keeps existing callers and tests deterministic.
        self.endpoint = (endpoint or self.endpoint).rstrip("/")
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_retry_wait_seconds = max_retry_wait_seconds
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
        response = self._request_with_retry(params)

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

    def _request_with_retry(self, params: dict[str, object]) -> httpx.Response:
        """Retry only transient arXiv failures with a small, explicit budget."""

        total_wait_seconds = 0.0
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.get(
                    self.endpoint,
                    params=params,
                    headers={"User-Agent": "WishForge/0.2 (research concept explorer)"},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
            except httpx.TransportError as exc:
                response = None
                last_error = exc.__class__.__name__
            else:
                if response.status_code not in self._RETRYABLE_STATUS_CODES:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        raise ProviderUnavailable(
                            f"arXiv 请求失败（HTTP {response.status_code}）。请检查网络或稍后重试。",
                            provider=self.name,
                        ) from exc
                    return response
                last_error = f"HTTP {response.status_code}"

            if attempt >= self.max_retries:
                break
            delay = self.retry_backoff_seconds * (2**attempt)
            if total_wait_seconds + delay > self.max_retry_wait_seconds:
                break
            if delay:
                self._sleep(delay)
                total_wait_seconds += delay

        raise ProviderUnavailable(
            "arXiv 暂时无法连接（已重试 "
            f"{self.max_retries} 次，最后一次：{last_error or '连接失败'}）。"
            "这不表示没有相关论文；请稍后重试或切换到多源检索。",
            provider=self.name,
        )

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
        endpoint: str | None = None,
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
        self.endpoint = (endpoint or "https://api.semanticscholar.org/graph/v1/paper/search").rstrip("/")
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
                    self.endpoint,
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


def _clean_markup(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _normalized_doi(value: object) -> str | None:
    doi = str(value or "").strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[16:]
    if doi.lower().startswith("http://doi.org/"):
        doi = doi[15:]
    return doi.casefold() or None


def _year_from_date_parts(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return None
    year = parts[0][0]
    return year if isinstance(year, int) and 1000 <= year <= 9999 else None


class OpenAlexSearchProvider:
    """Read public OpenAlex work metadata without an API key."""

    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(self, *, endpoint: str | None = None, timeout: float = 20.0) -> None:
        self.endpoint = (endpoint or self.endpoint).rstrip("/")
        self.timeout = timeout

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        try:
            response = httpx.get(
                self.endpoint,
                params={"search": concept, "per-page": max(1, min(limit, 25))},
                headers={"User-Agent": "WishForge/0.2 (research concept explorer)"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise ProviderUnavailable(
                f"OpenAlex 暂时不可用：{exc.__class__.__name__}。",
                provider=self.name,
            ) from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ProviderUnavailable("OpenAlex 返回格式不符合预期。", provider=self.name)

        records: list[PaperRecord] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = _clean_markup(item.get("title"))
            if not title:
                continue
            record_id = str(item.get("id") or item.get("doi") or title)
            authors = [
                _clean_markup((authorship.get("author") or {}).get("display_name"))
                for authorship in item.get("authorships", [])
                if isinstance(authorship, dict) and isinstance(authorship.get("author"), dict)
            ]
            location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
            source = location.get("source") if isinstance(location.get("source"), dict) else {}
            abstract_index = item.get("abstract_inverted_index")
            inverted_terms: list[tuple[int, str]] = []
            if isinstance(abstract_index, dict):
                for word, positions in abstract_index.items():
                    if isinstance(positions, list):
                        inverted_terms.extend(
                            (position, str(word)) for position in positions if isinstance(position, int)
                        )
            abstract = " ".join(word for _, word in sorted(inverted_terms))
            doi = _normalized_doi(item.get("doi"))
            records.append(
                PaperRecord(
                    id=f"openalex:{record_id.rsplit('/', 1)[-1]}",
                    provider_id=record_id,
                    canonical_id=f"doi:{doi}" if doi else record_id,
                    title=title,
                    authors=[author for author in authors if author],
                    year=item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
                    venue=_clean_markup(source.get("display_name")) or None,
                    abstract=abstract,
                    url=location.get("landing_page_url") or item.get("doi"),
                    doi=doi,
                    citation_count=item.get("cited_by_count") if isinstance(item.get("cited_by_count"), int) else None,
                    source=self.name,
                    source_kind="academic",
                    access_type="open_access" if bool((item.get("open_access") or {}).get("is_oa")) else "metadata_only",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        return records[:limit]


class CrossrefSearchProvider:
    """Read public Crossref work metadata without treating metadata as full text."""

    name = "crossref"
    endpoint = "https://api.crossref.org/works"

    def __init__(self, *, endpoint: str | None = None, timeout: float = 20.0) -> None:
        self.endpoint = (endpoint or self.endpoint).rstrip("/")
        self.timeout = timeout

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        try:
            response = httpx.get(
                self.endpoint,
                params={"query": concept, "rows": max(1, min(limit, 25))},
                headers={"User-Agent": "WishForge/0.2 (research concept explorer)"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise ProviderUnavailable(
                f"Crossref 暂时不可用：{exc.__class__.__name__}。",
                provider=self.name,
            ) from exc
        message = payload.get("message") if isinstance(payload, dict) else None
        items = message.get("items") if isinstance(message, dict) else None
        if not isinstance(items, list):
            raise ProviderUnavailable("Crossref 返回格式不符合预期。", provider=self.name)

        records: list[PaperRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            titles = item.get("title")
            title = _clean_markup(titles[0]) if isinstance(titles, list) and titles else ""
            if not title:
                continue
            doi = _normalized_doi(item.get("DOI"))
            authors = []
            for author in item.get("author", []):
                if not isinstance(author, dict):
                    continue
                name = " ".join(
                    part for part in (_clean_markup(author.get("given")), _clean_markup(author.get("family"))) if part
                )
                if name:
                    authors.append(name)
            container_titles = item.get("container-title")
            venue = _clean_markup(container_titles[0]) if isinstance(container_titles, list) and container_titles else None
            year = next(
                (
                    candidate
                    for candidate in (
                        _year_from_date_parts(item.get("published-print")),
                        _year_from_date_parts(item.get("published-online")),
                        _year_from_date_parts(item.get("issued")),
                    )
                    if candidate is not None
                ),
                None,
            )
            record_id = doi or str(item.get("URL") or title)
            records.append(
                PaperRecord(
                    id=f"crossref:{record_id}",
                    provider_id=doi or record_id,
                    canonical_id=f"doi:{doi}" if doi else record_id,
                    title=title,
                    authors=authors,
                    year=year,
                    venue=venue,
                    abstract=_clean_markup(item.get("abstract")),
                    url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                    doi=doi,
                    citation_count=item.get("is-referenced-by-count") if isinstance(item.get("is-referenced-by-count"), int) else None,
                    source=self.name,
                    source_kind="academic",
                    access_type="metadata_only",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        return records[:limit]


class MultiSourceSearchProvider:
    """Merge public scholarly metadata while keeping each source transparent."""

    name = "multi_source"

    def __init__(self, providers: Sequence[SearchProvider] | None = None) -> None:
        self.providers = list(providers or [
            ArxivSearchProvider(),
            OpenAlexSearchProvider(),
            CrossrefSearchProvider(),
        ])
        # 编排层据此提示局部失败，而不是因某一数据源临时不可用而丢掉其他结果。
        self.last_warnings: list[str] = []

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        per_source_limit = max(2, min(6, math.ceil(max(1, limit) / max(1, len(self.providers))) + 1))
        merged: list[PaperRecord] = []
        failures: list[str] = []
        self.last_warnings = []
        for provider in self.providers:
            try:
                merged.extend(provider.search(concept, per_source_limit))
            except ProviderUnavailable as exc:
                failures.append(f"{provider.name}：{exc}")
        if not merged and failures:
            raise ProviderUnavailable(
                "多源论文检索均未成功：" + "；".join(failures),
                provider=self.name,
            )
        if failures:
            unavailable_sources = "、".join(
                failure.split("：", 1)[0] for failure in failures
            )
            self.last_warnings.append(
                f"{unavailable_sources} 暂时不可用；已保留其他论文来源的检索结果，可稍后重试。"
            )

        deduplicated: list[PaperRecord] = []
        seen_dois: set[str] = set()
        seen_titles: set[str] = set()
        for record in merged:
            doi = _normalized_doi(record.doi)
            title_key = re.sub(r"\W+", "", record.title.casefold())
            if (doi and doi in seen_dois) or (title_key and title_key in seen_titles):
                continue
            if doi:
                seen_dois.add(doi)
            if title_key:
                seen_titles.add(title_key)
            deduplicated.append(record)
        return deduplicated[:limit]


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


def _format_paper_payload(
    papers: Sequence[PaperRecord],
    *,
    abstract_limit: int,
) -> str:
    return "\n\n".join(
        f"- {paper.title} ({paper.year or 'n.d.'}) [{paper.id}]\n摘要：{paper.abstract[:abstract_limit]}"
        for paper in papers[:10]
    )


def _select_balanced_evidence(
    evidence: Sequence[EvidenceCard],
    *,
    limit: int,
    preferred_types: set[str],
    preferred_only: bool = False,
) -> list[EvidenceCard]:
    """Round-robin papers so early papers cannot consume the whole prompt budget."""

    groups: dict[str, list[EvidenceCard]] = {}
    paper_order: list[str] = []
    for card in evidence:
        card_types = set(card.evidence_types or [card.evidence_type])
        if preferred_only and not card_types & preferred_types:
            continue
        if card.paper_id not in groups:
            paper_order.append(card.paper_id)
            groups[card.paper_id] = []
        groups[card.paper_id].append(card)
    for cards in groups.values():
        cards.sort(
            key=lambda card: (
                not bool(set(card.evidence_types or [card.evidence_type]) & preferred_types),
                card.id,
            )
        )

    selected: list[EvidenceCard] = []
    while len(selected) < limit:
        added = False
        for paper_id in paper_order:
            cards = groups[paper_id]
            if not cards:
                continue
            selected.append(cards.pop(0))
            added = True
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected


def _format_evidence_payload(evidence: Sequence[EvidenceCard]) -> str:
    return "\n\n".join(
        (
            f"[{item.id}] paper_id={item.paper_id}\n"
            f"类型：{'+'.join(item.evidence_types or [item.evidence_type])}\n"
            f"卡片说明：{item.claim}\n原文：{item.excerpt[:1600]}"
        )
        for item in evidence
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

    def plan_concept_graph(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        language: str,
    ) -> dict[str, object]:
        """Propose a bounded evidence-linked graph plan for later validation.

        The service treats this output as a proposal, never as authoritative
        graph data: unknown paper/evidence IDs and unsupported relations are
        discarded by the graph builder before the user sees them.
        """

        paper_payload = _format_paper_payload(list(papers[:8]), abstract_limit=1400)
        evidence_payload = _format_evidence_payload(list(evidence[:32]))
        prompt = f"""
你是 WishForge 的 ConceptGraphPlanner、NodeExplanationAgent 和 RelationAgent。
围绕“{concept}”生成一张有界研究概念网络；语言：{language}。
只依据下方论文标题、摘要与证据卡。不得声称读过全文，不得创造论文或证据 ID。

只返回 JSON 对象：
{{"nodes":[{{"id":"stable-short-id","label":"节点名","role":"concept|method|problem","explanation":"一条易懂解释","paper_ids":["给定 paper_id"],"evidence_ids":["给定 evidence_id"],"confidence":"low|medium|high"}}],"edges":[{{"source":"root 或节点 id","target":"节点 id","relation":"is_a|uses|improves|supports|related_to|has_problem","source_kind":"semantic_similarity|keyword|model_inference","confidence":"low|medium|high","explanation":"为什么相连"}}]}}

约束：
1. 最多 10 个非论文节点；不要返回根节点或论文节点，系统会从真实输入补上；
2. method/problem 节点至少关联一篇给定论文或证据；无法确认则不要生成；
3. 边只能连接 root 或返回的节点；不要生成自环；
4. 模型判断的边必须标为 model_inference，不得伪装成 citation；
5. 解释必须简洁、易懂，并说明证据边界。

论文：
{paper_payload or '无'}

证据卡：
{evidence_payload or '无'}
""".strip()
        return self._request_explanation_part(
            prompt,
            system="你负责生成保守、可验证的科研概念图提案，结构正确比节点数量更重要。",
            temperature=0.1,
            part_label="概念图规划",
        )

    def plan_research_directions(
        self,
        topic: str,
        papers: Sequence[PaperRecord],
        prior_queries: Sequence[str],
        *,
        max_directions: int,
    ) -> list[dict[str, object]]:
        """Propose Overview taxonomy directions from the retained corpus."""

        paper_payload = _format_paper_payload(list(papers[:12]), abstract_limit=1200)
        prompt = f"""
你是 WishForge 的 TopicTaxonomyPlannerAgent。研究主题：“{topic}”。
本次已有检索词：{', '.join(prior_queries[:8]) or '无'}。
只依据下方论文标题和摘要提出最多 {max_directions} 个一级研究方向。先用第一性原理拆解：
先确定该主题中研究者真正要优化的目标、不可回避的约束/失败模式，以及现有方案为什么无法满足；
再按“要解决的核心问题”而非按流行模型名或应用名划分方向。每个方向必须明确输出 problem，
并在 first_principles 中依次说明优化目标、不可回避的约束、主要失败模式与判断是否解决的标准；
definition 再说明该问题下常见的方法路线。

只返回 JSON：
{{"directions":[{{"key":"short_key","label":"问题方向名","problem":"要解决的核心问题","first_principles":"目标；约束；失败模式；成功标准","definition":"常见方法路线","boundary":"哪些论文不属于这里","query_terms":["英文 arXiv 检索短语"],"match_terms":["用于边界核对的中英文关键词"],"seed_paper_ids":["给定 paper_id"],"subdirections":[{{"key":"sub_key","label":"方法路线名","match_terms":["关键词"]}}]}}]}}

要求：
1. 方向彼此尽量区分，不能只是同义改写；problem 必须是可检验的问题，而不是领域名；
2. seed_paper_ids 只能使用下方论文 ID；
3. query_terms 每个方向 1 至 3 个，必须是简短英文检索词；
4. match_terms 至少 2 个，用于服务端边界过滤；
5. 最多 3 个细分方向；细分项优先按“解决该问题的方法路线”命名，没有证据支持时可以不填；
6. first_principles 不得写口号，必须覆盖目标、约束、失败模式和成功标准；
7. 不得声称这是一份完整学科分类。

论文：
{paper_payload or '无'}
""".strip()
        payload = self._request_explanation_part(
            prompt,
            system="你负责提出有边界、可检索、可审计的研究方向分类，不负责证明完整性。",
            temperature=0.1,
            part_label="研究方向规划",
        )
        directions = payload.get("directions")
        return directions[:max_directions] if isinstance(directions, list) else []

    def synthesize_research_overview(
        self,
        topic: str,
        directions: Sequence[dict[str, object]],
        paper_summaries: Sequence[dict[str, object]],
    ) -> dict[str, object]:
        """Write evidence-bounded Overview title/root/direction summaries."""

        prompt = f"""
你是 WishForge 的 OverviewSynthesisAgent。主题：“{topic}”。
根据下方已经审计过的方向和论文阅读摘要，生成展示文案；不能增加节点、论文或证据。
只返回 JSON：
{{"title":"研究方向图标题","root_explanation":"根节点简洁说明","direction_explanations":{{"direction_key":"简洁说明"}},"warnings":["范围边界"]}}
方向：{json.dumps(list(directions)[:8], ensure_ascii=False)}
论文阅读摘要：{json.dumps(list(paper_summaries)[:40], ensure_ascii=False)}
""".strip()
        return self._request_explanation_part(
            prompt,
            system="你负责综合已经验证的结构，只写展示文案，不得扩大事实范围。",
            temperature=0.1,
            part_label="研究方向综合",
        )

    def review_research_direction(
        self,
        topic: str,
        direction: dict[str, object],
        papers: Sequence[PaperRecord],
    ) -> dict[str, object]:
        """Act as one bounded branch reviewer after retrieval and deduplication."""

        paper_payload = _format_paper_payload(list(papers[:8]), abstract_limit=1800)
        prompt = f"""
你是 WishForge 的 DirectionReviewAgent，只审查一个问题分支。
总主题：{topic}
问题分支：{json.dumps(direction, ensure_ascii=False)}

基于下面已经通过服务端检索边界检查的论文，判断该问题是否形成至少两条有证据区分的方法路线。
只返回 JSON：
{{"decision":"split 或 keep","reason":"判断依据","method_routes":[{{"key":"short_key","label":"方法路线名","paper_ids":["给定 paper_id"]}}]}}

要求：
1. 只能使用下方给定的 paper_id，不得新增论文；
2. 每篇论文最多属于一条路线；不得按年份、作者或应用领域机械分组；
3. split 需要至少 3 篇论文且形成至少 2 条非空、方法机制不同的路线，否则必须 keep；
4. 最多 3 条路线；名称必须描述“如何解决问题”，不能只是“其他论文”；
5. 只依据标题和摘要，不得声称读过未提供的全文。

论文：
{paper_payload or '无'}
""".strip()
        return self._request_explanation_part(
            prompt,
            system="你是单一研究分支的审查 Agent；只做有边界的分组判断，不扩大论文集合。",
            temperature=0,
            part_label="研究方向分支审查",
        )

    def summarize_research_papers(
        self,
        topic: str,
        direction: dict[str, object],
        papers: Sequence[dict[str, object]],
    ) -> dict[str, object]:
        """Summarize a bounded branch from abstracts and extracted evidence only."""

        prompt = f"""
你是 WishForge 的 PaperReadingAgent。总主题：{topic}
当前核心问题与方法分支：{json.dumps(direction, ensure_ascii=False)}

根据下方每篇论文的摘要、规则摘句和开放 arXiv PDF 章节证据，为每篇论文生成简洁中文解析。
只返回 JSON：
{{"papers":[{{"paper_id":"给定 ID","problem":"解决什么问题","method":"提出什么方法","how_it_works":"大概怎么做","limitations":"已提供文本能确认的局限；没有则为空字符串"}}]}}

要求：
1. paper_id 只能来自输入；每篇输入论文最多返回一次；
2. problem、method、how_it_works 必须分别回答三个问题，不能互相复制；
3. 只能使用输入中的摘要和 evidence_excerpts，不得补充记忆中的论文事实；
4. 没有正文证据时明确保持摘要级措辞，不得声称读过全文；
5. 不评价论文好坏，不编造实验数字、引用数、章节或局限。

输入论文：
{json.dumps(list(papers)[:8], ensure_ascii=False)}
""".strip()
        return self._request_explanation_part(
            prompt,
            system="你是证据约束的论文阅读 Agent；只压缩给定文本，不新增事实或来源。",
            temperature=0,
            part_label="论文证据摘要",
        )

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
        if not papers:
            return self._explain_quick(concept, audience, language)
        return self._explain_literature(concept, papers, evidence, audience, language)

    def _explain_quick(
        self,
        concept: str,
        audience: str,
        language: str,
    ) -> ExplanationResult:
        prompt = f"""
你是 WishForge 的科研概念解释器。请解释“{concept}”。
目标读者：{audience}；语言：{language}。
这是快速解释模式，没有执行论文检索。请先给直觉、再给技术说明，避免堆砌术语。
不要伪造论文、证据 ID 或具体引用。

只返回 JSON 对象，字段为：
- one_sentence：一句话解释；
- intuitive：直觉类比；
- technical：技术说明；
- evolution：不带论文引用的简短演进字符串数组；
- claims：无来源的原子定义或机制主张，paper_ids、evidence_ids、evidence_quotes 必须为空，scope 写“通用知识，待检索核验”；
- scope_warnings：必须说明本次没有检索论文；
- related_concepts：标准相关术语数组。

evolution_items、research_limitations、research_gap_candidates、reproducibility_checks、
limitations、evidence_ids 必须返回空数组。不要返回 model_output_warnings。
""".strip()
        started_at = time.perf_counter()
        payload = self._request_explanation_part(
            prompt,
            system="你是一名善于建立直觉、同时明确知识边界的科研教师。",
            temperature=0.2,
            part_label="快速解释",
        )
        try:
            explanation = _parse_explanation_result(json.dumps(payload, ensure_ascii=False))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable("快速解释模型返回内容缺少必要字段或无法解析。") from exc
        return explanation.model_copy(
            update={
                "model_call_traces": [
                    ModelCallTrace(
                        part="快速解释",
                        status="succeeded",
                        duration_ms=round((time.perf_counter() - started_at) * 1000),
                        returned_fields=sorted(payload),
                        item_counts={
                            key: len(value)
                            for key, value in payload.items()
                            if isinstance(value, list)
                        },
                    )
                ]
            }
        )

    def _explain_literature(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        selected_papers = list(papers[:10])
        paper_payload = _format_paper_payload(selected_papers, abstract_limit=2200)
        limitation_evidence = _select_balanced_evidence(
            evidence,
            limit=30,
            preferred_types={"limitation", "future_work"},
            preferred_only=True,
        )

        core_prompt = f"""
你负责 WishForge 文献解释的“核心说明”部分。解释“{concept}”。
目标读者：{audience}；语言：{language}。
仅依据下方论文摘要，不得声称阅读过全文。先建立直觉，再解释共同技术机制。

只返回 JSON 对象，且只包含：
- one_sentence：一句话、易懂、不过度概括；
- intuitive：直觉类比；
- technical：综合多篇摘要后的技术说明；
- related_concepts：与主概念紧密相关的标准术语数组；
- scope_warnings：调研范围提醒数组，例如仅阅读摘要、检索数量有限。

不要生成时间线、原子主张、研究局限、研究空白或复现检查。

论文及摘要：
{paper_payload}
""".strip()

        limitations_prompt = f"""
你负责 WishForge 文献解释的“研究局限审核”部分。研究概念：“{concept}”；语言：{language}。
这不是通用解释任务。请逐张审核限制候选证据卡，不得跳过任何候选。

只返回 JSON 对象，且必须包含：limitation_decisions、research_limitations、research_gap_candidates、reproducibility_checks。

limitation_decisions 必须对下方每张候选卡各返回一项，包含：
- evidence_id：候选卡 ID；
- decision：只能是 limitation、research_gap、reject；
- reason：说明为什么接受为局限、接受为空白，或拒绝；
- limitation_kind：decision=limitation 时填写合法局限类型，否则为 null。

判定口径：
1. 当前论文指出“既有方法在某条件下失败、退化、产生额外代价或无法适用”，属于 method_limitation/failure_mode/applicability_boundary；
2. 理论上明确存在不可能性或适用边界，属于 theoretical_limit；
3. 明确写出尚未研究、缺乏系统指导或仍未解决，但没有具体方法负面后果，属于 research_gap；
4. 仅仅介绍方法、说存在 trade-off 却没有负面后果，或描述 KV cache 本身的常规内存代价，必须 reject；
5. 局限可以是论文作者对既有研究路线的明确批评，不要求必须是作者自己方法的缺陷。

research_limitations 要求：
1. 每项必须包含 text、limitation_kind、target、condition、consequence、paper_ids、evidence_ids、explicitness；
2. limitation_kind 只能是 method_limitation、failure_mode、tradeoff、applicability_boundary、evaluation_limitation、theoretical_limit；
3. paper_ids 和 evidence_ids 必须来自下方资料，且证据卡必须属于同一篇论文；
4. 只有摘要原句明确描述负面后果时才能标记 explicit；只有“trade-off/challenge”而没有负面后果时不要生成；
5. “仅阅读摘要、检索数量有限、需要人工核验”不是研究局限，不得写入；
6. 只为 decision=limitation 的候选生成，找不到合格局限时返回空数组，不得猜测。

合法示例：
{{"research_limitations":[{{"text":"短上下文校准会造成长上下文通道分布估计不足。","limitation_kind":"applicability_boundary","target":"KV cache 量化校准","condition":"使用短上下文校准数据时","consequence":"长上下文中的低频通道分布未被覆盖并造成性能损失","paper_ids":["paper-id"],"evidence_ids":["evidence-id"],"explicitness":"explicit"}}],"research_gap_candidates":[],"reproducibility_checks":[]}}

research_gap_candidates 只为 decision=research_gap 的候选生成，只能写当前检索范围内需要扩大检索验证的候选，不得声称整个领域不存在相关工作。
reproducibility_checks 中的 check_type 只能是以下五个英文值之一：code、data、environment、license、benchmark；
“not verified”“unknown”“unverified”不是 check_type，arXiv ID 只能放入 paper_ids；无法判断时不生成。

论文及摘要：
{_format_paper_payload(selected_papers, abstract_limit=1600)}

限制候选证据卡（已优先完整提供）：
{_format_evidence_payload(limitation_evidence) or '没有通过初步类型筛选的限制候选证据卡'}
""".strip()

        requests: dict[str, tuple[str, str, float, str]] = {
            "core": (
                core_prompt,
                "你负责清晰、准确的科研核心解释，不处理其他结构化任务。",
                0.2,
                "核心解释",
            ),
            "limitations": (
                limitations_prompt,
                "你负责从摘要原句中保守审核研究局限，宁缺毋滥，但不得忽略明确负面后果。",
                0.0,
                "研究局限审核",
            ),
        }

        paper_batches = [
            selected_papers[index : index + 2]
            for index in range(0, len(selected_papers), 2)
        ]
        for batch_index, batch in enumerate(paper_batches, 1):
            batch_paper_ids = {paper.id for paper in batch}
            batch_evidence = _select_balanced_evidence(
                [card for card in evidence if card.paper_id in batch_paper_ids],
                limit=16,
                preferred_types={"definition", "mechanism", "result"},
            )
            batch_prompt = f"""
你负责 WishForge 文献解释的“时间线与原子主张（批次 {batch_index}/{len(paper_batches)}）”部分。
研究概念：“{concept}”；语言：{language}。本批只有 {len(batch)} 篇论文。
仅依据下方论文摘要和证据卡，不得声称阅读过全文，也不得引用其他论文。

只返回 JSON 对象，且只包含 evolution_items、claims。
要求：
1. 每篇论文恰好生成一个 evolution_item，包含 year、title、summary、paper_ids、evidence_ids；summary 要说明它解决的痛点、主要方法和相对前序路线的变化，不能只是复述标题；
2. 对每篇摘要至少生成 2 条、至多 3 条原子 claims；优先保留一个核心机制和一个最重要结果。如果摘要确实只有一个可核验事实，允许只生成 1 条，但不得完全遗漏该论文；
3. claims 每项必须且只能使用这些字段：claim_type、text、paper_ids、evidence_ids、evidence_quotes、scope。不得把 text 写成 claim/content，不得把数组字段写成单个字符串；
4. claim_type 只能是 definition、mechanism、result；时间演变只写入 evolution_items，不要生成 evolution 类型主张。每条只能表达一个可独立核验事实；
5. 每条论文特定主张只能使用一个 paper_id；mechanism 每条只描述一个主要操作，不同操作必须拆开；
6. 数字、压缩率、速度和准确率必须各自写成独立 result，不能混入 mechanism；数值和单位必须保持摘要原句的表达，禁止自行换算倒数、百分比或新范围；
7. 每条主张必须提供 evidence_quotes，逐字复制 1 至 2 条摘要完整原句，禁止翻译、改写或拼接；
8. paper_ids 和 evidence_ids 只能使用下方出现的 ID；
9. “首次、首个、最优、保证、无损”等强表述只有在逐字证据中明确出现对应含义时才能使用；只有“存在固有局限/存在挑战”但没有具体对象和后果的模糊句子不要生成主张。

claims 合法示例：
{{"claim_type":"mechanism","text":"SQuat 约束量化误差与查询子空间正交。","paper_ids":["paper-id"],"evidence_ids":["evidence-id"],"evidence_quotes":["逐字复制的英文摘要完整原句。"],"scope":"论文摘要中的机制描述"}}

论文及摘要：
{_format_paper_payload(batch, abstract_limit=2400)}

证据卡：
{_format_evidence_payload(batch_evidence)}
""".strip()
            name = f"claims_{batch_index}"
            requests[name] = (
                batch_prompt,
                "你负责逐篇生成可核验的时间线条目和原子主张，不处理研究局限。",
                0.1,
                f"时间线与原子主张（批次 {batch_index}/{len(paper_batches)}）",
            )

        parts: dict[str, dict[str, object]] = {}
        failures: dict[str, ProviderUnavailable] = {}
        traces: dict[str, ModelCallTrace] = {}
        with ThreadPoolExecutor(
            max_workers=min(8, len(requests)),
            thread_name_prefix="wishforge-explanation",
        ) as executor:
            future_names: dict[object, tuple[str, float]] = {}
            for name, (prompt, system, temperature, part_label) in requests.items():
                started_at = time.perf_counter()
                future = executor.submit(
                    self._request_explanation_part,
                    prompt,
                    system=system,
                    temperature=temperature,
                    part_label=part_label,
                )
                future_names[future] = (name, started_at)
            for future in as_completed(future_names):
                name, started_at = future_names[future]
                duration_ms = round((time.perf_counter() - started_at) * 1000)
                try:
                    part = future.result()
                    parts[name] = part
                    traces[name] = ModelCallTrace(
                        part=requests[name][3],
                        status="succeeded",
                        duration_ms=duration_ms,
                        returned_fields=sorted(part),
                        item_counts={
                            key: len(value)
                            for key, value in part.items()
                            if isinstance(value, list)
                        },
                    )
                except ProviderUnavailable as exc:
                    failures[name] = exc
                    traces[name] = ModelCallTrace(
                        part=requests[name][3],
                        status="failed",
                        duration_ms=duration_ms,
                        message=str(exc),
                    )

        if "core" in failures or "core" not in parts:
            raise failures.get("core") or ProviderUnavailable("核心解释调用没有返回结果。")

        warnings: list[str] = []
        expected_fields: dict[str, tuple[str, ...]] = {
            "core": ("one_sentence", "intuitive", "technical", "related_concepts", "scope_warnings"),
            "limitations": (
                "limitation_decisions",
                "research_limitations",
                "research_gap_candidates",
                "reproducibility_checks",
            ),
            **{
                f"claims_{index}": ("evolution_items", "claims")
                for index in range(1, len(paper_batches) + 1)
            },
        }
        for name, fields in expected_fields.items():
            part = parts.get(name, {})
            if name in failures:
                warnings.append(f"{requests[name][3]}调用失败，该部分已保留为空；其他解释不受影响。")
            unknown_fields = set(part) - set(fields)
            if unknown_fields:
                warnings.append(
                    f"{requests[name][3]}调用返回了 {len(unknown_fields)} 个未约定字段，系统已忽略。"
                )
            if name in parts:
                for field in fields:
                    if field not in part:
                        warnings.append(f"{requests[name][3]}调用未返回 {field} 字段，系统已按空值处理。")

        core_part = parts["core"]
        merged: dict[str, object] = {
            field: core_part.get(field)
            for field in expected_fields["core"]
        }
        evolution_items: list[object] = []
        claims: list[object] = []
        for index in range(1, len(paper_batches) + 1):
            part = parts.get(f"claims_{index}", {})
            if isinstance(part.get("evolution_items"), list):
                evolution_items.extend(part["evolution_items"])
            if isinstance(part.get("claims"), list):
                claims.extend(part["claims"])
        merged["evolution_items"] = evolution_items
        merged["claims"] = claims
        merged["evolution"] = [
            f"{item.get('year') or 'n.d.'}：{item.get('title', '')} — {item.get('summary', '')}"
            for item in evolution_items
            if isinstance(item, dict)
        ]
        linked_ids: list[str] = []
        for item in [*evolution_items, *claims]:
            if isinstance(item, dict) and isinstance(item.get("evidence_ids"), list):
                linked_ids.extend(
                    value for value in item["evidence_ids"] if isinstance(value, str)
                )
        merged["evidence_ids"] = list(dict.fromkeys(linked_ids))[:40]
        limitation_part = parts.get("limitations", {})
        for field in expected_fields["limitations"]:
            merged[field] = limitation_part.get(field, [])

        if "limitations" in parts and not parts["limitations"].get("research_limitations"):
            warnings.append("研究局限审核调用未提取到满足条件的结构化局限。")
        decision_ids = {
            item.get("evidence_id")
            for item in limitation_part.get("limitation_decisions", [])
            if isinstance(item, dict)
        } if isinstance(limitation_part.get("limitation_decisions"), list) else set()
        missing_decisions = [card.id for card in limitation_evidence if card.id not in decision_ids]
        if missing_decisions:
            warnings.append(
                f"研究局限审核遗漏了 {len(missing_decisions)} 张候选证据卡的接受/拒绝裁决。"
            )
        merged["limitations"] = []
        try:
            explanation = _parse_explanation_result(json.dumps(merged, ensure_ascii=False))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable("拆分后的解释模型结果缺少必要字段或无法合并。") from exc

        if not explanation.claims:
            fallback_claim = AtomicClaimDraft(
                claim_type="definition",
                text=explanation.one_sentence,
                paper_ids=[],
                evidence_ids=[],
                evidence_quotes=[],
                scope="核心解释生成的通用定义；原子主张调用不可用或未返回主张",
            )
            explanation = explanation.model_copy(update={"claims": [fallback_claim]})
        covered_paper_ids = {
            paper_id
            for claim in explanation.claims
            for paper_id in claim.paper_ids
        }
        missing_claim_papers = [
            paper.title for paper in selected_papers if paper.id not in covered_paper_ids
        ]
        if missing_claim_papers:
            warnings.append(
                f"原子主张仍未覆盖 {len(missing_claim_papers)} 篇入选论文："
                + "；".join(missing_claim_papers[:4])
            )
        all_warnings = list(dict.fromkeys([*explanation.model_output_warnings, *warnings]))[:20]
        return explanation.model_copy(
            update={
                "limitations": [item.text for item in explanation.research_limitations],
                "model_output_warnings": all_warnings,
                "model_call_traces": [traces[name] for name in requests if name in traces],
            }
        )

    def _request_explanation_part(
        self,
        prompt: str,
        *,
        system: str,
        temperature: float,
        part_label: str,
    ) -> dict[str, object]:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("content 不是字符串")
            payload = json.loads(_strip_code_fence(content))
            if not isinstance(payload, dict):
                raise ValueError("返回内容不是 JSON 对象")
            return payload
        except httpx.HTTPError as exc:
            logger.warning("%s model request failed", part_label, exc_info=True)
            raise ProviderUnavailable(f"{part_label}模型请求失败。") from exc
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("%s model response could not be parsed", part_label, exc_info=True)
            raise ProviderUnavailable(f"{part_label}模型返回内容无法解析。") from exc

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
    "limitation_decisions": (LimitationDecision, 30),
}
_REPRODUCIBILITY_CHECK_TYPES = {"code", "data", "environment", "license", "benchmark"}
_EXPLANATION_FIELD_LABELS = {
    "evolution_items": "演变条目",
    "claims": "原子主张",
    "research_limitations": "研究局限",
    "research_gap_candidates": "研究空白候选",
    "reproducibility_checks": "复现检查",
    "limitation_decisions": "局限候选裁决",
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
        if field == "claims":
            candidate, changed = _normalize_atomic_claim_item(raw_item, candidate)
            normalized += int(changed)
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


def _normalize_atomic_claim_item(
    raw_item: dict[str, object],
    candidate: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """Repair common, unambiguous JSON-shape drift without inventing content."""

    repaired = dict(candidate)
    changed = False
    if "text" not in repaired:
        for alias in ("claim", "content", "statement"):
            value = raw_item.get(alias)
            if isinstance(value, str) and value.strip():
                repaired["text"] = value
                changed = True
                break
    if "claim_type" not in repaired:
        value = raw_item.get("type")
        if isinstance(value, str) and value.strip():
            repaired["claim_type"] = value
            changed = True

    singular_aliases = {
        "paper_ids": "paper_id",
        "evidence_ids": "evidence_id",
        "evidence_quotes": "evidence_quote",
    }
    for plural, singular in singular_aliases.items():
        value = repaired.get(plural)
        if isinstance(value, str):
            repaired[plural] = [value]
            changed = True
            continue
        if plural not in repaired:
            alias_value = raw_item.get(singular)
            if isinstance(alias_value, str) and alias_value.strip():
                repaired[plural] = [alias_value]
                changed = True
    return repaired, changed


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
