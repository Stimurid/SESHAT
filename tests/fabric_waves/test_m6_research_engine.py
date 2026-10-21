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
from seshat.fabric_waves.m6_w2_cycle import run_m6_world
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
    for item in manifest["items"]:
        assert item.get("completed_source_versions")


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


def test_m6_new_process_resume_is_a_real_m5_subgraph(tmp_path):
    """A distinct Python process must resume the three M5 stones; W2 is excluded from this proof."""
    result = run_m6_portfolio(
        FIXTURE, tmp_path,
        approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=True,
    )
    for item in result["worlds"]:
        probe = item["resume_evidence"]
        assert probe and probe["child_process_completed"] is True, probe
        assert probe["matches_uninterrupted_control"] is True, probe
        assert probe["scope"] == "M5_SUBGRAPH_NEW_PROCESS_ONLY_NOT_F09A_W2_REPLAY"
        assert item["rm_summary"]["fail"] == 0
        assert item["rm_summary"]["not_tested"] == 0


def test_m6_w2_refuses_real_and_foreign_schemes_without_carrier_injection():
    from seshat.fabric_waves.m6_w2_cycle import admit_synthetic_carrier
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(fixture["hosts"][0])
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha, skip_w2=True)
    store = world.engine.carrier_store
    assert store is not None
    original = set(store._carriers)
    for forbidden in (
        "https://example.org/actual-research.pdf",
        "synthetic://world-o/other-world",
        "synthetic://world-u/",
    ):
        with pytest.raises(ValueError, match="M6_W2_REAL_OR_UNVERIFIED_CARRIER_FORBIDDEN"):
            admit_synthetic_carrier(world, source_uri=forbidden, version="v1", text="invented")
        assert set(store._carriers) == original
    world.oracle_inputs_extra["m6_synthetic_test_context"] = False
    with pytest.raises(ValueError, match="M6_W2_REAL_OR_UNVERIFIED_CARRIER_FORBIDDEN"):
        admit_synthetic_carrier(world, source_uri="synthetic://world-u/test", version="v1", text="x")
    assert set(store._carriers) == original


def test_m6_w2_denies_missing_test_grant_and_does_not_trust_expectations():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    host = copy.deepcopy(fixture["hosts"][0])
    w2 = next(s for s in host["stones"] if s.get("kind") == "W2_RETURN")
    w2["external_source"]["rights"] = "DENIED"
    with pytest.raises(ValueError, match="M6_W2_NO_SYNTHETIC_TEST_GRANT"):
        run_m6_world(host, fixture=fixture, fixture_sha256=sha)
    w2["external_source"]["rights"] = "SYNTHETIC_OWNER_GRANT"
    w2["expected_overlap_with_beta"] = False
    world = run_m6_world(host, fixture=fixture, fixture_sha256=sha)
    from seshat.fabric_waves.m6_w2_cycle import w2_observations
    payload = w2_observations(world)[0].payload
    assert payload["sample_overlap_with_beta"] is True  # evidenced only by W2 bytes
    assert "expected_overlap_with_beta" not in payload
    assert "SYNTHETIC_SELF_ASSERTED_RETURN" in w2_observations(world)[0].provenance
    assert world.oracle_inputs_extra["m6_w2_receipts"][0]["source_authority"] == "TEST_FIXTURE_NOT_REAL_F07"


def test_m6_phantom_synthetic_uri_fails_in_customer_report():
    from seshat.fabric_waves.m6_oracles import evaluate_m6_oracles
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    world = run_m6_world(fixture["hosts"][0], fixture=fixture, fixture_sha256=sha)
    bundle = compose_report_bundle(world)
    counterfeit = copy.deepcopy(bundle)
    counterfeit["reports"][0]["markdown"] += " \x60synthetic://world-u/forged-unregistered\x60"
    rows = {r["oracle_id"]: r for r in evaluate_m6_oracles(world, counterfeit, operator_markdown="")}
    assert rows["RX06"]["observed"] == "FAIL"


def test_m6_human_refusal_requires_attempt_not_aporia_label():
    from seshat.fabric_waves.m6_oracles import evaluate_m6_oracles
    from seshat.fabric_waves.m5_room_carpet import _unauthorized_decision_probe
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    world = run_m6_world(fixture["hosts"][0], fixture=fixture, fixture_sha256=sha)
    bundle = compose_report_bundle(world)
    def rx05():
        return next(r for r in evaluate_m6_oracles(world, bundle, operator_markdown="") if r["oracle_id"] == "RX05")
    assert rx05()["observed"] == "NOT_TESTED"
    world.oracle_inputs_extra["m6_human_refusal"] = _unauthorized_decision_probe(world)
    assert rx05()["observed"] == "PASS"
    world.oracle_inputs_extra["m6_human_refusal"] = {"attempted": True, "rejected": False, "accepted_view_size_after": 1}
    assert rx05()["observed"] == "FAIL"
