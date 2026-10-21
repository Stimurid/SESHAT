"""Invented in-memory PDF QA for the atomic model quote gate."""

from __future__ import annotations

import hashlib
import json
import re
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import seshat.pdf_page_evidence as pdf_page_evidence
from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.pdf_claims import (
    ClaimDiagnostic,
    ModelCandidate,
    ModelQuoteGateReceipt,
    verify_pdf_model_claims,
)
from seshat.runtime import RuntimeSourceAccess

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _pdf(pages: list[str]) -> bytes:
    writer = PdfWriter()
    for value in pages:
        page = writer.add_blank_page(width=300, height=300)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 250 Td ({value}) Tj ET".encode("ascii"))
        font = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }))
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


PDF_ONE = _pdf([
    "Harbor clock records twelve pulses. Calibration paper was absent.",
    "The red buoy remained stationary. A blue lamp flashed twice.",
])
PDF_TWO = _pdf([
    "Orchard rows hold pear trees. Soil samples were stored indoors.",
    "Watering note repeats repeats and repeats again.",
])


class _Provider:
    def __init__(self, content: SourceContent) -> None:
        self.content = content

    def open_content(self, carrier_id: str) -> SourceContent:
        return self.content


def _access(
    data: bytes = PDF_ONE, *, policy: RawAccessPolicy = RawAccessPolicy.FULL_REQUIRED,
    complete: bool = True, authorized: bool = True,
    carrier_media_type: str | None = "application/pdf",
    content_media_type: str = "application/pdf",
) -> RuntimeSourceAccess:
    digest = hashlib.sha256(data).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented-pdf", source_identity="invented-only", version="v1",
        media_type=carrier_media_type, content_sha256=digest, byte_length=len(data),
    )
    content = SourceContent(
        carrier_id="invented-pdf", source_version="v1", media_type=content_media_type,
        content=data, content_sha256=digest, byte_length=len(data),
        complete=complete, authorized=authorized,
    )
    return RuntimeSourceAccess(policy, (carrier,), _Provider(content), ("invented-pdf",))


def _candidate() -> dict:
    return {
        "schema": "seshat.pdf_claims.v1", "method_id": "invented-method-tag",
        "source_id": "invented-pdf", "source_version": "v1",
        "run_scope": "SYNTHETIC_QA",
        "evidence": [
            {"claim": "Clock pulses recorded", "page": 1,
             "excerpt": "Harbor clock records twelve pulses.", "kind": "SOURCE_STATED"},
            {"claim": "Buoy position reported", "page": 2,
             "excerpt": "The red buoy remained stationary.", "kind": "SOURCE_STATED"},
        ],
        "unknowns": ["Instrument calibration remains unknown"],
        "rights_independently_attested": "NO",
        "scientific_acceptance": "NOT_ASSERTED", "customer_release": "NOT_AUTHORIZED",
    }


def _run(candidate: dict, access: RuntimeSourceAccess | None = None):
    payload = json.dumps(candidate, separators=(",", ":")).encode()
    return verify_pdf_model_claims(
        access=access or _access(), carrier_id="invented-pdf", response_json=payload
    )


def test_all_quotes_verified_without_promoting_semantics_or_rights() -> None:
    candidate = _candidate()
    result = _run(candidate)
    assert result.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert [item.code for item in result.claims] == ["EXACT_QUOTE", "EXACT_QUOTE"]
    assert result.semantic_entailment == "NOT_ASSESSED"
    assert result.real_model_identity == "NOT_INDEPENDENTLY_ATTESTED"
    assert result.rights_independently_attested == "NO"
    assert result.scientific_acceptance == "NOT_ASSERTED"
    assert result.customer_release == "NOT_AUTHORIZED"
    assert result.pdf_sha256 == hashlib.sha256(PDF_ONE).hexdigest()
    assert result.source_access_full_receipt_sha256
    dumped = result.model_dump_json()
    assert "Harbor clock" not in dumped and "Buoy" not in dumped
    assert "Clock pulses" not in dumped


def test_second_dissimilar_pdf() -> None:
    candidate = _candidate()
    candidate["evidence"] = [
        {"claim": "Pear rows", "page": 1, "excerpt": "Orchard rows hold pear trees.",
         "kind": "SOURCE_STATED"},
        {"claim": "Watering note", "page": 2, "excerpt": "Watering note repeats",
         "kind": "SOURCE_STATED"},
    ]
    assert _run(candidate, _access(PDF_TWO)).status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"


