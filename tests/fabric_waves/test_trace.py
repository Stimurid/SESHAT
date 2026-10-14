"""Tests for the trace renderers."""

from __future__ import annotations

from seshat.fabric_waves.contracts import (
    FabricRunOutcome,
    FabricStopReason,
    RunRecord,
    WaveBudget,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import assemble_spec_law_map, uppercase_thread
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentState
from seshat.fabric_waves.stone import StoneDispatcher
from seshat.fabric_waves.trace import render_html, render_svg, resonance_summary


def _engine() -> WaveEngine:
    spec, law = uppercase_thread(carrier_id="c1", text="hello")
    specs, laws = assemble_spec_law_map([(spec, law)])
    return WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )


def _budget() -> WaveBudget:
    return WaveBudget(max_waves=2, max_activations=2, max_stone_events=2)


def test_render_html_contains_run_id() -> None:
    engine = _engine()
    run = engine.run(run_id="r-html", budget=_budget())
    html_doc = render_html(
        run_record=run,
        ledger=engine.ledger,
        sediment=engine.sediment,
        resonances=engine.resonance_composer,
    )
    assert "r-html" in html_doc
    assert "Sediment" in html_doc
    assert "Resonance" in html_doc
    assert "Stone events (this run)" in html_doc
    assert "budget:" in html_doc


def test_render_svg_handles_empty_waves() -> None:
    empty_run = RunRecord(
        run_id="r",
        started_at_tick=0,
        ended_at_tick=0,
        outcome=FabricRunOutcome.SATURATED,
        stop_reason=FabricStopReason.NO_DELTA,
        budget=_budget(),
        sediment_initial_versions={},
        sediment_final_versions={},
        waves_emitted=0,
        activations_total=0,
        ledger_head_hash="0" * 64,
    )
    svg = render_svg(run_record=empty_run, ledger=RunLedger())
    assert "<svg" in svg


def test_resonance_summary_produces_dicts() -> None:
    engine = _engine()
    engine.run(run_id="r-summary", budget=_budget())
    summary = resonance_summary(engine.resonance_composer.values())
    assert isinstance(summary, list)
    assert all("kind" in item for item in summary)


def test_render_html_escapes_user_payload() -> None:
    engine = _engine()
    engine.run(run_id="r-esc", budget=_budget())
    html_doc = render_html(
        run_record=engine.ledger.runs[-1],
        ledger=engine.ledger,
        sediment=engine.sediment,
        resonances=engine.resonance_composer,
    )
    assert "<script>" not in html_doc