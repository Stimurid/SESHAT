"""Causal owner-selected source Carpet, with zero external model invocations.

Two real local source extractions are read through FabricCarrierStore. Original
I11 model outputs remain immutable inputs for a typed candidate-event index.
The engine executes actual read/index/field threads and exports its native
event, activation, wave and sediment trail. It is not a new LLM method run.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.fabric_waves.contracts import (
    EpistemicLevel, MethodBodyRef, PropagationLaw, StoneEvent, StoneEventKind,
    ThreadNodeSpec, WaveBudget, WorkflowThreadSpec,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult, MethodBodyRegistry
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore


@dataclass(frozen=True)
class _LocalMethod:
    method_body_id: str
    version: str
    fn: Callable[[BodyInvocation], BodyResult]

    def __call__(self, invocation: BodyInvocation) -> BodyResult:
        return self.fn(invocation)


def _produce(inv: BodyInvocation, data: dict[str, Any], *, study: str,
             kind: str, level: EpistemicLevel) -> BodyResult:
    digest = payload_hash(data)
    record = SedimentRecord(
        sediment_id=str(inv.carried_payload["output_sediment_id"]),
        object_type=kind, version=digest, research_object_id=study,
        payload=data, payload_hash=digest,
        provenance=("OWNER_SELECTED_LOCAL_SOURCE", "ENGINE_RUN_NOT_SCIENCE_ACCEPTED"),
        method_body_refs=(inv.method_body_ref,),
        source_carrier_refs=tuple(inv.carried_payload.get("carriers", ())),
        read_dependencies=inv.consumed_sediment_ids,
        epistemic_level=level,
        produced_by_thread=inv.thread_id,
        produced_at_tick=inv.tick, produced_in_wave=inv.wave_index,
        produced_by_stone_kind=inv.stone_kind,
    )
    return BodyResult(produced_sediments=(record,))


def _thread(tid: str, fn: Callable[[BodyInvocation], BodyResult], *,
            source_id: str | None = None, reads: Sequence[str] = (), output_type: str = "sourcebound.source_observation"):
    ref=MethodBodyRef(method_body_id="seshat.sourcebound."+tid, version="1")
    spec=WorkflowThreadSpec(
        thread_id=tid, name=tid, purpose="owner-selected source-bound evidence path",
        method_body_refs=(ref,),
        admissible_source_carriers=(source_id,) if source_id else (),
        raw_access_policy=RawAccessPolicy.FULL_REQUIRED if source_id else RawAccessPolicy.NEVER,
        nodes=(ThreadNodeSpec(
            node_id="compute",operation_id=ref.method_body_id,
            method_body_ref=ref,consumes_sediment_ids=tuple(reads),
            produces_sediment_id=tid,output_sediment_type=output_type,
        ),),
        input_state=tuple(reads), output_state=(tid,),
        exit_criterion="source-attested state or explicit aporia",
        canon_status="WORKING",bounded_budget_hint=16,
    )
    law=PropagationLaw(
        thread_id=tid,initial_state=tuple(reads),
        wakes_on_carrier_ids=(source_id,) if source_id else (),
        wakes_on_stone_kinds=(
            (StoneEventKind.QUERY, StoneEventKind.SOURCE_DELTA)
            if source_id else (StoneEventKind.SEDIMENT_AVAILABLE,)
        ),
    )
    return spec,law,_LocalMethod(ref.method_body_id,"1",fn)


def _eligible(sources: Sequence[Mapping[str, Any]], ids: Sequence[str]):
    lookup={str(x["source_id"]):x for x in sources}
    return [
        lookup[id]
        for id in sorted(ids)
        if id in lookup and not lookup[id].get("excluded") and
        lookup[id].get("status")=="WORKS" and lookup[id].get("text")
    ]


def run_source_bound_carpet(
    output_dir: Path, sources: Sequence[Mapping[str,Any]],
    method_outputs: Sequence[Mapping[str,Any]], selected_ids: Sequence[str],
) -> dict[str, Any]:
    """Execute source-bound read->archived-I11-index->aggregate operations.

    SOURCE_DELTA is a clearly labelled counterfactual local fixture; it never
    modifies the original publication or claims a provider performed a re-read.
    """
    from seshat.product_preview import _historical_i11_actions, _layer_census
    selected=_eligible(sources,selected_ids)
    if not selected:
        return {
            "status":"PARTIAL_NO_READABLE_SELECTED_SOURCE",
            "selected_sources_causally_bound_to_engine_activations":False,
            "activation_witnesses":[],
        }
    output_dir.mkdir(parents=True,exist_ok=True)
    full_source_membership=(len(selected)==len(set(selected_ids)))
    carriers={}
    contents={}
    bundles=[]
    source_text_digests={}
    method_by_study={}
    for item in method_outputs:
        method_by_study.setdefault(str(item.get("study_id")),[]).append(item)
    indexed_tids=[]
    read_tids=[]
    for i,src in enumerate(selected,1):
        cid=str(src["source_id"])
        sid=str(src["study_id"])
        text=str(src["text"])
        raw=text.encode("utf-8")
        text_digest=hashlib.sha256(raw).hexdigest()
        source_text_digests[cid]=text_digest
        carriers[cid]=SourceCarrier(
            carrier_id=cid,source_identity=cid,
            version="1",media_type="text/plain",
            uri=None,content_sha256=text_digest,byte_length=len(raw),
            metadata={"original_file_sha256":str(src.get("byte_sha256") or ""),
                      "origin_type":"CURRENT_LOCAL_EXTRACTION"},
        )
        contents[cid]=SourceContent(
            carrier_id=cid,source_version="1",media_type="text/plain",
            content=raw,content_sha256=text_digest,byte_length=len(raw),
            complete=True,authorized=True,
        )
        read_tid=f"source-read-{i}"
        index_tid=f"i11-archive-index-{i}"
        read_tids.append(read_tid)
        indexed_tids.append(index_tid)
        def read(inv: BodyInvocation, *, source=cid,study=sid,
                 original_sha=src.get("byte_sha256"),expected=text_digest):
            carried=inv.carried_payload.get("text")
            if not isinstance(carried,str):
                return BodyResult(aporia="SOURCE_TEXT_NOT_READABLE")
            current=hashlib.sha256(carried.encode("utf-8")).hexdigest()
            if current!=expected and inv.stone_kind!=StoneEventKind.SOURCE_DELTA:
                return BodyResult(aporia="LOCAL_SOURCE_TEXT_SHA_DISAGREES_WITH_READ")
            return _produce(inv,{
                "source_id":source,"study_id":study,
                "source_text_sha256":current,"source_text_characters":len(carried),
                "original_file_sha256":original_sha,
                "observation_kind":"FILE_BYTES_AND_EXTRACTION_ONLY",
            },study=study,kind="sourcebound.source_observation",
            level=EpistemicLevel.E1)
        bundles.append(_thread(read_tid,read,source_id=cid))
        def index(inv: BodyInvocation, *, study=sid,source=cid,upstream=read_tid):
            observed=[r for r in inv.carried_payload.get("candidate_sediments",())
                      if r.sediment_id==upstream]
            if not observed:
                return BodyResult(aporia="SOURCE_OBSERVATION_NOT_YET_AVAILABLE")
            saved=method_by_study.get(study,[])
            actions=_historical_i11_actions(saved)
            status=("HISTORICAL_I11_CANDIDATE_INDEX_REUSED"
                    if actions else "HISTORICAL_I11_NOT_AVAILABLE")
            return _produce(inv,{
                "study_id":study,"source_id":source,
                "upstream_observation_version":observed[-1].version,
                "historical_method_output_sha256":[
                    item.get("sha256") for item in saved if item.get("status")=="WORKS"
                ],
                "historical_i11_event_count":len(actions),
                "historical_i11_layers":_layer_census(actions),
                "status":status,
                "not_actual_new_i11_provider_invocation":True,
            },study=study,kind="sourcebound.historical_method_index",
            level=EpistemicLevel.E2)
        bundles.append(_thread(index_tid,index,reads=(read_tid,),output_type="sourcebound.historical_method_index"))

    def field(inv: BodyInvocation):
        candidates=[r for r in inv.carried_payload.get("candidate_sediments",())
                    if r.object_type=="sourcebound.historical_method_index"]
        if len(candidates)!=len(indexed_tids):
            return BodyResult(aporia="SELECTED_CORPUS_METHOD_INDEX_INCOMPLETE")
        data={
            "selected_study_ids":sorted({r.payload["study_id"] for r in candidates}),
            "selected_source_ids":sorted({r.payload["source_id"] for r in candidates}),
            "archived_i11_event_count":sum(
                max(int(r.payload["historical_i11_event_count"])
                    for r in candidates if r.payload["study_id"] == study)
                for study in {r.payload["study_id"] for r in candidates}
            ),
            "indexed_sediment_versions":{
                r.sediment_id:r.version for r in candidates
            },
            "scope":"SELECTED_OWNER_CORPUS_ONLY_NOT_UNIVERSITY_POPULATION",
            "claim":"CAUSAL_SOURCE_AND_MODEL_METADATA_INDEX_NOT_NEW_SCIENCE",
        }
        return _produce(inv,data,study="selected-corpus",
                        kind="sourcebound.selection_field_index",level=EpistemicLevel.E2)
    bundles.append(_thread("selected-field-summary",field,reads=tuple(indexed_tids),output_type="sourcebound.selection_field_index"))

    revisions={}
    if len(selected)>=2:
        chosen=selected[-1]
        cid=str(chosen["source_id"])
        derived=str(chosen["text"])+"\n[LOCAL_COUNTERFACTUAL_SOURCE_REVISION_TEST]\n"
        raw=derived.encode("utf-8")
        sha=hashlib.sha256(raw).hexdigest()
        revisions[(cid,"1","2")]=(
            SourceCarrier(carrier_id=cid,source_identity=cid,version="2",
                          media_type="text/plain",content_sha256=sha,byte_length=len(raw),
                          metadata={"owner_trial":"COUNTERFACTUAL_NO_ORIGINAL_MUTATION"}),
            SourceContent(carrier_id=cid,source_version="2",media_type="text/plain",
                          content=raw,content_sha256=sha,byte_length=len(raw),
                          complete=True,authorized=True),
        )

    def revision(cid,old,new):
        return revisions[(cid,old,new)]
    store=FabricCarrierStore(
        carriers=carriers,contents=contents,
        revision_provider=revision if revisions else None,
    )
    registry=MethodBodyRegistry()
    for spec,law,body in bundles:
        registry.register(body,operations=tuple(n.operation_id for n in spec.nodes))
    engine=WaveEngine(
        thread_specs={spec.thread_id:spec for spec,_,_ in bundles},
        propagation_laws={spec.thread_id:law for spec,law,_ in bundles},
        bodies=registry,sediment=SedimentState(),carrier_store=store,
    )
    budget=WaveBudget(max_waves=40,max_activations=100,max_stone_events=150,
                      aporia_after_waves=5)
    baseline_id="owner-source-baseline"
    engine.run(
        run_id=baseline_id,budget=budget,
        initial_stone=StoneEvent(
            event_id="owner-source-query",kind=StoneEventKind.QUERY,issued_at_tick=0,
            payload={"topic":"selected owner-source research evidence",
                     "query":"index only actual readable source carriers and cached I11"},
        ),
    )

    def activation_summary(run_id):
        return [
            {
                "thread_id":a.thread_id,"activation_id":a.activation_id,
                "outcome":a.outcome.value if hasattr(a.outcome,"value") else str(a.outcome),
                "source_carrier_ids":list(a.source_carrier_ids),
                "read_sediment_ids":list(a.read_sediment_ids),
                "produced_sediment_ids":list(a.produced_sediment_ids),
            }
            for a in engine.ledger.activations_for_run(run_id)
        ]
    before=activation_summary(baseline_id)
    fired=[a for a in before if a["outcome"]=="FIRED"]
    fired_threads={a["thread_id"] for a in fired}
    read_success=set(read_tids)<=fired_threads
    index_success=set(indexed_tids)<=fired_threads
    field_success="selected-field-summary" in fired_threads
    delta_receipt=None
    if revisions and read_success and index_success and field_success:
        cid=str(selected[-1]["source_id"])
        changed_text=str(selected[-1]["text"])+"\n[LOCAL_COUNTERFACTUAL_SOURCE_REVISION_TEST]\n"
        engine.run(
            run_id="owner-source-counterfactual-delta",
            budget=budget,
            initial_stone=StoneEvent(
                event_id="owner-local-trial-delta",
                kind=StoneEventKind.SOURCE_DELTA,
                issued_at_tick=5,
                target_carrier_id=cid,
                payload={"old_version":"1","new_version":"2","text":changed_text},
            ),
        )
        after=activation_summary("owner-source-counterfactual-delta")
        delta_fired={a["thread_id"] for a in after if a["outcome"]=="FIRED"}
        delta_receipt={
            "scenario":"COUNTERFACTUAL_LOCAL_TEST_NOT_REAL_PDF_REVISION",
            "changed_source":cid,"actual_fired_thread_ids":sorted(delta_fired),
            "unchanged_read_threads_remain_idle":all(
                f"source-read-{j}" not in delta_fired
                for j in range(1,len(selected))
            ),
            "changed_read_refired":f"source-read-{len(selected)}" in delta_fired,
            "field_summary_refired":"selected-field-summary" in delta_fired,
        }

    all_runs=[baseline_id]
    if delta_receipt is not None:
        all_runs.append("owner-source-counterfactual-delta")
    for run_id in all_runs:
        run_dir=output_dir/run_id
        run_dir.mkdir(parents=True,exist_ok=True)
        activations=[a.model_dump(mode="json") for a in engine.ledger.activations_for_run(run_id)]
        waves=[a.model_dump(mode="json") for a in engine.ledger.waves if a.run_id==run_id]
        events=[a.model_dump(mode="json") for a in engine.ledger.events if a.run_id==run_id]
        from seshat.fabric_waves.carpet_export import sediment_records_for_run
        from seshat.fabric_waves.trace import render_html
        snap_ledger,snap_sediment,snap_resonances=engine.snapshot(run_id)
        sediments=sediment_records_for_run(snap_ledger,snap_sediment,run_id)
        run_record=next(x for x in snap_ledger.runs if x.run_id==run_id)
        rendered=render_html(
            run_record=run_record,ledger=snap_ledger,
            sediment=snap_sediment,resonances=snap_resonances,
            thread_specs=engine.thread_specs,
            title="SESHAT owner-selected source Carpet "+run_id,
        )
        (run_dir/"carpet.html").write_text(rendered,encoding="utf-8")
        for filename,records in (
            ("activations.jsonl",activations),("waves.jsonl",waves),
            ("events.jsonl",events),("sediment.jsonl",sediments),
        ):
            (run_dir/filename).write_text(
                "".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in records),
                encoding="utf-8",
            )
    result={
        "schema":"seshat.owner_source_bound_carpet.v1",
        "status":"WORKS_ACTUAL_LOCAL_SOURCE_CARRIER_ENGINE"
        if read_success and index_success and field_success and full_source_membership
        else "PARTIAL_SELECTED_SOURCE_BINDING",
        "selected_sources_causally_bound_to_engine_activations":
            bool(read_success and index_success and field_success and full_source_membership),
        "complete_selected_membership":full_source_membership,
        "source_text_sha256":source_text_digests,
        "selected_source_ids":[x["source_id"] for x in selected],
        "activation_witnesses":fired,
        "at_least_two_cross_thread_activations":len(fired_threads)>=2,
        "read_threads_fired":read_success,
        "archived_i11_index_threads_fired":index_success,
        "field_summary_thread_fired":field_success,
        "counterfactual_delta":delta_receipt,
        "model_provider_calls":0,
        "scientific_claim_level":"LOCAL_EXTRACTION_AND_HISTORICAL_MODEL_METADATA_NOT_METHOD_RERUN",
        "receipt_root":str(output_dir),
    }
    (output_dir/"receipt.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True),
        encoding="utf-8",
    )
    return result
