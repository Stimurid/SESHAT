"""Owner-private operator R01/R02 bridge: two worlds and adversarial contracts.

All test inputs are invented. No protected source, network, paid model,
special privilege, or scientifically accepted method is involved.
"""
from __future__ import annotations

import copy
from hashlib import sha256

import pytest

from seshat.fabric_waves.operator_builtin_method import execute_literal_method
from seshat.fabric_waves.operator_local_demo import inputs
from seshat.fabric_waves.operator_methodbody import (
    OperatorRunLedger, invoke_operator_method_body,
)
from seshat.fabric_waves.operator_private_reports import (
    compose_private_operator_r01r02, verify_private_operator_r01r02,
)


def _run(fixture: str):
    source, source_bytes, method, method_bytes = inputs(fixture)
    ledger = OperatorRunLedger()
    receipt = invoke_operator_method_body(
        ledger=ledger,
        run_id=f"bridge-test-{fixture}",
        job_id=f"local-{fixture}",
        source=source, source_bytes=source_bytes,
        method=method, method_body_invocation_bytes=method_bytes,
        method_callable=execute_literal_method,
        requested_view="private-operator",
        declared_model_identity="deterministic-local-no-model",
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )
    return receipt, source_bytes, method_bytes, ledger


@pytest.mark.parametrize("fixture", ["materials", "organization"])
def test_private_r01_r02_two_distinct_real_local_invocations(fixture):
    receipt, source_bytes, method_bytes, ledger = _run(fixture)
    preview = compose_private_operator_r01r02(
        receipt, source_bytes=source_bytes, method_invocation_bytes=method_bytes,
    )
    assert preview["schema"] == "seshat.operator_private_r01r02.v1"
    assert preview["visibility"] == "OWNER_PRIVATE_ONLY"
    assert preview["customer_release"] == "BLOCKED"
    assert preview["scientific_acceptance"] == "NOT_PERFORMED"
    assert preview["model_run_attested"] is False
    assert preview["method_interpretation"] == "PINNED_BYTES_INTERPRETED_BUILTIN"
    r01, r02 = preview["reports"]
    assert (r01["report_id"], r02["report_id"]) == ("R01", "R02")
    assert r01["status"] == "SOURCE_GROUNDED_UNREVIEWED"
    assert r02["status"] == "SOURCE_GROUNDED_UNREVIEWED"
    assert r01["claims"] and r01["claims"][0]["excerpt_sha256"]
    assert r02["output_sediment_id"] == receipt.output_sediment.sediment_id
    assert r02["output_digest"] == receipt.output_digest
    assert any(e["relation"] == "METHOD_CALLED" for e in r02["graph_edges"])
    assert any(e["relation"] == "PRODUCED_PROVISIONAL" for e in r02["graph_edges"])
    verify_private_operator_r01r02(
        copy.deepcopy(preview), ledger.get(receipt.run_id),
        source_bytes=source_bytes, method_invocation_bytes=method_bytes,
    )
    # Projections are deterministic for the same actually completed run.
    assert compose_private_operator_r01r02(
        receipt, source_bytes=source_bytes, method_invocation_bytes=method_bytes
    ) == preview
    # The adapter did not grant real source rights or human acceptance.
    assert receipt.rights_attested == "NO"
    assert receipt.scientific_acceptance == "NOT_ASSERTED"


