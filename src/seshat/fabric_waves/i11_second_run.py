"""Fail-closed gate for a second authorial I11 ModelRun.

A published CC BY license and an F07 PDF-read receipt are not a model-transfer
grant. This module never submits a paid job.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    CCBY_PDF_SHA256,
    OBSERVED_I11_JOB_ID,
)
from seshat.fabric_waves.i11_real_admission import (
    identity_is_predeclared,
    permission_pins_predeclared_package,
)

_OWNER_EXCLUSION_SCHEMA = "seshat.owner_source_exclusion.v1"

BLOCKED_SECOND_MODELRUN = "BLOCKED_SECOND_MODELRUN"
MODEL_TRANSFER_GRANT = "GRANTED_THIS_SOURCE_VERSION_AND_DERIVED_TEXT"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fold(value: object) -> str:
    return str(value or "").strip().casefold()


def existing_job_for_source(
    job_registry: Mapping[str, Any] | None,
    *,
    source_sha256: str,
) -> str | None:
    if not job_registry:
        return None
    jobs = job_registry.get("jobs") if isinstance(job_registry.get("jobs"), list) else []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if _fold(item.get("source_sha256")) == _fold(source_sha256):
            job_id = str(item.get("job_id") or "")
            if job_id:
                return job_id
    return None


def admit_second_authorial_i11_run(
    *,
    exclusion_policy: dict[str, Any],
    f07_permission_b: dict[str, Any] | None,
    source_id: str,
    source_name: str = "",
    source_bytes: bytes | None = None,
    pages_bytes: bytes | None = None,
    job_registry: Mapping[str, Any] | None = None,
    submit_new_paid_job: bool = False,
) -> dict[str, Any]:
    """Return a precise block unless every required grant is present.

    Even a complete grant does not launch a model from this function.
    """
    if submit_new_paid_job:
        raise ValueError("I11_DUPLICATE_LAUNCH")
    reasons: list[str] = []
    if not (
        exclusion_policy.get("operator_supplied") is True
        and exclusion_policy.get("schema") == _OWNER_EXCLUSION_SCHEMA
        and exclusion_policy.get("authority") == "OWNER_EXPLICIT"
        and exclusion_policy.get("status") == "PERMANENT_ACTIVE_EXCLUSION"
    ):
        reasons.append("OWNER_EXCLUSION_POLICY_MISSING")
    if f07_permission_b is None:
        reasons.append("F07_MODEL_TRANSFER_GRANT_MISSING")
    else:
        if f07_permission_b.get("schema") != "seshat.f07_per_operation_permission.v1":
            reasons.append("F07_PERMISSION_INVALID")
        if f07_permission_b.get("operation_id") != AUTHORIAL_I11_ID:
            reasons.append("F07_OPERATION_MISMATCH")
        if f07_permission_b.get("rights_class") != "FULL_REQUIRED":
            reasons.append("F07_RIGHTS_CLASS_NOT_FULL_REQUIRED")
        if identity_is_predeclared(source_id, source_name):
            reasons.append("F07_PERMISSION_SOURCE_MISMATCH")
        if permission_pins_predeclared_package(f07_permission_b):
            reasons.append("F07_PERMISSION_SOURCE_MISMATCH")
        perm_sha = _fold(f07_permission_b.get("source_sha256"))
        if perm_sha == CCBY_PDF_SHA256:
            reasons.append("F07_PERMISSION_SOURCE_MISMATCH")
        if f07_permission_b.get("model_transfer") != MODEL_TRANSFER_GRANT:
            reasons.append("MODEL_TRANSFER_GRANT_MISSING")
        if not str(f07_permission_b.get("budget_authorization") or "").strip():
            reasons.append("MODEL_BUDGET_AUTHORIZATION_MISSING")
        if source_bytes is not None:
            digest = _sha(source_bytes)
            if perm_sha and digest != perm_sha:
                reasons.append("SOURCE_SHA_DRIFT")
            prior = existing_job_for_source(job_registry, source_sha256=digest)
            if prior and prior != OBSERVED_I11_JOB_ID:
                reasons.append("EXISTING_JOB_DO_NOT_RELAUNCH")
            if prior == OBSERVED_I11_JOB_ID:
                reasons.append("F07_PERMISSION_SOURCE_MISMATCH")
        if pages_bytes is not None:
            pages_sha = _fold(f07_permission_b.get("pages_sha256"))
            if pages_sha and _sha(pages_bytes) != pages_sha:
                reasons.append("PAGES_SHA_DRIFT")
    if reasons:
        return {
            "status": BLOCKED_SECOND_MODELRUN,
            "reasons": tuple(dict.fromkeys(reasons)),
            "launched": False,
            "provider": None,
            "job_id": None,
            "publication_license_is_not_grant": True,
            "scientific_acceptance": "NOT_PERFORMED",
            "customer_release": "BLOCKED",
            "provenance": "SELF_OBSERVED_UNATTESTED",
        }
    return {
        "status": BLOCKED_SECOND_MODELRUN,
        "reasons": ("HUB_MODEL_TRANSPORT_NOT_EXPOSED_IN_THIS_SCENE",),
        "launched": False,
        "provider": None,
        "job_id": None,
        "publication_license_is_not_grant": True,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "provenance": "SELF_OBSERVED_UNATTESTED",
    }