def test_atomic_red_for_two_of_four_invalid_quotes() -> None:
    candidate = _candidate()
    candidate["evidence"] += [
        {"claim": "Invented joined sentence", "page": 1,
         "excerpt": "Harbor clock records twelve pulses. The red buoy remained stationary.",
         "kind": "SOURCE_STATED"},
        {"claim": "Invented adjacent join", "page": 1,
         "excerpt": "pulses.Calibration paper was absent.", "kind": "SOURCE_STATED"},
    ]
    result = _run(candidate)
    assert result.status == "REJECTED"
    assert [x.code for x in result.claims] == [
        "EXACT_QUOTE", "EXACT_QUOTE", "EXCERPT_NOT_FOUND", "EXCERPT_NOT_FOUND",
    ]


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(source_id="other-file"),
    lambda c: c.update(source_version="v0"),
    lambda c: c.update(source_sha256="0" * 64),
    lambda c: c["evidence"][0].update(page=2),
    lambda c: c["evidence"][0].update(excerpt="imaginary quote"),
    lambda c: c["evidence"][0].update(page=True),
    lambda c: c["evidence"][0].update(excerpt="x" * 2001),
    lambda c: c["evidence"][0].update(unexpected="field"),
    lambda c: c.update(rights_independently_attested="YES"),
    lambda c: c.update(scientific_acceptance="ACCEPTED"),
    lambda c: c.update(customer_release="AUTHORIZED"),
    lambda c: c.update(run_scope="REAL_SOURCE"),
    lambda c: c.update(unknowns=[]),
])
def test_invalid_candidates_are_rejected(mutate) -> None:
    candidate = _candidate()
    mutate(candidate)
    assert _run(candidate).status == "REJECTED"


def test_repeated_excerpt_is_ambiguous_even_when_overlapping() -> None:
    candidate = _candidate()
    candidate["evidence"][0].update(page=2, excerpt="repeats")
    result = _run(candidate, _access(PDF_TWO))
    assert result.status == "REJECTED"
    assert result.claims[0].code == "EXCERPT_AMBIGUOUS"


@pytest.mark.parametrize("policy,complete,authorized", [
    (RawAccessPolicy.NEVER, True, True),
    (RawAccessPolicy.DRILLBACK, True, True),
    (RawAccessPolicy.FULL_REQUIRED, False, True),
    (RawAccessPolicy.FULL_REQUIRED, True, False),
])
def test_denied_or_incomplete_f07(policy, complete, authorized) -> None:
    result = _run(_candidate(), _access(policy=policy, complete=complete, authorized=authorized))
    assert result.status == "REJECTED"
    assert result.code == "SOURCE_ACCESS_DENIED"


def test_exact_response_bytes_are_hashed_and_duplicate_keys_rejected() -> None:
    candidate = _candidate()
    raw = json.dumps(candidate).encode()
    receipt = verify_pdf_model_claims(
        access=_access(), carrier_id="invented-pdf", response_json=raw
    )
    assert receipt.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.response_sha256 != _run(candidate).response_sha256
    duplicate = raw[:-1] + b',"schema":"seshat.pdf_claims.v1"}'
    assert verify_pdf_model_claims(
        access=_access(), carrier_id="invented-pdf", response_json=duplicate
    ).status == "REJECTED"


def test_response_size_bomb_rejected_before_parsing() -> None:
    result = verify_pdf_model_claims(
        access=_access(), carrier_id="invented-pdf", response_json=b" " * 32769
    )
    assert result.code == "RESPONSE_TOO_LARGE"


def test_positive_gate_never_claims_semantic_entailment() -> None:
    # The cited source is exact, but the claim is deliberately unjustified.
    # Quote matching must NOT certify this claim to be semantically true.
    candidate = _candidate()
    candidate["evidence"][0]["claim"] = "The timer was calibrated and certified."
    candidate["evidence"][0]["excerpt"] = "Calibration paper was absent."
    result = _run(candidate)
    assert result.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert result.semantic_entailment == "NOT_ASSESSED"
    assert result.scientific_acceptance == "NOT_ASSERTED"


