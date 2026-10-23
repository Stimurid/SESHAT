import copy
import hashlib
import json

import pytest

from seshat.fabric_waves.i11_activity_network import AUTHORIAL_I11_SHA256
from seshat.fabric_waves.i11_native_hub_lineage import (
    NativeHubLineageError,
    audit_native_hub_source,
    save_and_verify_lineage,
)


def sha(x):
    return hashlib.sha256(x).hexdigest()


def sample():
    original = b"%PDF-1.4 source object"
    canonical = b"PAGE 1\nheading\nPAGE 2\nconclusion\n"
    worktree = canonical.replace(b"\n", b"\r\n")
    stdout = b"Original model response"
    native = {
        "schema": "AIYE_LOCAL_EXEC_RECEIPT_v0.1",
        "job_id": "jx-test-a",
        "state": "SUCCEEDED", "exit_code": 0,
        "ended_at": "2026-10-22T11:00:15+00:00",
    }
    publication = {
        "schema": "AIYE_PUBLICATION_MANIFEST_v0.1",
        "job_id": "jx-test-a", "terminal_status": "SUCCEEDED",
        "error_class": None,
        "publication_status": "AWAITING_SEMANTIC_REVIEW",
        "output_manifest": {"stdout_sha256": sha(stdout)},
    }
    return {
        "native_receipt_bytes": json.dumps(native).encode(),
        "publication_manifest_bytes": json.dumps(publication).encode(),
        "original_pdf_bytes": original,
        "model_carrier_canonical_bytes": canonical,
        "model_carrier_worktree_bytes": worktree,
        "original_model_stdout_bytes": stdout,
        "expected_job_id": "jx-test-a",
        "pinned_pdf_sha256": sha(original),
        "pinned_model_carrier_sha256": sha(canonical),
        "pinned_stdout_sha256": sha(stdout),
        "work_id": "PLOS:sample", "git_commit": "a"*40,
        "source_git_path": "m7_source/open_source_pages.txt",
    }


def test_true_native_receipt_and_lf_crlf_do_not_certify_provider_read():
    values = audit_native_hub_source(**sample())
    assert values["native_terminal_state"] == "SUCCEEDED"
    assert values["source_carrier_relation"] == "LF_NORMALIZED_EQUIVALENT_NOT_BYTE_IDENTICAL"
    assert values["exact_provider_read_bytes"] == "NOT_ATTESTED_BY_NATIVE_HUB"
    assert values["hub_attested_original_pdf_sha"] is False
    assert values["frozen_method_byte_check"] == "NOT_PERFORMED"
    assert values["genuine_two_real_i11_r03_v2_admission"] == "BLOCKED"
    assert values["customer_release"] == "BLOCKED"
    assert len(values["projection_sha256"]) == 64


def test_native_exact_identical():
    args = sample()
    args["model_carrier_worktree_bytes"] = args["model_carrier_canonical_bytes"]
    assert audit_native_hub_source(**args)["source_carrier_relation"] == "BYTE_IDENTICAL"


@pytest.mark.parametrize("mutate,expected", [
    (lambda x: x.update(pinned_pdf_sha256="b"*64), "ORIGINAL_PDF_PIN_MISMATCH"),
    (lambda x: x.update(pinned_model_carrier_sha256="b"*64), "CANONICAL_CARRIER_PIN_MISMATCH"),
    (lambda x: x.update(pinned_stdout_sha256="a"*64), "MODEL_STDOUT_MANIFEST_MISMATCH"),
    (lambda x: x.update(expected_job_id="jx-other"), "NATIVE_HUB_TERMINAL_UNVERIFIED"),
    (lambda x: x.update(model_carrier_worktree_bytes=b"unrelated"), "MODEL_WORKTREE_CONTENT_NOT_EQUIVALENT"),
    (lambda x: x.update(method_sha256="b"*64), "WRONG_FROZEN_METHOD_PIN"),
    (lambda x: x.update(method_body_bytes=b"wrong bytes"), "METHOD_BODY_BYTES_MISMATCH"),
])
def test_mismatches_fail_closed(mutate, expected):
    args = copy.deepcopy(sample())
    mutate(args)
    with pytest.raises(NativeHubLineageError, match=expected):
        audit_native_hub_source(**args)


def test_false_approval_not_derived_from_native_terminal():
    args = sample()
    native = json.loads(args["native_receipt_bytes"])
    native["state"] = "FAILED"
    args["native_receipt_bytes"] = json.dumps(native).encode()
    with pytest.raises(NativeHubLineageError, match="NATIVE_HUB_TERMINAL_UNVERIFIED"):
        audit_native_hub_source(**args)


def test_wrong_manifest_source_refused():
    args = sample()
    pub = json.loads(args["publication_manifest_bytes"])
    pub["job_id"] = "jx-another"
    args["publication_manifest_bytes"] = json.dumps(pub).encode()
    with pytest.raises(NativeHubLineageError, match="PUBLICATION_MANIFEST_JOB_MISMATCH"):
        audit_native_hub_source(**args)


def test_immutable_private_writer_and_readback(tmp_path):
    evidence = audit_native_hub_source(**sample())
    dst = tmp_path / "receipt.json"
    h = save_and_verify_lineage(dst, evidence)
    assert h == sha(dst.read_bytes())
    assert save_and_verify_lineage(dst, evidence) == h
    altered = dict(evidence, work_id="FORGED")
    with pytest.raises(NativeHubLineageError, match="IMMUTABLE_LINEAGE_DRIFT"):
        save_and_verify_lineage(dst, altered)


def test_not_a_forged_admission(tmp_path):
    evidence = audit_native_hub_source(**sample())
    altered = dict(evidence, genuine_two_real_i11_r03_v2_admission="VERIFIED")
    with pytest.raises(NativeHubLineageError, match="IMPROPER_ADMISSION_CLAIM"):
        save_and_verify_lineage(tmp_path / "receipt.json", altered)


def test_method_pin_remains_operator_pinned():
    assert len(AUTHORIAL_I11_SHA256) == 64
    obj = audit_native_hub_source(**sample())
    assert obj["frozen_method_operator_pin_sha256"] == AUTHORIAL_I11_SHA256
    assert obj["frozen_method_byte_check"] != "BYTE_MATCH"
