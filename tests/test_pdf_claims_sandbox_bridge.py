"""Issue #73 seam: the claim gate routed through the ephemeral sandbox.

No real PDF and no Docker daemon are required: the sandbox checker is
injected. What is asserted is the *bridge's* contract — atomicity, zero
side effects on an invalid source, no host-parser fallback, and the
child's claim staying unattested.
"""

import hashlib
import json

import pytest

from seshat.pdf_claims_sandbox_bridge import (
    PublicSandboxQuoteSummary,
    SandboxedModelQuoteGateReceipt,
    verify_pdf_model_claims_sandboxed,
)
from seshat.pdf_sandbox import PdfSandboxError, SandboxQuoteObservation

CARRIER = "synthetic-pdf-carrier"
VERSION = "v1"
PDF_BYTES = b"%PDF-1.4 synthetic bridge fixture"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()
RECEIPT_SHA = "b" * 64


def candidate_json(pages=(1, 2), *, source_id=CARRIER, source_version=VERSION) -> bytes:
    return json.dumps(
        {
            "schema": "seshat.pdf_claims.v1",
            "method_id": "synthetic.bridge",
            "source_id": source_id,
            "source_version": source_version,
            "run_scope": "SYNTHETIC_QA",
            "evidence": [
                {
                    "claim": f"synthetic claim {page}",
                    "page": page,
                    "excerpt": f"synthetic excerpt {page}",
                    "kind": "SOURCE_STATED",
                }
                for page in pages
            ],
            "unknowns": ["everything semantic"],
            "rights_independently_attested": "NO",
            "scientific_acceptance": "NOT_ASSERTED",
            "customer_release": "NOT_AUTHORIZED",
        }
    ).encode("utf-8")


class _FakeAccess:
    """Stands in for RuntimeSourceAccess; the bridge type-checks the real one."""


@pytest.fixture()
def admitted(monkeypatch):
    """Patch the shared admission so no real PDF or F07 provider is needed."""

    import seshat.pdf_claims_sandbox_bridge as bridge
    from seshat.pdf_claims import _AdmittedSource, ModelCandidate

    calls = {"count": 0}

    def fake_parse_and_admit(*, access, carrier_id, response_json, response_digest, tags):
        raw = json.loads(response_json.decode("utf-8"))
        candidate = ModelCandidate.model_validate(raw)
        tags["method_id"] = candidate.method_id
        tags["run_scope"] = candidate.run_scope
        if candidate.source_id != carrier_id or getattr(access, "denied", False):
            from seshat.pdf_claims import _reject_fn

            return _reject_fn(response_digest, tags)("SOURCE_ID_MISMATCH"), None
        return None, _AdmittedSource(
            candidate=candidate,
            pdf_bytes=PDF_BYTES,
            version=VERSION,
            pdf_digest=PDF_SHA,
            source_receipt=object(),
            source_receipt_digest=RECEIPT_SHA,
            pins=dict(
                source_id=carrier_id,
                source_version=VERSION,
                pdf_sha256=PDF_SHA,
                source_access_full_receipt_sha256=RECEIPT_SHA,
            ),
        )

    monkeypatch.setattr(bridge, "_parse_and_admit", fake_parse_and_admit)
    return calls


def observation(page: int, *, excerpt: str = "x") -> SandboxQuoteObservation:
    return SandboxQuoteObservation(
        carrier_id=CARRIER,
        source_version=VERSION,
        source_access_full_receipt_sha256=RECEIPT_SHA,
        pdf_sha256=PDF_SHA,
        pdf_byte_length=len(PDF_BYTES),
        page_number=page,
        excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
    )


def test_all_quotes_reported_stays_unattested(admitted):
    calls = []

    def checker(access, carrier_id, *, page_number, expected_excerpt, image, timeout_seconds):
        calls.append(page_number)
        return observation(page_number)

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert isinstance(receipt, SandboxedModelQuoteGateReceipt)
    assert receipt.status == "CHILD_REPORTED_MATCH_UNATTESTED"
    assert receipt.code == "ALL_EXCERPTS_CHILD_REPORTED"
    assert calls == [1, 2]
    assert receipt.sandbox_invocations == 2
    # The strong words stay off.
    assert receipt.rights_independently_attested == "NO"
    assert receipt.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.customer_release == "NOT_AUTHORIZED"
    assert receipt.semantic_entailment == "NOT_ASSESSED"
    assert receipt.extraction_locus == "EPHEMERAL_OS_SANDBOX_CHILD"
    assert receipt.host_parser_fallback_used == "NEVER"