def test_forged_green_receipt_without_proven_quotes_is_structurally_invalid() -> None:
    from pydantic import ValidationError
    from seshat.pdf_claims import ModelQuoteGateReceipt

    alleged = {
        "status": "EXACT_PDF_PAGE_EXCERPTS_VERIFIED",
        "code": "ALL_EXCERPTS_EXACT",
        "response_sha256": "0" * 64,
        "source_id": "invented-pdf",
        "source_version": "v1",
        "pdf_sha256": "1" * 64,
        "source_access_full_receipt_sha256": "2" * 64,
        "claims": [],
        "rights_independently_attested": "NO",
        "scientific_acceptance": "NOT_ASSERTED",
        "customer_release": "NOT_AUTHORIZED",
    }
    with pytest.raises(ValidationError):
        ModelQuoteGateReceipt.model_validate(alleged)


# -- Opus audit jx-fc199987dd7a CONDITIONAL_PASS rework: A-F regression tests -


def test_unpaired_surrogate_page_text_rejected_not_crashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A: a malformed-PDF page whose extracted text has an unpaired surrogate
    must come back as a typed REJECTED diagnostic, never an uncaught
    UnicodeEncodeError leaking out of the gate."""

    def fake_extract(reader, page_number, page_count):
        if page_number == 1:
            return "prefix \ud800 Harbor clock records twelve pulses."
        return "prefix \ud800 The red buoy remained stationary."

    monkeypatch.setattr(pdf_page_evidence, "_extract_bounded_page_text", fake_extract)
    result = _run(_candidate())
    assert result.status == "REJECTED"
    assert result.code == "CLAIM_EVIDENCE_FAILED"
    assert all(item.code == "PAGE_TEXT_UNICODE_INVALID" for item in result.claims)
    dumped = result.model_dump_json()
    assert "\\ud800" not in dumped and "Harbor clock" not in dumped


def test_duplicate_page_excerpt_pair_rejected_before_source_read() -> None:
    """B: an identical (page, excerpt) pair repeated twice must not satisfy
    the evidence-count minimum; it must be rejected before any source read,
    proven here by making the underlying read fail if it were ever reached."""

    candidate = _candidate()
    candidate["evidence"][1] = dict(candidate["evidence"][0])
    result = _run(candidate, _access(authorized=False))
    assert result.status == "REJECTED"
    assert result.code == "CANDIDATE_DUPLICATE_EVIDENCE"


def test_single_parse_and_one_extract_per_distinct_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C: N claims spread across 2 distinct pages must parse the PDF exactly
    once and call the page-extraction helper exactly once per distinct page,
    not once per claim."""

    construct_calls: list[int] = []
    real_reader_cls = pdf_page_evidence.PdfReader

    class _CountingReader(real_reader_cls):
        def __init__(self, *args: object, **kwargs: object) -> None:
            construct_calls.append(1)
            super().__init__(*args, **kwargs)

    extract_calls: list[int] = []
    real_extract = pdf_page_evidence._extract_bounded_page_text

    def _counting_extract(reader, page_number, page_count):
        extract_calls.append(page_number)
        return real_extract(reader, page_number, page_count)

    monkeypatch.setattr(pdf_page_evidence, "PdfReader", _CountingReader)
    monkeypatch.setattr(pdf_page_evidence, "_extract_bounded_page_text", _counting_extract)

    candidate = _candidate()
    candidate["evidence"] = [
        {"claim": "a", "page": 1, "excerpt": "Harbor clock records twelve pulses.",
         "kind": "SOURCE_STATED"},
        {"claim": "b", "page": 1, "excerpt": "Calibration paper was absent.",
         "kind": "SOURCE_STATED"},
        {"claim": "c", "page": 2, "excerpt": "The red buoy remained stationary.",
         "kind": "SOURCE_STATED"},
        {"claim": "d", "page": 2, "excerpt": "A blue lamp flashed twice.",
         "kind": "SOURCE_STATED"},
    ]
    result = _run(candidate)
    assert result.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert len(construct_calls) == 1
    assert sorted(extract_calls) == [1, 2]


