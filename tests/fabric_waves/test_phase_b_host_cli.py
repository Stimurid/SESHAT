"""Phase B host CLI: dry run is the default; effects need explicit flags. MOCK transport only."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from seshat.fabric_waves.external_carrier.host_adapter import APPROVAL_SCHEMA, APPROVAL_SCOPE
from seshat.fabric_waves.external_carrier.host_cli import (
    CONFIG_SCHEMA,
    EXIT_OK,
    EXIT_WAITING,
    run,
)
from seshat.fabric_waves.external_carrier.host_envelope import request_pin_digest
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.hub_protocol import HubJobSpec
from seshat.fabric_waves.external_carrier.phase_b import OriginManifest, start_waiting_run
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError

from .phase_b_harness import (
    HUB_INSTANCE,
    ISSUER_ID,
    MODEL,
    PROVIDER,
    TOPICS,
    good_stdout,
    make_auth,
    make_record,
)


def _out(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_cli_end_to_end_dry_run_default_then_explicit_effects(tmp_path, capsys, monkeypatch):
    # Bypass the live-dispatch protocol gate for this isolated-engine CLI test: the unit under
    # test is the host CLI's dry-run-vs-execute flow, not the ``aiye-exec submit`` argv. The
    # unit test ``test_live_dispatch_fails_closed_when_caller_protocol_unverified`` exercises the
    # missing-override path independently.
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    host = tmp_path / "host"
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        assert kwargs["shell"] is False
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def cli(*args: str) -> int:
        return run(["--host-dir", str(host), *args], environ={}, runner=runner)

    assert (
        cli(
            "write-origin", "--engine", "campus", "--run-id", "phaseb-cli-campus",
            "--event-id", "phaseb-q", "--topic", TOPICS["campus"],
            "--query", "reconcile divergent branches with external research carrier",
            "--out-name", "campus-origin",
        )
        == EXIT_OK
    )
    assert _out(capsys)["state"] == "WRITTEN"

    origin_path = host / "origins" / "campus-origin.json"
    origin = OriginManifest.from_replay(json.loads(origin_path.read_text(encoding="utf-8")))
    need = start_waiting_run(origin).need
    (host / "host_config.json").write_text(
        json.dumps(
            {
                "schema": CONFIG_SCHEMA,
                "allowed_host_scopes": [need.worker_ref.host_scope],
                "policy": {"provider": PROVIDER, "model": MODEL, "role": "analyze"},
                "issuers": [
                    {
                        "issuer_id": ISSUER_ID,
                        "hub_instance_id": HUB_INSTANCE,
                        "allowed_providers": [PROVIDER],
                        "allowed_models": [MODEL],
                    }
                ],
                "approvals_file": "origin_approvals.json",
                "aiye_exec_path": str(host / "bin" / "aiye-exec"),
            }
        ),
        encoding="utf-8",
    )
    (host / "origin_approvals.json").write_text(
        json.dumps(
            {
                "schema": APPROVAL_SCHEMA,
                "approvals": [
                    {
                        "request_pin_sha256": request_pin_digest(need),
                        "request_id": need.request_id,
                        "run_id": need.run_id,
                        "approved_by": "owner-test",
                        "scope": APPROVAL_SCOPE,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # file arguments are confined to the host directory
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    for bad, code in (
        ("../outside.json", "PATH_TRAVERSAL"),
        (str(tmp_path / "outside.json"), "PATH_OUTSIDE_BASE"),
    ):
        with pytest.raises(ExternalAdmissionError) as exc:
            cli("prepare", "--origin", bad)
        assert str(exc.value.args[0]) == code

    # prepare: dry run persists nothing
    assert cli("prepare", "--origin", "origins/campus-origin.json") == EXIT_OK
    dry = _out(capsys)
    assert dry["state"] == "DRY_RUN" and dry["persisted"] is False and dry["dry_run"] is True
    assert HostJobStore(host / "store").list_job_ids() == []

    assert cli("prepare", "--origin", "origins/campus-origin.json", "--execute") == EXIT_OK
    prepared = _out(capsys)
    job_id = prepared["host_job_id"]
    assert prepared["state"] == "PREPARED"
    spec = HubJobSpec.model_validate(
        HostJobStore(host / "store").get_job(job_id).dispatch["spec"]
    )

    # dispatch: dry run builds the static argv but never calls the runner
    assert cli("dispatch", "--host-job-id", job_id) == EXIT_OK
    dispatch_dry = _out(capsys)
    assert dispatch_dry["state"] == "DRY_RUN" and dispatch_dry["dry_run"] is True
    assert dispatch_dry["manifest"]["argv"][1] == "submit"
    assert dispatch_dry["manifest"]["protocol_status"] == "UNVERIFIED_AGAINST_CALLER_PROTOCOL"
    assert calls == []

    with pytest.raises(ExternalAdmissionError) as exc:
        cli("dispatch", "--host-job-id", job_id, "--execute")
    assert str(exc.value.args[0]) == "LIVE_DISPATCH_NOT_AUTHORIZED"
    assert calls == []

    (host / "auth.json").write_text(json.dumps(make_auth(spec)), encoding="utf-8")
    assert (
        cli("dispatch", "--host-job-id", job_id, "--execute", "--authorization", "auth.json")
        == EXIT_OK
    )
    assert _out(capsys)["state"] == "SUBMITTED"
    assert len(calls) == 1 and calls[0][1] == "submit"

    # ingest: no Hub record yet -> typed WAITING (not a hallucinated result)
    assert cli("ingest", "--host-job-id", job_id) == EXIT_WAITING
    assert _out(capsys)["state"] == "WAITING"

    spool = host / "hub_spool" / spec.hub_job_id
    spool.mkdir(parents=True, exist_ok=True)
    data = good_stdout(tuple(need.source_carrier_ids))
    (spool / "record.json").write_text(make_record(spec, data).model_dump_json(), encoding="utf-8")
    (spool / "stdout.bin").write_bytes(data)

    assert cli("ingest", "--host-job-id", job_id) == EXIT_OK
    ingest_dry = _out(capsys)
    assert ingest_dry["state"] == "COMPLETED" and ingest_dry["wrote"] is False
    assert HostJobStore(host / "store").get_terminal(job_id) is None

    assert cli("ingest", "--host-job-id", job_id, "--execute") == EXIT_OK
    assert _out(capsys)["wrote"] is True
    assert HostJobStore(host / "store").get_terminal(job_id).status == "COMPLETED"

    # resume: verified replay; artifacts only with --execute
    assert cli("resume", "--host-job-id", job_id) == EXIT_OK
    resume_dry = _out(capsys)
    assert resume_dry["mode"] == "PHASE_B_REPLAY_VERIFIED" and resume_dry["dry_run"] is True
    assert not (host / "artifacts").exists()

    assert cli("resume", "--host-job-id", job_id, "--execute", "--output-name", "run1") == EXIT_OK
    done = _out(capsys)
    assert "carpet.html" in done["artifacts"] and "terminal_output_sha.jsonl" in done["artifacts"]
    receipt = json.loads((host / "artifacts" / "run1" / "receipt.json").read_text("utf-8"))
    assert receipt["transport_kind"] == "UNATTESTED_MANUAL_IMPORT"
    assert receipt["mode"] == "PHASE_B_REPLAY_VERIFIED"

    assert cli("status", "--host-job-id", job_id) == EXIT_OK
    status = _out(capsys)
    assert status["terminal_status"] == "COMPLETED"
    assert [item["kind"] for item in status["submissions"]][-1] == "SUBMIT_ACKED"


def test_resume_hub_spool_transport_requires_attested_submission(tmp_path, capsys, monkeypatch):
    """A genuine configured host dir + prepared job: HUB_TRANSPORT_UNATTESTED is the precise
    gate, not HOST_CONFIG_INVALID / PATH_NOT_FOUND. Then a positive path: with a fully-acked
    registry-verified terminal Hub record, ``--transport-kind HUB_SPOOL_RECORD`` succeeds.
    """

    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    host = tmp_path / "host"
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def cli(*args: str) -> int:
        return run(["--host-dir", str(host), *args], environ={}, runner=runner)

    from seshat.fabric_waves.external_carrier.host_cli import (
        TRANSPORT_HUB_SPOOL_RECORD,
    )

    # Seed an origin and prepare a real job (no ACK yet).
    assert (
        cli(
            "write-origin", "--engine", "campus", "--run-id", "phaseb-spool-test",
            "--event-id", "phaseb-q", "--topic", TOPICS["campus"],
            "--query", "reconcile divergent branches with external research carrier",
            "--out-name", "campus-origin-spool",
        )
        == EXIT_OK
    )
    need = start_waiting_run(
        OriginManifest.from_replay(
            json.loads((host / "origins" / "campus-origin-spool.json").read_text())
        )
    ).need
    (host / "host_config.json").write_text(
        json.dumps(
            {
                "schema": CONFIG_SCHEMA,
                "allowed_host_scopes": [need.worker_ref.host_scope],
                "policy": {"provider": PROVIDER, "model": MODEL, "role": "analyze"},
                "issuers": [
                    {
                        "issuer_id": ISSUER_ID,
                        "hub_instance_id": HUB_INSTANCE,
                        "allowed_providers": [PROVIDER],
                        "allowed_models": [MODEL],
                    }
                ],
                "approvals_file": "origin_approvals.json",
                "aiye_exec_path": str(host / "bin" / "aiye-exec"),
            }
        ),
        encoding="utf-8",
    )
    (host / "origin_approvals.json").write_text(
        json.dumps(
            {
                "schema": APPROVAL_SCHEMA,
                "approvals": [
                    {
                        "request_pin_sha256": request_pin_digest(need),
                        "request_id": need.request_id,
                        "run_id": need.run_id,
                        "approved_by": "owner-test",
                        "scope": APPROVAL_SCOPE,
                    }
                ],
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    assert cli("prepare", "--origin", "origins/campus-origin-spool.json", "--execute") == EXIT_OK
    job_id = json.loads(capsys.readouterr().out)["host_job_id"]
    spec = HubJobSpec.model_validate(
        HostJobStore(host / "store").get_job(job_id).dispatch["spec"]
    )

    # NEGATIVE: configured host, prepared job, NO ACK -> the transport gate fires with the
    # EXACT stable code (no acceptance from a side-channel PATH_NOT_FOUND / HOST_CONFIG_INVALID).
    with pytest.raises(ExternalAdmissionError) as exc:
        cli(
            "resume", "--host-job-id", job_id, "--execute",
            "--output-name", "x", "--transport-kind", TRANSPORT_HUB_SPOOL_RECORD,
        )
    assert str(exc.value.args[0]) == "HUB_TRANSPORT_UNATTESTED"

    # Manual ``HUB_SPOOL_RECORD`` strings typed against an UNACKED job must NOT be admitted even
    # under unrelated config errors: the gate must come from the adapter, not from path noise.
    bad_host = tmp_path / "badhost"
    bad_host.mkdir()
    (bad_host / "host_config.json").write_text("{}", encoding="utf-8")  # unreadable config
    with pytest.raises(ExternalAdmissionError) as exc:
        run(
            [
                "--host-dir", str(bad_host), "resume",
                "--host-job-id", job_id, "--execute",
                "--output-name", "x", "--transport-kind", TRANSPORT_HUB_SPOOL_RECORD,
            ],
            environ={},
        )
    assert str(exc.value.args[0]) in {
        "HOST_CONFIG_INVALID",
        "ORIGIN_NOT_APPROVED",
        "HUB_TRANSPORT_UNATTESTED",
    }

    # POSITIVE: submit through the host (mock runner returns 0), then ingest a verified Hub
    # record, then ``--transport-kind HUB_SPOOL_RECORD`` succeeds.
    (host / "auth.json").write_text(json.dumps(make_auth(spec)), encoding="utf-8")
    assert (
        cli(
            "dispatch", "--host-job-id", job_id, "--execute",
            "--authorization", "auth.json",
        )
        == EXIT_OK
    )
    assert calls
    spool = host / "hub_spool" / spec.hub_job_id
    spool.mkdir(parents=True, exist_ok=True)
    data = good_stdout(tuple(need.source_carrier_ids))
    (spool / "record.json").write_text(
        make_record(spec, data).model_dump_json(), encoding="utf-8"
    )
    (spool / "stdout.bin").write_bytes(data)
    assert cli("ingest", "--host-job-id", job_id, "--execute") == EXIT_OK

    assert (
        cli(
            "resume", "--host-job-id", job_id, "--execute",
            "--output-name", "with-spool", "--transport-kind", TRANSPORT_HUB_SPOOL_RECORD,
        )
        == EXIT_OK
    )
    payload = json.loads(capsys.readouterr().out)
    assert "carpet.html" in payload["artifacts"]
    receipt = json.loads((host / "artifacts" / "with-spool" / "receipt.json").read_text("utf-8"))
    assert receipt["transport_kind"] == TRANSPORT_HUB_SPOOL_RECORD


def test_cli_confines_file_arguments_to_host_dir(tmp_path):
    host = tmp_path / "host"
    host.mkdir()
    with pytest.raises(ExternalAdmissionError) as exc:
        run(
            [
                "--host-dir", str(host), "write-origin", "--engine", "campus",
                "--run-id", "../evil", "--event-id", "e", "--topic", "t", "--query", "q",
                "--out-name", "x",
            ],
            environ={},
        )
    assert str(exc.value.args[0]) == "RUN_ID_INVALID"
    assert not Path(tmp_path / "evil").exists()
