import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    ExplanationResult,
    GraphPatchCreate,
    PaperRecord,
    SearchQueryPlan,
)
from app.services.graph_service import GraphConflict, graph_service
from app.services.research_providers import (
    ArxivSearchProvider,
    OpenAICompatibleExplanationProvider,
)
from app.services.research_service import research_service
from app.services.settings_service import api_key_slots
from app.storage import Storage, storage

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_shell_is_served() -> None:
    page = client.get("/")
    stylesheet = client.get("/styles.css")
    app_script = client.get("/app.js")
    runtime_config = client.get("/runtime-config.js")
    legacy_stylesheet = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "WishForge" in page.text
    assert (
        "runtime-config.js" in page.text
        or "src/main.js" in page.text
        or "/assets/index-" in page.text
    )
    assert stylesheet.status_code == 200
    assert app_script.status_code == 200
    assert runtime_config.status_code == 200
    # The old path stays available for existing local bookmarks.
    assert legacy_stylesheet.status_code == 200


def test_create_and_list_project() -> None:
    payload = {
        "name": "标签噪声下的 Mixup 鲁棒性",
        "research_question": "Mixup 是否能提升标签噪声下的分类性能？",
    }

    created = client.post("/api/v1/projects", json=payload)
    assert created.status_code == 201
    assert created.json()["status"] == "draft"

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert len(projects.json()) == 1
    assert projects.json()[0]["name"] == payload["name"]


def test_project_validation() -> None:
    response = client.post(
        "/api/v1/projects",
        json={"name": "", "research_question": ""},
    )

    assert response.status_code == 422


def test_api_key_status_is_separated_and_masked() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="semantic_scholar",
        community_provider="official_api",
        explanation_provider="openai",
        experiment_provider="remote_runner",
        paper_api_key=SecretStr("paper-secret-1234"),
        community_api_key=SecretStr("community-secret-4321"),
        explanation_api_key=None,
        experiment_api_key=SecretStr("run-secret-5678"),
    )

    try:
        response = client.get("/api/v1/settings/api-keys")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["storage"] == "environment"
    slots = {slot["id"]: slot for slot in response.json()["slots"]}
    assert slots["paper_search"]["configured"] is True
    assert slots["paper_search"]["masked"] == "••••••••1234"
    assert slots["community_search"]["configured"] is True
    assert slots["community_search"]["masked"] == "••••••••4321"
    assert slots["experiment_runner"]["configured"] is True
    assert slots["experiment_runner"]["masked"] == "••••••••5678"
    assert slots["explanation_model"]["configured"] is False
    assert "paper-secret-1234" not in response.text
    assert "community-secret-4321" not in response.text
    assert "run-secret-5678" not in response.text


def test_settings_load_separate_environment_keys(monkeypatch) -> None:
    monkeypatch.setenv("WISHFORGE_PAPER_API_KEY", "paper-env-9999")
    monkeypatch.setenv("WISHFORGE_COMMUNITY_API_KEY", "community-env-7777")
    monkeypatch.setenv("WISHFORGE_EXPERIMENT_API_KEY", "runner-env-8888")

    # Read the environment variables set by this test, but do not let a
    # developer's repository-local .env leak a real explanation key into the
    # expected unconfigured slot.
    slots = {slot.id: slot for slot in api_key_slots(Settings(_env_file=None))}

    assert slots["paper_search"].configured is True
    assert slots["paper_search"].masked == "••••••••9999"
    assert slots["community_search"].configured is True
    assert slots["community_search"].masked == "••••••••7777"
    assert slots["experiment_runner"].configured is True
    assert slots["experiment_runner"].masked == "••••••••8888"
    assert slots["explanation_model"].configured is False


def test_concept_analysis_creates_evidence_and_graph() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        community_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={
                "concept": "Attention Mechanism",
                "level": "literature",
                "audience": "beginner",
                "max_papers": 4,
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]

        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break

        assert job["status"] == "completed"
        result = job["result"]
        assert len(result["papers"]) == 2
        assert len(result["evidence"]) >= len(result["papers"])
        assert {item["evidence_type"] for item in result["evidence"]} & {"mechanism", "result", "limitation"}
        assert result["graph"]["root_id"] == "root"
        assert result["graph"]["name"] == "Attention Mechanism 概念图"
        assert result["graph"]["version"] == 1
        assert result["graph_save_state"] == "transient"
        assert result["graph"]["save_state"] == "transient"
        assert client.get(f"/api/v1/graphs/{result['graph']['id']}").status_code == 404
        assert result["evidence"][0]["locator"]["kind"] == "abstract"
        assert len(result["graph"]["nodes"]) >= 5
        labels = {node["label"] for node in result["graph"]["nodes"]}
        assert not {"是什么", "核心机制", "文献证据", "限制与空白"} & labels
        node_ids = [node["id"] for node in result["graph"]["nodes"]]
        assert len(node_ids) == len(set(node_ids))
        valid_node_ids = set(node_ids)
        assert all(edge["source"] in valid_node_ids and edge["target"] in valid_node_ids for edge in result["graph"]["edges"])
        paper_nodes = [node for node in result["graph"]["nodes"] if node["role"] == "paper"]
        assert paper_nodes and all(node["paper_id"] for node in paper_nodes)
        evidence_ids = {card["id"] for card in result["evidence"]}
        evidence_backed = [
            node for node in result["graph"]["nodes"]
            if node["role"] in {"method", "problem"} and node["summary_level"] != "model_inference"
        ]
        assert all(node["paper_ids"] or set(node["evidence_ids"]) & evidence_ids for node in evidence_backed)
        assert result["explanation"]["one_sentence"]
    finally:
        app.dependency_overrides.clear()


