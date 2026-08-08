import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import ConceptGraph, ConceptNode, GraphPatchCreate, PaperRecord
from app.services.graph_service import GraphConflict, graph_service
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
    stylesheet = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "WishForge" in page.text
    assert stylesheet.status_code == 200


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
        explanation_provider="openai",
        experiment_provider="remote_runner",
        paper_api_key=SecretStr("paper-secret-1234"),
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
    assert slots["experiment_runner"]["configured"] is True
    assert slots["experiment_runner"]["masked"] == "••••••••5678"
    assert slots["explanation_model"]["configured"] is False
    assert "paper-secret-1234" not in response.text
    assert "run-secret-5678" not in response.text


def test_settings_load_separate_environment_keys(monkeypatch) -> None:
    monkeypatch.setenv("WISHFORGE_PAPER_API_KEY", "paper-env-9999")
    monkeypatch.setenv("WISHFORGE_EXPERIMENT_API_KEY", "runner-env-8888")

    slots = {slot.id: slot for slot in api_key_slots(Settings())}

    assert slots["paper_search"].configured is True
    assert slots["paper_search"].masked == "••••••••9999"
    assert slots["experiment_runner"].configured is True
    assert slots["experiment_runner"].masked == "••••••••8888"
    assert slots["explanation_model"].configured is False


def test_concept_analysis_creates_evidence_and_graph() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
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
        assert len(result["evidence"]) == 2
        assert result["graph"]["root_id"] == "root"
        assert result["graph"]["name"] == "Attention Mechanism 概念图"
        assert result["graph"]["version"] == 1
        assert result["evidence"][0]["locator"]["kind"] == "abstract"
        assert len(result["graph"]["nodes"]) >= 5
        assert result["explanation"]["one_sentence"]
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
                    }
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
    )
    return graph_service.save(graph)


def _add_node_operation(node_id: str) -> dict:
    return {
        "op": "add_node",
        "node": {"id": node_id, "label": node_id, "node_type": "concept"},
    }


def test_graph_patch_rejects_stale_base_version() -> None:
    graph = _seed_graph()
    first = graph_service.create_patch(
        graph.id,
        GraphPatchCreate(
            reason="先添加一个节点",
            base_version=graph.version,
            operations=[_add_node_operation("first")],
        ),
    )
    graph_service.apply_patch(graph.id, first.id)

    with pytest.raises(GraphConflict, match="graph version changed"):
        graph_service.create_patch(
            graph.id,
            GraphPatchCreate(
                reason="使用旧版本继续添加节点",
                base_version=graph.version,
                operations=[_add_node_operation("stale")],
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
            operations=[_add_node_operation("proposal-a")],
        ),
    )
    second = graph_service.create_patch(
        graph.id,
        GraphPatchCreate(
            reason="提案 B",
            base_version=graph.version,
            operations=[_add_node_operation("proposal-b")],
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
        assert len(result["search_terms"]) == 3
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
        json={"actor": "agent", "reason": "补充候选节点", "operations": [_add_node_operation("candidate")]},
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
        assert graph_service.get(graph.id).nodes[1].summary == ""
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


def test_storage_path_is_configurable_and_clear_is_available(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "custom-wishforge.db"
    monkeypatch.setenv("WISHFORGE_STORAGE_PATH", str(database_path))
    settings = Settings()
    assert settings.storage_path == str(database_path)

    isolated = Storage(str(database_path))
    assert database_path.exists()
    isolated.clear()
    isolated.close()


def test_shared_storage_clear_removes_analysis_and_graph_rows() -> None:
    graph = _seed_graph()
    assert storage.get_graph(graph.id) is not None
    storage.clear()
    assert storage.get_graph(graph.id) is None
    assert storage.list_analyses() == []
