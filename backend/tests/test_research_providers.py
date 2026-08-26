import httpx
import json
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import EvidenceCard, PaperRecord, SearchQueryPlan
from app.services import research_providers
from app.services.research_providers import (
    ArxivSearchProvider,
    CrossrefSearchProvider,
    MultiSourceSearchProvider,
    OpenAICompatibleExplanationProvider,
    OpenAlexSearchProvider,
    ProviderRateLimited,
    ProviderUnavailable,
    RuleBasedExplanationProvider,
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
        return _model_response(
            {
                "queries": [
                    {"query": "attention mechanism", "purpose": "core"},
                    {"query": "neural sequence alignment", "purpose": "foundational"},
                    {"query": "efficient self attention", "purpose": "recent"},
                ]
            }
        )

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )

    queries = provider.plan_search_queries("注意力机制", "zh-CN")

    assert [item.query for item in queries] == [
        "attention mechanism",
        "neural sequence alignment",
        "efficient self attention",
    ]
    assert [item.purpose for item in queries] == ["core", "foundational", "recent"]
    assert captured["url"] == "https://model.example/v1/chat/completions"
    request_json = captured["json"]
    assert request_json["model"] == "test-model"
    assert "注意力机制" in request_json["messages"][1]["content"]


def test_compatible_model_uses_first_round_papers_for_feedback_queries(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured.update({"url": url, **kwargs})
        return _model_response(
            {
                "queries": [
                    {
                        "query": "KV cache token pruning",
                        "purpose": "method_family",
                        "derived_from_paper_ids": ["paper-1"],
                    },
                    {
                        "query": "agentic coding KV cache",
                        "purpose": "application",
                        "derived_from_paper_ids": ["paper-1"],
                    },
                ]
            }
        )

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )
    paper = PaperRecord(
        id="paper-1",
        title="Structural KV Cache Compression",
        abstract="The method retains critical code tokens for agentic coding.",
        source="arxiv",
        source_kind="academic",
        access_type="abstract_only",
    )

    queries = provider.plan_followup_queries(
        "KV cache compression",
        [paper],
        [SearchQueryPlan(query="KV cache compression", purpose="core")],
        "zh-CN",
    )

    assert [item.query for item in queries] == [
        "KV cache token pruning",
        "agentic coding KV cache",
    ]
    assert all(item.phase == "feedback" for item in queries)
    assert all(item.derived_from_paper_ids == ["paper-1"] for item in queries)
    request_prompt = captured["json"]["messages"][1]["content"]
    assert paper.title in request_prompt
    assert paper.abstract in request_prompt


def test_arxiv_provider_spaces_multiple_calls_without_real_wait(monkeypatch) -> None:
    clock_values = iter([10.0, 10.5, 13.0])
    waits: list[float] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, content=ARXIV_FEED, request=httpx.Request("GET", url))

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)
    provider = ArxivSearchProvider(
        minimum_interval_seconds=3.0,
        sleep=waits.append,
        clock=lambda: next(clock_values),
    )

    provider.search("attention mechanism", 2)
    provider.search("efficient self attention", 2)

    assert waits == [2.5]


def test_arxiv_search_retries_a_transient_connection_reset(monkeypatch) -> None:
    attempts = 0
    waits: list[float] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection reset", request=httpx.Request("GET", url))
        return httpx.Response(200, content=ARXIV_FEED, request=httpx.Request("GET", url))

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)

    papers = ArxivSearchProvider(
        max_retries=2,
        retry_backoff_seconds=0.25,
        sleep=waits.append,
    ).search("attention mechanism", 2)

    assert attempts == 2
    assert waits == [0.25]
    assert papers[0].source == "arxiv"


