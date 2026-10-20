"""Synthetic host issuer only: no real credentials, paid jobs, or subprocesses.

Signing lives in this test fixture, not in the adapter under test. These are contract
tests for the independent publisher interface, NOT evidence of live Hub issuance.
"""
import json
from types import SimpleNamespace

import pytest

from seshat.fabric_waves.external_carrier.contracts import material_hash, utc_now_iso
from seshat.fabric_waves.external_carrier.host_dispatcher import HostDispatcher
from seshat.fabric_waves.external_carrier.host_envelope import FabricStoreSourceAuthority
from seshat.fabric_waves.external_carrier.host_security import HostBoundaryError, sha256_hex
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.native_hub_authority import NativeHubAuthority
from seshat.fabric_waves.external_carrier.native_hub_bridge import (
    NativeAiyeExecSubmitter, NativeHubBridge,
)
from seshat.fabric_waves.external_carrier.phase_b import (
    PHASE_B_REPLAY_VERIFIED, OriginManifest, resume_by_replay, start_waiting_run,
)

from .phase_b_harness import (
    HUB_INSTANCE, good_stdout, make_adapter, make_auth, make_harness, make_record,
)
from .test_native_hub_bridge import _launcher

JID = "jx-012345abcdef"


class FixtureHost:
    def __init__(self, tmp_path, engine_kind="campus", outcome="success"):
        self.h = make_harness(tmp_path, engine_kind, mac=True)
        h = self.h
        self.calls = 0
        self.outcome = outcome
        self.jobs = tmp_path / "originals"
        self.ledger = tmp_path / "issuer"
        self.ledger.mkdir()
        self.authority = NativeHubAuthority(
            self.jobs, self.ledger, h.mac_key, HUB_INSTANCE, "SESHAT_CARPET", "SESHAT",
        )
        h.adapter.native_authority = self.authority
        self.transport = NativeAiyeExecSubmitter(
            exe=str(tmp_path / "aiye-exec"), spool_dir=tmp_path / "prompts",
            mode="audit", client="SESHAT_CARPET", project_target="SESHAT",
            store=h.adapter.store, launcher=_launcher(tmp_path), runner=self.run, environ={},
        )
        self.bridge = NativeHubBridge(adapter=h.adapter, transport=self.transport,
                                      authority=self.authority)
        self.auth = make_auth(h.spec)
        self.sign("launch", {
            "authorization_sha256": material_hash(self.auth),
            "python_sha256": self.transport.launcher.python_sha256,
            "executor_sha256": self.transport.launcher.executor_sha256,
            "client": "SESHAT_CARPET", "project_target": "SESHAT", "decision_id": None,
        })

    def sign(self, kind, values):
        body = {
            "schema": f"seshat.native_hub.{kind}.v1", "host_job_id": self.h.job_id,
            "original_spec_sha256": self.h.spec.spec_sha256(), "hub_instance_id": HUB_INSTANCE,
            **values,
        }
        self.write(self.ledger / f"{self.h.job_id}.{kind}.json",
                   {"body": body, "mac": self.h.mac_key.mac(material_hash(body))})
        return body

    @staticmethod
    def write(path, doc):
        path.write_bytes(json.dumps(doc, sort_keys=True).encode())

    def run(self, argv, **kwargs):
        self.calls += 1
        assert kwargs["shell"] is False
        assert argv[:3] == [str(self.transport.launcher.python), "-E", "-s"]
        assert "--job-id" not in argv
        h = self.h
        assert argv[argv.index("--agent") + 1] == h.spec.provider
        assert argv[argv.index("--model") + 1] == h.spec.model
        now = utc_now_iso()
        folder = self.jobs / JID
        folder.mkdir(parents=True)
        native = {
            "schema": "AIYE_LOCAL_EXEC_TASK_v0.1", "job_id": JID,
            "ticket": h.spec.ticket, "role": h.spec.role, "mode": "audit",
            "agent": h.spec.provider, "model": h.spec.model,
            "prompt_sha256": h.spec.prompt_sha256, "max_seconds": h.spec.max_time_seconds,
            "client": "SESHAT_CARPET", "project_target": "SESHAT", "created_at": now,
        }
        self.write(folder / "spec.json", native)
        admission = self.sign("admission", {
            "native_job_id": JID, "nonce": self.auth["nonce"], "issued_at": now,
            "native_spec_sha256": sha256_hex((folder / "spec.json").read_bytes()),
        })
        stdout = good_stdout(h.carriers)
        effective = h.spec.model_copy(update={"hub_job_id": JID})
        record = make_record(effective, stdout, mac_key=h.mac_key, started_at=now, ended_at=now)
        self.write(folder / "status.json", {"job_id": JID, "state": "SUCCEEDED"})
        self.write(folder / "receipt.json", {
            **native, "schema": "AIYE_LOCAL_EXEC_RECEIPT_v0.1", "state": "SUCCEEDED",
            "started_at": now, "ended_at": now, "exit_code": 0,
        })
        (folder / "stdout.log").write_bytes(stdout)
        self.sign("terminal", {
            "native_job_id": JID, "admission_sha256": material_hash(admission),
            "original_sha256": {n: sha256_hex((folder / n).read_bytes()) for n in
                                ("spec.json", "status.json", "receipt.json", "stdout.log")},
            "usage_verified": True, "record": record.model_dump(mode="json"),
        })
        if self.outcome == "ghost":
            raise OSError("synthetic response lost after admission")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"job_id": JID}).encode())

    def dispatch(self):
        return HostDispatcher(adapter=self.h.adapter).dispatch(
            self.h.job_id, execute=True, submitter=self.bridge, authorization=self.auth,
        )


