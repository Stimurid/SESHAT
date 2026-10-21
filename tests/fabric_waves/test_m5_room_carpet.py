"""M5 two-world synthetic carpet acceptance (issue #60 room + carpet).

The two-world run is executed once per module and inspected from many
angles; each assertion names a property, not a counter.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from seshat.fabric_waves.m4_transport_boundary import (
    DeliveredSpan,
    StoredInputView,
    assess_delivery,
    assess_output_sections,
    preview_bounds,
)
from seshat.fabric_waves.m5_oracles import NOT_TESTED, PASS
from seshat.fabric_waves.m5_room_carpet import (
    M5_ARTIFACTS,
    ORIGINAL_FIXTURE_SHA256,
    REQUIRED_REPORT_SECTIONS,
    FixtureNotApproved,
    load_fixture,
    run_two_worlds,
)
from seshat.fabric_waves.m5_synthetic_hosts import host_slug

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m5_room_synthetic_acceptance_20261021_v01.json"
)


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    root = tmp_path_factory.mktemp("m5")
    return run_two_worlds(FIXTURE, root, verify_subprocess_resume=True), root


@pytest.fixture(scope="module")
def fixture_data():
    data, _ = load_fixture(FIXTURE)
    return data


def world_dirs(root, fixture_data):
    return [root / host_slug(h["host_id"]) for h in fixture_data["hosts"]]


# -- fixture admission --------------------------------------------------------


def test_original_fixture_is_accepted_by_its_pin():
    data, digest = load_fixture(FIXTURE)
    assert digest == ORIGINAL_FIXTURE_SHA256
    assert data["schema"].startswith("seshat.room_formation")
    assert len(data["thread_registry"]) >= 6


def test_a_different_fixture_needs_a_caller_approved_digest(tmp_path):
    invented = tmp_path / "other.json"
    body = json.dumps({"schema": "seshat.room_formation.x", "thread_registry": [], "hosts": []})
    invented.write_text(body, encoding="utf-8")
    with pytest.raises(FixtureNotApproved):
        load_fixture(invented)
    import hashlib

    digest = hashlib.sha256(invented.read_bytes()).hexdigest()
    data, got = load_fixture(invented, approved_sha256=digest)
    assert got == digest and data["hosts"] == []
    with pytest.raises(FixtureNotApproved):
        load_fixture(invented, approved_sha256="0" * 64)


# -- artifacts ----------------------------------------------------------------


def test_every_declared_artifact_is_written(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        for name in M5_ARTIFACTS:
            assert (world_dir / name).is_file(), f"{world_dir.name}/{name}"


def test_receipt_keeps_the_synthetic_boundary(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        receipt = json.loads((world_dir / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["synthetic_only"] is True
        assert receipt["scientific_acceptance"] == "NOT_PERFORMED"
        assert receipt["customer_release"] == "NOT_AUTHORIZED"
        assert receipt["fixture_sha256"] == ORIGINAL_FIXTURE_SHA256


# -- the room is applied to execution, not just recorded ----------------------


def test_only_admitted_capabilities_ever_fire(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        manifests = json.loads((world_dir / "room_manifest.json").read_text(encoding="utf-8"))
        for manifest in manifests:
            assert manifest["unplanned_activated_threads"] == [], manifest["room_id"]
            assert manifest["status"] != "ADMISSION_BREACH"


def test_rooms_are_derived_not_copied_from_must_wave(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        raw = (world_dir / "room_manifest.json").read_text(encoding="utf-8")
        assert "must_wave" not in raw
        manifests = json.loads(raw)
        aporia = [m for m in manifests if m["desired_output_states"] == ["ReconciledStateOrAPORIA"]]
        assert aporia, "the aporia stone must target a different output than a query"
        assert "N-P" not in aporia[0]["planned_registry_threads"]


# -- causal execution ---------------------------------------------------------


def test_six_functionally_distinct_capabilities_actually_fire(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        activations = [
            json.loads(line)
            for line in (world_dir / "activations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        fired = {a["thread_id"] for a in activations if a["outcome"] == "FIRED"}
        roles = {t.rsplit("-", 1)[0] if "-" in t else t for t in fired}
        assert len(fired) >= 6, sorted(fired)
        assert len(roles) >= 5, sorted(roles)


def test_an_aporia_is_recorded_and_retained(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        activations = [
            json.loads(line)
            for line in (world_dir / "activations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        aporias = [a for a in activations if a.get("error_code") == "BODY_APORIA"]
        assert aporias, f"{world_dir.name} recorded no aporia"
        assert any("SYNTHETIC_CONFLICT_UNRESOLVED" in (a.get("error_detail") or "") for a in aporias)


# -- oracles ------------------------------------------------------------------


def test_no_oracle_reports_pass_without_evidence(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        data = json.loads((world_dir / "oracles.json").read_text(encoding="utf-8"))
        for row in data["rows"]:
            assert row["observed"] in (PASS, "FAIL", NOT_TESTED)
            if row["observed"] == PASS:
                assert row["evidence"], f"{row['oracle_id']} passed with no evidence"


def test_both_worlds_have_strict_all_pass_and_nonempty_rm17_at_real_close(portfolio, fixture_data):
    """The synthetic acceptance run must exercise every RM and preserve real sediment."""
    _result, root = portfolio
    dirs = world_dirs(root, fixture_data)
    assert len(dirs) >= 2
    for world_dir in dirs:
        data = json.loads((world_dir / "oracles.json").read_text(encoding="utf-8"))
        summary = data["summary"]
        assert summary["all_passed"] is True, world_dir
        assert (summary["pass"], summary["fail"], summary["not_tested"]) == (20, 0, 0)
        rows = {item["oracle_id"]: item for item in data["rows"]}
        rm17 = rows["RM17"]
        assert rm17["observed"] == PASS
        assert rm17["evidence"]["retained"] > 0
        assert rm17["evidence"]["lost_sediment_ids"] == []
        assert rm17["evidence"]["mutated_sediment_ids"] == []


def test_oracle_summary_is_explicit_about_what_was_not_tested(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        data = json.loads((world_dir / "oracles.json").read_text(encoding="utf-8"))
        summary = data["summary"]
        assert summary["pass"] + summary["fail"] + summary["not_tested"] == 20
        assert set(summary["not_tested_ids"]).isdisjoint(summary["failed_ids"])


@pytest.mark.parametrize("oracle_id", ["RM01", "RM02", "RM03", "RM12"])
def test_core_causal_oracles_are_exercised_by_the_real_run(portfolio, fixture_data, oracle_id):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        rows = {
            r["oracle_id"]: r
            for r in json.loads((world_dir / "oracles.json").read_text(encoding="utf-8"))["rows"]
        }
        assert rows[oracle_id]["observed"] != NOT_TESTED, rows[oracle_id]


def test_rm03_join_names_two_distinct_parent_activations(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        rows = {
            r["oracle_id"]: r
            for r in json.loads((world_dir / "oracles.json").read_text(encoding="utf-8"))["rows"]
        }
        evidence = rows["RM03"]["evidence"]
        if rows["RM03"]["observed"] == PASS:
            assert len(set(evidence["consumed_parent_activation_ids"])) >= 2
            assert len(set(evidence["consumed_parent_thread_ids"])) >= 2


# -- the operator answer ------------------------------------------------------


def test_report_is_an_answer_not_a_counter_dump(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        text = (world_dir / "report.md").read_text(encoding="utf-8")
        assert "SYNTHETIC_ENGINEERING_ONLY" in text
        assert "## What was asked" in text
        assert "## What the evidence shows" in text
        assert "## What remains unresolved" in text
        assert "## Next discriminating action" in text
        assert "## Basis (rooms, runs and records)" in text
        # Counters live in telemetry, not in the operator answer.
        assert "Measured activations:" not in text


def test_report_covers_all_three_stones(portfolio, fixture_data):
    _result, root = portfolio
    for host in fixture_data["hosts"]:
        world_dir = root / host_slug(host["host_id"])
        text = (world_dir / "report.md").read_text(encoding="utf-8")
        for stone in host["stones"]:
            assert f"**{stone['stone_id']}**" in text, f"{world_dir.name} missing {stone['stone_id']}"


def test_report_references_resolve_to_real_records(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        receipt = json.loads((world_dir / "receipt.json").read_text(encoding="utf-8"))
        refs = receipt["operator_report"]["references"]
        assert refs, "an answer with no basis is not an answer"
        sediment_ids = {
            r["sediment_id"]
            for r in json.loads((world_dir / "sediment.json").read_text(encoding="utf-8"))
        }
        activation_ids = {
            json.loads(line)["activation_id"]
            for line in (world_dir / "activations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        for ref in refs:
            assert ref in sediment_ids | activation_ids, ref


def test_report_structural_gate_is_reported(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        receipt = json.loads((world_dir / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["operator_report"]["status"] in ("REPORT_COMPLETE", "REPORT_INCOMPLETE")
        assert set(REQUIRED_REPORT_SECTIONS)


def test_telemetry_is_kept_separate(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        telemetry = json.loads((world_dir / "telemetry.json").read_text(encoding="utf-8"))
        assert telemetry["activation_count"] >= 6
        assert telemetry["stone_outcomes"]
        assert telemetry["accepted_records"] == 0


# -- html ---------------------------------------------------------------------


def test_html_shows_every_stone_run(portfolio, fixture_data):
    _result, root = portfolio
    for host in fixture_data["hosts"]:
        world_dir = root / host_slug(host["host_id"])
        html = (world_dir / "carpet.html").read_text(encoding="utf-8")
        for stone in host["stones"]:
            assert f"Stone {stone['stone_id']}" in html
        assert "NOT_SCIENCE_ACCEPTED" in html


# -- sqlite ledger ------------------------------------------------------------


def test_sqlite_ledger_holds_rows_not_counters(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        with sqlite3.connect(str(world_dir / "ledger.sqlite")) as db:
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert {"m5_runs", "m5_activations", "m5_sediment", "m5_rooms", "m5_oracles"} <= tables
            assert db.execute("SELECT COUNT(*) FROM m5_activations").fetchone()[0] >= 6
            assert db.execute("SELECT COUNT(*) FROM m5_oracles").fetchone()[0] == 20
            assert db.execute("SELECT COUNT(*) FROM m5_rooms").fetchone()[0] >= 3


# -- M4 boundary groups, exercised concretely ---------------------------------


def test_consumed_sources_are_checked_on_the_real_invocation_path(portfolio, fixture_data):
    _result, root = portfolio
    for world_dir in world_dirs(root, fixture_data):
        receipt = json.loads((world_dir / "receipt.json").read_text(encoding="utf-8"))
        checks = receipt["consumed_source_checks"]
        assert checks, "the transport boundary must run on sources actually consumed"
        for check in checks:
            assert check["status"] == "REPORT_COMPLETE", check
            assert check["missing_ranges"] == []
            assert check["structural_only"] is True


@pytest.mark.parametrize(
    ("group_id", "check"),
    [
        ("G1_PARTIAL_DELIVERY", "partial"),
        ("G2_LONG_LINES", "long_lines"),
        ("G3_VERSION_DRIFT", "version"),
        ("G4_PERMISSION", "permission"),
        ("G5_SCOPE", "scope"),
        ("G6_LINE_BIND", "line_bind"),
    ],
)
def test_m4_group_behaviour(group_id, check):
    """Each documented M4 group asserts its own behaviour, not a stone count."""

    stored = StoredInputView("s://g", "v1", 100, "abc", complete=True)

    def span(offset, length, **kw):
        base = {"source_id": "s://g", "source_version": "v1", "content_sha256": "abc"}
        base.update(kw)
        return DeliveredSpan(offset=offset, length=length, **base)

    if check == "partial":
        status, code, report = assess_delivery(
            stored, [span(0, 30), span(60, 40)], admitted_byte_length=70, policy="FULL_REQUIRED"
        )
        assert status == "REPORT_INCOMPLETE"
        assert report.missing_ranges == ((30, 60),)
        assert code == "COVERAGE_GAPS[30-60]"
    elif check == "long_lines":
        meta = preview_bounds("a" * 5000 + "\n" + "b")
        assert meta["long_line_numbers"] == [1]
        assert meta["long_lines_preserved_not_truncated"] is True
    elif check == "version":
        status, code, _ = assess_delivery(
            stored,
            [span(0, 100, source_version="v2")],
            admitted_byte_length=100,
            policy="FULL_REQUIRED",
        )
        assert status == "DELIVERY_DENIED"
        assert "SPAN_SOURCE_VERSION_MISMATCH" in code
    elif check == "permission":
        from seshat.fabric_waves.m4_transport_boundary import permission_may_not_become_unknown

        assert permission_may_not_become_unknown(True, True) == "PERMISSION_ERASED_TO_UNKNOWN"
    elif check == "scope":
        from seshat.fabric_waves.m4_transport_boundary import scoped_success_not_inherited

        assert (
            scoped_success_not_inherited(True, "new purpose", True)
            == "NEW_PURPOSE_CANNOT_INHERIT_OLD_VALIDATION"
        )
    elif check == "line_bind":
        from seshat.fabric_waves.m4_transport_boundary import line_number_binding

        assert (
            line_number_binding("v1", 10, actual_version="v2")
            == "LINE_NUMBER_STALE_ARTIFACT_VERSION"
        )
    else:  # pragma: no cover - parametrisation guard
        raise AssertionError(group_id)


def test_output_gate_rejects_an_empty_required_section():
    sections = dict.fromkeys(REQUIRED_REPORT_SECTIONS, "content")
    assert assess_output_sections(sections, required=REQUIRED_REPORT_SECTIONS)[0] == "REPORT_COMPLETE"
    sections["unresolved"] = ""
    status, code = assess_output_sections(sections, required=REQUIRED_REPORT_SECTIONS)
    assert status == "REPORT_INCOMPLETE"
    assert "unresolved" in code


# -- portfolio ----------------------------------------------------------------


def test_portfolio_states_local_execution_boundary(portfolio):
    result, root = portfolio
    assert result["synthetic_only"] is True
    assert result["scientific_acceptance"] == "NOT_PERFORMED"
    assert (root / "m5_portfolio_receipt.json").is_file()
    assert len(result["worlds"]) == 2
