"""Tests for frontier selection and conditional edges."""

from __future__ import annotations

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    EdgeCondition,
    MethodBodyRef,
    PropagationLaw,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.frontier import (
    LexicographicFrontierStrategy,
    select_frontier,
)
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash


def _spec(
    *, thread_id: str, carrier_id: str = "c1", condition: EdgeCondition | None = None
) -> WorkflowThreadSpec:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    node = ThreadNodeSpec(
        node_id="noop",
        operation_id="safe.no-op",
        output_sediment_type="safe.noop",
        conditions=(condition,) if condition else (),
    )
    return WorkflowThreadSpec(
        thread_id=thread_id,
        name=thread_id,
        purpose="t",
        admissible_source_carriers=(carrier_id,),
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="x",
    )


def _law(thread_id: str, *, carrier_id: str = "c1", initial: tuple[str, ...] = ()) -> PropagationLaw:
    return PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(carrier_id,),
        wakes_on_stone_kinds=(StoneEventKind.QUERY,),
        initial_state=initial,
    )


def test_select_frontier_returns_only_threads_with_satisfied_law() -> None:
    spec_a = _spec(thread_id="A", carrier_id="c1")
    spec_b = _spec(thread_id="B", carrier_id="c2")
    specs = {"A": spec_a, "B": spec_b}
    laws = {
        "A": _law("A", carrier_id="c1"),
        "B": _law("B", carrier_id="c2"),
    }
    event = StoneEvent(
        event_id="e1",
        kind=StoneEventKind.QUERY,
        issued_at_tick=1,
        target_carrier_id="c1",
    )
    frontier = select_frontier(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        event=event,
    )
    assert {item.thread_id for item in frontier} == {"A"}


def test_strategic_cannot_widen_the_frontier() -> None:
    from seshat.fabric_waves.contracts import FrontierProposal

    specs = {"A": _spec(thread_id="A")}
    laws = {"A": _law("A")}

    class BadStrategy:
        def choose(self, **kwargs):
            return (FrontierProposal(thread_id="B", reason="forged"),)

    with __import__("pytest").raises(ValueError):
        select_frontier(
            thread_specs=specs,
            propagation_laws=laws,
            sediment=SedimentState(),
            event=StoneEvent(
                event_id="e1",
                kind=StoneEventKind.QUERY,
                issued_at_tick=1,
            ),
            strategy=BadStrategy(),
        )


def test_lexicographic_strategy_is_deterministic() -> None:
    strategy = LexicographicFrontierStrategy()
    result_a = strategy.choose(
        thread_specs={"B": _spec(thread_id="B"), "A": _spec(thread_id="A")},
        propagation_laws={
            "A": _law("A"),
            "B": _law("B"),
        },
        sediment=SedimentState(),
        event=StoneEvent(event_id="e", kind=StoneEventKind.QUERY, issued_at_tick=0),
        last_wave_thread_ids=(),
    )
    assert [item.thread_id for item in result_a] == ["A", "B"]


def test_initial_state_required_blocks_thread() -> None:
    specs = {"A": _spec(thread_id="A")}
    laws = {"A": PropagationLaw(
        thread_id="A",
        wakes_on_carrier_ids=("c1",),
        initial_state=("seed",),
    )}
    frontier = select_frontier(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        event=None,
    )
    assert frontier == ()


def test_initial_state_satisfied_unlocks_thread() -> None:
    sediment = SedimentState()
    sediment.deposit(
        SedimentRecord(
            sediment_id="seed",
            object_type="safe.seed",
            version="v1",
            research_object_id="r1",
            payload={"x": 1},
            payload_hash=payload_hash({"x": 1}),
            provenance=("seed",),
            method_body_refs=(),
            produced_by_thread="t-seed",
            produced_at_tick=0,
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.QUERY,
            acceptance_state=AcceptanceState.WORKING,
        )
    )
    specs = {"A": _spec(thread_id="A")}
    laws = {"A": PropagationLaw(
        thread_id="A",
        wakes_on_carrier_ids=("c1",),
        initial_state=("seed",),
    )}
    frontier = select_frontier(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=sediment,
        event=None,
    )
    assert {item.thread_id for item in frontier} == {"A"}


def test_condition_requires_sediment_acceptance() -> None:
    sediment = SedimentState()
    sediment.deposit(
        SedimentRecord(
            sediment_id="x",
            object_type="o",
            version="v1",
            research_object_id="r1",
            payload={},
            payload_hash=payload_hash({}),
            provenance=("seed",),
            method_body_refs=(),
            produced_by_thread="t-seed",
            produced_at_tick=0,
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.QUERY,
            acceptance_state=AcceptanceState.WORKING,
        )
    )
    cond = EdgeCondition(
        description="must be accepted",
        requires_sediment_id="x",
        requires_sediment_acceptance=AcceptanceState.ACCEPTED,
    )
    spec = _spec(thread_id="A", condition=cond)
    frontier = select_frontier(
        thread_specs={"A": spec},
        propagation_laws={"A": _law("A")},
        sediment=sediment,
        event=None,
    )
    assert frontier == ()


def test_engine_accepts_safe_registry() -> None:
    _ = build_safe_fixture_registry()