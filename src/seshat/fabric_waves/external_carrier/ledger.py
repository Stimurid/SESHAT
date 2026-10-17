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
            "worker_ref": worker_ref.model_dump(mode="python"),
            "host_job": host_job.model_dump(mode="python"),
            "canonical_input_hash": request.canonical_input_hash,
        }
    )


__all__ = ["ExternalCarrierLedger", "compute_host_binding_hash"]
