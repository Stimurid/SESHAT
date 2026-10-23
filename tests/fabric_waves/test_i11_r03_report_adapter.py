from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from seshat.corpus_host import HostRuntime
from seshat.fabric_waves.i11_r03_report_adapter import (
    I11R03ReportAdapterError,
    IndependentScienceReview,
    project_i11_r03_into_f08,
    write_and_verify_private_report,
)
from seshat.report_demo import demo_request, install_fixture
from seshat.reports import artifacts, report_session


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
        "status": "VERIFIED_SOURCE_ADMISSION_REVIEW_PENDING", "actual_real_model_runs": 2,
        "jobs": ["jx-a", "jx-b"], "method_sha256": "1" * 64,
        "comparison_claims": [{
            "kind": "MATERIAL_DIFFERENCE", "statement": "Synthetic bounded difference.",
            "evidence": evidence, "status": "SOURCE_ADDRESSED_REVIEW_PENDING",
            "limits": "Candidate only.",
        }],
        "admission_status": "VERIFIED_REAL_TWO_RUN_SOURCE_ADMISSION",
        "admission_digest": "2" * 64,
        "run_manifest_digests": ["3" * 64, "4" * 64],
        "event_ledger_digests": ["5" * 64, "6" * 64],
        "terminal_receipt_digests": ["7" * 64, "8" * 64],
        "original_sources_only": True,
        "source_evidence_status": "BYTE_AND_PAGE_EXCERPT_VERIFIED_WITH_REVIEW_PENDING",
        "sampling_rule": "TWO_OWNER_SELECTED_ORIGINAL_I11_RUNS_NOT_A_POPULATION_SAMPLE",
        "coverage_status": "BOUNDED_TWO_WORK_COMPARISON",
        "implementation_missingness": {"source_a": "UNKNOWN", "source_b": "UNKNOWN"},
        "product_wiring": "NOT_PRODUCT_WIRED", "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED", "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED", "provenance": "SELF_OBSERVED_UNATTESTED",
    }
    return {**content, "projection_sha256": digest(content)}


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


def test_real_f08_r03_composes_candidate_html_and_stable_private_readback(tmp_path):
    base = base_report(tmp_path)
    before = base.model_dump(mode="json")
    projected = project_i11_r03_into_f08(base, admitted_projection())
    assert projected.status == "SOURCE_GROUNDED_UNREVIEWED"
    assert projected.scientific_acceptance == "NOT_ASSERTED"
    assert projected.selections == base.selections
    assert projected.sections[:len(base.sections)] == base.sections
    assert projected.evidence[:len(base.evidence)] == base.evidence
    assert base.model_dump(mode="json") == before
    candidate = projected.sections[-1].claims[0]
    assert candidate.state == "BLOCKED"
    assert "Synthetic bounded difference" in str(candidate.value)
    files = artifacts(projected)
    assert b"I11 source comparison / CANDIDATE" in files["report.html"]
    assert b"first synthetic excerpt" not in b"".join(files.values())
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
    fake.update(status="VERIFIED_SOURCE_ADMISSION_REVIEW_PENDING", actual_real_model_runs=2,
                admission_status="VERIFIED_REAL_TWO_RUN_SOURCE_ADMISSION")
    fake["projection_sha256"] = digest({k: v for k, v in fake.items()
                                        if k != "projection_sha256"})
    with pytest.raises(I11R03ReportAdapterError, match="ADMITTED_SHAPE_INCOMPLETE"):
        project_i11_r03_into_f08(base_report(tmp_path), fake)


def test_digest_authority_v1_and_review_spoofs_fail_closed(tmp_path):
    base = base_report(tmp_path)
    for mutate, expected in (
        (lambda p: p.update(projection_sha256="0" * 64), "PROJECTION_DIGEST_MISMATCH"),
        (lambda p: p.update(scientific_acceptance="ACCEPTED"), "scientific_acceptance"),
        (lambda p: p.update(schema="seshat.i11.two_real_run_r03.v1"), "schema"),
    ):
        value = admitted_projection()
        mutate(value)
        with pytest.raises(I11R03ReportAdapterError, match=expected):
            project_i11_r03_into_f08(base, value)


