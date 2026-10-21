"""Owner-private, synthetic-only atomic gate for model PDF quote candidates.

Exact extracted page text is necessary evidence, never semantic or rights authority.
The caller must retain both the input JSON and returned receipt in private storage.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from seshat.contracts import SourceAccessStatus
from seshat.pdf_page_evidence import PdfPageEvidenceError, check_pdf_page_excerpt
from seshat.runtime import EvidenceAccessError, RuntimeSourceAccess

MAX_RESPONSE_BYTES = 32_768


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class QuoteCandidate(_Strict):
    claim: str = Field(min_length=1, max_length=2_000)
    page: int = Field(ge=1, le=10_000)
    excerpt: str = Field(min_length=1, max_length=2_000)
    kind: Literal["SOURCE_STATED"]


class ModelCandidate(_Strict):
    schema: Literal["seshat.pdf_claims.v1"]
    method_id: str = Field(min_length=1, max_length=128)
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
    page: int | None = Field(default=None, ge=1)
    page_text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    excerpt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    offset: int | None = Field(default=None, ge=0)


class ModelQuoteGateReceipt(_Strict):
    """Private fingerprint-bearing receipt. Never publish or treat as attestation."""

    schema: Literal["seshat.pdf_claims.receipt.v1"] = "seshat.pdf_claims.receipt.v1"
    status: Literal["REJECTED", "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"]
    code: str = Field(min_length=1, max_length=80)
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str | None = Field(default=None, min_length=1)
    source_version: str | None = Field(default=None, min_length=1)
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_access_full_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    claims: tuple[ClaimDiagnostic, ...] = ()
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
                or len(self.claims) < 2
                or any(item.code != "EXACT_QUOTE" for item in self.claims)
            ):
                raise ValueError("POSITIVE_RECEIPT_REQUIRES_FULL_PROOF")
        return self


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
    """

    if type(response_json) is not bytes:
        raise TypeError("response_json must be exact bytes")
    response_digest = hashlib.sha256(response_json).hexdigest()

    def rejected(code: str, **kwargs: object) -> ModelQuoteGateReceipt:
        return ModelQuoteGateReceipt(
            status="REJECTED", code=code, response_sha256=response_digest, **kwargs
        )

    if len(response_json) > MAX_RESPONSE_BYTES:
        return rejected("RESPONSE_TOO_LARGE")
    try:
        raw = json.loads(response_json.decode("utf-8"), object_pairs_hook=_unique_pairs)
        candidate = ModelCandidate.model_validate(raw)
        if any(not item.strip() or len(item) > 2_000 for item in candidate.unknowns):
            return rejected("CANDIDATE_SCHEMA_INVALID")
        if any(not item.claim.strip() or not item.excerpt.strip() for item in candidate.evidence):
            return rejected("CANDIDATE_SCHEMA_INVALID")
    except (UnicodeError, ValueError, ValidationError, TypeError):
        return rejected("CANDIDATE_SCHEMA_INVALID")

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
    source_receipt_digest = hashlib.sha256(
        json.dumps(
            source_receipt.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    diagnostics: list[ClaimDiagnostic] = []
    for index, item in enumerate(candidate.evidence):
        try:
            proof = check_pdf_page_excerpt(
                access, carrier_id, page_number=item.page, expected_excerpt=item.excerpt
            )
            if (
                proof.source_version != version
                or proof.pdf_sha256 != pdf_digest
                or proof.carrier_id != carrier_id
                or proof.source_access_full_receipt_sha256 != source_receipt_digest
            ):
                diagnostics.append(ClaimDiagnostic(index=index, code="SOURCE_DRIFT"))
                continue
            diagnostics.append(
                ClaimDiagnostic(
                    index=index, code="EXACT_QUOTE", page=proof.page_number,
                    page_text_sha256=proof.page_text_sha256,
                    excerpt_sha256=proof.excerpt_sha256, offset=proof.offset,
                )
            )
        except PdfPageEvidenceError as exc:
            diagnostics.append(ClaimDiagnostic(index=index, code=exc.code))
        except EvidenceAccessError:
            diagnostics.append(ClaimDiagnostic(index=index, code="SOURCE_ACCESS_DENIED"))

    pins = dict(
        source_id=carrier_id, source_version=version, pdf_sha256=pdf_digest,
        source_access_full_receipt_sha256=source_receipt_digest,
        claims=tuple(diagnostics),
    )
    if any(item.code != "EXACT_QUOTE" for item in diagnostics):
        return rejected("CLAIM_EVIDENCE_FAILED", **pins)
    return ModelQuoteGateReceipt(
        status="EXACT_PDF_PAGE_EXCERPTS_VERIFIED", code="ALL_EXCERPTS_EXACT",
        response_sha256=response_digest, **pins,
    )
