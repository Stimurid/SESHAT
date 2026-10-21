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
  page, or excerpt/offset mismatch raises ``PdfPageEvidenceError`` instead
  of guessing or returning a best-effort match.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import SourceAccessStatus
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
    # Set only by the sandbox wrapper. The host checks shape and bounds, but
    # cannot independently prove the child's extracted page text or offset.
    sandbox_child_observation_provenance: Literal["CHILD_ASSERTED_UNATTESTED"] | None = None


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

    effective_length = length if length is not None else len(expected_excerpt)

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
    source_receipt_digest = hashlib.sha256(
        json.dumps(
            source_receipt.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

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

    try:
        page_count = len(reader.pages)
    except Exception:  # noqa: BLE001
        raise PdfPageEvidenceError(
            "MALFORMED_DOCUMENT", "PDF page tree is invalid"
        ) from None

    if page_count > MAX_PAGE_COUNT:
        raise PdfPageEvidenceError(
            "PATHOLOGICAL_SIZE", f"page count exceeds bounded limit of {MAX_PAGE_COUNT}"
        )
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

    return PdfPageEvidenceReceipt(
        carrier_id=carrier_id,
        source_version=version,
        source_access_policy=source_access.policy.value,
        source_access_full_receipt_sha256=source_receipt_digest,
        pdf_sha256=pdf_sha256,
        pdf_byte_length=pdf_byte_length,
        page_number=page_number,
        page_count=page_count,
        page_text_sha256=hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
        excerpt_sha256=hashlib.sha256(actual_window.encode("utf-8")).hexdigest(),
        offset=resolved_offset,
        length=effective_length,
        extractor_name=_EXTRACTOR_NAME,
        extractor_version=_EXTRACTOR_VERSION,
    )
