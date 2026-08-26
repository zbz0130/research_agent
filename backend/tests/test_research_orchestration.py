from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import EvidenceCard, InnovationCandidate
from app.services.research_orchestration import (
    HackerNewsCommunityProvider,
    RedditCommunityProvider,
    ResearchOrchestrator,
    XCommunityProvider,
)
from app.services.research_providers import DemoSearchProvider
from app.services.research_service import research_service
from app.storage import storage
from app.services.project_service import project_service


client = TestClient(app)


class _JsonResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


def _wait_for_job(job_id: str) -> dict:
    for _ in range(80):
        job = client.get(f"/api/v1/analyses/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
    return job


def _demo_settings(**overrides: object) -> Settings:
    values = {
        "paper_provider": "demo",
        "explanation_provider": "rule_based",
        "community_provider": "demo",
        "demo_mode": True,
    }
    values.update(overrides)
    return Settings(**values)


def setup_function() -> None:
    storage.clear()
    project_service.clear()
    research_service.clear()
    # FastAPI inspects an override's signature.  Wrap the helper so its
    # convenience ``**overrides`` parameter is not exposed as a query field.
    app.dependency_overrides[get_settings] = lambda: _demo_settings()


def teardown_function() -> None:
    app.dependency_overrides.clear()
    storage.clear()
    project_service.clear()
    research_service.clear()


def test_research_mode_returns_auditable_multi_agent_brief() -> None:
    created = client.post(
        "/api/v1/analyses",
        json={"concept": "Attention Mechanism", "level": "research", "max_papers": 4},
    )
    assert created.status_code == 202

    job = _wait_for_job(created.json()["id"])
    assert job["status"] == "completed", job
    result = job["result"]
    brief = result["research_brief"]

    assert {run["role"] for run in brief["agent_runs"]} == {
        "community",
        "model_brainstorm",
        "future_work",
        "synthesis",
    }
    assert all(run["status"] == "completed" for run in brief["agent_runs"])
    assert brief["community_signals"]
    assert brief["model_ideas"]
    assert all(item["source_type"] == "model_generated" for item in brief["model_ideas"])
    assert brief["future_work_signals"]
    assert brief["innovation_candidates"]
    assert all(item["confidence"] == "low" for item in brief["innovation_candidates"])
    assert any("arXiv" in warning for warning in brief["warnings"])
    brief_response = client.get(
        f"/api/v1/analyses/{created.json()['id']}/research-brief"
    )
    assert brief_response.status_code == 200
    assert brief_response.json()["topic"] == "Attention Mechanism"


def test_community_failure_is_visible_and_does_not_become_novelty_claim() -> None:
    app.dependency_overrides[get_settings] = lambda: _demo_settings(community_provider="not_configured")
    created = client.post(
        "/api/v1/analyses",
        json={"concept": "Attention Mechanism", "level": "research"},
    )
    job = _wait_for_job(created.json()["id"])
    assert job["status"] == "completed", job
    brief = job["result"]["research_brief"]
    community_run = next(item for item in brief["agent_runs"] if item["role"] == "community")
    assert community_run["status"] == "failed"
    assert community_run["error"]
    assert brief["coverage"]["community_signals"] == 0
    assert any("社区 Agent 未完成" in warning for warning in brief["warnings"])
    assert "不能据此证明全球不存在" in job["result"]["novelty_note"]


def test_hacker_news_provider_returns_real_linked_signals_without_a_key() -> None:
    calls: list[str] = []

    def fake_get(url: str, **_: object) -> _JsonResponse:
        calls.append(url)
        if url.endswith("newstories.json"):
            return _JsonResponse([101, 102])
        if url.endswith("item/101.json"):
            return _JsonResponse(
                {
                    "id": 101,
                    "type": "story",
                    "title": "Signal processing tools for non-stationary data",
                    "text": "Ask HN: how do researchers validate non-stationary signal processing?",
                    "score": 31,
                    "descendants": 8,
                    "time": 1_700_000_000,
                }
            )
        return _JsonResponse({"id": 102, "type": "story", "title": "Unrelated post"})

    signals = HackerNewsCommunityProvider("https://hn.example/v0", request_get=fake_get).search(
        "非平稳信号处理",
        6,
        query_terms=["non-stationary signal processing"],
    )

    assert calls[0] == "https://hn.example/v0/newstories.json"
    assert len(signals) == 1
    assert signals[0].platform == "hacker_news"
    assert signals[0].id == "hacker-news-101"
    assert signals[0].url == "https://news.ycombinator.com/item?id=101"
    assert signals[0].verification_status == "unverified"


def test_x_and_reddit_providers_require_tokens_and_keep_source_links() -> None:
    def x_get(url: str, **kwargs: object) -> _JsonResponse:
        assert url == "https://api.x.com/2/tweets/search/recent"
        assert kwargs["headers"] == {"Authorization": "Bearer x-token"}
        return _JsonResponse(
            {"data": [{"id": "18", "text": "Signal processing benchmark is hard to reproduce", "public_metrics": {"like_count": 4, "reply_count": 2}}]}
        )

    x_signals = XCommunityProvider("x-token", request_get=x_get).search(
        "signal processing", 4
    )
    assert x_signals[0].platform == "x"
    assert x_signals[0].url == "https://x.com/i/web/status/18"

    def reddit_get(url: str, **kwargs: object) -> _JsonResponse:
        assert url == "https://oauth.reddit.com/search"
        assert kwargs["headers"]["Authorization"] == "Bearer reddit-token"
        return _JsonResponse(
            {"data": {"children": [{"data": {"id": "abc", "title": "KV cache memory trade-off", "selftext": "How do you reproduce it?", "subreddit": "LocalLLaMA", "score": 10, "num_comments": 3, "permalink": "/r/LocalLLaMA/comments/abc/example/", "created_utc": 1_700_000_000}}]}}
        )

    reddit_signals = RedditCommunityProvider("reddit-token", request_get=reddit_get).search(
        "KV cache", 4
    )
    assert reddit_signals[0].platform == "reddit"
    assert reddit_signals[0].url == "https://www.reddit.com/r/LocalLLaMA/comments/abc/example/"


def test_non_research_analysis_has_no_research_brief_endpoint() -> None:
    created = client.post(
        "/api/v1/analyses",
        json={"concept": "Attention Mechanism", "level": "literature"},
    )
    job = _wait_for_job(created.json()["id"])
    assert job["status"] == "completed", job
    response = client.get(f"/api/v1/analyses/{created.json()['id']}/research-brief")
    assert response.status_code == 404


def test_compatible_model_can_supply_brainstorm_and_synthesis_agents() -> None:
    class FakeModel:
        name = "fake_compatible_model"

        def brainstorm(self, concept, papers, evidence, language):
            return [
                InnovationCandidate(
                    title="Fake model candidate",
                    problem="验证一个明确边界",
                    mechanism="使用可复现对照实验",
                    novelty_level="L3",
                    confidence="high",
                    feasibility="high",
                    rationale="测试模型分支",
                    validation_steps=["运行最小实验"],
                )
            ]

        def synthesize_research(self, concept, community_signals, model_ideas, future_work_signals):
            return (
                "Fake synthesis",
                [
                    InnovationCandidate(
                        title="Synthesized candidate",
                        problem="验证综合结果",
                        mechanism="组合三个分支",
                        novelty_level="L2",
                        confidence="high",
                        feasibility="medium",
                        rationale="测试综合分支",
                        validation_steps=["核对论文和社区信号"],
                    )
                ],
            )

    papers = DemoSearchProvider().search("Attention Mechanism", 2)
    evidence = [
        EvidenceCard(
            paper_id=papers[0].id,
            claim="摘要级机制线索",
            excerpt=papers[0].abstract[:200],
        )
    ]
    brief = ResearchOrchestrator().run(
        "Attention Mechanism",
        papers,
        evidence,
        DemoSearchProvider(),
        _demo_settings(),
        explanation_provider=FakeModel(),
        language="en",
    )
    runs = {item.role: item for item in brief.agent_runs}
    assert runs["model_brainstorm"].provider == "fake_compatible_model"
    assert runs["synthesis"].provider == "fake_compatible_model"
    assert brief.synthesis.startswith("Fake synthesis")
    assert brief.innovation_candidates[0].source_type == "synthesis"
