"""Independent bridge tests using invented in-memory public PDF fixtures."""
from __future__ import annotations

import hashlib

import pytest

from test_public_source_admission import sample
from seshat.public_source_admission import admit_public_published_corpus
from seshat.public_pdf_method_bridge import (
    PublicPdfMethodBridgeError, make_public_pdf_method_views,
)
from seshat.fabric_waves.operator_methodbody import (
    OperatorRunLedger, OperatorMethodBodyPin,
    OperatorClaim, OperatorBodyResult, invoke_operator_method_body,
)


def setup():
    reqs, source_bytes = sample()
    packet = admit_public_published_corpus(reqs, source_bytes=source_bytes)
    return packet, reqs, source_bytes


def views(packet, reqs, src, **overrides):
    return make_public_pdf_method_views(
        packet, reqs, source_bytes=src,
        owner_excluded_source_ids=overrides.get("ids", frozenset()),
        owner_excluded_source_sha256=overrides.get("digests", frozenset()),
    )


def test_two_original_pdf_sources_become_distinct_full_text_operator_pins():
    packet, requests, raw = setup()
    result = views(packet, requests, raw)
    assert len(result) == 2
    assert {r.original_source_id for r in result} == {"pub-a", "pub-b"}
    for v in result:
        assert v.pdf_page_count == 2
        assert len(v.page_text_sha256) == 2
        assert v.original_page_evidence_count == 1
        assert v.original_pdf_sha256 == packet.articles[
            0 if v.original_source_id == "pub-a" else 1
        ].pdf_sha256
        assert hashlib.sha256(v.source_utf8).hexdigest() == v.source_pin.sha256
        assert v.original_pdf_sha256 != v.source_pin.sha256
        assert v.source_pin.authorized_view == "owner-private-published-page-text"
        assert "=== ORIGINAL PDF PAGE 1 / 2" in v.source_utf8.decode("utf-8")
        assert "=== ORIGINAL PDF PAGE 2 / 2" in v.source_utf8.decode("utf-8")
        assert v.model_run == "NOT_RUN"
        assert v.customer_release == "BLOCKED"
    assert views(packet, requests, raw) == result


@pytest.mark.parametrize("kind", ["missing_policy_ids", "missing_policy_hashes", "invalid_hash"])
def test_no_silent_owner_exclusion_policy_default(kind):
    packet, requests, raw = setup()
    kwargs = {"ids": frozenset(), "digests": frozenset()}
    if kind == "missing_policy_ids":
        kwargs["ids"] = None
    elif kind == "missing_policy_hashes":
        kwargs["digests"] = None
    else:
        kwargs["digests"] = frozenset({"not-a-sha"})
    with pytest.raises(PublicPdfMethodBridgeError, match="OWNER_POLICY"):
        views(packet, requests, raw, **kwargs)


@pytest.mark.parametrize("kind", ["carrier_id", "doi", "original_sha", "derived_view_sha"])
def test_owner_exclusion_blocks_renamed_original_and_derived_material(kind):
    packet, requests, raw = setup()
    initial = views(packet, requests, raw)
    if kind == "carrier_id":
        kwargs = {"ids": frozenset({"PuB-A"})}
    elif kind == "doi":
        kwargs = {"ids": frozenset({requests[0].pin.doi.upper()})}
    elif kind == "original_sha":
        kwargs = {"digests": frozenset({requests[0].pin.sha256})}
    else:
        kwargs = {"digests": frozenset({initial[0].source_pin.sha256})}
    with pytest.raises(PublicPdfMethodBridgeError, match="SOURCE_EXCLUDED"):
        views(packet, requests, raw, **kwargs)


def test_any_tampered_pdf_aborts_both_derived_method_views():
    packet, requests, raw = setup()
    with pytest.raises(PublicPdfMethodBridgeError, match="SOURCE_ADMISSION_FAILED"):
        views(packet, requests, {"pub-a": raw["pub-a"], "pub-b": raw["pub-b"][:-1]})


def test_forged_accepted_packet_does_not_create_method_input():
    packet, requests, raw = setup()
    forged = packet.model_copy(update={"customer_release": "ACCEPTED"})
    with pytest.raises(PublicPdfMethodBridgeError, match="SOURCE_ADMISSION_FAILED"):
        views(forged, requests, raw)


def test_real_operator_callable_can_consume_derived_page_input_without_faking_model_run():
    packet, requests, raw = setup()
    item = views(packet, requests, raw)[0]
    private_method_bytes = b"INVENTED local callback; NOT authorial W01 or W06"
    method = OperatorMethodBodyPin(
        method_body_id="PUBLIC_BRIDGE_LOCAL_TEST_ONLY",
        version="v0",
        invocation_body_sha256=hashlib.sha256(private_method_bytes).hexdigest(),
    )

    def operate(invocation):
        assert invocation.source_text.startswith("=== ORIGINAL PDF PAGE 1 / 2")
        excerpt = "Researchers interviewed twenty participants"
        index = invocation.source_bytes.index(excerpt.encode("utf-8"))
        return OperatorBodyResult(
            research_object_id="invented-test-study",
            claims=(OperatorClaim(
                text="A reported interview is present in this invented test PDF",
                evidence_excerpt=excerpt,
                byte_offset=index,
                byte_length=len(excerpt.encode("utf-8")),
            ),),
        )

    receipt = invoke_operator_method_body(
        ledger=OperatorRunLedger(), run_id="bridge-real-local-operation-test",
        job_id="local-not-a-provider-run",
        source=item.source_pin,
        source_bytes=item.source_utf8,
        method=method,
        method_body_invocation_bytes=private_method_bytes,
        method_callable=operate,
        requested_view="owner-private-published-page-text",
        declared_model_identity="LOCAL_NON_MODEL_TEST_ONLY",
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )
    assert receipt.invocation.exit_status == "OK"
    assert receipt.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.rights_attested == "NO"
    assert receipt.model_run_attested == "NO"
