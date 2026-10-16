"""Issue #60 acceptance traces: executed ledger, not label theater."""

import json

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.carpet_hosts import campus_host_engine, meteorology_host_engine
from seshat.fabric_waves.carpet_portfolio import execute_portfolio, export_artifacts
from seshat.fabric_waves.contracts import FabricRunOutcome, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.scenarios import repair_engine

BUDGET = WaveBudget(max_waves=40, max_activations=60, max_stone_events=60)


def _query(topic: str) -> StoneEvent:
    return StoneEvent(
        event_id="q",
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={"topic": topic, "query": "trace"},
    )


def test_t1_campus_six_threads_fan_in_answer():
    engine = campus_host_engine()
    run = engine.run(run_id="t1", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    thread_ids = {activation.thread_id for activation in engine.ledger.activations_for_run("t1")}
    assert len(thread_ids) >= 6
    assert "answer-campus" in thread_ids
    assert "reconcile-campus" in thread_ids
    answer = engine.sediment.views["working"].get("answer-campus")
    assert answer is not None
    assert answer.payload["grounded"] is True
    assert answer.payload["divergent"] is True
    assert run.activations_total >= 6
    resonances = engine.resonance_composer.values()
    assert any(record.kind.value == "ANSWER" for record in resonances)


def test_t2_source_delta_recomputes_dependent_branch_only():
    engine = campus_host_engine()
    before = engine.run(run_id="init", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    untouched_beta = before.sediment_final_versions.get("obs-campus-beta")
    after = engine.run(
        run_id="delta",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="delta",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=2,
            target_carrier_id="campus-branch-alpha",
            payload={
                "old_version": "1",
                "new_version": "2",
                "text": "revised lab telemetry: utilization index 79%",
            },
        ),
    )
    assert untouched_beta == after.sediment_final_versions.get("obs-campus-beta")
    alpha_history = engine.sediment.history("evidence-alpha-campus")
    assert any(record.acceptance_state is AcceptanceState.STALE for record in alpha_history[1:])


def test_t3_aporia_without_self_accepted_promotion():
    engine = repair_engine()
    run = engine.run(run_id="t3", budget=BUDGET)
    assert run.outcome is FabricRunOutcome.APORIA
    assert not engine.sediment.views["accepted"]


def test_t4_meteorology_host_reuses_framework():
    engine = meteorology_host_engine()
    engine.run(run_id="t4", budget=BUDGET, initial_stone=_query("winter-operations-wind-icing"))
    assert "answer-met" in engine.sediment.views["working"]
    campus = campus_host_engine()
    campus.run(run_id="c", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    assert set(campus.thread_specs) != set(engine.thread_specs)
    assert campus.ledger.head_hash != engine.ledger.head_hash


def test_portfolio_cli_writes_required_artifact_names(tmp_path):
    runs = execute_portfolio()
    receipt = export_artifacts(runs, tmp_path)
    for name in receipt["artifact_files"]:
        assert (tmp_path / name).is_file()
    activations = [
        json.loads(line)
        for line in (tmp_path / "activations.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(activations) >= 20
    assert "portfolio_digest_sha256" in receipt
