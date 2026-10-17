"""Scoped durable WAITING_EXTERNAL checkpoint (process restart; not Phase B live host)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from seshat.fabric_waves.external_carrier.contracts import AgentTaskRequest, material_hash
from seshat.fabric_waves.external_carrier.ledger import ExternalCarrierLedger


def _ledger_checkpoint_payload(ledger: ExternalCarrierLedger) -> dict[str, Any]:
    data = ledger.model_dump(mode="python")
    data["admitted_idempotency_keys"] = sorted(data["admitted_idempotency_keys"])
    data["stale_request_ids"] = sorted(data["stale_request_ids"])
    return data


class ExternalWaitCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "external_wait_checkpoint_v1"
    run_id: str
    request_id: str
    dispatch_snapshot: AgentTaskRequest
    ledger: ExternalCarrierLedger
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        request_id: str,
        dispatch_snapshot: AgentTaskRequest,
        ledger: ExternalCarrierLedger,
    ) -> ExternalWaitCheckpoint:
        body = {
            "schema_version": "external_wait_checkpoint_v1",
            "run_id": run_id,
            "request_id": request_id,
            "dispatch_snapshot": dispatch_snapshot.model_dump(mode="python"),
            "ledger": _ledger_checkpoint_payload(ledger),
        }
        return cls(
            run_id=run_id,
            request_id=request_id,
            dispatch_snapshot=dispatch_snapshot.model_copy(deep=True),
            ledger=ledger.model_copy(deep=True),
            checksum=material_hash(body),
        )

    def verify_checksum(self) -> None:
        body = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "dispatch_snapshot": self.dispatch_snapshot.model_dump(mode="python"),
            "ledger": _ledger_checkpoint_payload(self.ledger),
        }
        if material_hash(body) != self.checksum:
            raise ValueError("WAIT_CHECKPOINT_CHECKSUM_INVALID")


def _checkpoint_document(checkpoint: ExternalWaitCheckpoint) -> dict[str, Any]:
    data = checkpoint.model_dump(mode="python")
    data["ledger"] = _ledger_checkpoint_payload(checkpoint.ledger)
    return data


def write_wait_checkpoint(path: Path, checkpoint: ExternalWaitCheckpoint) -> None:
    checkpoint.verify_checksum()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        _checkpoint_document(checkpoint),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    readback = json.loads(path.read_text(encoding="utf-8"))
    restored = ExternalWaitCheckpoint.model_validate(readback)
    restored.verify_checksum()


def load_wait_checkpoint(path: Path) -> ExternalWaitCheckpoint:
    checkpoint = ExternalWaitCheckpoint.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )
    checkpoint.verify_checksum()
    return checkpoint


__all__ = [
    "ExternalWaitCheckpoint",
    "load_wait_checkpoint",
    "write_wait_checkpoint",
]
