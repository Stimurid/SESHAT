"""Independent child-process probe for the M5 portion of an M6 synthetic world.

The M6 W2_RETURN event is deliberately not interpreted by the M5 checkpoint
reader. This probe restores only the M5 stones, with the *same approved fixture*
and genuine checkpoint source/version checks, then exports observed evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from seshat.fabric_waves.m5_checkpoint import CheckpointRejected, load_checkpoint
from seshat.fabric_waves.m5_room_carpet import load_fixture, run_world
from seshat.fabric_waves.m6_w2_cycle import split_host_stones


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M6 synthetic M5-stage resume verifier")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--fixture-sha256", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--resume-checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    fixture, fixture_sha = load_fixture(
        args.fixture, approved_sha256=args.fixture_sha256
    )
    host = next(
        (h for h in fixture.get("hosts") or () if str(h["host_id"]) == args.host_id),
        None,
    )
    if host is None:
        raise CheckpointRejected("M6_M5_RESUME_UNKNOWN_HOST")

    host_m5, _w2_returns = split_host_stones(host)
    checkpoint = load_checkpoint(args.resume_checkpoint)
    world = run_world(
        host_m5,
        fixture=fixture,
        fixture_sha256=fixture_sha,
        resume_from=checkpoint,
    )
    evidence = {
        "schema": "seshat.m5_resume_evidence.v1",
        "host_id": args.host_id,
        "resumed_from_cursor": world.started_at_cursor,
        "continued_stone_ids": [outcome.stone_id for outcome in world.outcomes],
        "aporia_activations": [
            activation.activation_id
            for activation in world.engine.ledger.activations
            if activation.error_code == "BODY_APORIA"
        ],
        "ledger_head": world.engine.ledger.head_hash,
        "sediment_payload_hashes": sorted(
            [record.sediment_id, record.payload_hash]
            for record in world.engine.sediment.all_records()
        ),
        "scope": "M5_STAGE_ONLY_BEFORE_EXTERNAL_W2",
        "synthetic_only": True,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "resume_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
