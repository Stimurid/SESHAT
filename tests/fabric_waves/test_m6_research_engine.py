"""M6 two-world research engine acceptance (issue #78 minimal vertical slice)."""

import copy
import json
from pathlib import Path

import pytest

from seshat.fabric_waves.m6_research_engine import (
    M6_ARTIFACTS,
    ORIGINAL_FIXTURE_SHA256,
    run_m6_portfolio,
)
from seshat.fabric_waves.m6_report_composer import compose_report_bundle
from seshat.fabric_waves.m6_w2_cycle import (
    admit_synthetic_carrier,
    run_m6_world,
    w2_observations,
)
from seshat.fabric_waves.m6_oracles import evaluate_m6_oracles
from seshat.fabric_waves.m5_room_carpet import load_fixture

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m6_two_world_research_acceptance_20261021_v01.json"
)


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    root = tmp_path_factory.mktemp("m6")
    return run_m6_portfolio(
        FIXTURE,
        root,
        approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
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
        assert bundle.get("w2_admitted") is True
        triad_ids = [r["report_id"] for r in bundle["report_triad"]]
        assert triad_ids == ["R05", "R06", "R07"]


def test_world_u_revised_question_after_w2_overlap(portfolio):
    result, _root = portfolio
    university = next(
        w for w in result["worlds"] if w["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY"
    )
    bundle = university["m6_bundle"]
    assert bundle["initial_question"] != bundle["revised_question"]
    assert "independent labels" in bundle["revised_question"].lower()
    r05 = next(r for r in bundle["reports"] if r["report_id"] == "R05")
    assert r05["status"] == "AVAILABLE"
    assert "content_sha256" in r05.get("w2_provenance", {}) or "digest" in r05["markdown"]
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
    expected_changed = {
        "world-u-synthetic-university": ("m5-world-u-group-beta", "B2"),
        "world-o-synthetic-service": ("m5-world-o-calibration-beta", "O2"),
    }
    for item in manifest["items"]:
        versions = item.get("completed_source_versions")
        assert versions
        assert all(
            v.get("content_sha256")
            and v["content_sha256"] != "UNREADABLE"
            for v in versions
        ), versions
        changed_carrier, changed_version = expected_changed[item["world_slug"]]
        assert any(
            v["carrier_id"] == changed_carrier and v["version"] == changed_version
            for v in versions
        ), versions


def test_mutant_w2_absent_leaves_r05_partial(tmp_path):
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(next(h for h in fixture["hosts"] if h["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY"))
    host["stones"] = [s for s in host["stones"] if s.get("kind") != "W2_RETURN"]
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha, skip_w2=True)
    bundle = compose_report_bundle(world, frontier_probe={"trigger_activation_id": "need-x"})
    assert bundle.get("w2_admitted") is False
    r05 = next(r for r in bundle["reports"] if r["report_id"] == "R05")
    assert r05["status"] == "PARTIAL"


def test_mutant_independent_w2_does_not_force_label_overlap_question(tmp_path):
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(next(h for h in fixture["hosts"] if h["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY"))
    for stone in host["stones"]:
        if stone.get("kind") == "W2_RETURN":
            stone["external_source"]["content"] = (
                "Programme Echo COVERAGE_PROXY; independent_labels=YES; label_independence=CONFIRMED"
            )
            stone["expected_overlap_with_beta"] = False
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha)
    bundle = compose_report_bundle(world)
    assert bundle["revised_question"] == bundle["initial_question"]


def test_m6_true_new_process_resume_with_w2_excluded(tmp_path):
    result = run_m6_portfolio(
        FIXTURE, tmp_path / "m6-resume",
        approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=True,
    )
    assert len(result["worlds"]) == 2
    for world in result["worlds"]:
        evidence = world["resume_evidence"]
        assert evidence["child_process_completed"], evidence
        assert evidence["matches_uninterrupted_control"], evidence
        assert world["rm_summary"]["pass"] == 20, world["rm_summary"]
        assert world["rm_summary"]["not_tested"] == 0


def test_w2_test_adapter_denies_real_uri_before_source_store_mutation():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(
        next(h for h in fixture["hosts"] if h["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY")
    )
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha, skip_w2=True)
    store = world.engine.carrier_store
    assert store is not None
    before = set(store._carriers)
    with pytest.raises(ValueError, match="M6_W2_SOURCE_NOT_IN_TEST_NAMESPACE"):
        admit_synthetic_carrier(
            world, source_uri="https://example.org/private.pdf",
            version="v1", text="not a fictional carrier",
        )
    assert set(store._carriers) == before
    assert not w2_observations(world)


def test_w2_return_does_not_consume_fixture_expected_answer_and_replay_is_pure():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(
        next(h for h in fixture["hosts"] if h["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY")
    )
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha)
    observations = w2_observations(world)
    assert len(observations) == 1
    assert "expected_overlap_with_beta" not in observations[0].payload
    assert observations[0].payload["independent_f07_rights_attested"] is False
    assert "SYNTHETIC_SELF_ASSERTED_RETURN" in observations[0].provenance
    receipts = world.oracle_inputs_extra["m6_w2_receipts"]
    assert [r["status"] for r in receipts] == ["ADMITTED", "IDEMPOTENT_REPLAY"]
    assert receipts[-1]["fresh_sediment"] == 0
    assert receipts[-1]["fresh_activations"] == 0
    bundle = compose_report_bundle(world)
    rows = evaluate_m6_oracles(world, bundle, operator_markdown="Synthetic-only receipt")
    rx11 = next(r for r in rows if r["oracle_id"] == "RX11")
    assert rx11["observed"] == "PASS", rx11
    receipts[-1]["fresh_sediment"] = 1
    mutated = evaluate_m6_oracles(world, bundle, operator_markdown="Synthetic-only receipt")
    assert next(r for r in mutated if r["oracle_id"] == "RX11")["observed"] == "FAIL"


def test_m6_oracle_rejects_forged_synthetic_uri_in_report():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(
        next(h for h in fixture["hosts"] if h["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY")
    )
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha)
    bundle = compose_report_bundle(world)
    rows = evaluate_m6_oracles(
        world, bundle,
        operator_markdown="Alleged support: `synthetic://world-u/not-admitted`",
    )
    assert next(r for r in rows if r["oracle_id"] == "RX06")["observed"] == "FAIL"


def test_f09a_done_artifact_mutation_fails_before_skip(tmp_path):
    from seshat.fabric_waves.m5_checkpoint import CheckpointRejected

    root = tmp_path / "qualified"
    run_m6_portfolio(
        FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
    )
    manifest_path = root / "f09a_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert all(item.get("artifact_hashes") for item in manifest["items"])
    manifest["items"][0]["artifact_hashes"]["m6_report_bundle.json"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    with pytest.raises(CheckpointRejected, match="F09A_ARTIFACT_HASH_MISMATCH"):
        run_m6_portfolio(
            FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
            verify_subprocess_resume=False,
            f09a_resume_after_slug="world-u-synthetic-university",
        )


def test_f09a_missing_or_forged_source_version_refuses_done_skip(tmp_path):
    from seshat.fabric_waves.m5_checkpoint import CheckpointRejected

    root = tmp_path / "versioned"
    run_m6_portfolio(
        FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
    )
    manifest_path = root / "f09a_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["items"][0]["completed_source_versions"][0]["content_sha256"] = "UNREADABLE"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    with pytest.raises(CheckpointRejected, match="F09A_DONE_SOURCE_VERSION_INVALID"):
        run_m6_portfolio(
            FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
            verify_subprocess_resume=False,
            f09a_resume_after_slug="world-u-synthetic-university",
        )


def test_f09a_new_process_resume_preserves_completed_world_bytes(tmp_path):
    import shutil
    import subprocess
    import sys

    first_slug = "world-u-synthetic-university"
    second_slug = "world-o-synthetic-service"
    completed = tmp_path / "full"
    run_m6_portfolio(
        FIXTURE, completed, approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
    )
    root = tmp_path / "resumed"
    root.mkdir()
    shutil.copytree(completed / first_slug, root / first_slug)
    manifest = json.loads(
        (completed / "f09a_batch_manifest.json").read_text(encoding="utf-8")
    )
    first_sources = copy.deepcopy(manifest["items"][0]["completed_source_versions"])
    first_hashes = copy.deepcopy(manifest["items"][0]["artifact_hashes"])
    manifest["items"][1]["state"] = "QUEUED"
    manifest["items"][1].pop("artifact_hashes", None)
    manifest["items"][1]["completed_source_versions"] = []
    (root / "f09a_batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    before = (root / first_slug / "m6_report_bundle.json").read_bytes()
    child = subprocess.run(
        [
            sys.executable, "-m", "seshat.fabric_waves.m6_research_engine",
            "--fixture", str(FIXTURE),
            "--fixture-sha256", ORIGINAL_FIXTURE_SHA256,
            "--output-dir", str(root),
            "--f09a-resume-after", first_slug,
            "--no-subprocess-resume",
        ],
        capture_output=True, text=True, check=False,
    )
    assert child.returncode == 0, child.stderr
    assert (root / second_slug / "m6_report_bundle.json").is_file()
    assert (root / first_slug / "m6_report_bundle.json").read_bytes() == before
    after = json.loads(
        (root / "f09a_batch_manifest.json").read_text(encoding="utf-8")
    )
    assert all(item["state"] == "DONE" for item in after["items"])
    assert after["items"][0]["completed_source_versions"] == first_sources
    assert after["items"][0]["artifact_hashes"] == first_hashes
    assert after["items"][1]["artifact_hashes"]
    assert any(
        v.get("version") == "O2"
        for v in after["items"][1]["completed_source_versions"]
    )
