from __future__ import annotations

import importlib
import time
from threading import Lock
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import (
    AnalysisJob,
    AnalysisResult,
    ConceptGraph,
    ConceptNode,
    EvidenceCard,
    ExplanationResult,
    PaperRecord,
    OverviewCreate,
    OverviewDirectionAudit,
    OverviewJob,
    OverviewResult,
)
from app.storage import Storage, storage
from app.services.overview_pipeline import (
    DirectionResearchCoordinator,
    OpenArxivSectionReader,
    SectionReadResult,
    TopicTaxonomyPlanner,
)
from app.services.overview_service import _read_paper_abstract, _read_paper_sections
import app.services.overview_service as overview_module
from app.services.research_providers import (
    DemoSearchProvider,
    OpenAICompatibleExplanationProvider,
    ProviderUnavailable,
)
from app.services.research_service import research_service


client = TestClient(app)


def _wait_analysis(job_id: str) -> dict:
    for _ in range(500):
        payload = client.get(f"/api/v1/analyses/{job_id}").json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("analysis did not finish")


def _wait_overview(overview_id: str) -> dict:
    for _ in range(500):
        payload = client.get(f"/api/v1/overviews/{overview_id}").json()
        if payload["status"] in {"succeeded", "partial", "failed", "interrupted"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("overview did not finish")


def _completed_analysis(*, level: str = "literature") -> str:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    response = client.post(
        "/api/v1/analyses",
        json={
            "concept": "Attention Mechanism",
            "level": level,
            "audience": "beginner",
            "max_papers": 4,
        },
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    analysis = _wait_analysis(job_id)
    assert analysis["status"] == "completed"
    return job_id


def test_overview_create_poll_and_idempotent_reuse() -> None:
    try:
        analysis_id = _completed_analysis()
        created = client.post(f"/api/v1/analyses/{analysis_id}/overview", json={})
        assert created.status_code == 202
        overview_id = created.json()["id"]

        duplicate = client.post(f"/api/v1/analyses/{analysis_id}/overview", json={})
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == overview_id

        job = _wait_overview(overview_id)
        assert job["status"] == "succeeded"
        assert job["stage"] == "completed"
        assert job["progress"] == 100
        assert job["save_state"] == "transient"
        result = job["result"]
        graph = result["graph"]
        assert graph["graph_kind"] == "research_direction"
        assert graph["save_state"] == "transient"
        assert graph["source_analysis_id"] == analysis_id
        assert graph["source_scope"] == "metadata_abstract"
        assert graph["layout_algorithm"] == "breadthfirst"
        assert result["paper_count"] >= 1
        assert result["paper_count"] <= job["request"]["max_total_papers"]
        assert result["direction_count"] <= 16
        assert "当前检索范围内" in result["legend"]["heat_note"]

        nodes = graph["nodes"]
        node_by_id = {node["id"]: node for node in nodes}
        problem_nodes = [node for node in nodes if node["role"] == "problem"]
        method_nodes = [node for node in nodes if node["role"] == "method"]
        paper_nodes = [node for node in nodes if node["role"] == "paper"]
        assert problem_nodes
        assert method_nodes
        assert all(node["problem_summary"] for node in problem_nodes)
        assert all(node["method_summary"] for node in method_nodes)
        assert len(paper_nodes) == result["paper_count"]
        assert all(node["paper_id"] for node in paper_nodes)
        assert all(node["problem_summary"] for node in paper_nodes)
        assert all(node["method_summary"] for node in paper_nodes)
        assert all(node["how_it_works"] for node in paper_nodes)
        assert all(node["summary_level"] == "abstract_only" for node in paper_nodes)
        assert all(0 <= node["visual"]["recency_score"] <= 1 for node in nodes)
        assert all(0 <= node["visual"]["heat_score"] <= 1 for node in nodes)
        assert all(item["summary_level"] == "abstract_only" for item in result["paper_readings"])

        outgoing = {node["id"]: [] for node in nodes}
        for edge in graph["edges"]:
            outgoing[edge["source"]].append(edge["target"])
        assert all(not outgoing[node["id"]] for node in paper_nodes)
        parents = {edge["target"]: edge["source"] for edge in graph["edges"]}
        assert all(node_by_id[parents[node["id"]]]["role"] == "method" for node in paper_nodes)
        assert all(
            node_by_id[parents[parents[node["id"]]]]["role"] == "problem"
            for node in paper_nodes
        )
        assert all(
            parents[parents[parents[node["id"]]]] == graph["root_id"]
            for node in paper_nodes
        )
        assert client.get(f"/api/v1/graphs/{graph['id']}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_overview_uses_live_request_settings_for_optional_model_agents(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_plan(self, topic, papers, prior_queries, *, max_directions):
        calls.append(f"plan:{self.model}")
        return [
            {
                "key": "agent_systems",
                "label": "Agent 系统",
                "definition": "研究 Agent 的系统实现。",
                "boundary": "不包含无关主题。",
                "query_terms": ["agent systems"],
                "match_terms": ["agent", "system"],
                "seed_paper_ids": [paper.id for paper in papers[:2]],
            }
        ]

    def fake_synthesis(self, topic, directions, paper_summaries):
        calls.append(f"synthesis:{self.model}")
        return {
            "title": f"{topic} 研究方向图",
            "root_explanation": "使用请求时配置的模型设置生成展示文案。",
            "direction_explanations": {},
            "warnings": [],
        }

    def fake_review(self, topic, direction, papers):
        calls.append(f"review:{self.model}")
        return {
            "decision": "keep",
            "reason": "测试范围内的方法差异不足以继续拆分。",
            "method_routes": [
                {
                    "key": "core",
                    "label": "核心方法路线",
                    "paper_ids": [paper.id for paper in papers],
                }
            ],
        }

    def fake_paper_summaries(self, topic, direction, papers):
        calls.append(f"papers:{self.model}")
        return {
            "papers": [
                {
                    "paper_id": paper["paper_id"],
                    "problem": paper["deterministic_extract"]["problem"],
                    "method": paper["deterministic_extract"]["method"],
                    "how_it_works": paper["deterministic_extract"]["how_it_works"],
                    "limitations": "",
                }
                for paper in papers
            ]
        }

    monkeypatch.setattr(
        OpenAICompatibleExplanationProvider,
        "plan_research_directions",
        fake_plan,
    )
    monkeypatch.setattr(
        OpenAICompatibleExplanationProvider,
        "synthesize_research_overview",
        fake_synthesis,
    )
    monkeypatch.setattr(
        OpenAICompatibleExplanationProvider,
        "review_research_direction",
        fake_review,
    )
    monkeypatch.setattr(
        OpenAICompatibleExplanationProvider,
        "summarize_research_papers",
        fake_paper_summaries,
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="openai_compatible",
        explanation_api_key="runtime-test-key",
        explanation_model="runtime-overview-model",
        explanation_base_url="https://proxy.example.test/v1",
        demo_mode=True,
    )
    try:
        analysis_id = _completed_analysis()
        # _completed_analysis intentionally installs its own rule-based
        # override for the seed analysis; switch to the live runtime model
        # configuration before creating the Overview request.
        app.dependency_overrides[get_settings] = lambda: Settings(
            paper_provider="demo",
            explanation_provider="openai_compatible",
            explanation_api_key="runtime-test-key",
            explanation_model="runtime-overview-model",
            explanation_base_url="https://proxy.example.test/v1",
            demo_mode=True,
        )
        created = client.post(
            f"/api/v1/analyses/{analysis_id}/overview",
            json={"max_directions": 4},
        )
        assert created.status_code == 202
        current = _wait_overview(created.json()["id"])
        assert current["status"] in {"succeeded", "partial"}
        assert calls == [
            "plan:runtime-overview-model",
            "review:runtime-overview-model",
            "papers:runtime-overview-model",
            "synthesis:runtime-overview-model",
        ]
        warnings = current["result"]["warnings"]
        assert any(
            "TopicTaxonomyPlannerAgent=model:openai_compatible" in item
            for item in warnings
        )
        assert any(
            "OverviewSynthesisAgent=model:openai_compatible" in item
            for item in warnings
        )
    finally:
        app.dependency_overrides.clear()


def test_overview_save_is_idempotent_and_enters_graph_library() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        job = _wait_overview(overview_id)
        graph = job["result"]["graph"]
        assert job["result"]["direction_audits"]
        assert all(
            audit["queries"] and audit["provider"] and audit["decision"]
            for audit in job["result"]["direction_audits"]
        )
        root_detail = client.get(
            f"/api/v1/overviews/{overview_id}/nodes/{graph['root_id']}"
        )
        assert root_detail.status_code == 200
        assert root_detail.json()["node"]["id"] == graph["root_id"]

        saved = client.post(
            f"/api/v1/overviews/{overview_id}/save",
            json={"expected_version": graph["version"], "name": "Attention 研究地图"},
        )
        assert saved.status_code == 200
        assert saved.json()["save_state"] == "saved"
        assert saved.json()["graph"]["name"] == "Attention 研究地图"
        graph_id = saved.json()["saved_graph_id"]
        assert client.get(f"/api/v1/graphs/{graph_id}").status_code == 200

        retry = client.post(f"/api/v1/overviews/{overview_id}/save", json={})
        assert retry.status_code == 200
        assert retry.json()["saved_graph_id"] == graph_id
        matching = [
            item for item in client.get("/api/v1/graphs").json() if item["id"] == graph_id
        ]
        assert len(matching) == 1
    finally:
        app.dependency_overrides.clear()


def test_overview_expand_direction_keeps_papers_as_leaves() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        job = _wait_overview(overview_id)
        graph = job["result"]["graph"]
        method_ids = {
            node["id"] for node in graph["nodes"] if node["role"] == "method"
        }
        direct_paper_method = next(
            (
                edge["source"]
                for edge in graph["edges"]
                if edge["source"] in method_ids
                and next(node for node in graph["nodes"] if node["id"] == edge["target"])["role"]
                == "paper"
            ),
            None,
        )
        # The first-principles builder emits root -> problem -> method -> paper.
        # A method route can be refined once more while papers remain leaves.
        target = direct_paper_method or next(
            node["id"]
            for node in graph["nodes"]
            if node["role"] == "method"
            and any(
                edge["source"] == node["id"]
                and next(item for item in graph["nodes"] if item["id"] == edge["target"])["role"]
                == "paper"
                for edge in graph["edges"]
            )
        )
        expanded = client.post(
            f"/api/v1/overviews/{overview_id}/expand",
            json={"node_id": target, "expected_version": graph["version"]},
        )
        # depth 2 -> new direction at depth 3 is allowed under max_depth=3.
        assert expanded.status_code == 200
        new_graph = expanded.json()["result"]["graph"]
        assert any(
            audit["operation"] == "expand"
            for audit in expanded.json()["result"]["direction_audits"]
        )
        assert new_graph["version"] == graph["version"] + 1
        node_by_id = {node["id"]: node for node in new_graph["nodes"]}
        outgoing = {node_id: [] for node_id in node_by_id}
        for edge in new_graph["edges"]:
            outgoing[edge["source"]].append(edge["target"])
        assert all(not outgoing[node_id] for node_id, node in node_by_id.items() if node["role"] == "paper")

        conflict = client.post(
            f"/api/v1/overviews/{overview_id}/expand",
            json={"node_id": target, "expected_version": graph["version"]},
        )
        assert conflict.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_overview_resave_after_expansion_updates_graph_library() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        completed = _wait_overview(overview_id)
        assert completed["status"] in {"succeeded", "partial"}
        graph = completed["result"]["graph"]
        first_save = client.post(
            f"/api/v1/overviews/{overview_id}/save",
            json={"expected_version": graph["version"]},
        )
        assert first_save.status_code == 200
        saved_graph = first_save.json()["graph"]

        node_by_id = {node["id"]: node for node in graph["nodes"]}
        target = next(
            edge["source"]
            for edge in graph["edges"]
            if node_by_id[edge["source"]]["role"] == "method"
            and node_by_id[edge["target"]]["role"] == "paper"
        )
        expanded = client.post(
            f"/api/v1/overviews/{overview_id}/expand",
            json={"node_id": target, "expected_version": graph["version"]},
        )
        assert expanded.status_code == 200
        expanded_graph = expanded.json()["result"]["graph"]
        assert len(expanded_graph["nodes"]) > len(graph["nodes"])
        assert expanded.json()["save_state"] == "transient"

        second_save = client.post(
            f"/api/v1/overviews/{overview_id}/save",
            json={"expected_version": expanded_graph["version"]},
        )
        assert second_save.status_code == 200
        library = client.get(f"/api/v1/graphs/{saved_graph['id']}")
        assert library.status_code == 200
        assert len(library.json()["nodes"]) == len(expanded_graph["nodes"])
        assert library.json()["version"] > saved_graph["version"]
    finally:
        app.dependency_overrides.clear()


def test_overview_rejects_quick_analysis_and_missing_analysis() -> None:
    try:
        analysis_id = _completed_analysis(level="quick")
        quick = client.post(f"/api/v1/analyses/{analysis_id}/overview", json={})
        assert quick.status_code == 409
        missing = client.post(
            "/api/v1/analyses/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/overview", json={}
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_overview_storage_restart_marks_unfinished_jobs_interrupted(tmp_path) -> None:
    isolated = Storage(str(tmp_path / "overview.db"))
    root_graph = ConceptGraph(
        root_id="root",
        nodes=[ConceptNode(id="root", label="Topic")],
    )
    result = AnalysisResult(
        id="11111111-1111-1111-1111-111111111111",
        concept="Topic",
        level="literature",
        audience="beginner",
        provider="test",
        papers=[
            PaperRecord(
                id="paper-1",
                title="Tool-using agent",
                abstract="We propose a tool-using agent framework.",
                source="test",
            )
        ],
        evidence=[
            EvidenceCard(
                paper_id="paper-1",
                claim="method",
                excerpt="We propose a tool-using agent framework.",
            )
        ],
        explanation=ExplanationResult(
            one_sentence="Topic.", intuitive="Topic.", technical="Topic."
        ),
        graph=root_graph,
    )
    analysis = AnalysisJob(
        id="11111111-1111-1111-1111-111111111111",
        concept="Topic",
        level="literature",
        audience="beginner",
        status="completed",
        progress=100,
        result=result,
    )
    isolated.save_analysis(analysis)
    from app.research_schemas import OverviewJob

    job = OverviewJob(analysis_id=analysis.id, status="running", progress=50)
    isolated.save_overview(job)
    assert isolated.mark_unfinished_overviews_interrupted() == 1
    restored = isolated.get_overview(str(job.id))
    assert restored is not None
    assert restored.status == "interrupted"

    partial = job.model_copy(
        update={
            "id": UUID("22222222-2222-2222-2222-222222222222"),
            "status": "partial",
            "progress": 100,
            "stage": "completed",
        }
    )
    isolated.save_overview(partial)
    assert isolated.mark_unfinished_overviews_interrupted() == 0
    restored_partial = isolated.get_overview(str(partial.id))
    assert restored_partial is not None
    assert restored_partial.status == "partial"
    isolated.close()


def test_overview_history_list_recovers_terminal_jobs() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        completed = _wait_overview(overview_id)
        assert completed["status"] in {"succeeded", "partial"}

        history = client.get("/api/v1/overviews")
        assert history.status_code == 200
        assert any(item["id"] == overview_id for item in history.json())

        filtered = client.get(
            "/api/v1/overviews", params={"analysis_id": analysis_id}
        )
        assert filtered.status_code == 200
        assert [item["id"] for item in filtered.json()] == [overview_id]
    finally:
        app.dependency_overrides.clear()


def test_overview_delete_removes_history_but_keeps_saved_graph() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        completed = _wait_overview(overview_id)
        assert completed["status"] in {"succeeded", "partial"}
        graph = completed["result"]["graph"]

        saved = client.post(
            f"/api/v1/overviews/{overview_id}/save",
            json={"expected_version": graph["version"]},
        )
        assert saved.status_code == 200
        graph_id = saved.json()["saved_graph_id"]

        deleted = client.delete(f"/api/v1/overviews/{overview_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/overviews/{overview_id}").status_code == 404
        history = client.get("/api/v1/overviews")
        assert history.status_code == 200
        assert all(item["id"] != overview_id for item in history.json())
        # The graph-library copy is independently managed in the Concept Graph
        # page, so deleting an Overview history task must not remove it.
        assert client.get(f"/api/v1/graphs/{graph_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_overview_idea_generation_uses_graph_context_and_persists_brief(
    monkeypatch,
) -> None:
    """A completed direction map can drive the reusable multi-agent Idea flow."""

    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        completed = _wait_overview(overview_id)
        assert completed["status"] in {"succeeded", "partial"}

        # The Idea scope check is always arXiv in production.  Use a bounded
        # local provider here so this API test remains fully offline.
        monkeypatch.setattr(
            overview_module,
            "build_search_provider",
            lambda *args, **kwargs: DemoSearchProvider(),
        )
        app.dependency_overrides[get_settings] = lambda: Settings(
            paper_provider="demo",
            community_provider="demo",
            explanation_provider="rule_based",
            demo_mode=True,
        )

        response = client.post(f"/api/v1/overviews/{overview_id}/ideas")
        assert response.status_code == 200
        result = response.json()["result"]
        brief = result["idea_brief"]
        assert brief is not None
        assert brief["innovation_candidates"]
        assert {run["role"] for run in brief["agent_runs"]} >= {
            "community",
            "model_brainstorm",
            "future_work",
            "synthesis",
        }

        # Reopening the same durable overview must show the exact audit trail
        # and de-duplicated candidates without recomputing it.
        restored = client.get(f"/api/v1/overviews/{overview_id}")
        assert restored.status_code == 200
        restored_brief = restored.json()["result"]["idea_brief"]
        assert restored_brief["id"] == brief["id"]
        assert restored_brief["innovation_candidates"] == brief["innovation_candidates"]
    finally:
        app.dependency_overrides.clear()


class _RecordingDirectionProvider:
    name = "test_direction"

    def __init__(self, *, fail_term: str | None = None, delay: float = 0.015) -> None:
        self.fail_term = fail_term
        self.delay = delay
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        with self._lock:
            self.calls.append(concept)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if self.fail_term and self.fail_term in concept:
                raise ProviderUnavailable("test direction unavailable")
            normalized = concept.casefold()
            if "efficient" in normalized:
                return [
                    PaperRecord(
                        id="arxiv:2401.00001v1",
                        canonical_id="arxiv:2401.00001",
                        arxiv_id="2401.00001",
                        title="Efficient Agent Inference with KV Cache Management",
                        abstract=(
                            "We present an efficient agent inference system. "
                            "It uses KV cache management to reduce memory and latency."
                        ),
                        source="test",
                        source_kind="academic",
                        access_type="open_access",
                    )
                ]
            if "reasoning" in normalized:
                return [
                    PaperRecord(
                        id="arxiv:2402.00002v1",
                        canonical_id="arxiv:2402.00002",
                        arxiv_id="2402.00002",
                        title="Agent Reasoning through Planning and Reflection",
                        abstract=(
                            "We propose an agent reasoning method. "
                            "The agent uses planning and reflection to correct decisions."
                        ),
                        source="test",
                        source_kind="academic",
                        access_type="open_access",
                    )
                ]
            return []
        finally:
            with self._lock:
                self.active -= 1


def _agent_seed_papers() -> list[PaperRecord]:
    return [
        PaperRecord(
            id="seed-efficiency",
            title="Efficient Agent Serving",
            abstract="Agent serving reduces inference latency and memory using a cache.",
            source="test",
            source_kind="academic",
        ),
        PaperRecord(
            id="seed-reasoning",
            title="Planning and Reflection for Agents",
            abstract="Agent reasoning uses planning and reflection for decisions.",
            source="test",
            source_kind="academic",
        ),
        PaperRecord(
            id="seed-tools",
            title="Tool Use by Autonomous Agents",
            abstract="An agent workflow performs function calling and tool use.",
            source="test",
            source_kind="academic",
        ),
    ]


def test_direction_pipeline_shares_one_provider_bounds_concurrency_and_audits() -> None:
    provider = _RecordingDirectionProvider()
    seeds = _agent_seed_papers()
    plans = TopicTaxonomyPlanner().plan(
        "agent",
        seeds,
        ["agent efficiency", "agent reasoning"],
        max_directions=4,
    )
    assert 1 <= len(plans) <= 4
    result = DirectionResearchCoordinator(
        provider,
        max_concurrency=4,
        minimum_interval_seconds=0,
    ).research(
        plans,
        seeds,
        papers_per_direction=4,
        max_total_papers=12,
    )

    assert len(provider.calls) == len(plans)
    assert 2 <= provider.max_active <= 4
    assert result.provider_name == "test_direction"
    assert result.partial is False
    assert all(item.decision in {"split", "keep", "merge", "discard"} for item in result.decisions)
    assert all(item.reason for item in result.decisions)
    audit = result.audit_lines()
    assert len(audit) == len(plans)
    assert all("decision=" in item and "检索词=" in item and "接纳=" in item for item in audit)
    assert len({paper.id for paper in result.papers}) == len(result.papers)
    assert len(result.papers) <= 12


def test_direction_pipeline_preserves_successful_results_as_partial() -> None:
    provider = _RecordingDirectionProvider(fail_term="reasoning")
    seeds = _agent_seed_papers()
    plans = TopicTaxonomyPlanner().plan(
        "agent",
        seeds,
        ["agent efficiency", "agent reasoning"],
        max_directions=4,
    )
    result = DirectionResearchCoordinator(
        provider,
        max_concurrency=4,
        minimum_interval_seconds=0,
    ).research(
        plans,
        seeds,
        papers_per_direction=4,
        max_total_papers=12,
    )

    assert result.partial is True
    assert any(outcome.error for outcome in result.outcomes)
    assert any(not outcome.error for outcome in result.outcomes)
    assert result.papers
    assert any("partial" in warning for warning in result.warnings)
    assert any("error=ProviderUnavailable: provider unavailable" in item for item in result.audit_lines())


def test_open_arxiv_section_reader_extracts_sections_and_upgrades_scope() -> None:
    text = """
1 Introduction
Existing agent systems face a costly memory and latency problem during long inference.
We propose CacheAgent to address this problem with a bounded cache design.

2 Method
Our method uses fixed-size cache pages and a scheduler to reuse agent context safely.
The architecture consists of a cache manager and an inference worker.

3 Experiments
We evaluate the system on long-context agent tasks and report latency measurements.

4 Discussion
A limitation is that cache eviction may lose useful context. Future work should learn eviction policies.

5 Conclusion
CacheAgent reduces memory movement through paged context management.
"""
    reader = OpenArxivSectionReader(
        downloader=lambda url: b"%PDF-test",
        text_extractor=lambda payload: text,
    )
    paper = PaperRecord(
        id="arxiv:2401.00001v2",
        arxiv_id="2401.00001",
        title="CacheAgent",
        abstract="We propose CacheAgent for efficient inference.",
        url="https://arxiv.org/abs/2401.00001",
        source="arxiv",
        source_kind="academic",
        access_type="open_access",
    )
    extracted = reader.read(paper)
    assert extracted.attempted is True
    assert set(extracted.sections) >= {"Introduction", "Method", "Experiment", "Discussion", "Conclusion"}
    assert extracted.pdf_url == "https://arxiv.org/pdf/2401.00001.pdf"

    section_evidence = overview_module._section_evidence_cards(
        paper,
        extracted.sections,
        pdf_url=extracted.pdf_url,
    )
    reading = _read_paper_sections(
        paper,
        [],
        extracted.sections,
        list(extracted.warnings),
        section_evidence=section_evidence,
    )
    assert reading.summary_level == "arxiv_sections"
    assert "Introduction" in reading.source_sections
    assert "Method" in reading.source_sections
    assert "memory" in reading.problem.casefold()
    assert "cache" in reading.method.casefold()
    assert reading.section_evidence
    assert all(card.locator and card.locator.kind == "section" for card in reading.section_evidence)
    assert all(card.verification_status == "unverified" for card in reading.section_evidence)
    assert all(card.locator.page is None for card in reading.section_evidence)
    assert any("未进行 OCR" in warning for warning in reading.warnings)


def test_open_arxiv_section_reader_falls_back_without_claiming_full_text() -> None:
    def fail_download(url: str) -> bytes:
        raise TimeoutError("30 second test timeout")

    reader = OpenArxivSectionReader(downloader=fail_download)
    paper = PaperRecord(
        id="arxiv:2401.00001",
        arxiv_id="2401.00001",
        title="CacheAgent",
        abstract="We propose CacheAgent. It uses cache pages for inference.",
        url="https://arxiv.org/abs/2401.00001",
        source="arxiv",
        source_kind="academic",
        access_type="open_access",
    )
    extracted = reader.read(paper)
    assert extracted.attempted is True
    assert extracted.sections == {}
    assert any("退回摘要级" in warning for warning in extracted.warnings)

    fallback = _read_paper_abstract(paper, [])
    fallback = fallback.model_copy(
        update={"warnings": [*fallback.warnings, *extracted.warnings]}
    )
    assert fallback.summary_level == "abstract_only"
    assert fallback.source_sections == ["Abstract"]
    assert any("未验证论文正文" in warning for warning in fallback.warnings)


def test_pypdf_extraction_has_hard_timeout(monkeypatch) -> None:
    reader = OpenArxivSectionReader()
    original_import = importlib.import_module

    class SlowPage:
        def extract_text(self) -> str:
            time.sleep(0.05)
            return "late text"

    class FakePdf:
        class PdfReader:
            def __init__(self, _stream) -> None:
                self.pages = [SlowPage()]

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: FakePdf if name == "pypdf" else original_import(name),
    )
    monkeypatch.setattr(reader, "EXTRACT_TIMEOUT_SECONDS", 0.005)
    started = time.perf_counter()
    try:
        reader._extract_text(b"%PDF-timeout-test")
    except TimeoutError as exc:
        assert "抽取超过" in str(exc)
    else:
        raise AssertionError("pypdf extraction should have timed out")
    assert time.perf_counter() - started < 0.04


def test_overview_service_finishes_partial_and_keeps_successful_graph(monkeypatch) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))
    assert analysis.result is not None

    class PartialProvider(_RecordingDirectionProvider):
        name = "demo"

        def search(self, concept: str, limit: int) -> list[PaperRecord]:
            if "efficient" in concept.casefold():
                raise ProviderUnavailable("one direction failed")
            return super().search(concept, limit)

    provider = PartialProvider(delay=0)
    monkeypatch.setattr(
        overview_module,
        "build_search_provider",
        lambda provider_name: provider,
    )
    # Keep this integration test offline: its purpose is durable partial state,
    # while PDF success/fallback is covered by the isolated reader tests above.
    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(attempted=False),
    )
    service = overview_module.overview_service
    job = service.create(analysis.id, OverviewCreate(force_regenerate=True, max_directions=4))
    for _ in range(500):
        current = service.get(job.id)
        if current.status in {"partial", "succeeded", "failed"} and current.stage == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("partial overview did not finish")

    assert current.status == "partial"
    assert current.progress == 100
    assert current.result is not None
    assert current.result.paper_count >= 1
    assert current.result.graph.nodes
    assert any(
        "方向审计" in warning
        and "error=ProviderUnavailable: provider unavailable" in warning
        for warning in current.result.warnings
    )


