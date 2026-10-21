"""Invented in-memory PDF QA for the atomic model quote gate."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.pdf_claims import verify_pdf_model_claims
from seshat.runtime import RuntimeSourceAccess


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
) -> RuntimeSourceAccess:
    digest = hashlib.sha256(data).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented-pdf", source_identity="invented-only", version="v1",
        media_type="application/pdf", content_sha256=digest, byte_length=len(data),
    )
    content = SourceContent(
        carrier_id="invented-pdf", source_version="v1", media_type="application/pdf",
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
