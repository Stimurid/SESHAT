"""Owner bootstrap and caller attack witnesses, exclusively invented metadata."""

import hashlib
import json

import pytest

from seshat.corpus import build_corpus_space
from seshat.corpus_host import FilePin, HostConfiguration, HostRuntime
from seshat.corpus_private_cli import evaluate_owner_run
from seshat.corpus_report_input import CorpusReportInput
from test_corpus_confidentiality import outcome
from test_corpus_selection import MANIFEST, Rights, ids, spec, study, year


def pin_file(path, payload):
    raw = json.dumps(payload, sort_keys=True).encode()
    path.write_bytes(raw)
    return FilePin(path=path, sha256=hashlib.sha256(raw).hexdigest())


def config(tmp_path, rows, *, epoch="1", allowed=("visible",), host="archive-host"):
    source = {"host_id": host, "manifest_id": "primary", "version": "1",
              "declared_fields": sorted(MANIFEST.declared_fields),
              "records": [r.model_dump(mode="json") for r in rows]}
    rights = {"host_id": host, "epoch": epoch, "grants": [{
        "caller_id": "reader", "view_id": "research", "object_ids": list(allowed),
        "carrier_ids": [c.carrier_id for r in rows
                        if r.research_object.object_id in allowed for c in r.carriers]}]}
    return HostConfiguration(host_id=host, primary=pin_file(tmp_path / "source.json", source),
                             rights=pin_file(tmp_path / "rights.json", rights))


@pytest.mark.parametrize("mode", ["raise", "hidden-hash", "invalid"])
def test_malicious_sealing_callback_is_never_called(mode):
    class Malicious(Rights):
        def seal_selection(self, *args):
            if mode == "raise":
                raise RuntimeError("secret hidden population")
            return "f" * 64 if mode == "hidden-hash" else None

    row = study("visible", 2025)
    query = spec(year(2025, 2025))
    assert outcome(lambda: build_corpus_space(query, MANIFEST, [row], Malicious())) == (
        outcome(lambda: build_corpus_space(query, MANIFEST, [row], Rights())))


@pytest.mark.parametrize("host", ["archive-host", "unrelated-meteorology-host"])
def test_private_epochs_rebuild_without_public_hidden_world_oracle(tmp_path, host):
    visible = study("visible", 2025)
    hidden = study("hidden", 2020)
    runtime = HostRuntime(config(tmp_path, [visible], host=host))
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(year(2025, 2025))
    baseline = outcome(lambda: select(query))
    assert runtime.rebuild_count == 1
    assert outcome(lambda: select(query)) == baseline
    assert runtime.rebuild_count == 1
    worlds = ([visible, hidden], [hidden, visible],
              [study("hidden", 2099, version="2"), visible], [visible])
    for i, rows in enumerate(worlds, 2):
        runtime.install(config(tmp_path, rows, epoch=str(i), host=host))
        assert outcome(lambda: select(query)) == baseline
        assert runtime.rebuild_count == i
    # Policy rotation alone also invalidates, even though no public bit changes.
    runtime.install(config(tmp_path, [visible], epoch="rotation-only", host=host))
    assert outcome(lambda: select(query)) == baseline
    assert runtime.rebuild_count == 6
    runtime.install(config(tmp_path, [visible, hidden], allowed=("visible", "hidden"), host=host))
    assert ids(select(spec(year(2000, 2100)))) == ["hidden", "visible"]
    runtime.install(config(tmp_path, [visible, hidden], allowed=(), host=host))
    assert ids(select(query)) == []
    assert runtime.attest_package().package_state == "SOURCE_PACKAGE_INTEGRITY_VERIFIED"
    assert runtime.attest_package().original_source_fact_state == "NOT_VERIFIED"


def test_source_epoch_alone_invalidates_cache(tmp_path):
    visible = study("visible", 2025)
    runtime = HostRuntime(config(tmp_path, [visible]))
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(year(2025, 2025))
    first = select(query)
    runtime.install(config(tmp_path, [visible, study("hidden", 2020)]))
    assert select(query) == first
    assert runtime.rebuild_count == 2