def test_literature_analysis_uses_model_query_planner_and_arxiv(monkeypatch) -> None:
    searched: list[str] = []

    def fake_plan(
        self: OpenAICompatibleExplanationProvider, concept: str, language: str
    ) -> list[SearchQueryPlan]:
        assert concept == "注意力机制"
        assert language == "zh-CN"
        return [
            SearchQueryPlan(query="attention mechanism", purpose="core"),
            SearchQueryPlan(query="neural sequence alignment", purpose="foundational"),
            SearchQueryPlan(query="efficient self attention", purpose="recent"),
        ]

    def fake_search(
        self: ArxivSearchProvider, concept: str, limit: int
    ) -> list[PaperRecord]:
        searched.append(concept)
        index = len(searched)
        return [
            PaperRecord(
                id="arxiv:1706.03762" if index == 1 else f"arxiv:test-{index}",
                arxiv_id="1706.03762" if index == 1 else f"test-{index}",
                title="Attention Is All You Need" if index == 1 else f"Retrieval Angle {index}",
                authors=["Ashish Vaswani"],
                year=2017,
                abstract="The Transformer is based solely on attention mechanisms.",
                url="https://arxiv.org/abs/1706.03762",
                source="arxiv",
                source_kind="academic",
                access_type="open_access",
            )
        ]

    def fake_followup(
        self: OpenAICompatibleExplanationProvider,
        concept: str,
        papers: list[PaperRecord],
        existing_queries: list[SearchQueryPlan],
        language: str,
    ) -> list[SearchQueryPlan]:
        assert papers
        assert len(existing_queries) == 3
        return [
            SearchQueryPlan(
                query="attention token pruning",
                purpose="method_family",
                phase="feedback",
                derived_from_paper_ids=[papers[0].id],
            )
        ]

    def fake_explain(
        self: OpenAICompatibleExplanationProvider,
        concept: str,
        papers: list[PaperRecord],
        evidence: list,
        audience: str,
        language: str,
    ) -> ExplanationResult:
        assert papers[0].source == "arxiv"
        return ExplanationResult(
            one_sentence="注意力机制让模型按相关性聚合信息。",
            intuitive="像阅读时关注关键句。",
            technical="通过查询、键和值计算权重。",
            evolution=["2017：Transformer 将自注意力作为核心结构。"],
            related_concepts=["Self-Attention", "Transformer"],
            limitations=["当前只核对摘要。"],
            evidence_ids=[item.id for item in evidence],
        )

    def fake_graph_plan(
        self: OpenAICompatibleExplanationProvider,
        concept: str,
        papers: list[PaperRecord],
        evidence: list,
        language: str,
    ) -> dict:
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(OpenAICompatibleExplanationProvider, "plan_search_queries", fake_plan)
    monkeypatch.setattr(OpenAICompatibleExplanationProvider, "plan_followup_queries", fake_followup)
    monkeypatch.setattr(OpenAICompatibleExplanationProvider, "explain", fake_explain)
    monkeypatch.setattr(OpenAICompatibleExplanationProvider, "plan_concept_graph", fake_graph_plan)
    monkeypatch.setattr(ArxivSearchProvider, "search", fake_search)
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="arxiv",
        explanation_provider="openai",
        explanation_api_key=SecretStr("model-key"),
        demo_mode=False,
        _env_file=None,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={
                "concept": "注意力机制",
                "level": "literature",
                "audience": "beginner",
                "max_papers": 3,
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(50):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break

        assert job["status"] == "completed"
        assert searched == [
            "attention mechanism",
            "neural sequence alignment",
            "efficient self attention",
            "attention token pruning",
        ]
        assert job["result"]["search_terms"] == searched
        assert job["result"]["provider"] == "search=arxiv; explanation=openai_compatible"
        assert job["result"]["papers"][0]["arxiv_id"] == "1706.03762"
        assert job["result"]["explanation"]["evolution"]
        assert job["result"]["explanation"]["evolution_items"]
        assert job["result"]["retrieval_queries"] == [
            {"query": "attention mechanism", "purpose": "core", "phase": "initial", "derived_from_paper_ids": []},
            {"query": "neural sequence alignment", "purpose": "foundational", "phase": "initial", "derived_from_paper_ids": []},
            {"query": "efficient self attention", "purpose": "recent", "phase": "initial", "derived_from_paper_ids": []},
            {
                "query": "attention token pruning",
                "purpose": "method_family",
                "phase": "feedback",
                "derived_from_paper_ids": ["arxiv:1706.03762"],
            },
        ]
        assert job["result"]["stage_timings"]
        assert job["result"]["total_duration_ms"] >= 0
        assert job["result"]["explanation"]["related_concepts"]
    finally:
        app.dependency_overrides.clear()


def test_agent_graph_patch_requires_user_apply() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "LoRA", "level": "literature", "max_papers": 1},
        )
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        graph = job["result"]["graph"]
        saved = client.post(
            f"/api/v1/analyses/{job_id}/graph/save",
            json={"expected_version": graph["version"]},
        )
        assert saved.status_code == 200
        graph = saved.json()["graph"]
        patch = client.post(
            f"/api/v1/graphs/{graph['id']}/patches",
            json={
                "actor": "agent",
                "reason": "补充相关方法",
                "operations": [
                    {
                        "op": "add_node",
                        "node": {
                            "id": "related-idea",
                            "label": "QLoRA",
                            "summary": "量化条件下的参数高效微调",
                            "node_type": "method",
                            "evidence_ids": [],
                            "editable": True,
                        },
                    },
                    {
                        "op": "add_edge",
                        "edge": {
                            "id": "root-related-idea",
                            "source": graph["root_id"],
                            "target": "related-idea",
                            "relation": "related_to",
                            "source_kind": "model_inference",
                        },
                    },
                ],
            },
        )
        assert patch.status_code == 200
        assert patch.json()["status"] == "proposed"
        # Existing clients may omit base_version; the service pins the
        # proposal to the graph version observed at creation time.
        assert patch.json()["base_version"] == graph["version"]
        patch_id = patch.json()["id"]

        applied = client.post(f"/api/v1/graphs/{graph['id']}/patches/{patch_id}/apply")
        assert applied.status_code == 200
        assert applied.json()["status"] == "applied"
        updated_graph = client.get(f"/api/v1/graphs/{graph['id']}").json()
        assert any(node["id"] == "related-idea" for node in updated_graph["nodes"])
        assert updated_graph["version"] == graph["version"] + 1
    finally:
        app.dependency_overrides.clear()


