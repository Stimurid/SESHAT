"""Owner-private operator R01/R02 bridge: two worlds and adversarial contracts.

All test inputs are invented. No protected source, network, paid model,
special privilege, or scientifically accepted method is involved.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from hashlib import sha256

import pytest

from seshat.fabric_waves.contracts import EpistemicLevel
from seshat.fabric_waves.operator_builtin_method import execute_literal_method
from seshat.fabric_waves.operator_local_demo import inputs
from seshat.fabric_waves.operator_methodbody import (
    OperatorRunLedger, OperatorRunReceipt, invoke_operator_method_body,
)
from seshat.fabric_waves.operator_private_reports import (
    compose_private_operator_r01r02, verify_private_operator_r01r02,
)
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger


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
        receipt, ledger=ledger, source_bytes=source_bytes,
        method_invocation_bytes=method_bytes,
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
        copy.deepcopy(preview), ledger.get(receipt.run_id), ledger=ledger,
        source_bytes=source_bytes, method_invocation_bytes=method_bytes,
    )
    # Projections are deterministic for the same actually completed run.
    assert compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=source_bytes,
        method_invocation_bytes=method_bytes,
    ) == preview
    # The adapter did not grant real source rights or human acceptance.
    assert receipt.rights_attested == "NO"
    assert receipt.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.source_access_manifest == receipt.output_sediment.source_access_manifest
    assert receipt.provenance == "SELF_OBSERVED_UNATTESTED"


@pytest.mark.parametrize("fixture", ["materials", "organization"])
def test_bridge_rejects_changed_source_method_or_replayed_projection(fixture):
    receipt, src, method, ledger = _run(fixture)
    preview = compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
    )
    with pytest.raises(ValueError, match="SOURCE_PIN_MISMATCH"):
        compose_private_operator_r01r02(
            receipt, ledger=ledger, source_bytes=src + b"changed",
            method_invocation_bytes=method,
        )
    with pytest.raises(ValueError, match="METHOD_PIN_MISMATCH"):
        compose_private_operator_r01r02(
            receipt, ledger=ledger, source_bytes=src,
            method_invocation_bytes=method + b"changed",
        )
    forged = copy.deepcopy(preview)
    forged["reports"][0]["claims"][0]["claim_text"] = "This is now scientifically accepted"
    with pytest.raises(ValueError, match="PROJECTION_REPLAY_MISMATCH"):
        verify_private_operator_r01r02(
            forged, receipt, ledger=ledger, source_bytes=src,
            method_invocation_bytes=method,
        )
    forged = copy.deepcopy(preview)
    forged["customer_release"] = "AUTHORIZED"
    with pytest.raises(ValueError, match="PROJECTION_REPLAY_MISMATCH"):
        verify_private_operator_r01r02(
            forged, receipt, ledger=ledger, source_bytes=src,
            method_invocation_bytes=method,
        )
    forged = copy.deepcopy(preview)
    forged["scientific_acceptance"] = "HUMAN_APPROVED"
    with pytest.raises(ValueError, match="PROJECTION_REPLAY_MISMATCH"):
        verify_private_operator_r01r02(
            forged, receipt, ledger=ledger, source_bytes=src,
            method_invocation_bytes=method,
        )


def test_bridge_rejects_forged_claim_evidence_and_output_checksum():
    receipt, src, method, ledger = _run("materials")
    sed = receipt.output_sediment
    forged = copy.deepcopy(sed.payload)
    forged["claims"][0]["byte_offset"] = len(src) + 10
    tampered = receipt.model_copy(
        update={"output_sediment": sed.model_copy(update={"payload": forged}, deep=True)},
        deep=True,
    )
    with pytest.raises(ValueError, match="SEDIMENT_PAYLOAD_CHANGED"):
        compose_private_operator_r01r02(
            tampered, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )
    tampered = receipt.model_copy(update={"output_digest": "0" * 64}, deep=True)
    with pytest.raises(ValueError, match="OUTPUT_RECEIPT_CHANGED"):
        compose_private_operator_r01r02(
            tampered, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_non_source_anchored_page_or_granted_acceptance():
    receipt, src, method, ledger = _run("organization")
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
            page_forged, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )
    accepted = sed.model_copy(update={"acceptance_state": "ACCEPTED"}, deep=True)
    tampered = receipt.model_copy(update={"output_sediment": accepted}, deep=True)
    with pytest.raises(ValueError, match="INVALID_SEDIMENT_BINDING"):
        compose_private_operator_r01r02(
            tampered, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )
    e5 = sed.model_copy(update={"epistemic_level": EpistemicLevel.E5}, deep=True)
    tampered = receipt.model_copy(update={"output_sediment": e5}, deep=True)
    with pytest.raises(ValueError, match="INVALID_SEDIMENT_BINDING"):
        compose_private_operator_r01r02(
            tampered, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_fake_f07_manifest_or_swapped_source_identity():
    receipt, src, method, ledger = _run("materials")
    read = receipt.source_access_manifest.receipts[0]
    altered_read = read.model_copy(update={"content_sha256": "0" * 64}, deep=True)
    manifest = receipt.source_access_manifest.model_copy(
        update={"receipts": [altered_read]}, deep=True
    )
    forged = receipt.model_copy(update={"source_access_manifest": manifest}, deep=True)
    with pytest.raises(ValueError, match="F07_INCOMPLETE"):
        compose_private_operator_r01r02(
            forged, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )
    swapped = receipt.model_copy(update={"source_id": "other-carrier"}, deep=True)
    with pytest.raises(ValueError, match="INVALID_SEDIMENT_BINDING"):
        compose_private_operator_r01r02(
            swapped, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_divergent_or_missing_sediment_f07_manifest():
    """Top-level F07 must equal sediment F07; None or identity swaps fail closed."""
    receipt, src, method, ledger = _run("organization")
    assert receipt.source_access_manifest == receipt.output_sediment.source_access_manifest
    compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
    )

    missing = receipt.model_copy(update={
        "output_sediment": receipt.output_sediment.model_copy(
            update={"source_access_manifest": None}, deep=True,
        )
    }, deep=True)
    with pytest.raises(ValueError, match="F07_INCOMPLETE"):
        compose_private_operator_r01r02(
            missing, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )

    swapped_read = receipt.source_access_manifest.receipts[0].model_copy(update={
        "carrier_id": "invented-swapped-carrier",
        "source_version": "invented-swapped-v9",
        "content_sha256": "ab" * 32,
    }, deep=True)
    swapped_manifest = receipt.source_access_manifest.model_copy(
        update={"receipts": [swapped_read]}, deep=True,
    )
    swapped = receipt.model_copy(update={
        "output_sediment": receipt.output_sediment.model_copy(
            update={"source_access_manifest": swapped_manifest}, deep=True,
        )
    }, deep=True)
    with pytest.raises(ValueError, match="F07_INCOMPLETE"):
        compose_private_operator_r01r02(
            swapped, ledger=ledger, source_bytes=src, method_invocation_bytes=method,
        )


def test_bridge_rejects_unrecorded_or_hand_built_matching_receipt():
    recorded, src, method, original_ledger = _run("materials")
    hand_built = OperatorRunReceipt.model_validate(recorded.model_dump(mode="python"))
    empty = OperatorRunLedger()
    with pytest.raises(ValueError, match="OPERATOR_R01R02_UNRECORDED_RUN"):
        compose_private_operator_r01r02(
            hand_built, ledger=empty, source_bytes=src, method_invocation_bytes=method,
        )
    preview = compose_private_operator_r01r02(
        recorded, ledger=original_ledger, source_bytes=src,
        method_invocation_bytes=method,
    )
    assert preview["customer_release"] == "BLOCKED"
    assert preview["provenance"] == "SELF_OBSERVED_UNATTESTED"
    tweaked = recorded.model_copy(
        update={"declared_model_identity": "hand-edited-without-invocation"},
        deep=True,
    )
    with pytest.raises(ValueError, match="OPERATOR_R01R02_LEDGER_RECEIPT_MISMATCH"):
        compose_private_operator_r01r02(
            tweaked, ledger=original_ledger, source_bytes=src,
            method_invocation_bytes=method,
        )


def test_fresh_process_sqlite_reopen_matches_run_id_and_output_digest(tmp_path):
    source, source_bytes, method, method_bytes = inputs("materials")
    db_path = tmp_path / "runs.sqlite"
    writer = SQLiteOperatorRunLedger(db_path)
    receipt = invoke_operator_method_body(
        ledger=writer,
        run_id="sqlite-reopen-materials",
        job_id="local-materials",
        source=source, source_bytes=source_bytes,
        method=method, method_body_invocation_bytes=method_bytes,
        method_callable=execute_literal_method,
        requested_view="private-operator",
        declared_model_identity="deterministic-local-no-model",
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )
    preview = compose_private_operator_r01r02(
        receipt, ledger=writer, source_bytes=source_bytes,
        method_invocation_bytes=method_bytes,
    )
    reopened = SQLiteOperatorRunLedger(db_path)
    stored = reopened.get(receipt.run_id)
    assert stored.run_id == receipt.run_id
    assert stored.output_digest == receipt.output_digest
    verify_private_operator_r01r02(
        preview, stored, ledger=reopened, source_bytes=source_bytes,
        method_invocation_bytes=method_bytes,
    )


@pytest.mark.parametrize("fixture", ["materials", "organization"])
def test_full_private_cli_fresh_process_and_reject_tampered_prior_preview(tmp_path, fixture):
    out = tmp_path / fixture
    def invoke(*, verify=False):
        cmd = [
            sys.executable, "-m", "seshat.fabric_waves.operator_local_demo",
            "--fixture", fixture, "--out", str(out), "--private-report",
        ]
        if verify:
            cmd.append("--verify-only")
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    first = invoke()
    assert first.returncode == 0, first.stderr
    receipt = json.loads(first.stdout)
    assert receipt["preview_status"] == "CREATED_PRIVATE"
    assert receipt["run_id"] == f"local-demo-{fixture}"
    assert receipt["digest"]
    preview_file = out / "private_r01r02.json"
    assert preview_file.is_file()
    original_bytes = preview_file.read_bytes()
    stored_preview = json.loads(original_bytes)
    assert stored_preview["customer_release"] == "BLOCKED"
    assert "INVENTED MATERIAL STUDY" not in original_bytes.decode("utf-8")
    assert "INVENTED WORKFLOW CSV" not in original_bytes.decode("utf-8")
    second = invoke(verify=True)
    assert second.returncode == 0, second.stderr
    verified = json.loads(second.stdout)
    assert verified["preview_status"] == "VERIFIED_EXISTING_PRIVATE"
    assert verified["run_id"] == receipt["run_id"]
    assert verified["digest"] == receipt["digest"]
    assert preview_file.read_bytes() == original_bytes
    # A forged approval in the owner-private preview must be detected even if
    # the SQLite ledger and the original method invocation remain unchanged.
    changed = json.loads(original_bytes)
    changed["customer_release"] = "AUTHORIZED"
    preview_file.write_text(json.dumps(changed), encoding="utf-8")
    rejected = invoke(verify=True)
    assert rejected.returncode != 0
    assert "OPERATOR_R01R02_PROJECTION_REPLAY_MISMATCH" in rejected.stderr
    rejected_again = invoke()
    assert rejected_again.returncode != 0
    # A normal invocation must NOT silently overwrite a forged prior artifact.
    assert json.loads(preview_file.read_text())["customer_release"] == "AUTHORIZED"
