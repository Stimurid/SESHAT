from __future__ import annotations

import json
from pathlib import Path

import pytest

from seshat.product_preview import (
    ProductPreviewError,
    build_operation_route,
    build_reports,
    build_selections,
    ingest_sources,
    load_archive_census,
    load_method_outputs,
    run_preview,
    select_sources,
    validate_manifest,
)


def _manifest(tmp_path: Path) -> dict:
    (tmp_path / "a.txt").write_text("object alpha method network evidence", encoding="utf-8")
    (tmp_path / "d.txt").write_text("infrastructure room resource", encoding="utf-8")
    (tmp_path / "article.txt").write_text("external article calibration method", encoding="utf-8")
    (tmp_path / "i11.json").write_text(
        json.dumps({"events": ["observed"], "fixture": True}), encoding="utf-8"
    )
    return {
        "product_id": "test-preview",
        "default_selector": "all",
        "report_selectors": {"R01": "a", "R05": "article"},
        "sources": [
            {"source_id": "src-a", "study_id": "study-1", "source_kind": "A",
             "version": "1", "path": "a.txt", "objects": ["alpha"],
             "methods": ["network"], "infrastructure": ["system"]},
            {"source_id": "src-d", "study_id": "study-1", "source_kind": "D",
             "version": "1", "path": "d.txt", "objects": ["constraints"],
             "methods": ["inventory"], "infrastructure": ["room"]},
            {"source_id": "src-article", "study_id": "study-2",
             "source_kind": "ARTICLE", "version": "1", "path": "article.txt",
             "objects": ["calibration"], "methods": ["comparison"],
             "infrastructure": ["sensor"]},
        ],
        "selectors": [
            {"selector_id": "a", "mode": "A_ONLY"},
            {"selector_id": "d", "mode": "D_ONLY"},
            {"selector_id": "ad", "mode": "A_PLUS_D"},
            {"selector_id": "article", "mode": "ARTICLE_ONLY"},
            {"selector_id": "all", "mode": "ARBITRARY"},
        ],
        "method_outputs": [
            {"study_id": "study-1", "method_id": "I11", "version": "1",
             "path": "i11.json"}
        ],
    }


def _loaded(tmp_path: Path):
    manifest = _manifest(tmp_path)
    validate_manifest(manifest)
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    methods = load_method_outputs(manifest, tmp_path)
    return manifest, sources, selections, methods


