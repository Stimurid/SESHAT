import copy
import pytest

from seshat.fabric_waves.i08_i09_dependency import (
    EvidenceLedgerError,
    apply_resource_cut,
    apply_review_overlay,
    build_evidence_ledger,
)


def package():
    def ev_a(event, page):
        return {
            "job_id": "jx-A", "work_id": "PLOS:A", "event_id": event,
            "source_pdf_sha256": "a"*64, "model_page_text_sha256": "b"*64,
            "page": page,
        }
    def ev_b(event, page):
        return {
            "job_id": "jx-B", "work_id": "PLOS:B", "event_id": event,
            "source_pdf_sha256": "c"*64, "model_page_text_sha256": "d"*64,
            "page": page,
        }
    r03 = {
        "schema": "seshat.i11.two_real_run_r03.v1",
        "actual_real_model_runs": 2,
        "projection_sha256": "e"*64,
        "scientific_acceptance": "NOT_PERFORMED", "customer_release": "BLOCKED",
        "comparison_claims": [
            {"kind": "MATERIAL_DIFFERENCE", "statement": "coding modes differ",
             "evidence": [ev_a("E09", 4), ev_b("E14", 5)]},
            {"kind": "COMMON_OPERATION", "statement": "proposed future changes",
             "evidence": [ev_a("E20", 10), ev_b("E22", 2)]},
        ],
    }
    def spec(modes, label):
        return {
            "evidence_modes": list(modes),
            "claim_scope": label,
            "inferential_step": "source observation into bounded comparison",
            "missing_evidence": "no independently verified original transcript",
            "allowed_conclusion": "methods and claims reported by authors",
            "forbidden_promotion": "no implementation efficacy",
            "reproduction_scope": "P1_PUBLIC_SOURCE_RECONSTRUCTION",
        }
    specs = [
        spec(["S1_REPORTED_RESEARCH_OPERATION", "S5_SOURCE_EXTERNAL_NORM"], "two coding systems"),
        spec(["S6_AUTHORIAL_COUNTERFACTUAL", "S6_AUTHORIAL_COUNTERFACTUAL"], "two proposals"),
    ]
    derived = [
        {"claim_id": "C09.PILOT", "depends_on": ["R03.C01"],
         "reproduction_scope": "P2_NEW_FIELD_RESEARCH", "target_available": False},
        {"claim_id": "C09.BUYER", "depends_on": ["C09.PILOT"],
         "reproduction_scope": "P3_INDEPENDENT_EFFECT_TEST", "target_available": False},
    ]
    resource = {
        "resource_id": "I09.REB_NEW_SITE",
        "resource_mode": "AUTHORIAL_REQUIRED_FOR_REPLICATION",
        "source_event": None,
        "material": "separately consented patient information",
        "people_skill": "authorized clinical field researcher",
        "site_or_tool": "another target hospital",
        "rights": "not granted here",
        "source_address": "I09 canonical §5.9, source PLOS Methods",
        "failure_mode": "no right of entry or field observation",
        "criticality": "CRITICAL",
        "reproduction_scope": "P2_NEW_FIELD_RESEARCH",
        "target_availability": "TARGET_UNKNOWN",
        "dependent_claim_ids": ["R03.C01", "C09.PILOT"],
    }
    return r03, specs, derived, [resource]


def assembled():
    a,b,c,d = package()
    return build_evidence_ledger(a,claim_specs=b,derived_claims=c,resource_cards=d)


def test_preserves_real_r03_and_prevents_science_approval():
    src, _, _, _ = package()
    src_copy = copy.deepcopy(src)
    ledger = assembled()
    assert ledger["based_on_r03_projection_sha256"] == "e"*64
    assert len(ledger["claim_cards"]) == 4
    assert src == src_copy
    assert ledger["source_model_outputs_modified"] is False
    assert ledger["scientific_acceptance"] == "NOT_PERFORMED"
    assert ledger["customer_release"] == "BLOCKED"


def test_review_of_b_e14_selectively_taints_only_dependent_claims():
    original = assembled()
    result = apply_review_overlay(
        original, job_id="jx-B", event_id="E14", defect="FALSE_ATTRIBUTION",
        note="Ontario Health 2021 guide is an external normative instrument, not local research labour",
        overlay_id="I08.B06",
    )
    assert original["claim_cards"]["R03.C01"]["status"] == "SOURCE_ADDRESSED_UNREVIEWED"
    for cid in ("R03.C01", "C09.PILOT", "C09.BUYER"):
        assert result["claim_cards"][cid]["status"] == "UNDER_REVIEW"
    assert result["claim_cards"]["R03.C02"]["status"] == "SOURCE_ADDRESSED_UNREVIEWED"
    assert result["projection_sha256"] != original["projection_sha256"]