def test_there_is_no_verified_status_in_the_vocabulary():
    import typing

    from seshat.pdf_claims_sandbox_bridge import SandboxedModelQuoteGateReceipt as R

    allowed = typing.get_args(R.model_fields["status"].annotation)
    assert set(allowed) == {"REJECTED", "CHILD_REPORTED_MATCH_UNATTESTED"}


def test_two_of_four_failures_reject_the_whole_response(admitted):
    def checker(access, carrier_id, *, page_number, expected_excerpt, image, timeout_seconds):
        if page_number in (2, 4):
            raise PdfSandboxError("NOT_VERIFIED")
        return observation(page_number)

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(pages=(1, 2, 3, 4)),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert receipt.status == "REJECTED"
    assert receipt.code == "CLAIM_EVIDENCE_FAILED"
    # Zero quotes are accepted, including the two the child did report.
    accepted = [d for d in receipt.claims if d.code == "CHILD_REPORTED_MATCH_UNATTESTED"]
    assert len(accepted) == 2
    assert receipt.redacted_view().status == "REJECTED"
    assert len(receipt.claims) == 4


def test_an_invalid_source_never_reaches_the_sandbox(admitted):
    calls = []

    def checker(*args, **kwargs):
        calls.append(1)
        raise AssertionError("the sandbox must not be invoked")

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(source_id="a-different-source"),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert receipt.status == "REJECTED"
    assert receipt.code == "SOURCE_ID_MISMATCH"
    assert calls == []
    assert receipt.sandbox_invocations == 0


def test_an_unavailable_sandbox_does_not_fall_back_to_the_host_parser(admitted):
    def checker(*args, **kwargs):
        raise PdfSandboxError("UNSUPPORTED_SANDBOX")

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert receipt.status == "REJECTED"
    assert receipt.code == "SANDBOX_UNAVAILABLE"
    assert all(d.code == "SANDBOX_UNSUPPORTED_SANDBOX" for d in receipt.claims)
    assert receipt.host_parser_fallback_used == "NEVER"


def test_a_child_answer_pinned_to_the_wrong_source_is_refused(admitted):
    def checker(access, carrier_id, *, page_number, expected_excerpt, image, timeout_seconds):
        return observation(page_number).model_copy(update={"pdf_sha256": "c" * 64})

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert receipt.status == "REJECTED"
    assert {d.code for d in receipt.claims} == {"SANDBOX_PIN_MISMATCH"}


def test_a_child_answering_the_wrong_page_is_refused(admitted):
    def checker(access, carrier_id, *, page_number, expected_excerpt, image, timeout_seconds):
        return observation(99)

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(),
        image="synthetic:test",
        sandbox_check=checker,
    )
    assert receipt.status == "REJECTED"
    assert {d.code for d in receipt.claims} == {"SANDBOX_PIN_MISMATCH"}


def test_public_projection_carries_no_fingerprints(admitted):
    def checker(access, carrier_id, *, page_number, expected_excerpt, image, timeout_seconds):
        return observation(page_number)

    receipt = verify_pdf_model_claims_sandboxed(
        access=_FakeAccess(),
        carrier_id=CARRIER,
        response_json=candidate_json(),
        image="synthetic:test",
        sandbox_check=checker,
    )
    public = receipt.redacted_view()
    assert isinstance(public, PublicSandboxQuoteSummary)
    blob = public.model_dump_json()
    assert CARRIER not in blob
    assert PDF_SHA not in blob
    assert RECEIPT_SHA not in blob
    assert "synthetic excerpt" not in blob
    assert public.child_reported_match_count == 2
    assert public.child_observation_provenance == "CHILD_ASSERTED_UNATTESTED"
    # The private receipt, by contrast, does carry the pins it must retain.
    assert CARRIER in receipt.model_dump_json()


def test_response_must_be_exact_bytes():
    with pytest.raises(TypeError):
        verify_pdf_model_claims_sandboxed(
            access=_FakeAccess(),
            carrier_id=CARRIER,
            response_json="not bytes",  # type: ignore[arg-type]
            image="synthetic:test",
        )


def test_no_hardcoded_real_source_in_the_bridge():
    import re
    from pathlib import Path

    source = Path(
        __file__
    ).resolve().parents[1] / "src" / "seshat" / "pdf_claims_sandbox_bridge.py"
    text = source.read_text(encoding="utf-8")
    # Module names may contain ``pdf``; forbid literal filesystem/URL sources.
    assert re.search(r"""['"][^'"]+\.pdf['"]""", text) is None
    assert "http://" not in text and "https://" not in text
