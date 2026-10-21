"""Issue #73 seam: the ONE explicit bridge from the claim gate to the sandbox.

``seshat.pdf_claims.verify_pdf_model_claims`` extracts page text **in this
process**.  This module is the source-neutral alternative: the same strict
whole-JSON candidate check and the same single admitted F07 FULL read, but
every quote is checked by the existing ephemeral OS sandbox
(:mod:`seshat.pdf_sandbox`) instead.

Boundaries that this bridge does NOT cross, and must never be read as
crossing:

* The child's answer stays ``CHILD_REPORTED_MATCH_UNATTESTED``.  An unreviewed
  child process can lie.  A positive bridge receipt means "a bounded child,
  given one admitted source, reported a match" — nothing more.
* Full-source rights, method identity, semantic entailment and scientific
  acceptance are all left exactly where they were: unpromoted.
* There is **no host-parser fallback**.  If the sandbox is unavailable or
  fails, the result is a rejection, never a quietly in-process answer.
* Admission is atomic.  Any failing candidate rejects the whole response; a
  2-of-4 failure accepts zero quotes.
* A source-invalid candidate reaches the sandbox zero times.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal

from pydantic import Field

from seshat.pdf_claims import (
    ClaimDiagnostic,
    ModelQuoteGateReceipt,
    _parse_and_admit,
    _Strict,
)
from seshat.pdf_sandbox import (
    PdfSandboxError,
    SandboxQuoteObservation,
    check_pdf_page_excerpt_sandboxed,
)
from seshat.runtime import RuntimeSourceAccess

SandboxGateCode = Literal[
    "RESPONSE_TOO_LARGE", "CANDIDATE_SCHEMA_INVALID",
    "CANDIDATE_DUPLICATE_EVIDENCE", "SOURCE_ID_MISMATCH",
    "SOURCE_ACCESS_INVALID", "SOURCE_ACCESS_DENIED",
    "PDF_MEDIA_TYPE_REQUIRED", "SOURCE_VERSION_OR_RECEIPT_MISMATCH",
    "CLAIM_EVIDENCE_FAILED", "SANDBOX_UNAVAILABLE",
    "ALL_EXCERPTS_CHILD_REPORTED",
]

SandboxQuoteChecker = Callable[..., SandboxQuoteObservation]


class PublicSandboxQuoteSummary(_Strict):
    """Safe-for-wide-distribution projection of a bridge receipt.

    No carrier ID, no hash, no page, no offset, no quoted text.
    """

    schema_id: Literal["seshat.pdf_claims.sandbox_public_summary.v1"] = Field(
        alias="schema", default="seshat.pdf_claims.sandbox_public_summary.v1"
    )
    status: Literal["REJECTED", "CHILD_REPORTED_MATCH_UNATTESTED"]
    code: SandboxGateCode
    claim_count: int = Field(ge=0)
    child_reported_match_count: int = Field(ge=0)
    run_scope: Literal["SYNTHETIC_QA"] | None = None
    extraction_locus: Literal["EPHEMERAL_OS_SANDBOX_CHILD"] = "EPHEMERAL_OS_SANDBOX_CHILD"
    child_observation_provenance: Literal["CHILD_ASSERTED_UNATTESTED"] = (
        "CHILD_ASSERTED_UNATTESTED"
    )
    host_parser_fallback_used: Literal["NEVER"] = "NEVER"
    source_provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    real_model_identity: Literal["NOT_INDEPENDENTLY_ATTESTED"] = (
        "NOT_INDEPENDENTLY_ATTESTED"
    )
    rights_independently_attested: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"


class SandboxedModelQuoteGateReceipt(_Strict):
    """OWNER-PRIVATE bridge receipt. Never publish; use ``redacted_view()``.

    ``status`` can never be stronger than the child's own claim. There is no
    ``VERIFIED`` value in this vocabulary on purpose.
    """

    schema_id: Literal["seshat.pdf_claims.sandbox_receipt.v1"] = Field(
        alias="schema", default="seshat.pdf_claims.sandbox_receipt.v1"
    )
    status: Literal["REJECTED", "CHILD_REPORTED_MATCH_UNATTESTED"]
    code: SandboxGateCode
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]{1,128}$"
    )
    run_scope: Literal["SYNTHETIC_QA"] | None = None
    source_id: str | None = Field(default=None, min_length=1)
    source_version: str | None = Field(default=None, min_length=1)
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_access_full_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    claims: tuple[ClaimDiagnostic, ...] = ()
    sandbox_invocations: int = Field(default=0, ge=0)
    extraction_locus: Literal["EPHEMERAL_OS_SANDBOX_CHILD"] = "EPHEMERAL_OS_SANDBOX_CHILD"
    child_observation_provenance: Literal["CHILD_ASSERTED_UNATTESTED"] = (
        "CHILD_ASSERTED_UNATTESTED"
    )
    host_parser_fallback_used: Literal["NEVER"] = "NEVER"
    source_provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    real_model_identity: Literal["NOT_INDEPENDENTLY_ATTESTED"] = (
        "NOT_INDEPENDENTLY_ATTESTED"
    )
    rights_independently_attested: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"

    def redacted_view(self) -> PublicSandboxQuoteSummary:
        return PublicSandboxQuoteSummary(
            status=self.status,
            code=self.code,
            claim_count=len(self.claims),
            child_reported_match_count=sum(
                1 for item in self.claims if item.code == "CHILD_REPORTED_MATCH_UNATTESTED"
            ),
            run_scope=self.run_scope,
        )


def _from_private(receipt: ModelQuoteGateReceipt, **extra: object) -> SandboxedModelQuoteGateReceipt:
    """Re-shape a shared-admission rejection into the bridge's vocabulary."""

    return SandboxedModelQuoteGateReceipt(
        status="REJECTED",
        code=receipt.code,  # the shared admission codes are a subset
        response_sha256=receipt.response_sha256,
        method_id=receipt.method_id,
        run_scope=receipt.run_scope,
        **extra,
    )


