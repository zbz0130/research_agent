from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import ExplanationResult, PaperRecord
from app.services.research_service import _build_evidence, _build_evidence_ledger


client = TestClient(app)


def _wait_for_job(job_id: str) -> dict:
    for _ in range(40):
        response = client.get(f"/api/v1/analyses/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed"}:
            return job
    raise AssertionError("analysis did not finish in the test window")


def test_literature_analysis_contains_claim_level_ledger() -> None:
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
        job = _wait_for_job(created.json()["id"])
        assert job["status"] == "completed"

        ledger = job["result"]["evidence_ledger"]
        assert ledger["analysis_id"] == created.json()["id"]
        assert ledger["evidence_count"] == len(job["result"]["evidence"])
        assert ledger["claims"]
        assert ledger["linked_claim_count"] > 0
        assert 0 < ledger["coverage"] <= 1
        assert ledger["link_coverage"] == ledger["coverage"]
        assert ledger["verified_coverage"] == 0
        assert ledger["contradicted_claim_count"] >= 0
        assert any(claim["evidence_links"] for claim in ledger["claims"])
        assert any(claim["status"] == "unverified" for claim in ledger["claims"])
        assert ledger["warnings"]

        response = client.get(f"/api/v1/analyses/{created.json()['id']}/evidence-ledger")
        assert response.status_code == 200
        assert response.json()["analysis_id"] == created.json()["id"]
    finally:
        app.dependency_overrides.clear()

def test_quick_analysis_ledger_marks_explanation_as_unverified() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "一个尚未检索的概念", "level": "quick"},
        )
        assert created.status_code == 202
        job = _wait_for_job(created.json()["id"])
        assert job["status"] == "completed"
        ledger = job["result"]["evidence_ledger"]
        assert ledger["evidence_count"] == 0
        assert ledger["coverage"] == 0
        assert any(claim["status"] in {"unverified", "hypothesis"} for claim in ledger["claims"])
        assert ledger["warnings"]
    finally:
        app.dependency_overrides.clear()


def test_claim_matching_is_sparse_typed_and_keeps_irrelevant_claim_unlinked() -> None:
    paper = PaperRecord(
        id="paper-paged-cache",
        title="Paged KV Cache Management",
        year=2024,
        abstract=(
            "We propose a fixed-size paging method for KV cache management. "
            "Results show lower memory fragmentation and higher serving throughput. "
            "However, page-table overhead remains a limitation for very short requests."
        ),
        source="test_fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache compression", [paper])
    explanation = ExplanationResult(
        one_sentence="This claim is about an unrelated botanical taxonomy.",
        intuitive="A paging analogy can help explain the idea.",
        technical="The method uses fixed-size paging for KV cache management.",
        limitations=["Page-table overhead is a limitation for short requests."],
        related_concepts=[],
        evidence_ids=[],
    )

    ledger = _build_evidence_ledger("analysis-test", explanation, evidence, [paper])

    assert all(len(claim.evidence_links) <= 3 for claim in ledger.claims)
    definition = next(claim for claim in ledger.claims if claim.claim_type == "definition")
    mechanism = next(claim for claim in ledger.claims if claim.claim_type == "mechanism")
    limitation = next(claim for claim in ledger.claims if claim.claim_type == "limitation")
    assert definition.evidence_links == []
    assert mechanism.evidence_links
    assert limitation.evidence_links
    assert all(link.relation in {"qualifies", "background"} for link in mechanism.evidence_links)
    assert any("自动匹配" in link.note for link in limitation.evidence_links)
    assert len(ledger.claims) == 3
