"""M6 external W2 return cycle: ResearchNeed → F07 admission → typed sediment.

Synthetic host authority only. Does not grant real-world source rights.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef, StoneEventKind
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
from seshat.fabric_waves.m5_room_carpet import WorldRun, run_world
from seshat.fabric_waves.m5_synthetic_hosts import (
    carrier_id_from_uri,
    observed_missing_source_needs,
)
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_host_stones(host: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stones = list(host.get("stones") or ())
    core = [s for s in stones if str(s.get("kind")) != "W2_RETURN"]
    w2 = [s for s in stones if str(s.get("kind")) == "W2_RETURN"]
    host_m5 = {**host, "stones": core}
    return host_m5, w2


_SYNTHETIC_TEST_HOSTS = frozenset((
    "WORLD_U_SYNTHETIC_UNIVERSITY",
    "WORLD_O_SYNTHETIC_SERVICE",
))


def _require_synthetic_test_source(
    world: WorldRun, source_uri: str, version: str, text: str
) -> None:
    """Never admit a real or unrelated carrier through the fictional W2 adapter."""

    if str(world.host.get("host_id")) not in _SYNTHETIC_TEST_HOSTS:
        raise ValueError("M6_W2_ONLY_FROZEN_SYNTHETIC_HOSTS")
    uri = urlsplit(source_uri)
    declared = [
        str(item.get("id") or "")
        for item in world.host.get("source_versions") or ()
    ]
    namespaces = {
        urlsplit(item).netloc
        for item in declared
        if urlsplit(item).scheme == "synthetic"
    }
    if (
        uri.scheme != "synthetic"
        or not uri.netloc
        or uri.netloc not in namespaces
        or not uri.path.startswith("/")
        or ".." in uri.path.split("/")
        or source_uri in declared
    ):
        raise ValueError("M6_W2_SOURCE_NOT_IN_TEST_NAMESPACE")
    if any(
        str(item.get("rights") or "") != "SYNTHETIC_ALLOWED"
        for item in world.host.get("source_versions") or ()
    ):
        raise ValueError("M6_W2_SYNTHETIC_FIXTURE_RIGHTS_MISSING")
    if not version or len(version) > 64 or not text or len(text.encode("utf-8")) > 16384:
        raise ValueError("M6_W2_SYNTHETIC_PAYLOAD_NOT_BOUNDED")


def admit_synthetic_carrier(
    world: WorldRun,
    *,
    source_uri: str,
    version: str,
    text: str,
) -> tuple[str, str, int]:
    """Inject ONLY a fictional fixture carrier, never a real external source."""

    _require_synthetic_test_source(world, source_uri, version, text)
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
        result_provenance=("SYNTHETIC_SELF_ASSERTED_TEST_RECEIPT", f"bytes:{byte_length}"),
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

    if ext.get("rights", "SYNTHETIC_OWNER_GRANT") not in ("SYNTHETIC_ALLOWED", "SYNTHETIC_OWNER_GRANT"):
        raise ValueError("M6_W2_RIGHTS_DENIED_IN_TEST_FIXTURE")
    _require_synthetic_test_source(world, source_uri, version, text)
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
        "reading_extent": "FULL_REQUIRED",
        "independent_f07_rights_attested": False,
        "attestation_status": "SYNTHETIC_SELF_ASSERTED_TEST_ONLY",
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

    sediment_id = f"external-w2-{world.slug}-{stone_id}"
    digest = payload_hash(proposal)
    record = SedimentRecord(
        sediment_id=sediment_id,
        object_type="m6.external_w2_observation",
        version=digest,
        research_object_id=str(world.host["host_id"]),
        payload=proposal,
        payload_hash=digest,
        provenance=(
            "SYNTHETIC_SELF_ASSERTED_RETURN",
            f"return:{return_id}",
            f"request:{request_id}",
            f"source:{carrier_id}@{version}",
            f"f07_digest:{pinned}",
        ),
        source_carrier_refs=(carrier_id,),
        produced_by_thread=f"m6-w2-{world.slug}",
        produced_at_tick=1000,
        produced_in_wave=1,
        produced_by_stone_kind=StoneEventKind.FRONTIER_RETURN,
        epistemic_level=EpistemicLevel.E5,
    )
    world.engine.sediment.deposit(record)

    receipt = {
        "stone_id": stone_id,
        "return_id": return_id,
        "request_id": request_id,
        "status": "ADMITTED",
        "carrier_id": carrier_id,
        "source_version": version,
        "content_sha256": pinned,
        "byte_length": byte_len,
        "sediment_id": sediment_id,
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
    from seshat.fabric_waves.m5_room_carpet import _frontier_probe

    world.oracle_inputs_extra["m6_frontier_probe"] = _frontier_probe(world)
    ledger = ExternalCarrierLedger()
    receipts: list[dict[str, Any]] = []
    if not skip_w2:
        for stone in w2_stones:
            receipt = execute_w2_return(world, stone, ledger=ledger)
            receipts.append(receipt)
            # Deliberate replay probe: the same return cannot mint another
            # carrier, admission or sediment record. This is a synthetic
            # idempotence test, not a second external worker call.
            before_acts = len(world.engine.ledger.activations)
            before_records = len(world.engine.sediment.all_records())
            replay = execute_w2_return(world, stone, ledger=ledger)
            replay["fresh_activations"] = (
                len(world.engine.ledger.activations) - before_acts
            )
            replay["fresh_sediment"] = (
                len(world.engine.sediment.all_records()) - before_records
            )
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
    for cid, ver in declared_source_versions(world.host).items():
        try:
            digest = store.pin_content_digest(cid, pinned_version=ver)
        except ValueError:
            digest = "UNREADABLE"
        out.append({"carrier_id": cid, "version": ver, "content_sha256": digest})
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