def test_study_id_is_not_source_carrier_id(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["sources"][0]["study_id"] = "src-a"
    with pytest.raises(ProductPreviewError, match="STUDY_ID_MUST_DIFFER"):
        validate_manifest(manifest)


def test_duplicate_study_carrier_is_rejected(tmp_path):
    manifest = _manifest(tmp_path)
    duplicate = dict(manifest["sources"][0], source_id="src-other")
    manifest["sources"].append(duplicate)
    with pytest.raises(ProductPreviewError, match="DUPLICATE_STUDY_CARRIER"):
        validate_manifest(manifest)


def test_five_selector_modes_have_distinct_membership(tmp_path):
    _, _, selections, _ = _loaded(tmp_path)
    assert selections["a"]["members"] == ["src-a"]
    assert selections["d"]["members"] == ["src-d"]
    assert selections["ad"]["members"] == ["src-a", "src-d"]
    assert selections["article"]["members"] == ["src-article"]
    assert len({tuple(x["members"]) for x in selections.values()}) >= 4


def test_absent_d_is_empty_not_invented(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["sources"] = [x for x in manifest["sources"] if x["source_kind"] != "D"]
    sources = ingest_sources(manifest, tmp_path)
    assert select_sources({"mode": "D_ONLY"}, sources) == []


def test_malformed_source_becomes_partial(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["sources"][0]["path"] = "missing.pdf"
    records = ingest_sources(manifest, tmp_path)
    assert records[0]["status"] == "PARTIAL"
    assert records[0]["text_extraction"] == "FAILED"
    assert records[0]["byte_sha256"] is None


def test_nine_reports_have_different_purposes_and_field_map(tmp_path):
    manifest, sources, selections, methods = _loaded(tmp_path)
    reports = build_reports(manifest, sources, selections, methods)
    assert set(reports) == {f"R{i:02d}" for i in range(1, 10)}
    assert len({report["purpose"] for report in reports.values()}) == 9
    assert reports["R03"]["field_map"]["scope"] == "SELECTED_CORPUS_FIELD_NOT_GLOBAL_FIELD"
    assert "comparison_claims" not in reports["R03"]


def test_missing_external_data_is_honest(tmp_path):
    manifest, sources, selections, methods = _loaded(tmp_path)
    reports = build_reports(manifest, sources, selections, methods)
    assert len(reports["R05"]["dossiers"]) == 7
    assert "EXTERNAL_SRC_D_INCOMPLETE" in reports["R05"]["limitations"]
    assert reports["R06"]["comparisons"] == []
    assert reports["R09"]["authorized_decision"] is None


def test_operation_route_uses_immutable_i11_and_marks_missing_methods(tmp_path):
    _, sources, _, methods = _loaded(tmp_path)
    route = build_operation_route(sources, methods, {"status": "PARTIAL"})
    i11 = next(x for x in route["typed_operations"]
               if x["study_id"] == "study-1" and x["method_id"] == "I11")
    i12 = next(x for x in route["typed_operations"]
               if x["study_id"] == "study-1" and x["method_id"] == "I12")
    assert i11["status"] == "WORKS_IMMUTABLE_SUPPLIED_OUTPUT"
    assert i11["method_output_sha256"]
    assert i12["status"] == "PARTIAL_METHOD_OUTPUT_MISSING"


def test_batch_resume_has_no_duplicate_call(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        "seshat.product_preview.run_carpet",
        lambda *args: {"status": "WORKS_ENGINE_EXECUTED",
                      "at_least_two_cross_thread_activations": True,
                      "activation_witnesses": [{"thread_id": "a"}, {"thread_id": "b"}],
                      "selective_source_delta_replay": [{"oracle_id": "RM04", "observed": "PASS"}]},
    )
    monkeypatch.setattr(
        "seshat.product_preview.run_f09a_host_batches",
        lambda *args: {"sechenovka-like": {}, "meteorology": {}},
    )
    output = tmp_path / "out"
    run_preview(manifest_path, output)
    run_preview(manifest_path, output, resume=True)
    ledger = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert ledger["executed_items"] == []
    assert len(ledger["replayed_items"]) == 9
    assert ledger["duplicate_model_calls"] == 0
    assert all(item["model_calls"] == 0 for item in ledger["items"].values())


def test_source_revision_selectively_invalidates_members(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        "seshat.product_preview.run_carpet",
        lambda *args: {"status": "WORKS_ENGINE_EXECUTED",
                      "at_least_two_cross_thread_activations": True,
                      "activation_witnesses": [], "selective_source_delta_replay": []},
    )
    monkeypatch.setattr(
        "seshat.product_preview.run_f09a_host_batches",
        lambda *args: {"sechenovka-like": {}, "meteorology": {}},
    )
    output = tmp_path / "out"
    run_preview(manifest_path, output)
    (tmp_path / "d.txt").write_text("revised infrastructure room resource", encoding="utf-8")
    run_preview(manifest_path, output, resume=True)
    ledger = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert ledger["revised_source_ids"] == ["src-d"]
    assert "R01" in ledger["replayed_items"]  # A-only report is unaffected.
    assert "R02" in ledger["executed_items"]  # A+D evidence changed.
    assert 0 < len(ledger["executed_items"]) < 9


def test_owner_excluded_source_is_not_read(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["sources"][0].update(path="private-does-not-exist.txt", excluded=True)
    records = ingest_sources(manifest, tmp_path)
    assert records[0]["status"] == "EXCLUDED_BY_OWNER_POLICY"
    assert records[0]["text_extraction"] == "NOT_READ"


def test_archive_count_requires_real_manifest(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["archive_census_count"] = 186
    with pytest.raises(ProductPreviewError, match="DECLARED_ARCHIVE_COUNT_FORBIDDEN"):
        validate_manifest(manifest)
    manifest.pop("archive_census_count")
    (tmp_path / "archive.json").write_text(
        json.dumps({"records": [{"id": "one"}, {"id": "two"}]}), encoding="utf-8"
    )
    manifest["archive_manifest"] = "archive.json"
    census = load_archive_census(manifest, tmp_path)
    assert census["record_count"] == 2
    assert census["records_read_or_analysed"] is False


def test_historical_i11_events_render_readable_and_page_addressed(tmp_path):
    from seshat.product_preview import _markdown
    manifest = _manifest(tmp_path)
    (tmp_path / "i11.json").write_text(json.dumps({
        "work_id": "study-1",
        "action_events": [{
            "id": "E01",
            "layer": "RP",
            "relation_mode": "SOURCE_ASSERTED_OPERATION",
            "verb": "conducted interviews and created transcripts",
            "actor_ids": ["RESEARCHER_UNNAMED"],
            "source_addresses": [{"page": 4, "section": "Methods",
                                  "quote": "interviews were conducted"}],
        }],
    }), encoding="utf-8")
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    methods = load_method_outputs(manifest, tmp_path)
    reports = build_reports(manifest, sources, selections, methods)
    r01 = reports["R01"]
    r02 = reports["R02"]
    assembly = next(x for x in r01["study_assemblies"] if x["study_id"] == "study-1")
    assert len(assembly["historical_actions"]) == 1
    assert assembly["historical_layer_counts"] == {"RP": 1}
    assert "E01 / RP / SOURCE_ASSERTED_OPERATION" in _markdown(r01)
    assert "conducted interviews and created transcripts" in _markdown(r01)
    assert "p.4" in _markdown(r02)
    assert "linked JSON retains" in _markdown(r01)
    assert "Scientific acceptance" in _markdown(r01)


def test_canonical_i11_method_id_maps_to_existing_historical_variant(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["method_outputs"][0]["method_id"] = "I11_ACTIVITY_NETWORK"
    sources = ingest_sources(manifest, tmp_path)
    methods = load_method_outputs(manifest, tmp_path)
    route = build_operation_route(sources, methods, {"status": "PARTIAL"})
    i11 = next(x for x in route["typed_operations"]
               if x["study_id"] == "study-1" and x["method_id"] == "I11")
    assert i11["status"] == "WORKS_IMMUTABLE_SUPPLIED_OUTPUT"
    assert i11["method_output_sha256"]


def test_small_selected_field_reports_scope_and_six_education_zones(tmp_path):
    from seshat.product_preview import _markdown
    manifest, sources, selections, methods = _loaded(tmp_path)
    reports = build_reports(manifest, sources, selections, methods)
    assert "TWO_STUDY_FIELD_ONLY_NOT_INSTITUTIONAL_COVERAGE" in reports["R03"]["limitations"]
    assert "not stand for a university" in _markdown(reports["R03"])
    assert len(reports["R08"]["learning_projection"]["six_zones"]) == 6
    assert "Hypothesis Lab" in _markdown(reports["R08"])
    assert "Arena" in _markdown(reports["R08"])


def test_article_opportunities_are_not_about_missing_dissertation(tmp_path):
    manifest, sources, selections, methods = _loaded(tmp_path)
    manifest["report_selectors"]["R07"] = "article"
    reports = build_reports(manifest, sources, selections, methods)
    types = {x["type"] for x in reports["R07"]["opportunities"]}
    assert types == {"unresolved_research_gap", "method_transfer", "outside_evidence_test"}
