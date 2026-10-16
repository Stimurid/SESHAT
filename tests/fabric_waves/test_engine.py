"""Tests for the deterministic wave engine."""

from __future__ import annotations

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    ACCEPTANCE_DECISION_RIGHT,
    ActivationOutcome,
    WaveBudget,
)
from seshat.fabric_waves.decision_gate import TrustedDecisionAttestation
from seshat.fabric_waves.scenarios import source_store
from seshat.fabric_waves.engine import WaveEngine, WaveEngineConfigurationError
from seshat.fabric_waves.fixtures import (
    assemble_spec_law_map,
    fail_closed_thread,
    no_op_thread,
    uppercase_thread,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import (
    build_safe_fixture_registry,
)
from seshat.fabric_waves.sediment import SedimentState
from seshat.fabric_waves.stone import StoneDispatcher


def _uppercase_engine(*, budget: WaveBudget | None = None) -> WaveEngine:
    spec, law = uppercase_thread(carrier_id="c1", text="hello")
    specs, laws = assemble_spec_law_map([(spec, law)])
    bodies = build_safe_fixture_registry()
    return WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
        carrier_store=source_store({"c1": "hello"}),
    )


def test_engine_runs_until_saturation() -> None:
    engine = _uppercase_engine()
    run = engine.run(
        run_id="r1",
        budget=WaveBudget(max_waves=4, max_activations=8, max_stone_events=4),
    )
    assert run.outcome.value == "CONVERGED"
    assert run.waves_emitted >= 1
    assert any(
        act.outcome is ActivationOutcome.FIRED
        for act in engine.ledger.activations
    )


def test_engine_rejects_unregistered_method_body() -> None:
    spec, law = uppercase_thread(carrier_id="c1", text="hello")
    spec = spec.model_copy(
        update={
            "method_body_refs": (
                spec.method_body_refs[0].model_copy(
                    update={"method_body_id": "not.registered", "version": "9"}
                ),
            )
        }
    )
    bodies = build_safe_fixture_registry()
    with __import__("pytest").raises(WaveEngineConfigurationError):
        WaveEngine(
            thread_specs={"t": spec},
            propagation_laws={"t": law},
            sediment=SedimentState(),
            bodies=bodies,
        )


def test_engine_records_human_decision_and_promotes_to_accepted() -> None:
    engine = _uppercase_engine()
    engine.run(
        run_id="r1",
        budget=WaveBudget(max_waves=2, max_activations=4, max_stone_events=2),
    )
    produced = next(
        record
        for record in engine.sediment.all_records()
        if record.object_type == "safe.uppercase_text"
    )
    attestation = TrustedDecisionAttestation(decision_id="d1",
        subject_sediment_id=produced.sediment_id, subject_version=produced.version,
        choice="ACCEPT", issuer="external-test-idp", decided_by="test-human",
        decision_right=ACCEPTANCE_DECISION_RIGHT, nonce="test-nonce", attestation_token="test-signature")
    engine.decision_verifier = lambda envelope: envelope == attestation
    decision = engine.record_human_decision(
        run_id="r1",
        decision_id="d1",
        subject_sediment_id=produced.sediment_id,
        choice="ACCEPT",
        rationale="human acceptance",
        accepts=(produced.sediment_id,),
        attestation=attestation,
    )
    assert decision.decided_by == "test-human"
    promoted = engine.sediment.views["accepted"].get(produced.sediment_id)
    assert promoted is not None
    assert promoted.acceptance_state is AcceptanceState.ACCEPTED


def test_engine_replay_is_deterministic() -> None:
    engine_a = _uppercase_engine()
    engine_a.run(
        run_id="r1",
        budget=WaveBudget(max_waves=2, max_activations=4, max_stone_events=2),
    )
    engine_b = _uppercase_engine()
    engine_b.run(
        run_id="r1",
        budget=WaveBudget(max_waves=2, max_activations=4, max_stone_events=2),
    )
    final_versions_a = {k: v for k, v in engine_a.sediment.version_map().items()}
    final_versions_b = {k: v for k, v in engine_b.sediment.version_map().items()}
    assert final_versions_a == final_versions_b
    assert engine_a.ledger.head_hash == engine_b.ledger.head_hash


def test_engine_budget_exhaustion_stops_run() -> None:
    spec, law = uppercase_thread(carrier_id="c1", text="x")
    specs, laws = assemble_spec_law_map([(spec, law)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    run = engine.run(
        run_id="r-budget",
        budget=WaveBudget(max_waves=2, max_activations=1, max_stone_events=2),
    )
    assert run.activations_total <= 1


def test_engine_records_aporia_via_fail_closed_body() -> None:
    spec, law = fail_closed_thread()
    specs, laws = assemble_spec_law_map([(spec, law)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    run = engine.run(
        run_id="r-aporia",
        budget=WaveBudget(
            max_waves=2,
            max_activations=2,
            max_stone_events=1,
            aporia_after_waves=1,
        ),
    )
    assert run.outcome.value == "APORIA"
    assert any(
        record.object_type == "safe.aporia" for record in engine.sediment.all_records()
    )


def test_engine_no_op_thread_yields_no_delta() -> None:
    spec, law = no_op_thread("t-noop")
    specs, laws = assemble_spec_law_map([(spec, law)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    engine.run(
        run_id="r-noop",
        budget=WaveBudget(max_waves=4, max_activations=4, max_stone_events=2),
    )
    activations = engine.ledger.activations_for_run("r-noop")
    assert all(act.outcome is ActivationOutcome.SATURATED_NO_DELTA for act in activations)


def test_engine_includes_run_record_in_ledger() -> None:
    engine = _uppercase_engine()
    engine.run(
        run_id="r-ledger",
        budget=WaveBudget(max_waves=2, max_activations=4, max_stone_events=2),
    )
    assert any(item.run_id == "r-ledger" for item in engine.ledger.runs)


def test_engine_requires_matching_spec_and_law_keys() -> None:
    spec, _ = uppercase_thread(carrier_id="c1", text="x")
    bodies = build_safe_fixture_registry()
    with __import__("pytest").raises(WaveEngineConfigurationError):
        WaveEngine(
            thread_specs={spec.thread_id: spec},
            propagation_laws={},
            sediment=SedimentState(),
            bodies=bodies,
        )


def test_engine_records_run_only_once() -> None:
    engine = _uppercase_engine()
    with __import__("pytest").raises(WaveEngineConfigurationError):
        engine.run(
            run_id="r-dup",
            budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
        )
        engine.run(
            run_id="r-dup",
            budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
        )
