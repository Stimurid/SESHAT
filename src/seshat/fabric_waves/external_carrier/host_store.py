"""HOST-ONLY durable HostJobStore (SQLite WAL, cross-process first-writer terminal CAS).

Guarantees (single trusted host account, local disk):
* the ORIGINAL canonical ResearchNeed bytes, pins, owner origin, Hub spec and prompt are persisted
  before any submission and can never be updated or deleted (SQL triggers);
* a terminal row is first-writer-wins across processes (``BEGIN IMMEDIATE`` + primary key);
* every row carries a content digest (and an optional host-private HMAC) verified on each read,
  so a partial or edited row is refused instead of trusted.

Limits (stated, not hidden): an attacker with write access to the SQLite file AND the ability to
drop triggers can delete whole rows; the digests detect edits, not removal. The store file must
live in a host-private directory. Row digests are not a signature; only the optional HMAC (key
held privately by the host) adds authentication.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seshat.fabric_waves.external_carrier.contracts import (
    AgentTaskRequest,
    canonical_json,
    material_hash,
    utc_now_iso,
)
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError,
    HostIntegrityKey,
    sha256_hex,
)

STORE_SCHEMA = "seshat_host_job_store_v1"
STORE_FILENAME = "host_jobs.sqlite3"
META_INTEGRITY_KEY_REQUIRED = "integrity_key_required"

TERMINAL_STATUSES = ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUTPUT_REJECTED")

_JOB_COLUMNS = (
    "host_job_id",
    "request_id",
    "idempotency_key",
    "request_bytes",
    "request_sha256",
    "pins_json",
    "origin_json",
    "dispatch_json",
    "prompt_bytes",
    "source_digests_json",
    "replay_json",
)
_TERMINAL_COLUMNS = (
    "host_job_id",
    "status",
    "hub_record_json",
    "stdout_bytes",
    "stdout_sha256",
    "result_digest",
    "payload_json",
    "receipt_sha256",
    "detail",
)
_DDL = """
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  at TEXT NOT NULL,
  row_sha256 TEXT NOT NULL,
  row_mac TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
  host_job_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL UNIQUE,
  request_bytes BLOB NOT NULL,
  request_sha256 TEXT NOT NULL,
  pins_json TEXT NOT NULL,
  origin_json TEXT NOT NULL,
  dispatch_json TEXT NOT NULL,
  prompt_bytes BLOB NOT NULL,
  source_digests_json TEXT NOT NULL,
  replay_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  row_sha256 TEXT NOT NULL,
  row_mac TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS submissions (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  host_job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  at TEXT NOT NULL,
  row_sha256 TEXT NOT NULL,
  row_mac TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS terminals (
  host_job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  hub_record_json TEXT NOT NULL,
  stdout_bytes BLOB NOT NULL,
  stdout_sha256 TEXT NOT NULL,
  result_digest TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  detail TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  row_sha256 TEXT NOT NULL,
  row_mac TEXT NOT NULL DEFAULT ''
);
"""

_TRIGGERS = tuple(
    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()} BEFORE {verb} ON {table} "
    "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROW'); END;"
    for table in ("jobs", "terminals", "submissions", "meta")
    for verb in ("UPDATE", "DELETE")
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes_sha256__": sha256_hex(bytes(value)), "__len__": len(bytes(value))}
    return value


def _row_material(table: str, values: dict[str, Any], created: str) -> str:
    return material_hash(
        {"table": table, "values": {k: _jsonable(v) for k, v in sorted(values.items())}, "at": created}
    )


@dataclass(frozen=True)
class JobRecord:
    host_job_id: str
    request_id: str
    idempotency_key: str
    request_bytes: bytes
    request_sha256: str
    pins: dict[str, Any]
    origin: dict[str, Any]
    dispatch: dict[str, Any]
    prompt_bytes: bytes
    source_digests: dict[str, str]
    replay: dict[str, Any]
    created_at: str

    def request(self) -> AgentTaskRequest:
        try:
            return AgentTaskRequest.model_validate(json.loads(self.request_bytes))
        except (ValueError, TypeError):
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW") from None


@dataclass(frozen=True)
class TerminalRecord:
    host_job_id: str
    status: str
    hub_record: dict[str, Any]
    stdout_bytes: bytes
    stdout_sha256: str
    result_digest: str
    payload: dict[str, Any] | None
    receipt_sha256: str
    detail: str
    recorded_at: str


class HostJobStore:
    """Process-safe store: a fresh SQLite connection per operation."""

    def __init__(self, directory: Path, *, integrity_key: HostIntegrityKey | None = None) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / STORE_FILENAME
        self._key = integrity_key
        con = self._connect()
        try:
            # v1 created an unsealed two-column meta table. It cannot be upgraded merely by
            # adding columns: the original key requirement and schema value were never
            # authenticated. Refuse before any DDL or WAL setting changes its evidence.
            existing = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
            ).fetchone()
            had_meta = existing is not None
            if existing is not None:
                columns = {row[1] for row in con.execute("PRAGMA table_info(meta)")}
                if columns == {"k", "v"}:
                    raise HostBoundaryError("HOST_STORE_LEGACY_MIGRATION_REQUIRED")
                if columns != {"k", "v", "at", "row_sha256", "row_mac"}:
                    raise HostBoundaryError("HOST_STORE_SCHEMA_MISMATCH")
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_DDL)
            for trigger in _TRIGGERS:
                con.execute(trigger)
            # Seal every meta row INSERTed in this transaction. Updates/deletes are blocked by
            # the immutability triggers above; attacker-with-DROP-TRIGGER tampering is detected on
            # the next read because row_sha256 / row_mac no longer match. We must read each
            # row's OWN ``at`` value because it was set when the row was originally inserted,
            # not on every open.
            at = utc_now_iso()
            schema_row = con.execute(
                "SELECT v, at, row_sha256, row_mac FROM meta WHERE k='schema'"
            ).fetchone()
            if schema_row is None:
                if had_meta:
                    raise HostBoundaryError("HOST_STORE_METADATA_MISSING")
                values = {"k": "schema", "v": STORE_SCHEMA}
                digest, mac = self._seal("meta", values, at)
                con.execute(
                    "INSERT INTO meta (k, v, at, row_sha256, row_mac) VALUES (?, ?, ?, ?, ?)",
                    (values["k"], values["v"], at, digest, mac),
                )
                schema_row = (STORE_SCHEMA, at, digest, mac)
            self._check_meta_seal("schema", schema_row[0], schema_row[1], schema_row[2], schema_row[3])
            if schema_row[0] != STORE_SCHEMA:
                raise HostBoundaryError("HOST_STORE_SCHEMA_MISMATCH")
            key_row = con.execute(
                "SELECT v, at, row_sha256, row_mac FROM meta WHERE k=?", (META_INTEGRITY_KEY_REQUIRED,)
            ).fetchone()
            if key_row is None:
                row_counts = [
                    con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("jobs", "submissions", "terminals")
                ]
                if self._key is not None and any(row_counts):
                    raise HostBoundaryError("HOST_STORE_INTEGRITY_UPGRADE_REQUIRED")
                if any(
                    con.execute(f"SELECT 1 FROM {table} WHERE row_mac!='' LIMIT 1").fetchone()
                    for table in ("jobs", "submissions", "terminals")
                ):
                    raise HostBoundaryError("HOST_STORE_METADATA_MISSING")
            if self._key is not None:
                if key_row is None:
                    values = {"k": META_INTEGRITY_KEY_REQUIRED, "v": "true"}
                    digest, mac = self._seal("meta", values, at)
                    con.execute(
                        "INSERT INTO meta (k, v, at, row_sha256, row_mac) VALUES (?, ?, ?, ?, ?)",
                        (values["k"], values["v"], at, digest, mac),
                    )
                else:
                    # Digest mismatch surfaces as METADATA_TAMPERED; MAC mismatch (wrong key) is
                    # left as ROW_TAMPERED, so the existing ``test_keyed_store_rejects_wrong_key``
                    # contract (init permissive on wrong key, row read refuses with ROW_TAMPERED)
                    # is preserved.
                    self._check_meta_seal(
                        META_INTEGRITY_KEY_REQUIRED,
                        key_row[0],
                        key_row[1],
                        key_row[2],
                        key_row[3],
                    )
                    if key_row[0] != "true":
                        raise HostBoundaryError("HOST_STORE_METADATA_TAMPERED")
            elif key_row is not None:
                self._check_meta_seal(
                    META_INTEGRITY_KEY_REQUIRED,
                    key_row[0],
                    key_row[1],
                    key_row[2],
                    key_row[3],
                )
                if key_row[0] == "true":
                    raise HostBoundaryError("HOST_STORE_INTEGRITY_KEY_REQUIRED")
        finally:
            con.close()

    # -- plumbing -------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=FULL")
        return con

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
            except BaseException:
                con.execute("ROLLBACK")
                raise
            else:
                con.execute("COMMIT")
        finally:
            con.close()

    def _seal(self, table: str, values: dict[str, Any], created: str) -> tuple[str, str]:
        material = _row_material(table, values, created)
        mac = self._key.mac(material) if self._key is not None else ""
        return material, mac

    def _check_seal(
        self, table: str, values: dict[str, Any], created: str, digest: Any, mac: Any
    ) -> None:
        if not isinstance(digest, str) or not digest:
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        if _row_material(table, values, created) != digest:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        if isinstance(mac, str) and mac:
            if self._key is None:
                raise HostBoundaryError("HOST_STORE_INTEGRITY_KEY_REQUIRED")
            if not self._key.verify(digest, mac):
                raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        elif self._key is not None:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")

    @staticmethod
    def _load_json(text: Any, *, expect: type) -> Any:
        if not isinstance(text, str):
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        try:
            data = json.loads(text)
        except ValueError:
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW") from None
        if not isinstance(data, expect):
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        return data

    def _validate_job_seal(self, con: sqlite3.Connection, host_job_id: str) -> None:
        """Independently re-verify the job row's seal before recording any side effect.

        A poisoned or partial job row (forged request_id, swapped prompt bytes, dropped triggers
        + UPDATE) is refused here so ``record_submission`` and ``record_terminal`` cannot make a
        chargeable or terminal decision on top of a tampered job. ``_check_seal`` raises
        ``HOST_STORE_ROW_TAMPERED`` or ``HOST_STORE_PARTIAL_ROW``.
        """

        row = con.execute(
            "SELECT " + ", ".join(_JOB_COLUMNS) + ", created_at, row_sha256, row_mac "
            "FROM jobs WHERE host_job_id=?",
            (host_job_id,),
        ).fetchone()
        if row is None:
            raise HostBoundaryError("UNKNOWN_JOB_ID")
        values = dict(zip(_JOB_COLUMNS, row[: len(_JOB_COLUMNS)], strict=True))
        created, digest, mac = row[len(_JOB_COLUMNS) :]
        self._check_seal("jobs", values, created, digest, mac)

    def _check_meta_seal(self, key: str, value: str, at: str, digest: Any, mac: Any) -> None:
        """Verify the metadata digest and MAC before selecting a trust mode."""

        if not isinstance(digest, str) or not digest:
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        recomputed = _row_material("meta", {"k": key, "v": value}, at)
        if recomputed != digest:
            raise HostBoundaryError("HOST_STORE_METADATA_TAMPERED")
        if mac:
            if self._key is None:
                raise HostBoundaryError("HOST_STORE_INTEGRITY_KEY_REQUIRED")
            if not self._key.verify(digest, mac):
                raise HostBoundaryError("HOST_STORE_METADATA_TAMPERED")
        elif self._key is not None:
            raise HostBoundaryError("HOST_STORE_METADATA_TAMPERED")

    # -- jobs -----------------------------------------------------------------------------

    def insert_job(
        self,
        *,
        host_job_id: str,
        request: AgentTaskRequest,
        request_bytes: bytes,
        pins: dict[str, Any],
        origin: dict[str, Any],
        dispatch: dict[str, Any],
        prompt_bytes: bytes,
        source_digests: dict[str, str],
        replay: dict[str, Any],
    ) -> bool:
        """Persist the immutable job. Returns True if created, False if an identical job exists."""

        values: dict[str, Any] = {
            "host_job_id": host_job_id,
            "request_id": request.request_id,
            "idempotency_key": request.idempotency_key,
            "request_bytes": bytes(request_bytes),
            "request_sha256": sha256_hex(request_bytes),
            "pins_json": canonical_json(pins),
            "origin_json": canonical_json(origin),
            "dispatch_json": canonical_json(dispatch),
            "prompt_bytes": bytes(prompt_bytes),
            "source_digests_json": canonical_json(source_digests),
            "replay_json": canonical_json(replay),
        }
        created = utc_now_iso()
        digest, mac = self._seal("jobs", values, created)
        with self._tx() as con:
            existing = con.execute(
                "SELECT " + ", ".join(_JOB_COLUMNS) + " FROM jobs WHERE host_job_id=?",
                (host_job_id,),
            ).fetchone()
            if existing is not None:
                if dict(zip(_JOB_COLUMNS, existing, strict=True)) == values:
                    return False
                raise HostBoundaryError("HOST_JOB_ID_COLLISION")
            if con.execute(
                "SELECT 1 FROM jobs WHERE request_id=?", (request.request_id,)
            ).fetchone():
                raise HostBoundaryError("HOST_REQUEST_ID_CONFLICT")
            if con.execute(
                "SELECT 1 FROM jobs WHERE idempotency_key=?", (request.idempotency_key,)
            ).fetchone():
                raise HostBoundaryError("HOST_IDEMPOTENCY_CONFLICT")
            con.execute(
                "INSERT INTO jobs (" + ", ".join(_JOB_COLUMNS) + ", created_at, row_sha256, row_mac)"
                " VALUES (" + ", ".join("?" for _ in range(len(_JOB_COLUMNS) + 3)) + ")",
                (*[values[c] for c in _JOB_COLUMNS], created, digest, mac),
            )
        self.get_job(host_job_id)  # durable readback verification
        return True

    def _job_from_row(self, row: tuple[Any, ...]) -> JobRecord:
        if len(row) != len(_JOB_COLUMNS) + 3 or any(item is None for item in row):
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        values = dict(zip(_JOB_COLUMNS, row[: len(_JOB_COLUMNS)], strict=True))
        created, digest, mac = row[len(_JOB_COLUMNS) :]
        self._check_seal("jobs", values, created, digest, mac)
        if sha256_hex(bytes(values["request_bytes"])) != values["request_sha256"]:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        return JobRecord(
            host_job_id=values["host_job_id"],
            request_id=values["request_id"],
            idempotency_key=values["idempotency_key"],
            request_bytes=bytes(values["request_bytes"]),
            request_sha256=values["request_sha256"],
            pins=self._load_json(values["pins_json"], expect=dict),
            origin=self._load_json(values["origin_json"], expect=dict),
            dispatch=self._load_json(values["dispatch_json"], expect=dict),
            prompt_bytes=bytes(values["prompt_bytes"]),
            source_digests=self._load_json(values["source_digests_json"], expect=dict),
            replay=self._load_json(values["replay_json"], expect=dict),
            created_at=created,
        )

    _JOB_SELECT = (
        "SELECT " + ", ".join(_JOB_COLUMNS) + ", created_at, row_sha256, row_mac FROM jobs "
    )

    def get_job(self, host_job_id: str) -> JobRecord:
        con = self._connect()
        try:
            row = con.execute(self._JOB_SELECT + "WHERE host_job_id=?", (host_job_id,)).fetchone()
        finally:
            con.close()
        if row is None:
            raise HostBoundaryError("UNKNOWN_JOB_ID")
        return self._job_from_row(row)

    def find_job_by_request(self, request_id: str) -> JobRecord | None:
        con = self._connect()
        try:
            row = con.execute(self._JOB_SELECT + "WHERE request_id=?", (request_id,)).fetchone()
        finally:
            con.close()
        return None if row is None else self._job_from_row(row)

    def list_job_ids(self) -> list[str]:
        con = self._connect()
        try:
            rows = con.execute("SELECT host_job_id FROM jobs ORDER BY host_job_id").fetchall()
        finally:
            con.close()
        return [str(item[0]) for item in rows]

    # -- submissions (append-only audit of host->Hub actions) -----------------------------

    def record_submission(self, host_job_id: str, kind: str, detail: dict[str, Any]) -> int:
        values = {"host_job_id": host_job_id, "kind": kind, "detail_json": canonical_json(detail)}
        at = utc_now_iso()
        digest, mac = self._seal("submissions", values, at)
        with self._tx() as con:
            self._validate_job_seal(con, host_job_id)
            cursor = con.execute(
                "INSERT INTO submissions (host_job_id, kind, detail_json, at, row_sha256, row_mac)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (host_job_id, kind, values["detail_json"], at, digest, mac),
            )
            return int(cursor.lastrowid or 0)

    @staticmethod
    def derive_submission_state(kinds: list[str]) -> str:
        """NONE | ATTEMPTED | FAILED | ACKED from an ordered list of submission kinds."""

        state = "NONE"
        for kind in kinds:
            if kind == "SUBMIT_ACKED":
                return "ACKED"
            if kind in {"SUBMIT_ATTEMPTED", "SUBMIT_AMBIGUOUS"}:
                state = "ATTEMPTED"
            elif kind == "SUBMIT_FAILED":
                state = "FAILED"
        return state

    def submission_state(self, host_job_id: str) -> str:
        return self.derive_submission_state([item["kind"] for item in self.submissions(host_job_id)])

    def begin_submission(
        self,
        host_job_id: str,
        *,
        nonce: str,
        auth_detail: dict[str, Any],
        attempt_detail: dict[str, Any],
    ) -> None:
        """Atomically claim the single right to submit this job (cross-process safe).

        In ONE ``BEGIN IMMEDIATE`` transaction: refuse if already acknowledged, if a previous
        attempt is unresolved (ambiguous), or if the authorization nonce was already consumed;
        otherwise append LIVE_AUTH_CONSUMED and SUBMIT_ATTEMPTED. Two racing dispatchers
        therefore cannot both reach the Hub.
        """

        at = utc_now_iso()
        with self._tx() as con:
            self._validate_job_seal(con, host_job_id)
            raw_rows = con.execute(
                "SELECT host_job_id, kind, detail_json, at, row_sha256, row_mac "
                "FROM submissions WHERE host_job_id=? ORDER BY seq",
                (host_job_id,),
            ).fetchall()
            rows: list[tuple[str, str]] = []
            for job_ref, kind, detail_json, row_at, digest, mac in raw_rows:
                self._check_seal(
                    "submissions",
                    {"host_job_id": job_ref, "kind": kind, "detail_json": detail_json},
                    row_at,
                    digest,
                    mac,
                )
                rows.append((str(kind), detail_json))
            state = self.derive_submission_state([kind for kind, _ in rows])
            if state == "ACKED":
                raise HostBoundaryError("SUBMISSION_ALREADY_ACKED")
            if state == "ATTEMPTED":
                raise HostBoundaryError("SUBMISSION_STATE_AMBIGUOUS")
            for kind, detail_json in rows:
                if kind == "LIVE_AUTH_CONSUMED":
                    detail = self._load_json(detail_json, expect=dict)
                    if detail.get("nonce") == nonce:
                        raise HostBoundaryError("LIVE_AUTHORIZATION_REUSED")
            for kind, detail in (
                ("LIVE_AUTH_CONSUMED", {**auth_detail, "nonce": nonce}),
                ("SUBMIT_ATTEMPTED", attempt_detail),
            ):
                values = {
                    "host_job_id": host_job_id,
                    "kind": kind,
                    "detail_json": canonical_json(detail),
                }
                digest, mac = self._seal("submissions", values, at)
                con.execute(
                    "INSERT INTO submissions (host_job_id, kind, detail_json, at, row_sha256, row_mac)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (host_job_id, kind, values["detail_json"], at, digest, mac),
                )

    def submissions(self, host_job_id: str) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT seq, host_job_id, kind, detail_json, at, row_sha256, row_mac "
                "FROM submissions WHERE host_job_id=? ORDER BY seq",
                (host_job_id,),
            ).fetchall()
        finally:
            con.close()
        out: list[dict[str, Any]] = []
        for seq, job_id, kind, detail_json, at, digest, mac in rows:
            values = {"host_job_id": job_id, "kind": kind, "detail_json": detail_json}
            self._check_seal("submissions", values, at, digest, mac)
            out.append(
                {
                    "seq": seq,
                    "kind": kind,
                    "at": at,
                    "detail": self._load_json(detail_json, expect=dict),
                }
            )
        return out

    # -- terminals (first-writer-wins) ----------------------------------------------------

    def record_terminal(
        self,
        *,
        host_job_id: str,
        status: str,
        hub_record: dict[str, Any],
        stdout_bytes: bytes,
        stdout_sha256: str,
        result_digest: str,
        payload: dict[str, Any] | None,
        receipt_sha256: str,
        detail: str = "",
    ) -> TerminalRecord:
        """Atomic first-writer terminal CAS.

        An identical re-record is idempotent. A different terminal for the same job raises
        TERMINAL_RESULT_ALREADY_ISSUED; the first writer's row is never altered.
        """

        if status not in TERMINAL_STATUSES:
            raise HostBoundaryError("TERMINAL_STATUS_INVALID")
        values: dict[str, Any] = {
            "host_job_id": host_job_id,
            "status": status,
            "hub_record_json": canonical_json(hub_record),
            "stdout_bytes": bytes(stdout_bytes),
            "stdout_sha256": stdout_sha256,
            "result_digest": result_digest,
            "payload_json": canonical_json(payload) if payload is not None else "",
            "receipt_sha256": receipt_sha256,
            "detail": detail,
        }
        recorded = utc_now_iso()
        digest, mac = self._seal("terminals", values, recorded)
        with self._tx() as con:
            self._validate_job_seal(con, host_job_id)
            existing = con.execute(
                "SELECT " + ", ".join(_TERMINAL_COLUMNS) + " FROM terminals WHERE host_job_id=?",
                (host_job_id,),
            ).fetchone()
            if existing is not None:
                if dict(zip(_TERMINAL_COLUMNS, existing, strict=True)) == values:
                    pass
                else:
                    raise HostBoundaryError("TERMINAL_RESULT_ALREADY_ISSUED")
            else:
                con.execute(
                    "INSERT INTO terminals ("
                    + ", ".join(_TERMINAL_COLUMNS)
                    + ", recorded_at, row_sha256, row_mac) VALUES ("
                    + ", ".join("?" for _ in range(len(_TERMINAL_COLUMNS) + 3))
                    + ")",
                    (*[values[c] for c in _TERMINAL_COLUMNS], recorded, digest, mac),
                )
        result = self.get_terminal(host_job_id)
        if result is None:
            raise HostBoundaryError("TERMINAL_READBACK_MISSING")
        return result

    def get_terminal(self, host_job_id: str) -> TerminalRecord | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT "
                + ", ".join(_TERMINAL_COLUMNS)
                + ", recorded_at, row_sha256, row_mac FROM terminals WHERE host_job_id=?",
                (host_job_id,),
            ).fetchone()
        finally:
            con.close()
        if row is None:
            return None
        if len(row) != len(_TERMINAL_COLUMNS) + 3 or any(item is None for item in row):
            raise HostBoundaryError("HOST_STORE_PARTIAL_ROW")
        values = dict(zip(_TERMINAL_COLUMNS, row[: len(_TERMINAL_COLUMNS)], strict=True))
        recorded, digest, mac = row[len(_TERMINAL_COLUMNS) :]
        self._check_seal("terminals", values, recorded, digest, mac)
        stdout = bytes(values["stdout_bytes"])
        if sha256_hex(stdout) != values["stdout_sha256"]:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        payload_json = values["payload_json"]
        payload = self._load_json(payload_json, expect=dict) if payload_json else None
        return TerminalRecord(
            host_job_id=values["host_job_id"],
            status=values["status"],
            hub_record=self._load_json(values["hub_record_json"], expect=dict),
            stdout_bytes=stdout,
            stdout_sha256=values["stdout_sha256"],
            result_digest=values["result_digest"],
            payload=payload,
            receipt_sha256=values["receipt_sha256"],
            detail=values["detail"],
            recorded_at=recorded,
        )


__all__ = [
    "STORE_FILENAME",
    "STORE_SCHEMA",
    "TERMINAL_STATUSES",
    "HostJobStore",
    "JobRecord",
    "TerminalRecord",
]
