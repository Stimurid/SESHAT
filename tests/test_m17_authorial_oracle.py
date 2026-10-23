from __future__ import annotations

import hashlib
import json
from pathlib import Path

from seshat.authorial_oracle import load_authorial_study_oracle
from seshat.product_preview import (
    build_reports,
    build_selections,
    ingest_sources,
    load_method_outputs,
    run_preview,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(tmp_path: Path) -> tuple[dict, Path]:
    (tmp_path / "a.txt").write_text(
        "Synthetic abstract: material, method and bounded result.", encoding="utf-8"
    )
    (tmp_path / "d.txt").write_text(
        "Synthetic dissertation: variable-x 12/20; variable-y 17/20; local count 9/10.",
        encoding="utf-8",
    )
    (tmp_path / "article.txt").write_text("Unrelated calibration article.", encoding="utf-8")
    manifest = {
        "product_id": "synthetic-m17",
        "synthetic_fixture": True,
        "default_selector": "ad",
        "report_selectors": {"R01": "a", "R02": "ad"},
        "sources": [
            {"source_id": "source-a", "study_id": "study-neutral", "source_kind": "A",
             "version": "1", "path": "a.txt", "objects": ["material"],
             "methods": ["inspection"], "infrastructure": []},
            {"source_id": "source-d", "study_id": "study-neutral", "source_kind": "D",
             "version": "1", "path": "d.txt", "objects": ["measurement"],
             "methods": ["comparison"], "infrastructure": []},
            {"source_id": "source-article", "study_id": "other-study",
             "source_kind": "ARTICLE", "version": "1", "path": "article.txt",
             "objects": ["calibration"], "methods": ["review"], "infrastructure": []},
        ],
        "selectors": [
            {"selector_id": "a", "mode": "A_ONLY"},
            {"selector_id": "d", "mode": "D_ONLY"},
            {"selector_id": "ad", "mode": "A_PLUS_D"},
            {"selector_id": "article", "mode": "ARTICLE_ONLY"},
            {"selector_id": "all", "mode": "ARBITRARY"},
        ],
    }
    oracle = {
        "schema": "seshat.m17.owner_authorial_candidate.v0.1",
        "study_id": "study-neutral",
        "source_state": "TWO_SYNTHETIC_SOURCES_READABLE",
        "method_execution_status": "NOT_MODEL_RUN",
        "scientific_acceptance": "NOT_PERFORMED",
        "avoid_claim": "candidate is not independent acceptance",
        "carriers": [
            {"source_id": "source-a", "kind": "A", "path": "a.txt",
             "sha256": _sha(tmp_path / "a.txt")},
            {"source_id": "source-d", "kind": "D", "path": "d.txt",
             "sha256": _sha(tmp_path / "d.txt")},
        ],
        "questions": [
            {"question_id": f"5.{number}", "question": f"Neutral question {number}?",
             "candidate_answer": (
                 f"Candidate reconstruction {number}; A PDF p.{number}."
                 if number < 8 else f"Candidate reconstruction {number}; D PDF p.{number}."
             ),
             "assertion_modality": "E2_RECONSTRUCTION_CANDIDATE",
             "review_status": "SOURCE_DIRECT_AUTHORIAL_DRAFT_NOT_MODEL_RUN"}
            for number in range(1, 15)
        ],
        "asserted_source_claims": [
            {"claim_id": "C.D.X12", "carrier": "source-d", "pdf_page_index": 10,
             "location": "Table X", "asserted_proposition": "variable-x is 12 of 20",
             "metric": "variable-x", "numerator": 12, "denominator": 20,
             "source_modality": "E1_SOURCE_FIXATION"},
            {"claim_id": "C.D.Y17", "carrier": "source-d", "pdf_page_index": 11,
             "location": "Table Y", "asserted_proposition": "variable-y is 17 of 20",
             "metric": "variable-y", "numerator": 17, "denominator": 20,
             "source_modality": "E1_SOURCE_FIXATION"},
            {"claim_id": "C.D.COUNT9", "carrier": "source-d", "pdf_page_index": 12,
             "location": "Narrative", "asserted_proposition": "local count is 9",
             "metric": "group-count", "numerator": 9, "denominator": 10,
             "source_modality": "E1_SOURCE_FIXATION"},
            {"claim_id": "C.D.COUNT8", "carrier": "source-d", "pdf_page_index": 13,
             "location": "Summary", "asserted_proposition": "summary count is 8",
             "metric": "group-count", "numerator": 8, "denominator": 10,
             "source_modality": "E1_SOURCE_FIXATION"},
        ],
        "scientific_conflicts": [
            {"conflict_id": "N17-01", "type": "VARIABLE_IDENTITY_CONFLICT",
             "claim_ids": ["C.D.X12", "C.D.Y17"], "status": "UNRESOLVED",
             "interpretation": "variable-x and variable-y are not interchangeable",
             "desired_R01": "preserve", "desired_R02": "trace"},
            {"conflict_id": "N17-02", "type": "COUNT_DENOMINATOR_CONFLICT",
             "claim_ids": ["C.D.COUNT9", "C.D.COUNT8"], "status": "UNRESOLVED",
             "interpretation": "counts 9 and 8 disagree without explanation",
             "desired_R01": "preserve", "desired_R02": "trace"},
        ],
        "authored_prototype_reports": {
            "R01": "A coherent synthetic study narrative preserves 12/20 versus 17/20 and 9 versus 8 as unresolved.",
            "R02": "A coherent synthetic object-method narrative keeps two variables distinct and records both APORIA.",
        },
        "nonnegotiable_test_rules": ["no self acceptance"],
    }
    oracle_path = tmp_path / "oracle.json"
    oracle_path.write_text(json.dumps(oracle, ensure_ascii=False), encoding="utf-8")
    return manifest, oracle_path


def _loaded(tmp_path: Path):
    manifest, oracle_path = _case(tmp_path)
    sources = ingest_sources(manifest, tmp_path)
    selections = build_selections(manifest, sources)
    analysis = load_authorial_study_oracle(oracle_path, sources)
    reports = build_reports(manifest, sources, selections, load_method_outputs(manifest, tmp_path), [analysis])
    return manifest, oracle_path, sources, selections, analysis, reports


def _lightweight_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        "seshat.product_preview.run_carpet",
        lambda *args: {"status": "PARTIAL_SYNTHETIC_SKIPPED", "activation_witnesses": []},
    )
    monkeypatch.setattr(
        "seshat.product_preview.run_f09a_host_batches",
        lambda *args: {"sechenovka-like": {}, "meteorology": {}},
    )


