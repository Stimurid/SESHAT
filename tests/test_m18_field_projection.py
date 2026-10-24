"""M18 R03/R04 field-projection fixes.

Covers two defects found in the M17 product CLI against the real two-study
(DENT/SURG) pilot corpora:

DEFECT1: R03 years/objects/methods/infrastructure Counters iterated over every
selected *source carrier*, so a study published as one A carrier and one D
carrier was counted twice.  These tests use synthetic, source-neutral fixtures
(no private PDF/author/medical content) to prove the fix counts per distinct
ResearchObject (study), while still preserving the separately meaningful
per-carrier "source upload year" signal, and to prove a genuine A/D year
disagreement is surfaced as a discrepancy rather than silently resolved.

DEFECT2: R03/R04 claimed a scientific field view from PDF-extraction noise
(e.g. the "=== PAGE n ===" banner and bibliographic boilerplate) and never
distinguished "the manifest has readable text" from "an authorial scientific
overlay actually analysed this study".  These tests prove the explicit
SOURCE_CORPUS_READABLE / SCIENTIFIC_STUDY_ANALYSIS_MISSING statuses, and that
when two or more selected ResearchObjects carry a real (synthetic, in-test)
M17 AuthorialStudyOracle overlay, R03/R04 project genuinely distinct
per-study evidence with source citation and carrier-selection constraints,
never a fabricated cross-study comparability claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from seshat.authorial_oracle import load_authorial_study_oracle
from seshat.product_preview import (
    _words,
    build_reports,
    build_selections,
    ingest_sources,
    run_preview,
    validate_manifest,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _year_manifest(tmp_path: Path) -> dict:
    (tmp_path / "s1_a.txt").write_text(
        "Alpha abstract object-shared method-shared", encoding="utf-8"
    )
    (tmp_path / "s1_d.txt").write_text(
        "Alpha dissertation object-shared method-shared infra-shared", encoding="utf-8"
    )
    (tmp_path / "s2_a.txt").write_text(
        "Beta abstract object-other method-other", encoding="utf-8"
    )
    (tmp_path / "s2_d.txt").write_text(
        "Beta dissertation object-other method-other infra-other", encoding="utf-8"
    )
    return {
        "product_id": "m18-field-projection-years",
        "default_selector": "all",
        "sources": [
            {"source_id": "s1-a", "study_id": "study-1", "source_kind": "A",
             "version": "1", "path": "s1_a.txt", "year": 2021, "defense_year": 2022,
             "objects": ["object-shared"], "methods": ["method-shared"],
             "infrastructure": []},
            {"source_id": "s1-d", "study_id": "study-1", "source_kind": "D",
             "version": "1", "path": "s1_d.txt", "year": 2023, "defense_year": 2022,
             "objects": ["object-shared"], "methods": ["method-shared"],
             "infrastructure": ["infra-shared"]},
            {"source_id": "s2-a", "study_id": "study-2", "source_kind": "A",
             "version": "1", "path": "s2_a.txt", "year": 2024, "defense_year": 2024,
             "objects": ["object-other"], "methods": ["method-other"],
             "infrastructure": []},
            {"source_id": "s2-d", "study_id": "study-2", "source_kind": "D",
             "version": "1", "path": "s2_d.txt", "year": 2024, "defense_year": 2024,
             "objects": ["object-other"], "methods": ["method-other"],
             "infrastructure": ["infra-other"]},
        ],
        "selectors": [
            {"selector_id": "all", "mode": "A_PLUS_D"},
            {"selector_id": "a-only", "mode": "A_ONLY"},
            {"selector_id": "study1-only", "mode": "ARBITRARY",
             "filters": {"study_ids": ["study-1"]}},
        ],
    }


def test_year_and_tag_counts_are_deduped_per_study_not_per_carrier(tmp_path):
    manifest = _year_manifest(tmp_path)
    validate_manifest(manifest)
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    reports = build_reports(manifest, sources, selections, [])
    field_map = reports["R03"]["field_map"]

    # Two ResearchObjects (studies), one per year -> 1+1, not 2+2.
    assert field_map["years"] == {"2022": 1, "2024": 1}
    assert field_map["year_discrepancies"] == []
    # Per-carrier upload years remain a distinct, non-deduped signal.
    assert field_map["source_upload_years"] == {"2021": 1, "2023": 1, "2024": 2}
    # A tag shared by a study's A and D carrier counts once per study.
    assert field_map["objects"] == {"object-shared": 1, "object-other": 1}
    assert field_map["methods"] == {"method-shared": 1, "method-other": 1}
    assert field_map["infrastructure"] == {"infra-shared": 1, "infra-other": 1}
    assert field_map["study_count"] == 2
    assert field_map["source_count"] == 4


def test_year_conflict_between_carriers_is_reported_not_resolved(tmp_path):
    manifest = _year_manifest(tmp_path)
    manifest["sources"][1]["defense_year"] = 2099  # s1-d disagrees with s1-a's 2022
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    reports = build_reports(manifest, sources, selections, [])
    field_map = reports["R03"]["field_map"]

    discrepancy = next(
        d for d in field_map["year_discrepancies"] if d["study_id"] == "study-1"
    )
    assert discrepancy["field"] == "defense_year"
    assert sorted(discrepancy["conflicting_values"]) == ["2022", "2099"]
    assert field_map["years"]["CONFLICT"] == 1
    assert "YEAR_METADATA_DISCREPANCY_UNRESOLVED" in reports["R03"]["limitations"]


def test_pdf_page_banner_and_bibliographic_noise_excluded_from_recurring_terms():
    records = [{
        "text": (
            "=== PAGE 1 ===\nPMID 99887766 mentions repeatedly repeatedly "
            "repeatedly the shared concept."
        ),
    }]
    counts = _words(records)
    assert "page" not in counts
    assert "pmid" not in counts
    assert counts["repeatedly"] == 3


def test_r03_r04_metadata_only_corpus_is_honestly_flagged_missing(tmp_path):
    (tmp_path / "x.txt").write_text("plain text with no declared tags at all", encoding="utf-8")
    (tmp_path / "y.txt").write_text("another plain text here too", encoding="utf-8")
    manifest = {
        "product_id": "m18-missing-science",
        "default_selector": "all",
        "sources": [
            {"source_id": "x", "study_id": "study-x", "source_kind": "A",
             "version": "1", "path": "x.txt"},
            {"source_id": "y", "study_id": "study-y", "source_kind": "A",
             "version": "1", "path": "y.txt"},
        ],
        "selectors": [
            {"selector_id": "all", "mode": "A_ONLY"},
            {"selector_id": "x-only", "mode": "ARBITRARY", "filters": {"source_ids": ["x"]}},
            {"selector_id": "y-only", "mode": "ARBITRARY", "filters": {"source_ids": ["y"]}},
        ],
    }
    validate_manifest(manifest)
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    reports = build_reports(manifest, sources, selections, [])

    assert reports["R03"]["field_map"]["source_corpus_status"] == "SOURCE_CORPUS_READABLE"
    assert reports["R03"]["field_map"]["scientific_study_analysis_status"] == (
        "SCIENTIFIC_STUDY_ANALYSIS_MISSING"
    )
    assert "SCIENTIFIC_STUDY_ANALYSIS_MISSING" in reports["R03"]["limitations"]
    assert reports["R03"]["status"] == "PARTIAL"

    assert reports["R04"]["source_corpus_status"] == "SOURCE_CORPUS_READABLE"
    assert reports["R04"]["scientific_study_analysis_status"] == (
        "SCIENTIFIC_STUDY_ANALYSIS_MISSING"
    )
    assert "SCIENTIFIC_STUDY_ANALYSIS_MISSING" in reports["R04"]["limitations"]
    assert reports["R04"]["status"] == "PARTIAL"


def _full_oracle(
    study_id: str, carrier_id: str, carrier_kind: str, carrier_path: str,
    carrier_sha: str, answer_overrides: dict[str, str],
) -> dict:
    def question(number: int) -> dict:
        qid = f"5.{number}"
        text = answer_overrides.get(qid, f"Filler candidate {number} for {study_id}.")
        return {
            "question_id": qid, "question": f"Neutral question {number}?",
            "candidate_answer": text, "required_carrier_ids": [carrier_id],
            "assertion_modality": "E2_RECONSTRUCTION_CANDIDATE",
            "review_status": "SOURCE_DIRECT_AUTHORIAL_DRAFT_NOT_MODEL_RUN",
        }

    return {
        "schema": "seshat.m17.owner_authorial_candidate.v0.1",
        "study_id": study_id,
        "source_state": "SYNTHETIC_SINGLE_SOURCE_READABLE",
        "method_execution_status": "NOT_MODEL_RUN",
        "scientific_acceptance": "NOT_PERFORMED",
        "avoid_claim": "candidate is not independent acceptance",
        "carriers": [
            {"source_id": carrier_id, "kind": carrier_kind, "path": carrier_path,
             "sha256": carrier_sha},
        ],
        "questions": [question(number) for number in range(1, 15)],
        "asserted_source_claims": [],
        "scientific_conflicts": [],
        "authored_prototype_reports": {},
        "nonnegotiable_test_rules": [],
    }


def _science_manifest(tmp_path: Path) -> dict:
    (tmp_path / "study1.txt").write_text("Study one abstract text.", encoding="utf-8")
    (tmp_path / "study2.txt").write_text("Study two abstract text.", encoding="utf-8")
    return {
        "product_id": "m18-science-overlay",
        "default_selector": "all",
        "sources": [
            {"source_id": "study1-a", "study_id": "study-1", "source_kind": "A",
             "version": "1", "path": "study1.txt"},
            {"source_id": "study2-a", "study_id": "study-2", "source_kind": "A",
             "version": "1", "path": "study2.txt"},
        ],
        "selectors": [
            {"selector_id": "all", "mode": "A_ONLY"},
            {"selector_id": "study1-only", "mode": "ARBITRARY",
             "filters": {"study_ids": ["study-1"]}},
            {"selector_id": "study2-only", "mode": "ARBITRARY",
             "filters": {"study_ids": ["study-2"]}},
        ],
    }


def test_r03_r04_aggregate_two_distinct_overlays_needs_review_comparability(tmp_path):
    manifest = _science_manifest(tmp_path)
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    sha1 = _sha(tmp_path / "study1.txt")
    sha2 = _sha(tmp_path / "study2.txt")
    oracle1 = _full_oracle(
        "study-1", "study1-a", "A", "study1.txt", sha1,
        {"5.3": "Object of study is dental occlusion measurement; A PDF p.3."},
    )
    oracle2 = _full_oracle(
        "study-2", "study2-a", "A", "study2.txt", sha2,
        {"5.3": "Object of study is wound-healing rate; A PDF p.5."},
    )
    oracle1_path = tmp_path / "oracle1.json"
    oracle2_path = tmp_path / "oracle2.json"
    oracle1_path.write_text(json.dumps(oracle1), encoding="utf-8")
    oracle2_path.write_text(json.dumps(oracle2), encoding="utf-8")
    analysis1 = load_authorial_study_oracle(oracle1_path, sources)
    analysis2 = load_authorial_study_oracle(oracle2_path, sources)

    reports = build_reports(manifest, sources, selections, [], [analysis1, analysis2])

    overlay = reports["R03"]["field_map"]["science_overlay"]
    assert overlay["status"] == "AGGREGATED_TWO_OR_MORE_STUDY_OVERLAYS"
    assert overlay["cross_study_comparability"] == "NEEDS_REVIEW"
    section = overlay["sections"]["5.3_objects"]
    by_study = {row["study_id"]: row for row in section}
    assert by_study["study-1"]["candidate_answer"] != by_study["study-2"]["candidate_answer"]
    assert "dental occlusion" in by_study["study-1"]["candidate_answer"]
    assert "wound-healing" in by_study["study-2"]["candidate_answer"]
    assert by_study["study-1"]["source_addresses"][0]["source_id"] == "study1-a"
    assert reports["R03"]["field_map"]["scientific_study_analysis_status"] == (
        "SCIENTIFIC_STUDY_ANALYSIS_OVERLAY_PRESENT"
    )

    atlas_overlay = reports["R04"]["method_object_instrument_science_overlay"]
    assert atlas_overlay["status"] == "AGGREGATED_TWO_OR_MORE_STUDY_OVERLAYS"
    atlas_row_s1 = next(r for r in reports["R04"]["atlas_rows"] if r["study_id"] == "study-1")
    assert atlas_row_s1["science_overlay_sections"]["5.3_objects"][0]["candidate_answer"] == (
        by_study["study-1"]["candidate_answer"]
    )

    # A different (single-study) selector must yield a genuinely different,
    # honestly-scoped field -- not a fabricated two-study comparison.
    single_manifest = dict(manifest, default_selector="study1-only")
    single_reports = build_reports(
        single_manifest, sources, selections, [], [analysis1, analysis2]
    )
    single_overlay = single_reports["R03"]["field_map"]["science_overlay"]
    assert single_overlay["status"] == "SINGLE_STUDY_OVERLAY_ONLY"
    assert single_overlay["cross_study_comparability"] == "NOT_APPLICABLE_SINGLE_STUDY"
    assert single_overlay["contributing_study_ids"] == ["study-1"]


def test_selective_replay_invalidates_only_overlay_dependent_reports(tmp_path, monkeypatch):
    manifest = _science_manifest(tmp_path)
    sha1 = _sha(tmp_path / "study1.txt")
    sha2 = _sha(tmp_path / "study2.txt")
    oracle1 = _full_oracle(
        "study-1", "study1-a", "A", "study1.txt", sha1,
        {"5.3": "Object of study is dental occlusion measurement; A PDF p.3."},
    )
    oracle2 = _full_oracle(
        "study-2", "study2-a", "A", "study2.txt", sha2,
        {"5.3": "Object of study is wound-healing rate; A PDF p.5."},
    )
    oracle1_path = tmp_path / "oracle1.json"
    oracle2_path = tmp_path / "oracle2.json"
    oracle1_path.write_text(json.dumps(oracle1), encoding="utf-8")
    oracle2_path.write_text(json.dumps(oracle2), encoding="utf-8")
    manifest["study_analyses"] = [{"path": "oracle1.json"}, {"path": "oracle2.json"}]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        "seshat.product_preview.run_carpet",
        lambda *args: {"status": "PARTIAL_SYNTHETIC_SKIPPED", "activation_witnesses": []},
    )
    monkeypatch.setattr(
        "seshat.product_preview.run_f09a_host_batches",
        lambda *args: {"sechenovka-like": {}, "meteorology": {}},
    )
    output = tmp_path / "out"
    run_preview(manifest_path, output)
    first = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert len(first["executed_items"]) == 9

    revised = json.loads(oracle2_path.read_text(encoding="utf-8"))
    revised["questions"][2]["candidate_answer"] += " Revised candidate detail."
    oracle2_path.write_text(json.dumps(revised), encoding="utf-8")

    run_preview(manifest_path, output, resume=True)
    changed = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert changed["revised_analysis_ids"] == ["study-2"]
    assert "R03" in changed["executed_items"]
    assert "R04" in changed["executed_items"]
    assert set(changed["executed_items"]) <= {"R01", "R02", "R03", "R04"}
    for untouched in ("R05", "R06", "R07", "R08", "R09"):
        assert untouched in changed["replayed_items"]
    assert changed["duplicate_model_calls"] == 0
