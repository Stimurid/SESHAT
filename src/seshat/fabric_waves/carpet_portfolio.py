"""Runnable carpet portfolio: T1–T4 traces and standard operator artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seshat.fabric_waves.carpet_hosts import campus_host_engine, meteorology_host_engine
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.scenarios import repair_engine, revision_engine
from seshat.fabric_waves.trace import render_html


@dataclass(frozen=True)
class PortfolioRun:
    label: str
    run_id: str
    engine: WaveEngine


def _budget() -> WaveBudget:
    return WaveBudget(
        max_waves=40,
        max_activations=60,
        max_stone_events=60,
        aporia_after_waves=4,
    )


def _query_stone(event_id: str, *, topic: str) -> StoneEvent:
    return StoneEvent(
        event_id=event_id,
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={
            "topic": topic,
            "query": "reconcile divergent branches with versioned sediment",
        },
    )


def execute_portfolio() -> tuple[PortfolioRun, ...]:
    """Run T1–T4 demonstration sequence on shared or distinct host engines."""
    campus = campus_host_engine()
    t1 = campus.run(
        run_id="t1-campus-query",
        budget=_budget(),
        initial_stone=_query_stone("t1-query", topic="campus-facility-utilization"),
    )
    assert t1.activations_total >= 6

    campus.run(
        run_id="t2-campus-source-delta",
        budget=_budget(),
        initial_stone=StoneEvent(
            event_id="t2-delta",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=5,
            target_carrier_id="campus-branch-alpha",
            payload={
                "old_version": "1",
                "new_version": "2",
                "text": "revised lab telemetry: utilization index 79%",
            },
        ),
    )

    repair = repair_engine()
    repair.run(run_id="t3-aporia-human-gate", budget=_budget())

    met = meteorology_host_engine()
    met.run(
        run_id="t4-meteorology-query",
        budget=_budget(),
        initial_stone=_query_stone("t4-query", topic="winter-operations-wind-icing"),
    )

    # Baseline invalidation trace (shared revision fixture, independent of campus host).
    invalidation = revision_engine()
    invalidation.run(run_id="t2-baseline-init", budget=_budget())
    invalidation.run(
        run_id="t2-baseline-revision",
        budget=_budget(),
        initial_stone=StoneEvent(
            event_id="t2-baseline-delta",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=3,
            target_carrier_id="source-a",
            payload={
                "old_version": "1",
                "new_version": "2",
                "text": "revised synthetic source",
            },
        ),
    )

    return (
        PortfolioRun("T1", "t1-campus-query", campus),
        PortfolioRun("T2", "t2-campus-source-delta", campus),
        PortfolioRun("T3", "t3-aporia-human-gate", repair),
        PortfolioRun("T4", "t4-meteorology-query", met),
        PortfolioRun("T2_BASELINE", "t2-baseline-revision", invalidation),
    )


def _git_meta() -> dict[str, str | None]:
    def _run(args: Sequence[str]) -> str | None:
        try:
            result = subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    root = Path(__file__).resolve().parents[3]
    return {
        "head_sha": _run(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "tree_sha": _run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]),
        "branch": _run(["git", "-C", str(root), "branch", "--show-current"]),
    }


def export_artifacts(
    runs: Sequence[PortfolioRun],
    output_dir: Path,
    *,
    primary_run_id: str = "t1-campus-query",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stones: list[dict[str, Any]] = []
    waves_lines: list[str] = []
    activation_lines: list[str] = []
    sediment_records: list[dict[str, Any]] = []
    resonance_records: list[dict[str, Any]] = []

    engines_by_run: dict[str, WaveEngine] = {}
    for item in runs:
        engines_by_run[item.run_id] = item.engine
        ledger, sediment, resonances = item.engine.snapshot(item.run_id)
        for event in ledger.events:
            if event.run_id == item.run_id:
                stones.append(event.model_dump(mode="python"))
        for wave in ledger.waves:
            if wave.run_id == item.run_id:
                waves_lines.append(
                    json.dumps(wave.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
                )
        for activation in ledger.activations:
            if activation.run_id == item.run_id:
                activation_lines.append(
                    json.dumps(
                        activation.model_dump(mode="python"),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        for record in sediment.all_records():
            sediment_records.append(record.model_dump(mode="python"))
        for record in resonances.values():
            resonance_records.append(record.model_dump(mode="python"))

    primary = engines_by_run[primary_run_id]
    ledger, sediment, resonances = primary.snapshot(primary_run_id)
    run_record = next(run for run in ledger.runs if run.run_id == primary_run_id)
    carpet_html = render_html(
        run_record=run_record,
        ledger=ledger,
        sediment=sediment,
        resonances=resonances,
        thread_specs=primary.thread_specs,
        title="SESHAT executable carpet — campus T1 primary trace",
    )

    (output_dir / "stones.json").write_text(
        json.dumps(stones, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "waves.jsonl").write_text("\n".join(waves_lines) + ("\n" if waves_lines else ""), encoding="utf-8")
    (output_dir / "activations.jsonl").write_text(
        "\n".join(activation_lines) + ("\n" if activation_lines else ""),
        encoding="utf-8",
    )
    (output_dir / "sediment.json").write_text(
        json.dumps(sediment_records, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "resonances.json").write_text(
        json.dumps(resonance_records, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "carpet.html").write_text(carpet_html, encoding="utf-8")

    portfolio_digest = hashlib.sha256(
        (output_dir / "activations.jsonl").read_bytes()
        + (output_dir / "waves.jsonl").read_bytes()
    ).hexdigest()
    receipt = {
        "portfolio_digest_sha256": portfolio_digest,
        "runs": [
            {
                "label": item.label,
                "run_id": item.run_id,
                "ledger_head_hash": item.engine.ledger.runs[-1].ledger_head_hash
                if item.engine.ledger.runs
                else None,
            }
            for item in runs
        ],
        "artifact_files": [
            "stones.json",
            "waves.jsonl",
            "activations.jsonl",
            "sediment.json",
            "resonances.json",
            "carpet.html",
            "receipt.json",
        ],
        "git": _git_meta(),
        "known_limits": [
            "Synthetic public fixtures only; F07 CorpusSelection host path unchanged.",
            "T3 uses repair_engine APORIA gate; human DecisionRight via decision_gate API in tests.",
            "Independent Docker review and merge not performed in this executor run.",
        ],
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return receipt


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "carpet_portfolio",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    runs = execute_portfolio()
    receipt = export_artifacts(runs, args.output_dir)
    print(f"Wrote carpet portfolio to {args.output_dir.resolve()}")
    print(f"portfolio_digest_sha256={receipt['portfolio_digest_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
