"""Deterministic FakeHostExecutor for isolated unit tests only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    EpistemicLevel,
    HostJobEvidence,
    HostJobReceipt,
    canonical_json,
    material_hash,
    utc_now_iso,
)
from seshat.fabric_waves.external_carrier.ledger import (
    compute_host_binding_hash,
    dispatch_pins_match,
)
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError


@dataclass(frozen=True)
class _TerminalResult:
    result_digest: str
    method_call_receipt_hash: str
    host_job: HostJobEvidence


class FakeHostExecutor:
    """Signs receipts with a test-only binding secret (not a production host)."""

    def __init__(self, *, host_scope: str, signing_salt: bytes = b"fake-host-test-only") -> None:
        self.host_scope = host_scope
        self._salt = signing_salt
        self._dispatch_json: dict[str, str] = {}
        self._terminals: dict[str, _TerminalResult] = {}

    @staticmethod
    def _job_id_for(need: AgentTaskRequest) -> str:
        return hashlib.sha256(
            (need.request_id + need.idempotency_key).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _freeze_dispatch(need: AgentTaskRequest) -> str:
        return canonical_json(need.model_dump(mode="python"))

    def _load_dispatch(self, job_id: str) -> AgentTaskRequest:
        return AgentTaskRequest.model_validate(json.loads(self._dispatch_json[job_id]))

    def dispatch(self, need: AgentTaskRequest) -> str:
        job_id = self._job_id_for(need)
        frozen = self._freeze_dispatch(need.model_copy(deep=True))
        existing = self._dispatch_json.get(job_id)
        if existing is not None:
            if existing != frozen:
                raise ExternalAdmissionError("HOST_DISPATCH_JOB_ID_COLLISION")
            return job_id
        self._dispatch_json[job_id] = frozen
        return job_id

    def authoritative_dispatch(self, *, job_id: str) -> AgentTaskRequest:
        if job_id not in self._dispatch_json:
            raise ExternalAdmissionError("UNKNOWN_JOB_ID")
        return self._load_dispatch(job_id)

    def synthesize_return(
        self,
        *,
        need: AgentTaskRequest,
        job_id: str,
        proposal: dict[str, Any],
    ) -> AgentEvidenceReturn:
        if job_id not in self._dispatch_json:
            raise ExternalAdmissionError("UNKNOWN_JOB_ID")
        bound = self._load_dispatch(job_id)
        if bound.request_id != need.request_id:
            raise ExternalAdmissionError("JOB_REQUEST_MISMATCH")
        now = utc_now_iso()
        digest = material_hash(proposal)
        method_call_receipt_hash = hashlib.sha256(job_id.encode()).hexdigest()
        host_job = HostJobEvidence(
            job_id=job_id,
            host_scope=self.host_scope,
            request_id=bound.request_id,
            started_at=now,
            ended_at=now,
            result_provenance=("FAKE_HOST_SYNTHETIC",),
            result_digest=digest,
            allowed_source_rights=bound.source_rights,
        )
        binding_hash = compute_host_binding_hash(
            request=bound,
            host_job=host_job,
            worker_ref=bound.worker_ref,
        )
        receipt = HostJobReceipt(
            receipt_id=f"rcpt-{job_id}",
            authorized=True,
            host_job=host_job,
            binding_hash=binding_hash,
            worker_ref=bound.worker_ref,
        )
        self._terminals[job_id] = _TerminalResult(
            result_digest=digest,
            method_call_receipt_hash=method_call_receipt_hash,
            host_job=host_job.model_copy(deep=True),
        )
        return AgentEvidenceReturn(
            request_id=need.request_id,
            idempotency_key=need.idempotency_key,
            run_id=need.run_id,
            worker_ref=need.worker_ref,
            epistemic_level=EpistemicLevel.E5,
            proposal_payload=proposal,
            source_claim_refs=tuple(need.source_carrier_ids),
            method_call_receipt_hash=method_call_receipt_hash,
            result_digest=digest,
            host_receipt=receipt,
        )

    def verify_return(
        self,
        *,
        need: AgentTaskRequest,
        evidence: AgentEvidenceReturn,
    ) -> HostJobReceipt:
        job_id = evidence.host_receipt.host_job.job_id
        if job_id not in self._dispatch_json:
            raise ExternalAdmissionError("UNISSUED_HOST_JOB")
        if not evidence.host_receipt.authorized:
            raise ExternalAdmissionError("FORGED_AUTHORIZED_FLAG")
        bound = self._load_dispatch(job_id)
        if not dispatch_pins_match(need, bound):
            raise ExternalAdmissionError("LEDGER_DISPATCH_PIN_MISMATCH")
        if evidence.host_receipt.host_job.request_id != bound.request_id:
            raise ExternalAdmissionError("JOB_REQUEST_ID_MISMATCH")
        if evidence.host_receipt.worker_ref != bound.worker_ref:
            raise ExternalAdmissionError("WORKER_REF_MISMATCH")
        if bound.idempotency_key != need.idempotency_key:
            raise ExternalAdmissionError("JOB_IDEMPOTENCY_MISMATCH")
        if bound.canonical_input_hash != need.canonical_input_hash:
            raise ExternalAdmissionError("JOB_INPUT_HASH_MISMATCH")
        terminal = self._terminals.get(job_id)
        if terminal is None:
            raise ExternalAdmissionError("TERMINAL_RESULT_MISSING")
        if evidence.result_digest != terminal.result_digest:
            raise ExternalAdmissionError("FORGED_TERMINAL_RESULT")
        if evidence.method_call_receipt_hash != terminal.method_call_receipt_hash:
            raise ExternalAdmissionError("FORGED_METHOD_RECEIPT")
        if evidence.host_receipt.host_job.allowed_source_rights != bound.source_rights:
            raise ExternalAdmissionError("HOST_JOB_RIGHTS_ESCALATION")
        if evidence.host_receipt.host_job != terminal.host_job:
            raise ExternalAdmissionError("FORGED_HOST_JOB_TERMINAL")
        expected = compute_host_binding_hash(
            request=bound,
            host_job=evidence.host_receipt.host_job,
            worker_ref=bound.worker_ref,
        )
        if evidence.host_receipt.binding_hash != expected:
            raise ExternalAdmissionError("FAKE_HOST_SIGNATURE_INVALID")
        return evidence.host_receipt


__all__ = ["FakeHostExecutor"]