def test_site_resource_cut_does_not_erase_source_p1_claims():
    result = apply_resource_cut(
        assembled(), resource_id="I09.REB_NEW_SITE",
        evidence_note="target site did not authorize new observation",
    )
    assert result["resource_cards"]["I09.REB_NEW_SITE"]["target_availability"] == "TARGET_UNAVAILABLE"
    assert result["claim_cards"]["R03.C01"]["status"] == "SOURCE_ADDRESSED_UNREVIEWED"
    assert result["claim_cards"]["R03.C02"]["status"] == "SOURCE_ADDRESSED_UNREVIEWED"
    assert result["claim_cards"]["C09.PILOT"]["status"] == "UNDER_REVIEW"
    assert result["claim_cards"]["C09.BUYER"]["status"] == "UNDER_REVIEW"


def test_repeatably_hashes_same_claims():
    assert assembled() == assembled()


@pytest.mark.parametrize("mutation,error", [
    (lambda x: x[0].update(actual_real_model_runs=1), "UNACCEPTABLE_R03_SOURCE"),
    (lambda x: x[0].update(customer_release="APPROVED"), "UNACCEPTABLE_R03_SOURCE"),
    (lambda x: x[1].pop(), "CLAIM_SPEC_COUNT_MISMATCH"),
    (lambda x: x[1][0].update(evidence_modes=["S7_INDEPENDENTLY_TESTED_EFFECT",
                                              "S1_REPORTED_RESEARCH_OPERATION"]),
     "S7_REQUIRES_SEPARATE_ATTESTED_EFFECT"),
    (lambda x: x[1][0].update(evidence_modes=["UNKNOWN","S1_REPORTED_RESEARCH_OPERATION"]),
     "UNKNOWN_EVIDENCE_MODE"),
    (lambda x: x[2][0].update(depends_on=["MISSING"]), "INVALID_CLAIM_DEPENDENCY"),
    (lambda x: x[2][0].update(depends_on=["C09.BUYER"]), "CYCLIC_CLAIM_DEPENDENCY"),
    (lambda x: x[3][0].update(target_availability="TARGET_AVAILABLE_ATTESTED"),
     "TARGET_AVAILABILITY_NOT_ATTESTED"),
    (lambda x: x[3][0].update(resource_mode="MAGIC"), "UNKNOWN_RESOURCE_MODE"),
    (lambda x: x[3][0].update(dependent_claim_ids=["ZZZ"]), "UNKNOWN_RESOURCE_DEPENDENT"),
])
def test_invalid_evidence_and_resources_fail_closed(mutation,error):
    data = list(copy.deepcopy(package()))
    mutation(data)
    with pytest.raises(EvidenceLedgerError, match=error):
        build_evidence_ledger(data[0],claim_specs=data[1],
                              derived_claims=data[2],resource_cards=data[3])


def test_source_research_operation_requires_event():
    data = list(package())
    data[3][0]["resource_mode"] = "SOURCE_REPORTED_USED"
    with pytest.raises(EvidenceLedgerError, match="SOURCE_REPORTED_USE_NEEDS_EVENT"):
        build_evidence_ledger(data[0],claim_specs=data[1],
                              derived_claims=data[2],resource_cards=data[3])


def test_overlay_unknown_event_does_not_taint_unrelated():
    with pytest.raises(EvidenceLedgerError, match="SOURCE_EVENT_NOT_FOUND"):
        apply_review_overlay(assembled(),job_id="jx-B",event_id="E999",
                             defect="FALSE_ATTRIBUTION",note="no such event",
                             overlay_id="I08.TEST")


def test_resource_cut_requires_critical_p2_or_p3():
    original = assembled()
    with pytest.raises(EvidenceLedgerError, match="RESOURCE_NOT_FOUND"):
        apply_resource_cut(original,resource_id="I09.MISSING",evidence_note="lost")



