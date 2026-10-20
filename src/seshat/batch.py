"""F09A1 durable offline serial batch over F07/F08. Metadata only; concurrency=1."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import Field, model_validator

from seshat.corpus import FrozenModel, _digest, public_selection_digest
from seshat.corpus_host import HostRuntime
from seshat.reports import ReportProjection, ReportReceipt, ReportRequest, artifacts, report_session
from seshat.scientific_report import ScientificReportAsset

MANIFEST_VERSION = "F09A1-1"
LEDGER_FILENAME = "batch_ledger.sqlite"
MANIFEST_FILENAME = "manifest.json"
INDEX_FILENAME = "index.json"
RECEIPT_FILENAME = "batch_receipt.json"
ITEMS_DIR = "items"

BatchItemState = Literal[
    "QUEUED",
    "RUNNING",
    "DONE_METADATA",
    "DONE_SCIENTIFIC_UNREVIEWED",
    "PARTIAL_METADATA",
    "BLOCKED_METHOD",
    "BLOCKED_EXTERNAL",
    "FAILED_RETRYABLE",
    "FAILED_PERMANENT",
    "CANCELLED",
    "STALE",
]


class HostSourcePins(FrozenModel):
    primary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class BatchItemSpec(FrozenModel):
    item_id: str = Field(min_length=1)
    request: ReportRequest


class BatchManifest(FrozenModel):
    manifest_version: Literal["F09A1-1"] = MANIFEST_VERSION
    batch_id: str = Field(min_length=1)
    host_id: str = Field(min_length=1)
    caller_id: str = Field(min_length=1)
    rights_scope: str = Field(min_length=1)
    source_pins: HostSourcePins
    scientific_asset_digests: tuple[str, ...] = ()
    items: tuple[BatchItemSpec, ...] = Field(min_length=1)
    max_items: int = Field(default=64, ge=1, le=256)
    concurrency: Literal[1] = 1

    @model_validator(mode="after")
    def bounded_items(self):
        if len(self.items) > self.max_items:
            raise ValueError("BATCH_TOO_LARGE")
        ids = [i.item_id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_ITEM_ID")
        for item in self.items:
            if item.request.rights_scope != self.rights_scope:
                raise ValueError("BATCH_SCOPE_MISMATCH")
        return self


class BatchItemStatus(FrozenModel):
    item_id: str
    report_id: str
    state: BatchItemState
    reason_code: str
    input_fingerprint: str
    projection_digest: str | None = None
    report_json_sha256: str | None = None
    report_html_sha256: str | None = None
    receipt_json_sha256: str | None = None
    relative_path: str | None = None
    attempts: int = 0
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


class BatchReceipt(FrozenModel):
    receipt_version: Literal["F09A1-receipt-1"] = "F09A1-receipt-1"
    batch_id: str
    manifest_fingerprint: str
    host_id: str
    caller_id: str
    rights_scope: str
    template_version: str
    item_count: int
    items: tuple[BatchItemStatus, ...]
    code_pass: bool
    method_review: Literal["NOT_PERFORMED"] = "NOT_PERFORMED"
    scientific_accepted: Literal["NEVER_AUTO_SET"] = "NEVER_AUTO_SET"
    completed_at: str
    selection_snapshot_digests: tuple[str, ...]


class BatchStatus(FrozenModel):
    batch_id: str
    manifest_fingerprint: str
    cancelled: bool
    items: tuple[BatchItemStatus, ...]
    pending: int
    terminal: int


class BatchManifestConflict(Exception):
    """Same batch_id with a different manifest fingerprint."""


def canonical_bytes(value) -> bytes:
    if isinstance(value, FrozenModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def source_pins_from_runtime(runtime: HostRuntime) -> HostSourcePins:
    cfg = runtime._configuration
    return HostSourcePins(
        primary_sha256=cfg.primary.sha256,
        rights_sha256=cfg.rights.sha256,
        temporal_sha256=cfg.temporal.sha256 if cfg.temporal else None,
    )


def manifest_fingerprint(manifest: BatchManifest) -> str:
    return _digest({"domain": "seshat.f09a.manifest.v1",
                    "manifest": manifest.model_dump(mode="json")})


def item_input_fingerprint(manifest: BatchManifest, item: BatchItemSpec) -> str:
    selection_digests = tuple(
        public_selection_digest(s) for s in sorted(item.request.selections, key=lambda s: s.selector_id))
    return _digest({
        "domain": "seshat.f09a.item-input.v2",
        "batch_id": manifest.batch_id,
        "item_id": item.item_id,
        "template_version": item.request.template_version,
        "report_id": item.request.report_id,
        "selection_digests": selection_digests,
        "rights_scope": item.request.rights_scope,
    })


def _ledger_status(report: ReportProjection) -> BatchItemState:
    if report.status == "SOURCE_GROUNDED_UNREVIEWED":
        return "DONE_SCIENTIFIC_UNREVIEWED"
    if report.status == "SUBSTANTIVE_METADATA":
        return "DONE_METADATA"
    if report.status == "PARTIAL_METADATA":
        return "PARTIAL_METADATA"
    if report.status == "BLOCKED" and report.blocks:
        code = report.blocks[0].code
        if code == "BLOCKED_METHOD":
            return "BLOCKED_METHOD"
        return "BLOCKED_EXTERNAL"
    return "FAILED_PERMANENT"


def _reason_for(report: ReportProjection, state: BatchItemState) -> str:
    if state in {"DONE_METADATA", "DONE_SCIENTIFIC_UNREVIEWED", "PARTIAL_METADATA"}:
        return report.status
    if report.blocks:
        return report.blocks[0].code
    return state


def _reject_lexical_escape(path: Path) -> None:
    if ".." in path.parts:
        raise ValueError("UNSAFE_OUTPUT_PATH")
    for part in path.parts:
        if part == "..":
            raise ValueError("UNSAFE_OUTPUT_PATH")


def _lstat_symlink_or_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return path.is_symlink()
    if stat.S_ISLNK(info.st_mode):
        return True
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return True
    return False


def assert_safe_path(
    path: Path,
    *,
    must_not_exist: bool = False,
    trusted_root: Path | None = None,
) -> Path:
    _reject_lexical_escape(path)
    cursor = path
    while True:
        if _lstat_symlink_or_reparse(cursor):
            raise ValueError("UNSAFE_OUTPUT_PATH")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    resolved = path.resolve()
    _reject_lexical_escape(resolved)
    if trusted_root is not None:
        root_resolved = trusted_root.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise ValueError("UNSAFE_OUTPUT_PATH") from None
    if must_not_exist and resolved.exists():
        raise FileExistsError(str(resolved))
    return resolved


def _item_dir(root: Path, item_id: str) -> Path:
    if item_id != Path(item_id).name or item_id in {".", ".."}:
        raise ValueError("UNSAFE_ITEM_ID")
    return root / ITEMS_DIR / item_id


@contextmanager
def _ledger(root: Path):
    db = root / LEDGER_FILENAME
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS batch (
        batch_id TEXT PRIMARY KEY,
        manifest_fingerprint TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        cancelled INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS items (
        item_id TEXT PRIMARY KEY,
        report_id TEXT NOT NULL,
        state TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL,
        projection_digest TEXT,
        report_json_sha256 TEXT,
        report_html_sha256 TEXT,
        receipt_json_sha256 TEXT,
        relative_path TEXT,
        attempts INTEGER NOT NULL DEFAULT 0
    )""")
    try:
        yield conn
    finally:
        conn.close()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_files(item_path: Path, json_sha: str, html_sha: str, receipt_sha: str) -> bool:
    names = ("report.json", "report.html", "receipt.json")
    if not all((item_path / n).is_file() for n in names):
        return False
    try:
        receipt = ReportReceipt.model_validate_json((item_path / "receipt.json").read_bytes())
    except Exception:
        return False
    if receipt.report_markdown_sha256 is not None and (
            not (item_path / "report.md").is_file()
            or _sha256_bytes((item_path / "report.md").read_bytes()) != receipt.report_markdown_sha256):
        return False
    return (_sha256_bytes((item_path / "report.json").read_bytes()) == json_sha
            and _sha256_bytes((item_path / "report.html").read_bytes()) == html_sha
            and _sha256_bytes((item_path / "receipt.json").read_bytes()) == receipt_sha)