def test_overview_falls_back_when_enriched_graph_fails_validation(monkeypatch) -> None:
    """An invalid live enrichment must not erase the already valid analysis."""

    analysis_id = _completed_analysis()
    original_builder = overview_module._build_overview_result

    def fail_only_for_enriched_graph(job, analysis_result, *, pipeline=None, **kwargs):
        if pipeline is not None:
            raise ValidationError.from_exception_data(
                "ConceptNode",
                [{
                    "type": "string_too_long",
                    "loc": ("nodes", 1, "explanation"),
                    "msg": "String should have at most 5000 characters",
                    "input": "omitted",
                    "ctx": {"max_length": 5000},
                }],
            )
        return original_builder(job, analysis_result, pipeline=pipeline, **kwargs)

    monkeypatch.setattr(
        overview_module,
        "_build_overview_result",
        fail_only_for_enriched_graph,
    )
    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(attempted=False),
    )

    job = overview_module.overview_service.create(
        UUID(analysis_id),
        OverviewCreate(force_regenerate=True, max_directions=2),
    )
    for _ in range(500):
        current = overview_module.overview_service.get(job.id)
        if current.status in {"partial", "succeeded", "failed"} and current.stage == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("fallback overview did not finish")

    assert current.status == "partial"
    assert current.error is None
    assert current.result is not None
    assert current.result.graph.nodes
    assert any("已回退为基于原分析论文" in item for item in current.result.warnings)
    validation_runs = [
        item for item in current.result.agent_runs if item.role == "direction_validation"
    ]
    assert validation_runs and validation_runs[-1].status == "failed"


