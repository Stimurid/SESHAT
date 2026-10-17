"""Two-host synthetic lab configs with external research carrier threads."""

from __future__ import annotations

import hashlib
from typing import Any

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.carpet_hosts import (
    _answer,
    _concepts,
    _evidence,
    _question,
    _read_carrier,
)
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef, StoneEventKind
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.external_carrier.contracts import (
    AgentTaskRequest,
    ExternalWait,
    WorkerCarrierRef,
    material_hash,
    utc_now_iso,
)
from seshat.fabric_waves.external_carrier.ledger import ExternalCarrierLedger
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult
from seshat.fabric_waves.scenarios import bundle, engine_for, output, source_store
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash


def _worker_ref(host_id: str) -> WorkerCarrierRef:
    return WorkerCarrierRef(
        carrier_id=f"worker-lab-{host_id}",
        host_scope=f"synthetic-lab-{host_id}",
        capability_handle="external-research-v1",
    )


def _build_task_request(
    inv: BodyInvocation,
    *,
    host_id: str,
    alpha_evidence_id: str,
    beta_evidence_id: str,
) -> AgentTaskRequest:
    states = inv.carried_payload["candidate_sediments"]
    alpha = next(r for r in states if r.sediment_id == alpha_evidence_id)
    beta = next(r for r in states if r.sediment_id == beta_evidence_id)
    run_id = str(inv.carried_payload["run_id"])
    wave_id = str(inv.carried_payload["wave_id"])
    topic = str(inv.carried_payload.get("topic", f"{host_id}-external-gap"))
    query = str(inv.carried_payload.get("query", "resolve divergent branch signals"))
    input_material = {
        "alpha_version": alpha.version,
        "beta_version": beta.version,
        "alpha_signal": alpha.payload.get("signal"),
        "beta_signal": beta.payload.get("signal"),
        "topic": topic,
        "query": query,
    }
    canonical = material_hash(input_material)
    request_id = f"rn:{host_id}:{canonical[:12]}"
    idem = hashlib.sha256(f"{run_id}:{request_id}:{canonical}".encode()).hexdigest()
    carriers = tuple(inv.carried_payload.get("carriers", ()))
    versions = {}
    if inv.carried_payload.get("source_access_manifest"):
        manifest = inv.carried_payload["source_access_manifest"]
        for receipt in getattr(manifest, "receipts", ()) or ():
            versions[receipt.source_id] = receipt.source_version
    return AgentTaskRequest(
        request_id=request_id,
        idempotency_key=idem,
        run_id=run_id,
        wave_id=wave_id,
        thread_id=inv.thread_id,
        node_id=inv.node_id,
        method_body_ref=inv.method_body_ref,
        worker_ref=_worker_ref(host_id),
        source_carrier_ids=carriers,
        source_versions=versions,
        canonical_input_hash=canonical,
        admissible_evidence_classes=("E5", "structured_hypothesis"),
        source_rights=RawAccessPolicy.DRILLBACK,
        expected_output_schema="external.hypothesis.v1",
        question_topic=topic,
        question_query=query,
        created_at=utc_now_iso(),
        provenance=("EXTERNAL_GAP_DETECTED",),
    )


def _external_gap_request(
    inv: BodyInvocation,
    *,
    host_id: str,
    alpha_evidence_id: str,
    beta_evidence_id: str,
) -> BodyResult:
    states = inv.carried_payload["candidate_sediments"]
    alpha = next(r for r in states if r.sediment_id == alpha_evidence_id)
    beta = next(r for r in states if r.sediment_id == beta_evidence_id)
    if alpha.payload.get("signal") == beta.payload.get("signal"):
        return BodyResult(aporia="NO_EXTERNAL_GAP")
    request = _build_task_request(
        inv,
        host_id=host_id,
        alpha_evidence_id=alpha_evidence_id,
        beta_evidence_id=beta_evidence_id,
    )
    return BodyResult(
        external_wait=ExternalWait(request=request),
        notes=(f"external_wait:{request.request_id}",),
    )


def _reconcile_with_external(inv: BodyInvocation) -> BodyResult:
    states = inv.carried_payload["candidate_sediments"]
    by_branch = {
        record.payload["branch"]: record
        for record in states
        if isinstance(record.payload.get("branch"), str)
    }
    integrate = next(
        (r for r in states if r.object_type == "external.integrated"),
        None,
    )
    alpha = by_branch.get("alpha")
    beta = by_branch.get("beta")
    if alpha is None or beta is None:
        return BodyResult(aporia="MISSING_EVIDENCE_BRANCH")
    divergent = alpha.payload["signal"] != beta.payload["signal"]
    body: dict[str, Any] = {
        "alpha_signal": alpha.payload["signal"],
        "beta_signal": beta.payload["signal"],
        "divergent": divergent,
        "alpha_version": alpha.version,
        "beta_version": beta.version,
    }
    if integrate is not None:
        body["external_hypothesis"] = integrate.payload.get("hypothesis")
        body["external_integrate_version"] = integrate.version
    return output(inv, body)


