"""HOST-ONLY normalized AORUS Hub job types, issuer registry and record verification.

The normalized record schema below is an ADAPTER-LEVEL contract. Mapping a native
``aiye-exec`` / Hub receipt onto it has NOT been verified against CALLER_PROTOCOL.md in this
authoring run (the file was outside the permitted workspace). See docs/PHASE_B_HOST_ADAPTER.md.

Trust model: a Hub record is untrusted transport material until the host registry pins
(issuer, Hub instance, provider/model allow-list, optional host-private HMAC) AND the host's own
persisted original job spec digest AND the stdout hash/bytes all agree. The unkeyed
``compute_host_binding_hash`` is correlation only and is never used as authentication here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from seshat.fabric_waves.external_carrier.contracts import material_hash
from seshat.fabric_waves.external_carrier.host_security import (
    ALLOWED_HUB_ROLES,
    HostBoundaryError,
    HostIntegrityKey,
    sha256_hex,
)

HUB_SPEC_SCHEMA = "aiye.hub.job_spec.normalized.v1"
HUB_RECORD_SCHEMA = "aiye.hub.job_record.normalized.v1"


class HubJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


NON_TERMINAL_STATUSES: frozenset[HubJobStatus] = frozenset(
    {HubJobStatus.QUEUED, HubJobStatus.RUNNING}
)


class HubJobSpec(BaseModel):
    """Original job spec the HOST persisted before any submission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: str = HUB_SPEC_SCHEMA
    host_job_id: str = Field(min_length=1)
    hub_job_id: str = Field(min_length=1)
    ticket: str = Field(min_length=1)
    decision: str = "recommend"
    role: str = Field(min_length=1)
    mode: str = "read-only"
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_tokens: int = Field(ge=1)
    max_time_seconds: int = Field(ge=1)
    max_cost_cents: int = Field(ge=0)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_pin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def spec_sha256(self) -> str:
        return material_hash(self.model_dump(mode="python"))

    def assert_static_policy(self) -> None:
        if self.decision != "recommend":
            raise HostBoundaryError("HUB_SPEC_DECISION_NOT_RECOMMEND")
        if self.mode != "read-only":
            raise HostBoundaryError("HUB_SPEC_MODE_NOT_READ_ONLY")
        if self.role not in ALLOWED_HUB_ROLES:
            raise HostBoundaryError("HUB_SPEC_ROLE_DENIED")


