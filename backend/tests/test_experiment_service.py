from __future__ import annotations

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.experiment_schemas import (
    EvidenceProvenance,
    ExperimentMetric,
    ExperimentPlanRequest,
    ResourceEstimate,
)
from app.research_schemas import (
    EvidenceCard,
    IdeaCheckResult,
    InnovationCandidate,
    NoveltyCheck,
    PaperRecord,
)
from app.services.experiment_service import (
    ExperimentService,
    experiment_service,
)
from app.storage import storage
from app.main import app


client = TestClient(app)


def test_free_text_generates_complete_non_executable_plan() -> None:
    plan = experiment_service.generate("降低长上下文 LLM 推理的 KV Cache 显存占用")

    assert plan.title.startswith("验证：")
    assert plan.hypothesis
    assert plan.baseline
    assert plan.variables
    assert plan.controls
    assert plan.metrics
    assert any(metric.primary for metric in plan.metrics)
    assert plan.ablation
    assert plan.expected_outcomes
    assert plan.failure_criteria
    assert plan.resource_estimate.time_estimate_hours > 0
    assert plan.validation_steps
    assert plan.approval_status == "draft"
    assert plan.execution_status == "not_started"
    assert any("不执行" in warning for warning in plan.warnings)
    assert plan.resources is plan.resource_estimate
    assert plan.risks is plan.failure_criteria
    assert plan.provenance


def test_innovation_candidate_is_used_as_source_and_baseline_hint() -> None:
    candidate = InnovationCandidate(
        title="Adaptive KV cache budget",
        problem="Long-context inference exceeds memory budget",
        mechanism="Allocate cache capacity from token importance",
        nearest_work=["PagedAttention", "FlashAttention"],
        novelty_level="L2",
        confidence="low",
        feasibility="medium",
        rationale="A bounded candidate for a reproducible comparison",
        validation_steps=["Compare with a fixed cache budget"],
        warning="Needs full-text prior-art review",
        source_type="model_generated",
        source_agent_run_id="run-1",
        evidence_ids=["evidence-1"],
    )

    plan = ExperimentService().from_candidate(candidate)

    assert "Adaptive KV cache budget" in plan.title
    assert "Allocate cache capacity" in plan.hypothesis
    assert "PagedAttention" in plan.baseline
    candidate_sources = [item for item in plan.provenance if item.source_id == candidate.id]
    assert candidate_sources
    assert candidate_sources[0].evidence_ids == ["evidence-1"]
    assert candidate_sources[0].source_agent_run_id == "run-1"
    assert any("prior-art review" in warning for warning in plan.warnings)
    assert "Compare with a fixed cache budget" in plan.validation_steps


def test_idea_check_propagates_paper_and_evidence_provenance() -> None:
    paper = PaperRecord(
        id="paper-1",
        title="A paper on retrieval memory",
        abstract="We study memory cost and report a useful result.",
        source="demo",
        source_kind="demo",
        url="https://example.org/paper-1",
    )
    evidence = EvidenceCard(
        id="e-1",
        paper_id=paper.id,
        claim="Memory cost is a limitation",
        excerpt="Memory cost is discussed in the abstract.",
    )
    check = IdeaCheckResult(
        id="check-1",
        idea="Reduce retrieval memory cost",
        papers=[paper],
        evidence=[evidence],
        novelty=NoveltyCheck(
            level="L2",
            reason="Partial overlap",
            matched_paper_ids=[paper.id],
            compared_terms=["retrieval", "memory"],
            scope_note="Abstract metadata only",
        ),
        similarity_level="L2",
        similarity_reason="Partial overlap",
        current_conclusion="Needs an explicit boundary experiment",
        confidence="medium",
        warnings=["Only metadata was checked"],
        validation_steps=["Read the nearest paper in full"],
    )

    plan = experiment_service.generate(check)

    assert any(item.source_id == "check-1" for item in plan.provenance)
    paper_sources = [item for item in plan.provenance if item.source_id == paper.id]
    assert paper_sources and paper_sources[0].source_url == paper.url
    assert paper_sources[0].evidence_ids == [evidence.id]
    assert any("Only metadata was checked" in warning for warning in plan.warnings)
    assert "Read the nearest paper in full" in plan.validation_steps