def _atomic_write_file(path: Path, data: bytes) -> None:
    assert_safe_path(path.parent)
    staging = path.parent / f".staging-{path.name}"
    if staging.exists():
        staging.unlink()
    with staging.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    staging.replace(path)
    # Windows fsync requires a writable descriptor even for an existing file.
    # The contents were already flushed in staging; this final sync makes the
    # post-rename artifact handle durable without a read-only fd error.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _atomic_write_artifacts(item_path: Path, files: dict[str, bytes], *, trusted_root: Path) -> None:
    if not {"report.html", "report.json", "receipt.json"} <= set(files) or (
            set(files) - {"report.html", "report.json", "receipt.json"} - {"report.md"}):
        raise ValueError("INVALID_ARTIFACT_SET")
    assert_safe_path(item_path, trusted_root=trusted_root)
    staging = item_path.parent / f".staging-{item_path.name}"
    if staging.exists():
        for child in staging.iterdir():
            child.unlink()
        staging.rmdir()
    staging.mkdir(parents=True)
    try:
        for name, data in files.items():
            target = staging / name
            with target.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        item_path.mkdir(parents=True, exist_ok=True)
        for name in files:
            src = staging / name
            dst = item_path / name
            dst.write_bytes(src.read_bytes())
            # On Windows os.fsync on a read-only fd fails with EBADF.
            with dst.open("r+b") as stream:
                os.fsync(stream.fileno())
    finally:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()