def test_overview_persists_structured_direction_audits() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        job = _wait_overview(overview_id)
        audits = job["result"]["direction_audits"]
        assert audits
        assert all(item["provider"] for item in audits)
        assert all(item["queries"] for item in audits)
        assert all(item["query_scope"] in {
            "external_provider", "retained_analysis", "unavailable"
        } for item in audits)
        assert all(item["returned_count"] >= 0 for item in audits)
        assert all(item["accepted_count"] >= 0 for item in audits)
        assert all(item["rejected_count"] >= 0 for item in audits)
        assert all(item["decision"] in {"split", "keep", "merge", "discard"} for item in audits)
        assert all(item["decision_reason"] for item in audits)

        restored = Storage(storage.path).get_overview(overview_id)
        assert restored is not None and restored.result is not None
        assert len(restored.result.direction_audits) == len(audits)
    finally:
        app.dependency_overrides.clear()


def test_overview_persists_secret_free_structured_agent_runs() -> None:
    try:
        analysis_id = _completed_analysis()
        overview_id = client.post(
            f"/api/v1/analyses/{analysis_id}/overview", json={}
        ).json()["id"]
        job = _wait_overview(overview_id)
        runs = job["result"]["agent_runs"]
        assert runs

        roles = {item["role"] for item in runs}
        assert {
            "topic_taxonomy_planner",
            "direction_research_coordinator",
            "direction_research_worker",
            "direction_review_worker",
            "paper_reading",
            "direction_validation",
            "overview_synthesis",
        } <= roles
        assert all(item["provider"] for item in runs)
        assert all(item["summary"] for item in runs)
        assert all(item["duration_ms"] >= 0 for item in runs)
        assert all(item["started_at"] <= item["completed_at"] for item in runs)
        assert len(
            [item for item in runs if item["role"] == "direction_research_worker"]
        ) == len(job["result"]["direction_audits"])
        assert all(
            item["model"] is None
            for item in runs
            if item["execution_mode"] != "model"
        )

        planner = [item for item in runs if item["role"] == "topic_taxonomy_planner"]
        synthesis = [item for item in runs if item["role"] == "overview_synthesis"]
        assert [item["execution_mode"] for item in planner] == ["deterministic_rule"]
        assert [item["execution_mode"] for item in synthesis] == ["deterministic_rule"]
        assert all(item["provider"] != "rule_based_fallback" for item in planner + synthesis)

        serialized = str(runs).casefold()
        assert "api_key" not in serialized
        assert "authorization" not in serialized
        assert "bearer " not in serialized
        assert "base_url" not in serialized

        restored = Storage(storage.path).get_overview(overview_id)
        assert restored is not None and restored.result is not None
        assert len(restored.result.agent_runs) == len(runs)
    finally:
        app.dependency_overrides.clear()