@pytest.mark.parametrize("fixture", ["materials", "organization"])
def test_bridge_rejects_changed_source_method_or_replayed_projection(fixture):
    receipt, src, method, _ = _run(fixture)
    preview = compose_private_operator_r01r02(
        receipt, source_bytes=src, method_invocation_bytes=method,
    )
    with pytest.raises(ValueError, match="SOURCE_PIN_MISMATCH"):
        compose_private_operator_r01r02(
            receipt, source_bytes=src + b"changed", method_invocation_bytes=method,
        )
    with pytest.raises(ValueError, match="METHOD_PIN_MISMATCH"):
        compose_private_operator_r01r02(
            receipt, source_bytes=src, method_invocation_bytes=method + b"changed",
        )
    forged = copy.deepcopy(preview)
    forged["reports"][0]["claims"][0]["claim_text"] = "This is now scientifically accepted"
    with pytest.raises(ValueError, match="PROJECTION_REPLAY_MISMATCH"):
        verify_private_operator_r01r02(
            forged, receipt, source_bytes=src, method_invocation_bytes=method,
        )
    forged = copy.deepcopy(preview)
    forged["customer_release"] = "AUTHORIZED"
    with pytest.raises(ValueError, match="PROJECTION_REPLAY_MISMATCH"):
        verify_private_operator_r01r02(
            forged, receipt, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_forged_claim_evidence_and_output_checksum():
    receipt, src, method, _ = _run("materials")
    sed = receipt.output_sediment
    forged = copy.deepcopy(sed.payload)
    forged["claims"][0]["byte_offset"] = len(src) + 10
    tampered = receipt.model_copy(
        update={"output_sediment": sed.model_copy(update={"payload": forged}, deep=True)},
        deep=True,
    )
    with pytest.raises(ValueError, match="SEDIMENT_PAYLOAD_CHANGED"):
        compose_private_operator_r01r02(
            tampered, source_bytes=src, method_invocation_bytes=method,
        )
    tampered = receipt.model_copy(update={"output_digest": "0" * 64}, deep=True)
    with pytest.raises(ValueError, match="OUTPUT_RECEIPT_CHANGED"):
        compose_private_operator_r01r02(
            tampered, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_non_source_anchored_page_or_granted_acceptance():
    receipt, src, method, _ = _run("organization")
    sed = receipt.output_sediment
    new_claims = copy.deepcopy(sed.payload)
    new_claims["claims"][0]["page"] = 7
    from seshat.fabric_waves.sediment import payload_hash
    new_digest = payload_hash(new_claims)
    altered = sed.model_copy(update={
        "payload": new_claims, "payload_hash": new_digest, "version": new_digest,
    }, deep=True)
    new_output_digest = sha256(
        f"{new_digest}:{receipt.invocation.stdout_sha256}".encode("utf-8")
    ).hexdigest()
    page_forged = receipt.model_copy(
        update={"output_sediment": altered, "output_digest": new_output_digest},
        deep=True,
    )
    with pytest.raises(ValueError, match="BAD_CLAIM"):
        compose_private_operator_r01r02(
            page_forged, source_bytes=src, method_invocation_bytes=method,
        )
    accepted = sed.model_copy(update={"acceptance_state": "ACCEPTED"}, deep=True)
    tampered = receipt.model_copy(update={"output_sediment": accepted}, deep=True)
    with pytest.raises(ValueError, match="INVALID_SEDIMENT_BINDING"):
        compose_private_operator_r01r02(
            tampered, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_fake_f07_manifest_or_swapped_source_identity():
    receipt, src, method, _ = _run("materials")
    read = receipt.source_access_manifest.receipts[0]
    altered_read = read.model_copy(update={"content_sha256": "0" * 64}, deep=True)
    manifest = receipt.source_access_manifest.model_copy(
        update={"receipts": [altered_read]}, deep=True
    )
    forged = receipt.model_copy(update={"source_access_manifest": manifest}, deep=True)
    with pytest.raises(ValueError, match="F07_INCOMPLETE"):
        compose_private_operator_r01r02(
            forged, source_bytes=src, method_invocation_bytes=method,
        )
    swapped = receipt.model_copy(update={"source_id": "other-carrier"}, deep=True)
    with pytest.raises(ValueError, match="INVALID_SEDIMENT_BINDING"):
        compose_private_operator_r01r02(
            swapped, source_bytes=src, method_invocation_bytes=method,
        )
