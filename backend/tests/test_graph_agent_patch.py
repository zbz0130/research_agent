from fastapi.testclient import TestClient

from app.main import app
from app.research_schemas import ConceptEdge, ConceptGraph, ConceptNode
from app.services.graph_service import graph_service


client = TestClient(app)


def _seed_graph(*, locked_child: bool = False) -> ConceptGraph:
    graph = ConceptGraph(
        id="agent-patch-graph",
        name="Agent Patch 测试图",
        root_id="root",
        nodes=[
            ConceptNode(id="root", label="Attention Mechanism", node_type="concept"),
            ConceptNode(
                id="child",
                label="Self-Attention",
                node_type="method",
                editable=not locked_child,
            ),
        ],
        edges=[ConceptEdge(id="root-child", source="root", target="child", relation="is_a")],
    )
    return graph_service.save(graph)


def test_natural_language_agent_patch_is_proposed_and_bounded() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={
            "request": "在 Attention Mechanism 下增加一个 FlashAttention 节点，说明它解决长序列瓶颈",
            "target_node_id": graph.root_id,
            "base_version": graph.version,
        },
    )

    assert response.status_code == 200, response.text
    patch = response.json()
    assert patch["actor"] == "agent"
    assert patch["status"] == "proposed"
    assert patch["translation_mode"] == "heuristic"
    assert patch["source_request"].startswith("在 Attention Mechanism")
    assert patch["warnings"]
    assert len(patch["operations"]) <= 4
    assert patch["operations"][0]["op"] == "add_node"
    assert patch["operations"][0]["node"]["label"] == "FlashAttention"
    assert graph_service.get(graph.id).version == graph.version
    assert "FlashAttention" not in {node.label for node in graph_service.get(graph.id).nodes}

    # The proposal metadata is durable, not just a process-local annotation.
    graph_service._patches.clear()
    history = client.get(f"/api/v1/graphs/{graph.id}/patches")
    assert history.status_code == 200
    assert history.json()[0]["source_request"].startswith("在 Attention Mechanism")
    assert history.json()[0]["warnings"]

    applied = client.post(
        f"/api/v1/graphs/{graph.id}/patches/{patch['id']}/apply",
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    current = graph_service.get(graph.id)
    assert current.version == graph.version + 1
    assert "FlashAttention" in {node.label for node in current.nodes}


def test_natural_language_update_uses_target_and_respects_locked_nodes() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={
            "request": "给这个节点的说明改为用于建模序列内部依赖",
            "target_node_id": "child",
        },
    )
    assert response.status_code == 200, response.text
    patch = response.json()
    assert patch["operations"][0]["op"] == "update_node"
    assert patch["operations"][0]["node_id"] == "child"
    assert graph_service.get(graph.id).nodes[1].summary == ""

    locked = _seed_graph(locked_child=True)
    locked_response = client.post(
        f"/api/v1/graphs/{locked.id}/agent-patch",
        json={
            "request": "给 Self-Attention 的说明改为不应写入",
            "target_node_id": "child",
        },
    )
    assert locked_response.status_code == 409
    assert "locked" in locked_response.json()["detail"]


def test_natural_language_agent_patch_reuses_graph_version_check_and_root_guard() -> None:
    graph = _seed_graph()
    stale = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={
            "request": "给 Self-Attention 增加一句说明",
            "target_node_id": "child",
            "base_version": graph.version + 1,
        },
    )
    assert stale.status_code == 409
    assert "graph version changed" in stale.json()["detail"]

    root_remove = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={"request": "删除根节点", "target_node_id": "root"},
    )
    assert root_remove.status_code == 409
    assert "root" in root_remove.json()["detail"]
    assert graph_service.get(graph.id).version == graph.version


def test_ambiguous_request_is_saved_as_a_transparent_note() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={
            "request": "请综合考虑这个节点未来可能的研究方向",
            "target_node_id": "child",
            "max_operations": 1,
        },
    )
    assert response.status_code == 200, response.text
    patch = response.json()
    assert len(patch["operations"]) == 1
    assert patch["operations"][0]["op"] == "update_node"
    assert "未解析" in patch["operations"][0]["updates"]["summary"]
    assert any("未识别" in warning for warning in patch["warnings"])


def test_add_node_with_one_operation_budget_falls_back_to_connected_note() -> None:
    graph = _seed_graph()
    response = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={
            "request": "在根节点下新增 FlashAttention 方法节点",
            "target_node_id": graph.root_id,
            "max_operations": 1,
        },
    )
    assert response.status_code == 200, response.text
    patch = response.json()
    assert len(patch["operations"]) == 1
    assert patch["operations"][0]["op"] == "update_node"
    assert patch["operations"][0]["node_id"] == graph.root_id
    assert any("同时建立一条关系边" in warning for warning in patch["warnings"])


def test_agent_patch_request_is_strictly_bounded() -> None:
    graph = _seed_graph()
    too_many = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={"request": "新增节点", "max_operations": 5},
    )
    assert too_many.status_code == 422

    unknown_target = client.post(
        f"/api/v1/graphs/{graph.id}/agent-patch",
        json={"request": "新增一个方法节点", "target_node_id": "missing"},
    )
    assert unknown_target.status_code == 409
    assert "target_node_id" in unknown_target.json()["detail"]
