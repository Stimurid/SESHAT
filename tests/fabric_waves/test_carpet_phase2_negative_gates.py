"""Phase-II black-box gates and portfolio regression coverage (issue #60)."""

from __future__ import annotations

import json
from collections import Counter

from seshat.fabric_waves.carpet_hosts import campus_decision_host_engine, campus_host_engine
from seshat.fabric_waves.carpet_portfolio import execute_portfolio, export_artifacts
from seshat.fabric_waves.contracts import (
    OPERATOR_STONE_KINDS,
    FabricRunOutcome,
    StoneEvent,
    StoneEventKind,
    WaveBudget,
)
from seshat.fabric_waves.decision_gate import host_fixture_attestation, host_fixture_verifier
from seshat.fabric_waves.operator import load_stone_events, run_operator

BUDGET = WaveBudget(max_waves=40, max_activations=60, max_stone_events=60)


def _portfolio_dir(tmp_path):
    runs = execute_portfolio()
    export_artifacts(runs, tmp_path)
    return tmp_path


def _stone_types(stones: list[dict]) -> set[str]:
    return {item["kind"] for item in stones}


def test_negative_gate_t3_decision_stone_present(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    stones = json.loads((out / "stones.json").read_text(encoding="utf-8"))
    assert StoneEventKind.HUMAN_DECISION.value in _stone_types(stones)
    assert StoneEventKind.APORIA.value in _stone_types(stones)


def test_negative_gate_aporia_has_no_answer(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    resonances = json.loads((out / "resonances.json").read_text(encoding="utf-8"))
    t3 = [r for r in resonances if r.get("run_id") == "t3-aporia-human-gate"]
    assert not any(r["kind"] == "ANSWER" for r in t3)


def test_negative_gate_stones_are_operator_only(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    stones = json.loads((out / "stones.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (out / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert stones
    assert all(item["kind"] in {k.value for k in OPERATOR_STONE_KINDS} for item in stones)
    assert len(events) > len(stones)
    assert any(item["kind"] == StoneEventKind.SEDIMENT_AVAILABLE.value for item in events)


def test_negative_gate_resonance_ids_unique_in_export(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    resonances = json.loads((out / "resonances.json").read_text(encoding="utf-8"))
    ids = [item["resonance_id"] for item in resonances]
    assert len(ids) == len(set(ids))


def test_negative_gate_per_run_receipt_heads_distinct(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    heads = {
        item["run_id"]: item["ledger_head_hash"]
        for item in receipt["runs"]
        if item["run_id"] in ("t1-campus-query", "t2-campus-source-delta")
    }
    assert heads["t1-campus-query"]
    assert heads["t2-campus-source-delta"]
    assert heads["t1-campus-query"] != heads["t2-campus-source-delta"]


def test_t1_waves_reference_consumed_event_not_seed_only() -> None:
    engine = campus_host_engine()
    engine.run(
        run_id="t1",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="t1-query",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "campus-facility-utilization", "query": "trace"},
        ),
    )
    waves = [wave for wave in engine.ledger.waves if wave.run_id == "t1"]
    assert waves
    assert waves[0].triggering_event_id == "t1-query"


def test_t2_source_delta_wave_trigger_matches_delta_event() -> None:
    engine = campus_host_engine()
    engine.run(
        run_id="init",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="init-query",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "campus-facility-utilization", "query": "trace"},
        ),
    )
    engine.run(
        run_id="delta",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="delta-event",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=2,
            target_carrier_id="campus-branch-alpha",
            payload={"old_version": "1", "new_version": "2", "text": "revised lab telemetry: utilization index 79%"},
        ),
    )
    delta_waves = [
        wave
        for wave in engine.ledger.waves
        if wave.run_id == "delta" and wave.triggered_by is StoneEventKind.SOURCE_DELTA
    ]
    assert delta_waves[0].triggering_event_id == "delta-event"


def test_operator_campus_profile_multi_stone_stateful(tmp_path) -> None:
    events = load_stone_events(
        [
            {
                "kind": "QUERY",
                "event_id": "op-campus-q",
                "payload": {"topic": "campus-facility-utilization", "query": "trace"},
            },
            {
                "kind": "SOURCE_DELTA",
                "event_id": "op-campus-d",
                "target_carrier_id": "campus-branch-alpha",
                "payload": {
                    "old_version": "1",
                    "new_version": "2",
                    "text": "revised lab telemetry: utilization index 79%",
                },
            },
        ]
    )
    engine = campus_host_engine()
    run_operator(
        events=events,
        profile="campus",
        run_id="op-campus",
        budget=WaveBudget(max_waves=30, max_activations=40, max_stone_events=30),
        output_dir=tmp_path,
        engine=engine,
    )
    run_operator(
        events=load_stone_events(
            [
                {
                    "kind": "QUERY",
                    "event_id": "op-campus-q2",
                    "payload": {"topic": "campus-facility-utilization", "query": "trace-2"},
                }
            ]
        ),
        profile="campus",
        run_id="op-campus-2",
        budget=WaveBudget(max_waves=20, max_activations=30, max_stone_events=20),
        output_dir=tmp_path,
        engine=engine,
    )
    assert len(engine.ledger.runs) == 2


def test_human_decision_without_attestation_emits_decision_request_not_accepted() -> None:
    engine = campus_decision_host_engine()
    engine.dispatcher.drop(
        StoneEvent(
            event_id="apor",
            kind=StoneEventKind.APORIA,
            issued_at_tick=0,
            payload={"note": "hold"},
        )
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="q",
            kind=StoneEventKind.QUERY,
            issued_at_tick=1,
            payload={"topic": "campus-governance-aporia", "query": "trace"},
        )
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="reject",
            kind=StoneEventKind.HUMAN_DECISION,
            issued_at_tick=2,
            payload={"choice": "REJECT", "subject_sediment_id": "reconcile-campus"},
        )
    )
    engine.run(run_id="t3", budget=BUDGET)
    assert not engine.sediment.views["accepted"]
    kinds = [record.kind.value for record in engine.ledger.resonances_for_run("t3")]
    assert "DECISION_REQUEST" in kinds
    assert "ANSWER" not in kinds