def test_openalex_and_crossref_normalize_public_metadata(monkeypatch) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        if "openalex" in url:
            return httpx.Response(
                200,
                json={
                    "results": [{
                        "id": "https://openalex.org/W123",
                        "doi": "https://doi.org/10.1000/openalex",
                        "title": "OpenAlex Attention Work",
                        "publication_year": 2024,
                        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                        "primary_location": {
                            "landing_page_url": "https://example.test/openalex",
                            "source": {"display_name": "Open Journal"},
                        },
                        "abstract_inverted_index": {"attention": [0], "works": [1]},
                        "open_access": {"is_oa": True},
                        "cited_by_count": 42,
                    }],
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [{
                        "DOI": "10.1000/crossref",
                        "title": ["Crossref Attention Work"],
                        "author": [{"given": "Grace", "family": "Hopper"}],
                        "container-title": ["Metadata Journal"],
                        "issued": {"date-parts": [[2023, 1, 1]]},
                        "abstract": "<jats:p>Metadata abstract</jats:p>",
                        "URL": "https://doi.org/10.1000/crossref",
                        "is-referenced-by-count": 7,
                    }],
                },
            },
            request=request,
        )

    monkeypatch.setattr(research_providers.httpx, "get", fake_get)

    openalex = OpenAlexSearchProvider().search("attention", 2)[0]
    crossref = CrossrefSearchProvider().search("attention", 2)[0]

    assert openalex.doi == "10.1000/openalex"
    assert openalex.abstract == "attention works"
    assert openalex.access_type == "open_access"
    assert crossref.doi == "10.1000/crossref"
    assert crossref.authors == ["Grace Hopper"]
    assert crossref.abstract == "Metadata abstract"


def test_multi_source_keeps_available_results_and_deduplicates() -> None:
    class StaticProvider:
        def __init__(self, name: str, records: list[PaperRecord] | None = None) -> None:
            self.name = name
            self.records = records or []

        def search(self, concept: str, limit: int) -> list[PaperRecord]:
            if self.name == "offline":
                raise ProviderUnavailable("temporary outage", provider=self.name)
            return self.records[:limit]

    first = PaperRecord(
        id="arxiv:1", title="Shared Work", doi="10.1000/shared", source="arxiv", source_kind="academic", access_type="open_access"
    )
    duplicate = PaperRecord(
        id="openalex:1", title="Shared Work", doi="10.1000/shared", source="openalex", source_kind="academic", access_type="metadata_only"
    )
    distinct = PaperRecord(
        id="crossref:2", title="Distinct Work", doi="10.1000/distinct", source="crossref", source_kind="academic", access_type="metadata_only"
    )

    provider = MultiSourceSearchProvider([
        StaticProvider("arxiv", [first]),
        StaticProvider("offline"),
        StaticProvider("crossref", [duplicate, distinct]),
    ])
    papers = provider.search("attention", 4)

    assert [paper.title for paper in papers] == ["Shared Work", "Distinct Work"]
    assert provider.last_warnings == [
        "offline 暂时不可用；已保留其他论文来源的检索结果，可稍后重试。"
    ]