def test_model_direction_review_cannot_add_or_duplicate_papers() -> None:
    baseline = overview_module.DirectionExpansionDecision(
        direction_key="agent-memory",
        decision="split",
        reason="deterministic baseline",
        paper_ids=["p1", "p2", "p3"],
        subgroups={"baseline": ["p1", "p2", "p3"]},
        subgroup_labels={"baseline": "基线路线"},
    )
    reviewed = overview_module._validated_direction_review(
        {
            "decision": "split",
            "reason": "模型认为存在不同机制。",
            "method_routes": [
                {"key": "route-a", "label": "路线 A", "paper_ids": ["p1", "forged"]},
                {"key": "route-b", "label": "路线 B", "paper_ids": ["p1", "p2"]},
            ],
        },
        baseline,
    )

    assert reviewed is not None
    flattened = [paper_id for ids in reviewed.subgroups.values() for paper_id in ids]
    assert set(flattened) == {"p1", "p2", "p3"}
    assert len(flattened) == len(set(flattened))
    assert "forged" not in flattened


def test_model_paper_summary_preserves_source_scope_and_rejects_unknown_ids() -> None:
    paper = PaperRecord(
        id="known-paper",
        canonical_id="known-paper",
        title="Known Paper",
        abstract="We address an expensive memory problem. We propose a cache method. We do so by paging state.",
        source="arxiv",
        source_kind="academic",
    )
    original = _read_paper_abstract(paper, [])
    validated = overview_module._validated_model_paper_summaries(
        {
            "papers": [
                {
                    "paper_id": "known-paper",
                    "problem": "降低长程记忆检索成本。",
                    "method": "提出分页式缓存方法。",
                    "how_it_works": "按需换入相关状态并复用缓存页。",
                    "limitations": "",
                },
                {
                    "paper_id": "forged-paper",
                    "problem": "伪造问题",
                    "method": "伪造方法",
                    "how_it_works": "伪造过程",
                },
            ]
        },
        [original],
    )

    assert set(validated) == {"known-paper"}
    assert validated["known-paper"].summary_level == original.summary_level
    assert validated["known-paper"].source_sections == original.source_sections
    assert validated["known-paper"].evidence_ids == original.evidence_ids
    assert any("仅结合摘要" in warning for warning in validated["known-paper"].warnings)


