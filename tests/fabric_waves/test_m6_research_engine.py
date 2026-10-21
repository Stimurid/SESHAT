"""M6 two-world research engine acceptance (issue #78 minimal vertical slice)."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from seshat.fabric_waves.m5_checkpoint import CheckpointRejected

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
        if item["state"] == "DONE":
            assert item.get("artifact_hashes")
            assert item["artifact_hashes"].get("m6_report_bundle.json")


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


def test_f09a_resume_rejects_forged_artifact_hash(tmp_path):
    first = tmp_path / "batch"
    run_m6_portfolio(
        FIXTURE,
        first,
        approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
    )
    manifest_path = first / "f09a_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["items"][0]["artifact_hashes"]["m6_report_bundle.json"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    with pytest.raises(CheckpointRejected, match="F09A_ARTIFACT_HASH_MISMATCH"):
        run_m6_portfolio(
            FIXTURE,
            first,
            approved_sha256=ORIGINAL_FIXTURE_SHA256,
            verify_subprocess_resume=False,
            f09a_resume_after_slug="world-u-synthetic-university",
        )


def test_f09a_new_process_resume_completes_second_world(tmp_path):
    import shutil

    u_slug = "world-u-synthetic-university"
    o_slug = "world-o-synthetic-service"
    full = tmp_path / "full"
    run_m6_portfolio(
        FIXTURE,
        full,
        approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=True,
    )
    resume_root = tmp_path / "resume"
    resume_root.mkdir()
    shutil.copytree(full / u_slug, resume_root / u_slug)
    manifest = json.loads((full / "f09a_batch_manifest.json").read_text(encoding="utf-8"))
    manifest["items"][1]["state"] = "QUEUED"
    manifest["items"][1].pop("artifact_hashes", None)
    (resume_root / "f09a_batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    u_bundle_before = (resume_root / u_slug / "m6_report_bundle.json").read_bytes()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "seshat.fabric_waves.m6_research_engine",
            "--fixture",
            str(FIXTURE),
            "--output-dir",
            str(resume_root),
            "--f09a-resume-after",
            u_slug,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (resume_root / o_slug / "m6_report_bundle.json").is_file()
    assert (resume_root / u_slug / "m6_report_bundle.json").read_bytes() == u_bundle_before
    final = json.loads((resume_root / "f09a_batch_manifest.json").read_text(encoding="utf-8"))
    assert all(item["state"] == "DONE" for item in final["items"])


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


def test_m6_current_source_reporting_uses_b2_not_stale_b1(portfolio):
    output, _root = portfolio
    u = next(x for x in output["worlds"] if x["host_id"] == "WORLD_U_SYNTHETIC_UNIVERSITY")
    r03 = next(x for x in u["m6_bundle"]["reports"] if x["report_id"] == "R03")
    r06 = next(x for x in u["m6_bundle"]["reports"] if x["report_id"] == "R06")
    assert "group-beta@B2: coverage_proxy denominator=20" in r03["markdown"]
    assert "group-beta@B1: coverage_proxy denominator=18" not in r03["markdown"]
    assert "group-alpha@A1: coverage_proxy denominator=30" in r03["markdown"]
    assert "denominator=20" in r06["markdown"]
    assert "denominator=30" in r06["markdown"]
    assert "NONCOMPARABLE" in r06["markdown"]


def test_m6_w2_duplicate_is_witnessed_with_no_second_evidence():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    world = run_m6_world(fixture["hosts"][0], fixture=fixture, fixture_sha256=sha)
    receipts = world.oracle_inputs_extra["m6_w2_receipts"]
    assert len(receipts) == 2
    assert receipts[0]["status"] == "SYNTHETIC_SELF_ASSERTED_RETURN"
    assert receipts[1]["status"] == "IDEMPOTENT_REPLAY"
    assert receipts[1]["verified_no_new_evidence"] is True
    ledger = world.oracle_inputs_extra["m6_external_ledger"]
    assert len(ledger["evidence_returns"]) == 1


def test_f09a_finished_batch_duplicate_new_process_preserves_exact_portfolio(tmp_path):
    root = tmp_path / "batch"
    run_m6_portfolio(
        FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=True,
    )
    names = ["f09a_batch_manifest.json", "f09a_batch_receipt.json", "m6_portfolio_receipt.json"]
    before = {name: (root / name).read_bytes() for name in names}
    resumed = subprocess.run(
        [sys.executable, "-m", "seshat.fabric_waves.m6_research_engine",
         "--fixture", str(FIXTURE), "--output-dir", str(root),
         "--f09a-resume-after", "world-o-synthetic-service"],
        capture_output=True, text=True, check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    after = {name: (root / name).read_bytes() for name in names}
    assert after == before
    assert len(json.loads(after["m6_portfolio_receipt.json"])["worlds"]) == 2


@pytest.mark.parametrize("mutate", ["ledger", "oracle", "version", "phantom"])
def test_f09a_refuses_changed_ledger_or_version_and_missing_prior_artifact(tmp_path, mutate):
    root = tmp_path / mutate
    run_m6_portfolio(
        FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
        verify_subprocess_resume=False,
    )
    world = root / "world-u-synthetic-university"
    manifest_file = root / "f09a_batch_manifest.json"
    if mutate in {"ledger", "oracle"}:
        name = "m6_external_ledger.json" if mutate == "ledger" else "m6_oracles.json"
        with (world / name).open("a", encoding="utf-8") as stream:
            stream.write("\n")
        expected = "F09A_ARTIFACT_HASH_MISMATCH"
    elif mutate == "version":
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["items"][0]["completed_source_versions"][0]["version"] = "FORGED"
        manifest_file.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        expected = "F09A_SOURCE_VERSIONS_MISMATCH"
    else:
        import shutil
        shutil.rmtree(world)
        expected = "F09A_PHANTOM_DONE_MISSING_DIR"
    with pytest.raises(CheckpointRejected, match=expected):
        run_m6_portfolio(
            FIXTURE, root, approved_sha256=ORIGINAL_FIXTURE_SHA256,
            verify_subprocess_resume=False,
            f09a_resume_after_slug="world-u-synthetic-university",
        )


def test_w2_actual_compiled_room_fires_source_dependent_activation_and_sediment():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    for host in fixture["hosts"]:
        world = run_m6_world(host, fixture=fixture, fixture_sha256=sha)
        witnessed = world.oracle_inputs_extra["m6_w2_actual_activations"]
        assert len(witnessed) == 1
        receipt = world.oracle_inputs_extra["m6_w2_receipts"][0]
        link = witnessed[0]
        assert receipt["w2_activation_id"] == link["activation_id"]
        assert receipt["w2_run_id"] == link["run_id"]
        assert receipt["sediment_version"] == link["sediment_version"]
        assert link["need_activation_id"] in {
            a.activation_id for a in world.engine.ledger.activations if a.error_code == "BODY_APORIA"
        }
        assert link["source_sha256"] == receipt["content_sha256"]
        source_room = next(m for m in world.manifests if m.room_id == link["room_id"])
        assert source_room.admitted_engine_threads == (f"m6-w2-evidence-{world.slug}-{receipt['stone_id']}",)
        activation = next(a for a in world.engine.ledger.activations if a.activation_id == link["activation_id"])
        assert activation.outcome.value == "FIRED"
        assert activation.run_id == link["run_id"]
        evidence = next(r for r in world.engine.sediment.all_records() if r.sediment_id == link["sediment_id"])
        assert evidence.version == link["sediment_version"]
        assert evidence.source_carrier_refs == (link["source_carrier_id"],)
        assert evidence.produced_by_thread == activation.thread_id
        assert evidence.payload["content_sha256"] == link["source_sha256"]
        assert len(world.oracle_inputs_extra["m6_external_ledger"]["evidence_returns"]) == 1
        assert not any(r["status"] == "SYNTHETIC_SELF_ASSERTED_RETURN" for r in world.oracle_inputs_extra["m6_w2_receipts"][1:])


def test_w2_absence_leaves_no_late_wave_and_changed_source_only_changes_w2_line():
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    source_host = fixture["hosts"][0]
    no_return = run_m6_world(source_host, fixture=fixture, fixture_sha256=sha, skip_w2=True)
    assert not no_return.oracle_inputs_extra.get("m6_w2_actual_activations")
    base = run_m6_world(source_host, fixture=fixture, fixture_sha256=sha)
    alternative = copy.deepcopy(source_host)
    next(st for st in alternative["stones"] if st.get("kind") == "W2_RETURN")["external_source"]["content"] += "; independent_labels=YES"
    shifted = run_m6_world(alternative, fixture=fixture, fixture_sha256=sha)
    old = base.oracle_inputs_extra["m6_w2_actual_activations"][0]
    new = shifted.oracle_inputs_extra["m6_w2_actual_activations"][0]
    assert old["source_sha256"] != new["source_sha256"]
    assert old["run_id"] == new["run_id"]  # same operation, different pinned source evidence
    from seshat.fabric_waves.m5_room_carpet import _branch_snapshot
    assert _branch_snapshot(base.engine, branch="alpha", slug=base.slug).records == _branch_snapshot(
        shifted.engine, branch="alpha", slug=shifted.slug
    ).records


def test_w2_rx09_rejects_forged_activation_and_source_digest():
    from seshat.fabric_waves.m6_oracles import evaluate_m6_oracles
    fixture, sha = load_fixture(FIXTURE, approved_sha256=ORIGINAL_FIXTURE_SHA256)
    world = run_m6_world(fixture["hosts"][0], fixture=fixture, fixture_sha256=sha)
    bundle = compose_report_bundle(world)
    def row():
        return next(
            r for r in evaluate_m6_oracles(world, bundle, operator_markdown="")
            if r["oracle_id"] == "RX09"
        )
    assert row()["observed"] == "PASS"
    trace = world.oracle_inputs_extra["m6_w2_actual_activations"][0]
    original = trace["activation_id"]
    trace["activation_id"] = "made-up-activation"
    assert row()["observed"] == "FAIL"
    trace["activation_id"] = original
    original_digest = trace["source_sha256"]
    trace["source_sha256"] = "0" * 64
    assert row()["observed"] == "FAIL"
    trace["source_sha256"] = original_digest
    assert row()["observed"] == "PASS"
