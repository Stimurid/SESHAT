"""Runnable carpet portfolio: T1–T4 traces and standard operator artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seshat.fabric_waves.carpet_export import (
    all_run_events,
    operator_stone_events,
    run_ledger_head_hash,
    sediment_records_for_run,
)
from seshat.fabric_waves.carpet_hosts import (
    campus_decision_host_engine,
    campus_host_engine,
    meteorology_host_engine,
)
from seshat.fabric_waves.source_module_manifest import build_source_module_manifest
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.scenarios import revision_engine
from seshat.fabric_waves.trace import render_html

PORTFOLIO_HASHED_ARTIFACTS: tuple[str, ...] = (
    "stones.json",
    "events.jsonl",
    "waves.jsonl",
    "activations.jsonl",
    "sediment.json",
    "resonances.json",
    "carpet.html",
)


@dataclass(frozen=True)
class PortfolioRun:
    label: str
    run_id: str
    engine: WaveEngine


PORTFOLIO_EXPORT_RUNS: tuple[str, ...] = (
    "t1-campus-query",
    "t2-campus-source-delta",
    "t3-aporia-human-gate",
    "t4-meteorology-query",
)


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


def _run_t3_aporia_human_gate(engine: WaveEngine) -> None:
    engine.dispatcher.drop(
        StoneEvent(
            event_id="t3-aporia-hold",
            kind=StoneEventKind.APORIA,
            issued_at_tick=0,
            payload={"note": "operator holds promotion until governance review"},
        )
    )
    engine.dispatcher.drop(
        _query_stone("t3-query", topic="campus-governance-aporia"),
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="t3-human-reject",
            kind=StoneEventKind.HUMAN_DECISION,
            issued_at_tick=2,
            payload={
                "choice": "REJECT",
                "subject_sediment_id": "reconcile-campus",
                "rationale": "unauthenticated operator reject must not promote",
            },
        ),
    )
    engine.run(run_id="t3-aporia-human-gate", budget=_budget())


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

    t3_engine = campus_decision_host_engine()
    _run_t3_aporia_human_gate(t3_engine)

    met = meteorology_host_engine()
    met.run(
        run_id="t4-meteorology-query",
        budget=_budget(),
        initial_stone=_query_stone("t4-query", topic="winter-operations-wind-icing"),
    )

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
        PortfolioRun("T3", "t3-aporia-human-gate", t3_engine),
        PortfolioRun("T4", "t4-meteorology-query", met),
        PortfolioRun("T2_BASELINE", "t2-baseline-revision", invalidation),
    )


def _git_run(root: Path, args: Sequence[str], *, text: bool = True) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=text,
        )
        if text:
            return result.stdout.strip()
        return result.stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_module_paths_dirty(root: Path, entries: Sequence[Mapping[str, Any]]) -> bool:
    for entry in entries:
        rel = str(entry["relative_path"])
        try:
            subprocess.run(
                ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", rel],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return True
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
            capture_output=True,
        )
        if tracked.returncode != 0:
            return True
    return False


def _git_modules_match_head(root: Path, entries: Sequence[Mapping[str, Any]]) -> bool:
    for entry in entries:
        rel = str(entry["relative_path"])
        if ".." in Path(rel).parts:
            return False
        blob = _git_run(root, ["show", f"HEAD:{rel}"], text=False)
        if blob is None:
            return False
        if len(blob) != int(entry["byte_length"]):
            return False
        if hashlib.sha256(blob).hexdigest() != str(entry["sha256"]):
            return False
    return True


def _git_meta() -> dict[str, str | None]:
    root = Path(__file__).resolve().parents[3]
    head_sha = _git_run(root, ["rev-parse", "HEAD"])
    tree_sha = _git_run(root, ["rev-parse", "HEAD^{tree}"])
    branch = _git_run(root, ["branch", "--show-current"])
    modules = build_source_module_manifest()["modules"]

    attestation = "GIT_NOT_ATTESTED"
    if head_sha is None or tree_sha is None:
        head_sha = None
        tree_sha = None
    else:
        dirty = _git_module_paths_dirty(root, modules)
        matches = _git_modules_match_head(root, modules)
        if not dirty and matches:
            attestation = "GIT_BYTES_MATCH_HEAD_LOCAL"
        else:
            attestation = "GIT_REPORTED_UNVERIFIED"

    return {
        "attestation": attestation,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "branch": branch,
    }


def artifact_file_digests(output_dir: Path) -> dict[str, dict[str, int | str]]:
    digests: dict[str, dict[str, int | str]] = {}
    for name in PORTFOLIO_HASHED_ARTIFACTS:
        data = (output_dir / name).read_bytes()
        digests[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_length": len(data),
        }
    return digests


def export_artifacts(
    runs: Sequence[PortfolioRun],
    output_dir: Path,
    *,
    primary_run_id: str = "t1-campus-query",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stones: list[dict[str, Any]] = []
    event_lines: list[str] = []
    waves_lines: list[str] = []
    activation_lines: list[str] = []
    sediment_records: list[dict[str, Any]] = []
    resonance_records: list[dict[str, Any]] = []
    seen_resonance_ids: set[str] = set()

    export_runs = [item for item in runs if item.run_id in PORTFOLIO_EXPORT_RUNS]
    engines_by_run: dict[str, WaveEngine] = {}
    for item in export_runs:
        engines_by_run[item.run_id] = item.engine
        ledger, sediment, _composer = item.engine.snapshot(item.run_id)
        stones.extend(operator_stone_events(ledger, item.run_id))
        for event in all_run_events(ledger, item.run_id):
            event_lines.append(
                json.dumps(event, ensure_ascii=False, sort_keys=True)
            )
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
        sediment_records.extend(sediment_records_for_run(ledger, sediment, item.run_id))
        for record in ledger.resonances_for_run(item.run_id):
            if record.resonance_id in seen_resonance_ids:
                continue
            seen_resonance_ids.add(record.resonance_id)
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
    (output_dir / "events.jsonl").write_text(
        "\n".join(event_lines) + ("\n" if event_lines else ""),
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
    file_digests = artifact_file_digests(output_dir)
    source_modules = build_source_module_manifest()
    receipt = {
        "portfolio_digest_sha256": portfolio_digest,
        "artifact_file_digests": file_digests,
        "source_modules": source_modules,
        "runs": [
            {
                "label": item.label,
                "run_id": item.run_id,
                "ledger_head_hash": run_ledger_head_hash(
                    item.engine.snapshot(item.run_id)[0],
                    item.run_id,
                ),
            }
            for item in export_runs
        ],
        "artifact_files": [
            "stones.json",
            "events.jsonl",
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
            "T3 uses campus governance gate with APORIA + unauthenticated HUMAN_DECISION REJECT.",
            "Independent Docker review and merge not performed in this executor run.",
            "Portable receipt uses SOURCE_MODULE_BYTES_VERIFIED; git attestation is conservative (GIT_BYTES_MATCH_HEAD_LOCAL only when HEAD bytes match all listed modules and worktree is clean).",
            "GIT_REPORTED_UNVERIFIED / GIT_NOT_ATTESTED are honest self-reports; TRUSTED_EXTERNAL review must pin exact SHA/TREE + module digest independently.",
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