def test_forged_file_and_self_consistent_request_pin_do_not_replace_owner_pin(tmp_path):
    configuration = config(tmp_path, [study("visible", 2025)])
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    forged = config(tmp_path, [study("visible", 2099)])
    query = spec(year(2000, 2100), manifest=MANIFEST.pin.model_copy(
        update={"sha256": forged.primary.sha256}))
    assert outcome(lambda: select(query)) == ("error", "ValueError", "HOST_INPUT_UNAVAILABLE")


def test_host_and_session_spoofing_fail_closed(tmp_path):
    configuration = config(tmp_path, [study("visible", 2025)])
    with pytest.raises(ValueError, match="HOST_INPUT_UNAVAILABLE"):
        HostRuntime(configuration.model_copy(update={"host_id": "forged"}))
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="different-user", authorized_view="research")
    with pytest.raises(ValueError, match="SESSION_SCOPE_MISMATCH"):
        select(spec(year(2025, 2025)))


def test_actual_file_field_values_override_forged_evidence_labels(tmp_path):
    row = study("visible", 2025)
    fake = row.model_copy(update={"fields": tuple(f.model_copy(
        update={"evidence_ref": "fabricated:primary"}) for f in row.fields)})
    runtime = HostRuntime(config(tmp_path, [row]))
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(year(2025, 2025))
    first = select(query)
    runtime.install(config(tmp_path, [fake]))
    assert select(query) == first
    runtime.install(config(tmp_path, [study("visible", 2099)]))
    assert ids(select(query)) == []


def test_owner_cli_missing_private_mount_never_passes(tmp_path):
    result = evaluate_owner_run(FilePin(path=tmp_path / "absent.json", sha256="a" * 64),
                                expected_host_id="archive-host")
    assert result == {"REAL_V4_RUN": "BLOCKED_SOURCE_ACCESS"}


def test_owner_cli_rejects_self_consistent_fake_config_host(tmp_path):
    conf = {"host_id": "attacker", "master": {}, "intake": {}, "contract": {},
            "rights": {}, "caller_id": "reader", "view_id": "research"}
    result = evaluate_owner_run(pin_file(tmp_path / "forged.json", conf),
                                expected_host_id="archive-host")
    assert result == {"REAL_V4_RUN": "BLOCKED_OR_MISMATCH"}


def test_hidden_invalid_metadata_has_identical_public_output_and_errors(tmp_path):
    visible = study("visible", 2025)
    configuration = config(tmp_path, [visible])
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(year(2025, 2025))
    baseline = outcome(lambda: select(query))
    package = json.loads(configuration.primary.path.read_bytes())
    package["records"].append({"research_object": {"object_id": "hidden"},
                                "fields": "malformed", "carriers": None})
    changed = configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, package)})
    runtime.install(changed)
    assert outcome(lambda: select(query)) == baseline
    bad_query = query.model_copy(update={"caller_id": "forged"})
    error = outcome(lambda: select(bad_query))
    runtime.install(config(tmp_path, [visible]))
    assert outcome(lambda: select(bad_query)) == error


@pytest.mark.parametrize("report_id", [f"R{i:02}" for i in range(1, 10)])
def test_all_report_inputs_bind_named_versioned_selection(report_id):
    query = spec(year(2025, 2025))
    snapshot = build_corpus_space(query, MANIFEST, [study("visible", 2025)], Rights())
    result = CorpusReportInput(report_id=report_id, selection=query, corpus=snapshot)
    assert result.content_state == "METADATA_ONLY_NOT_REPORT_EVIDENCE"
    with pytest.raises(ValueError, match="REPORT_SELECTION_MISMATCH"):
        CorpusReportInput(report_id=report_id, selection=spec(year(2020, 2020)), corpus=snapshot)
    with pytest.raises(ValueError, match="REPORT_SNAPSHOT_MISMATCH"):
        CorpusReportInput(report_id=report_id, selection=query,
                          corpus=snapshot.model_copy(update={"selected_studies": 99}))


