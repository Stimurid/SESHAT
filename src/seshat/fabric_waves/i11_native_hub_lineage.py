"""Honest provenance from existing Hub receipt plus independently read source bytes.

The Hub's native receipt DOES NOT certify PDF/page-text/method/ledger pins.
This record keeps native terminal evidence separate from operator source checks,
and never supplies a synthetic terminal receipt for I11 v2 admission.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from seshat.fabric_waves.i11_activity_network import AUTHORIAL_I11_SHA256


class NativeHubLineageError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(obj: dict[str, Any]) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _load(raw: bytes, what: str) -> dict[str, Any]:
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeHubLineageError(f"INVALID_JSON_{what}") from exc
    if not isinstance(obj, dict):
        raise NativeHubLineageError(f"INVALID_OBJECT_{what}")
    return obj


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def audit_native_hub_source(
    *,
    native_receipt_bytes: bytes,
    publication_manifest_bytes: bytes,
    original_pdf_bytes: bytes,
    model_carrier_canonical_bytes: bytes,
    model_carrier_worktree_bytes: bytes,
    original_model_stdout_bytes: bytes,
    expected_job_id: str,
    pinned_pdf_sha256: str,
    pinned_model_carrier_sha256: str,
    pinned_stdout_sha256: str,
    work_id: str,
    git_commit: str | None,
    source_git_path: str | None,
    method_body_bytes: bytes | None = None,
    method_sha256: str = AUTHORIAL_I11_SHA256,
) -> dict[str, Any]:
    """Read native evidence and recompute independent operator-owned source pins.

    A content-equivalent Git LF blob and Windows CRLF working tree count as
    *different byte carriers*. No exact provider-read byte attestation exists.
    """
    native = _load(native_receipt_bytes, "NATIVE_RECEIPT")
    published = _load(publication_manifest_bytes, "PUBLICATION_MANIFEST")
    if (
        native.get("schema") != "AIYE_LOCAL_EXEC_RECEIPT_v0.1"
        or native.get("job_id") != expected_job_id
        or native.get("state") != "SUCCEEDED"
        or native.get("exit_code") != 0
        or not native.get("ended_at")
    ):
        raise NativeHubLineageError("NATIVE_HUB_TERMINAL_UNVERIFIED")
    if (
        published.get("schema") != "AIYE_PUBLICATION_MANIFEST_v0.1"
        or published.get("job_id") != expected_job_id
        or published.get("terminal_status") != "SUCCEEDED"
        or published.get("error_class") is not None
    ):
        raise NativeHubLineageError("PUBLICATION_MANIFEST_JOB_MISMATCH")
    pub_stdout = published.get("output_manifest", {}).get("stdout_sha256")
    if (
        _sha(original_model_stdout_bytes) != pinned_stdout_sha256
        or pub_stdout != pinned_stdout_sha256
    ):
        raise NativeHubLineageError("MODEL_STDOUT_MANIFEST_MISMATCH")
    if _sha(original_pdf_bytes) != pinned_pdf_sha256:
        raise NativeHubLineageError("ORIGINAL_PDF_PIN_MISMATCH")
    if _sha(model_carrier_canonical_bytes) != pinned_model_carrier_sha256:
        raise NativeHubLineageError("CANONICAL_CARRIER_PIN_MISMATCH")
    if _lf(model_carrier_worktree_bytes) != _lf(model_carrier_canonical_bytes):
        raise NativeHubLineageError("MODEL_WORKTREE_CONTENT_NOT_EQUIVALENT")
    if not work_id or not expected_job_id.startswith("jx-"):
        raise NativeHubLineageError("WORK_AND_JOB_IDS_REQUIRED")
    if method_sha256 != AUTHORIAL_I11_SHA256:
        raise NativeHubLineageError("WRONG_FROZEN_METHOD_PIN")
    if method_body_bytes is not None and _sha(method_body_bytes) != method_sha256:
        raise NativeHubLineageError("METHOD_BODY_BYTES_MISMATCH")
    equality = (
        "BYTE_IDENTICAL"
        if model_carrier_worktree_bytes == model_carrier_canonical_bytes
        else "LF_NORMALIZED_EQUIVALENT_NOT_BYTE_IDENTICAL"
    )
    content = {
        "schema": "seshat.i11.native_hub_lineage.v1",
        "job_id": expected_job_id,
        "work_id": work_id,
        "native_receipt_schema": native["schema"],
        "native_receipt_sha256": _sha(native_receipt_bytes),
        "native_terminal_state": "SUCCEEDED",
        "native_receipt_ended_at": native["ended_at"],
        "publication_manifest_sha256": _sha(publication_manifest_bytes),
        "publication_status": published.get("publication_status"),
        "original_pdf_sha256": _sha(original_pdf_bytes),
        "canonical_page_carrier_sha256": _sha(model_carrier_canonical_bytes),
        "worktree_page_carrier_sha256": _sha(model_carrier_worktree_bytes),
        "source_carrier_relation": equality,
        "source_git_commit": git_commit,
        "source_git_path": source_git_path,
        "stdout_sha256": _sha(original_model_stdout_bytes),
        "frozen_method_operator_pin_sha256": method_sha256,
        "frozen_method_byte_check": (
            "BYTE_MATCH" if method_body_bytes is not None else "NOT_PERFORMED"
        ),
        "hub_attested_original_pdf_sha": False,
        "hub_attested_model_carrier_sha": False,
        "hub_attested_method_body_sha": False,
        "hub_attested_event_ledger_sha": False,
        "exact_provider_read_bytes": "NOT_ATTESTED_BY_NATIVE_HUB",
        "admission_status": "PARTIAL_OPERATOR_SOURCE_REHASH_ONLY",
        "genuine_two_real_i11_r03_v2_admission": "BLOCKED",
        "model_claims_independently_science_accepted": False,
        "customer_release": "BLOCKED",
        "source_material_embedded": False,
    }
    return {**content, "projection_sha256": _sha(_canon(content))}


def save_and_verify_lineage(path: Path, lineage: dict[str, Any]) -> str:
    """Private immutable write and digest readback. Never embeds raw input bytes."""
    if lineage.get("schema") != "seshat.i11.native_hub_lineage.v1":
        raise NativeHubLineageError("WRONG_LINEAGE_SCHEMA")
    if lineage.get("genuine_two_real_i11_r03_v2_admission") != "BLOCKED":
        raise NativeHubLineageError("IMPROPER_ADMISSION_CLAIM")
    canonical = json.dumps(lineage, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    content = canonical.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise NativeHubLineageError("IMMUTABLE_LINEAGE_DRIFT") from None
    check = path.read_bytes()
    if check != content:
        raise NativeHubLineageError("LINEAGE_READBACK_MISMATCH")
    return _sha(check)
