"""Cold restart, tampering, pending provider ambiguity: no separate server."""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorClaim,
    OperatorMethodBodyPin,
    OperatorSourcePin,
    invoke_operator_method_body,
    replay_and_verify_operator_run,
)
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger


SOURCE = b"INVENTED PUBLIC TEXT: silver fox and copper wire."
METHOD = b"operator-owned procedure v1: cite a bounded literal span"


def _dispatch(ledger, *, run_id="run-one", source_bytes=SOURCE, invoked=None):
    source = OperatorSourcePin(
        source_id="fixture-silver",
        source_version="v1",
        sha256=hashlib.sha256(SOURCE).hexdigest(),
        rights_basis="owner-public-invented-fixture",
        authorized_view="private-operator",
    )
    method = OperatorMethodBodyPin(
        method_body_id="fixture.extract",
        version="v1",
        invocation_body_sha256=hashlib.sha256(METHOD).hexdigest(),
    )

    def call(invocation):
        if invoked is not None:
            invoked.append(invocation.run_id)
        return OperatorBodyResult(
            research_object_id="public-test-object",
            claims=(OperatorClaim(
                text="literal finding", evidence_excerpt="silver",
                byte_offset=22, byte_length=6,
            ),),
        )

    return invoke_operator_method_body(
        ledger=ledger, run_id=run_id, job_id="host-job",
        source=source, source_bytes=source_bytes,
        method=method, method_body_invocation_bytes=METHOD,
        method_callable=call, requested_view="private-operator",
    )


def test_durable_resume_from_new_process_object_never_reinvokes(tmp_path):
    db = tmp_path / "runs.db"
    calls = []
    first = _dispatch(SQLiteOperatorRunLedger(db), invoked=calls)
    second = _dispatch(SQLiteOperatorRunLedger(db), invoked=calls)
    assert calls == ["run-one"]
    assert first.output_digest == second.output_digest
    readback = replay_and_verify_operator_run(
        ledger=SQLiteOperatorRunLedger(db), run_id="run-one",
        source_bytes=SOURCE, method_body_invocation_bytes=METHOD,
    )
    assert readback.output_digest == first.output_digest


def test_durable_unknown_pending_after_failure_blocks_automatic_retry(tmp_path):
    db = tmp_path / "runs.db"
    ledger = SQLiteOperatorRunLedger(db)
    with pytest.raises(RuntimeError, match="provider-outcome-unknown"):
        ledger.record_or_resume("maybe-paid", "fingerprint-a", lambda: _raise_unknown())
    assert db.exists()
    with pytest.raises(ValueError, match="PENDING_REQUIRES_OWNER_RECONCILIATION"):
        SQLiteOperatorRunLedger(db).record_or_resume(
            "maybe-paid", "fingerprint-a",
            lambda: pytest.fail("MUST NOT retry paid provider"),
        )


def _raise_unknown():
    raise RuntimeError("provider-outcome-unknown")


def test_fingerprint_drift_still_rejected_after_cold_restart(tmp_path):
    db = tmp_path / "runs.db"
    _dispatch(SQLiteOperatorRunLedger(db))
    with pytest.raises(ValueError, match="AMBIGUOUS_DUPLICATE"):
        SQLiteOperatorRunLedger(db).record_or_resume(
            "run-one", "wrong-fingerprint", lambda: pytest.fail("not callable"),
        )


def test_direct_tamper_receipt_detected(tmp_path):
    db = tmp_path / "runs.db"
    _dispatch(SQLiteOperatorRunLedger(db))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE runs SET receipt_json = receipt_json || 'garbage' WHERE run_id='run-one'"
        )
    with pytest.raises(ValueError, match="RECEIPT_INTEGRITY_ERROR"):
        SQLiteOperatorRunLedger(db).get("run-one")


def test_changed_source_fails_before_resume(tmp_path):
    db = tmp_path / "runs.db"
    _dispatch(SQLiteOperatorRunLedger(db))
    with pytest.raises(ValueError, match="OPERATOR_SOURCE_BYTES_STALE"):
        _dispatch(SQLiteOperatorRunLedger(db), source_bytes=SOURCE + b" changed")
