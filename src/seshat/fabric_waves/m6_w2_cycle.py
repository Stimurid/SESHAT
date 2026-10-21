"""M6 external W2 return cycle: ResearchNeed → F07 admission → typed sediment.

Synthetic host authority only. Does not grant real-world source rights.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef, StoneEvent, StoneEventKind
from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    ExternalRequestStatus,
    HostJobEvidence,
    HostJobReceipt,
    WorkerCarrierRef,
    material_hash,
    utc_now_iso,
)
from seshat.fabric_waves.external_carrier.ledger import ExternalCarrierLedger
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.scenarios import bundle, output
from seshat.fabric_waves.m5_room_carpet import WorldRun, run_world
from seshat.fabric_waves.m5_synthetic_hosts import (
    BASE_SOURCE_STATE,
    MISSING_SOURCE_NEED_STATE,
    SYNTHETIC_RIGHT,
    carrier_id_from_uri,
    observed_missing_source_needs,
    verified_source_base_states,
)
from seshat.fabric_waves.room_builder import CapabilitySpec, admitted_threads, compile_room_for_stone
from seshat.fabric_waves.sediment import SedimentRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_host_stones(host: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stones = list(host.get("stones") or ())
    core = [s for s in stones if str(s.get("kind")) != "W2_RETURN"]
    w2 = [s for s in stones if str(s.get("kind")) == "W2_RETURN"]
    host_m5 = {**host, "stones": core}
    return host_m5, w2


def admit_synthetic_carrier(
    world: WorldRun,
    *,
    source_uri: str,
    version: str,
    text: str,
) -> tuple[str, str, int]:
    """Host-inject a new synthetic external carrier and return (carrier_id, digest, byte_len)."""

    # This is a fixture-only simulator, not a provider or F07 rights gateway.
    # Never allow caller-supplied real carrier bytes into the internal store.
    allowed_prefixes = {
        "WORLD_U_SYNTHETIC_UNIVERSITY": "synthetic://world-u/",
        "WORLD_O_SYNTHETIC_SERVICE": "synthetic://world-o/",
    }
    host_id = str(world.host.get("host_id") or "")
    prefix = allowed_prefixes.get(host_id)
    if (
        world.oracle_inputs_extra.get("m6_synthetic_test_context") is not True
        or prefix is None
        or not source_uri.startswith(prefix)
        or len(source_uri) <= len(prefix)
        or not version
    ):
        raise ValueError("M6_W2_REAL_OR_UNVERIFIED_CARRIER_FORBIDDEN")
    store = world.engine.carrier_store
    if store is None:
        raise ValueError("M6_W2_NO_CARRIER_STORE")
    cid = carrier_id_from_uri(source_uri)
    if cid in store._carriers:
        raise ValueError(f"M6_W2_CARRIER_ALREADY_PRESENT:{cid}")
    src, content = carrier(carrier_id=cid, version=version, text=text)
    store._carriers[cid] = src.model_copy(deep=True)
    store._contents[cid] = content.model_copy(deep=True)
    body = content.content if isinstance(content.content, bytes) else str(content.content).encode()
    digest = hashlib.sha256(body).hexdigest()
    return cid, digest, len(body)


def _parse_w2_fields(text: str) -> dict[str, Any]:
    overlap = "sample_overlap_with_beta=YES" in text or "overlap_with_beta=yes" in text.lower()
    independent = "independent_labels=YES" in text or "label_independence=CONFIRMED" in text
    safety_none = "maintenance_escalation_assertion=NONE" in text
    return {
        "sample_overlap_with_beta": overlap,
        "independent_labels_claimed": independent,
        "maintenance_escalation_assertion": not safety_none if "maintenance_escalation" in text else None,
    }


def _synthetic_method_ref() -> MethodBodyRef:
    return MethodBodyRef(method_body_id="m6-synthetic-w2-admission", version="2026-10-21")


def _build_research_need(
    world: WorldRun,
    *,
    request_id: str,
    need_activation_id: str,
    question: str,
) -> AgentTaskRequest:
    run_id = world.run_ids[-1] if world.run_ids else f"m6-{world.slug}-need"
    canonical = material_hash({"host": world.host["host_id"], "need": need_activation_id})
    return AgentTaskRequest(
        request_id=request_id,
        idempotency_key=material_hash({"request_id": request_id, "host": world.host["host_id"]}),
        run_id=run_id,
        wave_id=f"{run_id}:wave:1",
        thread_id=f"frontier-{world.slug}",
        node_id=f"m6-need-{world.slug}",
        method_body_ref=_synthetic_method_ref(),
        worker_ref=WorkerCarrierRef(
            carrier_id="m6-synthetic-external-worker",
            host_scope=str(world.host["host_id"]),
            capability_handle="SYNTHETIC_W2_RETURN",
        ),
        source_carrier_ids=(),
        canonical_input_hash=canonical,
        admissible_evidence_classes=("SYNTHETIC_EXTERNAL_FIELD",),
        source_rights=RawAccessPolicy.FULL_REQUIRED,
        expected_output_schema="m6.external_w2_observation.v1",
        status=ExternalRequestStatus.WAITING_EXTERNAL,
        created_at=utc_now_iso(),
        question_query=question,
        provenance=("M6_CAUSAL_WITNESS_NEED", f"trigger:{need_activation_id}"),
    )


def _build_evidence_return(
    *,
    request: AgentTaskRequest,
    return_id: str,
    carrier_id: str,
    source_version: str,
    content_digest: str,
    byte_length: int,
    proposal: dict[str, Any],
) -> AgentEvidenceReturn:
    job = HostJobEvidence(
        job_id=f"job-{return_id}",
        host_scope=request.worker_ref.host_scope,
        request_id=request.request_id,
        started_at=_utc_now(),
        ended_at=_utc_now(),
        result_provenance=("F07_SYNTHETIC_OWNER_GRANT", f"bytes:{byte_length}"),
        result_digest=material_hash(proposal),
        allowed_source_rights=RawAccessPolicy.FULL_REQUIRED,
    )
    receipt = HostJobReceipt(
        receipt_id=f"receipt-{return_id}",
        authorized=True,
        host_job=job,
        binding_hash=material_hash({"job": job.job_id, "digest": content_digest}),
        worker_ref=request.worker_ref,
    )
    return AgentEvidenceReturn(
        request_id=request.request_id,
        idempotency_key=material_hash({"return_id": return_id}),
        run_id=request.run_id,
        worker_ref=request.worker_ref,
        epistemic_level=EpistemicLevel.E5,
        proposal_payload=proposal,
        source_claim_refs=(f"{carrier_id}@{source_version}",),
        method_call_receipt_hash=material_hash({"method": "m6-w2-admit", "return": return_id}),
        result_digest=material_hash(proposal),
        host_receipt=receipt,
    )


def execute_w2_return(
    world: WorldRun,
    stone: Mapping[str, Any],
    *,
    ledger: ExternalCarrierLedger,
    require_prior_need: bool = True,
) -> dict[str, Any]:
    """Register need (if missing), admit W2 bytes, deposit external sediment."""

    stone_id = str(stone["stone_id"])
    return_id = str(stone.get("return_id") or f"return-{stone_id}")
    request_id = str(stone.get("request_id") or f"need-{world.slug}-{stone_id}")
    ext = stone.get("external_source") or {}
    source_uri = str(ext.get("id") or "")
    version = str(ext.get("version") or "")
    text = str(ext.get("content") or "")
    if not source_uri or not version or not text:
        raise ValueError("M6_W2_INCOMPLETE_SOURCE_SPEC")
    if ext.get("rights") != "SYNTHETIC_OWNER_GRANT":
        raise ValueError("M6_W2_NO_SYNTHETIC_TEST_GRANT")

    needs = observed_missing_source_needs(world.engine, world.run_ids)
    if require_prior_need and not needs:
        raise ValueError("M6_W2_NO_WITNESSED_NEED")

    need_activation = needs[0] if needs else f"synthetic-need-{stone_id}"
    if ledger.need_by_id(request_id) is None:
        question = ""
        for prior in world.host.get("stones") or ():
            if str(prior.get("kind")) == "QUERY":
                question = str(prior.get("question") or "")
        ledger.register_need(
            _build_research_need(
                world, request_id=request_id, need_activation_id=need_activation, question=question
            )
        )

    idem_key = material_hash({"return_id": return_id})
    if idem_key in ledger.admitted_idempotency_keys:
        prior = next(
            (r for r in ledger.evidence_returns if r.idempotency_key == idem_key),
            None,
        )
        return {
            "stone_id": stone_id,
            "return_id": return_id,
            "status": "IDEMPOTENT_REPLAY",
            "evidence_return": prior.model_dump(mode="python") if prior else None,
        }

    carrier_id, content_digest, byte_len = admit_synthetic_carrier(
        world, source_uri=source_uri, version=version, text=text
    )
    store = world.engine.carrier_store
    assert store is not None
    pinned = store.pin_content_digest(carrier_id, pinned_version=version)

    parsed = _parse_w2_fields(text)
    proposal = {
        "schema": "m6.external_w2_observation.v1",
        "carrier_id": carrier_id,
        "source_uri": source_uri,
        "source_version": version,
        "content_sha256": pinned,
        "byte_length": byte_len,
        "reading_extent": "FULL_SYNTHETIC_FIXTURE",
        "producer_run_id": world.run_ids[-1] if world.run_ids else None,
        **parsed,
    }
    request = ledger.need_by_id(request_id)
    if request is None:
        raise ValueError("M6_W2_NEED_MISSING")
    evidence = _build_evidence_return(
        request=request,
        return_id=return_id,
        carrier_id=carrier_id,
        source_version=version,
        content_digest=pinned,
        byte_length=byte_len,
        proposal=proposal,
    )
    ledger.admit_return(evidence)

    # Build a real, dynamically bound *synthetic* capability over the admitted
    # new carrier. A manually deposited E5 proposal does not count as F04/F05
    # work: the engine must fire an actual source-reading thread and ledger it.
    engine = world.engine
    thread_id = f"m6-w2-evidence-{world.slug}-{stone_id}"
    run_id = f"m6-{world.slug}-{stone_id}-source-wave"

    def observe_w2(inv):
        data = inv.carried_payload
        observed_text = str(data.get("text") or "")
        # Engine invocations expose the authenticated source manifest, not
        # the provider's free-form source_versions map. Read the exact F07
        # receipts and compare them to the synthetic host-pinned source.
        manifest = data.get("source_access_manifest")
        source_receipts = manifest.receipts if manifest else ()
        pinned_receipt = any(
            r.carrier_id == carrier_id
            and r.source_version == version
            and r.content_sha256 == pinned
            for r in source_receipts
        )
        observed_digest = hashlib.sha256(observed_text.encode("utf-8")).hexdigest()
        if not pinned_receipt or observed_digest != pinned:
            from seshat.fabric_waves.method_body import BodyResult
            return BodyResult(aporia="M6_W2_SOURCE_VERSION_OR_DIGEST_DRIFT")
        observed_version = version
        observed_payload = {
            **proposal,
            "source_version": observed_version,
            "content_sha256": observed_digest,
            "byte_length": len(observed_text.encode("utf-8")),
            "producer_run_id": run_id,
            **_parse_w2_fields(observed_text),
        }
        result = output(inv, observed_payload, kind="m6.external_w2_observation")
        return result.model_copy(update={
            "produced_sediments": tuple(
                item.model_copy(update={
                    "provenance": (*item.provenance,
                                   "SYNTHETIC_SELF_ASSERTED_RETURN",
                                   "TEST_FIXTURE_NOT_REAL_F07"),
                }, deep=True)
                for item in result.produced_sediments
            ),
        }, deep=True)

    spec, law, body = bundle(
        thread_id,
        observe_w2,
        source=carrier_id,
        kinds=(StoneEventKind.FRONTIER_RETURN,),
        output_sediment_type="m6.external_w2_observation",
    )
    engine.bodies.register(body, operations=(spec.nodes[0].operation_id,))
    engine.thread_specs[thread_id] = spec
    engine.propagation_laws[thread_id] = law
    # Expose the actual binding to RM20; a FIRED thread without an explicit
    # registry capability must remain a fatal unbound-orphan defect.
    world.binding["M6-W2-SYNTHETIC"] = (thread_id,)
    w2_capability = CapabilitySpec(
        registry_id="M6-W2-SYNTHETIC",
        role="synthetic source-bound external return validation",
        read_set=(MISSING_SOURCE_NEED_STATE, BASE_SOURCE_STATE),
        write_set=("SyntheticW2Observation",),
        requires_rights=SYNTHETIC_RIGHT,
    )
    room = compile_room_for_stone(
        host_id=str(world.host["host_id"]),
        host_slug=world.slug,
        stone={"stone_id": f"{stone_id}-W2-EVIDENCE", "kind": "FRONTIER_NEED"},
        registry=(*world.registry, w2_capability),
        thread_binding={**world.binding, "M6-W2-SYNTHETIC": (thread_id,)},
        available_base_states=(
            *verified_source_base_states(engine, world.host),
            MISSING_SOURCE_NEED_STATE,
        ),
        granted_rights=(SYNTHETIC_RIGHT,),
        budget=dict(world.host.get("room_budget") or {}),
        desired_output_states=("SyntheticW2Observation",),
    )
    if room.admitted_engine_threads != (thread_id,):
        raise ValueError("M6_W2_F04_F05_CAPABILITY_NOT_ADMITTED")
    world.manifests.append(room)
    source_event = StoneEvent(
        event_id=f"{run_id}:return",
        kind=StoneEventKind.FRONTIER_RETURN,
        issued_at_tick=1100,
        payload={
            "need_id": need_activation,
            "synthetic_return": True,
            "source_carrier_id": carrier_id,
            "source_version": version,
        },
    )
    with admitted_threads(engine, room.admitted_engine_threads):
        engine.run(run_id=run_id, budget=world.budget, initial_stone=source_event)
    room.close(activations=engine.ledger.activations, run_id=run_id)
    fired = [
        a for a in engine.ledger.activations
        if a.run_id == run_id and a.thread_id == thread_id and a.outcome.value == "FIRED"
    ]
    records = [
        r for r in engine.sediment.all_records()
        if r.produced_by_thread == thread_id
        and r.object_type == "m6.external_w2_observation"
        and r.payload.get("content_sha256") == pinned
    ]
    if len(fired) != 1 or len(records) != 1:
        selected = [
            (a.run_id, a.thread_id, a.outcome.value, a.error_code, a.error_detail)
            for a in engine.ledger.activations if a.run_id == run_id
        ]
        raise ValueError(
            f"M6_W2_F04_F05_NO_SOURCE_BOUND_ACTIVATION: fired={len(fired)} "
            f"records={len(records)} observed={selected!r}"
        )
    record = records[0]
    # Scientific status is not elevated: the source and this MethodBody are
    # artificial; E5 here remains the separately admitted external *proposal*.
    proposal["producer_run_id"] = run_id
    world.run_ids.append(run_id)
    world.oracle_inputs_extra.setdefault("m6_w2_actual_activations", []).append({
        "source_carrier_id": carrier_id,
        "source_version": version,
        "source_sha256": pinned,
        "need_activation_id": need_activation,
        "run_id": run_id,
        "activation_id": fired[0].activation_id,
        "room_id": room.room_id,
        "sediment_id": record.sediment_id,
        "sediment_version": record.version,
    })

    receipt = {
        "stone_id": stone_id,
        "return_id": return_id,
        "request_id": request_id,
        "status": "SYNTHETIC_SELF_ASSERTED_RETURN",
        "source_authority": "TEST_FIXTURE_NOT_REAL_F07",
        "carrier_id": carrier_id,
        "source_version": version,
        "content_sha256": pinned,
        "byte_length": byte_len,
        "sediment_id": record.sediment_id,
        "w2_activation_id": fired[0].activation_id,
        "w2_run_id": run_id,
        "w2_room_id": room.room_id,
        "sediment_version": record.version,
        "parsed": parsed,
        "evidence_return": evidence.model_dump(mode="python"),
    }
    return receipt


def run_m6_world(
    host: Mapping[str, Any],
    *,
    fixture: Mapping[str, Any],
    fixture_sha256: str,
    resume_from: Any = None,
    skip_w2: bool = False,
) -> WorldRun:
    host_m5, w2_stones = split_host_stones(host)
    world = run_world(host_m5, fixture=fixture, fixture_sha256=fixture_sha256, resume_from=resume_from)
    world.oracle_inputs_extra["m6_synthetic_test_context"] = (
        fixture.get("status") == "SYNTHETIC_EXPECTED_INPUTS_ONLY__NO_ACTUAL_RUNTIME"
        and fixture.get("host_rights") == "NONE_REQUIRED_FOR_INVENTED_INPUTS__NO_REAL_WORLD_SOURCES"
        and str(host.get("host_id") or "") in (
            "WORLD_U_SYNTHETIC_UNIVERSITY", "WORLD_O_SYNTHETIC_SERVICE"
        )
    )
    from seshat.fabric_waves.m5_room_carpet import _frontier_probe

    world.oracle_inputs_extra["m6_frontier_probe"] = _frontier_probe(world)
    ledger = ExternalCarrierLedger()
    receipts: list[dict[str, Any]] = []
    if not skip_w2:
        for stone in w2_stones:
            first = execute_w2_return(world, stone, ledger=ledger)
            receipts.append(first)
            # Deliberately exercise duplicate admission in this synthetic run:
            # it must find the original return without making another carrier,
            # evidence record or paid/external call.
            before_count = len(world.engine.sediment.all_records())
            before_admitted = len(ledger.evidence_returns)
            replay = execute_w2_return(world, stone, ledger=ledger)
            if (
                replay.get("status") != "IDEMPOTENT_REPLAY"
                or len(world.engine.sediment.all_records()) != before_count
                or len(ledger.evidence_returns) != before_admitted
            ):
                raise ValueError("M6_W2_DUPLICATE_CHANGED_SEDIMENT_OR_LEDGER")
            replay["verified_no_new_evidence"] = True
            receipts.append(replay)
    world.oracle_inputs_extra["m6_w2_receipts"] = receipts
    world.oracle_inputs_extra["m6_external_ledger"] = json.loads(ledger.model_dump_json())
    return world


def w2_observations(world: WorldRun) -> tuple[SedimentRecord, ...]:
    return tuple(
        r
        for r in world.engine.sediment.all_records()
        if r.object_type == "m6.external_w2_observation"
    )


def completed_source_versions(world: WorldRun) -> list[dict[str, str]]:
    """Per-carrier version and content digest for F09A manifest (no private paths)."""

    store = world.engine.carrier_store
    if store is None:
        return []
    from seshat.fabric_waves.m5_synthetic_hosts import declared_source_versions

    out: list[dict[str, str]] = []
    declared = declared_source_versions(world.host)
    actual = store.current_source_versions(tuple(declared))
    for cid in declared:
        current_version = actual.get(cid)
        if current_version is None:
            raise ValueError("M6_F09A_SOURCE_VERSION_NOT_OBSERVED")
        digest = store.pin_content_digest(cid, pinned_version=current_version)
        out.append({"carrier_id": cid, "version": current_version, "content_sha256": digest})
    for rec in w2_observations(world):
        payload = rec.payload or {}
        out.append(
            {
                "carrier_id": str(payload.get("carrier_id") or ""),
                "version": str(payload.get("source_version") or ""),
                "content_sha256": str(payload.get("content_sha256") or ""),
                "external_w2": "true",
            }
        )
    return out


__all__ = [
    "admit_synthetic_carrier",
    "completed_source_versions",
    "execute_w2_return",
    "run_m6_world",
    "split_host_stones",
    "w2_observations",
]
