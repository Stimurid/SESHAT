"""F08 adversarial delivery tests. Run only in the coordinator's isolated container."""
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from itertools import permutations

import pytest

from seshat.blackboard import Blackboard
from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject
from seshat.corpus import CorpusSelectionSpec, ManifestPin, Predicate, _digest
from seshat.corpus_host import HostConfiguration, HostRuntime
from seshat.report_demo import (
    demo_request, pin_package, synthetic_packages, write_artifacts,
)
from seshat.reports import (
    MethodAsset, ReportProjection, ReportReceipt, artifacts, report_session,
)


def setup_host(tmp_path, host="sechenovka-like"):
    packages = synthetic_packages(host)
    runtime = HostRuntime(configuration(tmp_path, packages))
    return runtime, packages


def configuration(tmp_path, packages):
    source, rights, temporal = packages
    return HostConfiguration(host_id=source["host_id"],
        primary=pin_package(tmp_path / "source.json", source),
        rights=pin_package(tmp_path / "rights.json", rights),
        temporal=pin_package(tmp_path / "temporal.json", temporal))


def session(runtime, **kwargs):
    return report_session(runtime, authenticated_caller="demo",
                          authorized_view="synthetic-public", **kwargs)


def values(report, title):
    return {c.label: c.value for s in report.sections if s.title == title for c in s.claims}


@pytest.mark.parametrize("host", ["sechenovka-like", "meteorology"])
def test_r03_meaningful_counts_overlap_and_temporal_map(tmp_path, host):
    runtime, _ = setup_host(tmp_path, host)
    report = session(runtime)(demo_request())
    assert report.status == "SUBSTANTIVE_METADATA"
    summary = values(report, "Local field / authorized denominators")
    assert summary == {"unique research objects (selected union)": 3,
                       "unique source carriers (selected union)": 4,
                       "overlap role-A / role-D": 1}
    for role in ("A", "D"):
        counts = values(report, f"Subset role-{role}@1")
        assert counts["eligible_studies"] == 3
        assert counts["eligible_carriers"] == 4
        assert counts["selected_studies"] == 2
        assert counts["selected_carriers"] == 3
    first = values(report, "Evidence matrix / synthetic-1")
    second = values(report, "Evidence matrix / synthetic-2")
    third = values(report, "Evidence matrix / synthetic-3")
    assert first["cohort_year"] == 2025 and first["defended_on_year"] == 2026
    assert second["cohort_year"] == 2026 and second["defended_on_year"] == "UNKNOWN"
    assert third["specialty"] == third["lab"] == "UNKNOWN"
    assert [first["source roles"], second["source roles"], third["source roles"]] == ["A", "D", "A+D"]
    assert values(report, "Distribution / defended_on_year / selected union") == {"2026": 1, "UNKNOWN": 2}
    assert all("NOT_EVALUABLE" in row["degree award"] for row in (first, second, third))
    ref_ids = {r.ref for r in report.evidence}
    assert all(c.evidence and set(c.evidence) <= ref_ids for s in report.sections for c in s.claims)


@pytest.mark.parametrize("field,op,expected", [
    ("cohort_year", "range", (2, 0, 0)),
    ("defended_on_year", "range", (1, 2, 0)),
    ("specialty", "equals", (1, 1, 0)),
    ("undeclared_lab_axis", "equals", (0, 0, 3)),
])
def test_range_unknown_not_evaluable(tmp_path, field, op, expected):
    runtime, _ = setup_host(tmp_path)
    request = demo_request()
    predicate = (Predicate(op="range", field=field, lower=2026, upper=2026) if op == "range"
                 else Predicate(op="equals", field=field, values=("imaging",)))
    selection = request.selections[0].model_copy(update={"predicate": predicate})
    report = session(runtime)(request.model_copy(update={"selections": (selection,)}))
    counts = values(report, "Subset role-A@1")
    assert tuple(counts[k] for k in ("selected_studies", "unknown_metadata", "not_evaluable")) == expected