class HubJobRecord(BaseModel):
    """Normalized terminal/progress record read back from the Hub (untrusted until verified)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: str = HUB_RECORD_SCHEMA
    job_id: str = Field(min_length=1)
    ticket: str = Field(min_length=1)
    status: HubJobStatus
    decision: str = ""
    role: str = ""
    mode: str = ""
    provider: str = ""
    model: str = ""
    spec_sha256: str = ""
    stdout_sha256: str = ""
    stdout_len: int = Field(default=0, ge=0)
    exit_code: int | None = None
    started_at: str = ""
    ended_at: str = ""
    receipt_id: str = ""
    issuer_id: str = ""
    hub_instance_id: str = ""
    cost_cents: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    issuer_mac: str = ""

    def mac_material(self) -> str:
        body = self.model_dump(mode="json")
        body.pop("issuer_mac", None)
        return material_hash(body)

    def receipt_sha256(self) -> str:
        """Digest of the full original record (including any MAC) for host receipts."""

        return material_hash(self.model_dump(mode="json"))


def parse_hub_record(data: Mapping[str, object]) -> HubJobRecord:
    try:
        record = HubJobRecord.model_validate(dict(data))
        for value in record.model_dump(mode="python").values():
            if isinstance(value, str):
                value.encode("utf-8")  # lone surrogates cannot be hashed or stored
    except (ValidationError, UnicodeEncodeError):
        raise HostBoundaryError("HUB_RECORD_SCHEMA_INVALID") from None
    return record


class HubTransportError(ValueError):
    """Typed transport outcome. args[0] is PROVIDER_UNAVAILABLE or BUDGET_EXHAUSTED."""

    @property
    def code(self) -> str:
        return str(self.args[0])


class HubSubmitter(Protocol):
    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        """Submit one job via the official Hub path. Raise HubTransportError for typed blocks."""


class HubFetcher(Protocol):
    def fetch(self, *, hub_job_id: str) -> tuple[HubJobRecord, bytes] | None:
        """Return (record, stdout bytes) or None when no record exists yet."""


@dataclass(frozen=True)
class HubIssuer:
    issuer_id: str
    hub_instance_id: str
    allowed_providers: frozenset[str]
    allowed_models: frozenset[str]
    mac_key: HostIntegrityKey | None = field(default=None, repr=False)


class HubIssuerRegistry:
    """Independently held issuer evidence. Without a MAC key the check is pins-only."""

    def __init__(self, issuers: list[HubIssuer]) -> None:
        self._issuers = {item.issuer_id: item for item in issuers}
        if len(self._issuers) != len(issuers):
            raise HostBoundaryError("HUB_REGISTRY_DUPLICATE_ISSUER")

    def issuer(self, issuer_id: str) -> HubIssuer | None:
        return self._issuers.get(issuer_id)

    def provider_model_allowed(self, provider: str, model: str) -> bool:
        return any(
            provider in item.allowed_providers and model in item.allowed_models
            for item in self._issuers.values()
        )

    def authentication_mode(self, issuer_id: str) -> str:
        item = self._issuers.get(issuer_id)
        if item is None:
            return "UNKNOWN_ISSUER"
        return "HMAC_VERIFIED" if item.mac_key is not None else "REGISTRY_PINS_ONLY"

    def verify_record(self, *, record: HubJobRecord, spec: HubJobSpec, stdout: bytes) -> None:
        """Raise HostBoundaryError unless record is consistent with the HOST's original spec."""

        spec.assert_static_policy()
        issuer = self._issuers.get(record.issuer_id)
        if issuer is None:
            raise HostBoundaryError("HUB_RECEIPT_UNKNOWN_ISSUER")
        if record.hub_instance_id != issuer.hub_instance_id:
            raise HostBoundaryError("HUB_RECEIPT_INSTANCE_MISMATCH")
        if issuer.mac_key is not None:
            if not record.issuer_mac or not issuer.mac_key.verify(
                record.mac_material(), record.issuer_mac
            ):
                raise HostBoundaryError("HUB_RECEIPT_FORGED")
        if record.schema_id != HUB_RECORD_SCHEMA:
            raise HostBoundaryError("HUB_RECORD_SCHEMA_INVALID")
        if record.job_id != spec.hub_job_id:
            raise HostBoundaryError("HUB_JOB_ID_MISMATCH")
        if record.ticket != spec.ticket:
            raise HostBoundaryError("HUB_TICKET_MISMATCH")
        if (record.decision, record.role, record.mode) != (spec.decision, spec.role, spec.mode):
            raise HostBoundaryError("HUB_SPEC_FIELD_MISMATCH")
        if (record.provider, record.model) != (spec.provider, spec.model):
            raise HostBoundaryError("HUB_PROVIDER_IDENTITY_MISMATCH")
        if spec.provider not in issuer.allowed_providers or spec.model not in issuer.allowed_models:
            raise HostBoundaryError("HUB_PROVIDER_NOT_ALLOWED")
        if record.spec_sha256 != spec.spec_sha256():
            raise HostBoundaryError("HUB_SPEC_DIGEST_MISMATCH")
        if record.status in NON_TERMINAL_STATUSES:
            return
        if record.cost_cents > spec.max_cost_cents or record.tokens_used > spec.max_tokens:
            raise HostBoundaryError("HUB_BUDGET_EXCEEDED_REPORTED")
        if sha256_hex(stdout) != record.stdout_sha256 or len(stdout) != record.stdout_len:
            raise HostBoundaryError("HUB_STDOUT_HASH_MISMATCH")
        if record.status is HubJobStatus.COMPLETED:
            if record.exit_code != 0:
                raise HostBoundaryError("HUB_COMPLETED_NONZERO_EXIT")
            if not record.started_at or not record.ended_at or not record.receipt_id:
                raise HostBoundaryError("HUB_RECORD_INCOMPLETE")


__all__ = [
    "HUB_RECORD_SCHEMA",
    "HUB_SPEC_SCHEMA",
    "NON_TERMINAL_STATUSES",
    "HubFetcher",
    "HubIssuer",
    "HubIssuerRegistry",
    "HubJobRecord",
    "HubJobSpec",
    "HubJobStatus",
    "HubSubmitter",
    "HubTransportError",
    "parse_hub_record",
]
