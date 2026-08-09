import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services import research_providers
from app.services.research_providers import ProviderRateLimited, SemanticScholarProvider


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers,
        json=payload if payload is not None else {},
        request=httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search"),
    )


def _successful_search_payload() -> dict:
    return {
        "data": [
            {
                "paperId": "paper-1",
                "title": "A rate-limit retry test paper",
                "abstract": "An abstract used only by the unit test.",
                "authors": [{"name": "Test Author"}],
                "year": 2025,
                "venue": "TestConf",
                "url": "https://example.com/paper-1",
                "openAccessPdf": {"url": "https://example.com/paper-1.pdf"},
                "citationCount": 1,
                "externalIds": {"DOI": "10.1000/test"},
            }
        ]
    }


def test_semantic_scholar_retries_429_after_retry_after_before_success(monkeypatch) -> None:
    responses = iter(
        [
            _response(429, headers={"Retry-After": "1.25"}),
            _response(200, payload=_successful_search_payload()),
        ]
    )
    calls: list[dict[str, object]] = []
    waits: list[float] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return next(responses)

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)
    provider = SemanticScholarProvider(
        api_key="paper-key",
        max_retries=2,
        retry_backoff_seconds=0.5,
        max_retry_wait_seconds=3.0,
        sleep=waits.append,
    )

    papers = provider.search("agent", 6)

    assert len(calls) == 2
    assert waits == [1.25]
    assert calls[0]["headers"] == {"User-Agent": "WishForge/0.1", "x-api-key": "paper-key"}
    assert papers[0].title == "A rate-limit retry test paper"


def test_semantic_scholar_uses_bounded_exponential_backoff_without_retry_after(monkeypatch) -> None:
    responses = iter([_response(429), _response(429), _response(429)])
    waits: list[float] = []
    call_count = 0

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return next(responses)

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)
    provider = SemanticScholarProvider(
        max_retries=2,
        retry_backoff_seconds=0.25,
        max_retry_wait_seconds=2.0,
        sleep=waits.append,
    )

    with pytest.raises(ProviderRateLimited) as error:
        provider.search("agent", 6)

    assert call_count == 3  # one initial request and two bounded retries
    assert waits == [0.25, 0.5]
    assert error.value.retries_attempted == 2
    assert error.value.public_detail()["code"] == "provider_rate_limited"


def test_semantic_scholar_does_not_retry_before_a_retry_after_beyond_wait_cap(monkeypatch) -> None:
    calls = 0
    waits: list[float] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(429, headers={"Retry-After": "120"})

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)
    provider = SemanticScholarProvider(
        max_retries=2,
        retry_backoff_seconds=0.5,
        max_retry_wait_seconds=3.0,
        sleep=waits.append,
    )

    with pytest.raises(ProviderRateLimited) as error:
        provider.search("agent", 6)

    assert calls == 1
    assert waits == []
    assert error.value.retry_after_seconds == 120.0
    assert error.value.stopped_by_wait_cap is True
    assert "HTTP 429" in str(error.value)
    assert "匿名/未配置论文检索 API Key" in str(error.value)
    assert "WISHFORGE_PAPER_API_KEY" in str(error.value)
    assert "演示模式" in str(error.value)


def test_analysis_rate_limit_falls_back_to_transparent_demo_without_empty_result_warning(monkeypatch) -> None:
    def raise_rate_limit(self: SemanticScholarProvider, concept: str, limit: int) -> list:
        raise ProviderRateLimited(
            api_key_configured=False,
            retries_attempted=2,
            waited_seconds=1.5,
            max_wait_seconds=3.0,
            retry_after_seconds=1.0,
        )

    monkeypatch.setattr(SemanticScholarProvider, "search", raise_rate_limit)
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="semantic_scholar",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "agent", "level": "literature", "max_papers": 3},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(50):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break

        assert job["status"] == "completed"
        assert job["result"]["papers"]
        assert all(paper["source_kind"] == "demo" for paper in job["result"]["papers"])
        warnings = job["result"]["warnings"]
        assert any("HTTP 429" in warning for warning in warnings)
        assert any("已切换到演示资料" in warning for warning in warnings)
        assert not any("检索没有返回论文" in warning for warning in warnings)
    finally:
        app.dependency_overrides.clear()


def test_research_analysis_never_labels_an_interrupted_empty_search_as_no_results(monkeypatch) -> None:
    calls = 0

    def empty_once_then_raise(
        self: SemanticScholarProvider, concept: str, limit: int
    ) -> list:
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        raise ProviderRateLimited(
            api_key_configured=False,
            retries_attempted=2,
            waited_seconds=1.5,
            max_wait_seconds=3.0,
            retry_after_seconds=1.0,
        )

    monkeypatch.setattr(SemanticScholarProvider, "search", empty_once_then_raise)
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="semantic_scholar",
        explanation_provider="rule_based",
        demo_mode=False,
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "agent", "level": "research", "max_papers": 3},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(50):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break

        assert job["status"] == "completed"
        assert job["result"]["papers"] == []
        warnings = job["result"]["warnings"]
        assert any("HTTP 429" in warning for warning in warnings)
        assert any("不能据此判断没有相关论文" in warning for warning in warnings)
        assert not any("检索没有返回论文" in warning for warning in warnings)
    finally:
        app.dependency_overrides.clear()
