"""F07/F08 public-article admission: two different, wholly invented test PDFs.

Real published bytes are intentionally absent from this public Git test suite.
"""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import hashlib

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from seshat.pdf_page_evidence import PageExcerptQuery
from seshat.public_source_admission import (
    PublicArticlePin, PublicArticleRequest, PublicSourceAdmissionError,
    admit_public_published_corpus,
)


def make_pdf(doi: str, text: str, *, lic: bool = True) -> bytes:
    writer = PdfWriter()
    for content in [
        f"PLOS ONE https://doi.org/{doi} "
        + ("Creative Commons Attribution License " if lic else "All rights reserved ")
        + "Article rights in printed published paper",
        text,
    ]:
        page = writer.add_blank_page(width=300, height=300)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 260 Td ({content}) Tj ET".encode("latin-1"))
        stream_ref = writer._add_object(stream)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        })
        page[NameObject("/Contents")] = stream_ref
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


DOI_A = "10.1371/journal.pone.0293107"
DOI_B = "10.1371/journal.pone.0297542"
A = make_pdf(DOI_A, "Researchers interviewed twenty participants from workplace A.")
B = make_pdf(DOI_B, "Observers documented discharge pathways in workplace B.")


def record(doi: str, raw: bytes, ident: str, excerpt: str) -> PublicArticleRequest:
    page2 = PdfReader(BytesIO(raw)).pages[1].extract_text()
    assert excerpt in page2
    return PublicArticleRequest(
        pin=PublicArticlePin(
            carrier_id=ident, doi=doi,
            publisher_article_url="https://journals.plos.org/plosone/article?id=" + doi,
            version="sha256:" + hashlib.sha256(raw).hexdigest(),
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw), operator_license_review_id="operator-cc-by-m8",
            attribution="Invented F07 test source under CC BY",
        ),
        evidence=(PageExcerptQuery(page_number=2, expected_excerpt=excerpt),),
    )


def sample():
    a = record(DOI_A, A, "pub-a", "Researchers interviewed twenty participants")
    b = record(DOI_B, B, "pub-b", "Observers documented discharge pathways")
    return (a, b), {"pub-a": A, "pub-b": B}


def test_two_distinct_public_works_admit_f07_f08_and_never_grant_science():
    requests, sources = sample()
    result = admit_public_published_corpus(requests, source_bytes=sources)
    assert len(result.articles) == 2
    assert result.customer_release == "BLOCKED"
    assert result.independent_owner_or_issuer_rights_attestation == "NO"
    assert result.public_rights_review == "OPERATOR_REVIEWED_ONLY"
    assert all(r.rights_independently_attested == "NO" for r in result.articles)
    assert all(r.scientific_acceptance == "NOT_ASSERTED" for r in result.articles)
    assert all(len(r.f08_page_evidence) == 1 for r in result.articles)
    assert all(r.f08_page_evidence[0].rights_independently_attested == "NO" for r in result.articles)
    assert all(r.f08_page_evidence[0].page_count == 2 for r in result.articles)


@pytest.mark.parametrize("part", ["sha", "size", "version", "license_review", "rights_scope"])
def test_modified_operator_manifest_fails_closed(part):
    reqs, sources = sample()
    old = reqs[0].pin
    updates = {
        "sha": {"sha256": "0" * 64},
        "size": {"byte_length": old.byte_length + 1},
        "version": {"version": ""},
        "license_review": {"operator_license_review_id": " "},
        "rights_scope": {"view": "PRIVATE_INTERVIEW_TRANSCRIPTS"},
    }
    reqs = (replace(reqs[0], pin=replace(old, **updates[part])), reqs[1])
    with pytest.raises(PublicSourceAdmissionError):
        admit_public_published_corpus(reqs, source_bytes=sources)


def test_wrong_or_missing_article_pdf_fails_atomically():
    reqs, sources = sample()
    with pytest.raises(PublicSourceAdmissionError, match="SOURCE_SET_MISMATCH"):
        admit_public_published_corpus(reqs, source_bytes={"pub-a": A})
    with pytest.raises(PublicSourceAdmissionError, match="SOURCE_BYTES_DRIFT"):
        admit_public_published_corpus(reqs, source_bytes={"pub-a": B, "pub-b": B})


@pytest.mark.parametrize("mode", ["duplicate_id", "duplicate_doi", "duplicate_digest", "one_source"])
def test_deduplication_and_multi_source_obligation(mode):
    reqs, sources = sample()
    if mode == "one_source":
        args = (reqs[0],)
    elif mode == "duplicate_id":
        args = (reqs[0], replace(reqs[1], pin=replace(reqs[1].pin, carrier_id="pub-a")))
    elif mode == "duplicate_doi":
        args = (reqs[0], replace(reqs[1], pin=replace(reqs[1].pin, doi=DOI_A)))
    else:
        args = (reqs[0], replace(reqs[1], pin=replace(reqs[1].pin, sha256=reqs[0].pin.sha256)))
    with pytest.raises(PublicSourceAdmissionError):
        admit_public_published_corpus(args, source_bytes=sources)


