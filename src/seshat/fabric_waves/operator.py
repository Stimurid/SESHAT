"""Operator CLI for dropping typed Stone events onto the fabric prototype.

Reads a JSON list of stone events, runs the bounded wave engine against safe
fixture threads, and writes JSON/HTML/SVG traces.  This is the narrow
operator surface requested for QUERY, SOURCE_DELTA, APORIA, FRONTIER_RETURN and
HUMAN_DECISION perturbations — not a production host adapter.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.trace import render_html, render_svg


def load_stone_events(payload: object) -> tuple[StoneEvent, ...]:
    if not isinstance(payload, list):
        raise ValueError("events file must contain a JSON array of stone events")
    events: list[StoneEvent] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"event at index {index} must be an object")
        kind = item.get("kind")
        if kind is None:
            raise ValueError(f"event at index {index} missing kind")
        events.append(
            StoneEvent(
                event_id=str(item.get("event_id", f"operator:{index}")),
                kind=StoneEventKind(str(kind)),
                issued_at_tick=int(item.get("issued_at_tick", index)),
                payload=item.get("payload", {}),
                target_carrier_id=item.get("target_carrier_id"),
                target_thread_id=item.get("target_thread_id"),
                target_research_object_id=item.get("target_research_object_id"),
            )
        )
    return tuple(events)


def build_engine(profile: str) -> WaveEngine:
    from seshat.fabric_waves.scenarios import corpus_engine, repair_engine, revision_engine
    factories = {"repair": repair_engine, "corpus": corpus_engine, "invalidation": revision_engine}
    if profile not in factories:
        raise ValueError("UNKNOWN_SYNTHETIC_PROFILE")
    return factories[profile]()

def run_operator(
    *,
    events: tuple[StoneEvent, ...],
    profile: str,
    run_id: str,
    budget: WaveBudget,
    output_dir: Path | None,
) -> dict[str, Any]:
    engine = build_engine(profile)
    for event in events:
        engine.dispatcher.drop(event)
    run = engine.run(run_id=run_id, budget=budget, auto_answer=True)
    trace = {
        "run": run.model_dump(mode="python"),
        "ledger": engine.ledger.serialize(),
        "sediment": [record.model_dump(mode="python") for record in engine.sediment.all_records()],
        "resonances": [
            record.model_dump(mode="python") for record in engine.resonance_composer.values()
        ],
        "stone_kinds_observed": sorted({event.kind.value for event in events}),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{run_id}.json"
        json_path.write_text(
            json.dumps(trace, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        html_doc = render_html(
            run_record=run,
            ledger=engine.ledger,
            sediment=engine.sediment,
            resonances=engine.resonance_composer,
            thread_specs=engine.thread_specs,
            title=f"SESHAT fabric operator trace — {run_id}",
        )
        (output_dir / f"{run_id}.html").write_text(html_doc, encoding="utf-8")
        (output_dir / f"{run_id}.svg").write_text(
            render_svg(run_record=run, ledger=engine.ledger),
            encoding="utf-8",
        )
    return trace


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drop typed Stone events on the fabric_waves safe prototype and emit traces."
    )
    parser.add_argument(
        "--events",
        type=Path,
        required=True,
        help="JSON file: array of {kind, event_id?, issued_at_tick?, payload?, target_carrier_id?}",
    )
    parser.add_argument(
        "--profile",
        choices=("repair", "corpus", "invalidation"),
        default="repair",
        help="Fixture thread bundle (default: repair = Object/Method mutual repair).",
    )
    parser.add_argument("--run-id", default="operator-run")
    parser.add_argument("--max-waves", type=int, default=6)
    parser.add_argument("--max-activations", type=int, default=12)
    parser.add_argument("--max-stone-events", type=int, default=12)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "fabric_waves" / "operator",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Write the trace JSON to stdout after artifacts are written.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    raw = json.loads(args.events.read_text(encoding="utf-8"))
    events = load_stone_events(raw)
    budget = WaveBudget(
        max_waves=args.max_waves,
        max_activations=args.max_activations,
        max_stone_events=args.max_stone_events,
        aporia_after_waves=2,
    )
    trace = run_operator(
        events=events,
        profile=args.profile,
        run_id=args.run_id,
        budget=budget,
        output_dir=args.output_dir,
    )
    print(f"Wrote operator trace for {args.run_id} to {args.output_dir.resolve()}")
    if args.print_json:
        json.dump(trace, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
