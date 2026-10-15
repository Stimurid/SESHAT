"""Synthetic owner-file and hostile request tests. Run only in isolated CI.

All pins are installed by the simulated owner before requests. No private v4
input, OS permission changes, credentials, PDFs or scientific claims are used.
"""

import hashlib
import io
import json

import pytest

from seshat.corpus import Predicate, TemporalProvenance
from seshat.corpus_adapters import (
    HostTemporalMetadata, pinned_temporal_metadata, sechenovka_v4_metadata_row,
)
from seshat.corpus_host import HostRuntime, main
from test_corpus_host import config, pin_file
from test_corpus_selection import spec
from test_corpus_temporal import intake


def owner_files(tmp_path, *, dates=None, allowed=("defended_on",), count=1):
    records = [sechenovka_v4_metadata_row(
        {**intake(), "study_id": f"synthetic-{i}"},
        row_evidence_ref="synthetic:intake", record_version="v4") for i in range(count)]
    configuration = config(tmp_path, records, allowed=tuple(
        r.research_object.object_id for r in records))
    primary = json.loads(configuration.primary.path.read_bytes())
    primary["declared_fields"] += ["defended_on", "defended_on_year", "defense_date_year",
                                   "abstract_published_year"]
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0]["temporal_fields"] = {
        r.research_object.object_id: list(allowed) for r in records}
    # Independent fixture builds the source join; do not use production binding
    # helper to generate the expected carrier identity/digest.
    temporal = {"host_id": configuration.host_id, "records": [{
        "study_id": r.research_object.object_id, "record_version": "v4",
        "carriers": [{"carrier_id": "invented-abstract", "source_identity": "v4:abstract",
                      "version": "v4", "sha256": "a" * 64}],
        **({"defended_on": "2026-02-18"} if dates is None else dates),
    } for r in records]}
    return configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, primary),
        "rights": pin_file(configuration.rights.path, rights),
        "temporal": pin_file(tmp_path / "temporal.json", temporal),
    })


def session(configuration):
    runtime = HostRuntime(configuration)
    return runtime, runtime.session(authenticated_caller="reader", authorized_view="research")


def query(field="defended_on_year", year=2026):
    return spec(Predicate(op="range", field=field, lower=year, upper=year))


@pytest.mark.parametrize("kind", ["manual", "matching-hash", "serialized"])
def test_direct_typed_and_self_hashed_temporal_models_never_authorize(kind):
    fake = HostTemporalMetadata(object_id="invented-temporal", evidence=(TemporalProvenance(
        source_field="defended_on", source_value="2026-02-18", source_sha256="f" * 64,
        source_version="adversary", precision="DATE"),))
    if kind == "matching-hash":
        raw = b'{"study_id":"invented-temporal","defended_on":"2026-02-18"}'
        fake = pinned_temporal_metadata(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                                       expected_object_id="invented-temporal",
                                       source_version="adversary")
    if kind == "serialized":
        fake = HostTemporalMetadata.model_validate_json(fake.model_dump_json())
    with pytest.raises(ValueError, match="^UNTRUSTED_TEMPORAL_METADATA$"):
        sechenovka_v4_metadata_row(intake(), row_evidence_ref="fake", record_version="v4",
                                  temporal_metadata=fake)


def test_owner_pinned_file_success_and_no_source_or_rights_mean_unknown(tmp_path):
    configuration = owner_files(tmp_path)
    runtime, select = session(configuration)
    assert select(query()).selected_studies == 1
    assert select(query("cohort_year", 2025)).selected_studies == 1
    assert select(query("defense_date_year")).unknown_metadata == 1
    runtime.install(configuration.model_copy(update={"temporal": None}))
    assert select(query()).unknown_metadata == 1
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0].pop("temporal_fields")
    runtime.install(configuration.model_copy(update={
        "rights": pin_file(configuration.rights.path, rights)}))
    assert select(query()).unknown_metadata == 1


