"""Adversarial tests for Opus F-01/F-02/F-03/F-04/F-05."""
from __future__ import annotations

import hashlib

import pytest

from seshat.fabric_waves.operator_builtin_method import execute_literal_method
from seshat.fabric_waves.operator_local_demo import inputs
from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorClaim,
    OperatorRunLedger,
    export_rights_reviewed_prose,
    invoke_operator_method_body,
)


def _run(source_id=None, *, ids=frozenset(), digests=frozenset(), method=None):
    source, source_data, method_pin, method_data = inputs("materials")
    if source_id:
        source = source.model_copy(update={"source_id": source_id})
    use_method = method or execute_literal_method
    return invoke_operator_method_body(
        ledger=OperatorRunLedger(), run_id="review-run", job_id="review-job",
        source=source, source_bytes=source_data,
        method=method_pin, method_body_invocation_bytes=method_data,
        method_callable=use_method, requested_view="private-operator",
        owner_excluded_source_ids=ids,
        owner_excluded_source_sha256=digests,
    )


def test_omitting_owner_policy_is_hard_failure():
    source, data, method, method_data = inputs("materials")
    with pytest.raises(ValueError, match="OWNER_SELECTION_POLICY_REQUIRED"):
        invoke_operator_method_body(
            ledger=OperatorRunLedger(), run_id="run", job_id="job",
            source=source, source_bytes=data, method=method,
            method_body_invocation_bytes=method_data,
            method_callable=execute_literal_method, requested_view="private-operator",
        )


def test_renaming_source_cannot_bypass_excluded_content_hash():
    source, data, _, _ = inputs("materials")
    digest = hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="SOURCE_EXCLUDED_BY_OWNER_POLICY"):
        _run(source_id="renamed-invented-source", digests=frozenset({digest}))


def test_policy_digest_and_no_source_or_model_attestation():
    item = _run()
    assert item.owner_selection_policy_digest
    assert item.owner_selection_policy_attested == "NO"
    assert item.rights_attested == "NO"
    assert item.model_run_attested == "NO"
    assert item.method_interpretation == "PINNED_BYTES_INTERPRETED_BUILTIN"
    assert item.output_sediment.acceptance_state == "PROPOSED"


def test_unrelated_or_empty_export_bytes_cannot_disable_guard():
    item = _run()
    _, data, _, instructions = inputs("materials")
    for wrong in (b"", b"unrelated method body"):
        with pytest.raises(ValueError, match="REVIEW_BYTES_MISMATCH"):
            export_rights_reviewed_prose(
                receipt=item, reviewed_prose="Human operator reviewed the fixture.",
                reviewer_rights_statement="fixture-only reviewer",
                raw_method_body_invocation_bytes=wrong,
                raw_source_bytes=data,
            )
    with pytest.raises(ValueError, match="REVIEW_BYTES_MISMATCH"):
        export_rights_reviewed_prose(
            receipt=item, reviewed_prose="Human operator reviewed the fixture.",
            reviewer_rights_statement="fixture-only reviewer",
            raw_method_body_invocation_bytes=instructions,
            raw_source_bytes=b"wrong-data",
        )


def test_large_secret_fragment_export_is_denied():
    item = _run()
    _, data, _, instructions = inputs("materials")
    fragment = instructions.decode("utf-8")[8:76]
    assert len(fragment) >= 64
    with pytest.raises(ValueError, match="SECRET_LEAK_DENIED"):
        export_rights_reviewed_prose(
            receipt=item,
            reviewed_prose="I pasted a middle fragment: " + fragment,
            reviewer_rights_statement="fixture-only reviewer",
            raw_method_body_invocation_bytes=instructions,
            raw_source_bytes=data,
        )


def test_out_of_bounds_span_length_rejected_even_if_truncated_text_matches():
    source, data, method, method_data = inputs("materials")
    suffix = data[-5:].decode("utf-8")
    def wrong(inv):
        return OperatorBodyResult(
            research_object_id=inv.source_id,
            claims=(OperatorClaim(
                text="forged length",
                evidence_excerpt=suffix,
                byte_offset=len(inv.source_bytes) - 5,
                byte_length=10000,
            ),),
        )
    with pytest.raises(ValueError, match="CLAIM_SPAN_INVALID"):
        invoke_operator_method_body(
            ledger=OperatorRunLedger(), run_id="span", job_id="job",
            source=source, source_bytes=data, method=method,
            method_body_invocation_bytes=method_data,
            method_callable=wrong, requested_view="private-operator",
            owner_excluded_source_ids=frozenset(),
            owner_excluded_source_sha256=frozenset(),
        )
