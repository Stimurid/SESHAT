"""Portable external worker-carrier contracts (host-neutral, no provider names)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef


def canonical_json(value: Any) -> str:
    def default(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="python", exclude_none=False)
        raise TypeError(type(item).__name__)

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=default
    )


def material_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ExternalRequestStatus(StrEnum):
    PENDING = "PENDING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    RETURN_ADMITTED = "RETURN_ADMITTED"
    STALE = "STALE"
    BLOCKED = "BLOCKED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


class WorkerCarrierRef(BaseModel):
    """Host-injected executor identity; generic engine never names a provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    carrier_id: str = Field(min_length=1)
    host_scope: str = Field(min_length=1)
    capability_handle: str = Field(min_length=1)


class AgentTaskRequest(BaseModel):
    """Durable external research / agent task (ResearchNeed machine shape)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    wave_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    method_body_ref: MethodBodyRef
    worker_ref: WorkerCarrierRef
    source_carrier_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_versions: dict[str, str] = Field(default_factory=dict)
    canonical_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    admissible_evidence_classes: tuple[str, ...] = Field(default_factory=tuple)
    source_rights: RawAccessPolicy = RawAccessPolicy.DRILLBACK
    expected_output_schema: str = Field(min_length=1)
    priority: int = Field(default=0, ge=0)
    time_budget_seconds: int = Field(default=3600, ge=1)
    token_budget: int = Field(default=8192, ge=1)
    status: ExternalRequestStatus = ExternalRequestStatus.WAITING_EXTERNAL
    created_at: str = Field(min_length=1)
    question_topic: str = ""
    question_query: str = ""
    provenance: tuple[str, ...] = Field(default_factory=tuple)


ResearchNeed = AgentTaskRequest


class ExternalWait(BaseModel):
    """Body signal: thread cannot proceed until host-verified external return."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: AgentTaskRequest
    wait_reason: str = "EXTERNAL_RESEARCH_REQUIRED"


class HostJobEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    host_scope: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    result_provenance: tuple[str, ...] = Field(default_factory=tuple)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_source_rights: RawAccessPolicy = RawAccessPolicy.DRILLBACK


class HostJobReceipt(BaseModel):
    """Trusted host export; untrusted payloads cannot set authorized=True alone."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(min_length=1)
    authorized: bool
    host_job: HostJobEvidence
    binding_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker_ref: WorkerCarrierRef


class AgentEvidenceReturn(BaseModel):
    """Normalized E5 candidate from verified host adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    worker_ref: WorkerCarrierRef
    epistemic_level: EpistemicLevel = EpistemicLevel.E5
    proposal_payload: dict[str, Any] = Field(default_factory=dict)
    source_claim_refs: tuple[str, ...] = Field(default_factory=tuple)
    method_call_receipt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    host_receipt: HostJobReceipt
    forged_human_decision: dict[str, Any] | None = None


class ExternalResumeReceipt(BaseModel):
    """Admission envelope for continuing a WAITING_EXTERNAL run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    evidence_return: AgentEvidenceReturn
    resume_at_tick: int = Field(ge=0, default=0)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "AgentEvidenceReturn",
    "AgentTaskRequest",
    "ExternalRequestStatus",
    "ExternalResumeReceipt",
    "ExternalWait",
    "HostJobEvidence",
    "HostJobReceipt",
    "ResearchNeed",
    "WorkerCarrierRef",
    "canonical_json",
    "material_hash",
    "utc_now_iso",
]
