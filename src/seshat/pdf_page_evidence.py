"""Bounded, read-only PDF page-evidence checker.

Downstream of an already-admitted, version-pinned PDF carrier, this module
verifies that an explicit 1-based page number and an explicit
character-offset excerpt are actually present in that page's extracted
text, and produces a hash-only receipt of the check.

Scope and limits (read before using this module elsewhere):

* Bytes are taken ONLY from ``RuntimeSourceAccess.read_all(carrier_id)``.
  They are never accepted as request-provided bytes or as a caller-supplied
  assertion flag, so a caller cannot fabricate "verified" evidence by
  passing in whatever bytes/claims it likes -- the existing F07 rights
  boundary and integrity checks in ``seshat.runtime`` run first.
* This checks extractor-relative TEXT EVIDENCE only. It does not establish
  physical page/OCR/layout fidelity, does not perform OCR, and does not
  touch the network.
* ``RIGHTS_INDEPENDENTLY_ATTESTED`` stays ``"NO"`` here unconditionally.
  Source rights are granted only by the pre-existing owner-controlled
  SourceContentProvider + F07 selection; this module never promotes a
  locally supplied content flag into an F07 grant.
* ``acceptance`` on the receipt is always ``"PROPOSED"``: a human acceptance
  workflow is a separate, later step (see docs/S_F07_PDF_001_RESULT.md).
* All failure modes are closed: any ambiguity, size/page-count outlier,
  encrypted/malformed/truncated document, unextractable or image-only
  page, excerpt/offset mismatch, or extracted text that cannot be
  represented in UTF-8 raises ``PdfPageEvidenceError`` instead of
  guessing or returning a best-effort match.
* ``_check_pdf_page_excerpts_from_bytes`` is a PRIVATE low-level parsing
  helper, not a source-admission operation or security authority. Its caller
  must first perform an F07 FULL read and validate carrier identity, version,
  declared/loaded MIME and receipt hash. Only the public
  ``check_pdf_page_excerpt`` and the separately gated
  ``verify_pdf_model_claims`` are intended as entrypoints. The private
  helper parses once and calls ``extract_text()`` per distinct page.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import SourceAccessReceipt, SourceAccessStatus
from seshat.runtime import RuntimeSourceAccess

try:
    import pypdf
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - dependency declared in pyproject.toml
    raise ImportError(
        "seshat.pdf_page_evidence requires the 'pypdf' dependency to be installed"
    ) from exc

_EXTRACTOR_VERSION: str = getattr(pypdf, "__version__", "")
if not _EXTRACTOR_VERSION:
    raise ImportError("PDF extractor version unavailable: cannot create reproducible evidence")

_EXTRACTOR_NAME: Final[str] = "pypdf"

#: Bounded limits. These exist only to fail closed on pathological inputs;
#: they are not a claim about what a legitimate document may look like.
MAX_PDF_BYTES: Final[int] = 50 * 1024 * 1024
MAX_PAGE_COUNT: Final[int] = 10_000
MAX_PAGE_TEXT_CHARS: Final[int] = 1_000_000


class PdfPageEvidenceError(ValueError):
    """A PDF page-evidence check failed closed. ``code`` is a stable tag."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class PdfPageEvidenceReceipt(BaseModel):
    """OWNER-PRIVATE and source-access-scoped, not customer/public-safe.

    Hashes of short excerpts are guessable fingerprints, as are source SHA
    and carrier IDs. Nothing here independently grants source rights.
    Never export this model unfiltered to users who cannot access the
    corresponding source; create a separate authorized redacted view.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    carrier_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_access_policy: Literal["FULL_REQUIRED"] = "FULL_REQUIRED"
    source_access_full_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_byte_length: int = Field(ge=1)
    page_number: int = Field(ge=1)
    page_count: int = Field(ge=1)
    page_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset: int = Field(ge=0)
    length: int = Field(ge=1)
    extractor_name: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    rights_independently_attested: Literal["NO"] = "NO"
    human_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    acceptance: Literal["PROPOSED"] = "PROPOSED"


@dataclass(frozen=True)
class PageExcerptQuery:
    """One (page, excerpt) check to run against an already-opened PDF.

    Fields are intentionally typed as ``object`` for ``page_number``,
    ``offset`` and ``length``: ``_check_pdf_page_excerpts_from_bytes`` applies
    the same strict-type validation ``check_pdf_page_excerpt`` applies to its
    keyword arguments, per query, so a caller cannot smuggle a bool/float/str
    past the positive-integer gate just because it built a dataclass by hand.
    """

    page_number: object
    expected_excerpt: object
    offset: object = None
    length: object = None


def _validate_query_inputs(
    page_number: object, expected_excerpt: object, offset: object, length: object
) -> int:
    """Shared strict-type gate for one (page, excerpt) query. Returns effective_length."""

    if type(page_number) is not int or page_number < 1:
        raise PdfPageEvidenceError(
            "PAGE_NUMBER_INVALID", "page_number requires a positive integer"
        )
    if not isinstance(expected_excerpt, str) or not expected_excerpt.strip():
        raise PdfPageEvidenceError("EXCERPT_EMPTY", "expected_excerpt must be non-empty")
    if offset is not None and (type(offset) is not int or offset < 0):
        raise PdfPageEvidenceError("OFFSET_INVALID", "offset must be a non-negative integer")
    if length is not None and (type(length) is not int or length <= 0):
        raise PdfPageEvidenceError("LENGTH_INVALID", "length must be a positive integer")
    return length if length is not None else len(expected_excerpt)


def _open_pdf_reader(pdf_bytes: bytes, pdf_byte_length: int) -> PdfReader:
    """Shared document-level open: header/size, parse, encryption state."""

    if pdf_byte_length == 0 or not pdf_bytes.startswith(b"%PDF-"):
        raise PdfPageEvidenceError("MALFORMED_DOCUMENT", "missing PDF header signature")
    if pdf_byte_length > MAX_PDF_BYTES:
        raise PdfPageEvidenceError(
            "PATHOLOGICAL_SIZE", f"PDF exceeds bounded size limit of {MAX_PDF_BYTES} bytes"
        )
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    except Exception:  # noqa: BLE001 - any parse failure fails closed
        raise PdfPageEvidenceError("MALFORMED_DOCUMENT", "PDF parser rejected input") from None
    try:
        is_encrypted = bool(reader.is_encrypted)
    except Exception:  # noqa: BLE001
        raise PdfPageEvidenceError("MALFORMED_DOCUMENT", "PDF encryption state invalid") from None
    if is_encrypted:
        raise PdfPageEvidenceError("ENCRYPTED_DOCUMENT", "encrypted PDFs are rejected")
    return reader


def _bounded_page_count(reader: PdfReader) -> int:
    """Shared document-level page count + pathological-size bound."""

    try:
        page_count = len(reader.pages)
    except Exception:  # noqa: BLE001
        raise PdfPageEvidenceError("MALFORMED_DOCUMENT", "PDF page tree is invalid") from None
    if page_count > MAX_PAGE_COUNT:
        raise PdfPageEvidenceError(
            "PATHOLOGICAL_SIZE", f"page count exceeds bounded limit of {MAX_PAGE_COUNT}"
        )
    return page_count


def _extract_bounded_page_text(reader: PdfReader, page_number: int, page_count: int) -> str:
    """Shared single-page extraction: range, extraction failure, size, image-only."""

    if page_count == 0 or page_number > page_count:
        raise PdfPageEvidenceError(
            "PAGE_OUT_OF_RANGE", f"page {page_number} exceeds page_count {page_count}"
        )
    try:
        page = reader.pages[page_number - 1]
        page_text = page.extract_text() or ""
    except Exception:  # noqa: BLE001
        raise PdfPageEvidenceError(
            "UNEXTRACTABLE_PAGE", "PDF page text extraction failed"
        ) from None
    if len(page_text) > MAX_PAGE_TEXT_CHARS:
        raise PdfPageEvidenceError(
            "PATHOLOGICAL_SIZE", "extracted page text exceeds the configured limit"
        )
    if not page_text.strip():
        raise PdfPageEvidenceError(
            "IMAGE_ONLY_PAGE",
            "page produced no extractable text (image-only or unextractable)",
        )
    return page_text


def _resolve_excerpt_window(
    page_text: str, expected_excerpt: str, offset: int | None, effective_length: int
) -> tuple[int, str]:
    """Shared single-page window resolution: ambiguous overlap, offset, mismatch."""

    if offset is None:
        first = page_text.find(expected_excerpt)
        if first < 0:
            raise PdfPageEvidenceError(
                "EXCERPT_NOT_FOUND", "expected_excerpt does not occur on this page"
            )
        # Search starting at first+1 to count *overlapping* occurrences too.
        if page_text.find(expected_excerpt, first + 1) >= 0:
            raise PdfPageEvidenceError(
                "EXCERPT_AMBIGUOUS",
                "expected_excerpt occurs more than once; an explicit offset is required",
            )
        resolved_offset = first
    else:
        resolved_offset = offset

    window_end = resolved_offset + effective_length
    if resolved_offset < 0 or window_end > len(page_text):
        raise PdfPageEvidenceError(
            "OFFSET_OUT_OF_RANGE", "offset/length exceed extracted page text length"
        )

    actual_window = page_text[resolved_offset:window_end]
    if actual_window != expected_excerpt:
        raise PdfPageEvidenceError(
            "EXCERPT_MISMATCH", "excerpt does not match text at the explicit offset"
        )
    return resolved_offset, actual_window


def _safe_text_sha256(text: str, *, code: str = "PAGE_TEXT_UNICODE_INVALID") -> str:
    """Hash extracted text, failing closed instead of raising a raw UnicodeEncodeError.

    A malformed PDF's embedded font/cmap can make ``extract_text()`` return a
    str containing an unpaired surrogate codepoint. Such a str is otherwise
    ordinary Python text (comparisons, slicing and ``.find`` all still work),
    but ``str.encode("utf-8")`` raises ``UnicodeEncodeError`` on it. Without
    this guard that raw exception would propagate out of this module as an
    untyped crash instead of the typed, redacted rejection every other
    failure mode here produces.
    """

    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PdfPageEvidenceError(
            code,
            "extracted text contains a value that cannot be represented in UTF-8 "
            "(for example an unpaired surrogate codepoint)",
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _full_receipt_sha256(receipt: SourceAccessReceipt) -> str:
    """Stable checksum of one F07-local FULL read receipt, not a signature."""
    return hashlib.sha256(
        json.dumps(
            receipt.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def check_pdf_page_excerpt(
    source_access: RuntimeSourceAccess,
    carrier_id: str,
    *,
    page_number: int,
    expected_excerpt: str,
    offset: int | None = None,
    length: int | None = None,
) -> PdfPageEvidenceReceipt:
    """Verify ``expected_excerpt`` is present on ``page_number`` of the PDF carrier.

    ``offset``/``length`` pin the exact character window in the page's
    extracted text. When both are omitted, the excerpt must occur exactly
    once in the page text; zero or multiple occurrences fail closed rather
    than guessing.

    Raises ``PdfPageEvidenceError`` for every rejection case; raises
    ``EvidenceAccessError`` (from ``seshat.runtime``) unchanged if the
    source-access policy/integrity checks deny the underlying read.
    """

    if not _EXTRACTOR_VERSION:
        raise PdfPageEvidenceError(
            "EXTRACTOR_VERSION_UNAVAILABLE",
            "PDF extractor version must be known to create reproducible evidence",
        )
    effective_length = _validate_query_inputs(page_number, expected_excerpt, offset, length)

    # The same authorized FULL read supplies both raw bytes and source
    # metadata. Do not infer media type from a leading "%PDF-" signature:
    # only a declared and validated PDF carrier can yield PDF page evidence.
    pdf_bytes, declared_media, actual_media, version, source_receipt = (
        source_access.read_full_with_metadata(carrier_id)
    )
    if declared_media != "application/pdf" or actual_media != "application/pdf":
        raise PdfPageEvidenceError(
            "PDF_MEDIA_TYPE_REQUIRED", "carrier was not admitted as application/pdf"
        )
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    pdf_byte_length = len(pdf_bytes)
    if (
        source_receipt.status is not SourceAccessStatus.VERIFIED
        or source_receipt.read_kind != "FULL"
        or source_receipt.carrier_id != carrier_id
        or source_receipt.source_version != version
        or source_receipt.content_sha256 != pdf_sha256
        or source_receipt.byte_length != pdf_byte_length
    ):
        raise PdfPageEvidenceError(
            "SOURCE_RECEIPT_MISMATCH", "validated FULL source receipt is inconsistent"
        )
    source_receipt_digest = _full_receipt_sha256(source_receipt)

    reader = _open_pdf_reader(pdf_bytes, pdf_byte_length)
    page_count = _bounded_page_count(reader)
    page_text = _extract_bounded_page_text(reader, page_number, page_count)
    resolved_offset, actual_window = _resolve_excerpt_window(
        page_text, expected_excerpt, offset, effective_length
    )

    return PdfPageEvidenceReceipt(
        carrier_id=carrier_id,
        source_version=version,
        source_access_policy=source_access.policy.value,
        source_access_full_receipt_sha256=source_receipt_digest,
        pdf_sha256=pdf_sha256,
        pdf_byte_length=pdf_byte_length,
        page_number=page_number,
        page_count=page_count,
        page_text_sha256=_safe_text_sha256(page_text),
        excerpt_sha256=_safe_text_sha256(actual_window),
        offset=resolved_offset,
        length=effective_length,
        extractor_name=_EXTRACTOR_NAME,
        extractor_version=_EXTRACTOR_VERSION,
    )


def _check_pdf_page_excerpts_from_bytes(
    *,
    pdf_bytes: bytes,
    carrier_id: str,
    source_version: str,
    source_receipt: SourceAccessReceipt,
    queries: Sequence[PageExcerptQuery],
) -> list[PdfPageEvidenceReceipt | PdfPageEvidenceError]:
    """Check many (page, excerpt) queries against one already-admitted PDF read.

    ``pdf_bytes``, ``source_version`` and ``source_receipt``
    must all come from exactly one prior, already-validated
    ``RuntimeSourceAccess.read_full_with_metadata`` call (media type, source
    receipt consistency and digest/version binding already checked by the
    caller). This function never calls back into ``RuntimeSourceAccess`` and
    never re-reads the source: the caller remains solely responsible for F07
    admission. It parses the PDF exactly once and calls ``extract_text()``
    at most once per *distinct* page number across all queries, instead of
    once per query, bounding resource use when many claims cite the same
    carrier.

    Document-level failures (unavailable extractor version, malformed/
    encrypted/oversized document, invalid page tree) apply to every query
    equally and are raised once rather than returned, since no query could
    have succeeded anyway. Per-page and per-excerpt failures (bad page
    number, image-only page, excerpt not found/ambiguous/mismatched,
    non-UTF-8 extracted text, ...) are independent per query and so are
    *returned* as ``PdfPageEvidenceError`` instances aligned by index with
    ``queries``, never raised, so one bad claim cannot hide the outcome of
    the others.
    """

    if not _EXTRACTOR_VERSION:
        raise PdfPageEvidenceError(
            "EXTRACTOR_VERSION_UNAVAILABLE",
            "PDF extractor version must be known to create reproducible evidence",
        )

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    pdf_byte_length = len(pdf_bytes)
    # Validate the *receipt object*, not a caller-supplied digest string.
    # The helper is PRIVATE and still does not grant owner/legal rights:
    # F07 admission is the responsibility of verify_pdf_model_claims.
    if (
        type(source_receipt) is not SourceAccessReceipt
        or source_receipt.status is not SourceAccessStatus.VERIFIED
        or source_receipt.read_kind != "FULL"
        or source_receipt.carrier_id != carrier_id
        or source_receipt.source_version != source_version
        or source_receipt.content_sha256 != pdf_sha256
        or source_receipt.byte_length != pdf_byte_length
    ):
        raise PdfPageEvidenceError(
            "SOURCE_RECEIPT_MISMATCH",
            "private batch helper rejected source/receipt inconsistency",
        )
    source_access_full_receipt_sha256 = _full_receipt_sha256(source_receipt)
    reader = _open_pdf_reader(pdf_bytes, pdf_byte_length)
    page_count = _bounded_page_count(reader)

    page_text_cache: dict[int, str | PdfPageEvidenceError] = {}
    page_sha_cache: dict[int, str | PdfPageEvidenceError] = {}

    def page_text_for(page_number: int) -> str:
        if page_number not in page_text_cache:
            try:
                page_text_cache[page_number] = _extract_bounded_page_text(
                    reader, page_number, page_count
                )
            except PdfPageEvidenceError as exc:
                page_text_cache[page_number] = exc
        cached = page_text_cache[page_number]
        if isinstance(cached, PdfPageEvidenceError):
            raise cached
        return cached

    def page_sha_for(page_number: int, page_text: str) -> str:
        if page_number not in page_sha_cache:
            try:
                page_sha_cache[page_number] = _safe_text_sha256(page_text)
            except PdfPageEvidenceError as exc:
                page_sha_cache[page_number] = exc
        cached = page_sha_cache[page_number]
        if isinstance(cached, PdfPageEvidenceError):
            raise cached
        return cached

    results: list[PdfPageEvidenceReceipt | PdfPageEvidenceError] = []
    for query in queries:
        try:
            effective_length = _validate_query_inputs(
                query.page_number, query.expected_excerpt, query.offset, query.length
            )
            page_number: int = query.page_number  # validated above
            expected_excerpt: str = query.expected_excerpt  # validated above
            page_text = page_text_for(page_number)
            resolved_offset, actual_window = _resolve_excerpt_window(
                page_text, expected_excerpt, query.offset, effective_length
            )
            page_text_sha256 = page_sha_for(page_number, page_text)
            excerpt_sha256 = _safe_text_sha256(actual_window)
            results.append(
                PdfPageEvidenceReceipt(
                    carrier_id=carrier_id,
                    source_version=source_version,
                    source_access_full_receipt_sha256=source_access_full_receipt_sha256,
                    pdf_sha256=pdf_sha256,
                    pdf_byte_length=pdf_byte_length,
                    page_number=page_number,
                    page_count=page_count,
                    page_text_sha256=page_text_sha256,
                    excerpt_sha256=excerpt_sha256,
                    offset=resolved_offset,
                    length=effective_length,
                    extractor_name=_EXTRACTOR_NAME,
                    extractor_version=_EXTRACTOR_VERSION,
                )
            )
        except PdfPageEvidenceError as exc:
            results.append(exc)
    return results