def test_request_overrides_are_validated_and_aliases_are_supported() -> None:
    request = ExperimentPlanRequest(
        idea="Test a ranking heuristic",
        resources=ResourceEstimate(time=1.5, gpu_hours=0),
        metrics=[
            ExperimentMetric(
                name="ndcg",
                direction="maximize",
                primary=True,
                unit="score",
            )
        ],
        provenance=[
            EvidenceProvenance(
                source="lab-notes",
                evidence=["note-1", "note-1"],
            )
        ],
    )

    plan = experiment_service.generate(
        request,
        baseline="BM25",
        failure_criteria=[{"condition": "nDCG does not improve", "severity": "stop"}],
    )

    assert plan.baseline == "BM25"
    assert plan.resource_estimate.time_estimate_hours == 1.5
    assert plan.metrics[0].name == "ndcg"
    assert plan.failure_criteria[0].condition == "nDCG does not improve"
    assert plan.provenance[0].evidence_ids == ["note-1"]


def test_plan_json_and_sqlite_round_trip_preserve_canonical_fields() -> None:
    project_a = uuid4()
    project_b = uuid4()
    first = experiment_service.generate(
        {
            "idea": "Compare a ranking heuristic",
            "project_id": project_a,
            "resources": {"time": 1.25, "gpu_hours": 0},
            "risks": [{"condition": "quality is unchanged", "severity": "stop"}],
        }
    )
    second = experiment_service.generate("A separate project idea", project_id=project_b)
    storage.save_experiment_plan(first)
    storage.save_experiment_plan(second)

    # ``save_experiment_plan`` stores model_dump_json; loading it back catches
    # accidental computed-field/alias additions that would be rejected by the
    # strict ``extra=forbid`` plan model.
    serialized = first.model_dump()
    assert "resources" in serialized and "risks" in serialized
    restored = storage.get_experiment_plan(first.id)
    assert restored is not None
    assert restored.id == first.id
    assert restored.resource_estimate.time_estimate_hours == 1.25
    assert restored.failure_criteria[0].condition == "quality is unchanged"
    assert restored.execution_status == "not_started"

    all_plans = storage.list_experiment_plans()
    project_a_plans = storage.list_experiment_plans(str(project_a))
    project_b_plans = storage.list_experiment_plans(str(project_b))
    assert {item.id for item in all_plans} >= {first.id, second.id}
    assert [item.id for item in project_a_plans] == [first.id]
    assert [item.id for item in project_b_plans] == [second.id]


def test_plan_accepts_legacy_alias_payload_with_canonical_values_preferred() -> None:
    from app.experiment_schemas import ExperimentPlan

    plan = ExperimentPlan.model_validate(
        {
            "title": "Alias compatibility",
            "hypothesis": "A hypothesis",
            "baseline": "Baseline",
            "resource_estimate": {"time": 2},
            "resources": {"time": 99},
            "failure_criteria": [{"condition": "canonical criterion"}],
            "risks": [{"condition": "legacy criterion"}],
        }
    )
    assert plan.resource_estimate.time_estimate_hours == 2
    assert plan.failure_criteria[0].condition == "canonical criterion"


def test_review_metadata_survives_round_trip_without_enabling_execution() -> None:
    from app.experiment_schemas import ExperimentPlanReview

    plan = experiment_service.generate("Validate a robust metric")
    reviewed = experiment_service.review(
        plan,
        ExperimentPlanReview(status="approved", note="Run only after manual setup", reviewer="qa"),
    )
    storage.save_experiment_plan(reviewed)
    restored = storage.get_experiment_plan(reviewed.id)

    assert restored is not None
    assert restored.approval_status == "approved"
    assert restored.review_note == "Run only after manual setup"
    assert restored.reviewed_by == "qa"
    assert restored.execution_status == "not_started"


def test_plan_api_project_filter_returns_only_matching_drafts() -> None:
    project_a = str(uuid4())
    project_b = str(uuid4())
    first = client.post(
        "/api/v1/experiments/plans",
        json={"idea": "Project A experiment idea", "project_id": project_a},
    )
    second = client.post(
        "/api/v1/experiments/plans",
        json={"idea": "Project B experiment idea", "project_id": project_b},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    filtered = client.get("/api/v1/experiments/plans", params={"project_id": project_a})
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [first.json()["id"]]


def test_empty_request_and_execution_like_overrides_are_rejected() -> None:
    with pytest.raises(ValueError):
        ExperimentPlanRequest()

    with pytest.raises(TypeError, match="覆盖字段"):
        experiment_service.generate("an idea", command="python train.py")