def test_overview_agent_runs_distinguish_model_success_from_rule_work(monkeypatch) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))

    class RecordingModelProvider:
        name = "test_model_provider"
        model = "safe-test-model"

        def plan_research_directions(self, topic, papers, prior_queries, *, max_directions):
            return [
                {
                    "key": "attention",
                    "label": "Attention 方法",
                    "definition": "研究注意力机制的方法设计。",
                    "boundary": "不包含没有 attention 证据的论文。",
                    "query_terms": ["attention mechanism"],
                    "match_terms": ["attention", "mechanism"],
                    "seed_paper_ids": [paper.id for paper in papers],
                }
            ]

        def synthesize_research_overview(self, topic, directions, paper_summaries):
            return {
                "title": "模型综合后的 Attention 方向图",
                "root_explanation": "只综合已验证的方向与论文。",
                "direction_explanations": {"attention": "注意力方法方向。"},
            }

        def review_research_direction(self, topic, direction, papers):
            return {
                "decision": "keep",
                "reason": "当前论文属于一条核心方法路线。",
                "method_routes": [
                    {
                        "key": "core",
                        "label": "核心注意力方法",
                        "paper_ids": [paper.id for paper in papers],
                    }
                ],
            }

        def summarize_research_papers(self, topic, direction, papers):
            return {
                "papers": [
                    {
                        "paper_id": paper["paper_id"],
                        "problem": paper["deterministic_extract"]["problem"],
                        "method": paper["deterministic_extract"]["method"],
                        "how_it_works": paper["deterministic_extract"]["how_it_works"],
                        "limitations": "",
                    }
                    for paper in papers
                ]
            }

    monkeypatch.setattr(
        overview_module,
        "_explanation_provider",
        lambda settings: RecordingModelProvider(),
    )
    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(attempted=False),
    )

    job = overview_module.overview_service.create(
        analysis.id,
        OverviewCreate(force_regenerate=True, max_directions=1),
    )
    for _ in range(500):
        current = overview_module.overview_service.get(job.id)
        if current.status in {"partial", "succeeded", "failed"} and current.stage == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("model-backed overview did not finish")

    assert current.result is not None
    model_runs = [
        item for item in current.result.agent_runs if item.execution_mode == "model"
    ]
    assert {(item.role, item.status) for item in model_runs} == {
        ("topic_taxonomy_planner", "succeeded"),
        ("direction_review_worker", "succeeded"),
        ("paper_reading", "succeeded"),
        ("overview_synthesis", "succeeded"),
    }
    assert all(item.provider == "test_model_provider" for item in model_runs)
    assert all(item.model == "safe-test-model" for item in model_runs)
    assert not any(
        item.execution_mode == "deterministic_rule_fallback"
        and item.role in {"topic_taxonomy_planner", "overview_synthesis"}
        for item in current.result.agent_runs
    )


