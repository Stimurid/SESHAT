from __future__ import annotations

import copy
import hashlib
import json

import pytest

import seshat.fabric_waves.i11_two_real_r03 as subject
from seshat.fabric_waves.i11_two_real_r03 import (
    RunArtifactBytes,
    TwoRealI11R03Error,
    build_two_real_i11_r03,
    verify_two_run_source_admission,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    return _sha(json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode())


def _pages(first: str, second: str) -> bytes:
    return (
        f"=== PRINTED PDF PAGE 1 / 2 ===\n{first}\n"
        f"=== PRINTED PDF PAGE 2 / 2 ===\n{second}\n"
    ).encode()


def _case(monkeypatch: pytest.MonkeyPatch):
    method = b"private frozen I11 method used only by this synthetic gate test"
    method_sha = _sha(method)
    monkeypatch.setattr(subject, "AUTHORIAL_I11_SHA256", method_sha)
    events_a = [{
        "event_id": "E01", "layer": "RP", "pages": [1],
        "relation_mode": "SOURCE_ASSERTED_OPERATION", "actor_types": ["PERSON_RESEARCHER"],
    }]
    events_b = [{
        "event_id": "E02", "layer": "BR", "pages": [2],
        "relation_mode": "SOURCE_ASSERTED_OPERATION", "actor_types": ["PERSON_RESEARCHER"],
    }]
    source_a, source_b = b"original-pdf-a", b"original-pdf-b"
    page_a = _pages("alpha exact asserted phrase", "unused")
    page_b = _pages("unused", "beta exact asserted phrase")
    stdout_a, stdout_b = b"original stdout a", b"original stdout b"

    def make_run(job, work, source, pages, stdout, events, receipt_id):
        pins = {
            "source_pdf_sha256": _sha(source),
            "model_page_text_sha256": _sha(pages),
            "stdout_sha256": _sha(stdout),
            "method_sha256": method_sha,
            "event_ledger_sha256": _digest(events),
        }
        receipt = json.dumps({
            "schema": "seshat.aiye.hub_terminal_receipt.v1",
            "receipt_id": receipt_id, "job_id": job, "status": "SUCCEEDED",
            "completed_at_utc": "2026-10-23T00:00:00Z",
            "original_source_bytes_observed": True,
            "source_rights_status": "VERIFIED_PUBLISHED_LICENSE",
            **pins,
        }, sort_keys=True).encode()
        run = {
            "job_id": job, "work_id": work, "run_state": "SUCCEEDED",
            "source_kind": "REAL_PUBLISHED", "page_count": 2,
            "methodbody_id": subject.AUTHORIAL_I11_ID,
            "terminal_receipt_sha256": _sha(receipt), **pins,
            "scientific_acceptance": "NOT_ASSERTED", "owner_acceptance": "NOT_PERFORMED",
            "customer_release": "BLOCKED",
        }
        artifacts = RunArtifactBytes(source, pages, stdout, method, receipt)
        return run, artifacts

    run_a, artifacts_a = make_run(
        "jx-first", "published-a", source_a, page_a, stdout_a, events_a, "receipt-a"
    )
    run_b, artifacts_b = make_run(
        "jx-second", "published-b", source_b, page_b, stdout_b, events_b, "receipt-b"
    )
    comparisons = [{
        "kind": "MATERIAL_DIFFERENCE",
        "event_a": "E01", "page_a": 1, "excerpt_a": "alpha exact asserted phrase",
        "event_b": "E02", "page_b": 2, "excerpt_b": "beta exact asserted phrase",
        "statement": "Distinct author-reported operations.",
        "limits": "Engineering verification is not scientific acceptance.",
    }]
    return [run_a, run_b, artifacts_a, artifacts_b, events_a, events_b, comparisons]


def _admit_and_build(items):
    run_a, run_b, artifacts_a, artifacts_b, events_a, events_b, comparisons = items
    admission = verify_two_run_source_admission(
        run_a, run_b, artifacts_a, artifacts_b, events_a, events_b
    )
    return build_two_real_i11_r03(
        run_a, run_b, events_a, events_b, comparisons, admission=admission
    )


def test_plain_hash_only_builder_is_explicitly_unverified(monkeypatch):
    items = _case(monkeypatch)
    result = build_two_real_i11_r03(items[0], items[1], items[4], items[5], items[6])
    assert result["status"] == "UNVERIFIED_INPUTS"
    assert result["actual_real_model_runs"] == 0
    assert result["admission_status"] == "UNVERIFIED_CALLER_ASSERTIONS"
    assert result["comparison_claims"] == []
    assert result["product_wiring"] == "NOT_PRODUCT_WIRED"


def test_verified_bytes_receipts_ledgers_and_excerpts_produce_review_pending(monkeypatch):
    result = _admit_and_build(_case(monkeypatch))
    assert result["actual_real_model_runs"] == 2
    assert result["status"] == "VERIFIED_SOURCE_ADMISSION_REVIEW_PENDING"
    assert result["scientific_acceptance"] == "NOT_PERFORMED"
    assert result["owner_acceptance"] == "NOT_PERFORMED"
    assert result["customer_release"] == "BLOCKED"
    assert result["product_wiring"] == "NOT_PRODUCT_WIRED"
    assert result["implementation_missingness"]["source_a"] == "UNKNOWN"
    assert result["implementation_missingness"]["source_b"] == "UNKNOWN"
    claim = result["comparison_claims"][0]
    assert claim["status"] == "SOURCE_ADDRESSED_REVIEW_PENDING"
    assert {item["evidence_verification"] for item in claim["evidence"]} == {"VERIFIED_EXACT"}
    assert all(len(item["excerpt_sha256"]) == 64 for item in claim["evidence"])
    assert len(result["run_manifest_digests"]) == 2
    assert len(result["event_ledger_digests"]) == 2
    assert len(result["terminal_receipt_digests"]) == 2


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d[0].update(work_id=d[1]["work_id"]), "I11_NOT_TWO_DISTINCT_WORKS"),
    (lambda d: d[1].update(job_id=d[0]["job_id"]), "I11_TERMINAL_RECEIPT_MISMATCH"),
    (lambda d: d[1].update(method_sha256=d[0]["method_sha256"]), None),
    (lambda d: d[0].update(scientific_acceptance="ACCEPTED"), "I11_OWNER_ACCEPTANCE_SPOOF"),
    (lambda d: d[1].update(owner_acceptance="accepted in prose"), "I11_OWNER_ACCEPTANCE_SPOOF"),
])
def test_identity_method_and_acceptance_mutants_fail(monkeypatch, mutate, expected):
    items = _case(monkeypatch)
    if expected is None:
        items[2] = RunArtifactBytes(
            items[2].source_pdf, items[2].model_page_text, items[2].stdout,
            b"wrong shared method", items[2].terminal_receipt,
        )
        items[3] = RunArtifactBytes(
            items[3].source_pdf, items[3].model_page_text, items[3].stdout,
            b"wrong shared method", items[3].terminal_receipt,
        )
        wrong = _sha(b"wrong shared method")
        items[0]["method_sha256"] = wrong
        items[1]["method_sha256"] = wrong
        expected = "I11_WRONG_FROZEN_METHOD"
    else:
        mutate(items)
    with pytest.raises(TwoRealI11R03Error, match=expected):
        verify_two_run_source_admission(*items[:6])


