"""Manual reconciliation is durable and never replays an ambiguous run."""
import pytest
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger


def raise_uncertain():
    raise RuntimeError("unknown outcome")


def test_owner_reconciliation_readback_still_blocks_retry(tmp_path):
    db = tmp_path / "journal.sqlite"
    ledger = SQLiteOperatorRunLedger(db)
    with pytest.raises(RuntimeError, match="unknown outcome"):
        ledger.record_or_resume("same-run", "input-digest", raise_uncertain)
    result = ledger.reconcile_pending(
        "same-run", resolution="ABANDONED_AMBIGUOUS",
        operator_note="Operator recorded an unresolved execution",
    )
    assert SQLiteOperatorRunLedger(db).get_reconciliation("same-run") == result
    with pytest.raises(ValueError, match="PENDING_REQUIRES_OWNER_RECONCILIATION"):
        SQLiteOperatorRunLedger(db).record_or_resume(
            "same-run", "input-digest", lambda: pytest.fail("duplicate execution"),
        )


def test_conflicting_manual_decision_is_refused(tmp_path):
    db = tmp_path / "journal.sqlite"
    ledger = SQLiteOperatorRunLedger(db)
    with pytest.raises(RuntimeError):
        ledger.record_or_resume("same-run", "fingerprint", raise_uncertain)
    note = "Operator verified an uncertain result"
    first = ledger.reconcile_pending(
        "same-run", resolution="ABANDONED_AMBIGUOUS", operator_note=note,
    )
    assert first == ledger.reconcile_pending(
        "same-run", resolution="ABANDONED_AMBIGUOUS", operator_note=note,
    )
    with pytest.raises(ValueError, match="RECONCILIATION_CONFLICT"):
        ledger.reconcile_pending(
            "same-run", resolution="ABANDONED_AMBIGUOUS",
            operator_note="Another unsupported external decision",
        )


def test_reconciliation_cannot_mint_result(tmp_path):
    ledger = SQLiteOperatorRunLedger(tmp_path / "journal.sqlite")
    with pytest.raises(ValueError, match="RESOLUTION_DENIED"):
        ledger.reconcile_pending(
            "missing", resolution="COMPLETE",
            operator_note="Prohibit acceptance through reconciliation",
        )
    with pytest.raises(ValueError, match="NOT_PENDING"):
        ledger.reconcile_pending(
            "missing", resolution="ABANDONED_AMBIGUOUS",
            operator_note="The record never existed",
        )
