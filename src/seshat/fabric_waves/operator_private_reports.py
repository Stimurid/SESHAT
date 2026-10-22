"""Private R01/R02 preview from an actually executed local MethodBody.

This is an operator-only *projection* of a locally journalled invocation,
not a new model call, source-rights certificate or scientific review.
This module never publishes or prints original source/method bytes. A local
journal is checked, but its contents are not independently authenticated.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from seshat.contracts import AcceptanceState, RawAccessPolicy, SourceAccessStatus
from seshat.fabric_waves.contracts import EpistemicLevel
from seshat.fabric_waves.operator_methodbody import OperatorRunLedger, OperatorRunReceipt
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger
from seshat.fabric_waves.sediment import payload_hash


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def compose_private_operator_r01r02(
    receipt: OperatorRunReceipt,
    *,
    ledger: OperatorRunLedger | SQLiteOperatorRunLedger,
    source_bytes: bytes,
    method_invocation_bytes: bytes,
) -> dict[str, Any]:
    """Return an owner-private structured R01/R02, fail-closed on mismatched bytes.

    This checks source spans *again* instead of trusting claims copied from a
    serialized receipt. Even an internally consistent user-edited receipt is
    only SELF_OBSERVED, never independent certification.
    """
    if _sha(source_bytes) != receipt.source_sha256 or not source_bytes:
        raise ValueError("OPERATOR_R01R02_SOURCE_PIN_MISMATCH")
    if _sha(method_invocation_bytes) != receipt.method_body_invocation_sha256 or not method_invocation_bytes:
        raise ValueError("OPERATOR_R01R02_METHOD_PIN_MISMATCH")
    if receipt.provenance != "SELF_OBSERVED_UNATTESTED" or receipt.scientific_acceptance != "NOT_ASSERTED":
        raise ValueError("OPERATOR_R01R02_FALSE_AUTHORITY")
    if receipt.rights_attested != "NO" or receipt.model_run_attested != "NO":
        raise ValueError("OPERATOR_R01R02_FALSE_AUTHORITY")
    if receipt.invocation.exit_status != "OK":
        raise ValueError("OPERATOR_R01R02_METHOD_NOT_EXECUTED")
    sed = receipt.output_sediment
    if (
        sed.acceptance_state != AcceptanceState.PROPOSED
        or sed.epistemic_level is EpistemicLevel.E5
        or sed.object_type != "operator.methodbody.reconstruction.v1"
        or sed.source_carrier_refs != (receipt.source_id,)
        or sed.sediment_id != f"operator:{receipt.run_id}:{receipt.job_id}"
        or not sed.method_body_refs
        or len(sed.method_body_refs) != 1
        or sed.method_body_refs[0].method_body_id != receipt.method_body_id
        or sed.method_body_refs[0].version != receipt.method_body_version
        or "SELF_OBSERVED_UNATTESTED" not in sed.provenance
    ):
        raise ValueError("OPERATOR_R01R02_INVALID_SEDIMENT_BINDING")
    if sed.payload_hash != payload_hash(sed.payload) or sed.version != sed.payload_hash:
        raise ValueError("OPERATOR_R01R02_SEDIMENT_PAYLOAD_CHANGED")
    expected_output = _sha(
        f"{sed.payload_hash}:{receipt.invocation.stdout_sha256}".encode("utf-8")
    )
    if receipt.output_digest != expected_output:
        raise ValueError("OPERATOR_R01R02_OUTPUT_RECEIPT_CHANGED")
    manifest = receipt.source_access_manifest
    sediment_manifest = sed.source_access_manifest
    if manifest is None or sediment_manifest is None:
        raise ValueError("OPERATOR_R01R02_F07_INCOMPLETE")
    if sediment_manifest != manifest:
        raise ValueError("OPERATOR_R01R02_F07_INCOMPLETE")
    if (
        manifest.policy != RawAccessPolicy.FULL_REQUIRED
        or not manifest.all_declared_sources_verified
        or len(manifest.receipts) != 1
    ):
        raise ValueError("OPERATOR_R01R02_F07_INCOMPLETE")
    read = manifest.receipts[0]
    if (
        read.status != SourceAccessStatus.VERIFIED
        or read.carrier_id != receipt.source_id
        or read.source_version != receipt.source_version
        or read.content_sha256 != receipt.source_sha256
        or read.byte_length != len(source_bytes)
        or read.returned_byte_length != len(source_bytes)
        or read.read_kind != "FULL"
    ):
        raise ValueError("OPERATOR_R01R02_F07_INCOMPLETE")

    raw_claims = sed.payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("OPERATOR_R01R02_NO_GROUNDED_CLAIMS")
    seen: set[tuple[int, int, str]] = set()
    anchors: list[dict[str, Any]] = []
    for index, claim in enumerate(raw_claims, start=1):
        if not isinstance(claim, dict):
            raise ValueError("OPERATOR_R01R02_BAD_CLAIM")
        text = claim.get("text")
        excerpt = claim.get("evidence_excerpt")
        start = claim.get("byte_offset")
        length = claim.get("byte_length")
        if (
            not isinstance(text, str) or not text.strip()
            or not isinstance(excerpt, str) or not excerpt
            or type(start) is not int or type(length) is not int
            or start < 0 or length < 1 or start + length > len(source_bytes)
            or claim.get("page") is not None
        ):
            raise ValueError("OPERATOR_R01R02_BAD_CLAIM")
        expected_excerpt = source_bytes[start : start + length]
        if expected_excerpt != excerpt.encode("utf-8"):
            raise ValueError("OPERATOR_R01R02_SPAN_MISMATCH")
        key = (start, length, excerpt)
        if key in seen:
            raise ValueError("OPERATOR_R01R02_DUPLICATE_EVIDENCE")
        seen.add(key)
        anchors.append({
            "claim_id": f"claim-{index:03d}",
            "claim_text": text,  # OWNER_PRIVATE only; not safe public copy
            "source_id": receipt.source_id,
            "source_version": receipt.source_version,
            "source_sha256": receipt.source_sha256,
            "byte_offset": start,
            "byte_length": length,
            "excerpt_sha256": _sha(expected_excerpt),
            "evidence_status": "EXACT_SOURCE_SPAN_VERIFIED_CLAIM_TRUTH_NOT_REVIEWED",
        })
    if "notes" not in sed.payload or not isinstance(sed.payload["notes"], list):
        raise ValueError("OPERATOR_R01R02_BAD_RESULT_PAYLOAD")

    # A constructed Pydantic receipt is not evidence of an executed method.
    # Require the prior completed operator ledger record, and recheck the
    # caller-provided receipt against that original. This remains a LOCAL
    # operator journal, *not* a trusted issuer or independent attestation.
    if not isinstance(ledger, (OperatorRunLedger, SQLiteOperatorRunLedger)):
        raise ValueError("OPERATOR_R01R02_VALID_LEDGER_REQUIRED")
    try:
        recorded = ledger.get(receipt.run_id)
    except ValueError as exc:
        raise ValueError("OPERATOR_R01R02_UNRECORDED_RUN") from exc
    if recorded != receipt:
        raise ValueError("OPERATOR_R01R02_LEDGER_RECEIPT_MISMATCH")

    r01 = {
        "report_id": "R01",
        "status": "SOURCE_GROUNDED_UNREVIEWED",
        "research_object_id": sed.research_object_id,
        "method_body_id": receipt.method_body_id,
        "method_body_version": receipt.method_body_version,
        "source_id": receipt.source_id,
        "source_version": receipt.source_version,
        "claims": anchors,
        "limitation": "Exact source snippets were read, but interpretive claims lack domain review.",
    }
    r02 = {
        "report_id": "R02",
        "status": "SOURCE_GROUNDED_UNREVIEWED",
        "graph_nodes": [
            {"id": receipt.source_id, "kind": "SOURCE", "version": receipt.source_version},
            {"id": receipt.method_body_id, "kind": "METHOD", "version": receipt.method_body_version},
            {"id": receipt.run_id, "kind": "ACTUAL_LOCAL_INVOCATION", "job_id": receipt.job_id},
            {"id": sed.sediment_id, "kind": "PROPOSED_SEDIMENT", "version": sed.version},
        ] + [{"id": a["claim_id"], "kind": "CLAIM", "excerpt_sha256": a["excerpt_sha256"]} for a in anchors],
        "graph_edges": [
            {"from": receipt.source_id, "to": receipt.run_id, "relation": "SOURCE_READ"},
            {"from": receipt.method_body_id, "to": receipt.run_id, "relation": "METHOD_CALLED"},
            {"from": receipt.run_id, "to": sed.sediment_id, "relation": "PRODUCED_PROVISIONAL"},
        ] + [
            {"from": sed.sediment_id, "to": a["claim_id"], "relation": "CONTAINS_CLAIM"}
            for a in anchors
        ],
        "output_sediment_id": sed.sediment_id,
        "output_sediment_version": sed.version,
        "method_invocation_sha256": receipt.method_body_invocation_sha256,
        "source_sha256": receipt.source_sha256,
        "output_digest": receipt.output_digest,
        "limitation": "Operator-local evidence is not an independently verified provider or owner decision.",
    }
    content = {
        "schema": "seshat.operator_private_r01r02.v1",
        "visibility": "OWNER_PRIVATE_ONLY",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "source_rights": "OPERATOR_DECLARED_NOT_INDEPENDENTLY_ATTESTED",
        "model_run_attested": False,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "run_id": receipt.run_id,
        "job_id": receipt.job_id,
        "method_interpretation": receipt.method_interpretation,
        "reports": [r01, r02],
    }
    return {**content, "projection_sha256": _sha(_canonical(content))}


def verify_private_operator_r01r02(
    projection: dict[str, Any],
    receipt: OperatorRunReceipt,
    *,
    ledger: OperatorRunLedger | SQLiteOperatorRunLedger,
    source_bytes: bytes,
    method_invocation_bytes: bytes,
) -> None:
    """Fresh-process readback; never a scientific or third-party attestation."""
    actual = compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=source_bytes,
        method_invocation_bytes=method_invocation_bytes
    )
    if _canonical(projection) != _canonical(actual):
        raise ValueError("OPERATOR_R01R02_PROJECTION_REPLAY_MISMATCH")