@pytest.mark.parametrize("engine_kind", ["campus", "meteorology"])
def test_native_original_to_same_waiting_and_two_dependent_threads(tmp_path, engine_kind):
    f = FixtureHost(tmp_path, engine_kind)
    h = f.h
    original = h.job.request_bytes
    assert f.dispatch().hub_job_id == JID
    assert h.adapter.load_job(h.job_id).request_bytes == original
    assert h.adapter._spec(h.adapter.load_job(h.job_id)).hub_job_id != JID
    result = HostDispatcher(adapter=h.adapter).ingest(h.job_id, fetcher=f.bridge, execute=True)
    assert result["state"] == "COMPLETED"
    h.adapter.assert_hub_attested_for_export(h.job_id)
    resumed = resume_by_replay(adapter=h.adapter, host_job_id=h.job_id)
    assert resumed.facts["wait_wave_id"] == h.need.wave_id
    assert len(resumed.facts["downstream_fired_threads"]) == 2
    assert resumed.facts["proposal_epistemic_level"] == "E5"
    assert f.calls == 1


def test_ghost_recovery_is_read_only_and_survives_new_transport(tmp_path):
    f = FixtureHost(tmp_path, outcome="ghost")
    assert f.dispatch().state == "AMBIGUOUS"
    with pytest.raises(HostBoundaryError, match="SUBMISSION_STATE_AMBIGUOUS"):
        f.dispatch()
    # Reopen the durable store, not just a single-instance boolean latch.
    store = HostJobStore(tmp_path / "store", integrity_key=f.h.mac_key)
    with pytest.raises(HostBoundaryError, match="NATIVE_LAUNCH_ALREADY_CLAIMED"):
        store.claim_native_launch(f.h.job_id, spec_sha256=f.h.spec.spec_sha256())
    f.bridge.recover(f.h.job_id)
    result = HostDispatcher(adapter=f.h.adapter).ingest(
        f.h.job_id, fetcher=f.bridge, execute=True,
    )
    assert result["state"] == "COMPLETED" and f.calls == 1