def validate_manifest(manifest: BatchManifest, runtime: HostRuntime,
                      *, caller_id: str, rights_scope: str,
                      enforce_source_pins: bool = True) -> None:
    manifest = BatchManifest.model_validate(manifest.model_dump())
    pins = source_pins_from_runtime(runtime)
    if manifest.host_id != runtime._configuration.host_id:
        raise ValueError("BATCH_HOST_MISMATCH")
    if manifest.caller_id != caller_id or manifest.rights_scope != rights_scope:
        raise ValueError("BATCH_SESSION_MISMATCH")
    if enforce_source_pins and manifest.source_pins != pins:
        raise ValueError("BATCH_SOURCE_PIN_MISMATCH")


def preview_batch(manifest: BatchManifest) -> dict[str, str]:
    return {item.item_id: item.request.report_id for item in manifest.items}


def _load_item_row(conn: sqlite3.Connection, item_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()


def _item_status_from_row(row: sqlite3.Row | None, spec: BatchItemSpec) -> BatchItemStatus:
    if row is None:
        return BatchItemStatus(item_id=spec.item_id, report_id=spec.request.report_id,
                               state="QUEUED", reason_code="PENDING",
                               input_fingerprint="", attempts=0)
    return BatchItemStatus(
        item_id=row["item_id"], report_id=row["report_id"], state=row["state"],
        reason_code=row["reason_code"], input_fingerprint=row["input_fingerprint"],
        projection_digest=row["projection_digest"],
        report_json_sha256=row["report_json_sha256"],
        report_html_sha256=row["report_html_sha256"],
        receipt_json_sha256=row["receipt_json_sha256"],
        relative_path=row["relative_path"], attempts=row["attempts"])


def status_batch(root: Path) -> BatchStatus:
    root = assert_safe_path(root)
    with _ledger(root) as conn:
        batch = conn.execute("SELECT * FROM batch").fetchone()
        if batch is None:
            raise ValueError("BATCH_NOT_FOUND")
        manifest = BatchManifest.model_validate_json(batch["manifest_json"])
        items = []
        pending = terminal = 0
        for spec in manifest.items:
            row = _load_item_row(conn, spec.item_id)
            status = _item_status_from_row(row, spec)
            items.append(status)
            if status.state in {"QUEUED", "RUNNING"}:
                pending += 1
            else:
                terminal += 1
        return BatchStatus(batch_id=batch["batch_id"],
                           manifest_fingerprint=batch["manifest_fingerprint"],
                           cancelled=bool(batch["cancelled"]), items=tuple(items),
                           pending=pending, terminal=terminal)


def cancel_batch(root: Path) -> BatchStatus:
    root = assert_safe_path(root)
    with _ledger(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute("SELECT * FROM batch").fetchone()
        if batch is None:
            raise ValueError("BATCH_NOT_FOUND")
        conn.execute("UPDATE batch SET cancelled=1")
        conn.execute(
            "UPDATE items SET state='CANCELLED', reason_code='BATCH_CANCELLED' "
            "WHERE state='QUEUED'")
        conn.execute("COMMIT")
    return status_batch(root)


HookAfterWrite = Callable[[str], None]


def run_batch(
    root: Path,
    manifest: BatchManifest,
    runtime: HostRuntime,
    *,
    resume: bool = False,
    caller_id: str,
    rights_scope: str,
    scientific_assets: tuple[ScientificReportAsset, ...] = (),
    scientific_sources: dict[str, bytes] | None = None,
    method_bodies: dict[str, bytes] | None = None,
    after_artifact_write_before_checkpoint: HookAfterWrite | None = None,
) -> BatchReceipt:
    """Serial durable batch. Caller must match manifest session binding."""
    validate_manifest(manifest, runtime, caller_id=caller_id, rights_scope=rights_scope,
                        enforce_source_pins=not resume)
    asset_digests = tuple(sorted(_digest(a) for a in scientific_assets))
    if asset_digests != tuple(sorted(manifest.scientific_asset_digests)):
        raise ValueError("BATCH_SCIENTIFIC_ASSET_CHANGED")
    fingerprint = manifest_fingerprint(manifest)
    if not resume:
        root = assert_safe_path(root, must_not_exist=True)
        root.mkdir(parents=True)
    else:
        root = assert_safe_path(root)
        if not root.is_dir():
            raise ValueError("BATCH_RESUME_MISSING")

    compose = report_session(runtime, authenticated_caller=caller_id,
                             authorized_view=rights_scope, scientific_assets=scientific_assets,
                             scientific_sources=scientific_sources or {},
                             method_bodies=method_bodies or {})
    manifest_bytes = canonical_bytes(manifest)
    manifest_path = root / MANIFEST_FILENAME
    work_performed = False

    with _ledger(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM batch").fetchone()
        if existing is None:
            if resume:
                raise ValueError("BATCH_RESUME_MISSING")
            conn.execute(
                "INSERT INTO batch (batch_id, manifest_fingerprint, manifest_json, cancelled) "
                "VALUES (?, ?, ?, 0)",
                (manifest.batch_id, fingerprint, manifest.model_dump_json()),
            )
            for spec in manifest.items:
                conn.execute(
                    "INSERT INTO items (item_id, report_id, state, reason_code, "
                    "input_fingerprint, attempts) VALUES (?, ?, 'QUEUED', 'PENDING', '', 0)",
                    (spec.item_id, spec.request.report_id),
                )
        else:
            if existing["batch_id"] != manifest.batch_id:
                raise ValueError("BATCH_ID_MISMATCH")
            if existing["manifest_fingerprint"] != fingerprint:
                raise BatchManifestConflict("BATCH_MANIFEST_CONFLICT")
        conn.execute("COMMIT")

        if not manifest_path.is_file():
            _atomic_write_file(manifest_path, manifest_bytes)
        elif manifest_path.read_bytes() != manifest_bytes:
            raise ValueError("BATCH_MANIFEST_TAMPERED")

        cancelled = bool(conn.execute("SELECT cancelled FROM batch").fetchone()["cancelled"])

        for spec in manifest.items:
            if cancelled:
                row = _load_item_row(conn, spec.item_id)
                if row and row["state"] == "QUEUED":
                    conn.execute(
                        "UPDATE items SET state='CANCELLED', reason_code='BATCH_CANCELLED' "
                        "WHERE item_id=?", (spec.item_id,))
                continue

            item_path = _item_dir(root, spec.item_id)
            assert_safe_path(item_path, trusted_root=root)
            rel_path = f"{ITEMS_DIR}/{spec.item_id}"
            current_fp = item_input_fingerprint(manifest, spec)
            row = _load_item_row(conn, spec.item_id)
            prior = _item_status_from_row(row, spec)

            if prior.state in {"DONE_METADATA", "DONE_SCIENTIFIC_UNREVIEWED", "PARTIAL_METADATA", "BLOCKED_METHOD", "BLOCKED_EXTERNAL"}:
                if row["input_fingerprint"] != current_fp:
                    conn.execute(
                        "UPDATE items SET state='STALE', reason_code='INPUT_FINGERPRINT_CHANGED', "
                        "projection_digest=NULL, report_json_sha256=NULL, report_html_sha256=NULL, "
                        "receipt_json_sha256=NULL, relative_path=NULL WHERE item_id=?",
                        (spec.item_id,))
                    prior = prior.model_copy(update={"state": "STALE"})
                    work_performed = True
                elif row["projection_digest"] and _verify_files(
                        item_path, row["report_json_sha256"],
                        row["report_html_sha256"], row["receipt_json_sha256"]):
                    projection = ReportProjection.model_validate_json(
                        (item_path / "report.json").read_bytes())
                    live = compose(spec.request)
                    if live.digest == row["projection_digest"] == projection.digest:
                        continue
                    work_performed = True
                # fall through to regenerate

            if prior.state == "CANCELLED":
                continue

            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE items SET state='RUNNING', reason_code='IN_PROGRESS', "
                "input_fingerprint=?, attempts=attempts+1 WHERE item_id=?",
                (current_fp, spec.item_id),
            )
            conn.execute("COMMIT")
            work_performed = True

            try:
                projection = compose(spec.request)
                files = artifacts(projection)
                raw = files["report.json"]
                html = files["report.html"]
                receipt_raw = files["receipt.json"]
                receipt = ReportReceipt.model_validate_json(receipt_raw)
                state = _ledger_status(projection)
                reason = _reason_for(projection, state)

                _atomic_write_artifacts(item_path, files, trusted_root=root)
                if after_artifact_write_before_checkpoint is not None:
                    after_artifact_write_before_checkpoint(spec.item_id)

                json_sha = _sha256_bytes(raw)
                html_sha = _sha256_bytes(html)
                receipt_sha = _sha256_bytes(receipt_raw)
                if receipt.report_json_sha256 != json_sha or receipt.report_html_sha256 != html_sha:
                    raise ValueError("RECEIPT_HASH_MISMATCH")

                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE items SET state=?, reason_code=?, projection_digest=?, "
                    "report_json_sha256=?, report_html_sha256=?, receipt_json_sha256=?, "
                    "relative_path=? WHERE item_id=?",
                    (state, reason, projection.digest, json_sha, html_sha, receipt_sha,
                     rel_path, spec.item_id),
                )
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE items SET state='FAILED_RETRYABLE', reason_code=? WHERE item_id=?",
                    (type(exc).__name__, spec.item_id),
                )
                conn.execute("COMMIT")
                raise

    return _export_receipt(root, manifest, fingerprint, work_performed=work_performed)


