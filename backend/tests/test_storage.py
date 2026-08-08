from app.research_schemas import (
    AnalysisJob,
    ConceptGraph,
    ConceptNode,
    GraphOperation,
    GraphPatch,
    IdeaCheckResult,
    NoveltyCheck,
)
from app.storage import Storage


def test_sqlite_documents_survive_a_new_storage_instance(tmp_path) -> None:
    database_path = tmp_path / "restart.db"
    first = Storage(str(database_path))
    graph = ConceptGraph(
        id="restart-graph",
        root_id="root",
        nodes=[ConceptNode(id="root", label="Root")],
    )
    job = AnalysisJob(concept="Attention", level="quick", audience="beginner")
    patch = GraphPatch(
        id="restart-patch",
        graph_id=graph.id,
        base_version=graph.version,
        operations=[
            GraphOperation(
                op="add_node",
                node=ConceptNode(id="future", label="Future"),
            )
        ],
        reason="restart test",
        actor="agent",
    )

    first.save_analysis(job)
    first.save_graph(graph)
    first.save_patch(patch)
    first.close()

    second = Storage(str(database_path))
    try:
        assert second.get_analysis(str(job.id)) is not None
        assert second.get_graph(graph.id).name == "未命名概念图"
        assert second.list_patches(graph.id)[0].id == patch.id
    finally:
        second.clear()
        second.close()


def test_idea_check_survives_a_new_storage_instance(tmp_path) -> None:
    database_path = tmp_path / "idea-check.db"
    first = Storage(str(database_path))
    result = IdeaCheckResult(
        id="idea-check-restart",
        idea="LoRA on a noisy dataset",
        novelty=NoveltyCheck(
            level="L2",
            reason="component overlap",
            scope_note="test scope",
        ),
        similarity_level="L2",
        similarity_reason="component overlap",
        current_conclusion="needs review",
    )
    first.save_idea_check(result)
    first.close()

    second = Storage(str(database_path))
    try:
        restored = second.get_idea_check(result.id)
        assert restored is not None
        assert restored.idea == result.idea
        assert second.list_idea_checks()[0].similarity_level == "L2"
    finally:
        second.clear()
        second.close()
