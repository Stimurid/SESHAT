"""Public-safe error surfaces for fabric runs.

Untrusted method bodies and providers must never leak raw exception text into
persisted ledgers, traces or demo exports.
"""

from __future__ import annotations

import hashlib
from typing import Any

PUBLIC_ERROR_CODES: frozenset[str] = frozenset(
    {
        "BODY_VIOLATION",
        "BODY_EXCEPTION",
        "BODY_APORIA",
        "MISSING_METHOD_BODY",
        "SOURCE_ACCESS_DENIED",
        "SEDIMENT_CONTRACT_VIOLATION",
    }
)


def opaque_error_id(material: str) -> str:
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"err-{digest}"


def sanitize_provider_error(
    *,
    code: str,
    internal_message: str,
    activation_id: str,
) -> tuple[str, str]:
    """Return (error_code, public_detail) safe for ledger export."""

    safe_code = code if code in PUBLIC_ERROR_CODES else "BODY_EXCEPTION"
    err_id = opaque_error_id(f"{activation_id}:{internal_message}")
    return safe_code, f"{safe_code}:{err_id}"


def sanitize_receipt_material(material: dict[str, Any]) -> dict[str, Any]:
    """Strip exception strings from receipt hashes while keeping structure."""

    cleaned = dict(material)
    if "error" in cleaned and isinstance(cleaned["error"], str):
        cleaned["error"] = opaque_error_id(cleaned["error"])
    return cleaned