@pytest.mark.parametrize("engine_kind", ["campus", "meteorology"])
def test_native_cold_restart_rebuilds_entire_chain_and_original_wait(tmp_path, engine_kind):
    f = FixtureHost(tmp_path, engine_kind, outcome="ghost")
    original_request = f.h.job.request_bytes
    original_wait_wave = f.h.need.wave_id
    original_wait_activation = f.h.waiting.engine.ledger.activations_for_run(
        f.h.origin.run_id
    )
    assert f.dispatch().state == "AMBIGUOUS"
    assert f.calls == 1

    # Process boundary: reconstruct every consumer from durable replay material.
    # The original fixture's adapter, authority, bridge and WaveEngine are unused.
    persisted = HostJobStore(tmp_path / "store", integrity_key=f.h.mac_key).get_job(f.h.job_id)
    origin = OriginManifest.from_replay(persisted.replay)
    waiting = start_waiting_run(origin)
    assert waiting.need.wave_id == original_wait_wave
    assert waiting.need.request_id == f.h.need.request_id
    authority = NativeHubAuthority(
        tmp_path / "originals", tmp_path / "issuer", f.h.mac_key,
        HUB_INSTANCE, "SESHAT_CARPET", "SESHAT",
    )
    adapter = make_adapter(
        tmp_path, waiting.need, FabricStoreSourceAuthority(waiting.engine.carrier_store),
        mac=True,
    )
    adapter.native_authority = authority
    calls = []
    transport = NativeAiyeExecSubmitter(
        exe=str(tmp_path / "aiye-exec"), spool_dir=tmp_path / "prompts-after-restart",
        mode="audit", client="SESHAT_CARPET", project_target="SESHAT",
        store=adapter.store, launcher=_launcher(tmp_path),
        runner=lambda *a, **k: calls.append(a), environ={},
    )
    bridge = NativeHubBridge(adapter=adapter, transport=transport, authority=authority)
    assert adapter.load_job(f.h.job_id).request_bytes == original_request
    assert bridge.recover(f.h.job_id)["native_job_id"] == JID
    with pytest.raises(HostBoundaryError, match="NATIVE_LAUNCH_ALREADY_CLAIMED"):
        adapter.store.claim_native_launch(f.h.job_id, spec_sha256=f.h.spec.spec_sha256())
    result = HostDispatcher(adapter=adapter).ingest(
        f.h.job_id, fetcher=bridge, execute=True,
    )
    assert result["state"] == "COMPLETED"
    adapter.assert_hub_attested_for_export(f.h.job_id)
    resumed = resume_by_replay(adapter=adapter, host_job_id=f.h.job_id)
    assert resumed.mode == PHASE_B_REPLAY_VERIFIED
    assert resumed.need.request_id == waiting.need.request_id
    assert resumed.facts["wait_wave_id"] == original_wait_wave
    assert resumed.facts["wait_activation_id"] in {
        a.activation_id for a in original_wait_activation
    }
    assert len(resumed.facts["downstream_fired_threads"]) == 2
    assert resumed.facts["proposal_epistemic_level"] == "E5"
    assert sum(r["kind"] == "SUBMIT_ATTEMPTED"
               for r in adapter.store.submissions(f.h.job_id)) == 1
    assert f.calls == 1 and calls == []


def test_raw_native_and_unknown_submitters_fail_closed(tmp_path):
    f = FixtureHost(tmp_path)
    for submitter in (f.transport, SimpleNamespace(submit=lambda **kw: pytest.fail("called"))):
        result = HostDispatcher(adapter=f.h.adapter).dispatch(
            f.h.job_id, execute=True, submitter=submitter, authorization=f.auth,
        )
        assert result.state == "BLOCKED_EXTERNAL"
    assert f.calls == 0
    assert f.h.adapter.store.submissions(f.h.job_id) == []


def test_direct_native_requires_durable_claim(tmp_path):
    f = FixtureHost(tmp_path)
    with pytest.raises(HostBoundaryError, match="NATIVE_DISPATCH_CLAIM_REQUIRED"):
        f.transport.submit(spec=f.h.spec, prompt=f.h.job.prompt_bytes)
    assert f.calls == 0


def test_route_registry_mismatch_refused_before_authorization(tmp_path, monkeypatch):
    f = FixtureHost(tmp_path)
    monkeypatch.setattr(f.h.adapter.registry, "provider_model_allowed", lambda *a: False)
    with pytest.raises(HostBoundaryError, match="HUB_PROVIDER_NOT_ALLOWED"):
        f.dispatch()
    assert f.calls == 0
    assert f.h.adapter.store.submissions(f.h.job_id) == []


@pytest.mark.parametrize("name", ["spec.json", "status.json", "receipt.json", "stdout.log"])
def test_hand_edited_original_cannot_be_admitted(tmp_path, name):
    f = FixtureHost(tmp_path)
    f.dispatch()
    (f.jobs / JID / name).write_bytes(b"{}")
    with pytest.raises(HostBoundaryError, match="NATIVE_ORIGINAL_DIGEST_MISMATCH"):
        HostDispatcher(adapter=f.h.adapter).ingest(f.h.job_id, fetcher=f.bridge, execute=True)
    assert f.h.adapter.store.get_terminal(f.h.job_id) is None