def test_overview_agent_runs_record_failed_model_attempt_and_fallback(monkeypatch) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))

    class FailingModelProvider:
        name = "test_model_provider"
        model = "safe-test-model"
        api_key = "must-never-be-persisted"
        base_url = "https://proxy.example.test/v1?secret=must-never-be-persisted"

        def plan_research_directions(self, *args, **kwargs):
            raise ProviderUnavailable("Bearer must-never-be-persisted")

        def synthesize_research_overview(self, *args, **kwargs):
            raise ProviderUnavailable("https://proxy.example.test/?secret=must-never-be-persisted")

    monkeypatch.setattr(
        overview_module,
        "_explanation_provider",
        lambda settings: FailingModelProvider(),
    )
    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(attempted=False),
    )

    job = overview_module.overview_service.create(
        analysis.id,
        OverviewCreate(force_regenerate=True, max_directions=2),
    )
    for _ in range(500):
        current = overview_module.overview_service.get(job.id)
        if current.status in {"partial", "succeeded", "failed"} and current.stage == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("fallback overview did not finish")

    assert current.result is not None
    for role in ("topic_taxonomy_planner", "overview_synthesis"):
        role_runs = [item for item in current.result.agent_runs if item.role == role]
        assert [(item.execution_mode, item.status) for item in role_runs] == [
            ("model", "failed"),
            ("deterministic_rule_fallback", "succeeded"),
        ]
        assert role_runs[0].model == "safe-test-model"
        assert role_runs[1].model is None

    serialized = current.result.model_dump_json().casefold()
    assert "must-never-be-persisted" not in serialized
    assert "proxy.example.test" not in serialized
    assert "bearer " not in serialized


