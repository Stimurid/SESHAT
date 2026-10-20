"""Portable red oracles: use only APIs present in rejected parent b0793b3.

Copy this file alone outside the checkout to test the parent installed wheel.
No new scenario/contract imports: failures must concern behavior, not collection.
"""
import pytest

from seshat.contracts import AcceptanceState, RawAccessPolicy
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import carrier, uppercase_thread
from seshat.fabric_waves.ledger import LedgerConsistencyError
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore


def seed(sid, reads=(), state=AcceptanceState.WORKING):
    return SedimentRecord(sediment_id=sid, object_type="test", version="1", research_object_id="r",
        payload={}, payload_hash=payload_hash({}), provenance=("fixture",),
        read_dependencies=reads, acceptance_state=state, produced_by_thread="fixture",
        produced_at_tick=0, produced_in_wave=1, produced_by_stone_kind=StoneEventKind.QUERY)


def test_parent_full_required_no_store_cannot_execute():
    spec, law = uppercase_thread(carrier_id="c", text="ignored")
    spec.raw_access_policy = RawAccessPolicy.FULL_REQUIRED
    engine = WaveEngine(thread_specs={spec.thread_id: spec}, propagation_laws={spec.thread_id: law},
        sediment=SedimentState(), bodies=build_safe_fixture_registry())
    engine.run(run_id="r", budget=WaveBudget(max_waves=3, max_activations=3, max_stone_events=3),
        initial_stone=StoneEvent(event_id="e", kind=StoneEventKind.QUERY, issued_at_tick=0,
                                payload={"text": "SYNTHETIC_SECRET"}))
    assert not engine.sediment.all_records()
    assert engine.ledger.activations[0].outcome.value == "BLOCKED_SOURCE"


def test_parent_source_delta_does_not_mint_authority():
    src, content = carrier(carrier_id="c", version="1", text="old")
    store = FabricCarrierStore(carriers={"c": src}, contents={"c": content})
    with pytest.raises(ValueError):
        store.apply_delta("c", new_version="2", new_text="unverified")
    assert store.carriers_for(("c",))[0].version == "1"


def test_parent_stale_middle_does_not_stop_invalidation():
    state = SedimentState()
    for record in (seed("A"), seed("B", ("A",), AcceptanceState.STALE), seed("C", ("B",))):
        state.deposit(record)
    state.invalidate_dependents("A", reason="changed")
    assert "C" in state.views["stale"]


def test_parent_bare_accept_is_denied():
    state = SedimentState()
    state.deposit(seed("A"))
    with pytest.raises(ValueError):
        state.accept("A", decision_id="pretend-human", decided_at_tick=1)


def test_parent_tail_removal_fails_verification():
    spec, law = uppercase_thread(carrier_id="c", text="ignored")
    engine = WaveEngine(thread_specs={spec.thread_id: spec}, propagation_laws={spec.thread_id: law},
        sediment=SedimentState(), bodies=build_safe_fixture_registry())
    engine.run(run_id="r", budget=WaveBudget(max_waves=3, max_activations=3, max_stone_events=3))
    engine.ledger._runs.pop()
    with pytest.raises(LedgerConsistencyError):
        engine.ledger.verify()