def _seed_graph(*, locked_node: bool = False) -> ConceptGraph:
    graph = ConceptGraph(
        id="graph-test",
        project_id=None,
        name="测试概念图",
        description="用于 GraphPatch API 测试",
        root_id="root",
        nodes=[
            ConceptNode(id="root", label="根概念", editable=True),
            ConceptNode(id="child", label="子概念", editable=not locked_node),
        ],
        edges=[
            ConceptEdge(
                id="root-child",
                source="root",
                target="child",
                relation="is_a",
                source_kind="user",
            )
        ],
    )
    return graph_service.save(graph)


def _add_node_operation(node_id: str) -> dict:
    return {
        "op": "add_node",
        "node": {"id": node_id, "label": node_id, "node_type": "concept"},
    }


def _add_connected_node_operations(node_id: str) -> list[dict]:
    return [
        _add_node_operation(node_id),
        {
            "op": "add_edge",
            "edge": {
                "id": f"root-{node_id}",
                "source": "root",
                "target": node_id,
                "relation": "related_to",
                "source_kind": "user",
            },
        },
    ]


def _connected_seed_graph() -> ConceptGraph:
    graph = ConceptGraph(
        id="connected-graph-test",
        name="连通性测试图",
        root_id="root",
        nodes=[
            ConceptNode(id="root", label="根概念"),
            ConceptNode(id="child", label="子概念"),
        ],
        edges=[
            ConceptEdge(
                id="root-child",
                source="root",
                target="child",
                relation="is_a",
                source_kind="user",
            )
        ],
    )
    return graph_service.save(graph)


def test_graph_patch_rejects_orphan_node_and_edge_removal() -> None:
    graph = _connected_seed_graph()

    orphan_add = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "actor": "user",
            "reason": "不能创建孤立节点",
            "base_version": graph.version,
            "operations": [_add_node_operation("orphan")],
        },
    )
    assert orphan_add.status_code == 409

    orphan_remove = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "actor": "user",
            "reason": "不能删掉唯一连线",
            "base_version": graph.version,
            "operations": [{"op": "remove_edge", "node_id": "root-child"}],
        },
    )
    assert orphan_remove.status_code == 409
    assert graph_service.get(graph.id).version == graph.version


def test_graph_patch_accepts_atomic_connected_node_and_edge_addition() -> None:
    graph = _connected_seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "actor": "user",
            "reason": "原子地增加一个有连接的节点",
            "base_version": graph.version,
            "operations": [
                _add_node_operation("method"),
                {
                    "op": "add_edge",
                    "edge": {
                        "id": "child-method",
                        "source": "child",
                        "target": "method",
                        "relation": "uses",
                        "source_kind": "user",
                    },
                },
            ],
        },
    )
    assert response.status_code == 200
    current = graph_service.get(graph.id)
    assert {node.id for node in current.nodes} == {"root", "child", "method"}
    assert {edge.id for edge in current.edges} == {"root-child", "child-method"}