def test_receipt_retains_method_id_run_scope_and_self_observed_provenance() -> None:
    """D: the private receipt must retain the method_id tag and run_scope,
    and always carry the fixed SELF_OBSERVED_UNATTESTED provenance literal."""

    result = _run(_candidate())
    assert result.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert result.method_id == "invented-method-tag"
    assert result.run_scope == "SYNTHETIC_QA"
    assert result.source_provenance == "SELF_OBSERVED_UNATTESTED"

    rejected = _run(_candidate(), _access(authorized=False))
    assert rejected.status == "REJECTED"
    assert rejected.method_id == "invented-method-tag"
    assert rejected.run_scope == "SYNTHETIC_QA"
    assert rejected.source_provenance == "SELF_OBSERVED_UNATTESTED"


def test_receipt_constructor_is_forgeable_shape_not_cryptographic_attestation() -> None:
    """D: direct construction with two fabricated EXACT_QUOTE diagnostics and
    dummy-but-well-formed digests must succeed. This is an ordinary Pydantic
    shape check, NOT proof any quote/hash/read ever happened; external
    callers must never trust a deserialized receipt as source-rights or
    scientific certification -- only ``verify_pdf_model_claims`` performs a
    real check."""

    fake_claims = (
        ClaimDiagnostic(
            index=0, code="EXACT_QUOTE", page=1,
            page_text_sha256="a" * 64, excerpt_sha256="b" * 64, offset=0,
        ),
        ClaimDiagnostic(
            index=1, code="EXACT_QUOTE", page=1,
            page_text_sha256="a" * 64, excerpt_sha256="c" * 64, offset=5,
        ),
    )
    forged = ModelQuoteGateReceipt(
        status="EXACT_PDF_PAGE_EXCERPTS_VERIFIED", code="ALL_EXCERPTS_EXACT",
        response_sha256="d" * 64, method_id="never-actually-ran",
        run_scope="SYNTHETIC_QA", source_id="not-the-real-source",
        source_version="v999", pdf_sha256="e" * 64,
        source_access_full_receipt_sha256="f" * 64, claims=fake_claims,
    )
    assert forged.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert forged.pdf_sha256 == "e" * 64
    assert forged.real_model_identity == "NOT_INDEPENDENTLY_ATTESTED"
    assert forged.scientific_acceptance == "NOT_ASSERTED"


def test_redacted_view_hides_hashes_offsets_and_source_identity() -> None:
    """E: redacted_view() must drop every carrier ID, hash, page and offset,
    on both a positive and a negative outcome."""

    positive = _run(_candidate())
    assert positive.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    summary = positive.redacted_view()
    dumped = summary.model_dump_json()
    assert not _HEX64.search(dumped)
    assert "invented-pdf" not in dumped
    assert "Harbor clock" not in dumped
    assert summary.claim_count == 2
    assert summary.exact_quote_count == 2
    assert "method_id" not in dumped
    assert summary.source_provenance == "SELF_OBSERVED_UNATTESTED"

    bad_candidate = _candidate()
    bad_candidate["evidence"][0]["excerpt"] = "this text does not exist anywhere"
    negative = _run(bad_candidate)
    assert negative.status == "REJECTED"
    neg_dumped = negative.redacted_view().model_dump_json()
    assert not _HEX64.search(neg_dumped)
    assert "invented-pdf" not in neg_dumped


@pytest.mark.parametrize("count", [1, 13])
def test_evidence_length_bounds_enforced(count: int) -> None:
    """F: fewer than 2 or more than 12 evidence items is a schema violation."""

    candidate = _candidate()
    base = candidate["evidence"][0]
    candidate["evidence"] = [dict(base, claim=f"claim-{i}") for i in range(count)]
    result = _run(candidate)
    assert result.status == "REJECTED"
    assert result.code == "CANDIDATE_SCHEMA_INVALID"


def test_non_utf8_response_bytes_rejected_not_crashed() -> None:
    """F: malformed UTF-8 response bytes must be a typed rejection."""

    payload = b'{"schema": "seshat.pdf_claims.v1", \xff invalid}'
    result = verify_pdf_model_claims(
        access=_access(), carrier_id="invented-pdf", response_json=payload
    )
    assert result.status == "REJECTED"
    assert result.code == "CANDIDATE_SCHEMA_INVALID"


def test_non_object_json_root_rejected() -> None:
    """F: a JSON array/scalar root instead of an object is a typed rejection."""

    payload = json.dumps([1, 2, 3]).encode()
    result = verify_pdf_model_claims(
        access=_access(), carrier_id="invented-pdf", response_json=payload
    )
    assert result.status == "REJECTED"
    assert result.code == "CANDIDATE_SCHEMA_INVALID"


