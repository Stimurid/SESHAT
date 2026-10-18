"""Fail-closed guards for native Hub dispatch and pre-seal store formats."""

from __future__ import annotations

import sqlite3

import pytest

from seshat.fabric_waves.external_carrier.host_dispatcher import (
    AiyeExecSubmitter,
    HostDispatcher,
    build_aiye_exec_argv,
)
from seshat.fabric_waves.external_carrier import phase_b
from seshat.fabric_waves.external_carrier.host_security import HostBoundaryError, HostIntegrityKey
from seshat.fabric_waves.external_carrier.host_store import (
    HostJobStore, STORE_FILENAME, _row_material,
)
from seshat.fabric_waves.external_carrier.hub_protocol import HubTransportError

from .phase_b_harness import MAC_KEY_BYTES, make_auth, make_harness


def test_environment_cannot_unlock_unverified_native_submit(tmp_path, monkeypatch):
    harness = make_harness(tmp_path)
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("native process must never start")

    submitter = AiyeExecSubmitter(
        exe=str(tmp_path / "aiye-exec"), spool_dir=tmp_path / "spool", runner=runner
    )
    with pytest.raises(HubTransportError, match="PROTOCOL_UNVERIFIED"):
        submitter.submit(spec=harness.spec, prompt=harness.job.prompt_bytes)
    with pytest.raises(HostBoundaryError, match="PROTOCOL_UNVERIFIED"):
        build_aiye_exec_argv(
            exe=str(tmp_path / "aiye-exec"), spec=harness.spec, prompt_path=tmp_path / "prompt"
        )
    assert calls == []
    assert not (tmp_path / "spool").exists()


def test_manual_ack_cannot_mint_hub_spool_artifact(tmp_path):
    harness = make_harness(tmp_path)
    harness.complete()
    harness.adapter.store.record_submission(harness.job_id, "SUBMIT_ACKED", {"local": True})
    result = phase_b.resume_live(harness.waiting, adapter=harness.adapter,
                                 host_job_id=harness.job_id)
    with pytest.raises(HostBoundaryError, match="HUB_TRANSPORT_UNATTESTED"):
        phase_b.export_phase_b_artifacts(
            tmp_path / "forged-export", result=result, adapter=harness.adapter,
            host_job_id=harness.job_id, transport_kind=phase_b.TRANSPORT_KIND_HUB_SPOOL_RECORD
        )
    assert not (tmp_path / "forged-export").exists()


def test_oserror_after_attempt_is_ambiguous_and_cannot_retry(tmp_path):
    harness = make_harness(tmp_path)

    class StartedThenFailed:
        def submit(self, *, spec, prompt):
            raise OSError("child status unknown")

    dispatcher = HostDispatcher(synthetic_only=True, adapter=harness.adapter)
    first = dispatcher.dispatch(harness.job_id, execute=True,
                                submitter=StartedThenFailed(),
                                authorization=make_auth(harness.spec))
    assert first.state == "AMBIGUOUS" and first.detail == "SUBMIT_OSERROR_AMBIGUOUS"
    with pytest.raises(HostBoundaryError, match="SUBMISSION_STATE_AMBIGUOUS"):
        dispatcher.dispatch(harness.job_id, execute=True,
                            submitter=StartedThenFailed(),
                            authorization=make_auth(harness.spec, nonce="new-nonce"))


@pytest.mark.parametrize("keyed", [False, True])
def test_legacy_store_refused_without_touching_original_rows(tmp_path, keyed):
    directory = tmp_path / "store"
    directory.mkdir()
    db = directory / STORE_FILENAME
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        con.execute("INSERT INTO meta VALUES ('schema', 'seshat_host_job_store_v1')")
        if keyed:
            con.execute("INSERT INTO meta VALUES ('integrity_key_required', 'true')")
        con.execute("CREATE TABLE jobs (host_job_id TEXT PRIMARY KEY, request_bytes BLOB)")
        con.execute("INSERT INTO jobs VALUES ('old-job', ?)", (b'original-request',))
        con.execute("CREATE TABLE submissions (seq INTEGER PRIMARY KEY, detail_json TEXT)")
        con.execute("INSERT INTO submissions (detail_json) VALUES ('original-receipt')")
        con.execute("CREATE TABLE terminals (host_job_id TEXT PRIMARY KEY, stdout_bytes BLOB)")
        con.execute("INSERT INTO terminals VALUES ('old-job', ?)", (b'original-terminal',))
    before = db.read_bytes()
    key = HostIntegrityKey(MAC_KEY_BYTES) if keyed else None
    with pytest.raises(HostBoundaryError, match="HOST_STORE_LEGACY_MIGRATION_REQUIRED"):
        HostJobStore(directory, integrity_key=key)
    assert db.read_bytes() == before
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT request_bytes FROM jobs").fetchone() == (b"original-request",)
        assert con.execute("SELECT detail_json FROM submissions").fetchone() == (
            "original-receipt",
        )
        assert con.execute("SELECT stdout_bytes FROM terminals").fetchone() == (
            b"original-terminal",
        )


def test_rehashed_metadata_poison_and_deleted_key_marker_refused(tmp_path):
    harness = make_harness(tmp_path, mac=True)
    db = harness.adapter.store.path
    with sqlite3.connect(db) as con:
        at = con.execute(
            "SELECT at FROM meta WHERE k='integrity_key_required'"
        ).fetchone()[0]
        forged = _row_material("meta", {"k": "integrity_key_required", "v": "false"}, at)
        con.execute("DROP TRIGGER meta_no_update")
        con.execute(
            "UPDATE meta SET v='false', row_sha256=? WHERE k='integrity_key_required'",
            (forged,),
        )
    with pytest.raises(HostBoundaryError, match="HOST_STORE_METADATA_TAMPERED"):
        HostJobStore(db.parent, integrity_key=HostIntegrityKey(MAC_KEY_BYTES))

    # A second store shows deletion of the key marker also refuses before job access.
    other = make_harness(tmp_path / "deleted", mac=True)
    with sqlite3.connect(other.adapter.store.path) as con:
        con.execute("DROP TRIGGER meta_no_delete")
        con.execute("DELETE FROM meta WHERE k='integrity_key_required'")
    with pytest.raises(HostBoundaryError, match="HOST_STORE_INTEGRITY_UPGRADE_REQUIRED"):
        HostJobStore(other.adapter.store.path.parent,
                     integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