@pytest.mark.parametrize("target", ["temporal", "rights"])
def test_changed_bytes_and_recomputed_request_sha_do_not_replace_owner_pin(tmp_path, target):
    configuration = owner_files(tmp_path)
    _, select = session(configuration)
    assert select(query()).selected_studies == 1  # warm the cache
    pin = getattr(configuration, target)
    payload = json.loads(pin.path.read_bytes())
    if target == "temporal":
        payload["records"][0]["defended_on"] = "2099-01-01"
    else:
        payload["grants"][0]["temporal_fields"] = {}
    forged = pin_file(pin.path, payload)  # owner does NOT install this pin
    request = query().model_copy(update={
        "manifest": query().manifest.model_copy(update={"sha256": forged.sha256})})
    with pytest.raises(ValueError, match="^HOST_INPUT_UNAVAILABLE$"):
        select(request)


@pytest.mark.parametrize("mutation", ["object", "carrier-id", "carrier-sha", "identity",
                                      "record-version", "carrier-version", "duplicate"])
def test_owner_file_must_join_exact_admitted_study_and_carriers(tmp_path, mutation):
    configuration = owner_files(tmp_path)
    payload = json.loads(configuration.temporal.path.read_bytes())
    row = payload["records"][0]
    if mutation == "object":
        row["study_id"] = "swapped-object"
    elif mutation == "record-version":
        row["record_version"] = "other"
    elif mutation == "duplicate":
        payload["records"].append(dict(row))
    else:
        field = {"carrier-id": "carrier_id", "carrier-sha": "sha256",
                 "identity": "source_identity", "carrier-version": "version"}[mutation]
        row["carriers"][0][field] = "f" * 64 if mutation == "carrier-sha" else "other"
    configuration = configuration.model_copy(update={
        "temporal": pin_file(configuration.temporal.path, payload)})
    _, select = session(configuration)
    if mutation == "object":
        assert select(query()).unknown_metadata == 1
    else:
        with pytest.raises(ValueError, match="^HOST_TEMPORAL_UNAVAILABLE$"):
            select(query())


def test_field_revocation_and_source_changes_invalidate_cached_dates(tmp_path):
    configuration = owner_files(tmp_path, dates={
        "defended_on": "2026-01-17", "defense_date": "2026-02-18"},
        allowed=("defended_on", "defense_date"))
    runtime, select = session(configuration)
    first = select(query())
    payload = json.loads(configuration.temporal.path.read_bytes())
    payload["records"][0]["defended_on"] = "2026-01-18"
    configuration = configuration.model_copy(update={
        "temporal": pin_file(configuration.temporal.path, payload)})
    runtime.install(configuration)
    second = select(query())
    assert first.members == second.members and first.input_digest != second.input_digest
    assert runtime.rebuild_count == 2
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0]["temporal_fields"]["synthetic-0"] = ["defense_date"]
    runtime.install(configuration.model_copy(update={
        "rights": pin_file(configuration.rights.path, rights)}))
    assert select(query()).unknown_metadata == 1
    assert select(query("defense_date_year")).selected_studies == 1


def test_hidden_date_and_denied_field_mutations_do_not_change_public_bytes(tmp_path):
    configuration = owner_files(tmp_path)
    runtime, select = session(configuration)
    first = select(query()).model_dump_json()
    payload = json.loads(configuration.temporal.path.read_bytes())
    for i, value in enumerate(("2020-01-01", "2099-12-31", "bad-date", {"bad": []}), 2):
        payload["records"][0]["defense_date"] = value  # denied field on visible study
        payload["records"] = [payload["records"][0], {
            "study_id": "hidden", "defended_on": value, "carriers": "invalid"}]
        configuration = configuration.model_copy(update={
            "temporal": pin_file(configuration.temporal.path, payload)})
        runtime.install(configuration)
        assert select(query()).model_dump_json() == first
        assert runtime.rebuild_count == i


@pytest.mark.parametrize("value", ["2026-02-30", "2026", True, 2026.0, 0, 10000, [], {}])
def test_invalid_owner_dates_fail_only_after_field_rights(tmp_path, value):
    configuration = owner_files(tmp_path, dates={"defended_on": value})
    runtime, select = session(configuration)
    with pytest.raises(ValueError, match="^HOST_TEMPORAL_UNAVAILABLE$"):
        select(query())
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0]["temporal_fields"] = {}
    runtime.install(configuration.model_copy(update={
        "rights": pin_file(configuration.rights.path, rights)}))
    assert select(query()).unknown_metadata == 1


