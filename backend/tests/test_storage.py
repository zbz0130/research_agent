from app.research_schemas import (
    AnalysisJob,
    ConceptGraph,
    ConceptNode,
    GraphOperation,
    GraphPatch,
    IdeaCheckResult,
    NoveltyCheck,
)
from app.experiment_schemas import ExperimentPlanReview
from app.services.experiment_service import experiment_service
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


def test_experiment_plan_survives_a_new_storage_instance(tmp_path) -> None:
    database_path = tmp_path / "experiment-plan.db"
    first = Storage(str(database_path))
    plan = experiment_service.generate("比较一个检索排序方法与 BM25")
    reviewed = experiment_service.review(
        plan,
        ExperimentPlanReview(status="approved", note="先做小规模预实验", reviewer="tester"),
    )
    first.save_experiment_plan(reviewed)
    first.close()

    second = Storage(str(database_path))
    try:
        restored = second.get_experiment_plan(plan.id)
        assert restored is not None
        assert restored.approval_status == "approved"
        assert restored.review_note == "先做小规模预实验"
        assert restored.execution_status == "not_started"
        assert restored.resource_estimate.compute
        listed = second.list_experiment_plans()
        assert [item.id for item in listed] == [plan.id]
    finally:
        second.clear()
        second.close()