def test_overview_agent_runs_treat_empty_model_synthesis_as_failed_output(monkeypatch) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))

    class EmptySynthesisProvider:
        name = "test_model_provider"
        model = "safe-test-model"

        def plan_research_directions(self, *args, **kwargs):
            return []

        def synthesize_research_overview(self, *args, **kwargs):
            return {}

    monkeypatch.setattr(
        overview_module,
        "_explanation_provider",
        lambda settings: EmptySynthesisProvider(),
    )
    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(attempted=False),
    )

    job = overview_module.overview_service.create(
        analysis.id,
        OverviewCreate(force_regenerate=True, max_directions=2),
    )
    for _ in range(500):
        current = overview_module.overview_service.get(job.id)
        if current.status in {"partial", "succeeded", "failed"} and current.stage == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("empty-model-output overview did not finish")

    assert current.result is not None
    synthesis_runs = [
        item for item in current.result.agent_runs if item.role == "overview_synthesis"
    ]
    assert [(item.execution_mode, item.status) for item in synthesis_runs] == [
        ("model", "failed"),
        ("deterministic_rule_fallback", "succeeded"),
    ]
    assert synthesis_runs[0].error_type == "ValueError"


def test_overview_agent_run_schema_rejects_model_name_on_non_model_run() -> None:
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from app.research_schemas import OverviewAgentRun

    now = datetime.now(timezone.utc)
    try:
        OverviewAgentRun(
            role="paper_reading",
            status="succeeded",
            execution_mode="document_parser",
            provider="local_parser",
            model="fabricated-model",
            started_at=now,
            completed_at=now,
            duration_ms=0,
        )
    except ValidationError as exc:
        assert "只有真实模型调用记录" in str(exc)
    else:
        raise AssertionError("non-model audit must not carry a model identifier")


