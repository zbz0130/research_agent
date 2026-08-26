from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import EvidenceCard, InnovationCandidate
from app.services.research_orchestration import ResearchOrchestrator
from app.services.research_providers import DemoSearchProvider
from app.services.research_service import research_service
from app.storage import storage
from app.services.project_service import project_service


client = TestClient(app)


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