def test_four_identity_flags_cannot_be_cleared_by_comparison_schema():
    from seshat.corpus_evaluation import PrivateV4Comparison

    result = PrivateV4Comparison(selectors_compared=14, identity_qa_pending=4)
    assert result.identity_qa_state == "NOT_CLEARED_BY_METADATA"
    with pytest.raises(ValueError):
        PrivateV4Comparison(selectors_compared=14, identity_qa_pending=0)


def test_unrelated_host_uses_its_own_metadata_schema(tmp_path):
    from seshat.corpus import EvidenceField, Predicate

    row = study("visible", 2025)
    row = row.model_copy(update={
        "research_object": row.research_object.model_copy(update={"object_type": "weather-sample"}),
        "fields": (EvidenceField(name="station", value="north", evidence_ref="invented:station"),)})
    configuration = config(tmp_path, [row], host="meteorology")
    package = json.loads(configuration.primary.path.read_bytes())
    package["declared_fields"] = ["station"]
    configuration = configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, package)})
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    result = select(spec(Predicate(op="equals", field="station", values=("north",))))
    assert ids(result) == ["visible"]
    assert select(spec(year(2025, 2025))).not_evaluable == 1


def test_visible_errors_equal_with_or_without_hidden_rows(tmp_path):
    configuration = config(tmp_path, [study("visible", 2025)])
    package = json.loads(configuration.primary.path.read_bytes())
    package["records"][0]["fields"] = "invalid"
    configuration = configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, package)})
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(year(2025, 2025))
    first = outcome(lambda: select(query))
    assert first == ("error", "ValueError", "invalid study pin")
    package["records"].append({"research_object": {"object_id": "hidden"}, "fields": None})
    runtime.install(configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, package)}))
    assert outcome(lambda: select(query)) == first


def test_owner_cli_rejects_synthetic_oracles_even_with_coherent_owner_file_pins(tmp_path):
    from test_corpus_evaluation import fixture

    master, intake, contract = fixture(tmp_path)
    contract_pin = pin_file(tmp_path / "contract.json", contract.model_dump(mode="json"))
    rights = pin_file(tmp_path / "rights.json", {
        "host_id": "synthetic", "epoch": "1", "grants": [{
            "caller_id": "private-evaluator", "view_id": "private-all",
            "object_ids": ["invented-a", "invented-b"],
            "carrier_ids": [b.carrier_id for b in contract.bindings]}]})
    configuration = {"host_id": "synthetic",
                     "master": {"path": str(master), "sha256": contract.master_sha256},
                     "intake": {"path": str(intake), "sha256": contract.intake_sha256},
                     "contract": contract_pin.model_dump(mode="json"),
                     "rights": rights.model_dump(mode="json"),
                     "caller_id": "private-evaluator", "view_id": "private-all"}
    result = evaluate_owner_run(pin_file(tmp_path / "run.json", configuration),
                                expected_host_id="synthetic")
    assert result == {"REAL_V4_RUN": "BLOCKED_OR_MISMATCH"}


def test_host_process_request_channel_cannot_install_policy_or_configuration(
        tmp_path, monkeypatch, capsys):
    import io

    from seshat.corpus_host import main

    configuration = config(tmp_path, [study("visible", 2025)])
    root = pin_file(tmp_path / "host.json", configuration.model_dump(mode="json"))
    query = spec(year(2025, 2025))
    attack = {**query.model_dump(mode="json"), "configuration": configuration.model_dump(mode="json"),
              "seal_selection": "attacker", "rights": {"grants": "all"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps(attack) + "\n" + query.model_dump_json() + "\n"
        + query.model_copy(update={"caller_id": "other"}).model_dump_json() + "\n"))
    assert main(["--config", str(root.path), "--config-sha256", root.sha256,
                 "--host-id", "archive-host", "--caller-id", "reader",
                 "--view-id", "research"]) == 0
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0] == output[2] == {"error": "SELECTION_UNAVAILABLE"}
    assert output[1]["selected_studies"] == 1
    assert output[1]["selection_state"] == "PROVISIONAL"
    assert root.sha256 not in json.dumps(output)