def test_authenticated_host_fixture_reject_still_no_accepted_promotion() -> None:
    engine = campus_decision_host_engine()
    engine.dispatcher.drop(
        StoneEvent(
            event_id="apor",
            kind=StoneEventKind.APORIA,
            issued_at_tick=0,
            payload={},
        )
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="q",
            kind=StoneEventKind.QUERY,
            issued_at_tick=1,
            payload={"topic": "campus-governance-aporia", "query": "trace"},
        )
    )
    engine.run(run_id="pre", budget=BUDGET)
    reconcile = engine.sediment.views["working"].get("reconcile-campus")
    assert reconcile is not None
    att = host_fixture_attestation(
        decision_id="d-reject",
        subject_sediment_id="reconcile-campus",
        subject_version=reconcile.version,
        choice="REJECT",
        nonce="n1",
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="reject-auth",
            kind=StoneEventKind.HUMAN_DECISION,
            issued_at_tick=3,
            payload={
                "choice": "REJECT",
                "subject_sediment_id": "reconcile-campus",
                "attestation": att.model_dump(mode="python"),
            },
        )
    )
    engine.run(run_id="post", budget=BUDGET)
    assert not engine.sediment.views["accepted"]


def test_t3_traverses_multiple_functional_threads() -> None:
    engine = campus_decision_host_engine()
    from seshat.fabric_waves.carpet_portfolio import _run_t3_aporia_human_gate

    _run_t3_aporia_human_gate(engine)
    threads = {
        activation.thread_id
        for activation in engine.ledger.activations_for_run("t3-aporia-human-gate")
    }
    assert "question-campus" in threads
    assert "reconcile-campus" in threads
    assert "governance-campus" in threads
    assert "object" not in threads