def test_old_nine_claim_v1_review_fail_sample_is_not_imported(tmp_path):
    old = {
        "schema": "seshat.i11.private_r03.v1",
        "report_id": "R03",
        "review": "FAIL",
        "claims": [{"statement": f"rejected-old-claim-{index}"} for index in range(9)],
    }
    with pytest.raises(I11R03ReportAdapterError, match="schema"):
        project_i11_r03_into_f08(base_report(tmp_path), old)


def test_review_fail_and_mismatch_emit_no_comparison(tmp_path):
    base, source = base_report(tmp_path), admitted_projection()
    failed = IndependentScienceReview(
        projection_sha256=source["projection_sha256"], disposition="FAIL", review_id="review-1"
    )
    blocked = project_i11_r03_into_f08(base, source, independent_review=failed)
    assert blocked.status == "BLOCKED"
    assert all("Synthetic bounded difference" not in str(c.value)
               for s in blocked.sections for c in s.claims)
    mismatch = failed.model_copy(update={"projection_sha256": "9" * 64})
    with pytest.raises(I11R03ReportAdapterError, match="REVIEW_PROJECTION_MISMATCH"):
        project_i11_r03_into_f08(base, source, independent_review=mismatch)
    with pytest.raises(ValidationError):
        IndependentScienceReview.model_validate({
            **failed.model_dump(), "scientific_acceptance": "ACCEPTED"
        })


def test_incomplete_source_evidence_blocks_and_does_not_leak_statement(tmp_path):
    source = admitted_projection()
    source["comparison_claims"][0]["evidence"][0]["evidence_verification"] = "NORMALIZED_ONLY"
    source["comparison_claims"][0]["status"] = "EVIDENCE_VERIFICATION_REVIEW_PENDING"
    source["projection_sha256"] = digest({k: v for k, v in source.items()
                                          if k != "projection_sha256"})
    blocked = project_i11_r03_into_f08(base_report(tmp_path), source)
    assert blocked.status == "BLOCKED"
    assert "SOURCE_EVIDENCE_INCOMPLETE" in str(blocked.sections[-1].claims[0].value)
    assert b"Synthetic bounded difference" not in artifacts(blocked)["report.json"]


def test_stale_projection_and_report_readback_are_explicit(tmp_path):
    base = base_report(tmp_path)
    stale = base.model_copy(update={"digest": "0" * 64})
    with pytest.raises(I11R03ReportAdapterError, match="BASE_PROJECTION_DIGEST_MISMATCH"):
        project_i11_r03_into_f08(stale, admitted_projection())
    projected = project_i11_r03_into_f08(base, admitted_projection())
    output = tmp_path / "private-report"
    with pytest.raises(I11R03ReportAdapterError, match="MISSING_REPORT"):
        write_and_verify_private_report(output, projected, verify_only=True)
    write_and_verify_private_report(output, projected)
    (output / "report.html").write_bytes(b"stale")
    with pytest.raises(I11R03ReportAdapterError, match="STALE_REPORT"):
        write_and_verify_private_report(output, projected, verify_only=True)


def test_rights_bound_metadata_is_unchanged_even_with_review_pass(tmp_path):
    base, source = base_report(tmp_path), admitted_projection()
    review = IndependentScienceReview(
        projection_sha256=source["projection_sha256"], disposition="PASS", review_id="review-pass"
    )
    projected = project_i11_r03_into_f08(base, source, independent_review=review)
    assert projected.rights_scope == base.rights_scope
    assert projected.selections == base.selections
    assert projected.sections[:-1] == base.sections
    assert projected.scientific_acceptance == "NOT_ASSERTED"
    assert projected.sections[-1].claims[0].state == "BLOCKED"
    assert projected.blocks == base.blocks
