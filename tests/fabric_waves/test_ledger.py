"""Tests for the append-only run ledger."""

from __future__ import annotations

import pytest

from seshat.fabric_waves.contracts import (
    ActivationOutcome,
    ActivationRecord,
    EventRecord,
    StoneEventKind,
    WaveRecord,
)
from seshat.fabric_waves.ledger import (
    LedgerConsistencyError,
    RunLedger,
    hash_mapping,
)


def _activation(*, activation_id: str = "a1", wave_id: str = "w1") -> ActivationRecord:
    return ActivationRecord(
        activation_id=activation_id,
        run_id="r1",
        wave_id=wave_id,
        thread_id="t1",
        started_at_tick=1,
        ended_at_tick=2,
        outcome=ActivationOutcome.FIRED,
        receipts_hash="0" * 64,
    )


def _wave(*, wave_id: str = "w1") -> WaveRecord:
    return WaveRecord(
        wave_id=wave_id,
        run_id="r1",
        wave_index=1,
        triggered_by=StoneEventKind.QUERY,
        triggering_event_id="e1",
    )


def _event(*, event_id: str = "e1") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        run_id="r1",
        issued_at_tick=1,
        kind=StoneEventKind.QUERY,
        payload_hash="0" * 64,
        kind_enum=StoneEventKind.QUERY,
    )


def test_append_only_rejects_duplicate_activation_id() -> None:
    ledger = RunLedger()
    ledger.append_activation(_activation())
    with pytest.raises(LedgerConsistencyError):
        ledger.append_activation(_activation())


def test_hash_chain_changes_when_record_added() -> None:
    ledger = RunLedger()
    head0 = ledger.head_hash
    ledger.append_activation(_activation())
    head1 = ledger.head_hash
    assert head0 != head1


def test_verify_succeeds_for_clean_ledger() -> None:
    ledger = RunLedger()
    ledger.append_activation(_activation())
    ledger.append_event(_event())
    ledger.verify()


def test_serialized_view_includes_head_hash() -> None:
    ledger = RunLedger()
    ledger.append_activation(_activation())
    snapshot = ledger.serialize()
    assert snapshot["head_hash"] == ledger.head_hash
    assert len(snapshot["activations"]) == 1


def test_activations_indexed_by_wave() -> None:
    ledger = RunLedger()
    ledger.append_activation(_activation(activation_id="a-w1", wave_id="w1"))
    ledger.append_activation(_activation(activation_id="a-w2", wave_id="w2"))
    assert {a.activation_id for a in ledger.activations_for_wave("w1")} == {"a-w1"}


def test_hash_mapping_is_deterministic() -> None:
    a = hash_mapping({"k": 1, "j": 2})
    b = hash_mapping({"j": 2, "k": 1})
    assert a == b