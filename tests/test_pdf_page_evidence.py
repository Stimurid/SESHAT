"""Tests for the bounded PDF page-evidence checker.

All PDFs here are invented in-memory fixtures built with pypdf's PdfWriter
plus a hand-built text content stream. No real/authored source material,
no fixtures committed to disk, no network, no OCR.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.pdf_page_evidence import (
    PdfPageEvidenceError,
    check_pdf_page_excerpt,
)
from seshat.runtime import EvidenceAccessError, RuntimeSourceAccess
import seshat.pdf_page_evidence as pdf_page_evidence


def _build_pdf(page_texts: list[str | None]) -> bytes:
    """Build a minimal in-memory multi-page PDF; None pages carry no content stream."""

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=300, height=300)
        if text is None:
            continue
        stream_obj = DecodedStreamObject()
        stream_obj.set_data(f"BT /F1 18 Tf 10 250 Td ({text}) Tj ET".encode("latin-1"))
        stream_ref = writer._add_object(stream_obj)
        font_obj = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font_obj)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        page[NameObject("/Contents")] = stream_ref
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _reference_page_text(pdf_bytes: bytes, page_number: int) -> str:
    """Independently extract page text the same way the module does.

    Used only to derive real, explicit offsets for the "pinned offset"
    positive tests below instead of guessing at pypdf's exact whitespace
    behavior around a hand-built content stream.
    """

    reader = PdfReader(BytesIO(pdf_bytes))
    return reader.pages[page_number - 1].extract_text() or ""


PDF_A = _build_pdf(["The quick brown fox jumps over the lazy dog."])
PDF_B = _build_pdf(
    [
        "Alpha section content unique here.",
        "Beta repeats alpha twice: alpha and alpha again.",
    ]
)
PDF_IMAGE_ONLY = _build_pdf([None])


class _DictContentProvider:
    def __init__(self, contents: dict[str, SourceContent]) -> None:
        self._contents = contents

    def open_content(self, carrier_id: str) -> SourceContent:
        return self._contents[carrier_id]


def _access_for(
    pdf_bytes: bytes,
    *,
    carrier_id: str = "pdf1",
    policy: RawAccessPolicy = RawAccessPolicy.FULL_REQUIRED,
    version: str = "1",
    content_version: str | None = None,
    carrier_sha256: str | None = None,
    carrier_byte_length: int | None = None,
    complete: bool = True,
    authorized: bool = True,
    missing_content: bool = False,
    carrier_media_type: str | None = "application/pdf",
    content_media_type: str = "application/pdf",
) -> RuntimeSourceAccess:
    actual_sha = hashlib.sha256(pdf_bytes).hexdigest()
    carrier = SourceCarrier(
        carrier_id=carrier_id,
        source_identity=f"source:{carrier_id}",
        version=version,
        media_type=carrier_media_type,
        content_sha256=carrier_sha256 or actual_sha,
        byte_length=carrier_byte_length if carrier_byte_length is not None else len(pdf_bytes),
    )
    contents: dict[str, SourceContent] = {}
    if not missing_content:
        contents[carrier_id] = SourceContent(
            carrier_id=carrier_id,
            source_version=content_version or version,
            media_type=content_media_type,
            content=pdf_bytes,
            content_sha256=actual_sha,
            byte_length=len(pdf_bytes),
            complete=complete,
            authorized=authorized,
        )
    return RuntimeSourceAccess(
        policy=policy,
        carriers=(carrier,),
        content_provider=_DictContentProvider(contents),
        carrier_ids=(carrier_id,),
    )


# -- Positive cases -----------------------------------------------------------


def test_explicit_offset_excerpt_verified_on_single_page_pdf() -> None:
    phrase = "quick brown fox"
    offset = _reference_page_text(PDF_A, 1).index(phrase)
    access = _access_for(PDF_A)
    receipt = check_pdf_page_excerpt(
        access,
        "pdf1",
        page_number=1,
        expected_excerpt=phrase,
        offset=offset,
        length=len(phrase),
    )
    assert receipt.carrier_id == "pdf1"
    assert receipt.page_number == 1
    assert receipt.page_count == 1
    assert receipt.pdf_sha256 == hashlib.sha256(PDF_A).hexdigest()
    assert receipt.pdf_byte_length == len(PDF_A)
    assert receipt.excerpt_sha256 == hashlib.sha256(phrase.encode()).hexdigest()
    assert receipt.extractor_name == "pypdf"
    assert receipt.rights_independently_attested == "NO"
    assert receipt.human_acceptance == "NOT_ASSERTED"
    assert receipt.acceptance == "PROPOSED"


def test_second_distinct_pdf_second_page_explicit_offset() -> None:
    phrase = "Beta repeats alpha"
    offset = _reference_page_text(PDF_B, 2).index(phrase)
    access = _access_for(PDF_B)
    receipt = check_pdf_page_excerpt(
        access,
        "pdf1",
        page_number=2,
        expected_excerpt=phrase,
        offset=offset,
        length=len(phrase),
    )
    assert receipt.page_number == 2
    assert receipt.page_count == 2
    assert receipt.pdf_sha256 == hashlib.sha256(PDF_B).hexdigest()


def test_unique_excerpt_without_offset_resolves_correct_position() -> None:
    access = _access_for(PDF_A)
    receipt = check_pdf_page_excerpt(
        access, "pdf1", page_number=1, expected_excerpt="lazy dog."
    )
    assert receipt.length == len("lazy dog.")
    assert receipt.excerpt_sha256 == hashlib.sha256(b"lazy dog.").hexdigest()


# -- Negative: page / offset / excerpt -----------------------------------


def test_wrong_page_number_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=2, expected_excerpt="fox", offset=0, length=3
        )
    assert caught.value.code == "PAGE_OUT_OF_RANGE"


def test_wrong_excerpt_at_explicit_offset_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access,
            "pdf1",
            page_number=1,
            expected_excerpt="elephant",
            offset=4,
            length=len("elephant"),
        )
    assert caught.value.code == "EXCERPT_MISMATCH"


def test_negative_offset_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=1, expected_excerpt="fox", offset=-1, length=3
        )
    assert caught.value.code == "OFFSET_INVALID"


def test_non_positive_length_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=1, expected_excerpt="fox", offset=16, length=0
        )
    assert caught.value.code == "LENGTH_INVALID"


def test_offset_length_beyond_page_text_end_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=1, expected_excerpt="dog.", offset=9999, length=4
        )
    assert caught.value.code == "OFFSET_OUT_OF_RANGE"


def test_ambiguous_duplicate_excerpt_without_offset_rejected() -> None:
    access = _access_for(PDF_B)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=2, expected_excerpt="alpha")
    assert caught.value.code == "EXCERPT_AMBIGUOUS"


def test_excerpt_not_found_without_offset_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="giraffe")
    assert caught.value.code == "EXCERPT_NOT_FOUND"


def test_empty_excerpt_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="")
    assert caught.value.code == "EXCERPT_EMPTY"


def test_page_number_below_one_rejected() -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=0, expected_excerpt="fox")
    assert caught.value.code == "PAGE_NUMBER_INVALID"


# -- Negative: document-level -----------------------------------------------


def test_image_only_unextractable_page_rejected() -> None:
    access = _access_for(PDF_IMAGE_ONLY)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="anything")
    assert caught.value.code == "IMAGE_ONLY_PAGE"


def test_encrypted_document_rejected() -> None:
    w = PdfWriter()
    w.append(BytesIO(PDF_A))
    w.encrypt(user_password="synthetic-only")
    buf = BytesIO()
    w.write(buf)
    encrypted_bytes = buf.getvalue()

    access = _access_for(encrypted_bytes)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "ENCRYPTED_DOCUMENT"


def test_missing_pdf_header_rejected() -> None:
    access = _access_for(b"NOT A PDF AT ALL, JUST BYTES")
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "MALFORMED_DOCUMENT"


def test_empty_document_rejected() -> None:
    access = _access_for(b"")
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "MALFORMED_DOCUMENT"


def test_truncated_document_rejected() -> None:
    # Keep only the header; the catalog/xref/trailer are entirely gone, so
    # there is no recovery path that could locate a page tree.
    truncated = PDF_A[:20]
    access = _access_for(truncated)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    # pypdf's lenient recovery parser may surface truncation either as an
    # outright parse failure or as a (possibly empty) recovered page tree;
    # both are acceptable fail-closed outcomes here.
    assert caught.value.code in {"MALFORMED_DOCUMENT", "PAGE_OUT_OF_RANGE", "UNEXTRACTABLE_PAGE"}


def test_pathological_byte_size_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_page_evidence, "MAX_PDF_BYTES", 10)
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "PATHOLOGICAL_SIZE"


def test_pathological_page_count_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_page_evidence, "MAX_PAGE_COUNT", 1)
    access = _access_for(PDF_B)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="Alpha")
    assert caught.value.code == "PATHOLOGICAL_SIZE"


# -- Negative: source-access boundary (never, drillback, tamper, drift, etc.) -


@pytest.mark.parametrize("policy", [RawAccessPolicy.NEVER, RawAccessPolicy.DRILLBACK])
def test_non_full_required_policy_denied(policy: RawAccessPolicy) -> None:
    access = _access_for(PDF_A, policy=policy)
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "POLICY_DENIED"


def test_tampered_digest_denied_before_reaching_pdf_parser() -> None:
    access = _access_for(PDF_A, carrier_sha256="0" * 64)
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "INTEGRITY_ERROR"


def test_version_drift_denied() -> None:
    access = _access_for(PDF_A, content_version="2")
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "SOURCE_DRIFT"


def test_incomplete_source_denied() -> None:
    access = _access_for(PDF_A, complete=False)
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "PARTIAL_SOURCE"


def test_unauthorized_source_denied() -> None:
    access = _access_for(PDF_A, authorized=False)
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "UNAUTHORIZED"


def test_missing_source_denied() -> None:
    access = _access_for(PDF_A, missing_content=True)
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "CONTENT_UNAVAILABLE"


# -- PDF text-projection bypass stays denied at the fabric_waves boundary ----


def test_pdf_utf8_text_projection_bypass_denied_by_fabric_carrier_store() -> None:
    actual_sha = hashlib.sha256(PDF_A).hexdigest()
    carrier = SourceCarrier(
        carrier_id="pdf1",
        source_identity="source:pdf1",
        version="1",
        media_type="application/pdf",
        content_sha256=actual_sha,
        byte_length=len(PDF_A),
    )
    content = SourceContent(
        carrier_id="pdf1",
        source_version="1",
        media_type="application/pdf",
        content=PDF_A,
        content_sha256=actual_sha,
        byte_length=len(PDF_A),
        complete=True,
        authorized=True,
    )
    store = FabricCarrierStore(carriers={"pdf1": carrier}, contents={"pdf1": content})

    with pytest.raises(ValueError, match="SOURCE_MEDIA_TEXT_PROJECTION_UNSUPPORTED"):
        store.resolve_payload(
            policy=RawAccessPolicy.FULL_REQUIRED,
            carrier_ids=("pdf1",),
            stone_payload={},
            operation_id="probe",
        )


# -- Independent red-QA promoted into the canonical regression suite --------


@pytest.mark.parametrize("bad_page", [True, 1.5, "1", None])
def test_strict_positive_integer_page_rejects_python_coercion(bad_page) -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=bad_page, expected_excerpt="fox")
    assert caught.value.code == "PAGE_NUMBER_INVALID"


@pytest.mark.parametrize("bad_offset", [True, 0.5, "0"])
def test_strict_nonnegative_integer_offset_rejects_python_coercion(bad_offset) -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=1,
            expected_excerpt="fox", offset=bad_offset,
        )
    assert caught.value.code == "OFFSET_INVALID"


@pytest.mark.parametrize("bad_length", [True, 1.5, "3"])
def test_strict_positive_integer_length_rejects_python_coercion(bad_length) -> None:
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(
            access, "pdf1", page_number=1,
            expected_excerpt="fox", offset=0, length=bad_length,
        )
    assert caught.value.code == "LENGTH_INVALID"


def test_overlapping_repeated_excerpt_requires_exact_offset() -> None:
    # Nonoverlapping str.count("aa") on "aaa" is 1, though two source
    # positions (0 and 1) actually match the excerpt.
    overlap_pdf = _build_pdf(["aaa"])
    access = _access_for(overlap_pdf)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="aa")
    assert caught.value.code == "EXCERPT_AMBIGUOUS"


def test_receipt_model_rejects_fabricated_positive_rights_or_acceptance() -> None:
    from pydantic import ValidationError
    from seshat.pdf_page_evidence import PdfPageEvidenceReceipt

    forged = {
        "carrier_id": "public-fixture",
        "source_version": "v1",
        "source_access_policy": "FULL_REQUIRED",
        "source_access_full_receipt_sha256": "f" * 64,
        "pdf_sha256": "0" * 64,
        "pdf_byte_length": 100,
        "page_number": 1,
        "page_count": 1,
        "page_text_sha256": "1" * 64,
        "excerpt_sha256": "2" * 64,
        "offset": 0,
        "length": 3,
        "extractor_name": "fixture",
        "extractor_version": "1",
        "rights_independently_attested": "YES",
        "human_acceptance": "ACCEPTED",
        "acceptance": "ACCEPTED",
    }
    with pytest.raises(ValidationError):
        PdfPageEvidenceReceipt.model_validate(forged)


def test_trailer_deleted_without_eof_is_rejected() -> None:
    truncated = PDF_A.rsplit(b"%%EOF", 1)[0]
    access = _access_for(truncated)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "MALFORMED_DOCUMENT"


def test_page_extraction_length_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_page_evidence, "MAX_PAGE_TEXT_CHARS", 8)
    access = _access_for(PDF_A)
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "PATHOLOGICAL_SIZE"


# -- Opus independent exact-SHA review H1/M2/M3: proven negative contracts --


def test_pdf_drillback_ascii_byte_slice_cannot_become_fabric_text() -> None:
    """Even an ASCII-readable PDF byte range is never source TEXT for G1."""
    digest = hashlib.sha256(PDF_A).hexdigest()
    carrier = SourceCarrier(
        carrier_id="pdf1",
        source_identity="synthetic-test:pdf1",
        version="1",
        media_type="application/pdf",
        content_sha256=digest,
        byte_length=len(PDF_A),
    )
    body = SourceContent(
        carrier_id="pdf1", source_version="1", media_type="application/pdf",
        content=PDF_A, content_sha256=digest, byte_length=len(PDF_A),
        complete=True, authorized=True,
    )
    store = FabricCarrierStore(carriers={"pdf1": carrier}, contents={"pdf1": body})
    # %PDF-... is ASCII; a generic UTF-8 decode would erroneously succeed.
    with pytest.raises(ValueError, match="SOURCE_MEDIA_TEXT_PROJECTION_UNSUPPORTED"):
        store.resolve_payload(
            policy=RawAccessPolicy.DRILLBACK,
            carrier_ids=("pdf1",),
            stone_payload={"drillback_address": {
                "carrier_id": "pdf1", "source_version": "1",
                "address_type": "byte_range", "start": 0, "end": 6
            }},
            operation_id="independent-pdf-review",
        )


@pytest.mark.parametrize(
    ("declared_media_type", "actual_media_type"),
    [("text/plain", "text/plain"), (None, "application/pdf")],
)
def test_pdf_header_cannot_self_upgrade_a_non_pdf_carrier(
    declared_media_type: str | None, actual_media_type: str,
) -> None:
    """Content sniffing never becomes source-admission authority."""
    access = _access_for(
        PDF_A,
        carrier_media_type=declared_media_type,
        content_media_type=actual_media_type,
    )
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "PDF_MEDIA_TYPE_REQUIRED"


def test_mismatched_pdf_and_text_metadata_denied_by_source_access() -> None:
    access = _access_for(
        PDF_A, carrier_media_type="text/plain", content_media_type="application/pdf",
    )
    with pytest.raises(EvidenceAccessError) as caught:
        check_pdf_page_excerpt(access, "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code.value == "SOURCE_DRIFT"


def test_pdf_page_receipt_binds_source_version_policy_and_exact_full_read() -> None:
    access = _access_for(PDF_A, version="fixed-pdf-v7")
    receipt = check_pdf_page_excerpt(
        access, "pdf1", page_number=1, expected_excerpt="brown fox",
    )
    assert receipt.source_version == "fixed-pdf-v7"
    assert receipt.source_access_policy == "FULL_REQUIRED"
    assert receipt.pdf_sha256 == hashlib.sha256(PDF_A).hexdigest()

    manifest = access.manifest()
    assert manifest.policy is RawAccessPolicy.FULL_REQUIRED
    assert len(manifest.receipts) == 1
    full = manifest.receipts[0]
    assert full.source_version == receipt.source_version
    assert full.content_sha256 == receipt.pdf_sha256
    assert full.read_kind == "FULL"
    assert receipt.source_access_full_receipt_sha256 == hashlib.sha256(
        json.dumps(
            full.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert receipt.rights_independently_attested == "NO"


# -- Post-review low-level source-contract hardening -------------------------


def test_missing_extractor_version_fails_before_citing_any_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_page_evidence, "_EXTRACTOR_VERSION", "")
    with pytest.raises(PdfPageEvidenceError) as caught:
        check_pdf_page_excerpt(_access_for(PDF_A), "pdf1", page_number=1, expected_excerpt="fox")
    assert caught.value.code == "EXTRACTOR_VERSION_UNAVAILABLE"


@pytest.mark.parametrize("policy", [RawAccessPolicy.FULL_REQUIRED, RawAccessPolicy.DRILLBACK])
def test_non_utf8_text_carrier_is_typed_denial_not_raw_decode_error(
    policy: RawAccessPolicy,
) -> None:
    malformed = b"UTF8-introducer-\xff-invalid"
    digest = hashlib.sha256(malformed).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented-text1", source_identity="synthetic-test:invented-text1",
        version="v1", media_type="text/plain",
        content_sha256=digest, byte_length=len(malformed),
    )
    content = SourceContent(
        carrier_id="invented-text1", source_version="v1", media_type="text/plain",
        content=malformed, content_sha256=digest, byte_length=len(malformed),
        complete=True, authorized=True,
    )
    store = FabricCarrierStore(
        carriers={"invented-text1": carrier}, contents={"invented-text1": content},
    )
    drill = {"drillback_address": {
        "carrier_id": "invented-text1", "source_version": "v1",
        "address_type": "byte_range", "start": 0, "end": len(malformed),
    }}
    with pytest.raises(ValueError, match="SOURCE_TEXT_UTF8_INVALID"):
        store.resolve_payload(
            policy=policy, carrier_ids=("invented-text1",),
            stone_payload=drill if policy is RawAccessPolicy.DRILLBACK else {},
            operation_id="synthetic-negative",
        )
