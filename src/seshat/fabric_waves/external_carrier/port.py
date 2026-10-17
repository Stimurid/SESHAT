"""Host-injected ExecutorPort; engine receives only verified normalized returns."""

from __future__ import annotations

from typing import Protocol

from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    ExternalResumeReceipt,
    HostJobReceipt,
    material_hash,
)
from seshat.fabric_waves.external_carrier.ledger import (
    ExternalCarrierLedger,
    compute_host_binding_hash,
)


class ExternalAdmissionError(ValueError):
    """Stable rejection code for forged or mismatched external material."""


class ExecutorPort(Protocol):
    def dispatch(self, need: AgentTaskRequest) -> str:
        """Return opaque host job_id (may be recorded in agent_jobs.jsonl)."""

    def verify_return(
        self,
        *,
        need: AgentTaskRequest,
        evidence: AgentEvidenceReturn,
    ) -> HostJobReceipt:
        """Raise ExternalAdmissionError if host receipt is not authentic."""


def verify_resume_receipt(
    *,
    ledger: ExternalCarrierLedger,
    receipt: ExternalResumeReceipt,
    port: ExecutorPort | None,
) -> AgentEvidenceReturn:
    need = ledger.need_by_id(receipt.request_id)
    if need is None:
        raise ExternalAdmissionError("UNKNOWN_REQUEST_ID")
    if need.run_id != receipt.run_id:
        raise ExternalAdmissionError("RUN_ID_MISMATCH")
    if receipt.request_id != receipt.evidence_return.request_id:
        raise ExternalAdmissionError("REQUEST_ID_CROSS_WIRE")
    if need.idempotency_key != receipt.evidence_return.idempotency_key:
        raise ExternalAdmissionError("IDEMPOTENCY_MISMATCH")
    if need.worker_ref != receipt.evidence_return.worker_ref:
        raise ExternalAdmissionError("WORKER_REF_MISMATCH")
    if receipt.request_id in ledger.stale_request_ids:
        raise ExternalAdmissionError("REQUEST_STALE")
    if need.status.value == "STALE":
        raise ExternalAdmissionError("REQUEST_STALE")
    expected_binding = compute_host_binding_hash(
        request=need,
        host_job=receipt.evidence_return.host_receipt.host_job,
        worker_ref=receipt.evidence_return.worker_ref,
    )
    if receipt.evidence_return.host_receipt.binding_hash != expected_binding:
        raise ExternalAdmissionError("BINDING_HASH_INVALID")
    host_job = receipt.evidence_return.host_receipt.host_job
    if host_job.request_id != need.request_id:
        raise ExternalAdmissionError("JOB_REQUEST_ID_MISMATCH")
    if host_job.host_scope != need.worker_ref.host_scope:
        raise ExternalAdmissionError("HOST_SCOPE_MISMATCH")
    if host_job.result_digest != receipt.evidence_return.result_digest:
        raise ExternalAdmissionError("JOB_RESULT_DIGEST_MISMATCH")
    if need.source_carrier_ids:
        missing = [
            cid
            for cid in need.source_carrier_ids
            if cid not in need.source_versions
        ]
        if missing:
            raise ExternalAdmissionError("SOURCE_VERSION_PIN_MISSING")
        for cid in need.source_versions:
            if cid not in need.source_carrier_ids:
                raise ExternalAdmissionError("SOURCE_SCOPE_MISMATCH")
    if port is None:
        raise ExternalAdmissionError("EXECUTOR_PORT_REQUIRED")
    port.verify_return(need=need, evidence=receipt.evidence_return)
    if receipt.evidence_return.forged_human_decision:
        raise ExternalAdmissionError("FORGED_HUMAN_DECISION_REJECTED")
    if receipt.evidence_return.epistemic_level.value == "E1":
        raise ExternalAdmissionError("E5_ONLY_EXTERNAL_RETURN")
    digest_material = material_hash(receipt.evidence_return.proposal_payload)
    if digest_material != receipt.evidence_return.result_digest:
        raise ExternalAdmissionError("RESULT_DIGEST_MISMATCH")
    if receipt.evidence_return.run_id != need.run_id:
        raise ExternalAdmissionError("EVIDENCE_RUN_ID_MISMATCH")
    try:
        ledger.admit_return(receipt.evidence_return)
    except ValueError as exc:
        if "IDEMPOTENCY_REPLAY" in str(exc):
            raise ExternalAdmissionError("IDEMPOTENCY_REPLAY") from exc
        raise
    return receipt.evidence_return


__all__ = [
    "ExecutorPort",
    "ExternalAdmissionError",
    "verify_resume_receipt",
]
