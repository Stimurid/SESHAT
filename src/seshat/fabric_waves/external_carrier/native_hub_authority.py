"""Consumer of independent, host-issued native Hub attestations.

There is deliberately NO signing/publishing function here. A separately authorized
host component must verify immutable issuance provenance and publish certificates in
its protected ledger. Merely copying spec/status/receipt files does not qualify.
The host provisions the ledger/root/key; the unprivileged caller cannot choose them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from seshat.fabric_waves.external_carrier.contracts import material_hash
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError, HostIntegrityKey, read_file_under, sha256_hex,
)
from seshat.fabric_waves.external_carrier.hub_protocol import (
    HubJobRecord, HubJobSpec, HubIssuerRegistry, parse_hub_record,
)


def _object(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HostBoundaryError("NATIVE_ORIGINAL_INVALID") from None
    if not isinstance(value, dict):
        raise HostBoundaryError("NATIVE_ORIGINAL_INVALID")
    return value


def _time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result
    except (ValueError, AttributeError):
        raise HostBoundaryError("NATIVE_TIME_INVALID") from None


@dataclass(frozen=True)
class NativeHubAuthority:
    jobs_root: Path
    ledger_root: Path
    attestation_key: HostIntegrityKey
    hub_instance_id: str
    client: str
    project_target: str

    def _certificate(self, spec: HubJobSpec, suffix: str) -> dict:
        _, raw = read_file_under(self.ledger_root, f"{spec.host_job_id}.{suffix}.json",
                                 max_bytes=64_000)
        envelope = _object(raw)
        body = envelope.get("body")
        if not isinstance(body, dict) or not self.attestation_key.verify(
            material_hash(body), envelope.get("mac", "")
        ):
            raise HostBoundaryError("NATIVE_ATTESTATION_FORGED")
        if (body.get("schema") != f"seshat.native_hub.{suffix}.v1"
                or body.get("host_job_id") != spec.host_job_id
                or body.get("original_spec_sha256") != spec.spec_sha256()
                or body.get("hub_instance_id") != self.hub_instance_id):
            raise HostBoundaryError("NATIVE_ATTESTATION_BINDING_MISMATCH")
        return body

    def admission(self, spec: HubJobSpec, *, nonce: str, attempted_at: str,
                  native_job_id: str | None = None) -> dict:
        body = self._certificate(spec, "admission")
        jid = body.get("native_job_id")
        if not isinstance(jid, str) or not re.fullmatch(r"jx-[0-9a-f]{12}", jid):
            raise HostBoundaryError("NATIVE_JOB_ID_INVALID")
        if native_job_id is not None and jid != native_job_id:
            raise HostBoundaryError("NATIVE_JOB_ID_MISMATCH")
        if body.get("nonce") != nonce or _time(body.get("issued_at")) < _time(attempted_at):
            raise HostBoundaryError("NATIVE_ISSUANCE_NOT_AFTER_CLAIM")
        _, raw = read_file_under(self.jobs_root, Path(jid) / "spec.json", max_bytes=128_000)
        native = _object(raw)
        if sha256_hex(raw) != body.get("native_spec_sha256"):
            raise HostBoundaryError("NATIVE_ORIGINAL_DIGEST_MISMATCH")
        expected = {
            "schema": "AIYE_LOCAL_EXEC_TASK_v0.1", "job_id": jid,
            "ticket": spec.ticket, "role": spec.role, "mode": "audit",
            "prompt_sha256": spec.prompt_sha256, "client": self.client,
            "project_target": self.project_target, "agent": spec.provider,
            "model": spec.model, "max_seconds": spec.max_time_seconds,
        }
        if any(native.get(k) != v for k, v in expected.items()):
            raise HostBoundaryError("NATIVE_ORIGINAL_BINDING_MISMATCH")
        if native.get("allow_edits") or native.get("retry_of") or native.get("after"):
            raise HostBoundaryError("NATIVE_ORIGINAL_NOT_INDEPENDENT")
        if _time(native.get("created_at")) < _time(attempted_at):
            raise HostBoundaryError("NATIVE_ISSUANCE_NOT_AFTER_CLAIM")
        return body

    def terminal(self, spec: HubJobSpec, admission: dict,
                 registry: HubIssuerRegistry) -> tuple[HubJobRecord, bytes]:
        body = self._certificate(spec, "terminal")
        jid = admission["native_job_id"]
        if (body.get("native_job_id") != jid
                or body.get("admission_sha256") != material_hash(admission)):
            raise HostBoundaryError("NATIVE_TERMINAL_BINDING_MISMATCH")
        originals = {}
        hashes = body.get("original_sha256", {})
        for name in ("spec.json", "status.json", "receipt.json", "stdout.log"):
            _, raw = read_file_under(self.jobs_root, Path(jid) / name, max_bytes=1_000_000)
            if sha256_hex(raw) != hashes.get(name):
                raise HostBoundaryError("NATIVE_ORIGINAL_DIGEST_MISMATCH")
            originals[name] = raw
        if hashes["spec.json"] != admission["native_spec_sha256"]:
            raise HostBoundaryError("NATIVE_ORIGINAL_DIGEST_MISMATCH")
        status = _object(originals["status.json"])
        receipt = _object(originals["receipt.json"])
        if (status.get("job_id") != jid or receipt.get("job_id") != jid
                or receipt.get("schema") != "AIYE_LOCAL_EXEC_RECEIPT_v0.1"
                or status.get("state") != receipt.get("state")):
            raise HostBoundaryError("NATIVE_TERMINAL_BINDING_MISMATCH")
        states = {"SUCCEEDED": "completed", "FAILED": "failed",
                  "CANCELLED": "cancelled", "TIMED_OUT": "timeout",
                  "INTERRUPTED": "failed"}
        record = parse_hub_record(body.get("record", {}))
        for key, expected in {
            "agent": spec.provider, "model": spec.model, "role": spec.role,
            "ticket": spec.ticket, "mode": "audit", "prompt_sha256": spec.prompt_sha256,
            "client": self.client, "exit_code": record.exit_code,
            "started_at": record.started_at, "ended_at": record.ended_at,
        }.items():
            if receipt.get(key) != expected:
                raise HostBoundaryError("NATIVE_TERMINAL_BINDING_MISMATCH")
        if (states.get(receipt.get("state")) != record.status.value
                or record.hub_instance_id != self.hub_instance_id
                or _time(record.started_at) < _time(admission["issued_at"])
                or _time(record.ended_at) < _time(record.started_at)):
            raise HostBoundaryError("NATIVE_TERMINAL_BINDING_MISMATCH")
        # Native usage_tokens can be absent; the independent issuer must supply
        # verified bounded usage/cost, never infer zero from missing telemetry.
        if body.get("usage_verified") is not True:
            raise HostBoundaryError("NATIVE_USAGE_UNVERIFIED")
        if registry.authentication_mode(record.issuer_id) != "HMAC_VERIFIED":
            raise HostBoundaryError("NATIVE_ISSUER_AUTH_REQUIRED")
        effective = spec.model_copy(update={"hub_job_id": jid})
        registry.verify_record(record=record, spec=effective, stdout=originals["stdout.log"])
        return record, originals["stdout.log"]
