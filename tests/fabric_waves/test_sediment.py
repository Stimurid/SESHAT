"""Tests for the sediment state and acceptance rules."""

from __future__ import annotations

import pytest

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import MethodBodyRef, StoneEventKind
from seshat.fabric_waves.sediment import (
    SedimentCollisionError,
    SedimentRecord,
    SedimentState,
    payload_hash,
)


def _record(
    *,
    sediment_id: str = "s1",
    payload: object = {"k": 1},
    source_carriers: tuple[str, ...] = (),
    reads: tuple[str, ...] = (),
    writes: tuple[str, ...] = (),
    state: AcceptanceState = AcceptanceState.WORKING,
) -> SedimentRecord:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    return SedimentRecord(
        sediment_id=sediment_id,
        object_type="safe.test",
        version="v1",
        research_object_id="r1",
        payload=payload,
        payload_hash=payload_hash(payload),
        provenance=("test",),
        method_body_refs=(body,),
        source_carrier_refs=source_carriers,
        read_dependencies=reads,
        write_dependencies=writes,
        acceptance_state=state,
        produced_by_thread="t1",
        produced_at_tick=1,
        produced_in_wave=1,
        produced_by_stone_kind=StoneEventKind.QUERY,
    )


def test_deposit_rejects_accepted_without_decision() -> None:
    sediment = SedimentState()
    with pytest.raises(SedimentCollisionError):
        sediment.deposit(_record(state=AcceptanceState.ACCEPTED))


def test_accept_requires_decision_id() -> None:
    sediment = SedimentState()
    sediment.deposit(_record())
    with pytest.raises(SedimentCollisionError):
        sediment.accept("s1", decision_id="", decided_at_tick=2)


def test_invalidating_dependents_marks_only_strict_dependents() -> None:
    sediment = SedimentState()
    sediment.deposit(_record(sediment_id="upstream", source_carriers=("c1",)))
    sediment.deposit(_record(sediment_id="downstream", reads=("upstream",)))
    sediment.deposit(_record(sediment_id="unrelated"))
    sediment.invalidate_dependents("upstream", reason="c1-revised")
    states = {
        record.sediment_id: record.acceptance_state
        for record in sediment.all_records()
    }
    assert states["upstream"] is AcceptanceState.WORKING  # upstream itself not auto-stale
    assert states["downstream"] is AcceptanceState.STALE
    assert states["unrelated"] is AcceptanceState.WORKING


def test_version_map_keys_unique() -> None:
    sediment = SedimentState()
    sediment.deposit(_record(sediment_id="a"))
    sediment.deposit(_record(sediment_id="b"))
    versions = sediment.version_map()
    assert versions == {"a": "v1", "b": "v1"}


def test_history_preserved_after_invalidation() -> None:
    sediment = SedimentState()
    sediment.deposit(_record(sediment_id="u"))
    sediment.deposit(_record(sediment_id="d", reads=("u",)))
    sediment.invalidate_dependents("u", reason="test")
    history = sediment.history("d")
    assert [record.acceptance_state for record in history] == [
        AcceptanceState.WORKING,
        AcceptanceState.STALE,
    ]