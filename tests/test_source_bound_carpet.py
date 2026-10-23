"""Owner-source Carpet causality tests: synthetic files only, no private corpus."""
from __future__ import annotations

import json
from pathlib import Path

from seshat.product_preview import ingest_sources, load_method_outputs
from seshat.source_bound_carpet import run_source_bound_carpet


def _inputs(root: Path, *, exclude_second=False, missing_second=False):
    (root / "a.txt").write_text(
        "research object A: interview coding and documented consent",encoding="utf-8"
    )
    (root / "b.txt").write_text(
        "research object B: observation and method comparison",encoding="utf-8"
    )
    (root / "i11a.json").write_text(json.dumps({
        "action_events": [
            {"id":"E01","layer":"RP","verb":"collected interview evidence",
             "relation_mode":"SOURCE_ASSERTED_OPERATION",
             "source_addresses":[{"page":2,"quote":"interviewed participants"}]}
        ]
    }),encoding="utf-8")
    m={
        "product_id":"test-dynamic-carpet",
        "sources":[
            {"source_id":"src-a","study_id":"study-A","source_kind":"ARTICLE",
             "version":"1","path":"a.txt"},
            {"source_id":"src-b","study_id":"study-B","source_kind":"ARTICLE",
             "version":"1","path":"missing.txt" if missing_second else "b.txt",
             "excluded":exclude_second},
        ],
        "method_outputs":[
            {"study_id":"study-A","method_id":"I11_ACTIVITY_NETWORK",
             "version":"1","path":"i11a.json"},
        ],
    }
    return ingest_sources(m,root),load_method_outputs(m,root)


def test_real_source_path_generates_live_cross_thread_activations(tmp_path):
    sources,methods=_inputs(tmp_path)
    r=run_source_bound_carpet(tmp_path/"out",sources,methods,["src-a","src-b"])
    assert r["status"]=="WORKS_ACTUAL_LOCAL_SOURCE_CARRIER_ENGINE"
    assert r["selected_sources_causally_bound_to_engine_activations"]
    assert r["at_least_two_cross_thread_activations"]
    assert r["read_threads_fired"] and r["archived_i11_index_threads_fired"]
    assert r["field_summary_thread_fired"]
    threads={x["thread_id"] for x in r["activation_witnesses"]}
    assert threads=={
        "source-read-1","source-read-2",
        "i11-archive-index-1","i11-archive-index-2","selected-field-summary"
    }
    assert r["model_provider_calls"]==0
    assert (tmp_path/"out"/"owner-source-baseline"/"waves.jsonl").is_file()


def test_counterfactual_revision_is_selective_and_preserves_original(tmp_path):
    sources,methods=_inputs(tmp_path)
    before_a=(tmp_path/"a.txt").read_bytes()
    before_b=(tmp_path/"b.txt").read_bytes()
    r=run_source_bound_carpet(tmp_path/"out",sources,methods,["src-a","src-b"])
    trial=r["counterfactual_delta"]
    assert trial["scenario"]=="COUNTERFACTUAL_LOCAL_TEST_NOT_REAL_PDF_REVISION"
    assert trial["changed_source"]=="src-b"
    assert trial["changed_read_refired"]
    assert trial["field_summary_refired"]
    assert trial["unchanged_read_threads_remain_idle"]
    assert "source-read-1" not in trial["actual_fired_thread_ids"]
    assert (tmp_path/"a.txt").read_bytes()==before_a
    assert (tmp_path/"b.txt").read_bytes()==before_b


def test_owner_exclusion_is_not_read(tmp_path):
    sources,methods=_inputs(tmp_path,exclude_second=True)
    r=run_source_bound_carpet(tmp_path/"out",sources,methods,["src-a","src-b"])
    assert r["selected_source_ids"]==["src-a"]
    assert r["counterfactual_delta"] is None
    assert r["read_threads_fired"]
    assert {x["thread_id"] for x in r["activation_witnesses"]}=={
        "source-read-1","i11-archive-index-1","selected-field-summary"
    }


def test_missing_source_does_not_fabricate_activations(tmp_path):
    sources,methods=_inputs(tmp_path,missing_second=True)
    r=run_source_bound_carpet(tmp_path/"out",sources,methods,["src-b"])
    assert r["status"]=="PARTIAL_NO_READABLE_SELECTED_SOURCE"
    assert r["activation_witnesses"]==[]
    assert not r["selected_sources_causally_bound_to_engine_activations"]


def test_fixed_inputs_have_deterministic_native_activation_trace(tmp_path):
    sources,methods=_inputs(tmp_path)
    run_source_bound_carpet(tmp_path/"r1",sources,methods,["src-a","src-b"])
    run_source_bound_carpet(tmp_path/"r2",sources,methods,["src-a","src-b"])
    p1=tmp_path/"r1"/"owner-source-baseline"/"activations.jsonl"
    p2=tmp_path/"r2"/"owner-source-baseline"/"activations.jsonl"
    assert p1.read_bytes()==p2.read_bytes()


def test_same_research_study_with_two_carriers_is_not_double_counted(tmp_path):
    sources,methods=_inputs(tmp_path)
    sources[1]["study_id"]="study-A"
    result=run_source_bound_carpet(
        tmp_path/"ad",sources,methods,["src-a","src-b"]
    )
    assert result["selected_sources_causally_bound_to_engine_activations"]
    lines=(tmp_path/"ad"/"owner-source-baseline"/"sediment.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    field=[
        x for x in (json.loads(s) for s in lines)
        if x["object_type"]=="sourcebound.selection_field_index"
    ]
    assert len(field)==1
    assert field[0]["payload"]["selected_study_ids"]==["study-A"]
    assert field[0]["payload"]["archived_i11_event_count"]==1


def test_real_source_carpet_exports_visualization_for_both_runs(tmp_path):
    sources,methods=_inputs(tmp_path)
    run_source_bound_carpet(tmp_path/"view",sources,methods,["src-a","src-b"])
    for run in ("owner-source-baseline","owner-source-counterfactual-delta"):
        base=tmp_path/"view"/run
        visual=(base/"carpet.html")
        assert visual.exists() and len(visual.read_bytes())>1000
        assert (base/"sediment.jsonl").exists()
        assert (base/"activations.jsonl").exists()