def test_absent_original_source_and_forged_hash_fail(monkeypatch):
    items = _case(monkeypatch)
    items[2] = RunArtifactBytes(
        b"", items[2].model_page_text, items[2].stdout,
        items[2].method, items[2].terminal_receipt,
    )
    with pytest.raises(TwoRealI11R03Error, match="I11_ORIGINAL_SOURCE_ABSENT"):
        verify_two_run_source_admission(*items[:6])
    plain = _case(monkeypatch)
    plain[0]["source_pdf_sha256"] = "a" * 64
    with pytest.raises(TwoRealI11R03Error, match="I11_RECOMPUTED_SOURCE_PDF_SHA256_MISMATCH"):
        verify_two_run_source_admission(*plain[:6])


def test_swapped_event_ledger_fails_after_admission(monkeypatch):
    items = _case(monkeypatch)
    admission = verify_two_run_source_admission(*items[:6])
    with pytest.raises(TwoRealI11R03Error, match="I11_ADMISSION_LEDGER_MISMATCH"):
        build_two_real_i11_r03(
            items[0], items[1], items[5], items[4], items[6], admission=admission
        )


def test_duplicate_terminal_receipt_id_fails(monkeypatch):
    items = _case(monkeypatch)
    receipt_b = json.loads(items[3].terminal_receipt)
    receipt_b["receipt_id"] = "receipt-a"
    encoded = json.dumps(receipt_b, sort_keys=True).encode()
    items[1]["terminal_receipt_sha256"] = _sha(encoded)
    items[3] = RunArtifactBytes(
        items[3].source_pdf, items[3].model_page_text, items[3].stdout,
        items[3].method, encoded,
    )
    with pytest.raises(TwoRealI11R03Error, match="I11_DUPLICATE_OR_STALE_RECEIPT"):
        verify_two_run_source_admission(*items[:6])


def test_normalized_match_cannot_promote_claim(monkeypatch):
    items = _case(monkeypatch)
    items[6][0]["excerpt_a"] = "alpha-exact-asserted-phrase"
    result = _admit_and_build(items)
    assert result["comparison_claims"][0]["evidence"][0]["evidence_verification"] == (
        "NORMALIZED_ONLY"
    )
    assert result["comparison_claims"][0]["status"] == (
        "EVIDENCE_VERIFICATION_REVIEW_PENDING"
    )


@pytest.mark.parametrize("layer,mode,actor_type,expected", [
    ("RP", "SOURCE_ASSERTED_OPERATION", "PERSON_EDITORIAL", "I11_EDITOR_PROMOTED_TO_RP"),
    ("RP", "SOURCE_ASSERTED_OPERATION", "ORGANISATION_FUNDER", "I11_FUNDER_PROMOTED"),
    ("RP", "SOURCE_ASSERTED_OPERATION", "ORGANISATION_NORM_PRODUCER", "I11_EXTERNAL_GUIDE"),
    ("IM", "SOURCE_ASSERTED_OPERATION", "PERSON_CLINICAL", "I11_FALSE_IMPLEMENTATION"),
    ("IM", "SOURCE_PROPOSED_COOPERATION", "PERSON_RESEARCHER", "I11_FALSE_IMPLEMENTATION"),
])
def test_layer_and_relation_discipline(monkeypatch, layer, mode, actor_type, expected):
    items = _case(monkeypatch)
    items[4][0].update(layer=layer, relation_mode=mode, actor_types=[actor_type])
    items[0]["event_ledger_sha256"] = _digest(items[4])
    with pytest.raises(TwoRealI11R03Error, match=expected):
        verify_two_run_source_admission(*items[:6])


def test_admission_is_deterministic(monkeypatch):
    items = _case(monkeypatch)
    first = _admit_and_build(copy.deepcopy(items))
    second = _admit_and_build(copy.deepcopy(items))
    assert first == second