def _integrate_external(inv: BodyInvocation, *, host_id: str) -> BodyResult:
    proposal = inv.carried_payload["candidate_sediments"][0]
    if proposal.epistemic_level != EpistemicLevel.E5:
        return BodyResult(aporia="EXTERNAL_INTEGRATE_REQUIRES_E5")
    payload = {
        "host_id": host_id,
        "hypothesis": proposal.payload.get("hypothesis"),
        "proposal_version": proposal.version,
        "grounded": True,
    }
    digest = payload_hash(payload)
    record = SedimentRecord(
        sediment_id=inv.carried_payload["output_sediment_id"],
        object_type="external.integrated",
        version=digest,
        research_object_id=inv.carried_payload.get("research_object_id", inv.thread_id),
        payload=payload,
        payload_hash=digest,
        provenance=("EXTERNAL_INTEGRATE", f"proposal={proposal.sediment_id}"),
        method_body_refs=(inv.method_body_ref,),
        source_carrier_refs=proposal.source_carrier_refs,
        epistemic_level=EpistemicLevel.E5,
        read_dependencies=inv.consumed_sediment_ids,
        produced_by_thread=inv.thread_id,
        produced_at_tick=inv.tick,
        produced_in_wave=inv.wave_index,
        produced_by_stone_kind=inv.stone_kind,
    )
    return BodyResult(produced_sediments=(record,))


def _host_engine(
    *,
    host_id: str,
    carrier_alpha: str,
    carrier_beta: str,
    alpha_text: str,
    beta_text: str,
    alpha_signal: str,
    beta_signal: str,
    default_topic: str,
    revisions: dict | None = None,
) -> WaveEngine:
    obs_a = f"obs-{host_id}-alpha"
    obs_b = f"obs-{host_id}-beta"
    ev_a = f"evidence-alpha-{host_id}"
    ev_b = f"evidence-beta-{host_id}"
    ext = f"external-research-{host_id}"
    integrate = f"external-integrate-{host_id}"
    proposal_id = f"external-proposal-{host_id}"
    bundles = [
        bundle(obs_a, lambda inv: _read_carrier(inv, branch="alpha"), source=carrier_alpha),
        bundle(obs_b, lambda inv: _read_carrier(inv, branch="beta"), source=carrier_beta),
        bundle(
            f"question-{host_id}",
            lambda inv: _question(inv, default_topic=default_topic),
            accepts_operator_query=True,
        ),
        bundle(f"concepts-{host_id}", _concepts, reads=(f"question-{host_id}",)),
        bundle(
            ev_a,
            lambda inv: _evidence(inv, branch="alpha", signal_key=alpha_signal),
            reads=(f"concepts-{host_id}", obs_a),
        ),
        bundle(
            ev_b,
            lambda inv: _evidence(inv, branch="beta", signal_key=beta_signal),
            reads=(f"concepts-{host_id}", obs_b),
        ),
        bundle(
            ext,
            lambda inv: _external_gap_request(
                inv,
                host_id=host_id,
                alpha_evidence_id=ev_a,
                beta_evidence_id=ev_b,
            ),
            reads=(ev_a, ev_b),
        ),
        bundle(
            integrate,
            lambda inv: _integrate_external(inv, host_id=host_id),
            reads=(proposal_id,),
            kinds=(StoneEventKind.SEDIMENT_AVAILABLE,),
            output_sediment_type="external.integrated",
        ),
        bundle(
            f"reconcile-{host_id}",
            _reconcile_with_external,
            reads=(ev_a, ev_b, integrate),
        ),
        bundle(f"answer-{host_id}", _answer, reads=(f"reconcile-{host_id}",)),
    ]
    store = source_store(
        {carrier_alpha: alpha_text, carrier_beta: beta_text},
        revisions=revisions,
    )
    engine = engine_for(bundles, store)
    engine.external_ledger = ExternalCarrierLedger()
    engine.executor_port = None
    engine.external_proposal_sediment_id = proposal_id
    return engine


def campus_external_host_engine() -> WaveEngine:
    revision = carrier(
        carrier_id="campus-branch-alpha",
        version="2",
        text="revised lab telemetry: utilization index 79%",
    )
    return _host_engine(
        host_id="campus",
        carrier_alpha="campus-branch-alpha",
        carrier_beta="campus-branch-beta",
        alpha_text="lab telemetry: utilization index 82%",
        beta_text="facilities audit memo: utilization index 64%",
        alpha_signal="82",
        beta_signal="64",
        default_topic="campus-facility-utilization",
        revisions={("campus-branch-alpha", "1", "2"): revision},
    )


def meteorology_external_host_engine() -> WaveEngine:
    return _host_engine(
        host_id="met",
        carrier_alpha="met-sensor-north",
        carrier_beta="met-sensor-south",
        alpha_text="north tower anemometer: gust 41 kt, icing risk moderate",
        beta_text="south maintenance log: gust 28 kt, icing risk low",
        alpha_signal="41",
        beta_signal="28",
        default_topic="winter-operations-wind-icing",
    )


__all__ = [
    "campus_external_host_engine",
    "meteorology_external_host_engine",
]
