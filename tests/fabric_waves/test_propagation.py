"""Tests for the propagation / invalidation layer."""

from __future__ import annotations

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    MethodBodyRef,
    PropagationLaw,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.fixtures import uppercase_thread
from seshat.fabric_waves.propagation import (
    invalidate_cascade,
    threads_woken_by_carrier_delta,
    threads_woken_by_event,
)
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash


def _record(*, sediment_id: str = "s1", carriers: tuple[str, ...] = ()) -> SedimentRecord:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    return SedimentRecord(
        sediment_id=sediment_id,
        object_type="o",
        version="v1",
        research_object_id="r1",
        payload={"k": 1},
        payload_hash=payload_hash({"k": 1}),
        provenance=("t",),
        method_body_refs=(body,),
        source_carrier_refs=carriers,
        produced_by_thread="t1",
        produced_at_tick=0,
        produced_in_wave=1,
        produced_by_stone_kind=StoneEventKind.QUERY,
        acceptance_state=AcceptanceState.WORKING,
    )


def test_threads_woken_only_by_matching_carrier() -> None:
    spec_a, law_a = uppercase_thread(carrier_id="c1", text="x", thread_id="A")
    spec_b, law_b = uppercase_thread(carrier_id="c2", text="x", thread_id="B")
    woken = threads_woken_by_carrier_delta(
        carrier_id="c1",
        thread_specs={"A": spec_a, "B": spec_b},
        propagation_laws={"A": law_a, "B": law_b},
        sediment=SedimentState(),
    )
    assert woken == ("A",)


def test_threads_woken_by_event_match_kind_and_target() -> None:
    spec_a, law_a = uppercase_thread(carrier_id="c1", text="x", thread_id="A")
    spec_b, law_b = uppercase_thread(carrier_id="c2", text="x", thread_id="B")
    laws = {"A": law_a, "B": law_b}
    specs = {"A": spec_a, "B": spec_b}
    event = StoneEvent(
        event_id="e1",
        kind=StoneEventKind.SOURCE_DELTA,
        issued_at_tick=1,
        target_carrier_id="c1",
    )
    woken = threads_woken_by_event(event=event, thread_specs=specs, propagation_laws=laws)
    assert woken == ("A",)


def test_invalidate_cascade_only_marks_records_with_carrier() -> None:
    sediment = SedimentState()
    sediment.deposit(_record(sediment_id="touches", carriers=("c1",)))
    sediment.deposit(_record(sediment_id="does-not"))
    invalidate_cascade(carrier_id="c1", sediment=sediment)
    states = {record.sediment_id: record.acceptance_state for record in sediment.all_records()}
    assert states["touches"] is AcceptanceState.STALE
    assert states["does-not"] is AcceptanceState.WORKING


def test_propagation_law_initial_state_blocks_dead_threads() -> None:
    spec = WorkflowThreadSpec(
        thread_id="T",
        name="T",
        purpose="p",
        nodes=(
            ThreadNodeSpec(node_id="n", operation_id="o", output_sediment_type="x"),
        ),
        exit_criterion="x",
    )
    law = PropagationLaw(
        thread_id="T",
        wakes_on_carrier_ids=("c1",),
        initial_state=("seed",),
    )
    sediment = SedimentState()
    woken = threads_woken_by_carrier_delta(
        carrier_id="c1",
        thread_specs={"T": spec},
        propagation_laws={"T": law},
        sediment=sediment,
    )
    assert woken == ()