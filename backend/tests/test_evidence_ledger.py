from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.research_schemas import (
    AtomicClaimDraft,
    ExplanationResult,
    PaperRecord,
    ResearchGapCandidate,
    ResearchLimitation,
)
from app.services.research_service import (
    _build_evidence,
    _build_evidence_ledger,
    _classify_abstract_sentence_types,
    _is_atomic_claim,
    _match_claim_evidence,
    _normalize_evolution_provenance,
)


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
    assert any("系统校验" in link.note for link in limitation.evidence_links)
    assert len(ledger.claims) == 3


def test_explicit_atomic_claims_replace_long_explanation_and_separate_real_limitations() -> None:
    paper = PaperRecord(
        id="paper-codecomp",
        title="Structural KV Cache Compression",
        year=2026,
        abstract=(
            "Attention-only methods discard structurally critical code tokens, causing failures in agentic coding. "
            "We propose CodeComp, which uses code property graphs to retain critical tokens. "
            "CodeComp improves bug localization accuracy under equal memory budgets."
        ),
        source="test_fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache compression", [paper])
    limitation_card = next(item for item in evidence if "limitation" in item.evidence_types)
    mechanism_card = next(item for item in evidence if item.excerpt.startswith("We propose CodeComp"))
    result_card = next(item for item in evidence if item.evidence_type == "result")
    explanation = ExplanationResult(
        one_sentence="A display summary that must not become a ledger claim.",
        intuitive="An analogy.",
        technical="A long paragraph combining many methods and metrics that must be ignored by the ledger.",
        claims=[
            AtomicClaimDraft(
                claim_type="mechanism",
                text="CodeComp uses code property graphs to retain critical tokens.",
                paper_ids=[paper.id],
                evidence_ids=[mechanism_card.id],
                evidence_quotes=[mechanism_card.excerpt],
            ),
            AtomicClaimDraft(
                claim_type="result",
                text="CodeComp improves bug localization accuracy under equal memory budgets.",
                paper_ids=[paper.id],
                evidence_ids=[result_card.id],
                evidence_quotes=[result_card.excerpt],
            ),
        ],
        research_limitations=[
            ResearchLimitation(
                text="Attention-only compression can discard structurally critical code tokens.",
                limitation_kind="failure_mode",
                target="attention-only KV cache compression",
                condition="agentic coding",
                consequence="critical code structure can be lost",
                paper_ids=[paper.id],
                evidence_ids=[limitation_card.id],
                explicitness="explicit",
            ),
            ResearchLimitation(
                text="This invalid limitation points to a mechanism sentence.",
                limitation_kind="method_limitation",
                target="CodeComp",
                consequence="unsupported consequence",
                paper_ids=[paper.id],
                evidence_ids=[mechanism_card.id],
                explicitness="explicit",
            ),
        ],
        research_gap_candidates=[
            ResearchGapCandidate(
                text="A unified evaluation protocol may be missing.",
                scope="Only within the current retrieved abstracts.",
            )
        ],
        limitations=["Only abstracts were read; this is a system warning, not a research limitation."],
        scope_warnings=["Only abstracts were read."],
    )

    ledger = _build_evidence_ledger("analysis-atomic", explanation, evidence, [paper])

    texts = [claim.text for claim in ledger.claims]
    assert explanation.technical not in texts
    assert explanation.limitations[0] not in texts
    assert len(ledger.claims) == 4
    limitation = next(claim for claim in ledger.claims if claim.claim_type == "limitation")
    assert limitation.evidence_links
    assert all(
        next(item for item in evidence if item.id == link.evidence_id).paper_id == paper.id
        for link in limitation.evidence_links
    )
    gap = next(claim for claim in ledger.claims if claim.claim_type == "research_gap")
    assert gap.status == "hypothesis"
    assert any("未进入研究局限账本" in warning for warning in ledger.warnings)


def test_abstract_evidence_keeps_mechanism_and_limitation_labels() -> None:
    sentence = (
        "We propose VidKV, a token quantization method that reduces memory, "
        "but it can cause information loss on long videos."
    )

    labels = _classify_abstract_sentence_types(sentence)

    assert "mechanism" in labels
    assert "limitation" in labels


def test_abstract_evidence_recognizes_explicit_gaps_and_failure_language() -> None:
    gap_labels = _classify_abstract_sentence_types(
        "KV cache quantization below two bits has not been investigated."
    )
    failure_labels = _classify_abstract_sentence_types(
        "Prior methods neglect the distinct roles of keys and values, leading to significant performance drops."
    )

    assert "future_work" in gap_labels
    assert "limitation" in failure_labels


def test_gap_decision_recovers_a_scoped_candidate_when_model_item_is_invalid() -> None:
    paper = PaperRecord(
        id="paper-gap",
        title="Lower-bit Cache Quantization",
        abstract="KV cache quantization below two bits has not been investigated.",
        source="fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache quantization", [paper])
    gap_card = next(item for item in evidence if "future_work" in item.evidence_types)
    explanation = ExplanationResult(
        one_sentence="A definition.",
        intuitive="An analogy.",
        technical="A technical note.",
        limitation_decisions=[
            {
                "evidence_id": gap_card.id,
                "decision": "research_gap",
                "reason": "更低比特 KV cache 量化仍需扩大检索验证。",
                "limitation_kind": None,
            }
        ],
    )

    normalized = _normalize_evolution_provenance(explanation, [paper], evidence)

    assert len(normalized.research_gap_candidates) == 1
    gap = normalized.research_gap_candidates[0]
    assert gap.evidence_ids == [gap_card.id]
    assert gap.paper_ids == [paper.id]
    assert "扩大检索" in gap.scope
    assert any("研究空白由已验证的候选裁决补全" in item for item in normalized.scope_warnings)


