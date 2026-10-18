"""F09A1 durable batch tests. Coordinator runs in isolated container."""
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from seshat.batch import (
    BatchItemSpec,
    BatchManifest,
    BatchManifestConflict,
    assert_safe_path,
    item_input_fingerprint,
    resume_batch,
    run_batch,
    status_batch,
)
from seshat.batch_demo import demo_manifest
from seshat.report_demo import demo_request, install_fixture, synthetic_packages


@pytest.mark.parametrize("host", ["sechenovka-like", "meteorology"])
def test_cli_creates_ledger_reports_and_receipt_on_both_hosts(tmp_path, host):
    output = tmp_path / f"batch-{host}"
    result = subprocess.run(
        [sys.executable, "-m", "seshat.batch_demo", "--fixture", host, "--output", str(output)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "batch_ledger.sqlite").is_file()
    assert (output / "batch_receipt.json").is_file()
    assert (output / "index.json").is_file()
    r03 = output / "items" / "r03-corpus"
    assert {p.name for p in r03.iterdir()} == {"report.json", "report.html", "receipt.json"}
    report = json.loads((r03 / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "SUBSTANTIVE_METADATA"
    summary = next(s for s in report["sections"] if s["title"] == "Local field / authorized denominators")
    values = {c["label"]: c["value"] for c in summary["claims"]}
    assert values["unique research objects (selected union)"] == 3
    assert values["unique source carriers (selected union)"] == 4
    r02 = json.loads((output / "items" / "r02-method-graph" / "report.json").read_text(encoding="utf-8"))
    assert r02["status"] == "PARTIAL_METADATA"
    assert r02["blocks"][0]["code"] == "BLOCKED_METHOD"
    r05 = json.loads((output / "items" / "r05-external-blocked" / "report.json").read_text(encoding="utf-8"))
    assert r05["status"] == "BLOCKED"
    assert r05["blocks"][0]["code"] == "BLOCKED_EXTERNAL_EVIDENCE"
    receipt = json.loads((output / "batch_receipt.json").read_text(encoding="utf-8"))
    assert receipt["scientific_accepted"] == "NEVER_AUTO_SET"
    assert receipt["code_pass"] is True
    assert "source_pins" not in receipt
    receipt_blob = (output / "batch_receipt.json").read_text(encoding="utf-8")
    assert "rights_sha256" not in receipt_blob
    assert "temporal_sha256" not in receipt_blob


def test_resume_idempotent_no_duplicate_bytes(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = demo_manifest(host, runtime, batch_id="resume-demo")
    root = tmp_path / "batch"
    first = run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    receipt_before = (root / "batch_receipt.json").read_bytes()
    index_before = (root / "index.json").read_bytes()
    before = {
        p: (root / "items" / "r03-corpus" / p).read_bytes()
        for p in ("report.json", "report.html", "receipt.json")
    }
    second = resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    assert (root / "batch_receipt.json").read_bytes() == receipt_before
    assert (root / "index.json").read_bytes() == index_before
    assert second.manifest_fingerprint == first.manifest_fingerprint
    after = {
        p: (root / "items" / "r03-corpus" / p).read_bytes()
        for p in ("report.json", "report.html", "receipt.json")
    }
    assert before == after
    st = status_batch(root)
    assert st.pending == 0


def test_interrupted_before_checkpoint_then_resume_completes(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = BatchManifest.model_validate(demo_manifest(host, runtime, batch_id="interrupt").model_dump())
    manifest = manifest.model_copy(update={"items": (manifest.items[0],)})
    root = tmp_path / "batch"

    def boom(_item_id):
        raise RuntimeError("SIMULATED_CRASH")

    with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
        run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
                  after_artifact_write_before_checkpoint=boom)
    item = status_batch(root).items[0]
    assert item.state == "FAILED_RETRYABLE"
    assert (root / "items" / manifest.items[0].item_id / "report.json").is_file()
    resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    item = status_batch(root).items[0]
    assert item.state == "DONE_METADATA"
    assert item.projection_digest


def test_tampered_report_json_triggers_regeneration(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = demo_manifest(host, runtime, batch_id="tamper")
    manifest = manifest.model_copy(update={"items": (manifest.items[0],)})
    root = tmp_path / "batch"
    run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    path = root / "items" / "r03-corpus" / "report.json"
    original = path.read_bytes()
    path.write_bytes(b"{\"tampered\":true}")
    resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    assert path.read_bytes() != b"{\"tampered\":true}"
    assert path.read_bytes() == original


def test_source_pin_change_marks_stale_and_rebuilds(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = demo_manifest(host, runtime, batch_id="stale-pin")
    manifest = manifest.model_copy(update={"items": (manifest.items[0],)})
    root = tmp_path / "batch"
    run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    before_digest = status_batch(root).items[0].projection_digest
    source, rights, temporal = synthetic_packages(host)
    source["records"][0]["fields"][0]["value"] = "Visible title mutation"
    from seshat.report_demo import pin_package
    from seshat.corpus_host import HostConfiguration, HostRuntime

    runtime.install(HostConfiguration(
        host_id=host,
        primary=pin_package(scratch / "source2.json", source),
        rights=pin_package(scratch / "rights2.json", rights),
        temporal=pin_package(scratch / "temporal2.json", temporal),
    ))
    resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    after = status_batch(root).items[0]
    assert after.projection_digest != before_digest
    assert after.state == "DONE_METADATA"


def test_manifest_fingerprint_conflict_rejected(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = demo_manifest(host, runtime, batch_id="conflict")
    manifest = manifest.model_copy(update={"items": (manifest.items[0],)})
    root = tmp_path / "batch"
    run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    manifest_bytes = (root / "manifest.json").read_bytes()
    attempts_before = status_batch(root).items[0].attempts
    altered = manifest.model_copy(update={
        "items": (BatchItemSpec(item_id="r03-corpus", request=demo_request("R01")),)})
    with pytest.raises(BatchManifestConflict):
        resume_batch(root, altered, runtime, caller_id="demo", rights_scope="synthetic-public")
    assert (root / "manifest.json").read_bytes() == manifest_bytes
    resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    assert status_batch(root).items[0].attempts == attempts_before


def test_hidden_denied_mutation_does_not_change_public_batch_bytes(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    manifest = demo_manifest(host, runtime, batch_id="denied")
    manifest = manifest.model_copy(update={"items": (manifest.items[0],)})
    root = tmp_path / "batch"
    run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    baseline = (root / "items" / "r03-corpus" / "report.json").read_bytes()
    source, rights, temporal = synthetic_packages(host)
    hidden = {"research_object": {"object_id": "DENIED-ID"}, "fields": None, "carriers": None}
    source = deepcopy(source)
    source["records"] = [hidden, *source["records"]]
    rights = deepcopy(rights)
    rights["epoch"] = "PRIVATE-EPOCH"
    from seshat.report_demo import pin_package
    from seshat.corpus_host import HostConfiguration

    runtime.install(HostConfiguration(
        host_id=host,
        primary=pin_package(scratch / "source3.json", source),
        rights=pin_package(scratch / "rights3.json", rights),
        temporal=pin_package(scratch / "temporal3.json", temporal),
    ))
    receipt_before = (root / "batch_receipt.json").read_bytes()
    index_before = (root / "index.json").read_bytes()
    attempts_before = status_batch(root).items[0].attempts
    resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    actual = (root / "items" / "r03-corpus" / "report.json").read_bytes()
    assert actual == baseline
    assert b"DENIED" not in actual
    assert b"PRIVATE" not in actual
    assert (root / "batch_receipt.json").read_bytes() == receipt_before
    assert (root / "index.json").read_bytes() == index_before
    assert status_batch(root).items[0].attempts == attempts_before


def test_unsafe_item_id_and_symlink_output_rejected(tmp_path):
    with pytest.raises(ValueError, match="UNSAFE_ITEM_ID"):
        from seshat.batch import _item_dir
        _item_dir(tmp_path, "../escape")
    if os.name != "nt":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError, match="UNSAFE_OUTPUT_PATH"):
            assert_safe_path(link / "nested" / "batch")


def test_template_change_invalidates_item_fingerprint(tmp_path):
    host = "sechenovka-like"
    scratch = tmp_path / "fixture"
    scratch.mkdir()
    runtime = install_fixture(scratch, host)
    item = BatchItemSpec(item_id="only", request=demo_request("R03"))
    manifest = demo_manifest(host, runtime, batch_id="template").model_copy(update={"items": (item,)})
    root = tmp_path / "batch"
    run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public")
    fp1 = item_input_fingerprint(manifest, item)
    changed = item.model_copy(update={
        "request": item.request.model_copy(update={"template_version": "F08-A-1"})})
    fp2 = item_input_fingerprint(manifest, changed)
    assert fp1 == fp2  # same template constant
    changed_sel = item.model_copy(update={
        "request": item.request.model_copy(update={
            "selections": (item.request.selections[0].model_copy(update={"version": "2"}),)
        })})
    fp3 = item_input_fingerprint(manifest, changed_sel)
    assert fp3 != fp1