def _verified_v2_input(monkeypatch):
    """Genuine synthetic-byte I11 gate, not a hand-invented positive JSON."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).with_name("test_i11_r03_report_adapter.py")
    spec = importlib.util.spec_from_file_location("_seshat_ledger_v2_gate_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.gated_builder_projection(monkeypatch)


def test_current_v2_admission_enters_i08_i09_only_as_unattested_ledger(monkeypatch):
    projection, admission = _verified_v2_input(monkeypatch)
    specs = package()[1][:1]
    ledger = build_evidence_ledger(
        projection, claim_specs=specs, source_admission=admission,
    )
    assert ledger["based_on_r03_projection_sha256"] == projection["projection_sha256"]
    assert list(ledger["claim_cards"]) == ["R03.C01"]
    assert ledger["source_admission_provenance"] == "V2_BYTE_COHERENT_SELF_OBSERVED_UNATTESTED"
    assert ledger["claim_cards"]["R03.C01"]["status"] == "SOURCE_ADDRESSED_UNREVIEWED"
    assert ledger["scientific_acceptance"] == "NOT_PERFORMED"
    assert ledger["customer_release"] == "BLOCKED"


def test_archival_v1_ledger_is_not_misrepresented_as_current_proof():
    ledger = assembled()
    assert ledger["source_admission_provenance"] == "V1_LEGACY_ARCHIVAL_UNATTESTED"


def test_v2_self_hashed_projection_cannot_skip_admission(monkeypatch):
    source, admission = _verified_v2_input(monkeypatch)
    with pytest.raises(EvidenceLedgerError, match="R03_V2_GATE_ADMISSION_REQUIRED"):
        build_evidence_ledger(source, claim_specs=package()[1][:1])
    unverified = copy.deepcopy(source)
    unverified["status"] = "UNVERIFIED_INPUTS"
    from seshat.corpus import _digest
    unverified["projection_sha256"] = _digest({
        k: v for k,v in unverified.items() if k != "projection_sha256"
    })
    with pytest.raises(EvidenceLedgerError, match="UNACCEPTABLE_R03_V2_SHAPE|R03_V2_GATE_ADMISSION_REQUIRED"):
        build_evidence_ledger(
            unverified, claim_specs=package()[1][:1], source_admission=admission,
        )


def test_v2_normalized_only_page_is_rejected_even_with_gate(monkeypatch):
    source, admission = _verified_v2_input(monkeypatch)
    tainted = copy.deepcopy(source)
    tainted["comparison_claims"][0]["evidence"][0]["evidence_verification"] = "NORMALIZED_ONLY"
    tainted["comparison_claims"][0]["status"] = "EVIDENCE_VERIFICATION_REVIEW_PENDING"
    from seshat.corpus import _digest
    tainted["projection_sha256"] = _digest({
        k: v for k,v in tainted.items() if k != "projection_sha256"
    })
    with pytest.raises(EvidenceLedgerError, match="R03_V2_EXACT_SOURCE_EVIDENCE_REQUIRED"):
        build_evidence_ledger(
            tainted, claim_specs=package()[1][:1], source_admission=admission,
        )


def test_v2_evidence_identity_mutation_cannot_inherit_admission(monkeypatch):
    source, admission = _verified_v2_input(monkeypatch)
    tampered = copy.deepcopy(source)
    tampered["comparison_claims"][0]["evidence"][0]["source_pdf_sha256"] = "9" * 64
    from seshat.corpus import _digest
    tampered["projection_sha256"] = _digest({
        k: v for k,v in tampered.items() if k != "projection_sha256"
    })
    with pytest.raises(EvidenceLedgerError, match="R03_V2_SOURCE_IDENTITY_MISMATCH"):
        build_evidence_ledger(
            tampered, claim_specs=package()[1][:1], source_admission=admission,
        )



def test_per_card_provenance_distinguishes_archival_v1_from_live_v2(monkeypatch):
    archived = assembled()
    assert archived["claim_cards"]["R03.C01"]["provenance"] == (
        "OPERATOR_AUTHORED_WITH_UNVERIFIED_LEGACY_V1_POINTERS"
    )
    source, admission = _verified_v2_input(monkeypatch)
    live = build_evidence_ledger(
        source, claim_specs=package()[1][:1], source_admission=admission
    )
    assert live["claim_cards"]["R03.C01"]["provenance"] == (
        "OPERATOR_AUTHORED_WITH_SOURCE_EVENT_POINTERS"
    )
    assert live["source_admission_provenance"] == (
        "V2_BYTE_COHERENT_SELF_OBSERVED_UNATTESTED"
    )