def test_legacy_disconnected_graph_can_be_annotated_and_repaired_incrementally() -> None:
    graph = _seed_graph()
    legacy = graph.model_copy(deep=True)
    legacy.edges = []
    storage.save_graph(legacy)
    graph_service.invalidate(legacy.id)

    annotated = client.post(
        f"/api/v1/graphs/{legacy.id}/patches",
        json={
            "actor": "user",
            "reason": "旧图仍可补充说明",
            "base_version": legacy.version,
            "operations": [
                {
                    "op": "update_node",
                    "node_id": "child",
                    "updates": {"summary": "等待重新连接的旧节点"},
                }
            ],
        },
    )
    assert annotated.status_code == 200
    current = graph_service.get(legacy.id)
    repaired = client.post(
        f"/api/v1/graphs/{legacy.id}/patches",
        json={
            "actor": "user",
            "reason": "把旧节点重新连到根",
            "base_version": current.version,
            "operations": [
                {
                    "op": "add_edge",
                    "edge": {
                        "id": "repair-root-child",
                        "source": "root",
                        "target": "child",
                        "relation": "related_to",
                        "source_kind": "user",
                    },
                }
            ],
        },
    )
    assert repaired.status_code == 200


def test_graph_patch_rejects_stale_base_version() -> None:
    graph = _seed_graph()
    first = graph_service.create_patch(
        graph.id,
        GraphPatchCreate(
            reason="先添加一个节点",
            base_version=graph.version,
            operations=_add_connected_node_operations("first"),
        ),
    )
    graph_service.apply_patch(graph.id, first.id)

    with pytest.raises(GraphConflict, match="graph version changed"):
        graph_service.create_patch(
            graph.id,
            GraphPatchCreate(
                reason="使用旧版本继续添加节点",
                base_version=graph.version,
                operations=_add_connected_node_operations("stale"),
            ),
        )

    assert graph_service.get(graph.id).version == graph.version + 1


def test_graph_patch_api_returns_conflict_for_stale_base_version() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "reason": "过期版本",
            "base_version": graph.version + 1,
            "operations": [_add_node_operation("future")],
        },
    )
    assert response.status_code == 409


def test_graph_patch_rejects_non_positive_base_version() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "reason": "非法版本号",
            "base_version": 0,
            "operations": [_add_node_operation("invalid-version")],
        },
    )
    assert response.status_code == 422


def test_two_proposals_from_same_version_conflict_on_second_apply() -> None:
    graph = _seed_graph()
    first = graph_service.create_patch(
        graph.id,
        GraphPatchCreate(
            reason="提案 A",
            base_version=graph.version,
            operations=_add_connected_node_operations("proposal-a"),
        ),
    )
    second = graph_service.create_patch(
        graph.id,
        GraphPatchCreate(
            reason="提案 B",
            base_version=graph.version,
            operations=_add_connected_node_operations("proposal-b"),
        ),
    )

    graph_service.apply_patch(graph.id, first.id)
    with pytest.raises(GraphConflict, match="graph version changed"):
        graph_service.apply_patch(graph.id, second.id)

    current = graph_service.get(graph.id)
    assert current.version == 2
    assert {node.id for node in current.nodes} == {"root", "child", "proposal-a"}


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "update_node", "node_id": "child", "updates": {"id": "renamed"}},
        {"op": "update_node", "node_id": "child", "updates": {"editable": False}},
        {"op": "update_node", "node_id": "child", "updates": {}},
        {"op": "add_node"},
        {"op": "remove_edge"},
    ],
)
def test_graph_patch_rejects_malformed_operations(operation: dict) -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={"reason": "非法修改", "base_version": graph.version, "operations": [operation]},
    )
    assert response.status_code == 422


def test_graph_patch_is_atomic_when_a_later_operation_is_invalid() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "actor": "user",
            "reason": "第二个操作的边端点不存在",
            "base_version": graph.version,
            "operations": [
                _add_node_operation("temporary"),
                {
                    "op": "add_edge",
                    "edge": {
                        "id": "invalid-edge",
                        "source": "root",
                        "target": "missing-node",
                        "relation": "related_to",
                    },
                },
            ],
        },
    )
    assert response.status_code == 409

    current = graph_service.get(graph.id)
    assert current.version == graph.version
    assert "temporary" not in {node.id for node in current.nodes}


def test_locked_node_cannot_be_updated() -> None:
    graph = _seed_graph(locked_node=True)
    response = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={
            "actor": "user",
            "reason": "尝试修改锁定节点",
            "base_version": graph.version,
            "operations": [
                {
                    "op": "update_node",
                    "node_id": "child",
                    "updates": {"summary": "不应写入"},
                }
            ],
        },
    )
    assert response.status_code == 409


