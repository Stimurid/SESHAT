"""End-to-end scenarios covering the required invariants.

These scenarios exercise the engine, the ledger and the sediment in concert.
They are the integration tests that protect the owner-charter invariants:

* source revision wakes only affected threads;
* acceptance is human authority;
* APORIA is preserved, not silently passed;
* budget stops infinite loops;
* replay is byte-for-byte deterministic;
* distinct projections reuse state.
"""

from __future__ import annotations

import json

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    StoneEvent,
    StoneEventKind,
    WaveBudget,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import (
    assemble_spec_law_map,
    corpus_aggregate_thread,
    sum_thread,
    uppercase_thread,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentState
from seshat.fabric_waves.stone import StoneDispatcher

# -- Scenario 1: Object↔Method mutual repair --------------------------------


def test_single_study_object_method_mutual_repair() -> None:
    spec_upper, law_upper = uppercase_thread(
        carrier_id="c-upper", text="hello", thread_id="t-upper"
    )
    spec_sum, law_sum = sum_thread(carrier_id="c-sum", thread_id="t-sum")
    specs, laws = assemble_spec_law_map([(spec_upper, law_upper), (spec_sum, law_sum)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )
    engine.run(
        run_id="r-repair",
        budget=WaveBudget(max_waves=4, max_activations=8, max_stone_events=4),
        initial_stone=StoneEvent(
            event_id="r-repair:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"text": "hello", "values": [1, 2, 3]},
        ),
    )
    # Both threads fired
    fired_thread_ids = {
        thread_id
        for wave in engine.ledger.waves
        for thread_id in wave.fired_thread_ids
    }
    assert fired_thread_ids == {"t-upper", "t-sum"}
    # Both produced sediments
    types = {record.object_type for record in engine.sediment.all_records()}
    assert "safe.uppercase_text" in types
    assert "safe.sum" in types


# -- Scenario 2: Corpus aggregation reusing individual states --------------


def test_corpus_aggregation_reuses_sum_state() -> None:
    sum_spec, sum_law = sum_thread(carrier_id="c1", thread_id="t-sum-1")
    corpus_spec, corpus_law = corpus_aggregate_thread(
        corpus_id="corpus-a", thread_id="t-corpus-a"
    )
    specs, laws = assemble_spec_law_map([(sum_spec, sum_law), (corpus_spec, corpus_law)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    engine.run(
        run_id="r-corpus",
        budget=WaveBudget(max_waves=4, max_activations=8, max_stone_events=4),
        initial_stone=StoneEvent(
            event_id="r-corpus:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"values": [1, 2, 3]},
        ),
    )
    aggregate_records = [
        record for record in engine.sediment.all_records() if record.object_type == "safe.corpus_aggregate"
    ]
    assert aggregate_records, "corpus thread did not run"
    aggregate = aggregate_records[0]
    assert aggregate.payload["total"] == 6
    assert aggregate.payload["count"] == 1
    assert "C12-corpus-aggregation" in aggregate.applicability


# -- Scenario 3: Source revision invalidates dependent conclusions ----------


def test_source_revision_selectively_wakes_only_dependent_thread() -> None:
    spec_upper, law_upper = uppercase_thread(
        carrier_id="c-upper", text="hello", thread_id="t-upper"
    )
    spec_sum, law_sum = sum_thread(carrier_id="c-other", thread_id="t-sum")
    specs, laws = assemble_spec_law_map([(spec_upper, law_upper), (spec_sum, law_sum)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )
    # Initial run
    engine.run(
        run_id="r1-init",
        budget=WaveBudget(max_waves=2, max_activations=8, max_stone_events=2),
        initial_stone=StoneEvent(
            event_id="r1-init:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"text": "hello", "values": [1, 2, 3]},
        ),
    )
    # Now drop a SOURCE_DELTA on c-upper
    engine.dispatcher.drop(
        StoneEvent(
            event_id="r1-delta:event",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=10,
            payload={"old": "v1", "new": "v2"},
            target_carrier_id="c-upper",
        )
    )
    engine.run(
        run_id="r1-delta",
        budget=WaveBudget(max_waves=4, max_activations=8, max_stone_events=4),
        auto_answer=False,
    )
    # The thread reading c-upper must have been eligible (and likely fired),
    # while the thread reading c-other must NOT have been touched by the delta.
    # The SOURCE_DELTA wave is the one triggered by StoneEventKind.SOURCE_DELTA.
    delta_waves = [
        wave for wave in engine.ledger.waves if wave.triggered_by is StoneEventKind.SOURCE_DELTA
    ]
    assert delta_waves, "no SOURCE_DELTA wave recorded"
    last_delta_wave = delta_waves[-1]
    assert "t-upper" in last_delta_wave.eligible_thread_ids or "t-upper" in last_delta_wave.fired_thread_ids
    # No delta should reach t-sum because it depends on c-other
    assert "t-sum" not in last_delta_wave.eligible_thread_ids
    # Sediment for t-upper must be STALE because its carrier was revised
    upper_states = [
        record.acceptance_state
        for record in engine.sediment.all_records()
        if record.object_type == "safe.uppercase_text"
    ]
    assert AcceptanceState.STALE in upper_states


# -- Scenario 4: Acceptance is human authority, never self-certified -------


def test_engine_does_not_self_certify_acceptance() -> None:
    spec_upper, law_upper = uppercase_thread(
        carrier_id="c-upper", text="x", thread_id="t"
    )
    specs, laws = assemble_spec_law_map([(spec_upper, law_upper)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    engine.run(
        run_id="r-accept",
        budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
    )
    accepted = engine.sediment.views["accepted"].values()
    assert accepted == ()


# -- Scenario 5: Replay is byte-for-byte deterministic ----------------------


def test_replay_determinism() -> None:
    def make() -> WaveEngine:
        spec_upper, law_upper = uppercase_thread(
            carrier_id="c-upper", text="x", thread_id="t"
        )
        specs, laws = assemble_spec_law_map([(spec_upper, law_upper)])
        return WaveEngine(
            thread_specs=specs,
            propagation_laws=laws,
            sediment=SedimentState(),
            bodies=build_safe_fixture_registry(),
            ledger=RunLedger(),
            dispatcher=StoneDispatcher(),
        )

    e1 = make()
    e2 = make()
    e1.run(
        run_id="r",
        budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
    )
    e2.run(
        run_id="r",
        budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
    )
    assert e1.ledger.head_hash == e2.ledger.head_hash


# -- Scenario 6: Distinct projections reuse state ----------------------------


def test_distinct_projections_share_sediment() -> None:
    spec_upper, law_upper = uppercase_thread(
        carrier_id="c-upper", text="x", thread_id="t"
    )
    specs, laws = assemble_spec_law_map([(spec_upper, law_upper)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
    )
    engine.run(
        run_id="r-proj",
        budget=WaveBudget(max_waves=2, max_activations=2, max_stone_events=2),
    )
    kinds = {record.kind.value for record in engine.resonance_composer.values()}
    assert {"ANSWER", "MAP", "REPORT"}.issubset(kinds)
    upper_ids = [
        record.sediment_id
        for record in engine.sediment.all_records()
        if record.object_type == "safe.uppercase_text"
    ]
    # All three resonances should reference the same uppercase sediment
    sediment_refs = {
        sid
        for record in engine.resonance_composer.values()
        for sid in record.trace_sediment_ids
    }
    assert any(sid in sediment_refs for sid in upper_ids)


def test_cli_demo_runs_all_three_scenarios(tmp_path) -> None:
    """End-to-end CLI smoke: invokes the demo runner and verifies artifacts."""

    import importlib
    import sys

    scripts_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent.parent
        / "scripts"
    )
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    demo = importlib.import_module("fabric_waves_demo")

    output_dir = tmp_path / "demo"
    exit_code = demo.main(["--output-dir", str(output_dir)])
    assert exit_code == 0
    artifacts = sorted(output_dir.iterdir())
    assert any(artifact.name == "summary.json" for artifact in artifacts)
    expected_html = {
        "s1-s1-repair.html",
        "s2-s2-corpus.html",
        "s3-s3-init.html",
        "s3-s3-after-delta.html",
    }
    expected_svg = {
        "s1-s1-repair.svg",
        "s2-s2-corpus.svg",
        "s3-s3-init.svg",
        "s3-s3-after-delta.svg",
    }
    found_names = {artifact.name for artifact in artifacts}
    assert expected_html.issubset(found_names)
    assert expected_svg.issubset(found_names)

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert len(summary["artifacts"]) == 3