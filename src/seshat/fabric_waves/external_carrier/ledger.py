"""Durable external request / job / return ledger (exportable, no secrets)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    ExternalRequestStatus,
    HostJobEvidence,
    HostJobReceipt,
    WorkerCarrierRef,
    material_hash,
)


class ExternalCarrierLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_needs: list[AgentTaskRequest] = Field(default_factory=list)
    agent_jobs: list[dict[str, Any]] = Field(default_factory=list)
    evidence_returns: list[AgentEvidenceReturn] = Field(default_factory=list)
    admitted_idempotency_keys: set[str] = Field(default_factory=set)
    stale_request_ids: set[str] = Field(default_factory=set)

    def register_need(self, need: AgentTaskRequest) -> None:
        if any(item.request_id == need.request_id for item in self.research_needs):
            raise ValueError(f"duplicate request_id {need.request_id!r}")
        self.research_needs.append(need.model_copy(deep=True))

    def mark_stale(self, request_id: str) -> None:
        self.stale_request_ids.add(request_id)
        for idx, need in enumerate(self.research_needs):
            if need.request_id == request_id:
                self.research_needs[idx] = need.model_copy(
                    update={"status": ExternalRequestStatus.STALE}
                )
                break

    def admit_return(self, evidence: AgentEvidenceReturn) -> None:
        key = evidence.idempotency_key
        if key in self.admitted_idempotency_keys:
            raise ValueError("IDEMPOTENCY_REPLAY")
        self.admitted_idempotency_keys.add(key)
        self.evidence_returns.append(evidence.model_copy(deep=True))
        for idx, need in enumerate(self.research_needs):
            if need.request_id == evidence.request_id:
                self.research_needs[idx] = need.model_copy(
                    update={"status": ExternalRequestStatus.RETURN_ADMITTED}
                )
                break

    def need_by_id(self, request_id: str) -> AgentTaskRequest | None:
        for need in self.research_needs:
            if need.request_id == request_id:
                return need
        return None

    def export_jsonl(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        needs_path = output_dir / "research_needs.jsonl"
        jobs_path = output_dir / "agent_jobs.jsonl"
        returns_path = output_dir / "evidence_returns.jsonl"
        needs_path.write_text(
            "\n".join(
                json.dumps(n.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
                for n in self.research_needs
            )
            + ("\n" if self.research_needs else ""),
            encoding="utf-8",
        )
        jobs_path.write_text(
            "\n".join(json.dumps(j, ensure_ascii=False, sort_keys=True) for j in self.agent_jobs)
            + ("\n" if self.agent_jobs else ""),
            encoding="utf-8",
        )
        returns_path.write_text(
            "\n".join(
                json.dumps(r.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
                for r in self.evidence_returns
            )
            + ("\n" if self.evidence_returns else ""),
            encoding="utf-8",
        )

    def export_resume_receipt(self, output_dir: Path, receipt: dict[str, Any]) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "resume_receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )


def compute_host_binding_hash(
    *,
    request: AgentTaskRequest,
    host_job: HostJobEvidence,
    worker_ref: WorkerCarrierRef,
) -> str:
    return material_hash(
        {
            "request_id": request.request_id,
            "run_id": request.run_id,
            "wave_id": request.wave_id,
            "thread_id": request.thread_id,
            "node_id": request.node_id,
            "method_body_ref": request.method_body_ref.model_dump(mode="python"),
            "source_carrier_ids": list(request.source_carrier_ids),
            "source_versions": dict(request.source_versions),
            "source_rights": request.source_rights.value,
            "expected_output_schema": request.expected_output_schema,
            "admissible_evidence_classes": list(request.admissible_evidence_classes),
            "worker_ref": worker_ref.model_dump(mode="python"),
            "host_job": host_job.model_dump(mode="python"),
            "canonical_input_hash": request.canonical_input_hash,
        }
    )


def dispatch_pins_match(
    ledger_need: AgentTaskRequest,
    host_need: AgentTaskRequest,
) -> bool:
    """Host dispatch snapshot is authoritative; ledger row must not drift after dispatch."""

    return (
        ledger_need.request_id == host_need.request_id
        and ledger_need.idempotency_key == host_need.idempotency_key
        and ledger_need.run_id == host_need.run_id
        and ledger_need.wave_id == host_need.wave_id
        and ledger_need.thread_id == host_need.thread_id
        and ledger_need.node_id == host_need.node_id
        and ledger_need.method_body_ref == host_need.method_body_ref
        and ledger_need.worker_ref == host_need.worker_ref
        and ledger_need.source_carrier_ids == host_need.source_carrier_ids
        and ledger_need.source_versions == host_need.source_versions
        and ledger_need.canonical_input_hash == host_need.canonical_input_hash
        and ledger_need.source_rights == host_need.source_rights
        and ledger_need.expected_output_schema == host_need.expected_output_schema
        and ledger_need.admissible_evidence_classes == host_need.admissible_evidence_classes
    )


__all__ = [
    "ExternalCarrierLedger",
    "compute_host_binding_hash",
    "dispatch_pins_match",
]
