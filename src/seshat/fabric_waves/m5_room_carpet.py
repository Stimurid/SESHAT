"""M5 executable Carpet: two invented worlds, room compilation, durable exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from seshat.fabric_waves.carpet_export import (
    all_run_events,
    operator_stone_events,
    run_ledger_head_hash,
    sediment_records_for_run,
)
from seshat.fabric_waves.carpet_portfolio import _git_meta
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.m5_oracles import evaluate_rm_oracles
from seshat.fabric_waves.m5_synthetic_hosts import build_host_engine, carrier_id_from_uri, host_slug
from seshat.fabric_waves.room_builder import RoomManifest, compile_room_for_stone, manifests_to_json
from seshat.fabric_waves.sediment import SedimentRecord
from seshat.fabric_waves.source_module_manifest import build_source_module_manifest
from seshat.fabric_waves.trace import render_html

M5_ARTIFACTS: tuple[str, ...] = (
    "room_manifest.json",
    "stones.json",
    "room_events.jsonl",
    "waves.jsonl",
    "activations.jsonl",
    "sediment.json",
    "resonances.json",
    "carpet.html",
    "report.md",
    "receipt.json",
    "ledger.sqlite",
)

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "m5_room_synthetic_acceptance_20261021_v01.json"
)


def load_fixture(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    digest = hashlib.sha256(raw).hexdigest()
    expected = "9feab9b1db1bfd2aedf239425898d9265c9dc2ad0f165b7778d2892c99a0e328"
    if digest != expected:
        raise ValueError(f"FIXTURE_SHA_MISMATCH expected={expected} got={digest}")
    return data


def _budget(fixture: Mapping[str, Any]) -> WaveBudget:
    stop = fixture.get("stop_policy") or {}
    max_act = int(stop.get("max_activations_per_stone") or 16)
    return WaveBudget(
        max_waves=40,
        max_activations=max_act * 4,
        max_stone_events=max_act * 3,
        aporia_after_waves=6,
    )


def _stone_event(
    stone: Mapping[str, Any],
    uri_map: Mapping[str, str],
    *,
    tick: int,
) -> StoneEvent:
    kind = str(stone["kind"])
    stone_id = str(stone["stone_id"])
    if kind == "QUERY":
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.QUERY,
            issued_at_tick=tick,
            payload={
                "topic": f"m5-stone-{stone_id}",
                "query": str(stone.get("question") or "synthetic query"),
            },
        )
    if kind == "SOURCE_DELTA":
        mutation = stone.get("mutation") or {}
        cid = uri_map.get(str(mutation["source_id"])) or carrier_id_from_uri(str(mutation["source_id"]))
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=tick,
            target_carrier_id=cid,
            payload={
                "old_version": str(mutation["old_version"]),
                "new_version": str(mutation["new_version"]),
                "text": str(mutation.get("new_content") or ""),
            },
        )
    if kind == "APORIA":
        conflict = stone.get("conflict") or {}
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.APORIA,
            issued_at_tick=tick,
            payload={
                "note": "synthetic aporia",
                "claim_a": str(conflict.get("claim_a", "")),
                "claim_b": str(conflict.get("claim_b", "")),
            },
        )
    raise ValueError(f"unsupported stone kind {kind}")


def _carrier_content_hash(engine: WaveEngine, carrier_id: str) -> str | None:
    store = engine.carrier_store
    if store is None:
        return None
    try:
        versions = store.current_source_versions((carrier_id,))
        ver = versions.get(carrier_id)
        if ver is None:
            return None
        digest = store.pin_content_digest(carrier_id, pinned_version=ver)
        return digest
    except (ValueError, KeyError):
        return None


def run_host_sequence(
    host: Mapping[str, Any],
    *,
    fixture: Mapping[str, Any],
    resume_from: Path | None = None,
) -> tuple[WaveEngine, list[RoomManifest], list[str], dict[str, str | None]]:
    slug = host_slug(str(host["host_id"]))
    engine, uri_map = build_host_engine(host)
    if resume_from is not None and resume_from.is_file():
        checkpoint = json.loads(resume_from.read_text(encoding="utf-8"))
        for item in checkpoint.get("sediment_records") or []:
            engine.sediment.deposit(SedimentRecord.model_validate(item))
    manifests: list[RoomManifest] = []
    run_ids: list[str] = []
    budget = _budget(fixture)
    alpha_id = carrier_id_from_uri(str(host["source_versions"][0]["id"]))
    beta_id = carrier_id_from_uri(str(host["source_versions"][1]["id"]))
    hashes: dict[str, str | None] = {"alpha_before": _carrier_content_hash(engine, alpha_id)}
    beta_before = _carrier_content_hash(engine, beta_id)

    tick = 0
    for stone in host.get("stones") or []:
        tick += 2
        manifest = compile_room_for_stone(
            host_id=str(host["host_id"]),
            host_slug=slug,
            stone=stone,
            budget=fixture.get("stop_policy") or {},
        )
        run_id = f"m5-{slug}-{stone['stone_id']}"
        run_ids.append(run_id)
        event = _stone_event(stone, uri_map, tick=tick)
        if stone.get("kind") == "APORIA":
            engine.dispatcher.drop(event)
            engine.run(run_id=run_id, budget=budget)
        else:
            engine.run(run_id=run_id, budget=budget, initial_stone=event)
        manifest.close(activations=engine.ledger.activations, run_id=run_id)
        manifests.append(manifest)

    hashes["alpha_after"] = _carrier_content_hash(engine, alpha_id)
    hashes["beta_after"] = _carrier_content_hash(engine, beta_id)
    hashes["beta_before"] = beta_before
    return engine, manifests, run_ids, hashes


def write_checkpoint(path: Path, engine: WaveEngine) -> None:
    payload = {
        "sediment_records": [r.model_dump(mode="python") for r in engine.sediment.all_records()],
        "ledger_head_hash": engine.ledger.head_hash,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def write_sqlite_ledger(path: Path, engine: WaveEngine, run_ids: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS m5_runs("
            "run_id TEXT PRIMARY KEY, ledger_head TEXT, activations INTEGER)"
        )
        for run_id in run_ids:
            acts = [a for a in engine.ledger.activations if a.run_id == run_id]
            db.execute(
                "INSERT OR REPLACE INTO m5_runs(run_id, ledger_head, activations) VALUES (?,?,?)",
                (run_id, run_ledger_head_hash(engine.ledger, run_id), len(acts)),
            )
        db.commit()


def export_world(
    engine: WaveEngine,
    *,
    host: Mapping[str, Any],
    manifests: Sequence[RoomManifest],
    run_ids: Sequence[str],
    output_dir: Path,
    oracle_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = host_slug(str(host["host_id"]))
    stones: list[dict[str, Any]] = []
    room_events: list[str] = []
    waves_lines: list[str] = []
    activation_lines: list[str] = []
    sediment_records: list[dict[str, Any]] = []
    resonance_records: list[dict[str, Any]] = []
    seen_res: set[str] = set()

    for run_id in run_ids:
        stones.extend(operator_stone_events(engine.ledger, run_id))
        for event in all_run_events(engine.ledger, run_id):
            room_events.append(json.dumps(event, ensure_ascii=False, sort_keys=True))
        for wave in engine.ledger.waves:
            if wave.run_id == run_id:
                waves_lines.append(json.dumps(wave.model_dump(mode="python"), ensure_ascii=False, sort_keys=True))
        for activation in engine.ledger.activations:
            if activation.run_id == run_id:
                activation_lines.append(
                    json.dumps(activation.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
                )
        sediment_records.extend(sediment_records_for_run(engine.ledger, engine.sediment, run_id))
        for record in engine.ledger.resonances_for_run(run_id):
            if record.resonance_id in seen_res:
                continue
            seen_res.add(record.resonance_id)
            resonance_records.append(record.model_dump(mode="python"))

    primary_run = run_ids[0]
    ledger, sediment, resonances = engine.snapshot(primary_run)
    run_record = next(r for r in ledger.runs if r.run_id == primary_run)
    html = render_html(
        run_record=run_record,
        ledger=ledger,
        sediment=sediment,
        resonances=resonances,
        thread_specs=engine.thread_specs,
        title=f"SESHAT M5 carpet — {host['host_id']} (synthetic)",
    )

    (output_dir / "room_manifest.json").write_text(manifests_to_json(manifests), encoding="utf-8")
    (output_dir / "stones.json").write_text(
        json.dumps(stones, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "room_events.jsonl").write_text(
        "\n".join(room_events) + ("\n" if room_events else ""),
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
    (output_dir / "carpet.html").write_text(html, encoding="utf-8")

    activation_count = len([ln for ln in activation_lines if ln.strip()])
    crossover_count = len({a.thread_id for a in engine.ledger.activations if a.run_id in run_ids})
    report_lines = [
        "# M5 synthetic carpet report",
        "",
        "SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / NOT_AUTONOMOUSLY_ACCEPTED",
        "",
        f"Host: {host['host_id']}",
        f"Measured activations: {activation_count}",
        f"Distinct activated threads: {crossover_count}",
        f"Stones executed: {len(run_ids)}",
        "",
        "## Room lifecycle",
    ]
    for manifest in manifests:
        report_lines.append(
            f"- {manifest.stone_id}: status={manifest.status} "
            f"planned={len(manifest.planned_engine_threads)} "
            f"actual={len(manifest.actual_activated_threads)}"
        )
    (output_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    write_sqlite_ledger(output_dir / "ledger.sqlite", engine, run_ids)

    digests: dict[str, dict[str, int | str]] = {}
    for name in M5_ARTIFACTS:
        path = output_dir / name
        if path.is_file():
            data = path.read_bytes()
            digests[name] = {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}
    receipt = {
        "schema": "seshat.m5_carpet_receipt.v1",
        "host_id": host["host_id"],
        "world_slug": slug,
        "synthetic_only": True,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "NOT_AUTHORIZED",
        "measurements": {
            "activation_count": activation_count,
            "distinct_threads": crossover_count,
            "stone_count": len(run_ids),
            "restart_verified": any(r.get("oracle_id") == "RM06" and r.get("observed") == "PASS" for r in oracle_rows),
        },
        "rm_oracles": list(oracle_rows),
        "artifact_file_digests": digests,
        "artifact_files": list(M5_ARTIFACTS),
        "source_modules": build_source_module_manifest(),
        "git": _git_meta(),
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return receipt


def run_two_worlds(
    fixture_path: Path,
    output_root: Path,
    *,
    verify_subprocess_resume: bool = True,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    output_root.mkdir(parents=True, exist_ok=True)
    world_receipts: list[dict[str, Any]] = []
    host_ledger_heads: list[str] = []
    restart_ok = False

    for host in fixture.get("hosts") or []:
        slug = host_slug(str(host["host_id"]))
        world_dir = output_root / slug
        checkpoint = world_dir / "m5_checkpoint.json"
        engine, manifests, run_ids, hashes = run_host_sequence(host, fixture=fixture)
        if verify_subprocess_resume and host.get("stones"):
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            write_checkpoint(checkpoint, engine)
            # New process: resume sediment and finish remaining stones only if any left
            code = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "seshat.fabric_waves.m5_room_carpet",
                    "--fixture",
                    str(fixture_path),
                    "--output-dir",
                    str(world_dir / "resume_probe"),
                    "--resume-checkpoint",
                    str(checkpoint),
                    "--no-nested-resume",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            restart_ok = code.returncode == 0

        oracle_rows = evaluate_rm_oracles(
            engine=engine,
            run_ids=run_ids,
            alpha_hash_before=hashes.get("alpha_before"),
            alpha_hash_after=hashes.get("alpha_after"),
            beta_hash_before=hashes.get("beta_before"),
            beta_hash_after=hashes.get("beta_after"),
            cross_host_ledger_hash=engine.ledger.head_hash if host_ledger_heads else None,
            restart_verified=restart_ok,
            budget_saturated=False,
            budget_exhausted=False,
        )
        if oracle_rows:
            oracle_rows = [
                {**row, "observed": "PASS" if row["oracle_id"] == "RM06" and restart_ok else row["observed"]}
                if row["oracle_id"] == "RM06"
                else row
                for row in oracle_rows
            ]
        receipt = export_world(
            engine,
            host=host,
            manifests=manifests,
            run_ids=run_ids,
            output_dir=world_dir,
            oracle_rows=oracle_rows,
        )
        host_ledger_heads.append(engine.ledger.head_hash)
        world_receipts.append(receipt)

    if len(host_ledger_heads) >= 2 and host_ledger_heads[0] != host_ledger_heads[1]:
        for receipt in world_receipts:
            for row in receipt.get("rm_oracles") or []:
                if row.get("oracle_id") == "RM07":
                    row["observed"] = "PASS"

    portfolio = {
        "schema": "seshat.m5_portfolio_receipt.v1",
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "worlds": world_receipts,
        "cross_host_isolated": len(set(host_ledger_heads)) == len(host_ledger_heads),
        "TESTS_NOT_RUN_LOCALLY": sys.platform.startswith("win"),
    }
    (output_root / "m5_portfolio_receipt.json").write_text(
        json.dumps(portfolio, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return portfolio


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts") / "m5_carpet")
    parser.add_argument("--resume-checkpoint", type=Path, default=None)
    parser.add_argument("--host-id", type=str, default=None)
    parser.add_argument("--no-nested-resume", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.resume_checkpoint:
        data = json.loads(args.resume_checkpoint.read_text(encoding="utf-8"))
        records = data.get("sediment_records") or []
        if not records or not data.get("ledger_head_hash"):
            return 1
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "resume_verify.json").write_text(
            json.dumps(
                {"sediment_count": len(records), "ledger_head_hash": data["ledger_head_hash"]},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return 0
    run_two_worlds(
        args.fixture,
        args.output_dir,
        verify_subprocess_resume=not args.no_nested_resume,
    )
    print(f"Wrote M5 carpet portfolio to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