def test_compatible_model_distinguishes_quick_and_abstract_modes(monkeypatch) -> None:
    prompts: list[str] = []
    quick_payload = {
                "one_sentence": "注意力机制让模型按相关性聚合信息。",
                "intuitive": "像阅读时把注意力放在关键句上。",
                "technical": "通过查询、键和值计算加权表示。",
                "evolution": ["从对齐机制发展到自注意力"],
                "claims": [
                    {
                        "claim_type": "definition",
                        "text": "注意力机制按相关性聚合信息。",
                        "paper_ids": [],
                        "evidence_ids": [],
                        "scope": "通用知识，待检索核验",
                    }
                ],
                "research_limitations": [],
                "research_gap_candidates": [],
                "reproducibility_checks": [],
                "scope_warnings": ["本次没有检索论文。"],
                "related_concepts": ["Self-Attention", "Transformer"],
                "limitations": ["本次没有检索论文，需要后续文献核验。"],
                "evidence_ids": [],
    }
    core_payload = {
        "one_sentence": "注意力机制根据相关性汇聚上下文。",
        "intuitive": "像带着问题查阅资料。",
        "technical": "摘要资料显示自注意力支持并行序列建模。",
        "related_concepts": ["Self-Attention", "Transformer"],
        "scope_warnings": ["当前仅核对摘要。"],
    }
    claims_payload = {
                "evolution": ["2017：Transformer 将自注意力作为核心结构"],
                "evolution_items": [],
                "claims": [
                    {
                        "claim_type": "mechanism",
                        "text": "Transformer 使用自注意力进行序列建模。",
                        "paper_ids": ["arxiv:1706.03762"],
                        "evidence_ids": ["evidence-1"],
                        "evidence_quotes": [
                            "The Transformer is based solely on attention mechanisms."
                        ],
                        "scope": "摘要级线索",
                    }
                ],
                "evidence_ids": ["evidence-1"],
    }
    limitations_payload = {
                "limitation_decisions": [
                    {
                        "evidence_id": "evidence-1",
                        "decision": "limitation",
                        "reason": "摘要明确说明标准自注意力无法高效扩展。",
                        "limitation_kind": "method_limitation",
                    }
                ],
                "research_limitations": [
                    {
                        "text": "标准自注意力无法高效扩展到超长序列。",
                        "limitation_kind": "method_limitation",
                        "target": "标准自注意力",
                        "condition": "超长序列",
                        "consequence": "计算成本过高",
                        "paper_ids": ["arxiv:1706.03762"],
                        "evidence_ids": ["evidence-1"],
                        "explicitness": "explicit",
                    }
                ],
                "research_gap_candidates": [],
                "reproducibility_checks": [],
    }

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompt = kwargs["json"]["messages"][1]["content"]
        prompts.append(prompt)
        if "快速解释模式" in prompt:
            return _model_response(quick_payload)
        if "核心说明" in prompt:
            return _model_response(core_payload)
        if "时间线与原子主张" in prompt:
            return _model_response(claims_payload)
        if "研究局限审核" in prompt:
            return _model_response(limitations_payload)
        raise AssertionError("unexpected model prompt")

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
        abstract=(
            "The Transformer is based solely on attention mechanisms. "
            "However, standard self-attention cannot scale efficiently to very long sequences."
        ),
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
        evidence_type="mechanism",
        evidence_types=["mechanism", "limitation"],
    )
    literature = provider.explain(
        "注意力机制", [paper], [evidence], "beginner", "zh-CN"
    )

    assert quick.evidence_ids == []
    assert literature.evidence_ids == ["evidence-1"]
    assert quick.claims[0].claim_type == "definition"
    assert literature.claims[0].paper_ids == [paper.id]
    assert literature.research_limitations[0].limitation_kind == "method_limitation"
    assert literature.limitation_decisions[0].decision == "limitation"
    assert literature.scope_warnings == ["当前仅核对摘要。"]
    assert [item.status for item in quick.model_call_traces] == ["succeeded"]
    assert len(literature.model_call_traces) == 3
    assert all(item.status == "succeeded" for item in literature.model_call_traces)
    assert len(prompts) == 4
    assert any("快速解释模式" in prompt for prompt in prompts)
    assert any("核心说明" in prompt for prompt in prompts)
    assert any("时间线与原子主张" in prompt for prompt in prompts)
    assert any("研究局限审核" in prompt for prompt in prompts)
    assert all(paper.abstract in prompt for prompt in prompts if "快速解释模式" not in prompt)


