import httpx
import json
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import EvidenceCard, PaperRecord
from app.services import research_providers
from app.services.research_providers import (
    ArxivSearchProvider,
    OpenAICompatibleExplanationProvider,
    ProviderRateLimited,
    ProviderUnavailable,
    SemanticScholarProvider,
)


ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <updated>2023-08-02T00:41:18Z</updated>
    <published>2017-06-12T17:57:34Z</published>
    <title> Attention Is All You Need </title>
    <summary>
      The dominant sequence transduction models are based on recurrent networks.
      We propose a new architecture based solely on attention mechanisms.
    </summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html" />
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf" />
    <arxiv:primary_category term="cs.CL" />
    <arxiv:doi>10.5555/3295222.3295349</arxiv:doi>
  </entry>
</feed>
"""


def test_arxiv_search_parses_atom_and_records_exact_scope(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(
            200,
            content=ARXIV_FEED,
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)

    papers = ArxivSearchProvider().search("attention mechanism", 6)

    assert len(calls) == 1
    assert calls[0]["url"] == "https://export.arxiv.org/api/query"
    assert calls[0]["params"] == {
        "search_query": 'all:"attention mechanism"',
        "start": 0,
        "max_results": 6,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    assert calls[0]["follow_redirects"] is True
    assert len(papers) == 1
    paper = papers[0]
    assert paper.id == "arxiv:1706.03762v7"
    assert paper.canonical_id == "arxiv:1706.03762"
    assert paper.arxiv_id == "1706.03762"
    assert paper.version == "v7"
    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper.year == 2017
    assert paper.venue == "arXiv:cs.CL"
    assert paper.doi == "10.5555/3295222.3295349"
    assert paper.url == "https://arxiv.org/abs/1706.03762v7"
    assert paper.access_type == "open_access"
    assert "solely on attention mechanisms" in paper.abstract


def test_arxiv_search_rejects_malformed_atom(monkeypatch) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not xml",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)

    with pytest.raises(ProviderUnavailable, match="Atom"):
        ArxivSearchProvider().search("attention", 3)


def _model_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        request=httpx.Request("POST", "https://model.example/v1/chat/completions"),
    )


def test_compatible_model_plans_an_english_arxiv_query(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured.update({"url": url, **kwargs})
        return _model_response({"query": "attention mechanism"})

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )

    query = provider.plan_search_query("注意力机制", "zh-CN")

    assert query == "attention mechanism"
    assert captured["url"] == "https://model.example/v1/chat/completions"
    request_json = captured["json"]
    assert request_json["model"] == "test-model"
    assert "注意力机制" in request_json["messages"][1]["content"]


def test_compatible_model_distinguishes_quick_and_abstract_modes(monkeypatch) -> None:
    prompts: list[str] = []
    responses = iter(
        [
            {
                "one_sentence": "注意力机制让模型按相关性聚合信息。",
                "intuitive": "像阅读时把注意力放在关键句上。",
                "technical": "通过查询、键和值计算加权表示。",
                "evolution": ["从对齐机制发展到自注意力"],
                "related_concepts": ["Self-Attention", "Transformer"],
                "limitations": ["本次没有检索论文，需要后续文献核验。"],
                "evidence_ids": [],
            },
            {
                "one_sentence": "注意力机制根据相关性汇聚上下文。",
                "intuitive": "像带着问题查阅资料。",
                "technical": "摘要资料显示自注意力支持并行序列建模。",
                "evolution": ["2017：Transformer 将自注意力作为核心结构"],
                "related_concepts": ["Self-Attention", "Transformer"],
                "limitations": ["当前仅核对摘要。"],
                "evidence_ids": ["evidence-1"],
            },
        ]
    )

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompts.append(kwargs["json"]["messages"][1]["content"])
        return _model_response(next(responses))

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )

    quick = provider.explain("注意力机制", [], [], "beginner", "zh-CN")
    paper = PaperRecord(
        id="arxiv:1706.03762",
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        year=2017,
        abstract="The Transformer is based solely on attention mechanisms.",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        source_kind="academic",
        access_type="open_access",
    )
    evidence = EvidenceCard(
        id="evidence-1",
        paper_id=paper.id,
        claim="摘要介绍了基于注意力的 Transformer。",
        excerpt=paper.abstract,
    )
    literature = provider.explain(
        "注意力机制", [paper], [evidence], "beginner", "zh-CN"
    )

    assert quick.evidence_ids == []
    assert literature.evidence_ids == ["evidence-1"]
    assert "快速解释" in prompts[0]
    assert "文献解释" in prompts[1]
    assert paper.abstract in prompts[1]


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
