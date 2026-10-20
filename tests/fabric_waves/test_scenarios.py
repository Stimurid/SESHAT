"""Synthetic integration scenarios; science acceptance remains external."""
import json
from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import WaveBudget
from seshat.fabric_waves.demo import scenario_source_revision
from seshat.fabric_waves.scenarios import corpus_engine, repair_engine

BUDGET = WaveBudget(max_waves=20, max_activations=20, max_stone_events=20)

def test_single_study_object_method_mutual_repair():
    engine = repair_engine()
    run = engine.run(run_id="repair", budget=BUDGET)
    assert [a.thread_id for a in engine.ledger.activations] == ["object", "method-critic", "object-repair"]
    assert run.outcome.value == "APORIA"

def test_corpus_aggregation_reuses_sum_state():
    engine = corpus_engine()
    engine.run(run_id="corpus", budget=BUDGET)
    aggregate = engine.sediment.views["working"].get("aggregate")
    assert aggregate.payload["count"] == 8
    assert set(aggregate.payload["cached_refs"]) == {"study-a", "study-b"}

def test_corpus_aggregation_succeeds_when_corpus_registered_before_sum():
    normal, reversed_engine = corpus_engine(), corpus_engine(reverse=True)
    for engine in (normal, reversed_engine):
        engine.run(run_id="corpus", budget=BUDGET)
    assert normal.sediment.version_map() == reversed_engine.sediment.version_map()

def test_source_revision_selectively_wakes_only_dependent_thread():
    result = scenario_source_revision()
    engine = result.engines[0]
    assert {a.thread_id for a in engine.ledger.activations_for_run("s3-after-delta")} == {"A", "B", "C"}
    assert AcceptanceState.STALE in [r.acceptance_state for r in engine.sediment.history("C")]

def test_engine_does_not_self_certify_acceptance():
    engine = corpus_engine()
    engine.run(run_id="r", budget=BUDGET)
    assert engine.sediment.all_records()
    assert not engine.sediment.views["accepted"].values()

def test_replay_determinism():
    a, b = corpus_engine(), corpus_engine()
    for engine in (a, b):
        engine.run(run_id="r", budget=BUDGET)
    assert a.ledger.head_hash == b.ledger.head_hash

def test_distinct_projections_share_sediment():
    engine = corpus_engine()
    engine.run(run_id="r", budget=BUDGET)
    assert {r.kind.value for r in engine.resonance_composer.values()} == {"ANSWER", "MAP", "REPORT"}
    assert "aggregate" in {sid for r in engine.resonance_composer.values() for sid in r.trace_sediment_ids}

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