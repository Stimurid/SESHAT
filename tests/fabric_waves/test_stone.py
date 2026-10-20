"""Tests for the stone dispatcher."""

from __future__ import annotations

import pytest

from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveRecord
from seshat.fabric_waves.stone import StoneDispatcher, StoneQueueFull


def _stone(event_id: str = "e1", kind: StoneEventKind = StoneEventKind.QUERY) -> StoneEvent:
    return StoneEvent(event_id=event_id, kind=kind, issued_at_tick=1, payload={"k": 1})


def test_dispatcher_rejects_duplicate_event_ids() -> None:
    dispatcher = StoneDispatcher()
    dispatcher.drop(_stone())
    with pytest.raises(ValueError):
        dispatcher.drop(_stone())


def test_dispatcher_records_hash_in_envelope() -> None:
    dispatcher = StoneDispatcher()
    record = dispatcher.drop(_stone())
    assert len(record.payload_hash) == 64


def test_dispatcher_full_raises() -> None:
    dispatcher = StoneDispatcher(max_pending=1)
    dispatcher.drop(_stone(event_id="a"))
    with pytest.raises(StoneQueueFull):
        dispatcher.drop(_stone(event_id="b"))


def test_consume_binds_event_to_wave() -> None:
    dispatcher = StoneDispatcher()
    stone = _stone()
    envelope = dispatcher.drop(stone)
    wave = WaveRecord(
        wave_id="w1",
        run_id="r1",
        wave_index=1,
        triggered_by=stone.kind,
        triggering_event_id=stone.event_id,
    )
    event = dispatcher.consume_next(run_id="r1", wave=wave)
    assert event is not None
    assert envelope.kind_enum is stone.kind