def test_research_mode_exposes_cautious_innovation_candidate() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        community_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention Mechanism", "level": "research", "max_papers": 4},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        assert job["status"] == "completed"
        result = job["result"]
        assert result["search_terms"]
        assert result["innovation_candidates"]
        candidate = result["innovation_candidates"][0]
        assert candidate["confidence"] == "low"
        assert candidate["validation_steps"]
        assert "不能据此证明全球不存在" in result["novelty_note"]
    finally:
        app.dependency_overrides.clear()


def test_demo_provider_supports_chinese_attention_alias() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "注意力机制", "level": "literature", "max_papers": 4},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        assert job["status"] == "completed"
        assert job["result"]["papers"][0]["id"] == "demo-attention-vaswani"
    finally:
        app.dependency_overrides.clear()


def test_graph_list_and_patch_history_endpoints() -> None:
    graph = _seed_graph()
    listed = client.get("/api/v1/graphs")
    assert listed.status_code == 200
    assert any(item["id"] == graph.id for item in listed.json())

    proposed = client.post(
        f"/api/v1/graphs/{graph.id}/patches",
        json={"actor": "agent", "reason": "补充候选节点", "operations": _add_connected_node_operations("candidate")},
    )
    assert proposed.status_code == 200
    history = client.get(f"/api/v1/graphs/{graph.id}/patches")
    assert history.status_code == 200
    assert history.json()[0]["id"] == proposed.json()["id"]

    rejected = client.post(
        f"/api/v1/graphs/{graph.id}/patches/{proposed.json()['id']}/reject"
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert graph_service.get(graph.id).version == 1


def test_independent_graph_create_endpoint_does_not_overwrite_existing_graph() -> None:
    payload = {
        "id": "manual-graph",
        "name": "手工概念树",
        "description": "用户从零开始整理的概念树",
        "root_id": "root",
        "nodes": [
            {"id": "root", "label": "研究主题", "node_type": "concept"},
            {"id": "method", "label": "候选方法", "node_type": "method"},
        ],
        "edges": [
            {"source": "root", "target": "method", "relation": "is_a"},
        ],
    }
    created = client.post("/api/v1/graphs", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "manual-graph"
    assert created.json()["root_id"] == "root"

    duplicate = client.post("/api/v1/graphs", json=payload)
    assert duplicate.status_code == 409
    restored = client.get("/api/v1/graphs/manual-graph")
    assert restored.status_code == 200
    assert restored.json()["version"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "缺少根节点",
            "root_id": "missing",
            "nodes": [{"id": "root", "label": "根"}],
        },
        {
            "name": "边端点不存在",
            "root_id": "root",
            "nodes": [{"id": "root", "label": "根"}],
            "edges": [{"source": "root", "target": "missing", "relation": "is_a"}],
        },
    ],
)
def test_independent_graph_create_validates_root_and_edge_endpoints(payload: dict) -> None:
    response = client.post("/api/v1/graphs", json=payload)
    assert response.status_code == 422


def test_graph_metadata_can_be_renamed_with_version_check() -> None:
    graph = _seed_graph()
    renamed = client.patch(
        f"/api/v1/graphs/{graph.id}",
        json={"name": "新的概念树名称", "base_version": graph.version},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "新的概念树名称"
    assert renamed.json()["version"] == 2

    stale = client.patch(
        f"/api/v1/graphs/{graph.id}",
        json={"name": "过期修改", "base_version": 1},
    )
    assert stale.status_code == 409


def test_agent_node_explanation_is_a_patch_until_approved() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        graph = _seed_graph()
        response = client.post(
            f"/api/v1/graphs/{graph.id}/nodes/child/explanation-patch",
            json={"audience": "beginner", "language": "zh-CN"},
        )
        assert response.status_code == 200
        patch = response.json()
        assert patch["status"] == "proposed"
        assert patch["operations"][0]["op"] == "update_node"
        assert patch["operations"][0]["updates"]["summary"]
        assert patch["source_request"]
        assert patch["translation_mode"] == "heuristic"
        assert graph_service.get(graph.id).nodes[1].summary == ""
    finally:
        app.dependency_overrides.clear()


def test_agent_node_explanation_provider_failure_is_not_a_500() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="unsupported",
        demo_mode=False,
    )
    try:
        graph = _seed_graph()
        response = client.post(
            f"/api/v1/graphs/{graph.id}/nodes/child/explanation-patch",
            json={"audience": "beginner", "language": "zh-CN"},
        )
        assert response.status_code == 503
        assert "Provider" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_source_urls_only_allow_http_or_https() -> None:
    with pytest.raises(ValueError, match="只允许 http 或 https"):
        PaperRecord(id="bad", title="恶意来源", source="fixture", url="javascript:alert(1)")


