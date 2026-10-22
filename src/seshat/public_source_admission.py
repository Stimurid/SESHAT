"""Operator-controlled multi-source public-PDF F07/F08 scientific intake.

This is a bounded local adapter for *published* articles, not an issuer of
independent rights certificates. It admits neither raw interview datasets
nor arbitrary untrusted PDF files. The operator must pin publisher DOI,
source bytes, allowed scope and license decision before calling this API.
For adversarial PDFs the production Docker sandbox remains mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Literal, Mapping
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import (
    RawAccessPolicy, SourceAccessStatus, SourceCarrier, SourceContent,
)
from seshat.pdf_page_evidence import (
    PageExcerptQuery, PdfPageEvidenceError, PdfPageEvidenceReceipt,
    _bounded_page_count, _check_pdf_page_excerpts_from_bytes,
    _extract_bounded_page_text, _full_receipt_sha256, _open_pdf_reader,
)
from seshat.runtime import RuntimeSourceAccess


MAX_PUBLIC_SOURCE_BYTES = 6 * 1024 * 1024
_CC_BY_NORMALIZED = "creativecommonsattributionlicense"


class PublicSourceAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class PublicArticlePin:
    carrier_id: str
    doi: str
    publisher_article_url: str
    version: str
    sha256: str
    byte_length: int
    operator_license_review_id: str
    attribution: str
    view: str = "PUBLISHED_ARTICLE_ONLY"


@dataclass(frozen=True)
class PublicArticleRequest:
    pin: PublicArticlePin
    # Exact quotes from the pypdf extracted page text, never free paraphrases.
    evidence: tuple[PageExcerptQuery, ...]


class AdmittedPublicArticle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    carrier_id: str
    version: str
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_byte_length: int = Field(gt=0)
    doi: str
    publisher_article_url: str
    operator_license_review_id: str
    attribution: str
    page_count: int = Field(gt=0)
    f07_full_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    f08_page_evidence: tuple[PdfPageEvidenceReceipt, ...]
    license_witness_page: int = 1
    license_witness: str = "CREATIVE_COMMONS_ATTRIBUTION_LICENSE_ON_PUBLISHED_PAGE"
    rights_scope: Literal["PUBLISHED_ARTICLE_ONLY"] = "PUBLISHED_ARTICLE_ONLY"
    rights_independently_attested: Literal["NO"] = "NO"
    provenance: str = "OPERATOR_PINNED_PUBLICATION_AND_LICENSE_WITNESS"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["BLOCKED"] = "BLOCKED"


class PublicCorpusIntake(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "SESHAT_PUBLIC_CORPUS_F07_F08_v1"
    articles: tuple[AdmittedPublicArticle, ...]
    all_requested_page_excerpts_verified: bool = True
    public_rights_review: str = "OPERATOR_REVIEWED_ONLY"
    independent_owner_or_issuer_rights_attestation: Literal["NO"] = "NO"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["BLOCKED"] = "BLOCKED"


class _PinnedProvider:
    def __init__(self, contents: Mapping[str, SourceContent]) -> None:
        self._contents = contents

    def open_content(self, carrier_id: str) -> SourceContent:
        return self._contents[carrier_id]


def _compact(value: str) -> str:
    return "".join(c.lower() for c in value if c.isascii() and c.isalnum())


def _validate_pin(pin: PublicArticlePin, raw: bytes) -> None:
    if (not pin.carrier_id or len(pin.carrier_id) > 160
        or re.fullmatch(r"[A-Za-z0-9_.:-]+", pin.carrier_id) is None):
        raise PublicSourceAdmissionError("PUBLIC_SOURCE_ID_INVALID")
    if not re.fullmatch(r"10\.1371/journal\.pone\.[0-9]{7,8}", pin.doi):
        raise PublicSourceAdmissionError("PUBLIC_PUBLISHER_DOI_NOT_SUPPORTED")
    uri = urlparse(pin.publisher_article_url)
    if (uri.scheme != "https" or uri.hostname != "journals.plos.org"
        or uri.username is not None or uri.password is not None
        or uri.path != "/plosone/article" or uri.fragment
        or uri.port not in (None, 443)
        or parse_qs(uri.query, strict_parsing=True) != {"id": [pin.doi]}):
        raise PublicSourceAdmissionError("PUBLIC_PUBLISHER_ORIGIN_NOT_VERIFIED")
    if (not re.fullmatch(r"[0-9a-f]{64}", pin.sha256)
        or not pin.version or not pin.operator_license_review_id.strip()
        or not pin.attribution.strip()
        or pin.view != "PUBLISHED_ARTICLE_ONLY"):
        raise PublicSourceAdmissionError("PUBLIC_SOURCE_OPERATOR_POLICY_MISSING")
    if (not raw or len(raw) > MAX_PUBLIC_SOURCE_BYTES or len(raw) != pin.byte_length
        or hashlib.sha256(raw).hexdigest() != pin.sha256):
        raise PublicSourceAdmissionError("PUBLIC_SOURCE_BYTES_DRIFT")


def admit_public_published_corpus(
    requests: tuple[PublicArticleRequest, ...],
    *,
    source_bytes: Mapping[str, bytes],
) -> PublicCorpusIntake:
    """All-or-nothing offline F07/F08 intake of TWO OR MORE pinned public works.

    Caller carries operator grant and local bytes; receipt proves byte and page
    integrity within that caller's environment. It is NOT an externally signed
    publication license or source-rights attestation. Original interview
    data cannot be admitted through PUBLISHED_ARTICLE_ONLY.
    """
    if len(requests) < 2 or len(requests) > 12:
        raise PublicSourceAdmissionError("PUBLIC_CORPUS_REQUIRES_DISTINCT_WORKS")
    ids = [req.pin.carrier_id for req in requests]
    dois = [req.pin.doi for req in requests]
    digests = [req.pin.sha256 for req in requests]
    if len(set(ids)) != len(ids) or len(set(dois)) != len(dois) or len(set(digests)) != len(digests):
        raise PublicSourceAdmissionError("PUBLIC_CORPUS_DUPLICATE_WORK")
    if set(source_bytes) != set(ids):
        raise PublicSourceAdmissionError("PUBLIC_CORPUS_SOURCE_SET_MISMATCH")

    carriers: list[SourceCarrier] = []
    contents: dict[str, SourceContent] = {}
    for req in requests:
        pin = req.pin
        raw = source_bytes[pin.carrier_id]
        _validate_pin(pin, raw)
        if not req.evidence or len(req.evidence) > 64:
            raise PublicSourceAdmissionError("PUBLIC_SOURCE_EVIDENCE_REQUIRED")
        carriers.append(SourceCarrier(
            carrier_id=pin.carrier_id, source_identity=pin.publisher_article_url,
            version=pin.version, media_type="application/pdf",
            content_sha256=pin.sha256, byte_length=pin.byte_length,
        ))
        contents[pin.carrier_id] = SourceContent(
            carrier_id=pin.carrier_id, source_version=pin.version,
            media_type="application/pdf", content=raw,
            content_sha256=pin.sha256, byte_length=pin.byte_length,
            complete=True, authorized=True,
        )
    access = RuntimeSourceAccess(
        RawAccessPolicy.FULL_REQUIRED, carriers, _PinnedProvider(contents), ids,
    )
    access.verify_all(ids)
    results: list[AdmittedPublicArticle] = []
    for req in requests:
        pin = req.pin
        raw, declared_media, actual_media, version, read = access.read_full_with_metadata(pin.carrier_id)
        if (declared_media != "application/pdf" or actual_media != "application/pdf"
            or version != pin.version or read.status is not SourceAccessStatus.VERIFIED
            or read.read_kind != "FULL" or read.content_sha256 != pin.sha256):
            raise PublicSourceAdmissionError("PUBLIC_F07_RECEIPT_INCONSISTENT")

        # Re-check the publisher's explicit license notice in the *actual*
        # admitted PDF first page. A query string or a filename cannot prove it.
        try:
            reader = _open_pdf_reader(raw, len(raw))
            page_count = _bounded_page_count(reader)
            first = _extract_bounded_page_text(reader, 1, page_count)
        except PdfPageEvidenceError as exc:
            raise PublicSourceAdmissionError("PUBLIC_PDF_SOURCE_UNREADABLE") from exc
        if (_CC_BY_NORMALIZED not in _compact(first)
            or _compact(pin.doi) not in _compact(first)):
            raise PublicSourceAdmissionError("PUBLIC_PUBLISHER_LICENSE_WITNESS_ABSENT")

        try:
            verified = _check_pdf_page_excerpts_from_bytes(
                pdf_bytes=raw, carrier_id=pin.carrier_id,
                source_version=pin.version, source_receipt=read,
                queries=req.evidence,
            )
        except PdfPageEvidenceError as exc:
            raise PublicSourceAdmissionError("PUBLIC_PDF_EVIDENCE_UNREADABLE") from exc
        if any(isinstance(value, PdfPageEvidenceError) for value in verified):
            raise PublicSourceAdmissionError("PUBLIC_F08_PAGE_EXCERPT_FAILED")
        receipts = tuple(item for item in verified if isinstance(item, PdfPageEvidenceReceipt))
        if len(receipts) != len(req.evidence):
            raise PublicSourceAdmissionError("PUBLIC_F08_MISSING_PAGE_EVIDENCE")
        if any(r.pdf_sha256 != pin.sha256 or r.source_access_full_receipt_sha256 != _full_receipt_sha256(read)
               or r.source_version != pin.version for r in receipts):
            raise PublicSourceAdmissionError("PUBLIC_F08_DRIFT")
        results.append(AdmittedPublicArticle(
            carrier_id=pin.carrier_id, version=version,
            pdf_sha256=pin.sha256, pdf_byte_length=pin.byte_length,
            doi=pin.doi, publisher_article_url=pin.publisher_article_url,
            operator_license_review_id=pin.operator_license_review_id,
            attribution=pin.attribution, page_count=page_count,
            f07_full_receipt_sha256=_full_receipt_sha256(read),
            f08_page_evidence=receipts,
        ))
    return PublicCorpusIntake(articles=tuple(results))

def replay_and_verify_public_corpus(
    packet: PublicCorpusIntake,
    requests: tuple[PublicArticleRequest, ...],
    *,
    source_bytes: Mapping[str, bytes],
) -> PublicCorpusIntake:
    """Fresh-process, fail-closed readback of an owner-private F07/F08 batch.

    A serialized packet alone is insufficient evidence. Pydantic model_copy
    does not validate its update fields. Rebuild each F07 original-byte read,
    CC BY license-page witness, and F08 page quote from pinned sources,
    then compare the complete structured result. This is local operator
    consistency, not independently authenticated rights or human approval.
    """
    if type(packet) is not PublicCorpusIntake:
        raise PublicSourceAdmissionError("PUBLIC_REPLAY_TYPED_PACKET_REQUIRED")
    try:
        validated = PublicCorpusIntake.model_validate(packet.model_dump(mode="python"))
    except Exception as exc:
        raise PublicSourceAdmissionError("PUBLIC_REPLAY_PACKET_SCHEMA_INVALID") from exc
    if packet != validated:
        raise PublicSourceAdmissionError("PUBLIC_REPLAY_PACKET_INCONSISTENT")
    original = admit_public_published_corpus(requests, source_bytes=source_bytes)
    if validated != original:
        raise PublicSourceAdmissionError("PUBLIC_REPLAY_RECEIPT_DRIFT")
    return original
