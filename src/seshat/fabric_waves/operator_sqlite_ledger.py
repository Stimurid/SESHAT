"""Owner-private, crash-safe SQLite ledger for a local SESHAT MethodBody run.

This is a local *replay and integrity journal*, NOT a trusted issuer and not
a guarantee of one paid provider call. Every run_id enters PENDING in SQLite
*before* invoking code. After a process crash or an unknown paid outcome,
PENDING blocks automatic replay; an owner must reconcile it explicitly.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from seshat.fabric_waves.operator_methodbody import OperatorRunReceipt


class SQLiteOperatorRunLedger:
    """Durable operator-controlled journal; caller must use a private local path."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.parent.exists():
            raise ValueError("OPERATOR_LEDGER_PARENT_MISSING")
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs("
                "run_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, "
                "state TEXT NOT NULL CHECK(state IN ('PENDING','COMPLETE')), "
                "receipt_json TEXT, receipt_sha256 TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS reconciliations("
                "run_id TEXT PRIMARY KEY, resolution TEXT NOT NULL, "
                "operator_note_sha256 TEXT NOT NULL, "
                "FOREIGN KEY(run_id) REFERENCES runs(run_id))"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @staticmethod
    def _decode(record: tuple[object, ...]) -> OperatorRunReceipt:
        data, digest = record
        if not isinstance(data, str) or not isinstance(digest, str):
            raise ValueError("OPERATOR_LEDGER_RECEIPT_MISSING")
        if hashlib.sha256(data.encode("utf-8")).hexdigest() != digest:
            raise ValueError("OPERATOR_LEDGER_RECEIPT_INTEGRITY_ERROR")
        try:
            parsed = OperatorRunReceipt.model_validate_json(data)
        except Exception as exc:
            raise ValueError("OPERATOR_LEDGER_RECEIPT_INVALID") from exc
        # The nested sediment digest cannot be taken on faith from JSON.
        from seshat.fabric_waves.sediment import payload_hash

        if payload_hash(parsed.output_sediment.payload) != parsed.output_sediment.payload_hash:
            raise ValueError("OPERATOR_LEDGER_SEDIMENT_DRIFT")
        expected_output = hashlib.sha256(
            f"{parsed.output_sediment.payload_hash}:{parsed.invocation.stdout_sha256}".encode("utf-8")
        ).hexdigest()
        if expected_output != parsed.output_digest:
            raise ValueError("OPERATOR_LEDGER_OUTPUT_DRIFT")
        return parsed

    def record_or_resume(
        self,
        run_id: str,
        fingerprint: str,
        build: Callable[[], OperatorRunReceipt],
    ) -> OperatorRunReceipt:
        if not run_id or not fingerprint:
            raise ValueError("OPERATOR_RUN_ID_REQUIRED")
        # Insert the durable lock before the provider or local callable runs.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT fingerprint,state,receipt_json,receipt_sha256 FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if previous is not None:
                old_fingerprint, state, receipt_json, receipt_digest = previous
                if old_fingerprint != fingerprint:
                    raise ValueError("OPERATOR_RUN_ID_AMBIGUOUS_DUPLICATE")
                if state != "COMPLETE":
                    raise ValueError("OPERATOR_RUN_PENDING_REQUIRES_OWNER_RECONCILIATION")
                receipt = self._decode((receipt_json, receipt_digest))
                if receipt.run_id != run_id:
                    raise ValueError("OPERATOR_LEDGER_RUN_ID_MISMATCH")
                return receipt
            db.execute(
                "INSERT INTO runs(run_id,fingerprint,state) VALUES(?,?,'PENDING')",
                (run_id, fingerprint),
            )
            db.commit()

        # A crash, process kill or exception leaves the row PENDING deliberately.
        # Do not delete it to make a paid retry appear safe.
        receipt = build()
        if receipt.run_id != run_id:
            raise ValueError("OPERATOR_LEDGER_RUN_ID_MISMATCH")
        data = receipt.model_dump_json()
        digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute(
                "UPDATE runs SET state='COMPLETE',receipt_json=?,receipt_sha256=? "
                "WHERE run_id=? AND fingerprint=? AND state='PENDING'",
                (data, digest, run_id, fingerprint),
            )
            if cur.rowcount != 1:
                raise ValueError("OPERATOR_LEDGER_CONCURRENT_UPDATE")
            db.commit()
        return receipt

    def get(self, run_id: str) -> OperatorRunReceipt:
        with self._connect() as db:
            row = db.execute(
                "SELECT state,receipt_json,receipt_sha256 FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ValueError("OPERATOR_RUN_NOT_FOUND")
        if row[0] != "COMPLETE":
            raise ValueError("OPERATOR_RUN_PENDING_REQUIRES_OWNER_RECONCILIATION")
        result = self._decode((row[1], row[2]))
        if result.run_id != run_id:
            raise ValueError("OPERATOR_LEDGER_RUN_ID_MISMATCH")
        return result

    def reconcile_pending(
        self,
        run_id: str,
        *,
        resolution: str,
        operator_note: str,
    ) -> dict[str, str]:
        """Record a manual outcome decision without replaying an uncertain call.

        This never deletes or reopens a PENDING run_id and never invokes
        `build`. To try again, the owner must explicitly use a *new* run ID
        after independently establishing whether the first attempt cost money.
        """
        if resolution != "ABANDONED_AMBIGUOUS":
            raise ValueError("OPERATOR_RECONCILIATION_RESOLUTION_DENIED")
        if not operator_note.strip() or len(operator_note.strip()) < 12:
            raise ValueError("OPERATOR_RECONCILIATION_NOTE_REQUIRED")
        digest = hashlib.sha256(operator_note.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None or row[0] != "PENDING":
                raise ValueError("OPERATOR_RECONCILIATION_NOT_PENDING")
            old = db.execute(
                "SELECT resolution,operator_note_sha256 "
                "FROM reconciliations WHERE run_id=?", (run_id,)
            ).fetchone()
            if old is not None:
                if old != (resolution, digest):
                    raise ValueError("OPERATOR_RECONCILIATION_CONFLICT")
                return {
                    "run_id": run_id, "resolution": resolution,
                    "operator_note_sha256": digest,
                }
            db.execute(
                "INSERT INTO reconciliations("
                "run_id,resolution,operator_note_sha256) VALUES(?,?,?)",
                (run_id, resolution, digest),
            )
            db.commit()
        return {
            "run_id": run_id,
            "resolution": resolution,
            "operator_note_sha256": digest,
        }

    def get_reconciliation(self, run_id: str) -> dict[str, str]:
        """Read back the manual decision; never a human scientific acceptance."""
        with self._connect() as db:
            row = db.execute(
                "SELECT resolution,operator_note_sha256 "
                "FROM reconciliations WHERE run_id=?", (run_id,),
            ).fetchone()
        if row is None:
            raise ValueError("OPERATOR_RECONCILIATION_NOT_FOUND")
        return {
            "run_id": run_id, "resolution": row[0],
            "operator_note_sha256": row[1],
        }


__all__ = ["SQLiteOperatorRunLedger"]