def test_mechanism_atomicity_rejects_multiple_operations() -> None:
    atomic = AtomicClaimDraft(
        claim_type="mechanism",
        text="The method quantizes keys and values.",
    )
    bundled = AtomicClaimDraft(
        claim_type="mechanism",
        text="The method quantizes keys and prunes value tokens.",
    )
    bundled_architecture = AtomicClaimDraft(
        claim_type="mechanism",
        text="CLLA integrates dimension reduction, layer sharing, and quantization.",
    )

    assert _is_atomic_claim(atomic) is True
    assert _is_atomic_claim(bundled) is False
    assert _is_atomic_claim(bundled_architecture) is False


def test_wrong_model_evidence_id_cannot_override_claim_alignment() -> None:
    paper = PaperRecord(
        id="paper-squat",
        title="SQuat KV Cache Quantization",
        abstract=(
            "We propose a generic KV cache compression baseline. "
            "SQuat is a method that selectively quantizes spatial tokens and retains salient spatial tokens."
        ),
        source="fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache compression", [paper])
    wrong = next(card for card in evidence if "generic" in card.excerpt)
    correct = next(card for card in evidence if "SQuat" in card.excerpt)

    matches = _match_claim_evidence(
        "SQuat selectively quantizes spatial tokens.",
        "mechanism",
        evidence,
        {paper.id: paper},
        [wrong.id],
        [paper.id],
    )

    assert matches
    assert matches[0].card.id == correct.id
    assert all(match.card.id != wrong.id for match in matches)


def test_result_claim_requires_matching_numbers() -> None:
    paper = PaperRecord(
        id="paper-result",
        title="Measured Cache Compression",
        abstract="Results show a 5.6x speedup while retaining task accuracy.",
        source="fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache compression", [paper])
    result_card = evidence[0]

    wrong = _match_claim_evidence(
        "The method achieves a 13x speedup.",
        "result",
        evidence,
        {paper.id: paper},
        [result_card.id],
        [paper.id],
        [result_card.excerpt],
    )
    correct = _match_claim_evidence(
        "The method achieves a 5.6x speedup.",
        "result",
        evidence,
        {paper.id: paper},
        [result_card.id],
        [paper.id],
        [result_card.excerpt],
    )

    assert wrong == []
    assert correct
    assert correct[0].relation == "supports"


def test_exact_same_paper_quote_survives_evidence_type_mismatch() -> None:
    paper = PaperRecord(
        id="paper-cross-language",
        title="A Cache Study",
        abstract="The practical algorithm reports promising performance on LongBench.",
        source="fixture",
        source_kind="academic",
        access_type="abstract_only",
    )
    evidence = _build_evidence("KV cache compression", [paper])
    card = evidence[0]
    assert "result" not in card.evidence_types

    matches = _match_claim_evidence(
        "该算法在 LongBench 上报告了有前景的性能。",
        "result",
        evidence,
        {paper.id: paper},
        [card.id],
        [paper.id],
        [card.excerpt],
    )

    assert matches
    assert matches[0].card.id == card.id
    assert matches[0].relation == "supports"


def test_related_concepts_stay_out_of_claim_ledger() -> None:
    explanation = ExplanationResult(
        one_sentence="A cautious definition.",
        intuitive="An analogy.",
        technical="A technical note.",
        related_concepts=["Transformer", "Token pruning"],
    )

    ledger = _build_evidence_ledger("analysis-related", explanation, [], [])

    assert all(claim.claim_type != "related_concept" for claim in ledger.claims)


def test_researcher_can_review_a_claim_evidence_link() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="demo",
        explanation_provider="rule_based",
        demo_mode=True,
    )
    try:
        created = client.post(
            "/api/v1/analyses",
            json={"concept": "Attention Mechanism", "level": "literature", "max_papers": 2},
        )
        job = _wait_for_job(created.json()["id"])
        claim = next(
            item for item in job["result"]["evidence_ledger"]["claims"]
            if item["evidence_links"]
        )
        link = claim["evidence_links"][0]

        reviewed = client.patch(
            f"/api/v1/analyses/{job['id']}/claims/{claim['id']}/evidence/{link['evidence_id']}/review",
            json={
                "relation": "supports",
                "review_note": "摘要原句与该主张直接一致。",
                "reviewed_by": "测试研究者",
            },
        )

        assert reviewed.status_code == 200
        payload = reviewed.json()["result"]
        reviewed_claim = next(
            item for item in payload["evidence_ledger"]["claims"] if item["id"] == claim["id"]
        )
        reviewed_link = reviewed_claim["evidence_links"][0]
        assert reviewed_link["origin"] == "manual"
        assert reviewed_link["verification_status"] == "reviewed"
        assert reviewed_link["reviewed_by"] == "测试研究者"
        assert payload["evidence_ledger"]["verified_coverage"] > 0
        reviewed_card = next(
            item for item in payload["evidence"] if item["id"] == link["evidence_id"]
        )
        assert reviewed_card["verification_status"] == "reviewed"
    finally:
        app.dependency_overrides.clear()
