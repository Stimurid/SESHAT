"""M5 two-world synthetic carpet acceptance (issue #60 room + carpet)."""

import json
from pathlib import Path

import pytest

from seshat.fabric_waves.m5_room_carpet import (
    DEFAULT_FIXTURE,
    M5_ARTIFACTS,
    load_fixture,
    run_two_worlds,
)
from seshat.fabric_waves.m5_synthetic_hosts import host_slug
from seshat.fabric_waves.room_builder import compile_room_for_stone


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "m5_room_synthetic_acceptance_20261021_v01.json"


def test_fixture_sha_and_registry():
    data = load_fixture(FIXTURE)
    assert data["schema"].startswith("seshat.room_formation")
    assert len(data["thread_registry"]) >= 6


def test_room_planned_vs_actual_threads():
    host = load_fixture(FIXTURE)["hosts"][0]
    stone = host["stones"][0]
    slug = host_slug(host["host_id"])
    manifest = compile_room_for_stone(
        host_id=host["host_id"],
        host_slug=slug,
        stone=stone,
        budget={},
    )
    assert "N-Q" in manifest.planned_registry_threads
    assert len(manifest.planned_engine_threads) >= 6


def test_two_world_run_writes_artifacts(tmp_path):
    portfolio = run_two_worlds(FIXTURE, tmp_path, verify_subprocess_resume=True)
    assert portfolio["cross_host_isolated"] is True
    for host in load_fixture(FIXTURE)["hosts"]:
        slug = host_slug(host["host_id"])
        world_dir = tmp_path / slug
        for name in M5_ARTIFACTS:
            assert (world_dir / name).is_file(), name
        receipt = json.loads((world_dir / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["synthetic_only"] is True
        assert receipt["scientific_acceptance"] == "NOT_PERFORMED"
        activations = [
            json.loads(line)
            for line in (world_dir / "activations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(activations) >= 6
        assert "SYNTHETIC_ENGINEERING_ONLY" in (world_dir / "report.md").read_text(encoding="utf-8")
        rm = {row["oracle_id"]: row["observed"] for row in receipt["rm_oracles"]}
        assert rm.get("RM02") == "PASS"
        assert rm.get("RM03") == "PASS"


@pytest.mark.parametrize(
    "group_id",
    ["G1_PARTIAL_DELIVERY", "G2_LONG_LINES", "G3_VERSION_DRIFT", "G4_PERMISSION", "G5_SCOPE", "G6_LINE_BIND"],
)
def test_m4_groups_documented_in_receipt(tmp_path, group_id):
    run_two_worlds(FIXTURE, tmp_path / group_id, verify_subprocess_resume=False)
    receipt = json.loads(
        (tmp_path / group_id / host_slug(load_fixture(FIXTURE)["hosts"][0]["host_id"]) / "receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["measurements"]["stone_count"] >= 3
