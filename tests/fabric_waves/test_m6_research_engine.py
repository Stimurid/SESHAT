"""M6 two-world research engine acceptance (issue #78 minimal vertical slice)."""

import json
from pathlib import Path

import pytest

from seshat.fabric_waves.m6_research_engine import (
    M6_ARTIFACTS,
    ORIGINAL_FIXTURE_SHA256,
    run_m6_portfolio,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m6_two_world_research_acceptance_20261021_v01.json"
)


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    root = tmp_path_factory.mktemp("m6")
    return run_m6_portfolio(
        FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256, verify_subprocess_resume=True
    ), root


def test_m6_fixture_pin():
    import hashlib

    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert digest == ORIGINAL_FIXTURE_SHA256


def test_m6_artifacts_and_report_triad(portfolio):
    result, root = portfolio
    assert not result.get("report_incomplete_worlds")
    for world in result["worlds"]:
        slug = world["world_slug"]
        world_dir = root / slug
        world_artifacts = tuple(a for a in M6_ARTIFACTS if not a.startswith("f09a_"))
        for name in world_artifacts:
            assert (world_dir / name).is_file(), f"{slug}/{name}"
        bundle = json.loads((world_dir / "m6_report_bundle.json").read_text(encoding="utf-8"))
        assert bundle["report_completeness"] == "REPORT_COMPLETE"
        triad_ids = [r["report_id"] for r in bundle["report_triad"]]
        assert triad_ids == ["R05", "R06", "R07"]


def test_world_u_revised_question_and_noncomparable_ranking(portfolio):
    result, _root = portfolio
    university = next(
        w for w in result["worlds"] if w["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY"
    )
    bundle = university["m6_bundle"]
    assert bundle["initial_question"] != bundle["revised_question"]
    assert "label" in bundle["revised_question"].lower()
    r06 = next(r for r in bundle["reports"] if r["report_id"] == "R06")
    assert "NONCOMPARABLE" in r06["markdown"]


def test_world_o_service_rights_in_r07(portfolio):
    result, _root = portfolio
    service = next(w for w in result["worlds"] if w["host_id"] == "WORLD_O_SYNTHETIC_SERVICE")
    r07 = next(r for r in service["m6_bundle"]["reports"] if r["report_id"] == "R07")
    assert "DecisionRight" in r07["markdown"]


def test_m5_rm_matrix_still_passes(portfolio):
    result, _root = portfolio
    for world in result["worlds"]:
        summary = world["rm_summary"]
        assert summary["fail"] == 0, summary


def test_m6_rx_oracles_pass(portfolio):
    result, _root = portfolio
    for world in result["worlds"]:
        assert world["m6_summary"]["fail"] == 0, world["m6_summary"]


def test_f09a_manifest_serial_complete(portfolio, tmp_path):
    _result, root = portfolio
    for name in ("f09a_batch_manifest.json", "f09a_batch_receipt.json"):
        assert (root / name).is_file()
    manifest = json.loads((root / "f09a_batch_manifest.json").read_text(encoding="utf-8"))
    assert all(item["state"] == "DONE" for item in manifest["items"])
    assert manifest["concurrency"] == 1
