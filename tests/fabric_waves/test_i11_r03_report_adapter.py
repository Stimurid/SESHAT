from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import seshat.fabric_waves.i11_r03_report_adapter as adapter_module
import seshat.fabric_waves.i11_two_real_r03 as source_module

from seshat.corpus_host import HostRuntime
from seshat.fabric_waves.i11_r03_report_adapter import (
    I11R03ReportAdapterError,
    IndependentScienceReview,
    project_i11_r03_into_f08,
    write_and_verify_private_report,
)
from seshat.report_demo import demo_request, install_fixture
from seshat.reports import artifacts, report_session

_case_spec = importlib.util.spec_from_file_location(
    "_seshat_i11_gate_fixture", Path(__file__).with_name("test_i11_two_real_r03.py")
)
assert _case_spec is not None and _case_spec.loader is not None
_case_module = importlib.util.module_from_spec(_case_spec)
_case_spec.loader.exec_module(_case_module)
_case = _case_module._case


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def admitted_projection():
    evidence = []
    for side, source, page, excerpt in (
        ("a", "a" * 64, 1, "first synthetic excerpt"),
        ("b", "b" * 64, 2, "second synthetic excerpt"),
    ):
        evidence.append({
            "work_id": f"synthetic-{side}", "job_id": f"jx-{side}",
            "source_pdf_sha256": source, "model_page_text_sha256": side * 64,
            "event_ledger_sha256": ("c" if side == "a" else "d") * 64,
            "terminal_receipt_sha256": ("e" if side == "a" else "f") * 64,
            "event_id": f"E-{side}", "layer": "RP", "page": page,
            "excerpt": excerpt, "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
            "evidence_verification": "VERIFIED_EXACT",
        })
    content = {
        "schema": "seshat.i11.two_real_run_r03.v2", "report_id": "R03",
        "status": "BYTE_CONSISTENT_UNATTESTED_REVIEW_PENDING", "actual_real_model_runs": 2,
        "jobs": ["jx-a", "jx-b"], "method_sha256": adapter_module.AUTHORIAL_I11_SHA256,
        "comparison_claims": [{
            "kind": "MATERIAL_DIFFERENCE", "statement": "Synthetic bounded difference.",
            "evidence": evidence, "status": "SOURCE_ADDRESSED_REVIEW_PENDING",
            "limits": "Candidate only.",
        }],
        "admission_status": "IN_PROCESS_BYTE_COHERENCE_ONLY",
        "admission_digest": "2" * 64,
        "run_manifest_digests": ["3" * 64, "4" * 64],
        "event_ledger_digests": ["c" * 64, "d" * 64],
        "terminal_receipt_digests": ["e" * 64, "f" * 64],
        "original_sources_only": None,
        "source_evidence_status": "CALLER_BYTES_PAGE_EXCERPTS_SELF_CHECKED_REVIEW_PENDING",
        "sampling_rule": "TWO_CALLER_SUPPLIED_I11_RUNS_NOT_A_POPULATION_SAMPLE",
        "coverage_status": "BOUNDED_TWO_WORK_COMPARISON",
        "implementation_missingness": {"source_a": "UNKNOWN", "source_b": "UNKNOWN"},
        "product_wiring": "NOT_PRODUCT_WIRED", "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED", "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED", "provenance": "SELF_OBSERVED_UNATTESTED",
    }
    return {**content, "projection_sha256": digest(content)}


def gated_builder_projection(monkeypatch):
    """Use the actual verified-byte builder, never caller-shaped checksum fixture."""
    items = _case(monkeypatch)
    monkeypatch.setattr(
        adapter_module, "AUTHORIAL_I11_SHA256", items[0]["method_sha256"]
    )
    admission = source_module.verify_two_run_source_admission(*items[:6])
    projection = source_module.build_two_real_i11_r03(
        items[0], items[1], items[4], items[5], items[6], admission=admission
    )
    return projection, admission


def review_for(projection, disposition="PASS"):
    return IndependentScienceReview(
        projection_sha256=projection["projection_sha256"],
        disposition=disposition,
        review_id="synthetic-independent-test-review",
    )


