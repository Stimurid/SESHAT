"""The checkpoint must carry real continuation state and refuse bad input.

A JSON blob holding two counters would pass none of these.
"""

import json
from pathlib import Path

import pytest

from seshat.fabric_waves.m5_checkpoint import (
    CheckpointRejected,
    M5Checkpoint,
    load_checkpoint,
    owner_token,
    reconcile_pending,
    restore_ledger,
    stone_fingerprint,
    write_checkpoint,
)
from seshat.fabric_waves.m5_room_carpet import (
    _checkpoint_for,
    load_fixture,
    run_world,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m5_room_synthetic_acceptance_20261021_v01.json"
)


@pytest.fixture(scope="module")
def worlds():
    data, digest = load_fixture(FIXTURE)
    out = []
    for host in data["hosts"]:
        world = run_world(host, fixture=data, fixture_sha256=digest)
        out.append((world, _checkpoint_for(world)))
    return out


def test_checkpoint_carries_continuation_state_not_counters(worlds):
    _world, checkpoint = worlds[0]
    assert checkpoint.sediment_records, "sediment must be retained"
    assert checkpoint.sediment_producers, "producer links must be retained"
    assert checkpoint.ledger["append_order"], "ledger append order must be retained"
    assert checkpoint.source_versions, "current source versions must be retained"
    assert checkpoint.stone_fingerprints, "processed stone fingerprints must be retained"
    assert checkpoint.budget["max_waves"] >= 1
    assert checkpoint.run_results
    assert checkpoint.stone_cursor == len(checkpoint.processed_stone_ids)


def test_ledger_round_trips_through_its_append_order(worlds):
    world, checkpoint = worlds[0]
    restored = restore_ledger(checkpoint.ledger, expected_head=checkpoint.ledger_head_hash)
    assert restored.head_hash == world.engine.ledger.head_hash
    assert [a.activation_id for a in restored.activations] == [
        a.activation_id for a in world.engine.ledger.activations
    ]


def test_source_delta_is_recorded_so_versions_can_be_rebuilt(worlds):
    _world, checkpoint = worlds[0]
    assert checkpoint.applied_source_deltas, "the delta stone must be recorded"
    delta = checkpoint.applied_source_deltas[0]
    assert delta.old_version != delta.new_version
    # The post-delta version is what the checkpoint claims as current.
    assert checkpoint.source_versions[delta.carrier_id] == delta.new_version


def test_a_corrupted_checkpoint_is_rejected(tmp_path, worlds):
    _world, checkpoint = worlds[0]
    path = tmp_path / "cp.json"
    write_checkpoint(path, checkpoint)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stone_cursor"] = int(data["stone_cursor"]) + 7
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CheckpointRejected, match="CHECKSUM_INVALID"):
        load_checkpoint(path)


def test_a_malformed_checkpoint_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": "nope"}', encoding="utf-8")
    with pytest.raises(CheckpointRejected, match="MALFORMED"):
        load_checkpoint(path)


def test_a_foreign_hosts_checkpoint_is_refused(worlds):
    world_a, _ = worlds[0]
    _world_b, checkpoint_b = worlds[1]
    with pytest.raises(CheckpointRejected, match="FOREIGN_HOST"):
        checkpoint_b.verify_owner(
            host_id=str(world_a.host["host_id"]), fixture_sha256=world_a.fixture_sha256
        )
    # And it verifies fine for its own owner: this is ownership, not corruption.
    checkpoint_b.verify_owner(
        host_id=str(_world_b.host["host_id"]), fixture_sha256=_world_b.fixture_sha256
    )


def test_a_checkpoint_from_another_fixture_is_refused(worlds):
    world, checkpoint = worlds[0]
    with pytest.raises(CheckpointRejected, match="FOREIGN_FIXTURE"):
        checkpoint.verify_owner(host_id=str(world.host["host_id"]), fixture_sha256="f" * 64)


def test_owner_token_binds_host_and_fixture():
    a = owner_token(host_id="H1", fixture_sha256="a" * 64)
    assert a != owner_token(host_id="H2", fixture_sha256="a" * 64)
    assert a != owner_token(host_id="H1", fixture_sha256="b" * 64)


def test_tampered_ledger_head_cannot_be_restored(worlds):
    _world, checkpoint = worlds[0]
    bad = dict(checkpoint.ledger)
    bad["head_hash"] = "0" * 64
    with pytest.raises(Exception):
        restore_ledger(bad, expected_head="0" * 64)


def test_an_interrupted_checkpoint_is_not_silently_replayed(worlds):
    world, _ = worlds[0]
    interrupted = _checkpoint_for(world, completed=False).model_copy()
    assert interrupted.completed is False
    with pytest.raises(CheckpointRejected, match="REQUIRES_RECONCILIATION"):
        run_world(
            world.host,
            fixture={"thread_registry": [], "stop_policy": {}},
            fixture_sha256=world.fixture_sha256,
            resume_from=interrupted,
        )


def test_pending_stone_requires_an_explicit_decision(worlds):
    world, _ = worlds[0]
    interrupted = _checkpoint_for(world, completed=False)
    with pytest.raises(CheckpointRejected, match="RECONCILE_UNKNOWN"):
        reconcile_pending(interrupted, decision="JUST_GUESS")
    resolved = reconcile_pending(interrupted, decision="DISCARD_PENDING_STONE")
    assert resolved.completed is True
    resolved.verify_checksum()


def test_stone_fingerprint_binds_the_state_it_applies_to():
    stone = {"stone_id": "A1", "kind": "QUERY", "question": "q"}
    a = stone_fingerprint(stone, source_versions={"c": "A1"})
    b = stone_fingerprint(stone, source_versions={"c": "A2"})
    assert a != b, "the same stone against different sources is different work"
    assert a == stone_fingerprint(stone, source_versions={"c": "A1"})


def test_checkpoint_is_integrity_only_not_external_authority(worlds):
    world, checkpoint = worlds[0]
    checkpoint.verify_checksum()
    # Verifying one's own checkpoint promotes nothing.
    assert len(world.engine.sediment.views["accepted"]) == 0


def test_write_is_atomic_and_read_back(tmp_path, worlds):
    _world, checkpoint = worlds[0]
    path = tmp_path / "nested" / "cp.json"
    write_checkpoint(path, checkpoint)
    assert path.is_file()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert load_checkpoint(path).ledger_head_hash == checkpoint.ledger_head_hash


def test_checkpoint_model_rejects_unknown_fields():
    with pytest.raises(Exception):
        M5Checkpoint.model_validate({"schema_version": "x", "unexpected": 1})