def test_forged_ledger_and_launch_cannot_authorize_paid_call(tmp_path):
    f = FixtureHost(tmp_path)
    path = f.ledger / f"{f.h.job_id}.launch.json"
    doc = json.loads(path.read_bytes())
    doc["body"]["authorization_sha256"] = "0" * 64
    f.write(path, doc)
    with pytest.raises(HostBoundaryError, match="NATIVE_ATTESTATION_FORGED"):
        f.dispatch()
    assert f.calls == 0 and f.h.adapter.store.submissions(f.h.job_id) == []


def test_unsigned_normalized_spool_cannot_replace_native_terminal(tmp_path):
    f = FixtureHost(tmp_path)
    f.dispatch()
    record, stdout = f.h.adapter.native_original(f.h.job_id)
    with pytest.raises(HostBoundaryError, match="NATIVE_TERMINAL_BINDING_MISMATCH"):
        f.h.adapter.ingest_hub_result(host_job_id=f.h.job_id,
                                      record=record.model_copy(update={"receipt_id": "fake"}),
                                      stdout=stdout)


def test_environment_echo_is_refused_before_claim_or_spawn(tmp_path):
    f = FixtureHost(tmp_path)
    f.transport.environ = {"SYNTHETIC_ENV": "sensitive-value-example"}
    with pytest.raises(HostBoundaryError, match="OUTBOUND_ENV_LEAK"):
        f.transport.submit(spec=f.h.spec, prompt=b"sensitive-value-example")
    assert f.calls == 0 and f.h.adapter.store.submissions(f.h.job_id) == []


@pytest.mark.parametrize("field,value,code", [
    ("hub_instance_id", "other-host", "NATIVE_ATTESTATION_BINDING_MISMATCH"),
    ("original_spec_sha256", "0" * 64, "NATIVE_ATTESTATION_BINDING_MISMATCH"),
    ("nonce", "replayed-nonce", "NATIVE_ISSUANCE_NOT_AFTER_CLAIM"),
    ("issued_at", "2000-01-01T00:00:00Z", "NATIVE_ISSUANCE_NOT_AFTER_CLAIM"),
    ("native_job_id", "jx-abc123", "NATIVE_JOB_ID_INVALID"),
])
def test_wrong_host_replay_backdated_and_invalid_id_are_rejected(tmp_path, field, value, code):
    f = FixtureHost(tmp_path, outcome="ghost")
    f.dispatch()
    path = f.ledger / f"{f.h.job_id}.admission.json"
    body = json.loads(path.read_bytes())["body"]
    body[field] = value
    f.sign("admission", body)
    with pytest.raises(HostBoundaryError, match=code):
        f.bridge.recover(f.h.job_id)
    assert f.h.adapter.store.native_binding(f.h.job_id) is None
    assert f.calls == 1


def test_unbound_ghost_cannot_ingest_normalized_spool(tmp_path):
    f = FixtureHost(tmp_path, outcome="ghost")
    f.dispatch()
    stdout = good_stdout(f.h.carriers)
    record = make_record(f.h.spec, stdout, mac_key=f.h.mac_key)
    with pytest.raises(HostBoundaryError, match="NATIVE_JOB_NOT_BOUND"):
        f.h.adapter.ingest_hub_result(host_job_id=f.h.job_id, record=record, stdout=stdout)
    assert f.h.adapter.store.get_terminal(f.h.job_id) is None


def test_installation_pin_drift_fails_before_paid_call(tmp_path):
    f = FixtureHost(tmp_path)
    f.transport.launcher.executor.write_bytes(b"changed official source")
    with pytest.raises(HostBoundaryError, match="NATIVE_LAUNCHER_PIN_MISMATCH"):
        f.dispatch()
    assert f.calls == 0 and f.h.adapter.store.submissions(f.h.job_id) == []


def test_racing_dispatchers_cannot_both_launch(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    f = FixtureHost(tmp_path)

    def dispatch():
        try:
            return f.dispatch().state
        except HostBoundaryError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: dispatch(), range(2)))
    assert outcomes.count("SUBMITTED") == 1
    assert set(outcomes) <= {"SUBMITTED", "ALREADY_SUBMITTED", "SUBMISSION_STATE_AMBIGUOUS"}
    assert f.calls == 1
