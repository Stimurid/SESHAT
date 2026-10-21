"""M6 research-to-action engine: M5 carpet execution + R01–R07 bundle + F09A resume.

SYNTHETIC ONLY. Does not merge PR #76/#77, deploy, or assert scientific acceptance.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Sequence

from seshat.fabric_waves.m5_checkpoint import CheckpointRejected, load_checkpoint, write_checkpoint
from seshat.fabric_waves.m5_oracles import evaluate_rm_oracles, oracle_summary
from seshat.fabric_waves.m5_oracles import OracleInputs
from seshat.fabric_waves.m5_room_carpet import (
    _budget_probe,
    _compare_resume,
    _excluded_source_probe,
    _foreign_checkpoint_probe,
    _frontier_probe,
    _partial_checkpoint,
    _rights_probe,
    _self_attestation_probe,
    _unauthorized_decision_probe,
    export_world,
    load_fixture,
    run_world,
)
from seshat.fabric_waves.m6_w2_cycle import completed_source_versions, run_m6_world, split_host_stones
from seshat.fabric_waves.m5_synthetic_hosts import host_slug
from seshat.fabric_waves.m6_oracles import evaluate_m6_oracles
from seshat.fabric_waves.m6_report_composer import (
    bundle_to_json,
    compose_report_bundle,
    render_public_html,
    render_public_markdown,
)

PACKAGE_FIXTURE_NAME = "m6_two_world_research_acceptance_20261021_v01.json"
ORIGINAL_FIXTURE_SHA256 = (
    "fcebb73cb3f546a782af5e268e2795c2bd5de818ae222dafe346c74ffcfab479"
)
F09A_MANIFEST_VERSION = "F09A-M6-1"
M6_ARTIFACTS: tuple[str, ...] = (
    "m6_report_bundle.json",
    "m6_report.md",
    "m6_report.html",
    "m6_oracles.json",
    "m6_external_ledger.json",
    "carpet.html",
    "f09a_batch_manifest.json",
    "f09a_batch_receipt.json",
)


def packaged_fixture_path() -> Path | None:
    try:
        from importlib.resources import files

        resource = files("seshat.fabric_waves.m6_fixtures") / PACKAGE_FIXTURE_NAME
        path = Path(str(resource))
        return path if path.is_file() else None
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        return None


def default_fixture_path() -> Path | None:
    packaged = packaged_fixture_path()
    if packaged is not None:
        return packaged
    repo_copy = (
        Path(__file__).resolve().parents[3] / "tests" / "fixtures" / PACKAGE_FIXTURE_NAME
    )
    return repo_copy if repo_copy.is_file() else None


def _write_f09a_manifest(
    output_root: Path,
    *,
    fixture_sha256: str,
    world_slugs: Sequence[str],
    completed: Sequence[str],
    world_source_snapshots: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> dict[str, Any]:
    snapshots = world_source_snapshots or {}
    manifest = {
        "manifest_version": F09A_MANIFEST_VERSION,
        "fixture_sha256": fixture_sha256,
        "concurrency": 1,
        "items": [
            {
                "world_slug": slug,
                "state": "DONE" if slug in completed else "QUEUED",
                "completed_source_versions": list(snapshots.get(slug) or ()),
            }
            for slug in world_slugs
        ],
        "synthetic_only": True,
    }
    (output_root / "f09a_batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return manifest


def _run_world_with_m6_exports(
    host: dict[str, Any],
    *,
    fixture: dict[str, Any],
    fixture_sha256: str,
    output_dir: Path,
    fixture_path: Path,
    verify_subprocess_resume: bool,
    portfolio_checkpoints: dict[str, Any],
) -> dict[str, Any]:
    world = run_m6_world(host, fixture=fixture, fixture_sha256=fixture_sha256)
    slug = world.slug
    output_dir.mkdir(parents=True, exist_ok=True)

    host_m5, _w2_only = split_host_stones(host)
    resume_evidence: dict[str, Any] | None = None
    if verify_subprocess_resume and len(host_m5.get("stones") or []) > 1:
        partial_cp = _partial_checkpoint(host_m5, fixture, fixture_sha256, stones_to_run=1)
        cp_path = output_dir / "resume_after_first_stone.json"
        write_checkpoint(cp_path, partial_cp)
        child_dir = output_dir / "resume_probe"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "seshat.fabric_waves.m6_research_engine",
                "--resume-m5-subgraph-checkpoint",
                str(cp_path),
                "--fixture",
                str(fixture_path),
                "--fixture-sha256",
                fixture_sha256,
                "--host-id",
                str(host["host_id"]),
                "--output-dir",
                str(child_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # Compare like with like: the child resumes the M5 source subgraph.
        # W2 is a later synthetic external return, not in that checkpoint.
        core_control = run_world(host_m5, fixture=fixture, fixture_sha256=fixture_sha256)
        resume_evidence = _compare_resume(completed, child_dir, control=core_control)
        resume_evidence["scope"] = "M5_SUBGRAPH_NEW_PROCESS_ONLY_NOT_F09A_W2_REPLAY"

    frontier = world.oracle_inputs_extra.get("m6_frontier_probe") or _frontier_probe(world)
    budget_probe = _budget_probe(world)
    foreign = next(
        (cp for hid, cp in portfolio_checkpoints.items() if hid != str(host["host_id"])),
        None,
    )
    from seshat.fabric_waves.m5_room_carpet import (
        _operator_known_identifiers,
        _operator_sections,
        render_operator_report,
    )

    sections, filtered_refs = _operator_sections(world)
    operator_report_md = render_operator_report(world, sections)
    from seshat.fabric_waves.m5_room_carpet import _checkpoint_for

    checkpoint = _checkpoint_for(world)
    inputs = OracleInputs(
        engine=world.engine,
        run_ids=world.run_ids,
        manifests=world.manifests,
        alpha_before=world.oracle_inputs_extra.get("alpha_before"),
        alpha_after=world.oracle_inputs_extra.get("alpha_after"),
        beta_before=world.oracle_inputs_extra.get("beta_before"),
        beta_after=world.oracle_inputs_extra.get("beta_after"),
        delta_run_id=world.oracle_inputs_extra.get("delta_run_id"),
        source_before=world.oracle_inputs_extra.get("source_before") or {},
        source_after=world.oracle_inputs_extra.get("source_after") or {},
        frontier_capability_id=frontier["capability"],
        frontier_admitted_before=frontier["admitted_before"],
        frontier_admitted_after=frontier["admitted_after"],
        frontier_fired_activation_id=frontier["fired_activation_id"],
        frontier_trigger_activation_id=frontier["trigger_activation_id"],
        resume_evidence=resume_evidence,
        duplicate_stone_evidence=world.oracle_inputs_extra.get("duplicate_stone"),
        foreign_reference_rejection=_foreign_checkpoint_probe(world, foreign),
        excluded_source_rejection=_excluded_source_probe(world),
        rights_denied_probe=_rights_probe(world),
        unauthorized_decision_rejection=_unauthorized_decision_probe(world),
        self_attestation_probe=_self_attestation_probe(world, checkpoint),
        budget_exhausted_run_id=budget_probe.get("run_id"),
        saturated_run_id=next((o.run_id for o in world.outcomes if o.kind == "QUERY" and o.run_id), None),
        sediment_versions_before_close=world.oracle_inputs_extra.get("sediment_versions_before_close"),
        sediment_versions_after_close=world.oracle_inputs_extra.get("sediment_versions_after_close"),
        operator_answer_refs=filtered_refs,
        operator_report_markdown=operator_report_md,
        operator_known_identifiers=_operator_known_identifiers(world),
        stale_after_delta_ids=world.oracle_inputs_extra.get("stale_after_delta"),
        capability_binding=world.binding,
    )
    rm_rows = evaluate_rm_oracles(inputs)
    m5_receipt = export_world(
        world, output_dir=output_dir, oracle_rows=rm_rows, checkpoint=checkpoint
    )

    bundle = compose_report_bundle(world, frontier_probe=frontier)
    (output_dir / "m6_report_bundle.json").write_text(bundle_to_json(bundle), encoding="utf-8")
    (output_dir / "m6_report.md").write_text(render_public_markdown(bundle), encoding="utf-8")
    (output_dir / "m6_report.html").write_text(render_public_html(bundle), encoding="utf-8")

    m6_rows = evaluate_m6_oracles(world, bundle, operator_markdown=operator_report_md)
    (output_dir / "m6_oracles.json").write_text(
        json.dumps(m6_rows, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    ledger = world.oracle_inputs_extra.get("m6_external_ledger")
    if ledger:
        (output_dir / "m6_external_ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    return {
        "world_slug": slug,
        "host_id": host["host_id"],
        "m5_receipt": m5_receipt,
        "m6_bundle": bundle,
        "checkpoint": checkpoint,
        "rm_summary": oracle_summary(rm_rows),
        "m6_summary": oracle_summary(m6_rows),
        "frontier_probe": frontier,
        "resume_evidence": resume_evidence,
        "completed_source_versions": completed_source_versions(world),
    }


def run_m6_portfolio(
    fixture_path: Path,
    output_root: Path,
    *,
    approved_sha256: str | None = None,
    verify_subprocess_resume: bool = True,
    f09a_resume_after_slug: str | None = None,
) -> dict[str, Any]:
    pin = approved_sha256 or ORIGINAL_FIXTURE_SHA256
    fixture, fixture_sha = load_fixture(fixture_path, approved_sha256=pin)

    output_root.mkdir(parents=True, exist_ok=True)
    hosts = list(fixture.get("hosts") or [])
    slugs = [host_slug(str(h["host_id"])) for h in hosts]

    checkpoints: dict[str, Any] = {}
    checkpoint_objects: dict[str, Any] = {}
    world_results: list[dict[str, Any]] = []
    completed_slugs: list[str] = []
    source_snapshots: dict[str, list[dict[str, str]]] = {}

    if f09a_resume_after_slug:
        manifest_path = output_root / "f09a_batch_manifest.json"
        if not manifest_path.is_file():
            raise CheckpointRejected("F09A_RESUME_MANIFEST_MISSING")
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        completed_slugs = [
            item["world_slug"]
            for item in prior.get("items") or ()
            if item.get("state") == "DONE"
        ]

    for host in hosts:
        slug = host_slug(str(host["host_id"]))
        if f09a_resume_after_slug and slug in completed_slugs:
            continue
        if f09a_resume_after_slug and completed_slugs and slug != f09a_resume_after_slug:
            # Serial batch: only the next queued world after resume marker.
            if slug != next(s for s in slugs if s not in completed_slugs):
                continue

        world_dir = output_root / slug
        result = _run_world_with_m6_exports(
            host,
            fixture=fixture,
            fixture_sha256=fixture_sha,
            output_dir=world_dir,
            fixture_path=fixture_path,
            verify_subprocess_resume=verify_subprocess_resume,
            portfolio_checkpoints=checkpoint_objects,
        )
        checkpoints[str(host["host_id"])] = result["m5_receipt"]
        checkpoint_objects[str(host["host_id"])] = result.get("checkpoint")
        world_results.append(result)
        completed_slugs.append(slug)
        source_snapshots[slug] = list(result.get("completed_source_versions") or ())

    manifest = _write_f09a_manifest(
        output_root,
        fixture_sha256=fixture_sha,
        world_slugs=slugs,
        completed=completed_slugs,
        world_source_snapshots=source_snapshots,
    )
    receipt = {
        "schema": "seshat.m6_f09a_receipt.v1",
        "manifest_version": F09A_MANIFEST_VERSION,
        "fixture_sha256": fixture_sha,
        "completed_world_slugs": completed_slugs,
        "synthetic_only": True,
    }
    (output_root / "f09a_batch_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    incomplete = [
        w["world_slug"]
        for w in world_results
        if w["m6_bundle"].get("report_completeness") != "REPORT_COMPLETE"
    ]
    portfolio = {
        "schema": "seshat.m6_portfolio_receipt.v1",
        "fixture_path": str(fixture_path),
        "fixture_sha256": fixture_sha,
        "f09a_manifest": manifest,
        "worlds": world_results,
        "report_incomplete_worlds": incomplete,
        "synthetic_only": True,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "NOT_AUTHORIZED",
        "pr77_reconciliation": "NOT_MERGED_IN_THIS_BRANCH",
        "independent_source_review": "NOT_PERFORMED",
    }
    (output_root / "m6_portfolio_receipt.json").write_text(
        json.dumps(portfolio, ensure_ascii=False, sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    return portfolio


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SESHAT M6 synthetic research engine")
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--fixture-sha256", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts") / "m6_research")
    parser.add_argument("--no-subprocess-resume", action="store_true")
    parser.add_argument("--resume-m5-subgraph-checkpoint", type=Path, default=None)
    parser.add_argument("--host-id", type=str, default=None)
    parser.add_argument(
        "--f09a-resume-after",
        type=str,
        default=None,
        help="slug of last completed world for serial F09A resume",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    fixture_path = args.fixture or default_fixture_path()
    if fixture_path is None:
        print("No M6 fixture found", file=sys.stderr)
        return 2
    if args.resume_m5_subgraph_checkpoint:
        if not args.host_id:
            print("--resume-m5-subgraph-checkpoint requires --host-id", file=sys.stderr)
            return 2
        fixture, fixture_sha = load_fixture(Path(fixture_path), approved_sha256=args.fixture_sha256 or ORIGINAL_FIXTURE_SHA256)
        host = next((h for h in fixture.get("hosts") or () if str(h.get("host_id")) == args.host_id), None)
        if host is None:
            raise CheckpointRejected("M6_SUBGRAPH_UNKNOWN_HOST")
        core_host, _ = split_host_stones(host)
        cp = load_checkpoint(args.resume_m5_subgraph_checkpoint)
        world = run_world(core_host, fixture=fixture, fixture_sha256=fixture_sha, resume_from=cp)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        aporias = [a.activation_id for a in world.engine.ledger.activations if a.error_code == "BODY_APORIA"]
        evidence = {
            "schema": "seshat.m5_resume_evidence.v1",
            "host_id": args.host_id,
            "resumed_from_cursor": world.started_at_cursor,
            "continued_stone_ids": [o.stone_id for o in world.outcomes],
            "aporia_activations": aporias,
            "ledger_head": world.engine.ledger.head_hash,
            "sediment_payload_hashes": sorted([r.sediment_id, r.payload_hash] for r in world.engine.sediment.all_records()),
            "scope": "M5_SUBGRAPH_ONLY_NO_W2_REPLAY",
        }
        (args.output_dir / "resume_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        return 0
    portfolio = run_m6_portfolio(
        Path(fixture_path),
        args.output_dir,
        approved_sha256=args.fixture_sha256,
        verify_subprocess_resume=not args.no_subprocess_resume,
        f09a_resume_after_slug=args.f09a_resume_after,
    )
    print(f"Wrote M6 portfolio to {args.output_dir.resolve()}")
    if portfolio.get("report_incomplete_worlds"):
        print(
            f"REPORT_INCOMPLETE worlds: {', '.join(portfolio['report_incomplete_worlds'])}",
            file=sys.stderr,
        )
        return 1
    rm_failed = sorted(
        {
            oid
            for w in portfolio["worlds"]
            for oid in w["rm_summary"].get("failed_ids") or ()
        }
    )
    if rm_failed:
        print(f"M5 RM FAIL: {', '.join(rm_failed)}", file=sys.stderr)
        return 1
    m6_failed = sorted(
        {
            oid
            for w in portfolio["worlds"]
            for oid in w["m6_summary"].get("failed_ids") or ()
        }
    )
    if m6_failed:
        print(f"M6 RX FAIL: {', '.join(m6_failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