def test_typed_import_keeps_one_research_object_two_carriers_and_14_candidates(tmp_path):
    _, _, _, _, analysis, _ = _loaded(tmp_path)
    assert analysis.research_object_id == "study-neutral"
    assert {item.source_id for item in analysis.carriers} == {"source-a", "source-d"}
    assert len(analysis.answers) == 14
    assert all(item.assertion_modality == "E2_RECONSTRUCTION_CANDIDATE" for item in analysis.answers)
    assert all(item.sha256 == _sha(tmp_path / item.path) for item in analysis.carriers)
    assert analysis.method_execution_status == "NOT_MODEL_RUN"


def test_conflicts_are_typed_and_a_only_excludes_d_claims(tmp_path):
    _, _, _, _, _, reports = _loaded(tmp_path)
    a_state = reports["R01"]["study_analyses"][0]
    ad_state = reports["R02"]["study_analyses"][0]
    assert a_state["claims"] == []
    assert a_state["contradictions"] == []
    assert {item["contradiction_id"] for item in ad_state["contradictions"]} == {
        "N17-01", "N17-02"
    }
    assert "12/20" in reports["R02"]["scientific_narratives"][0]["text"]
    assert reports["R02"]["method_run_performed"] is False
    assert reports["R06"]["comparisons"] == []  # no fake global novelty from source D


def test_d_only_is_a_real_study_view_not_no_study(tmp_path):
    manifest, _, sources, selections, analysis, _ = _loaded(tmp_path)
    manifest["report_selectors"]["R01"] = "d"
    reports = build_reports(manifest, sources, selections, [], [analysis])
    assert reports["R01"]["selection_members"] == ["source-d"]
    assert reports["R01"]["study_assemblies"][0]["study_id"] == "study-neutral"
    assert len(reports["R01"]["study_analyses"][0]["claims"]) == 4


def test_actual_source_bound_carpet_fires_two_threads_and_persists_claim_sediment(
    tmp_path, monkeypatch
):
    manifest, oracle_path = _case(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _lightweight_runtime(monkeypatch)
    receipt = run_preview(
        manifest_path, tmp_path / "out", study_analysis_paths=[oracle_path]
    )
    source_bound = receipt["carpet"]["source_bound"]
    assert source_bound["at_least_two_distinct_activations"] is True
    assert {item["thread_role"] for item in source_bound["activation_witnesses"]} == {
        "STUDY_EVIDENCE_STATE", "CLAIM_CONTRADICTION_APORIA"
    }
    assert len(source_bound["typed_claim_sediments"]) == 4
    assert len(source_bound["typed_contradiction_sediments"]) == 2
    assert receipt["route"]["selected_sources_causally_bound_to_engine_activations"] is True
    assert (tmp_path / "out/carpet/m17_source_bound/activations.jsonl").is_file()


def test_resume_reuses_versions_and_contradiction_delta_only_invalidates_r02(
    tmp_path, monkeypatch
):
    manifest, oracle_path = _case(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _lightweight_runtime(monkeypatch)
    output = tmp_path / "out"
    run_preview(manifest_path, output, study_analysis_paths=[oracle_path])
    first = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    replay_receipt = run_preview(
        manifest_path, output, resume=True, study_analysis_paths=[oracle_path]
    )
    replay = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert replay["executed_items"] == []
    assert replay["items"]["R02"]["report_version"] == first["items"]["R02"]["report_version"]
    assert replay_receipt["carpet"]["source_bound"]["status"] == (
        "REPLAYED_SOURCE_BOUND_NO_MODEL_CALL"
    )

    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle["scientific_conflicts"][0]["interpretation"] += "; revised candidate"
    oracle_path.write_text(json.dumps(oracle, ensure_ascii=False), encoding="utf-8")
    receipt = run_preview(manifest_path, output, resume=True, study_analysis_paths=[oracle_path])
    changed = json.loads((output / "f09a_preview_ledger.json").read_text(encoding="utf-8"))
    assert changed["revised_analysis_ids"] == ["study-neutral"]
    assert "R01" in changed["replayed_items"]
    assert "R02" in changed["executed_items"]
    assert receipt["carpet"]["source_bound"]["targeted_invalidated_reports"] == ["R02"]
    assert changed["duplicate_model_calls"] == 0