class _SpoofedRuntimeSourceAccess(RuntimeSourceAccess):
    """A subclass used only to prove isinstance-style spoofing is rejected."""


def test_source_access_subclass_spoof_rejected() -> None:
    """F: a RuntimeSourceAccess subclass must not pass the exact-type gate."""

    digest = hashlib.sha256(PDF_ONE).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented-pdf", source_identity="invented-only", version="v1",
        media_type="application/pdf", content_sha256=digest, byte_length=len(PDF_ONE),
    )
    content = SourceContent(
        carrier_id="invented-pdf", source_version="v1", media_type="application/pdf",
        content=PDF_ONE, content_sha256=digest, byte_length=len(PDF_ONE),
        complete=True, authorized=True,
    )
    spoofed = _SpoofedRuntimeSourceAccess(
        RawAccessPolicy.FULL_REQUIRED, (carrier,), _Provider(content), ("invented-pdf",)
    )
    result = _run(_candidate(), spoofed)
    assert result.status == "REJECTED"
    assert result.code == "SOURCE_ACCESS_INVALID"


def test_both_media_types_declared_non_pdf_rejected_as_media_type_required() -> None:
    """F: declared/actual media types agreeing but not being a PDF is distinct
    from a declared/actual mismatch; it must reach the explicit PDF gate."""

    result = _run(
        _candidate(),
        _access(carrier_media_type="text/plain", content_media_type="text/plain"),
    )
    assert result.status == "REJECTED"
    assert result.code == "PDF_MEDIA_TYPE_REQUIRED"


def test_declared_actual_media_type_drift_denied_by_source_access() -> None:
    """F: a declared-vs-actual media type mismatch is an F07 SOURCE_DRIFT
    denial, caught and surfaced as SOURCE_ACCESS_DENIED, never as a silent
    content-sniffed PDF admission."""

    result = _run(
        _candidate(),
        _access(carrier_media_type="application/pdf", content_media_type="text/plain"),
    )
    assert result.status == "REJECTED"
    assert result.code == "SOURCE_ACCESS_DENIED"


def test_schema_field_uses_alias_without_shadowing_basemodel_schema_method() -> None:
    """F: the external JSON key stays exactly "schema" while the Python
    attribute is renamed to schema_id, so the field no longer shadows
    BaseModel.schema()."""

    assert ModelCandidate.model_fields["schema_id"].alias == "schema"
    assert ModelQuoteGateReceipt.model_fields["schema_id"].alias == "schema"

    parsed = ModelCandidate.model_validate(_candidate())
    assert parsed.schema_id == "seshat.pdf_claims.v1"
    dumped = parsed.model_dump(mode="json")
    assert dumped["schema"] == "seshat.pdf_claims.v1"
    assert "schema_id" not in dumped

    receipt = _run(_candidate())
    receipt_dumped = receipt.model_dump(mode="json")
    assert receipt_dumped["schema"] == "seshat.pdf_claims.receipt.v1"
    assert "schema_id" not in receipt_dumped



def test_public_summary_rejects_arbitrary_private_code() -> None:
    """A structurally forged private receipt must not launder model text via code."""
    from pydantic import ValidationError

    forged = _run(_candidate()).model_copy(
        update={"code": "restricted private title or source secret"}
    )
    with pytest.raises(ValidationError):
        forged.redacted_view()


@pytest.mark.parametrize("method_id", [chr(0xD800), "secret paper title", "unsafe;command"])
def test_model_method_tag_cannot_embed_surrogate_or_secret_prose(method_id: str) -> None:
    candidate = _candidate()
    candidate["method_id"] = method_id
    result = _run(candidate)
    assert result.status == "REJECTED"
    assert result.code == "CANDIDATE_SCHEMA_INVALID"
    assert result.method_id is None
    assert "restricted" not in result.redacted_view().model_dump_json()


def test_bounded_model_method_tag_still_passes() -> None:
    candidate = _candidate()
    candidate["method_id"] = "method.schema:42-beta"
    result = _run(candidate)
    assert result.status == "EXACT_PDF_PAGE_EXCERPTS_VERIFIED"
    assert result.method_id == "method.schema:42-beta"
    assert "method.schema:42-beta" not in result.redacted_view().model_dump_json()