def test_idea_check_reports_scoped_prior_art_and_alternatives() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        response = client.post(
            "/api/v1/ideas/check",
            json={
                "idea": "让 PagedAttention 管理长上下文的 KV cache",
                "max_papers": 4,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["similarity_level"] == "L0"
        assert result["novelty"]["scope_note"]
        assert result["manual_review_status"] == "needs_review"
        assert result["papers"]
        assert result["alternative_ideas"]
        assert result["validation_steps"]
        assert result["related_work_summaries"]
        assert result["related_work_summaries"][0]["summary_level"] == "abstract_only"
        assert result["related_work_summaries"][0]["plain_language_summary"]
        assert "不能" in "".join(result["warnings"]) or result["novelty"]["confidence"] == "low"

        check_id = result["id"]
        restored = client.get(f"/api/v1/ideas/checks/{check_id}")
        assert restored.status_code == 200
        assert restored.json()["id"] == check_id
        assert any(item["id"] == check_id for item in client.get("/api/v1/ideas/checks").json())
    finally:
        app.dependency_overrides.clear()


def test_idea_check_validates_minimum_idea_length() -> None:
    response = client.post("/api/v1/ideas/check", json={"idea": "太短"})
    assert response.status_code == 422


def test_idea_check_does_not_turn_provider_failure_into_a_novelty_claim() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="unsupported",
        explanation_provider="rule_based",
        demo_mode=False,
    )
    try:
        response = client.post(
            "/api/v1/ideas/check",
            json={"idea": "A sufficiently specific research idea for checking"},
        )
        assert response.status_code == 503
        assert "Provider" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_idea_check_can_record_human_review_without_changing_search_scope() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/ideas/check",
            json={"idea": "Use paged memory for long context inference cache"},
        )
        assert created.status_code == 200
        check = created.json()
        reviewed = client.post(
            f"/api/v1/ideas/checks/{check['id']}/review",
            json={
                "status": "reviewed",
                "note": "已打开最相似论文并核对摘要与方法标题",
                "reviewer": "researcher",
            },
        )
        assert reviewed.status_code == 200
        body = reviewed.json()
        assert body["manual_review_status"] == "reviewed"
        assert body["review_note"]
        assert body["reviewed_by"] == "researcher"
        assert body["reviewed_at"]
        assert body["search_terms"] == check["search_terms"]
    finally:
        app.dependency_overrides.clear()