def test_pdf_section_evidence_is_persisted_and_returned_by_overview_inspector(
    monkeypatch,
) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))
    assert analysis.result is not None

    monkeypatch.setattr(
        OpenArxivSectionReader,
        "read",
        lambda self, paper: SectionReadResult(
            attempted=True,
            sections={
                "Introduction": "Existing systems face a memory bottleneck. We study this problem.",
                "Method": "Our method uses bounded cache pages to reuse context safely.",
            },
            pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
        ),
    )
    job = overview_module.overview_service.create(
        analysis.id,
        OverviewCreate(force_regenerate=True, max_directions=4),
    )
    current = _wait_overview(str(job.id))
    assert current["status"] in {"succeeded", "partial"}
    paper_node = next(
        node for node in current["result"]["graph"]["nodes"]
        if node["role"] == "paper" and node["summary_level"] == "arxiv_sections"
    )
    detail = client.get(
        f"/api/v1/overviews/{job.id}/nodes/{paper_node['id']}"
    )
    assert detail.status_code == 200
    section_cards = [
        card for card in detail.json()["evidence"]
        if card["locator"] and card["locator"]["kind"] == "section"
    ]
    assert section_cards
    assert all(card["excerpt"] for card in section_cards)
    assert all(card["locator"]["section"] in {"Introduction", "Method"} for card in section_cards)
    assert all(card["locator"]["url"].startswith("https://arxiv.org/pdf/") for card in section_cards)
    assert all(card["locator"]["page"] is None for card in section_cards)
    assert all(card["locator"]["paragraph"] is None for card in section_cards)

    saved = client.post(
        f"/api/v1/overviews/{job.id}/save",
        json={"expected_version": current["result"]["graph"]["version"]},
    )
    assert saved.status_code == 200
    graph_id = saved.json()["saved_graph_id"]
    saved_detail = client.get(
        f"/api/v1/graphs/{graph_id}/nodes/{paper_node['id']}"
    )
    assert saved_detail.status_code == 200
    saved_sections = [
        card for card in saved_detail.json()["evidence"]
        if card["locator"] and card["locator"]["kind"] == "section"
    ]
    assert {card["id"] for card in saved_sections} == {card["id"] for card in section_cards}

    deleted = client.delete(
        f"/api/v1/graphs/{graph_id}",
        params={"expected_version": saved.json()["graph"]["version"]},
    )
    assert deleted.status_code == 204
    restored = client.get(f"/api/v1/overviews/{job.id}")
    assert restored.status_code == 200
    assert restored.json()["save_state"] == "transient"
    assert restored.json()["saved_graph_id"] is None
    assert restored.json()["result"]["graph"]["save_state"] == "transient"


def test_expand_uses_direction_provider_and_respects_total_bound(monkeypatch) -> None:
    try:
        analysis_id = _completed_analysis()
        provider = _RecordingDirectionProvider(delay=0)
        monkeypatch.setattr(overview_module, "build_search_provider", lambda _: provider)
        monkeypatch.setattr(
            OpenArxivSectionReader,
            "read",
            lambda self, paper: SectionReadResult(attempted=False),
        )
        job = overview_module.overview_service.create(
            UUID(analysis_id),
            OverviewCreate(
                force_regenerate=True,
                max_directions=4,
                papers_per_direction=4,
                max_total_papers=8,
            ),
        )
        current = _wait_overview(str(job.id))
        graph = current["result"]["graph"]
        methods = {node["id"]: node for node in graph["nodes"] if node["role"] == "method"}
        target = next(
            edge["source"] for edge in graph["edges"]
            if edge["source"] in methods
            and next(node for node in graph["nodes"] if node["id"] == edge["target"])["role"] == "paper"
        )
        before_calls = len(provider.calls)
        expanded = client.post(
            f"/api/v1/overviews/{job.id}/expand",
            json={"node_id": target, "expected_version": graph["version"]},
        )
        assert expanded.status_code == 200
        payload = expanded.json()
        assert len(provider.calls) > before_calls
        assert payload["result"]["paper_count"] <= 8
        audit = payload["result"]["direction_audits"][-1]
        assert audit["operation"] == "expand"
        assert audit["provider"] == provider.name
        assert audit["returned_count"] >= audit["accepted_count"] - len(audit["seed_paper_ids"])
    finally:
        app.dependency_overrides.clear()


def test_retry_failed_direction_runs_only_that_scope(monkeypatch) -> None:
    analysis_id = _completed_analysis()
    analysis = research_service.get(UUID(analysis_id))
    assert analysis.result is not None
    provider = _RecordingDirectionProvider(delay=0)
    monkeypatch.setattr(overview_module, "build_search_provider", lambda _: provider)
    graph = ConceptGraph(
        id="retry-overview-graph",
        graph_kind="research_direction",
        source_analysis_id=analysis_id,
        root_id="root",
        nodes=[
            ConceptNode(id="root", label="agent", role="root"),
            ConceptNode(id="direction-efficiency", label="效率", role="direction", node_type="direction"),
        ],
        edges=[
            overview_module.ConceptEdge(source="root", target="direction-efficiency", relation="is_a")
        ],
    )
    audit = OverviewDirectionAudit(
        direction_key="efficiency",
        direction_node_id="direction-efficiency",
        label="效率、推理与系统优化",
        definition="减少延迟和显存。",
        boundary="需要系统或计算开销证据。",
        provider="demo",
        query_scope="external_provider",
        queries=["agent efficient inference"],
        match_terms=["efficient", "agent", "cache"],
        decision="discard",
        decision_reason="首次检索失败。",
        error="temporary failure",
    )
    job = OverviewJob(
        analysis_id=analysis.id,
        status="partial",
        stage="completed",
        progress=100,
        request=OverviewCreate(max_total_papers=8, papers_per_direction=4),
        result=OverviewResult(graph=graph, direction_audits=[audit]),
    )
    storage.save_overview(job)
    response = client.post(
        f"/api/v1/overviews/{job.id}/directions/efficiency/retry",
        json={"expected_version": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert provider.calls == ["agent efficient inference"]
    latest = payload["result"]["direction_audits"][-1]
    assert latest["operation"] == "retry"
    assert latest["direction_key"] == "efficiency"
    assert latest["error"] is None
    assert payload["result"]["paper_count"] <= 8


def test_retry_rejects_direction_without_failed_audit() -> None:
    analysis_id = _completed_analysis()
    overview_id = client.post(
        f"/api/v1/analyses/{analysis_id}/overview", json={}
    ).json()["id"]
    current = _wait_overview(overview_id)
    direction_key = current["result"]["direction_audits"][0]["direction_key"]
    response = client.post(
        f"/api/v1/overviews/{overview_id}/directions/{direction_key}/retry",
        json={"expected_version": current["result"]["graph"]["version"]},
    )
    assert response.status_code == 409