def verify_pdf_model_claims_sandboxed(
    *,
    access: RuntimeSourceAccess,
    carrier_id: str,
    response_json: bytes,
    image: str,
    sandbox_check: SandboxQuoteChecker = check_pdf_page_excerpt_sandboxed,
    timeout_seconds: float = 15,
) -> SandboxedModelQuoteGateReceipt:
    """Check every quote in an ephemeral sandbox child. Never partially accept.

    ``sandbox_check`` is injectable so a synthetic fixture entrypoint can be
    supplied in tests; it is NOT a fallback seam. Whatever is passed here is
    the only extractor, and the host parser is never consulted.
    """

    if type(response_json) is not bytes:
        raise TypeError("response_json must be exact bytes")
    response_digest = hashlib.sha256(response_json).hexdigest()
    tags: dict[str, object] = {"method_id": None, "run_scope": None}

    rejection, admitted = _parse_and_admit(
        access=access, carrier_id=carrier_id, response_json=response_json,
        response_digest=response_digest, tags=tags,
    )
    if rejection is not None:
        # Nothing reached the sandbox: a source-invalid candidate has a
        # sandbox side-effect count of exactly zero.
        return _from_private(rejection, sandbox_invocations=0)
    assert admitted is not None
    candidate = admitted.candidate
    pins = admitted.pins

    diagnostics: list[ClaimDiagnostic] = []
    invocations = 0
    for index, item in enumerate(candidate.evidence):
        try:
            invocations += 1
            observation = sandbox_check(
                access,
                carrier_id,
                page_number=item.page,
                expected_excerpt=item.excerpt,
                image=image,
                timeout_seconds=timeout_seconds,
            )
        except PdfSandboxError as exc:
            # No host-parser fallback: an unavailable sandbox is a rejection.
            diagnostics.append(ClaimDiagnostic(index=index, code=f"SANDBOX_{exc.code}"))
            continue
        if not isinstance(observation, SandboxQuoteObservation):
            diagnostics.append(ClaimDiagnostic(index=index, code="SANDBOX_CONTRACT_INVALID"))
            continue
        if (
            observation.status != "CHILD_REPORTED_MATCH_UNATTESTED"
            or observation.carrier_id != carrier_id
            or observation.source_version != admitted.version
            or observation.pdf_sha256 != admitted.pdf_digest
            or observation.source_access_full_receipt_sha256 != admitted.source_receipt_digest
            or observation.page_number != item.page
            or observation.pdf_byte_length != len(admitted.pdf_bytes)
        ):
            diagnostics.append(ClaimDiagnostic(index=index, code="SANDBOX_PIN_MISMATCH"))
            continue
        diagnostics.append(
            ClaimDiagnostic(
                index=index,
                code="CHILD_REPORTED_MATCH_UNATTESTED",
                page=observation.page_number,
                excerpt_sha256=observation.excerpt_sha256,
            )
        )

    failed = [d for d in diagnostics if d.code != "CHILD_REPORTED_MATCH_UNATTESTED"]
    if failed:
        unavailable = all(d.code.startswith("SANDBOX_") for d in failed) and len(failed) == len(
            diagnostics
        )
        code: SandboxGateCode = "SANDBOX_UNAVAILABLE" if unavailable else "CLAIM_EVIDENCE_FAILED"
        return SandboxedModelQuoteGateReceipt(
            status="REJECTED",
            code=code,
            response_sha256=response_digest,
            method_id=candidate.method_id,
            run_scope=candidate.run_scope,
            claims=tuple(diagnostics),
            sandbox_invocations=invocations,
            **pins,
        )
    return SandboxedModelQuoteGateReceipt(
        status="CHILD_REPORTED_MATCH_UNATTESTED",
        code="ALL_EXCERPTS_CHILD_REPORTED",
        response_sha256=response_digest,
        method_id=candidate.method_id,
        run_scope=candidate.run_scope,
        claims=tuple(diagnostics),
        sandbox_invocations=invocations,
        **pins,
    )


__all__ = [
    "PublicSandboxQuoteSummary",
    "SandboxGateCode",
    "SandboxedModelQuoteGateReceipt",
    "SandboxQuoteChecker",
    "verify_pdf_model_claims_sandboxed",
]