def test_compatible_model_repairs_optional_items_without_losing_valid_explanation(monkeypatch) -> None:
    prompts: list[str] = []
    payload = {
        "one_sentence": "KV cache 压缩用于降低长上下文推理的缓存占用。",
        "intuitive": "像保留笔记中的关键信息。",
        "technical": "方法会选择或压缩历史键值表示。",
        "evolution": [],
        "claims": [
            {
                "claim_type": "mechanism",
                "text": "该方法压缩历史键值表示。",
                "paper_ids": ["arxiv:2506.00001"],
                "evidence_ids": ["evidence-1"],
                "scope": "摘要级线索",
            },
            {
                "claim_type": "result",
                "paper_ids": ["arxiv:2506.00001"],
                "evidence_ids": [],
                "scope": "缺少 text，应被逐条忽略",
            },
        ],
        "research_limitations": [],
        "research_gap_candidates": [],
        "reproducibility_checks": [
            {
                "text": "论文代码是否公开尚未验证。",
                "check_type": "not verified",
                "paper_ids": ["arxiv:2506.00001"],
            },
            {
                "text": "需要确认实现采用的许可证。",
                "check_type": "arxiv:2506.00001",
                "paper_ids": [],
            },
            {
                "text": "这条内容无法判断属于哪种复现检查。",
                "check_type": "unknown",
                "paper_ids": [],
            },
        ],
        "scope_warnings": ["当前仅核对摘要。"],
        "related_concepts": ["KV cache eviction"],
        "limitations": [],
        "evidence_ids": ["evidence-1"],
        "unexpected_debug_field": "ignore me",
    }

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompt = kwargs["json"]["messages"][1]["content"]
        prompts.append(prompt)
        if "核心说明" in prompt:
            return _model_response(
                {
                    key: payload[key]
                    for key in ("one_sentence", "intuitive", "technical", "related_concepts", "scope_warnings")
                }
            )
        if "时间线与原子主张" in prompt:
            return _model_response(
                {
                    "evolution": payload["evolution"],
                    "evolution_items": [],
                    "claims": payload["claims"],
                    "evidence_ids": payload["evidence_ids"],
                    "unexpected_debug_field": "ignore me",
                }
            )
        if "研究局限审核" in prompt:
            return _model_response(
                {
                    "limitation_decisions": [],
                    "research_limitations": payload["research_limitations"],
                    "research_gap_candidates": payload["research_gap_candidates"],
                    "reproducibility_checks": payload["reproducibility_checks"],
                }
            )
        raise AssertionError("unexpected model prompt")

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )
    paper = PaperRecord(
        id="arxiv:2506.00001",
        arxiv_id="2506.00001",
        title="A KV Cache Compression Paper",
        abstract="The method compresses cached key-value representations.",
        source="arxiv",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = EvidenceCard(
        id="evidence-1",
        paper_id=paper.id,
        claim="摘要介绍了一种 KV cache 压缩方法。",
        excerpt=paper.abstract,
    )

    explanation = provider.explain(
        "KV cache 压缩", [paper], [evidence], "researcher", "zh-CN"
    )

    assert explanation.one_sentence == payload["one_sentence"]
    assert len(explanation.claims) == 1
    assert [item.check_type for item in explanation.reproducibility_checks] == ["code", "license"]
    assert explanation.reproducibility_checks[1].paper_ids == ["arxiv:2506.00001"]
    assert any("原子主张中有 1 条" in item for item in explanation.model_output_warnings)
    assert any("复现检查中有 2 条类型已自动纠正" in item for item in explanation.model_output_warnings)
    assert any("复现检查中有 1 条无法安全校验" in item for item in explanation.model_output_warnings)
    assert any("未约定字段" in item for item in explanation.model_output_warnings)
    prompt = next(item for item in prompts if "研究局限审核" in item)
    assert "check_type 只能是以下五个英文值之一" in prompt
    assert "arXiv ID 只能放入 paper_ids" in prompt


def test_atomic_claim_parser_repairs_unambiguous_field_aliases() -> None:
    explanation = research_providers._parse_explanation_result(
        json.dumps(
            {
                "one_sentence": "A concise definition.",
                "intuitive": "An analogy.",
                "technical": "A technical explanation.",
                "claims": [
                    {
                        "type": "mechanism",
                        "claim": "The method compresses cache states.",
                        "paper_id": "paper-1",
                        "evidence_id": "evidence-1",
                        "evidence_quote": "The method compresses cache states.",
                        "scope": "abstract",
                    }
                ],
            }
        )
    )

    assert len(explanation.claims) == 1
    assert explanation.claims[0].text == "The method compresses cache states."
    assert explanation.claims[0].paper_ids == ["paper-1"]
    assert explanation.claims[0].evidence_ids == ["evidence-1"]
    assert explanation.claims[0].evidence_quotes == ["The method compresses cache states."]
    assert any("原子主张中有 1 条类型已自动纠正" in item for item in explanation.model_output_warnings)


def test_split_literature_call_keeps_core_when_limitation_part_fails(monkeypatch) -> None:
    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompt = kwargs["json"]["messages"][1]["content"]
        if "核心说明" in prompt:
            return _model_response(
                {
                    "one_sentence": "KV cache 压缩用于降低推理缓存占用。",
                    "intuitive": "像压缩工作记忆。",
                    "technical": "方法选择、量化或合并历史键值表示。",
                    "related_concepts": ["KV cache eviction"],
                    "scope_warnings": ["当前仅核对摘要。"],
                }
            )
        if "时间线与原子主张" in prompt:
            return _model_response(
                {
                    "evolution": [],
                    "evolution_items": [],
                    "claims": [
                        {
                            "claim_type": "mechanism",
                            "text": "该方法压缩历史键值表示。",
                            "paper_ids": ["paper-1"],
                            "evidence_ids": ["evidence-1"],
                            "evidence_quotes": ["The method compresses cached key-value representations."],
                            "scope": "摘要级线索",
                        }
                    ],
                    "evidence_ids": ["evidence-1"],
                }
            )
        if "研究局限审核" in prompt:
            return httpx.Response(
                503,
                request=httpx.Request("POST", url),
            )
        raise AssertionError("unexpected model prompt")

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )
    paper = PaperRecord(
        id="paper-1",
        title="Cache Compression",
        abstract="The method compresses cached key-value representations.",
        source="arxiv",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = EvidenceCard(
        id="evidence-1",
        paper_id=paper.id,
        claim="摘要中的机制线索。",
        excerpt=paper.abstract,
        evidence_type="mechanism",
        evidence_types=["mechanism"],
    )

    explanation = provider.explain(
        "KV cache 压缩", [paper], [evidence], "researcher", "zh-CN"
    )

    assert explanation.one_sentence == "KV cache 压缩用于降低推理缓存占用。"
    assert explanation.claims[0].evidence_ids == ["evidence-1"]
    assert explanation.research_limitations == []
    assert any("研究局限审核调用失败" in item for item in explanation.model_output_warnings)


def test_limitation_part_receives_late_multilabel_evidence(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompt = kwargs["json"]["messages"][1]["content"]
        prompts.append(prompt)
        if "核心说明" in prompt:
            return _model_response(
                {
                    "one_sentence": "A concise explanation.",
                    "intuitive": "An analogy.",
                    "technical": "A technical explanation.",
                    "related_concepts": [],
                    "scope_warnings": [],
                }
            )
        if "时间线与原子主张" in prompt:
            return _model_response(
                {"evolution": [], "evolution_items": [], "claims": [], "evidence_ids": []}
            )
        if "研究局限审核" in prompt:
            return _model_response(
                {
                    "limitation_decisions": [
                        {
                            "evidence_id": "evidence-late-limitation",
                            "decision": "reject",
                            "reason": "fixture rejection",
                            "limitation_kind": None,
                        }
                    ],
                    "research_limitations": [],
                    "research_gap_candidates": [],
                    "reproducibility_checks": [],
                }
            )
        raise AssertionError("unexpected model prompt")

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )
    paper = PaperRecord(
        id="paper-1",
        title="Late Limitation Evidence",
        abstract="Existing methods fail under long contexts.",
        source="arxiv",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = [
        EvidenceCard(
            id=f"evidence-{index}",
            paper_id=paper.id,
            claim="普通证据卡。",
            excerpt=f"Background sentence {index}.",
            evidence_type="context",
        )
        for index in range(14)
    ]
    evidence.append(
        EvidenceCard(
            id="evidence-late-limitation",
            paper_id=paper.id,
            claim="摘要中的明确失败模式。",
            excerpt="Existing methods fail under long contexts.",
            evidence_type="mechanism",
            evidence_types=["limitation", "mechanism"],
        )
    )

    explanation = provider.explain(
        "KV cache compression", [paper], evidence, "researcher", "zh-CN"
    )

    limitation_prompt = next(item for item in prompts if "研究局限审核" in item)
    assert "evidence-late-limitation" in limitation_prompt
    assert "类型：limitation+mechanism" in limitation_prompt
    assert "evidence-0" not in limitation_prompt
    assert any("未提取到满足条件" in item for item in explanation.model_output_warnings)


def test_claim_generation_batches_cover_every_selected_paper(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        prompt = kwargs["json"]["messages"][1]["content"]
        prompts.append(prompt)
        if "核心说明" in prompt:
            return _model_response(
                {
                    "one_sentence": "A batched explanation.",
                    "intuitive": "An analogy.",
                    "technical": "A technical synthesis.",
                    "related_concepts": [],
                    "scope_warnings": [],
                }
            )
        if "时间线与原子主张" in prompt:
            included = [index for index in range(4) if f"Paper {index}" in prompt]
            return _model_response(
                {
                    "evolution_items": [
                        {
                            "year": 2020 + index,
                            "title": f"Paper {index}",
                            "summary": f"Paper {index} introduces method {index}.",
                            "paper_ids": [f"paper-{index}"],
                            "evidence_ids": [f"evidence-{index}"],
                        }
                        for index in included
                    ],
                    "claims": [
                        {
                            "claim_type": "mechanism",
                            "text": f"Method {index} compresses cache states.",
                            "paper_ids": [f"paper-{index}"],
                            "evidence_ids": [f"evidence-{index}"],
                            "evidence_quotes": [f"Method {index} compresses cache states."],
                            "scope": "abstract",
                        }
                        for index in included
                    ],
                }
            )
        if "研究局限审核" in prompt:
            return _model_response(
                {
                    "limitation_decisions": [],
                    "research_limitations": [],
                    "research_gap_candidates": [],
                    "reproducibility_checks": [],
                }
            )
        raise AssertionError("unexpected model prompt")

    monkeypatch.setattr(research_providers.httpx, "post", fake_post)
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )
    papers = [
        PaperRecord(
            id=f"paper-{index}",
            title=f"Paper {index}",
            year=2020 + index,
            abstract=f"Method {index} compresses cache states.",
            source="arxiv",
            source_kind="academic",
            access_type="abstract_only",
        )
        for index in range(4)
    ]
    evidence = [
        EvidenceCard(
            id=f"evidence-{index}",
            paper_id=f"paper-{index}",
            claim="mechanism",
            excerpt=f"Method {index} compresses cache states.",
            evidence_type="mechanism",
            evidence_types=["mechanism"],
        )
        for index in range(4)
    ]

    explanation = provider.explain(
        "cache compression", papers, evidence, "researcher", "zh-CN"
    )

    assert {paper_id for claim in explanation.claims for paper_id in claim.paper_ids} == {
        paper.id for paper in papers
    }
    claim_prompts = [item for item in prompts if "时间线与原子主张" in item]
    assert len(claim_prompts) == 2
    assert all(sum(f"Paper {index}" in prompt for index in range(4)) == 2 for prompt in claim_prompts)
    assert len(explanation.model_call_traces) == 4
    assert not any("仍未覆盖" in item for item in explanation.model_output_warnings)


def test_compatible_model_still_rejects_missing_core_explanation(monkeypatch) -> None:
    monkeypatch.setattr(
        research_providers.httpx,
        "post",
        lambda url, **kwargs: _model_response(
            {
                "intuitive": "缺少一句话定义。",
                "technical": "核心字段不完整。",
                "claims": [],
            }
        ),
    )
    provider = OpenAICompatibleExplanationProvider(
        api_key="model-key",
        base_url="https://model.example/v1",
        model="test-model",
    )

    with pytest.raises(ProviderUnavailable, match="缺少必要字段"):
        provider.explain("KV cache 压缩", [], [], "researcher", "zh-CN")


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
        community_provider="demo",
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
    monkeypatch.setattr(
        RuleBasedExplanationProvider,
        "plan_search_queries",
        lambda self, concept, language: [
            SearchQueryPlan(query="agent systems", purpose="core"),
            SearchQueryPlan(query="autonomous agents", purpose="recent"),
        ],
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="semantic_scholar",
        community_provider="demo",
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