def unverified_projection():
    content = {
        "schema": "seshat.i11.two_real_run_r03.v2", "report_id": "R03",
        "status": "UNVERIFIED_INPUTS", "actual_real_model_runs": 0,
        "candidate_jobs": ["jx-fake-a", "jx-fake-b"], "comparison_claims": [],
        "admission_status": "UNVERIFIED_CALLER_ASSERTIONS",
        "product_wiring": "NOT_PRODUCT_WIRED", "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED", "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED", "provenance": "SELF_OBSERVED_UNATTESTED",
    }
    return {**content, "projection_sha256": digest(content)}


def base_report(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    runtime: HostRuntime = install_fixture(fixture, "sechenovka-like")
    return report_session(
        runtime, authenticated_caller="demo", authorized_view="synthetic-public"
    )(demo_request("R03"))


def test_real_f08_r03_composes_candidate_html_and_stable_private_readback(tmp_path, monkeypatch):
    base = base_report(tmp_path)
    source, admission = gated_builder_projection(monkeypatch)
    before = base.model_dump(mode="json")
    projected = project_i11_r03_into_f08(
        base, source, admission=admission, independent_review=review_for(source)
    )
    assert projected.status == "PARTIAL_METADATA"
    assert projected.scientific_acceptance == "NOT_ASSERTED"
    assert projected.source_state == "METADATA_ONLY"
    assert projected.selections == base.selections
    assert projected.sections[:len(base.sections)] == base.sections
    assert projected.evidence[:len(base.evidence)] == base.evidence
    assert base.model_dump(mode="json") == before
    candidate = projected.sections[-1].claims[0]
    assert candidate.state == "BLOCKED"
    assert "Distinct author-reported operations" in str(candidate.value)
    assert "comparison sampling rule" in [c.label for c in projected.sections[-1].claims]
    assert "candidate 1 limitations" in [c.label for c in projected.sections[-1].claims]
    files = artifacts(projected)
    assert b"I11 source comparison / CANDIDATE" in files["report.html"]
    assert b"alpha exact asserted phrase" not in b"".join(files.values())
    output = tmp_path / "private-report"
    first = write_and_verify_private_report(output, projected)
    second = write_and_verify_private_report(output, projected)
    checked = write_and_verify_private_report(output, projected, verify_only=True)
    assert first == second == checked
    assert first.report_json_sha256 == hashlib.sha256((output / "report.json").read_bytes()).hexdigest()


def test_unverified_fake_two_runs_block_without_substantive_claims(tmp_path):
    result = project_i11_r03_into_f08(base_report(tmp_path), unverified_projection())
    assert result.status == "BLOCKED"
    assert result.sections[-1].title.endswith("BLOCKED")
    assert "byte admission is absent" in str(result.sections[-1].claims[0].value)
    assert "candidate comparison" not in artifacts(result)["report.html"].decode()


def test_fake_verified_shape_without_byte_admission_fields_is_rejected(tmp_path):
    fake = unverified_projection()
    fake.update(status="BYTE_CONSISTENT_UNATTESTED_REVIEW_PENDING", actual_real_model_runs=2,
                admission_status="IN_PROCESS_BYTE_COHERENCE_ONLY")
    fake["projection_sha256"] = digest({k: v for k, v in fake.items()
                                        if k != "projection_sha256"})
    with pytest.raises(I11R03ReportAdapterError, match="ADMITTED_SHAPE_INCOMPLETE"):
        project_i11_r03_into_f08(base_report(tmp_path), fake)


def test_digest_authority_v1_and_review_spoofs_fail_closed(tmp_path, monkeypatch):
    base = base_report(tmp_path)
    source, admission = gated_builder_projection(monkeypatch)
    for mutate, expected in (
        (lambda p: p.update(projection_sha256="0" * 64), "PROJECTION_DIGEST_MISMATCH"),
        (lambda p: p.update(scientific_acceptance="ACCEPTED"), "scientific_acceptance"),
        (lambda p: p.update(schema="seshat.i11.two_real_run_r03.v1"), "schema"),
    ):
        value = dict(source)
        mutate(value)
        with pytest.raises(I11R03ReportAdapterError, match=expected):
            project_i11_r03_into_f08(base, value, admission=admission)


def test_old_nine_claim_v1_review_fail_sample_is_not_imported(tmp_path):
    old = {
        "schema": "seshat.i11.private_r03.v1",
        "report_id": "R03",
        "review": "FAIL",
        "claims": [{"statement": f"rejected-old-claim-{index}"} for index in range(9)],
    }
    with pytest.raises(I11R03ReportAdapterError, match="schema"):
        project_i11_r03_into_f08(base_report(tmp_path), old)


def test_review_fail_and_mismatch_emit_no_comparison(tmp_path, monkeypatch):
    base = base_report(tmp_path)
    source, admission = gated_builder_projection(monkeypatch)
    failed = IndependentScienceReview(
        projection_sha256=source["projection_sha256"], disposition="FAIL", review_id="review-1"
    )
    blocked = project_i11_r03_into_f08(base, source, admission=admission, independent_review=failed)
    assert blocked.status == "BLOCKED"
    assert all("Distinct author-reported operations" not in str(c.value)
               for s in blocked.sections for c in s.claims)
    mismatch = failed.model_copy(update={"projection_sha256": "9" * 64})
    with pytest.raises(I11R03ReportAdapterError, match="REVIEW_PROJECTION_MISMATCH"):
        project_i11_r03_into_f08(base, source, admission=admission, independent_review=mismatch)
    with pytest.raises(ValidationError):
        IndependentScienceReview.model_validate({
            **failed.model_dump(), "scientific_acceptance": "ACCEPTED"
        })


def test_incomplete_source_evidence_blocks_and_does_not_leak_statement(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    source["comparison_claims"][0]["evidence"][0]["evidence_verification"] = "NORMALIZED_ONLY"
    source["comparison_claims"][0]["status"] = "EVIDENCE_VERIFICATION_REVIEW_PENDING"
    source["projection_sha256"] = digest({k: v for k, v in source.items()
                                          if k != "projection_sha256"})
    blocked = project_i11_r03_into_f08(
        base_report(tmp_path), source, admission=admission, independent_review=review_for(source)
    )
    assert blocked.status == "BLOCKED"
    assert "SOURCE_EVIDENCE_INCOMPLETE" in str(blocked.sections[-1].claims[0].value)
    assert b"Distinct author-reported operations" not in artifacts(blocked)["report.json"]


def test_stale_projection_and_report_readback_are_explicit(tmp_path, monkeypatch):
    base = base_report(tmp_path)
    source, admission = gated_builder_projection(monkeypatch)
    stale = base.model_copy(update={"digest": "0" * 64})
    with pytest.raises(I11R03ReportAdapterError, match="BASE_PROJECTION_DIGEST_MISMATCH"):
        project_i11_r03_into_f08(stale, source)
    projected = project_i11_r03_into_f08(
        base, source, admission=admission, independent_review=review_for(source)
    )
    output = tmp_path / "private-report"
    with pytest.raises(I11R03ReportAdapterError, match="MISSING_REPORT"):
        write_and_verify_private_report(output, projected, verify_only=True)
    write_and_verify_private_report(output, projected)
    (output / "report.html").write_bytes(b"stale")
    with pytest.raises(I11R03ReportAdapterError, match="STALE_REPORT"):
        write_and_verify_private_report(output, projected, verify_only=True)


def test_rights_bound_metadata_is_unchanged_even_with_review_pass(tmp_path, monkeypatch):
    base = base_report(tmp_path)
    source, admission = gated_builder_projection(monkeypatch)
    review = IndependentScienceReview(
        projection_sha256=source["projection_sha256"], disposition="PASS", review_id="review-pass"
    )
    projected = project_i11_r03_into_f08(base, source, admission=admission, independent_review=review)
    assert projected.rights_scope == base.rights_scope
    assert projected.selections == base.selections
    assert projected.sections[:-1] == base.sections
    assert projected.scientific_acceptance == "NOT_ASSERTED"
    assert projected.sections[-1].claims[0].state == "BLOCKED"
    assert projected.blocks == base.blocks


def test_caller_forged_admitted_projection_cannot_show_comparison(tmp_path):
    fake = admitted_projection()
    result = project_i11_r03_into_f08(
        base_report(tmp_path), fake, independent_review=review_for(fake)
    )
    assert result.status == "BLOCKED"
    assert "GATE_ADMISSION_REQUIRED" in str(result.sections[-1].claims[0].value)
    assert "Synthetic bounded difference" not in artifacts(result)["report.html"].decode()


def test_genuine_builder_with_gate_but_no_review_remains_blocked(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    result = project_i11_r03_into_f08(base_report(tmp_path), source, admission=admission)
    assert result.status == "BLOCKED"
    assert "INDEPENDENT_SCIENCE_REVIEW_REQUIRED" in str(result.sections[-1].claims[0].value)


def test_pins_and_admission_are_bound_even_when_self_checksum_recomputed(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    base = base_report(tmp_path)
    tampered = json.loads(json.dumps(source))
    tampered["admission_digest"] = "a" * 64
    tampered["projection_sha256"] = digest({k: v for k, v in tampered.items()
                                          if k != "projection_sha256"})
    with pytest.raises(I11R03ReportAdapterError, match="ADMISSION_BINDING_MISMATCH"):
        project_i11_r03_into_f08(base, tampered,
                                  admission=admission, independent_review=review_for(tampered))
    bad_evidence = json.loads(json.dumps(source))
    bad_evidence["comparison_claims"][0]["evidence"][0]["event_ledger_sha256"] = "f" * 64
    bad_evidence["projection_sha256"] = digest({k: v for k, v in bad_evidence.items()
                                              if k != "projection_sha256"})
    with pytest.raises(I11R03ReportAdapterError, match="EVIDENCE_TOP_LEVEL_PIN_MISMATCH"):
        project_i11_r03_into_f08(base, bad_evidence,
                                  admission=admission)


def test_excerpt_must_be_on_original_gate_verified_page(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    forged = json.loads(json.dumps(source))
    ev = forged["comparison_claims"][0]["evidence"][0]
    ev["excerpt"] = "invented phrase absent from original model page"
    ev["excerpt_sha256"] = hashlib.sha256(ev["excerpt"].encode()).hexdigest()
    forged["projection_sha256"] = digest({k: v for k, v in forged.items()
                                        if k != "projection_sha256"})
    result = project_i11_r03_into_f08(
        base_report(tmp_path), forged, admission=admission,
        independent_review=review_for(forged)
    )
    assert result.status == "BLOCKED"
    assert "SOURCE_EVIDENCE_INCOMPLETE" in str(result.sections[-1].claims[0].value)


def test_duplicate_comparison_projection_rejected(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    base = base_report(tmp_path)
    once = project_i11_r03_into_f08(
        base, source, admission=admission, independent_review=review_for(source)
    )
    with pytest.raises(I11R03ReportAdapterError, match="ALREADY_PROJECTED"):
        project_i11_r03_into_f08(
            once, source, admission=admission, independent_review=review_for(source)
        )


@pytest.mark.parametrize("field", (
    "work_id", "job_id", "source_pdf_sha256", "model_page_text_sha256",
))
def test_admitted_source_identity_pins_cannot_be_rebound(
    tmp_path, monkeypatch, field,
):
    source, admission = gated_builder_projection(monkeypatch)
    tampered = json.loads(json.dumps(source))
    evidence = tampered["comparison_claims"][0]["evidence"][0]
    if field == "job_id":
        value = "jx-forged-identity"
        tampered["jobs"][0] = value
    elif field in ("source_pdf_sha256", "model_page_text_sha256"):
        value = "9" * 64
    else:
        value = "invented-source-id"
    evidence[field] = value
    tampered["projection_sha256"] = digest({
        key: value for key, value in tampered.items()
        if key != "projection_sha256"
    })
    with pytest.raises(I11R03ReportAdapterError, match="SOURCE_IDENTITY_PIN_MISMATCH"):
        project_i11_r03_into_f08(
            base_report(tmp_path), tampered, admission=admission,
            independent_review=review_for(tampered),
        )


def test_admitted_source_status_never_claims_original_authority(tmp_path, monkeypatch):
    source, admission = gated_builder_projection(monkeypatch)
    assert source["status"] == "BYTE_CONSISTENT_UNATTESTED_REVIEW_PENDING"
    assert source["admission_status"] == "IN_PROCESS_BYTE_COHERENCE_ONLY"
    assert source["original_sources_only"] is None
    assert source["provenance"] == "SELF_OBSERVED_UNATTESTED"
    report = project_i11_r03_into_f08(
        base_report(tmp_path), source, admission=admission,
        independent_review=review_for(source),
    )
    html = artifacts(report)["report.html"].decode("utf-8")
    assert "review=PASS" not in html
    assert "CALLER_SUBMITTED_UNATTESTED_NOT_SCIENTIFIC_ACCEPTANCE" in html
    assert report.status == "PARTIAL_METADATA"