def test_hidden_mutation_denied_carrier_and_private_epochs_byte_identical(tmp_path):
    runtime, packages = setup_host(tmp_path)
    compose = session(runtime)
    baseline = artifacts(compose(demo_request()))
    original, rights, temporal = packages
    for garbage in (None, [], {}, "PRIVATE-GARBAGE", 42):
        hidden = {"research_object": {"object_id": "DENIED-ID"}, "fields": garbage,
                  "carriers": garbage, "private_url": "https://secret.invalid/PRIVATE-PDF"}
        # Collision with admitted ID plus a known denied carrier must be filtered
        # before malformed fields, in either carrier order.
        for carriers in permutations([garbage, {"carrier_id": "DENIED-CARRIER"}]):
            denied_carrier = deepcopy(original["records"][0])
            denied_carrier.update(carriers=list(carriers), fields=garbage)
            source = deepcopy(original)
            source.update(version="PRIVATE-SOURCE-EPOCH", records=[hidden, denied_carrier,
                                                                    *original["records"]])
            changed_rights = deepcopy(rights)
            changed_rights["epoch"] = "PRIVATE-RIGHTS-EPOCH"
            runtime.install(configuration(tmp_path, (source, changed_rights, temporal)))
            actual = artifacts(compose(demo_request()))
            assert actual == baseline
            assert b"PRIVATE" not in b"".join(actual.values())
            assert b"DENIED" not in b"".join(actual.values())
            assert str(tmp_path).encode() not in b"".join(actual.values())


def test_permutations_duplicates_and_request_private_pin_are_stable(tmp_path):
    runtime, packages = setup_host(tmp_path)
    request = demo_request()
    baseline = artifacts(session(runtime)(request))
    source, rights, temporal = packages
    for ordered in permutations(source["records"]):
        revised = deepcopy(source)
        revised["records"] = [*ordered, deepcopy(ordered[0])]
        for row in revised["records"]:
            row["fields"].reverse()
            row["roles"].reverse()
            row["carriers"].reverse()
        runtime.install(configuration(tmp_path, (revised, rights, temporal)))
        selectors = tuple(s.model_copy(update={"manifest": s.manifest.model_copy(update={
            "sha256": "f" * 64, "version": "PRIVATE"})}) for s in reversed(request.selections))
        assert artifacts(session(runtime)(request.model_copy(update={"selections": selectors}))) == baseline


@pytest.mark.parametrize("change", ["title", "carrier", "record-version", "predicate", "selector-version"])
def test_visible_change_invalidates_digest(tmp_path, change):
    runtime, packages = setup_host(tmp_path)
    request = demo_request()
    before = session(runtime)(request)
    source, rights, temporal = deepcopy(packages)
    # Change third row, which has no temporal binding in this fixture.
    row = source["records"][2]
    if change == "title":
        row["fields"][0]["value"] = "Visible changed title"
    elif change == "carrier":
        row["carriers"][0]["content_sha256"] = "f" * 64
    elif change == "record-version":
        row["research_object"]["version"] = "2"
    else:
        updates = ({"version": "2"} if change == "selector-version" else
                   {"predicate": Predicate(op="ids", ids=("synthetic-1",))})
        request = request.model_copy(update={"selections": (
            request.selections[0].model_copy(update=updates), request.selections[1])})
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    after = session(runtime)(request)
    assert before.digest != after.digest
    if change in {"carrier", "record-version"}:
        members = {m.object_id: m for s in before.selections for m in s.members}
        with pytest.raises(ValueError, match="REPORT_SOURCE_CHANGED"):
            session(runtime)(request.model_copy(update={"expected_members": tuple(members.values())}))


def test_source_tampering_and_wrong_session_fail_closed(tmp_path):
    runtime, _ = setup_host(tmp_path)
    request = demo_request()
    wrong = request.selections[0].model_copy(update={"caller_id": "attacker"})
    with pytest.raises(ValueError, match="SESSION_SCOPE_MISMATCH"):
        session(runtime)(request.model_copy(update={"selections": (wrong,)}))
    (tmp_path / "source.json").write_bytes(b"PRIVATE malformed source")
    with pytest.raises(ValueError, match="^HOST_INPUT_UNAVAILABLE$"):
        session(runtime)(request)