@pytest.mark.parametrize("mutant", ["wrong_page", "fabricated_quote", "ambiguous_span", "no_evidence"])
def test_f08_page_witness_mutation_fails_whole_corpus(mutant):
    reqs, sources = sample()
    if mutant == "wrong_page":
        ev = (PageExcerptQuery(page_number=1, expected_excerpt="Researchers interviewed"),)
    elif mutant == "fabricated_quote":
        ev = (PageExcerptQuery(page_number=2, expected_excerpt="Invented interview result is true"),)
    elif mutant == "ambiguous_span":
        ev = (PageExcerptQuery(page_number=2, expected_excerpt="workplace A."), PageExcerptQuery(page_number=0, expected_excerpt="something"))
    else:
        ev = ()
    reqs = (replace(reqs[0], evidence=ev), reqs[1])
    with pytest.raises(PublicSourceAdmissionError):
        admit_public_published_corpus(reqs, source_bytes=sources)


def test_publisher_license_absence_rejected_even_with_operator_claim():
    raw = make_pdf(DOI_A, "Researchers interviewed twenty participants from workplace A.", lic=False)
    reqs, sources = sample()
    first = record(DOI_A, raw, "pub-a", "Researchers interviewed twenty participants")
    with pytest.raises(PublicSourceAdmissionError, match="LICENSE_WITNESS_ABSENT"):
        admit_public_published_corpus((first, reqs[1]), source_bytes={"pub-a": raw, "pub-b": B})


def test_false_publisher_domain_and_doi_not_admitted():
    reqs, sources = sample()
    bad = replace(reqs[0].pin, publisher_article_url="https://journals.plos.org.evil.example/plosone/article?id="+DOI_A)
    with pytest.raises(PublicSourceAdmissionError, match="PUBLISHER_ORIGIN"):
        admit_public_published_corpus((replace(reqs[0], pin=bad), reqs[1]), source_bytes=sources)


def test_no_independent_rights_or_human_approval_even_from_mutated_payload():
    reqs, sources = sample()
    r = admit_public_published_corpus(reqs, source_bytes=sources)
    with pytest.raises(Exception):
        r.model_copy(update={"customer_release": "ACCEPTED"}).model_validate(
            r.model_copy(update={"customer_release": "ACCEPTED"}).model_dump()
        )
    # Direct model reconstruction validates our pinned Literal contracts on rights.
    from seshat.public_source_admission import AdmittedPublicArticle
    item = r.articles[0].model_dump()
    item["rights_independently_attested"] = "YES"
    with pytest.raises(Exception):
        AdmittedPublicArticle.model_validate(item)

def test_private_readback_revalidates_full_original_f07_and_f08():
    from seshat.public_source_admission import replay_and_verify_public_corpus
    reqs, sources = sample()
    expected = admit_public_published_corpus(reqs, source_bytes=sources)
    replayed = replay_and_verify_public_corpus(expected, reqs, source_bytes=sources)
    assert replayed == expected
    assert replayed.customer_release == "BLOCKED"
    assert all(a.rights_independently_attested == "NO" for a in replayed.articles)


def test_private_readback_refuses_pydantic_model_copy_forged_human_acceptance():
    from seshat.public_source_admission import replay_and_verify_public_corpus
    reqs, sources = sample()
    packet = admit_public_published_corpus(reqs, source_bytes=sources)
    forged = packet.model_copy(update={"customer_release": "ACCEPTED"})
    with pytest.raises(PublicSourceAdmissionError, match="PACKET_SCHEMA_INVALID"):
        replay_and_verify_public_corpus(forged, reqs, source_bytes=sources)
    item = packet.articles[0].model_copy(update={"rights_independently_attested": "YES"})
    forged = packet.model_copy(update={"articles": (item, packet.articles[1])})
    with pytest.raises(PublicSourceAdmissionError, match="PACKET_SCHEMA_INVALID"):
        replay_and_verify_public_corpus(forged, reqs, source_bytes=sources)


def test_private_readback_refuses_structurally_valid_false_page_receipt():
    from seshat.public_source_admission import replay_and_verify_public_corpus
    reqs, sources = sample()
    packet = admit_public_published_corpus(reqs, source_bytes=sources)
    old = packet.articles[0]
    fake_quote = old.f08_page_evidence[0].model_copy(update={"excerpt_sha256": "0" * 64})
    forged_article = old.model_copy(update={"f08_page_evidence": (fake_quote,)})
    forged = packet.model_copy(update={"articles": (forged_article, packet.articles[1])})
    with pytest.raises(PublicSourceAdmissionError, match="RECEIPT_DRIFT"):
        replay_and_verify_public_corpus(forged, reqs, source_bytes=sources)


def test_private_readback_refuses_drifted_source_and_manifest():
    from seshat.public_source_admission import replay_and_verify_public_corpus
    reqs, sources = sample()
    packet = admit_public_published_corpus(reqs, source_bytes=sources)
    with pytest.raises(PublicSourceAdmissionError, match="SOURCE_BYTES_DRIFT"):
        replay_and_verify_public_corpus(
            packet, reqs, source_bytes={**sources, "pub-b": sources["pub-b"][:-1]},
        )
    reqs2 = (
        replace(reqs[0], pin=replace(reqs[0].pin, operator_license_review_id="different-review")),
        reqs[1],
    )
    with pytest.raises(PublicSourceAdmissionError, match="RECEIPT_DRIFT"):
        replay_and_verify_public_corpus(packet, reqs2, source_bytes=sources)