def test_primary_package_cannot_launder_forged_temporal_labels(tmp_path):
    configuration = owner_files(tmp_path)
    payload = json.loads(configuration.primary.path.read_bytes())
    payload["records"][0]["fields"].append({"name": "defended_on_year", "value": 2099,
        "evidence_ref": "fake", "temporal_provenance": {"source_sha256": "f" * 64}})
    configuration = configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, payload), "temporal": None})
    _, select = session(configuration)
    assert select(query(year=2099)).unknown_metadata == 1


@pytest.mark.parametrize("deny", ["object_ids", "carrier_ids"])
def test_row_and_carrier_denial_precedes_temporal_validation(tmp_path, deny):
    configuration = owner_files(tmp_path, dates={"defended_on": "invalid date"})
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0][deny] = []
    configuration = configuration.model_copy(update={
        "rights": pin_file(configuration.rights.path, rights)})
    _, select = session(configuration)
    baseline = select(query()).model_dump_json()
    assert select(query()).selected_studies == 0
    payload = json.loads(configuration.temporal.path.read_bytes())
    payload["records"][0]["defended_on"] = "2099-01-01"
    payload["records"].append(dict(payload["records"][0]))
    configuration = configuration.model_copy(update={
        "temporal": pin_file(configuration.temporal.path, payload)})
    _, select = session(configuration)
    assert select(query()).model_dump_json() == baseline


def test_missing_or_wrong_owner_source_pin_is_blocked(tmp_path):
    configuration = owner_files(tmp_path)
    for replacement in (
        configuration.temporal.model_copy(update={"sha256": "f" * 64}),
        configuration.temporal.model_copy(update={"path": tmp_path / "missing.json"}),
    ):
        with pytest.raises(ValueError, match="^HOST_INPUT_UNAVAILABLE$"):
            HostRuntime(configuration.model_copy(update={"temporal": replacement}))


def test_separate_owner_process_accepts_only_selector_json_lines(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    configuration = owner_files(tmp_path)
    root = pin_file(tmp_path / "host.json", configuration.model_dump(mode="json"))
    attack = {**query().model_dump(mode="json"),
              "temporal": configuration.temporal.model_dump(mode="json"),
              "rights": {"grants": "all"}}
    result = subprocess.run(
        [sys.executable, "-m", "seshat.corpus_host", "--config", str(root.path),
         "--config-sha256", root.sha256, "--host-id", configuration.host_id,
         "--caller-id", "reader", "--view-id", "research"],
        input=json.dumps(attack) + "\n" + query().model_dump_json() + "\n",
        text=True, capture_output=True, timeout=15, cwd=tmp_path,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
             "PYTHONDONTWRITEBYTECODE": "1",
             **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {})})
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0] == {"error": "SELECTION_UNAVAILABLE"}
    assert responses[1]["selected_studies"] == 1


def test_sixteen_unknown_dates_remain_unknown_and_no_degree_is_asserted(tmp_path):
    configuration = owner_files(tmp_path, dates={}, count=16)
    _, select = session(configuration)
    result = select(query())
    assert result.unknown_metadata == 16 and result.selected_studies == 0
    assert select(query("degree_awarded", 2026)).not_evaluable == 16


@pytest.mark.parametrize("key", ["temporal", "temporal_metadata", "FilePin", "rights",
                                 "configuration"])
def test_json_line_caller_cannot_install_temporal_authority(tmp_path, monkeypatch, capsys, key):
    configuration = owner_files(tmp_path)
    root = pin_file(tmp_path / "host.json", configuration.model_dump(mode="json"))
    attack = {**query().model_dump(mode="json"), key: configuration.model_dump(mode="json")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(attack) + "\n"
                                                + query().model_dump_json() + "\n"))
    assert main(["--config", str(root.path), "--config-sha256", root.sha256,
                 "--host-id", configuration.host_id, "--caller-id", "reader",
                 "--view-id", "research"]) == 0
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0] == {"error": "SELECTION_UNAVAILABLE"}
    assert output[1]["selected_studies"] == 1
    assert configuration.temporal.sha256 not in json.dumps(output)
