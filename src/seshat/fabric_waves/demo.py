"""SESHAT fabric_waves CLI demo (installable entry point)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.trace import render_html, render_svg


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    run_records: tuple[Any, ...]
    engines: tuple[WaveEngine, ...]


def _budget() -> WaveBudget:
    return WaveBudget(
        max_waves=20,
        max_activations=12,
        max_stone_events=12,
        aporia_after_waves=2,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def scenario_single_study() -> ScenarioResult:
    from seshat.fabric_waves.scenarios import repair_engine
    engine = repair_engine()
    run = engine.run(run_id="s1-repair", budget=_budget())
    return ScenarioResult("s1", (run,), (engine,))


def scenario_corpus() -> ScenarioResult:
    from seshat.fabric_waves.scenarios import corpus_engine
    engine = corpus_engine()
    run = engine.run(run_id="s2-corpus", budget=_budget())
    return ScenarioResult("s2", (run,), (engine,))


def scenario_source_revision() -> ScenarioResult:
    from seshat.fabric_waves.scenarios import revision_engine
    engine = revision_engine()
    initial = engine.run(run_id="s3-init", budget=_budget())
    revised = engine.run(run_id="s3-after-delta", budget=_budget(), initial_stone=StoneEvent(
        event_id="s3-revision", kind=StoneEventKind.SOURCE_DELTA, issued_at_tick=10,
        target_carrier_id="source-a",
        payload={"old_version": "1", "new_version": "2", "text": "revised synthetic source"}))
    return ScenarioResult("s3", (initial, revised), (engine,))

def render_result(result: ScenarioResult, output_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"scenario_id": result.scenario_id, "runs": []}
    engine = result.engines[0]
    for run in result.run_records:
        ledger, sediment, resonances = engine.snapshot(run.run_id)
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
            "ledger": ledger.serialize(),
            "sediment": [
                record.model_dump(mode="python") for record in sediment.all_records()
            ],
            "resonances": [
                record.model_dump(mode="python") for record in resonances.values()
            ],
        }
        _write_json(output_dir / f"{result.scenario_id}-{run.run_id}.json", json_payload)
        html_doc = render_html(
            run_record=run,
            ledger=ledger,
            sediment=sediment,
            resonances=resonances,
            thread_specs=engine.thread_specs,
            title=f"SESHAT fabric_waves scenario {result.scenario_id} — {run.run_id}",
        )
        _write_text(output_dir / f"{result.scenario_id}-{run.run_id}.html", html_doc)
        svg = render_svg(run_record=run, ledger=ledger)
        _write_text(output_dir / f"{result.scenario_id}-{run.run_id}.svg", svg)
    return summary


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "fabric_waves",
    )
    parser.add_argument(
        "--scenario",
        choices=("s1", "s2", "s3", "all"),
        default="all",
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