def test_experiment_plan_api_is_plan_only_and_reviewable() -> None:
    response = client.post(
        "/api/v1/experiments/plans",
        json={
            "idea": "降低长上下文 LLM 推理的 KV Cache 显存占用",
            "baseline": "标准 KV Cache 管理",
        },
    )
    assert response.status_code == 201
    plan = response.json()
    assert plan["approval_status"] == "draft"
    assert plan["execution_status"] == "not_started"
    assert plan["hypothesis"]
    assert plan["metrics"]
    assert plan["failure_criteria"]
    assert any("不执行" in warning for warning in plan["warnings"])

    plan_id = plan["id"]
    listed = client.get("/api/v1/experiments/plans")
    assert listed.status_code == 200
    assert any(item["id"] == plan_id for item in listed.json())

    reviewed = client.post(
        f"/api/v1/experiments/plans/{plan_id}/review",
        json={"status": "approved", "note": "先做小规模预实验", "reviewer": "researcher"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["approval_status"] == "approved"
    assert reviewed.json()["review_note"] == "先做小规模预实验"
    assert reviewed.json()["execution_status"] == "not_started"


def test_experiment_plan_requires_a_source() -> None:
    response = client.post("/api/v1/experiments/plans", json={})
    assert response.status_code == 422


def test_graph_compare_returns_unverified_cross_domain_connections() -> None:
    first = ConceptGraph(
        id="graph-a",
        name="长序列推理",
        root_id="root-a",
        nodes=[
            ConceptNode(id="root-a", label="LLM 推理", node_type="concept"),
            ConceptNode(id="problem-a", label="KV cache 显存占用", node_type="problem"),
        ],
    )
    second = ConceptGraph(
        id="graph-b",
        name="操作系统缓存",
        root_id="root-b",
        nodes=[
            ConceptNode(id="root-b", label="操作系统", node_type="concept"),
            ConceptNode(id="method-b", label="分页虚拟内存", node_type="method"),
        ],
    )
    graph_service.save(first)
    graph_service.save(second)
    response = client.post(
        "/api/v1/graphs/compare",
        json={
            "graph_ids": [first.id, second.id],
            "node_ids": ["problem-a", "method-b"],
            "focus": "找出可以互相借鉴的缓存机制",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["connections"]
    connection = result["connections"][0]
    assert connection["confidence"] == "low"
    assert connection["relation"] == "method_transfer"
    assert connection["validation_steps"]
    assert result["warnings"]


def test_graph_subset_keeps_ancestors_without_mutating_source() -> None:
    graph = ConceptGraph(
        id="graph-subset",
        name="可裁剪图",
        root_id="root",
        nodes=[
            ConceptNode(id="root", label="根"),
            ConceptNode(id="branch", label="分支", node_type="method"),
            ConceptNode(id="leaf", label="叶子", node_type="idea"),
        ],
        edges=[
            {"source": "root", "target": "branch", "relation": "is_a"},
            {"source": "branch", "target": "leaf", "relation": "part_of"},
        ],
    )
    graph_service.save(graph)
    response = client.get(f"/api/v1/graphs/{graph.id}/subset?node_ids=leaf")
    assert response.status_code == 200
    subset = response.json()
    assert subset["source_graph_id"] == graph.id
    assert {node["id"] for node in subset["graph"]["nodes"]} == {"root", "branch", "leaf"}
    assert client.get(f"/api/v1/graphs/{graph.id}").json()["version"] == 1


def test_analysis_and_graph_survive_service_cache_reset() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention Mechanism", "level": "literature", "max_papers": 4},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        assert job["status"] == "completed"
        graph_id = job["result"]["graph"]["id"]
        saved = client.post(
            f"/api/v1/analyses/{job_id}/graph/save",
            json={"expected_version": job["result"]["graph"]["version"]},
        )
        assert saved.status_code == 200

        # Simulate a service restart: durable rows remain, process-local caches
        # do not. The public GET/list APIs must hydrate from SQLite.
        research_service._jobs.clear()
        graph_service._graphs.clear()
        graph_service._patches.clear()

        restored_job = client.get(f"/api/v1/analyses/{job_id}")
        restored_graph = client.get(f"/api/v1/graphs/{graph_id}")
        listed_jobs = client.get("/api/v1/analyses")
        listed_graphs = client.get("/api/v1/graphs")

        assert restored_job.status_code == 200
        assert restored_job.json()["status"] == "completed"
        assert restored_graph.status_code == 200
        assert restored_graph.json()["id"] == graph_id
        assert any(item["id"] == job_id for item in listed_jobs.json())
        assert any(item["id"] == graph_id for item in listed_graphs.json())
    finally:
        app.dependency_overrides.clear()


def test_analysis_graph_lifecycle_save_is_idempotent_and_delete_preserves_history() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention", "level": "literature", "max_papers": 1},
        )
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        assert job["status"] == "completed"
        graph = job["result"]["graph"]
        graph_id = graph["id"]
        assert client.get("/api/v1/graphs").json() == []

        first = client.post(
            f"/api/v1/analyses/{job_id}/graph/save",
            json={"expected_version": graph["version"], "name": "Attention 已保存"},
        )
        assert first.status_code == 200
        assert first.json()["saved_graph_id"] == graph_id
        assert first.json()["graph"]["save_state"] == "saved"

        second = client.post(
            f"/api/v1/analyses/{job_id}/graph/save",
            json={"expected_version": graph["version"]},
        )
        assert second.status_code == 200
        assert second.json()["saved_graph_id"] == graph_id
        assert len(client.get("/api/v1/graphs").json()) == 1

        patch = client.post(
            f"/api/v1/graphs/{graph_id}/patches",
            json={
                "actor": "agent",
                "reason": "保存后增加一个节点",
                "operations": _add_connected_node_operations("saved-extra"),
            },
        )
        assert patch.status_code == 200
        patch_id = patch.json()["id"]
        deleted = client.delete(f"/api/v1/graphs/{graph_id}?expected_version=1")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/graphs/{graph_id}").status_code == 404
        assert client.get(f"/api/v1/graphs/{graph_id}/patches").status_code == 404
        # Deleting the library copy does not destroy the analysis snapshot.
        restored = client.get(f"/api/v1/analyses/{job_id}/graph")
        assert restored.status_code == 200
        assert restored.json()["id"] == graph_id
        assert restored.json()["save_state"] == "transient"
        history = client.get(f"/api/v1/analyses/{job_id}")
        assert history.status_code == 200
        assert history.json()["result"]["graph_save_state"] == "transient"
        assert history.json()["result"]["saved_graph_id"] is None
        # The historical snapshot remains reusable after the library copy is
        # removed, so the user can save it again later without creating a
        # second analysis result.
        resaved = client.post(
            f"/api/v1/analyses/{job_id}/graph/save",
            json={"expected_version": restored.json()["version"]},
        )
        assert resaved.status_code == 200
        assert resaved.json()["saved_graph_id"] == graph_id
        assert resaved.json()["graph"]["save_state"] == "saved"
        assert client.get(f"/api/v1/graphs/{graph_id}/patches/{patch_id}").status_code in {
            404,
            405,
        }
    finally:
        app.dependency_overrides.clear()


def test_analysis_graph_metadata_patch_is_still_transient() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention", "level": "literature", "max_papers": 1},
        )
        job_id = created.json()["id"]
        for _ in range(30):
            job = client.get(f"/api/v1/analyses/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
        graph = job["result"]["graph"]
        updated = client.patch(
            f"/api/v1/analyses/{job_id}/graph",
            json={"name": "临时重命名", "base_version": graph["version"]},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "临时重命名"
        assert updated.json()["version"] == graph["version"] + 1
        assert updated.json()["save_state"] == "transient"
        assert client.get("/api/v1/graphs").json() == []
    finally:
        app.dependency_overrides.clear()


def test_storage_path_is_configurable_and_clear_is_available(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "custom-wishforge.db"
    monkeypatch.setenv("WISHFORGE_STORAGE_PATH", str(database_path))
    settings = Settings()
    assert settings.storage_path == str(database_path)

    isolated = Storage(str(database_path))
    assert database_path.exists()
    isolated.clear()
    isolated.close()


def test_phase1_storage_migration_adds_lifecycle_columns_and_patch_table(tmp_path) -> None:
    database_path = tmp_path / "legacy-wishforge.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE concept_graphs (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            project_id TEXT,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()

    isolated = Storage(str(database_path))
    try:
        connection = sqlite3.connect(database_path)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(concept_graphs)").fetchall()
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.close()
        assert {"graph_kind", "source_analysis_id", "source_scope", "save_state", "generation_id"}.issubset(columns)
        assert "overview_jobs" in tables
        assert "analysis_graph_patches" in tables
        assert version >= 2
    finally:
        isolated.close()


def test_shared_storage_clear_removes_analysis_and_graph_rows() -> None:
    graph = _seed_graph()
    assert storage.get_graph(graph.id) is not None
    storage.clear()
    assert storage.get_graph(graph.id) is None
    assert storage.list_analyses() == []


def test_transient_analysis_graph_supports_reviewed_patches() -> None:
    import time

    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo", explanation_provider="rule_based", demo_mode=True
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention Mechanism", "level": "literature", "max_papers": 3},
        )
        assert created.status_code == 202
        analysis_id = created.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/v1/analyses/{analysis_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed"
        graph = job["result"]["graph"]
        proposal = client.post(
            f"/api/v1/analyses/{analysis_id}/graph/agent-patch",
            json={
                "request": "在根节点下新增“线性注意力”方法节点",
                "target_node_id": graph["root_id"],
                "base_version": graph["version"],
            },
        )
        assert proposal.status_code == 200
        patch = proposal.json()
        assert patch["status"] == "proposed"
        assert client.get(f"/api/v1/graphs/{graph['id']}").status_code == 404
        applied = client.post(
            f"/api/v1/analyses/{analysis_id}/graph/patches/{patch['id']}/apply"
        )
        assert applied.status_code == 200
        current = client.get(f"/api/v1/analyses/{analysis_id}/graph").json()
        assert current["version"] == graph["version"] + 1
        assert current["save_state"] == "transient"
        assert any(node["label"] == "线性注意力" for node in current["nodes"])
    finally:
        app.dependency_overrides.clear()


def test_transient_analysis_graph_rejects_orphaning_edge_removal() -> None:
    import time

    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo", explanation_provider="rule_based", demo_mode=True
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention Mechanism", "level": "literature", "max_papers": 2},
        )
        analysis_id = created.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/v1/analyses/{analysis_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed"
        graph = job["result"]["graph"]
        root_edge = next(edge for edge in graph["edges"] if edge["source"] == graph["root_id"])

        rejected = client.post(
            f"/api/v1/analyses/{analysis_id}/graph/patches",
            json={
                "actor": "user",
                "reason": "尝试删除唯一父边",
                "base_version": graph["version"],
                "operations": [{"op": "remove_edge", "node_id": root_edge["id"]}],
            },
        )
        assert rejected.status_code == 409
        current = client.get(f"/api/v1/analyses/{analysis_id}/graph").json()
        assert current["version"] == graph["version"]
        assert any(edge["id"] == root_edge["id"] for edge in current["edges"])
    finally:
        app.dependency_overrides.clear()


def test_saved_graph_node_detail_and_layout_are_persisted() -> None:
    graph = _seed_graph()
    detail = client.get(f"/api/v1/graphs/{graph.id}/nodes/{graph.root_id}")
    assert detail.status_code == 200
    assert detail.json()["node"]["id"] == graph.root_id
    layout = client.patch(
        f"/api/v1/graphs/{graph.id}/layout",
        json={
            "expected_version": graph.version,
            "positions": [
                {"node_id": node.id, "x": index * 100 + 10, "y": index * 50 + 20}
                for index, node in enumerate(graph.nodes)
            ],
            "layout_algorithm": "preset",
        },
    )
    assert layout.status_code == 200
    updated = layout.json()
    assert updated["version"] == graph.version + 1
    assert updated["layout_algorithm"] == "preset"
    assert all(node["visual"]["x"] is not None for node in updated["nodes"])
    stale = client.patch(
        f"/api/v1/graphs/{graph.id}/layout",
        json={
            "expected_version": graph.version,
            "positions": [{"node_id": graph.root_id, "x": 0, "y": 0}],
        },
    )
    assert stale.status_code == 409
