"""Public-safe error surfaces for fabric runs.

Untrusted method bodies and providers must never leak raw exception text into
persisted ledgers, traces or demo exports.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_SAFE_APORIA_CODE = re.compile(r"^[A-Z][A-Z0-9_]{3,96}$")

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


def sanitize_aporia_detail(aporia: str, *, activation_id: str) -> str:
    """Retain fixture-safe aporia codes; never persist arbitrary provider prose."""

    blocked_tokens = ("SECRET", "DO_NOT_PERSIST", "PASSWORD", "TOKEN")
    if any(t in aporia for t in blocked_tokens):
        return f"BODY_APORIA:{opaque_error_id(f'{activation_id}:{aporia}')}"
    head = aporia.split(":", 1)[0]
    if _SAFE_APORIA_CODE.fullmatch(head) and len(aporia) <= 512:
        return aporia
    if aporia.startswith("SYNTHETIC_") and len(aporia) <= 512:
        return aporia
    return f"BODY_APORIA:{opaque_error_id(f'{activation_id}:{aporia}')}"


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