def test_rights_rotation_removal_and_snapshot_pin(tmp_path):
    runtime, packages = setup_host(tmp_path)
    request = demo_request()
    original = session(runtime)(request)
    pinned = request.model_copy(update={
        "expected_snapshot_digests": tuple(s.snapshot_digest for s in original.selections)})
    assert session(runtime)(pinned).digest == original.digest
    source, rights, temporal = packages
    rights["grants"][0]["object_ids"].remove("synthetic-3")
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    with pytest.raises(ValueError, match="REPORT_SNAPSHOT_CHANGED"):
        session(runtime)(pinned)
    restricted = artifacts(session(runtime)(request))
    assert b"synthetic-3" not in b"".join(restricted.values())
    (tmp_path / "rights.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="^HOST_INPUT_UNAVAILABLE$"):
        session(runtime)(request)


def test_r01_rejects_corpus_assembly_and_r04_has_matrix(tmp_path):
    runtime, _ = setup_host(tmp_path)
    with pytest.raises(ValueError, match="R01_REQUIRES_ONE_RESEARCH_OBJECT"):
        session(runtime)(demo_request().model_copy(update={"report_id": "R01"}))
    report = session(runtime)(demo_request("R04"))
    html = artifacts(report)["report.html"].decode()
    assert "Object × Method × Infrastructure atlas" in html
    assert "synthetic sensor" in html and "UNKNOWN" in html


@pytest.mark.parametrize("report_id,code", [
    ("R01", "BLOCKED_METHOD"), ("R02", "BLOCKED_METHOD"), ("R04", "BLOCKED_METHOD"),
    ("R05", "BLOCKED_EXTERNAL_EVIDENCE"), ("R06", "BLOCKED_EXTERNAL_EVIDENCE"),
    ("R07", "BLOCKED_EXTERNAL_EVIDENCE"), ("R08", "BLOCKED_ADAPTER"),
    ("R09", "BLOCKED_DECISION_RIGHTS"),
])
def test_partial_and_blocked_modes_are_not_substantive_completion(tmp_path, report_id, code):
    runtime, _ = setup_host(tmp_path)
    report = session(runtime)(demo_request(report_id))
    assert report.blocks[0].code == code and report.blocks[0].unmet_input
    assert not json.loads(artifacts(report)["receipt.json"])["substantive_completed"]
    assert "ACCEPTED_CURRENT" not in artifacts(report)["report.json"].decode()
    if report_id in {"R01", "R02", "R04"}:
        assert values(report, "Evidence matrix / synthetic-1")["title"].startswith("Invented")


def test_method_history_stale_absent_body_and_denied_asset(tmp_path):
    runtime, _ = setup_host(tmp_path)
    request = demo_request("R02")
    base = session(runtime)(request)
    member = base.selections[0].members[0]
    board = Blackboard()
    board.put(DerivedObject(derived_id="m1", object_type="Method", version="1",
        operation_id="synthetic", research_object_id=member.object_id,
        payload={"private": "MUST NOT PROJECT"}, acceptance_state=AcceptanceState.ACCEPTED))
    asset = MethodAsset(object_id=member.object_id, derived_id="m1", version="1",
        caller_id="demo", rights_scope="synthetic-public", source_member=member)
    compose = session(runtime, blackboard=board, method_assets=(asset,))
    assert "MethodBody unavailable" in values(compose(request),
                                              f"Evidence matrix / {member.object_id}")["Method state"]
    bound = asset.model_copy(update={"body_sha256": "a" * 64})
    accepted = session(runtime, blackboard=board, method_assets=(bound,))(request)
    assert "accepted-current result binding only" in values(accepted,
                                           f"Evidence matrix / {member.object_id}")["Method state"]
    assert accepted.method_states[0].state == "BLOCKED_METHOD"
    board.add_dependency(DependencyEdge(
        upstream_id="source", downstream_id="m1", dependency_type="source"))
    board.mark_changed("source")
    assert board.accepted_state(member.object_id, "Method")  # historical acceptance remains
    stale = session(runtime, blackboard=board, method_assets=(bound,))(request)
    assert "ACCEPTED_CURRENT" not in artifacts(stale)["report.json"].decode()
    assert "stale, historical" in values(stale, f"Evidence matrix / {member.object_id}")["Method state"]
    denied = bound.model_copy(update={"caller_id": "someone-else"})
    assert artifacts(session(runtime, blackboard=board, method_assets=(denied,))(request)) == artifacts(base)
    assert b"MUST NOT PROJECT" not in artifacts(stale)["report.json"]


def test_html_escapes_source_text_and_omits_carrier_metadata(tmp_path):
    runtime, packages = setup_host(tmp_path)
    source, rights, temporal = packages
    attack = '<script>alert("x")</script><img src="https://evil.invalid">'
    source["records"][0]["fields"][0]["value"] = attack
    source["records"][0]["carriers"][0].update(uri="file:///PRIVATE-ROOT/PRIVATE-PDF",
                                                              metadata={"secret": "PRIVATE-METADATA"})
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    files = artifacts(session(runtime)(demo_request()))
    html = files["report.html"].decode()
    assert "<script>" not in html and "<img src=" not in html
    assert "&lt;script&gt;" in html and "&quot;" in html
    assert b"PRIVATE-ROOT" not in b"".join(files.values())
    assert b"PRIVATE-METADATA" not in b"".join(files.values())


@pytest.mark.parametrize("host", ["sechenovka-like", "meteorology"])
def test_real_cli_delivery_and_receipt_recomputation(tmp_path, host):
    output = tmp_path / "delivery"
    result = subprocess.run([sys.executable, "-m", "seshat.report_demo", "--fixture", host,
                             "--output", str(output)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert {p.name for p in output.iterdir()} == {"report.json", "report.html", "receipt.json"}
    raw = (output / "report.json").read_bytes()
    html = (output / "report.html").read_bytes()
    report = ReportProjection.model_validate_json(raw)
    receipt = ReportReceipt.model_validate_json((output / "receipt.json").read_bytes())
    assert report.digest == _digest(report.model_dump(mode="json", exclude={"digest"}))
    assert receipt.projection_digest == report.digest
    assert receipt.report_json_sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.report_html_sha256 == hashlib.sha256(html).hexdigest()
    assert html.startswith(b"<!doctype html>") and b"Evidence matrix" in html
    assert receipt.substantive_completed
    second = tmp_path / "again"
    subprocess.run([sys.executable, "-m", "seshat.report_demo", "--fixture", host,
                    "--output", str(second)], check=True, timeout=30)
    assert all((second / p.name).read_bytes() == p.read_bytes() for p in output.iterdir())


def test_output_refuses_existing_directory_and_symlink(tmp_path):
    files = {"report.json": b"{}", "receipt.json": b"{}", "report.html": b"safe"}
    with pytest.raises(FileExistsError):
        write_artifacts(tmp_path, files)
    if os.name != "nt":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError, match="UNSAFE_OUTPUT_DIRECTORY"):
            write_artifacts(link / "output", files)


@pytest.mark.parametrize("host", ["sechenovka-like", "meteorology"])
def test_r03_disjoint_composition_groups_with_precise_counts_and_members(tmp_path, host):
    runtime, _ = setup_host(tmp_path, host)
    report = session(runtime)(demo_request())
    groups = {g.group_id: g for g in report.source_composition_groups}
    assert set(groups) == {"A-only", "D-only", "A+D", "UNKNOWN"}
    assert groups["A-only"].scope == "selected_union"
    assert groups["A-only"].selected_studies == 1
    assert groups["A-only"].selected_carriers == 1
    assert groups["A-only"].object_ids == ("synthetic-1",)
    assert groups["D-only"].selected_studies == 1
    assert groups["D-only"].selected_carriers == 1
    assert groups["D-only"].object_ids == ("synthetic-2",)
    assert groups["A+D"].selected_studies == 1
    assert groups["A+D"].selected_carriers == 2
    assert groups["A+D"].object_ids == ("synthetic-3",)
    assert groups["UNKNOWN"].selected_studies == 0
    assert groups["UNKNOWN"].selected_carriers == 0
    assert groups["UNKNOWN"].object_ids == ()
    all_object_ids = sum((g.object_ids for g in report.source_composition_groups), ())
    assert sorted(all_object_ids) == ["synthetic-1", "synthetic-2", "synthetic-3"]
    all_carrier_counts = sum(g.selected_carriers for g in report.source_composition_groups)
    assert all_carrier_counts == 4
    ref_ids = {r.ref for r in report.evidence}
    role_ref_by_object = {}
    for section in report.sections:
        if not section.title.startswith("Evidence matrix /"):
            continue
        oid = section.title.split("/", 1)[1].strip()
        role_claim = next(c for c in section.claims if c.label == "source roles")
        role_ref_by_object[oid] = {e for e in role_claim.evidence if e.startswith("host-field:")}
    for g in report.source_composition_groups:
        pins = [r for r in g.evidence if r.kind == "SOURCE_PIN"]
        role_pins = [r for r in g.evidence if r.kind == "HOST_FIELD" and r.field == "source_role"]
        assert len(pins) == g.selected_studies
        assert len(role_pins) == sum(len(role_ref_by_object[oid]) for oid in g.object_ids)
        for ref in g.evidence:
            assert ref.ref in ref_ids
            assert ref.kind in {"SOURCE_PIN", "HOST_FIELD"}
            if ref.kind == "HOST_FIELD":
                assert ref.field == "source_role"
    assert len(role_ref_by_object["synthetic-1"]) == 1
    assert len(role_ref_by_object["synthetic-2"]) == 1
    assert len(role_ref_by_object["synthetic-3"]) == 2
    section = next(s for s in report.sections
                   if s.title == "Source composition groups / selected union")
    label_values = {c.label: c.value for c in section.claims}
    assert label_values["A-only studies"] == 1
    assert label_values["D-only studies"] == 1
    assert label_values["A+D studies"] == 1
    assert label_values["UNKNOWN studies"] == 0
    assert label_values["A-only carriers"] == 1
    assert label_values["D-only carriers"] == 1
    assert label_values["A+D carriers"] == 2
    assert label_values["UNKNOWN carriers"] == 0


@pytest.mark.parametrize("host", ["sechenovka-like", "meteorology"])
def test_r03_groups_visible_in_html_with_disjoint_denominator(tmp_path, host):
    runtime, _ = setup_host(tmp_path, host)
    html = artifacts(session(runtime)(demo_request()))["report.html"].decode()
    assert "Source composition groups" in html
    for label in ("A-only", "D-only", "A+D"):
        assert f"<strong>{label}</strong>" in html
    # Group denominator is explicitly selected union, never private corpus.
    assert "selected union" in html.lower()
    assert "PRIVATE-PDF" not in html
    assert "denied-cardinality" not in html.lower()


def test_r03_unknown_category_for_unexpected_or_missing_role(tmp_path):
    runtime, packages = setup_host(tmp_path)
    source, rights, temporal = deepcopy(packages)
    # Replace the A-only record's roles with an unrecognized value to force UNKNOWN.
    source["records"][0]["roles"] = [{"name": "source_role", "value": "X",
                                       "evidence_ref": "invented role X"}]
    # Drop roles entirely on the A+D record so missing-role lands in UNKNOWN too.
    source["records"][2]["roles"] = []
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    cohort_union = CorpusSelectionSpec(
        selector_id="cohort-span", version="1",
        manifest=ManifestPin(manifest_id="public-request", version="1", sha256="0" * 64),
        predicate=Predicate(op="range", field="cohort_year", lower=2025, upper=2026),
        caller_id="demo", view_id="synthetic-public")
    report = session(runtime)(demo_request().model_copy(update={"selections": (cohort_union,)}))
    groups = {g.group_id: g for g in report.source_composition_groups}
    assert groups["UNKNOWN"].selected_studies == 2
    assert groups["UNKNOWN"].selected_carriers == 3
    assert sorted(groups["UNKNOWN"].object_ids) == ["synthetic-1", "synthetic-3"]
    assert groups["A-only"].selected_studies == 0
    assert groups["D-only"].selected_studies == 1
    assert groups["D-only"].object_ids == ("synthetic-2",)


def test_r03_denied_only_hidden_mutation_byte_identical_across_artifacts(tmp_path):
    runtime, packages = setup_host(tmp_path)
    baseline = artifacts(session(runtime)(demo_request()))
    original, rights, temporal = packages
    for garbage in (None, [], {}, "PRIVATE-GARBAGE", 42):
        hidden = {"research_object": {"object_id": "DENIED-ID"}, "fields": garbage,
                  "carriers": garbage, "private_url": "https://secret.invalid/PRIVATE-PDF"}
        for carriers in permutations([garbage, {"carrier_id": "DENIED-CARRIER"}]):
            denied_carrier = deepcopy(original["records"][0])
            denied_carrier.update(carriers=list(carriers), fields=garbage)
            source = deepcopy(original)
            source.update(version="PRIVATE-SOURCE-EPOCH",
                          records=[hidden, denied_carrier, *original["records"]])
            changed_rights = deepcopy(rights)
            changed_rights["epoch"] = "PRIVATE-RIGHTS-EPOCH"
            runtime.install(configuration(tmp_path, (source, changed_rights, temporal)))
            actual = artifacts(session(runtime)(demo_request()))
            assert actual == baseline
            joined = b"".join(actual.values())
            assert b"PRIVATE" not in joined
            assert b"DENIED" not in joined
            assert b"PRIVATE-PDF" not in joined


def test_r02_typed_graph_with_object_method_evidence_nodes(tmp_path):
    runtime, _ = setup_host(tmp_path)
    report = session(runtime)(demo_request("R02"))
    assert report.method_evidence_graph is not None
    graph = report.method_evidence_graph
    object_nodes = [n for n in graph.nodes if n.kind == "OBJECT"]
    candidate_nodes = [n for n in graph.nodes if n.kind == "METHOD_CANDIDATE"]
    evidence_nodes = [n for n in graph.nodes if n.kind == "EVIDENCE"]
    assert {n.object_id for n in object_nodes} == {"synthetic-1", "synthetic-2", "synthetic-3"}
    assert len(object_nodes) >= 3
    assert len(candidate_nodes) >= 1
    measurement = next(n for n in candidate_nodes
                       if "measurement" in (n.candidate_label or ""))
    assert measurement.candidate_field == "method_candidate"
    assert measurement.evidence_ref
    assert measurement.evidence_ref in {r.ref for r in report.evidence}
    assert evidence_nodes, "EVIDENCE nodes must reference admitted evidence"
    node_ids = {n.node_id for n in graph.nodes}
    for edge in graph.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids
    edge_kinds = {edge.kind for edge in graph.edges}
    assert "DECLARES_CANDIDATE" in edge_kinds
    assert "EVIDENCED_BY" in edge_kinds
    state_nodes = [n for n in graph.nodes if n.kind == "METHOD_STATE"]
    assert len(state_nodes) == 3
    assert all(n.result_currentness == "UNAVAILABLE" for n in state_nodes)
    assert report.status == "PARTIAL_METADATA"
    assert report.blocks[0].code == "BLOCKED_METHOD"
    assert not json.loads(artifacts(report)["receipt.json"])["substantive_completed"]


def test_r02_graph_omits_unauthorized_assets_and_stale_board(tmp_path):
    runtime, _ = setup_host(tmp_path)
    request = demo_request("R02")
    base = session(runtime)(request)
    member = base.selections[0].members[0]
    board = Blackboard()
    board.put(DerivedObject(derived_id="m1", object_type="Method", version="1",
        operation_id="synthetic", research_object_id=member.object_id,
        payload={"private": "MUST NOT PROJECT"}, acceptance_state=AcceptanceState.ACCEPTED))
    asset = MethodAsset(object_id=member.object_id, derived_id="m1", version="1",
        caller_id="demo", rights_scope="synthetic-public", source_member=member)
    unbound = session(runtime, blackboard=board, method_assets=(asset,))(request)
    assert unbound.method_evidence_graph is not None
    state_nodes = [n for n in unbound.method_evidence_graph.nodes if n.kind == "METHOD_STATE"]
    assert state_nodes and state_nodes[0].state == "BLOCKED_METHOD"
    assert state_nodes[0].result_currentness == "UNAVAILABLE"
    bound = asset.model_copy(update={"body_sha256": "a" * 64})
    accepted = session(runtime, blackboard=board, method_assets=(bound,))(request)
    state_nodes = [n for n in accepted.method_evidence_graph.nodes if n.kind == "METHOD_STATE"]
    assert state_nodes and state_nodes[0].result_currentness == "ACCEPTED_CURRENT"
    assert state_nodes[0].state == "BLOCKED_METHOD"
    assert all("MUST NOT PROJECT" not in (n.diagnostic or "")
               and (n.candidate_label or "") != "MUST NOT PROJECT"
               for n in accepted.method_evidence_graph.nodes)
    board.add_dependency(DependencyEdge(
        upstream_id="source", downstream_id="m1", dependency_type="source"))
    board.mark_changed("source")
    stale = session(runtime, blackboard=board, method_assets=(bound,))(request)
    state_nodes = [n for n in stale.method_evidence_graph.nodes if n.kind == "METHOD_STATE"]
    assert state_nodes and state_nodes[0].result_currentness == "STALE_OR_CANDIDATE"
    assert state_nodes[0].state == "BLOCKED_METHOD"
    assert b"MUST NOT PROJECT" not in artifacts(stale)["report.json"]
    denied = bound.model_copy(update={"caller_id": "someone-else"})
    denied_artifact = session(runtime, blackboard=board, method_assets=(denied,))(request)
    assert denied_artifact.method_evidence_graph is not None
    base_states = [n for n in base.method_evidence_graph.nodes if n.kind == "METHOD_STATE"]
    denied_states = [n for n in denied_artifact.method_evidence_graph.nodes if n.kind == "METHOD_STATE"]
    assert len(base_states) == len(denied_states) == 3
    assert all(n.result_currentness == "UNAVAILABLE" for n in base_states)
    assert all(n.result_currentness == "UNAVAILABLE" for n in denied_states)
    assert artifacts(denied_artifact) == artifacts(base)


def test_r02_html_renders_graph_table_and_escapes_user_text(tmp_path):
    runtime, packages = setup_host(tmp_path)
    source, rights, temporal = packages
    source["records"][0]["fields"][0]["value"] = (
        '<script>alert("x")</script><img src="https://evil.invalid">')
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    html = artifacts(session(runtime)(demo_request("R02")))["report.html"].decode()
    assert "Object\u2013Method\u2013Evidence graph" in html
    assert "<h3>Nodes</h3>" in html and "<h3>Edges</h3>" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "&quot;" in html
    assert "<img src=" not in html
    assert 'href="https://evil.invalid"' not in html
    assert 'src="https://evil.invalid"' not in html
    assert "default-src 'none'" in html


def test_r03_source_change_invalidates_groups_and_digest(tmp_path):
    runtime, packages = setup_host(tmp_path)
    before = session(runtime)(demo_request())
    source, rights, temporal = deepcopy(packages)
    # Change the A+D study's role value so its category switches to D-only.
    source["records"][2]["roles"] = [{"name": "source_role", "value": "D",
                                       "evidence_ref": "invented role D"}]
    runtime.install(configuration(tmp_path, (source, rights, temporal)))
    after = session(runtime)(demo_request())
    assert before.digest != after.digest
    a_plus_d = next(g for g in after.source_composition_groups if g.group_id == "A+D")
    d_only = next(g for g in after.source_composition_groups if g.group_id == "D-only")
    assert a_plus_d.selected_studies == 0
    assert d_only.object_ids == ("synthetic-2", "synthetic-3")


def test_r03_groups_and_r02_graph_cli_delivery_byte_stable(tmp_path):
    output = tmp_path / "r03-cli"
    subprocess.run([sys.executable, "-m", "seshat.report_demo", "--fixture", "sechenovka-like",
                    "--report", "R03", "--output", str(output)], check=True, timeout=30)
    raw = (output / "report.json").read_bytes()
    html = (output / "report.html").read_bytes()
    report = ReportProjection.model_validate_json(raw)
    receipt = ReportReceipt.model_validate_json((output / "receipt.json").read_bytes())
    assert report.source_composition_groups
    assert report.method_evidence_graph is None
    assert receipt.substantive_completed
    assert b"Source composition groups" in html
    assert b"A-only" in html and b"D-only" in html and b"A+D" in html

    output2 = tmp_path / "r02-cli"
    subprocess.run([sys.executable, "-m", "seshat.report_demo", "--fixture", "sechenovka-like",
                    "--report", "R02", "--output", str(output2)], check=True, timeout=30)
    raw = (output2 / "report.json").read_bytes()
    html = (output2 / "report.html").read_bytes()
    report = ReportProjection.model_validate_json(raw)
    assert report.source_composition_groups == ()
    assert report.method_evidence_graph is not None
    assert b"Object\xe2\x80\x93Method\xe2\x80\x93Evidence graph" in html

    second = tmp_path / "r03-again"
    subprocess.run([sys.executable, "-m", "seshat.report_demo", "--fixture", "sechenovka-like",
                    "--report", "R03", "--output", str(second)], check=True, timeout=30)
    assert all((second / p.name).read_bytes() == p.read_bytes() for p in output.iterdir())
