"""Regression tests for independent review blockers P1-01 .. P2-09."""

from __future__ import annotations

import json

import pytest

from seshat.contracts import AcceptanceState, RawAccessPolicy
from seshat.fabric_waves.contracts import (
    MethodBodyRef,
    PropagationLaw,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WaveBudget,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.decision_gate import accept_with_attestation, synthetic_test_attestation
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import (
    assemble_spec_law_map,
    carrier,
    corpus_aggregate_thread,
    sum_thread,
    uppercase_thread,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.fabric_waves.stone import StoneDispatcher


def test_p1_04_transitive_invalidation_a_b_c() -> None:
    sediment = SedimentState()
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")

    def rec(sid: str, reads: tuple[str, ...] = (), carriers: tuple[str, ...] = ()) -> SedimentRecord:
        return SedimentRecord(
            sediment_id=sid,
            object_type="safe.test",
            version="v1",
            research_object_id="r",
            payload={"id": sid},
            payload_hash=payload_hash({"id": sid}),
            provenance=("t",),
            method_body_refs=(body,),
            source_carrier_refs=carriers,
            read_dependencies=reads,
            produced_by_thread="t",
            produced_at_tick=1,
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.QUERY,
        )

    sediment.deposit(rec("a", carriers=("c1",)))
    sediment.deposit(rec("b", reads=("a",)))
    sediment.deposit(rec("c", reads=("b",)))
    sediment.invalidate_dependents("a", reason="rev")
    states = {r.sediment_id: r.acceptance_state for r in sediment.all_records()}
    assert states["b"] is AcceptanceState.STALE
    assert states["c"] is AcceptanceState.STALE


def test_p1_01_dependent_thread_wakes_after_sediment_produced() -> None:
    sum_spec, sum_law = sum_thread(carrier_id="c1", thread_id="t-sum")
    corpus_spec, corpus_law = corpus_aggregate_thread(corpus_id="corp", thread_id="t-corpus")
    specs, laws = assemble_spec_law_map([(sum_spec, sum_law), (corpus_spec, corpus_law)])
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )
    engine.run(
        run_id="r",
        budget=WaveBudget(max_waves=6, max_activations=8, max_stone_events=8),
        initial_stone=StoneEvent(
            event_id="r:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"values": [2, 3]},
        ),
    )
    sediment_events = [
        e for e in engine.ledger.events if e.kind is StoneEventKind.SEDIMENT_AVAILABLE
    ]
    assert sediment_events, "expected causal SEDIMENT_AVAILABLE events"
    corpus_waves = [
        w
        for w in engine.ledger.waves
        if "t-corpus" in w.fired_thread_ids or "t-corpus" in w.eligible_thread_ids
    ]
    assert len(corpus_waves) >= 1


def test_p1_03_source_delta_run_does_not_inject_query() -> None:
    spec_upper, law_upper = uppercase_thread(carrier_id="c-upper", text="hi", thread_id="t-upper")
    spec_sum, law_sum = sum_thread(carrier_id="c-other", thread_id="t-sum")
    specs, laws = assemble_spec_law_map([(spec_upper, law_upper), (spec_sum, law_sum)])
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="delta-only",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=1,
            target_carrier_id="c-upper",
            payload={"new_version": "v2", "text": "revised"},
        )
    )
    engine.run(
        run_id="r-delta",
        budget=WaveBudget(max_waves=3, max_activations=6, max_stone_events=3),
        auto_answer=False,
    )
    kinds = [e.kind for e in engine.ledger.events if e.run_id == "r-delta"]
    assert StoneEventKind.QUERY not in kinds


def test_p1_05_two_node_thread_respects_max_activations_one() -> None:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    nodes = (
        ThreadNodeSpec(
            node_id="n1",
            operation_id="safe.no-op",
            output_sediment_type="safe.noop",
            method_body_ref=body,
        ),
        ThreadNodeSpec(
            node_id="n2",
            operation_id="safe.no-op",
            output_sediment_type="safe.noop",
            method_body_ref=body,
        ),
    )
    spec = WorkflowThreadSpec(
        thread_id="t-two",
        name="two-node",
        purpose="budget probe",
        method_body_refs=(body,),
        nodes=nodes,
        exit_criterion="done",
    )
    law = PropagationLaw(thread_id="t-two")
    engine = WaveEngine(
        thread_specs={"t-two": spec},
        propagation_laws={"t-two": law},
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
    )
    run = engine.run(
        run_id="r",
        budget=WaveBudget(max_waves=2, max_activations=1, max_stone_events=4),
    )
    assert run.activations_total == 1


def test_p1_08_secret_not_in_ledger_export() -> None:
    from dataclasses import dataclass

    from seshat.fabric_waves.method_body import BodyInvocation, BodyResult

    secret = "TOP_SECRET_PROVIDER_LEAK"

    @dataclass(frozen=True)
    class _LeakyBody:
        method_body_id: str = "safe-fixture.leaky"
        version: str = "1"

        def __call__(self, invocation: BodyInvocation) -> BodyResult:
            raise RuntimeError(secret)

    body = MethodBodyRef(method_body_id="safe-fixture.leaky", version="1")
    node = ThreadNodeSpec(
        node_id="n",
        operation_id="safe.leaky",
        output_sediment_type="safe.noop",
        method_body_ref=body,
    )
    spec = WorkflowThreadSpec(
        thread_id="t",
        name="leaky",
        purpose="error sanitization probe",
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="x",
    )
    law = PropagationLaw(thread_id="t")
    registry = build_safe_fixture_registry()
    registry.register(_LeakyBody())
    engine = WaveEngine(
        thread_specs={"t": spec},
        propagation_laws={"t": law},
        sediment=SedimentState(),
        bodies=registry,
    )
    engine.run(
        run_id="r",
        budget=WaveBudget(max_waves=1, max_activations=2, max_stone_events=2),
    )
    blob = json.dumps(engine.ledger.serialize())
    assert secret not in blob


def test_p1_07_stale_cannot_be_accepted_without_attestation() -> None:
    sediment = SedimentState()
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    record = SedimentRecord(
        sediment_id="s",
        object_type="safe.test",
        version="v1",
        research_object_id="r",
        payload={},
        payload_hash=payload_hash({}),
        provenance=("t",),
        method_body_refs=(body,),
        acceptance_state=AcceptanceState.STALE,
        produced_by_thread="t",
        produced_at_tick=1,
        produced_in_wave=1,
        produced_by_stone_kind=StoneEventKind.QUERY,
    )
    sediment.deposit(record)
    attestation = synthetic_test_attestation("d1", "s")
    from seshat.fabric_waves.sediment import SedimentCollisionError

    with pytest.raises(SedimentCollisionError):
        accept_with_attestation(sediment, attestation, decided_at_tick=2)


def test_p1_02_full_required_blocks_stone_payload_text() -> None:
    src, content = carrier(carrier_id="c1", version="v1", text="trusted")
    store = FabricCarrierStore(carriers={"c1": src}, contents={"c1": content})
    spec, law = uppercase_thread(carrier_id="c1", text="ignored", thread_id="t")
    spec = spec.model_copy(update={"raw_access_policy": RawAccessPolicy.FULL_REQUIRED})
    specs, laws = assemble_spec_law_map([(spec, law)])
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
        carrier_store=store,
    )
    engine.run(
        run_id="r",
        budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
        initial_stone=StoneEvent(
            event_id="r:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"text": "UNTRUSTED_SECRET"},
        ),
    )
    upper = next(r for r in engine.sediment.all_records() if r.object_type == "safe.uppercase_text")
    assert upper.payload["value"] == "TRUSTED"
