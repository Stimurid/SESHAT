"""M4 transport vs semantic delivery boundaries (synthetic contracts only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DeliveryStatus = Literal["REPORT_COMPLETE", "REPORT_INCOMPLETE", "DELIVERY_DENIED"]


@dataclass(frozen=True)
class StoredInputView:
    """What the host stored for a source version."""

    source_id: str
    source_version: str
    byte_length: int
    content_sha256: str
    complete: bool


@dataclass(frozen=True)
class DeliveredRange:
    """What was actually delivered to a consumer in one transport hop."""

    offset: int
    length: int
    finish: str
    routing_metadata_only: bool = False


def assess_delivery(
    stored: StoredInputView,
    delivered: DeliveredRange,
    *,
    admitted_byte_length: int,
    policy: str,
) -> tuple[DeliveryStatus, str]:
    """Distinguish stored input from delivered ranges; transport SUCCESS != full answer."""

    end = delivered.offset + delivered.length
    if end > stored.byte_length:
        return "DELIVERY_DENIED", "DELIVERED_RANGE_EXCEEDS_STORED"
    if delivered.routing_metadata_only and delivered.finish == "stop":
        return "REPORT_INCOMPLETE", "ROUTING_METADATA_FINISH_STOP"
    if (
        policy == "FULL_REQUIRED"
        and delivered.length < stored.byte_length
        and delivered.finish == "stop"
    ):
        return "REPORT_INCOMPLETE", "PARTIAL_WITH_FINISH_STOP"
    if policy == "FULL_REQUIRED" and admitted_byte_length < stored.byte_length:
        return "REPORT_INCOMPLETE", "FULL_REQUIRED_ADMITTED_BYTES_SHORT"
    if delivered.length < stored.byte_length and policy == "FULL_REQUIRED":
        return "REPORT_INCOMPLETE", "PARTIAL_WITHOUT_FULL_ADMISSION"
    if not stored.complete:
        return "REPORT_INCOMPLETE", "STORED_MARKED_INCOMPLETE"
    return "REPORT_COMPLETE", "DELIVERED_MATCHES_STORED_CONTRACT"


def preview_bounds(content: str, *, max_preview: int = 50 * 1024) -> dict[str, Any]:
    lines = content.splitlines()
    long_lines = [idx for idx, line in enumerate(lines, 1) if len(line) > 2000]
    preview = content[:max_preview]
    return {
        "preview_bytes": len(preview.encode("utf-8")),
        "truncated": len(content.encode("utf-8")) > max_preview,
        "long_line_numbers": long_lines,
        "missing_middle_detected": "…" in content and len(content) > max_preview,
        "end_marker_only": content.strip().endswith("[END]") and len(content.strip()) < 32,
    }


def line_number_binding(
    artifact_version: str, reported_line: int, *, actual_version: str
) -> str:
    if artifact_version != actual_version:
        return "LINE_NUMBER_STALE_ARTIFACT_VERSION"
    if reported_line < 1:
        return "LINE_NUMBER_INVALID"
    return "LINE_NUMBER_BOUND_TO_ARTIFACT_VERSION"


def permission_may_not_become_unknown(explicit_permission: bool, output_unknown: bool) -> str:
    if explicit_permission and output_unknown:
        return "PERMISSION_ERASED_TO_UNKNOWN"
    return "OK"


def scoped_success_not_inherited(old_purpose_ok: bool, new_purpose: str, inherited: bool) -> str:
    if inherited and not old_purpose_ok:
        return "INHERITED_VALIDATION_WITHOUT_OLD_SCOPE"
    if new_purpose and old_purpose_ok and inherited:
        return "NEW_PURPOSE_CANNOT_INHERIT_OLD_VALIDATION"
    return "OK"
