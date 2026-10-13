#!/usr/bin/env python
"""SESHAT fabric_waves CLI demo.

Runs the three owner-mandated scenarios end-to-end, writing JSON, HTML and SVG
artifacts to ``--output-dir`` (default ``artifacts/fabric_waves/``).

Scenarios:

* S1 — single-study Object↔Method mutual repair (uppercase + sum).
* S2 — corpus question reusing individual states (C12/C04 aggregation).
* S3 — changed external EvidenceReturn invalidating dependent conclusions
       and selectively waking only the necessary threads (SOURCE_DELTA).

Usage::

    python -m scripts.fabric_waves_demo                 # default output dir
    python -m scripts.fabric_waves_demo --output-dir /tmp/seshat-demo
    python -m scripts.fabric_waves_demo --scenario s1  # one scenario only

The demo uses deterministic synthetic SAFE fixtures only.  No donor data,
production adapters, secrets or protected MethodBodies are involved.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from seshat.fabric_waves.trace import render_html, render_svg


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    run_records: tuple[Any, ...]
    engines: tuple[WaveEngine, ...]


def _budget() -> WaveBudget:
    return WaveBudget(
        max_waves=4,
        max_activations=8,
        max_stone_events=4,
        aporia_after_waves=2,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def scenario_single_study() -> ScenarioResult:
    """S1 — Object↔Method mutual repair: uppercase text + integer sum."""

    spec_upper, law_upper = uppercase_thread(carrier_id="c-upper", text="hello")
    spec_sum, law_sum = sum_thread(carrier_id="c-sum")
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
    run = engine.run(
        run_id="s1-repair",
        budget=_budget(),
        initial_stone=StoneEvent(
            event_id="s1-repair:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"text": "hello", "values": [1, 2, 3, 4]},
        ),
    )
    return ScenarioResult(scenario_id="s1", run_records=(run,), engines=(engine,))


def scenario_corpus() -> ScenarioResult:
    """S2 — corpus aggregation reusing individual sum states."""

    spec_sum, law_sum = sum_thread(carrier_id="c-sum", thread_id="t-sum-corpus")
    spec_corp, law_corp = corpus_aggregate_thread(corpus_id="corpus-1", thread_id="t-corpus-1")
    specs, laws = assemble_spec_law_map([(spec_sum, law_sum), (spec_corp, law_corp)])
    bodies = build_safe_fixture_registry()
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=bodies,
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
    )
    run = engine.run(
        run_id="s2-corpus",
        budget=_budget(),
        initial_stone=StoneEvent(
            event_id="s2-corpus:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"values": [10, 20, 30]},
        ),
    )
    return ScenarioResult(scenario_id="s2", run_records=(run,), engines=(engine,))


def scenario_source_revision() -> ScenarioResult:
    """S3 — source revision invalidates dependent conclusions selectively."""

    spec_upper, law_upper = uppercase_thread(
        carrier_id="c-upper", text="hello", thread_id="t-upper-3"
    )
    spec_sum, law_sum = sum_thread(carrier_id="c-other", thread_id="t-sum-3")
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
        run_id="s3-init",
        budget=_budget(),
        initial_stone=StoneEvent(
            event_id="s3-init:init",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"text": "hello", "values": [1, 2, 3]},
        ),
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="s3-delta:event",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=10,
            payload={"old": "v1", "new": "v2"},
            target_carrier_id="c-upper",
        )
    )
    run_after = engine.run(
        run_id="s3-after-delta",
        budget=_budget(),
        auto_answer=False,
    )
    return ScenarioResult(
        scenario_id="s3",
        run_records=(engine.ledger.runs[0], run_after),
        engines=(engine,),
    )


def render_result(result: ScenarioResult, output_dir: Path) -> dict[str, Any]:
    """Write JSON, HTML and SVG artifacts for the scenario and return summary."""

    summary: dict[str, Any] = {"scenario_id": result.scenario_id, "runs": []}
    engine = result.engines[0]
    for run in result.run_records:
        summary["runs"].append(
            {
                "run_id": run.run_id,
                "outcome": run.outcome.value,
                "stop_reason": run.stop_reason.value,
                "waves_emitted": run.waves_emitted,
                "activations_total": run.activations_total,
                "ledger_head_hash": run.ledger_head_hash,
                "sediment_final_versions": run.sediment_final_versions,
            }
        )
        json_payload = {
            "run": run.model_dump(mode="python"),
            "ledger": engine.ledger.serialize(),
            "sediment": [record.model_dump(mode="python") for record in engine.sediment.all_records()],
            "resonances": [record.model_dump(mode="python") for record in engine.resonance_composer.values()],
        }
        _write_json(output_dir / f"{result.scenario_id}-{run.run_id}.json", json_payload)
        html_doc = render_html(
            run_record=run,
            ledger=engine.ledger,
            sediment=engine.sediment,
            resonances=engine.resonance_composer,
            title=f"SESHAT fabric_waves scenario {result.scenario_id} — {run.run_id}",
        )
        _write_text(output_dir / f"{result.scenario_id}-{run.run_id}.html", html_doc)
        svg = render_svg(run_record=run, ledger=engine.ledger)
        _write_text(output_dir / f"{result.scenario_id}-{run.run_id}.svg", svg)
    return summary


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "fabric_waves",
        help="Directory to write JSON/HTML/SVG artifacts to.",
    )
    parser.add_argument(
        "--scenario",
        choices=("s1", "s2", "s3", "all"),
        default="all",
        help="Which scenario to run (default: all).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    chosen = {
        "s1": scenario_single_study,
        "s2": scenario_corpus,
        "s3": scenario_source_revision,
    }
    scenarios: tuple[str, ...] = ("s1", "s2", "s3") if args.scenario == "all" else (args.scenario,)
    summaries: list[Mapping[str, Any]] = []
    for sid in scenarios:
        result = chosen[sid]()
        summaries.append(render_result(result, output_dir))
    _write_json(
        output_dir / "summary.json",
        {"artifacts": summaries, "decision_right": "seshat:fabric:human-acceptance"},
    )
    print(f"Wrote {len(summaries)} scenario(s) to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())