def resume_batch(root: Path, manifest: BatchManifest, runtime: HostRuntime, *,
                   caller_id: str, rights_scope: str,
                   scientific_assets: tuple[ScientificReportAsset, ...] = (),
                   scientific_sources: dict[str, bytes] | None = None,
                   method_bodies: dict[str, bytes] | None = None,
                   after_artifact_write_before_checkpoint: HookAfterWrite | None = None) -> BatchReceipt:
    return run_batch(root, manifest, runtime, resume=True, caller_id=caller_id,
                       rights_scope=rights_scope,
                       scientific_assets=scientific_assets,
                       scientific_sources=scientific_sources,
                       method_bodies=method_bodies,
                     after_artifact_write_before_checkpoint=after_artifact_write_before_checkpoint)


def _export_receipt(
    root: Path,
    manifest: BatchManifest,
    fingerprint: str,
    *,
    work_performed: bool,
) -> BatchReceipt:
    status = status_batch(root)
    selection_digests = []
    for spec in manifest.items:
        for sel in spec.request.selections:
            selection_digests.append(public_selection_digest(sel))
    selection_digests = tuple(sorted(set(selection_digests)))
    terminal_ok = {"DONE_METADATA", "DONE_SCIENTIFIC_UNREVIEWED", "PARTIAL_METADATA",
                   "BLOCKED_METHOD", "BLOCKED_EXTERNAL"}
    code_pass = all(i.state in terminal_ok for i in status.items)
    receipt_path = root / RECEIPT_FILENAME
    index_path = root / INDEX_FILENAME
    existing_completed_at: str | None = None
    if receipt_path.is_file():
        try:
            existing_completed_at = BatchReceipt.model_validate_json(
                receipt_path.read_bytes()).completed_at
        except Exception:
            existing_completed_at = None
    if work_performed or existing_completed_at is None:
        completed_at = datetime.now(timezone.utc).isoformat()
    else:
        completed_at = existing_completed_at
    receipt = BatchReceipt(
        batch_id=manifest.batch_id,
        manifest_fingerprint=fingerprint,
        host_id=manifest.host_id,
        caller_id=manifest.caller_id,
        rights_scope=manifest.rights_scope,
        template_version=manifest.items[0].request.template_version,
        item_count=len(manifest.items),
        items=status.items,
        code_pass=code_pass,
        completed_at=completed_at,
        selection_snapshot_digests=selection_digests,
    )
    index = {
        "batch_id": manifest.batch_id,
        "manifest_fingerprint": fingerprint,
        "items": [i.model_dump(mode="json") for i in status.items],
    }
    receipt_bytes = canonical_bytes(receipt)
    index_bytes = canonical_bytes(index)
    if (not work_performed and receipt_path.is_file() and index_path.is_file()
            and receipt_path.read_bytes() == receipt_bytes
            and index_path.read_bytes() == index_bytes):
        return BatchReceipt.model_validate_json(receipt_path.read_bytes())
    staging = root / ".receipt-staging"
    staging.mkdir(exist_ok=True)
    try:
        (staging / RECEIPT_FILENAME).write_bytes(receipt_bytes)
        (staging / INDEX_FILENAME).write_bytes(index_bytes)
        for name in (RECEIPT_FILENAME, INDEX_FILENAME):
            data = (staging / name).read_bytes()
            _atomic_write_file(root / name, data)
    finally:
        for child in staging.iterdir():
            child.unlink()
        staging.rmdir()
    return receipt