def test_t4_meteorology_operator_profile(tmp_path) -> None:
    events = load_stone_events(
        [
            {
                "kind": "QUERY",
                "event_id": "met-q",
                "payload": {"topic": "winter-operations-wind-icing", "query": "trace"},
            }
        ]
    )
    trace = run_operator(
        events=events,
        profile="meteorology",
        run_id="met-op",
        budget=WaveBudget(max_waves=30, max_activations=40, max_stone_events=20),
        output_dir=tmp_path,
    )
    assert trace["run"]["outcome"] in {"CONVERGED", "SATURATED"}


def test_portfolio_stone_kind_coverage(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    stones = json.loads((out / "stones.json").read_text(encoding="utf-8"))
    kinds = _stone_types(stones)
    assert StoneEventKind.QUERY.value in kinds
    assert StoneEventKind.SOURCE_DELTA.value in kinds
    assert StoneEventKind.HUMAN_DECISION.value in kinds
    assert StoneEventKind.APORIA.value in kinds


def test_portfolio_no_baseline_ghost_in_receipt(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    run_ids = {item["run_id"] for item in receipt["runs"]}
    assert "t2-baseline-init" not in run_ids
    assert "t2-baseline-revision" not in run_ids


def test_aporia_outcome_is_recorded_for_t3(tmp_path) -> None:
    runs = execute_portfolio()
    t3 = next(item for item in runs if item.run_id == "t3-aporia-human-gate")
    run = next(r for r in t3.engine.ledger.runs if r.run_id == "t3-aporia-human-gate")
    assert run.outcome is FabricRunOutcome.APORIA


def test_resonance_export_scoped_per_run(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    resonances = json.loads((out / "resonances.json").read_text(encoding="utf-8"))
    by_run = Counter(item["run_id"] for item in resonances)
    assert by_run["t1-campus-query"] >= 1
    assert by_run["t3-aporia-human-gate"] >= 1
    for item in resonances:
        assert item["resonance_id"].startswith(item["run_id"])


def test_host_fixture_verifier_positive() -> None:
    att = host_fixture_attestation(
        decision_id="d1",
        subject_sediment_id="s",
        subject_version="v",
        choice="ACCEPT",
        nonce="n",
    )
    assert host_fixture_verifier(att) is True


def test_converged_run_still_emits_answer_resonance() -> None:
    engine = campus_host_engine()
    engine.run(
        run_id="t1",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="q",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "campus-facility-utilization", "query": "trace"},
        ),
    )
    kinds = [record.kind.value for record in engine.ledger.resonances_for_run("t1")]
    assert "ANSWER" in kinds


def test_events_jsonl_includes_internal_causal_kinds(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    events = [
        json.loads(line)
        for line in (out / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = {item["kind"] for item in events}
    assert StoneEventKind.SEDIMENT_AVAILABLE.value in kinds


def test_t2_campus_delta_only_reactivates_alpha_path() -> None:
    engine = campus_host_engine()
    engine.run(
        run_id="init",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="q",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "campus-facility-utilization", "query": "trace"},
        ),
    )
    beta_v1 = engine.sediment.views["working"].get("obs-campus-beta").version
    engine.run(
        run_id="delta",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="d",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=1,
            target_carrier_id="campus-branch-alpha",
            payload={"old_version": "1", "new_version": "2", "text": "revised lab telemetry: utilization index 79%"},
        ),
    )
    beta_v2 = engine.sediment.views["working"].get("obs-campus-beta").version
    assert beta_v1 == beta_v2


def test_carpet_html_present_and_non_empty(tmp_path) -> None:
    out = _portfolio_dir(tmp_path)
    html = (out / "carpet.html").read_text(encoding="utf-8")
    assert "t1-campus-query" in html
    assert "Stone events" in html
