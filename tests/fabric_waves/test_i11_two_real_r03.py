from __future__ import annotations

import copy

import pytest

from seshat.fabric_waves.i11_two_real_r03 import (
    TwoRealI11R03Error,
    build_two_real_i11_r03,
)


def _sample():
    a = {
        "job_id": "jx-first", "work_id": "published-a", "run_state": "SUCCEEDED",
        "source_kind": "REAL_PUBLISHED", "page_count": 12,
        "source_pdf_sha256": "a" * 64,
        "model_page_text_sha256": "b" * 64,
        "stdout_sha256": "c" * 64, "method_sha256": "d" * 64,
        "scientific_acceptance": "NOT_ASSERTED", "customer_release": "BLOCKED",
    }
    b = {
        **a, "job_id": "jx-second", "work_id": "published-b",
        "page_count": 17, "source_pdf_sha256": "e" * 64,
        "model_page_text_sha256": "f" * 64, "stdout_sha256": "0" * 64,
    }
    e_a = [{"event_id": "E01", "layer": "RP", "pages": [2]}]
    e_b = [{"event_id": "E02", "layer": "RP", "pages": [4]}]
    claims = [{
        "kind": "MATERIAL_DIFFERENCE", "event_a": "E01", "page_a": 2,
        "event_b": "E02", "page_b": 4,
        "statement": "Distinct empirically described operations.",
        "limits": "These are author claims, not measured causal efficacy.",
    }]
    return a, b, e_a, e_b, claims


def _build(items):
    return build_two_real_i11_r03(*items)


def test_two_real_runs_produce_two_page_evidence_and_provisional_only():
    result = _build(_sample())
    assert result["actual_real_model_runs"] == 2
    assert len(result["comparison_claims"][0]["evidence"]) == 2
    assert [x["page"] for x in result["comparison_claims"][0]["evidence"]] == [2, 4]
    assert result["scientific_acceptance"] == "NOT_PERFORMED"
    assert result["customer_release"] == "BLOCKED"
    assert result["status"] == "SOURCE_GROUNDED_UNREVIEWED"
    assert len(result["projection_sha256"]) == 64


@pytest.mark.parametrize("change,expected", [
    (lambda d: d[1].update(job_id=d[0]["job_id"]), "I11_NOT_TWO_DISTINCT_RUNS"),
    (lambda d: d[1].update(source_pdf_sha256=d[0]["source_pdf_sha256"]), "I11_NOT_TWO_DISTINCT_RUNS"),
    (lambda d: d[1].update(model_page_text_sha256=d[0]["model_page_text_sha256"]), "I11_NOT_TWO_DISTINCT_RUNS"),
    (lambda d: d[1].update(method_sha256="3"*64), "I11_METHOD_VERSION_MISMATCH"),
    (lambda d: d[0].update(source_kind="TEST_ONLY_FICTIONAL"), "I11_REAL_TERMINAL_REQUIRED"),
    (lambda d: d[1].update(run_state="QUEUED"), "I11_REAL_TERMINAL_REQUIRED"),
    (lambda d: d[1].update(scientific_acceptance="ACCEPTED"), "I11_OWNER_ACCEPTANCE_SPOOF"),
    (lambda d: d[0].update(customer_release="AUTHORIZED"), "I11_CUSTOMER_RELEASE_SPOOF"),
    (lambda d: d[0].update(stdout_sha256="fake"), "I11_INVALID_PIN_STDOUT_SHA256"),
    (lambda d: d[4][0].update(event_b="E999"), "I11_COMPARISON_EVENT_NOT_FOUND"),
    (lambda d: d[4][0].update(page_b=18), "I11_COMPARISON_PAGE_UNVERIFIED"),
    (lambda d: d[4][0].update(page_a=True), "I11_COMPARISON_PAGE_UNVERIFIED"),
    (lambda d: d[4][0].update(kind="PROVED_EFFECTIVENESS"), "I11_INVALID_COMPARISON_KIND"),
    (lambda d: d[4][0].update(statement=" "), "I11_EMPTY_COMPARISON"),
    (lambda d: d[3].append(d[3][0].copy()), "I11_EVENT_ID_DUPLICATED"),
])
def test_rejects_fake_comparative_admission(change, expected):
    args = copy.deepcopy(_sample())
    args = list(args)
    change(args)
    with pytest.raises(TwoRealI11R03Error, match=expected):
        _build(args)


def test_rejects_empty_claims():
    args = list(_sample())
    args[4] = []
    with pytest.raises(TwoRealI11R03Error, match="I11_COMPARATIVE_CLAIMS_MISSING"):
        _build(args)


def test_repeat_is_deterministic():
    sample = _sample()
    assert _build(sample) == _build(sample)
