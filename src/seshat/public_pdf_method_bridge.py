"""F07/F08-admitted public PDF -> strictly derived UTF-8 MethodBody input.

This is an operator-local *source view*. It never calls a model, creates a
MethodBody execution receipt, attests publisher rights independently, or
claims scientific/customer approval. A real executable method remains a
separate owner-authorized operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from seshat.fabric_waves.operator_methodbody import OperatorSourcePin
from seshat.pdf_page_evidence import (
    PdfPageEvidenceError,
    _EXTRACTOR_VERSION,
    _bounded_page_count,
    _extract_bounded_page_text,
    _open_pdf_reader,
)
from seshat.public_source_admission import (
    PublicArticleRequest,
    PublicCorpusIntake,
    PublicSourceAdmissionError,
    replay_and_verify_public_corpus,
)

MAX_METHOD_PDF_PAGES = 64
MAX_METHOD_PAGE_CHARS = 65536
MAX_METHOD_VIEW_BYTES = 512 * 1024


class PublicPdfMethodBridgeError(ValueError):
    pass


@dataclass(frozen=True)
class SourceBackedMethodInput:
    """Private bytes plus a source-neutral, provenance-linked pin."""

    source_pin: OperatorSourcePin
    source_utf8: bytes
    original_source_id: str
    original_source_version: str
    original_pdf_sha256: str
    original_f07_receipt_sha256: str
    original_page_evidence_count: int
    pdf_page_count: int
    page_text_sha256: tuple[str, ...]
    extractor_version: str
    scope: str = "OPERATOR_REVIEWED_PUBLISHED_ARTICLE_ONLY"
    owner_acceptance: str = "NOT_PERFORMED"
    customer_release: str = "BLOCKED"
    model_run: str = "NOT_RUN"


def make_public_pdf_method_views(
    packet: PublicCorpusIntake,
    requests: tuple[PublicArticleRequest, ...],
    *,
    source_bytes: Mapping[str, bytes],
    owner_excluded_source_ids: frozenset[str] | None,
    owner_excluded_source_sha256: frozenset[str] | None,
) -> tuple[SourceBackedMethodInput, ...]:
    """Replay ALL admitted originals and derive page-addressed UTF-8 views.

    Explicit private owner exclusion lists are mandatory. This checks supplied
    lists but does not certify that a caller supplied the complete owner policy.
    All PDFs here are operator-reviewed PLOS originals, not arbitrary hostile
    attachments; hardened isolated parsing remains a separate gate.
    """
    if owner_excluded_source_ids is None or owner_excluded_source_sha256 is None:
        raise PublicPdfMethodBridgeError("METHOD_VIEW_OWNER_POLICY_REQUIRED")
    if any(len(d) != 64 or any(ch not in "0123456789abcdef" for ch in d)
           for d in owner_excluded_source_sha256):
        raise PublicPdfMethodBridgeError("METHOD_VIEW_OWNER_POLICY_INVALID")

    # Revalidates Literal status fields, original PDF bytes, publisher/CC BY,
    # original F07 receipt and *all* F08 page excerpts before deriving text.
    try:
        verified = replay_and_verify_public_corpus(
            packet, requests, source_bytes=source_bytes,
        )
    except PublicSourceAdmissionError as exc:
        raise PublicPdfMethodBridgeError("METHOD_VIEW_SOURCE_ADMISSION_FAILED") from exc

    denied_ids = {str(item).casefold() for item in owner_excluded_source_ids}
    result: list[SourceBackedMethodInput] = []
    for item in verified.articles:
        if (item.carrier_id.casefold() in denied_ids
            or item.doi.casefold() in denied_ids
            or item.pdf_sha256 in owner_excluded_source_sha256):
            raise PublicPdfMethodBridgeError("METHOD_VIEW_SOURCE_EXCLUDED")

        raw = source_bytes[item.carrier_id]
        if hashlib.sha256(raw).hexdigest() != item.pdf_sha256:
            raise PublicPdfMethodBridgeError("METHOD_VIEW_ORIGINAL_BYTES_DRIFT")
        try:
            reader = _open_pdf_reader(raw, len(raw))
            pages = _bounded_page_count(reader)
            if pages != item.page_count or pages > MAX_METHOD_PDF_PAGES:
                raise PublicPdfMethodBridgeError("METHOD_VIEW_PAGE_LIMIT_OR_DRIFT")
            chunks: list[str] = []
            page_digests: list[str] = []
            for number in range(1, pages + 1):
                page = _extract_bounded_page_text(reader, number, pages)
                if len(page) > MAX_METHOD_PAGE_CHARS:
                    raise PublicPdfMethodBridgeError("METHOD_VIEW_PAGE_TEXT_TOO_LARGE")
                data = page.encode("utf-8")
                page_digests.append(hashlib.sha256(data).hexdigest())
                chunks.append(
                    f"=== ORIGINAL PDF PAGE {number} / {pages} "
                    f"SOURCE {item.carrier_id} ===\n{page}\n"
                )
            method_bytes = "\n".join(chunks).encode("utf-8")
        except (PdfPageEvidenceError, UnicodeEncodeError) as exc:
            raise PublicPdfMethodBridgeError("METHOD_VIEW_PDF_TEXT_UNAVAILABLE") from exc
        if not method_bytes or len(method_bytes) > MAX_METHOD_VIEW_BYTES:
            raise PublicPdfMethodBridgeError("METHOD_VIEW_TOTAL_TEXT_LIMIT")
        view_sha = hashlib.sha256(method_bytes).hexdigest()
        # Source_id is deliberately distinct from the original PDF carrier:
        # operator_methodbody works with UTF-8, not PDF binary bytes.
        pin = OperatorSourcePin(
            source_id=f"{item.carrier_id}:page-text:{view_sha[:16]}",
            source_version=f"sha256:{view_sha}",
            sha256=view_sha,
            rights_basis=f"OPERATOR_REVIEWED_CC_BY:{item.operator_license_review_id}",
            authorized_view="owner-private-published-page-text",
        )
        if pin.source_id.casefold() in denied_ids or view_sha in owner_excluded_source_sha256:
            raise PublicPdfMethodBridgeError("METHOD_VIEW_SOURCE_EXCLUDED")
        result.append(SourceBackedMethodInput(
            source_pin=pin,
            source_utf8=method_bytes,
            original_source_id=item.carrier_id,
            original_source_version=item.version,
            original_pdf_sha256=item.pdf_sha256,
            original_f07_receipt_sha256=item.f07_full_receipt_sha256,
            original_page_evidence_count=len(item.f08_page_evidence),
            pdf_page_count=pages,
            page_text_sha256=tuple(page_digests),
            extractor_version=_EXTRACTOR_VERSION,
        ))
    if len(result) != len(requests):
        raise PublicPdfMethodBridgeError("METHOD_VIEW_PARTIAL_CORPUS")
    return tuple(result)
