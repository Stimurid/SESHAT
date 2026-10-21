"""Synthetic-only F07 -> isolated PDF child -> F08 candidate bridge.

The result is intentionally not a PDF page proof. A child can fabricate a quote
match, so even when all child checks agree, the strongest status is
UNATTESTED_CHILD_OBSERVATIONS. Never release this as science or source rights.
No untrusted PDF is parsed in this module.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from seshat.contracts import RawAccessPolicy, SourceAccessStatus
from seshat.pdf_claims import MAX_RESPONSE_BYTES, ModelCandidate, _unique_pairs
from seshat.pdf_sandbox import (
    PdfSandboxError, SandboxQuoteObservation, _check_synthetic_pdf_fixture,
    _SYNTHETIC_CARRIER_ID, MAX_SANDBOX_PDF_BYTES,
)
from seshat.runtime import RuntimeSourceAccess


BridgeStatus = Literal["REJECTED", "BLOCKED", "UNATTESTED_CHILD_OBSERVATIONS"]
BridgeCode = Literal[
    "INVALID_CANDIDATE", "DUPLICATE_EVIDENCE", "SOURCE_MISMATCH",
    "F07_DENIED_OR_DRIFTED", "PDF_INPUT_LIMIT", "SANDBOX_NOT_VERIFIED",
    "SANDBOX_UNAVAILABLE", "ALL_CHILD_OBSERVATIONS_UNATTESTED",
]


class IsolatedBridgePublic(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    schema_id: Literal["seshat.pdf_isolated_bridge.public.v1"] = (
        "seshat.pdf_isolated_bridge.public.v1"
    )
    status: BridgeStatus
    code: BridgeCode
    claim_count: int = Field(ge=0, le=12)
    admitted_quote_count: Literal[0] = 0
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    source_rights_independently_attested: Literal["NO"] = "NO"
    model_identity_independently_attested: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"


class IsolatedBridgeReceipt(BaseModel):
    """OWNER-PRIVATE fingerprint-bearing diagnostic, not trust authority."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    status: BridgeStatus
    code: BridgeCode
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str | None = None
    source_version: str | None = None
    pdf_sha256: str | None = None
    method_id: str | None = None
    claim_count: int = Field(ge=0, le=12)
    observations: tuple[SandboxQuoteObservation, ...] = ()
    source_provenance: Literal["SELF_OBSERVED_UNATTESTED"] = (
        "SELF_OBSERVED_UNATTESTED"
    )
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"

    def public_view(self) -> IsolatedBridgePublic:
        return IsolatedBridgePublic(
            status=self.status, code=self.code, claim_count=self.claim_count
        )


def verify_synthetic_claims_in_sandbox(
    *, access: RuntimeSourceAccess, carrier_id: str,
    response_json: bytes, image: str, timeout_seconds: float = 15,
) -> IsolatedBridgeReceipt:
    """Evaluate exact response bytes against child-reported PDF excerpts.

    One complete F07 precheck occurs before any Docker execution; the sandbox
    rechecks F07 on each citation, and every child observation must match the
    initial pinned version/byte digest. Only invented fixture carriers allowed.
    A forbidden or stale source never launches Docker. No model is called here.
    """
    if type(response_json) is not bytes:
        raise TypeError("response_json must be original bytes")
    digest = hashlib.sha256(response_json).hexdigest()
    candidate: ModelCandidate | None = None

    def result(
        status: BridgeStatus, code: BridgeCode,
        observations: tuple[SandboxQuoteObservation, ...] = (),
    ) -> IsolatedBridgeReceipt:
        return IsolatedBridgeReceipt(
            status=status, code=code, response_sha256=digest,
            source_id=candidate.source_id if candidate else None,
            source_version=candidate.source_version if candidate else None,
            method_id=candidate.method_id if candidate else None,
            claim_count=len(candidate.evidence) if candidate else 0,
            observations=observations,
        )

    if len(response_json) > MAX_RESPONSE_BYTES:
        return result("REJECTED", "INVALID_CANDIDATE")
    try:
        decoded = json.loads(
            response_json.decode("utf-8"), object_pairs_hook=_unique_pairs
        )
        candidate = ModelCandidate.model_validate(decoded)
        if (
            any(not s.strip() for s in candidate.unknowns)
            or any(not c.claim.strip() or not c.excerpt.strip()
                   for c in candidate.evidence)
        ):
            return result("REJECTED", "INVALID_CANDIDATE")
    except (ValueError, UnicodeError, ValidationError, TypeError):
        return result("REJECTED", "INVALID_CANDIDATE")

    pairs = [(c.page, c.excerpt) for c in candidate.evidence]
    if len(set(pairs)) != len(pairs):
        return result("REJECTED", "DUPLICATE_EVIDENCE")

    if (
        carrier_id != _SYNTHETIC_CARRIER_ID
        or candidate.source_id != carrier_id
        or type(access) is not RuntimeSourceAccess
        or access.policy is not RawAccessPolicy.FULL_REQUIRED
    ):
        return result("BLOCKED", "SOURCE_MISMATCH")

    try:
        pdf, declared, actual, version, receipt = (
            access.read_full_with_metadata(carrier_id)
        )
        pdf_hash = hashlib.sha256(pdf).hexdigest()
        if (
            declared != "application/pdf"
            or actual != "application/pdf"
            or candidate.source_version != version
            or receipt.status is not SourceAccessStatus.VERIFIED
            or receipt.read_kind != "FULL"
            or receipt.carrier_id != carrier_id
            or receipt.source_version != version
            or receipt.content_sha256 != pdf_hash
            or receipt.byte_length != len(pdf)
            or not pdf.startswith(b"%PDF-")
        ):
            return result("BLOCKED", "F07_DENIED_OR_DRIFTED")
    except Exception:  # noqa: BLE001 - no private provider output
        return result("BLOCKED", "F07_DENIED_OR_DRIFTED")
    if len(pdf) > MAX_SANDBOX_PDF_BYTES:
        return result("BLOCKED", "PDF_INPUT_LIMIT")

    observations: list[SandboxQuoteObservation] = []
    for quote in candidate.evidence:
        try:
            obs = _check_synthetic_pdf_fixture(
                access, carrier_id, page_number=quote.page,
                expected_excerpt=quote.excerpt, image=image,
                timeout_seconds=timeout_seconds,
            )
        except PdfSandboxError as exc:
            return result(
                "REJECTED" if exc.code == "NOT_VERIFIED" else "BLOCKED",
                "SANDBOX_NOT_VERIFIED"
                if exc.code == "NOT_VERIFIED" else "SANDBOX_UNAVAILABLE",
            )
        if (
            obs.status != "CHILD_REPORTED_MATCH_UNATTESTED"
            or obs.carrier_id != carrier_id
            or obs.source_version != version
            or obs.pdf_sha256 != pdf_hash
            or obs.pdf_byte_length != len(pdf)
            or obs.page_number != quote.page
            or obs.excerpt_sha256 != hashlib.sha256(
                quote.excerpt.encode("utf-8")
            ).hexdigest()
        ):
            return result("BLOCKED", "F07_DENIED_OR_DRIFTED")
        observations.append(obs)

    return result(
        "UNATTESTED_CHILD_OBSERVATIONS",
        "ALL_CHILD_OBSERVATIONS_UNATTESTED",
        tuple(observations),
    )
