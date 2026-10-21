"""Owner-private, synthetic-only atomic gate for model PDF quote candidates.

Exact extracted page text is necessary evidence, never semantic or rights
authority. The caller must retain both the input JSON and returned receipt
in private storage. ``ModelQuoteGateReceipt`` is OWNER-PRIVATE and UNFILTERED:
it carries carrier IDs and content hashes that are guessable fingerprints of
the underlying source. Never export it to an audience that cannot already
access that source; use ``ModelQuoteGateReceipt.redacted_view()`` instead.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from seshat.contracts import SourceAccessStatus
from seshat.pdf_page_evidence import (
    PageExcerptQuery,
    PdfPageEvidenceError,
    _check_pdf_page_excerpts_from_bytes,
    _full_receipt_sha256,
)
from seshat.runtime import EvidenceAccessError, RuntimeSourceAccess

MAX_RESPONSE_BYTES = 32_768

# Closed output vocabulary: a public summary must never carry caller text.
QuoteGateOutcomeCode = Literal[
    "RESPONSE_TOO_LARGE", "CANDIDATE_SCHEMA_INVALID",
    "CANDIDATE_DUPLICATE_EVIDENCE", "SOURCE_ID_MISMATCH",
    "SOURCE_ACCESS_INVALID", "SOURCE_ACCESS_DENIED",
    "PDF_MEDIA_TYPE_REQUIRED", "SOURCE_VERSION_OR_RECEIPT_MISMATCH",
    "CLAIM_EVIDENCE_FAILED", "ALL_EXCERPTS_EXACT",
]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    def model_dump(self, **kwargs: object) -> dict:
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: object) -> str:
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(**kwargs)


class QuoteCandidate(_Strict):
    claim: str = Field(min_length=1, max_length=2_000)
    page: int = Field(ge=1, le=10_000)
    excerpt: str = Field(min_length=1, max_length=2_000)
    kind: Literal["SOURCE_STATED"]


class ModelCandidate(_Strict):
    # Renamed to schema_id (alias "schema") so the Python attribute no longer
    # shadows pydantic.BaseModel's own deprecated schema() method; by_alias
    # dumping above keeps the external JSON key exactly "schema".
    schema_id: Literal["seshat.pdf_claims.v1"] = Field(alias="schema")
    method_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]{1,128}$"
    )
    source_id: str = Field(min_length=1, max_length=256)
    source_version: str = Field(min_length=1, max_length=128)
    run_scope: Literal["SYNTHETIC_QA"]
    evidence: list[QuoteCandidate] = Field(min_length=2, max_length=12)
    unknowns: list[str] = Field(min_length=1, max_length=12)
    rights_independently_attested: Literal["NO"]
    scientific_acceptance: Literal["NOT_ASSERTED"]
    customer_release: Literal["NOT_AUTHORIZED"]


class ClaimDiagnostic(_Strict):
    index: int = Field(ge=0)
    code: str = Field(min_length=1, max_length=80)
    page: int | None = Field(default=None, ge=1, le=10_000)
    page_text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    excerpt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    offset: int | None = Field(default=None, ge=0)


class PublicModelQuoteSummary(_Strict):
    """Safe-for-wide-distribution summary of a ``ModelQuoteGateReceipt``.

    Carries no carrier ID, no PDF/quote hash, no page number, no offset and
    no quoted text: only closed-vocabulary status/code tags, counts, and the
    same fixed never-promote-rights/semantics/acceptance literals already on
    the private receipt. Recipients who cannot read the underlying source
    can safely receive this.
    """

    schema_id: Literal["seshat.pdf_claims.public_summary.v1"] = Field(
        alias="schema", default="seshat.pdf_claims.public_summary.v1"
    )
    status: Literal["REJECTED", "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"]
    code: QuoteGateOutcomeCode
    claim_count: int = Field(ge=0)
    exact_quote_count: int = Field(ge=0)
    # The model-supplied method_id is private, even though it is not a source
    # ID: an adversarial label could itself encode a restricted source title.
    run_scope: Literal["SYNTHETIC_QA"] | None = None
    source_provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    real_model_identity: Literal["NOT_INDEPENDENTLY_ATTESTED"] = (
        "NOT_INDEPENDENTLY_ATTESTED"
    )
    rights_independently_attested: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"

    @model_validator(mode="after")
    def enforce_public_status_consistency(self) -> "PublicModelQuoteSummary":
        if self.exact_quote_count > self.claim_count:
            raise ValueError("PUBLIC_SUMMARY_INVALID_COUNTS")
        if self.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED":
            if (
                self.code != "ALL_EXCERPTS_EXACT"
                or self.claim_count < 2
                or self.exact_quote_count != self.claim_count
                or self.run_scope != "SYNTHETIC_QA"
            ):
                raise ValueError("PUBLIC_SUMMARY_INVALID_POSITIVE_STATUS")
        elif self.code == "ALL_EXCERPTS_EXACT":
            raise ValueError("PUBLIC_SUMMARY_REJECTED_WITH_SUCCESS_CODE")
        return self


class ModelQuoteGateReceipt(_Strict):
    """OWNER-PRIVATE, UNFILTERED fingerprint-bearing receipt.

    Never publish or treat as attestation, and never forward this object
    (or its default ``model_dump``/``model_dump_json``) to an audience that
    cannot already access the underlying source -- use ``redacted_view()``
    for that. This is an ordinary Pydantic model: constructing one directly
    with fabricated field values (including a fabricated ``EXACT_QUOTE``
    diagnostic and dummy-but-well-formed hashes) produces a structurally
    valid instance. That is not cryptographic attestation of anything; the
    only trustworthy way to obtain a receipt is ``verify_pdf_model_claims``.
    """

    schema_id: Literal["seshat.pdf_claims.receipt.v1"] = Field(
        alias="schema", default="seshat.pdf_claims.receipt.v1"
    )
    status: Literal["REJECTED", "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"]
    code: QuoteGateOutcomeCode
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_id: str | None = Field(
        default=None, min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9._:-]{1,128}$"
    )
    run_scope: Literal["SYNTHETIC_QA"] | None = None
    source_id: str | None = Field(default=None, min_length=1)
    source_version: str | None = Field(default=None, min_length=1)
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_access_full_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    claims: tuple[ClaimDiagnostic, ...] = ()
    source_provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    semantic_entailment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    real_model_identity: Literal["NOT_INDEPENDENTLY_ATTESTED"] = (
        "NOT_INDEPENDENTLY_ATTESTED"
    )
    rights_independently_attested: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"

    @model_validator(mode="after")
    def enforce_positive_result_has_full_quote_proof(self) -> "ModelQuoteGateReceipt":
        # These flags are still SELF_OBSERVED/UNATTESTED. This only prevents
        # accidental serialization of a structurally impossible green receipt.
        if self.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED":
            if (
                self.code != "ALL_EXCERPTS_EXACT"
                or not self.source_id
                or not self.source_version
                or not self.pdf_sha256
                or not self.source_access_full_receipt_sha256
                or not self.method_id
                or self.run_scope != "SYNTHETIC_QA"
                or len(self.claims) < 2
                or any(item.code != "EXACT_QUOTE" for item in self.claims)
            ):
                raise ValueError("POSITIVE_RECEIPT_REQUIRES_FULL_PROOF")
        return self

    def redacted_view(self) -> PublicModelQuoteSummary:
        """Safe high-level state only; see ``PublicModelQuoteSummary``."""

        return PublicModelQuoteSummary(
            status=self.status,
            code=self.code,
            claim_count=len(self.claims),
            # On rejection, suppress the number of partial private-source hits.
            exact_quote_count=(
                sum(1 for item in self.claims if item.code == "EXACT_QUOTE")
                if self.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED" else 0
            ),
            run_scope=self.run_scope,
        )


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def verify_pdf_model_claims(
    *, access: RuntimeSourceAccess, carrier_id: str, response_json: bytes
) -> ModelQuoteGateReceipt:
    """Check every model quote against F07-admitted bytes; never partially accept.

    ``response_json`` must be the exact serialized model response bytes. Passing a
    reconstructed mapping would lose the byte-level provenance of the response.
    Rejections contain codes only; no original claim, excerpt or PDF text.

    The underlying PDF is read via exactly one admitted F07 FULL read and
    parsed exactly once, regardless of how many quote candidates are present
    (see ``seshat.pdf_page_evidence._check_pdf_page_excerpts_from_bytes``).
    """

    if type(response_json) is not bytes:
        raise TypeError("response_json must be exact bytes")
    response_digest = hashlib.sha256(response_json).hexdigest()

    tags: dict[str, object] = {"method_id": None, "run_scope": None}

    def rejected(code: QuoteGateOutcomeCode, **kwargs: object) -> ModelQuoteGateReceipt:
        return ModelQuoteGateReceipt(
            status="REJECTED",
            code=code,
            response_sha256=response_digest,
            method_id=tags["method_id"],
            run_scope=tags["run_scope"],
            **kwargs,
        )

    if len(response_json) > MAX_RESPONSE_BYTES:
        return rejected("RESPONSE_TOO_LARGE")
    try:
        raw = json.loads(response_json.decode("utf-8"), object_pairs_hook=_unique_pairs)
        candidate = ModelCandidate.model_validate(raw)
        tags["method_id"] = candidate.method_id
        tags["run_scope"] = candidate.run_scope
        if any(not item.strip() or len(item) > 2_000 for item in candidate.unknowns):
            return rejected("CANDIDATE_SCHEMA_INVALID")
        if any(not item.claim.strip() or not item.excerpt.strip() for item in candidate.evidence):
            return rejected("CANDIDATE_SCHEMA_INVALID")
    except (UnicodeError, ValueError, ValidationError, TypeError):
        return rejected("CANDIDATE_SCHEMA_INVALID")

    evidence_pairs = [(item.page, item.excerpt) for item in candidate.evidence]
    if len(evidence_pairs) != len(set(evidence_pairs)):
        return rejected("CANDIDATE_DUPLICATE_EVIDENCE")

    if candidate.source_id != carrier_id:
        return rejected("SOURCE_ID_MISMATCH")
    if type(access) is not RuntimeSourceAccess:
        return rejected("SOURCE_ACCESS_INVALID")
    try:
        pdf_bytes, declared_media, actual_media, version, source_receipt = (
            access.read_full_with_metadata(carrier_id)
        )
    except EvidenceAccessError:
        return rejected("SOURCE_ACCESS_DENIED")
    if declared_media != "application/pdf" or actual_media != "application/pdf":
        return rejected("PDF_MEDIA_TYPE_REQUIRED")
    pdf_digest = hashlib.sha256(pdf_bytes).hexdigest()
    if (
        candidate.source_version != version
        or source_receipt.status is not SourceAccessStatus.VERIFIED
        or source_receipt.read_kind != "FULL"
        or source_receipt.carrier_id != carrier_id
        or source_receipt.source_version != version
        or source_receipt.content_sha256 != pdf_digest
        or source_receipt.byte_length != len(pdf_bytes)
    ):
        return rejected("SOURCE_VERSION_OR_RECEIPT_MISMATCH")
    source_receipt_digest = _full_receipt_sha256(source_receipt)

    queries = [
        PageExcerptQuery(page_number=item.page, expected_excerpt=item.excerpt)
        for item in candidate.evidence
    ]
    pins = dict(
        source_id=carrier_id, source_version=version, pdf_sha256=pdf_digest,
        source_access_full_receipt_sha256=source_receipt_digest,
    )
    try:
        proofs = _check_pdf_page_excerpts_from_bytes(
            pdf_bytes=pdf_bytes,
            carrier_id=carrier_id,
            source_version=version,
            source_receipt=source_receipt,
            queries=queries,
        )
    except PdfPageEvidenceError as exc:
        # A document-level failure (malformed/encrypted/oversized/unavailable
        # extractor) applies identically to every claim: none of them could
        # have been checked regardless of index.
        diagnostics = tuple(
            ClaimDiagnostic(index=index, code=exc.code) for index in range(len(candidate.evidence))
        )
        return rejected("CLAIM_EVIDENCE_FAILED", claims=diagnostics, **pins)

    diagnostics_list: list[ClaimDiagnostic] = []
    for index, result in enumerate(proofs):
        if isinstance(result, PdfPageEvidenceError):
            diagnostics_list.append(ClaimDiagnostic(index=index, code=result.code))
            continue
        proof = result
        # Defensive INTERNAL invariant only: the private batch helper is
        # passed exactly one immutable F07 snapshot, not a second provider
        # read. It cannot independently detect source drift or TOCTOU.
        if (
            proof.source_version != version
            or proof.pdf_sha256 != pdf_digest
            or proof.carrier_id != carrier_id
            or proof.source_access_full_receipt_sha256 != source_receipt_digest
        ):
            diagnostics_list.append(
                ClaimDiagnostic(index=index, code="INTERNAL_PROOF_MISMATCH")
            )
            continue
        diagnostics_list.append(
            ClaimDiagnostic(
                index=index, code="EXACT_QUOTE", page=proof.page_number,
                page_text_sha256=proof.page_text_sha256,
                excerpt_sha256=proof.excerpt_sha256, offset=proof.offset,
            )
        )

    if any(item.code != "EXACT_QUOTE" for item in diagnostics_list):
        return rejected("CLAIM_EVIDENCE_FAILED", claims=tuple(diagnostics_list), **pins)
    return ModelQuoteGateReceipt(
        status="EXACT_PDF_PAGE_EXCERPTS_VERIFIED", code="ALL_EXCERPTS_EXACT",
        response_sha256=response_digest, method_id=candidate.method_id,
        run_scope=candidate.run_scope, claims=tuple(diagnostics_list), **pins,
    )
