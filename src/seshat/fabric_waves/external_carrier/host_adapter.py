"""HOST-ONLY trusted AORUS Hub adapter implementing the generic ExecutorPort.

The unprivileged core only ever sees normalized ``AgentEvidenceReturn`` objects that this
adapter re-derived from host-held state: the persisted ORIGINAL request bytes, the original Hub
job spec, the Hub record verified against the host issuer registry, the stored stdout bytes and
the first-writer terminal row. Nothing the model or a transport asserted is trusted directly.

This module performs NO network I/O, imports no model CLI and no subprocess. Submission to the
official ``aiye-exec`` path lives in ``host_dispatcher`` behind a dry-run default.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from seshat.fabric_waves.contracts import EpistemicLevel
from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    HostJobEvidence,
    HostJobReceipt,
    material_hash,
)
from seshat.fabric_waves.external_carrier.host_envelope import (
    SourceAuthority,
    build_outbound,
    original_request_bytes,
    parse_model_output,
    request_pin_digest,
)
from seshat.fabric_waves.external_carrier.host_security import (
    ALLOWED_HUB_ROLES,
    HostBoundaryError,
    HostLimits,
    require_safe_token,
    sha256_hex,
)
from seshat.fabric_waves.external_carrier.host_store import HostJobStore, JobRecord, TerminalRecord
from seshat.fabric_waves.external_carrier.hub_protocol import (
    NON_TERMINAL_STATUSES,
    HubIssuerRegistry,
    HubJobRecord,
    HubJobSpec,
    HubJobStatus,
    parse_hub_record,
)
from seshat.fabric_waves.external_carrier.ledger import (
    compute_host_binding_hash,
    dispatch_pins_match,
)

APPROVAL_SCOPE = "phaseb_e5_hub_dispatch"
APPROVAL_SCHEMA = "seshat.owner_origin_approvals.v1"


@dataclass(frozen=True)
class DispatchPolicy:
    """Host-chosen Hub execution identity. Never taken from a StoneEvent or the model."""

    provider: str
    model: str
    role: str = "analyze"

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_HUB_ROLES:
            raise HostBoundaryError("HUB_SPEC_ROLE_DENIED")
        require_safe_token(self.provider, code="HUB_POLICY_PROVIDER_INVALID", extra=":/")
        require_safe_token(self.model, code="HUB_POLICY_MODEL_INVALID", extra=":/")


class OwnerApprovals:
    """Host-held, owner-authored approvals binding a machine ResearchNeed to Hub dispatch."""

    def __init__(self, entries: list[Mapping[str, Any]]) -> None:
        cleaned: list[dict[str, str]] = []
        for entry in entries:
            item = {str(k): str(v) for k, v in dict(entry).items()}
            digest = item.get("request_pin_sha256", "")
            if (
                len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or not item.get("request_id")
                or not item.get("run_id")
                or not item.get("approved_by")
                or item.get("scope") != APPROVAL_SCOPE
            ):
                raise HostBoundaryError("OWNER_APPROVAL_INVALID")
            cleaned.append(item)
        self._entries = cleaned

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> OwnerApprovals:
        if document.get("schema") != APPROVAL_SCHEMA or not isinstance(
            document.get("approvals"), list
        ):
            raise HostBoundaryError("OWNER_APPROVAL_INVALID")
        return cls(list(document["approvals"]))

    def approval_for(self, need: AgentTaskRequest, pin_digest: str) -> dict[str, str] | None:
        for item in self._entries:
            if (
                item["request_pin_sha256"] == pin_digest
                and item["request_id"] == need.request_id
                and item["run_id"] == need.run_id
            ):
                return dict(item)
        return None


@dataclass(frozen=True)
class IngestOutcome:
    """Typed result of examining a Hub record. ``terminal`` is set only after a CAS write."""

    state: str  # WAITING | COMPLETED | FAILED | CANCELLED | TIMEOUT | OUTPUT_REJECTED
    detail: str
    result_digest: str
    payload: dict[str, Any] | None
    terminal: TerminalRecord | None
    wrote: bool


class TrustedHubHostAdapter:
    """ExecutorPort backed by a durable HostJobStore and a verified Hub record chain."""

    def __init__(
        self,
        *,
        store: HostJobStore,
        registry: HubIssuerRegistry,
        source_authority: SourceAuthority,
        approvals: OwnerApprovals,
        policy: DispatchPolicy,
        allowed_host_scopes: frozenset[str],
        limits: HostLimits | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if not allowed_host_scopes:
            raise HostBoundaryError("HOST_SCOPES_REQUIRED")
        self.store = store
        self.registry = registry
        self._authority = source_authority
        self._approvals = approvals
        self._policy = policy
        self._scopes = frozenset(allowed_host_scopes)
        self.limits = limits or HostLimits()
        self._environ = environ

    # -- helpers -----------------------------------------------------------------------

    def _env(self) -> Mapping[str, str]:
        return self._environ if self._environ is not None else os.environ

    @staticmethod
    def _spec(job: JobRecord) -> HubJobSpec:
        try:
            spec = HubJobSpec.model_validate(job.dispatch["spec"])
        except (KeyError, ValueError):
            raise HostBoundaryError("HOST_JOB_RECORD_INCONSISTENT") from None
        return spec

    def load_job(self, host_job_id: str) -> JobRecord:
        """Load a job and cross-check its stored request, spec and prompt digests."""

        job = self.store.get_job(host_job_id)
        request = job.request()
        pin = request_pin_digest(request)
        spec = self._spec(job)
        if (
            job.pins.get("request_pin_sha256") != pin
            or spec.request_pin_sha256 != pin
            or spec.host_job_id != job.host_job_id
            or job.dispatch.get("spec_sha256") != spec.spec_sha256()
            or sha256_hex(job.prompt_bytes) != spec.prompt_sha256
            or request.request_id != job.request_id
            or request.idempotency_key != job.idempotency_key
        ):
            raise HostBoundaryError("HOST_JOB_RECORD_INCONSISTENT")
        return job

    def spec_for(self, job: JobRecord) -> HubJobSpec:
        return self._spec(job)

    # -- ExecutorPort -----------------------------------------------------------------

    def _plan(self, need: AgentTaskRequest) -> dict[str, Any]:
        """Run every gate and compute the job columns. Pure: nothing is persisted."""

        scope = need.worker_ref.host_scope
        if scope not in self._scopes:
            raise HostBoundaryError("HOST_SCOPE_NOT_ALLOWED")
        pin = request_pin_digest(need)
        approval = self._approvals.approval_for(need, pin)
        if approval is None:
            raise HostBoundaryError("ORIGIN_NOT_APPROVED")
        if not self.registry.provider_model_allowed(self._policy.provider, self._policy.model):
            raise HostBoundaryError("HUB_PROVIDER_NOT_ALLOWED")
        host_job_id = f"hostjob-{pin[:24]}"
        package = build_outbound(
            need,
            host_job_id=host_job_id,
            source_authority=self._authority,
            limits=self.limits,
            environ=self._env(),
        )
        spec = HubJobSpec(
            host_job_id=host_job_id,
            hub_job_id=f"seshat-pb-{pin[:20]}",
            ticket=f"SESHAT-PB-{pin[:12].upper()}",
            role=self._policy.role,
            provider=self._policy.provider,
            model=self._policy.model,
            max_tokens=package.max_tokens,
            max_time_seconds=package.max_time_seconds,
            max_cost_cents=package.max_cost_cents,
            prompt_sha256=package.prompt_sha256,
            request_pin_sha256=pin,
        )
        spec.assert_static_policy()
        pins: dict[str, Any] = {
            "request_pin_sha256": pin,
            "request_id": need.request_id,
            "idempotency_key": need.idempotency_key,
            "run_id": need.run_id,
            "wave_id": need.wave_id,
            "thread_id": need.thread_id,
            "node_id": need.node_id,
            "method_body_ref": need.method_body_ref.model_dump(mode="json"),
            "worker_ref": need.worker_ref.model_dump(mode="json"),
            "source_carrier_ids": list(need.source_carrier_ids),
            "source_versions": dict(need.source_versions),
            "canonical_input_hash": need.canonical_input_hash,
            "source_rights": need.source_rights.value,
            "expected_output_schema": need.expected_output_schema,
            "admissible_evidence_classes": list(need.admissible_evidence_classes),
        }
        origin = {
            "origin_kind": "MACHINE_GENERATED_RESEARCH_NEED_OWNER_APPROVED",
            "approved_by": approval["approved_by"],
            "approval_scope": approval["scope"],
            "approval_request_pin_sha256": approval["request_pin_sha256"],
            "idempotency_key": need.idempotency_key,
        }
        dispatch = {
            "spec": spec.model_dump(mode="json"),
            "spec_sha256": spec.spec_sha256(),
            "prompt_sha256": package.prompt_sha256,
            "outbound_envelope_sha256": material_hash(package.envelope),
        }
        return {
            "host_job_id": host_job_id,
            "request": need,
            "request_bytes": original_request_bytes(need),
            "pins": pins,
            "origin": origin,
            "dispatch": dispatch,
            "prompt_bytes": package.prompt_bytes,
            "source_digests": package.source_digests,
            "spec": spec,
        }

    def preview(self, need: AgentTaskRequest) -> dict[str, Any]:
        """Dry-run of ``prepare``: all gates, no persistence. Returns a public summary."""

        plan = self._plan(need)
        spec: HubJobSpec = plan["spec"]
        return {
            "host_job_id": plan["host_job_id"],
            "hub_job_id": spec.hub_job_id,
            "ticket": spec.ticket,
            "spec_sha256": spec.spec_sha256(),
            "prompt_sha256": spec.prompt_sha256,
            "request_pin_sha256": spec.request_pin_sha256,
            "original_request_sha256": sha256_hex(plan["request_bytes"]),
            "source_digests": dict(plan["source_digests"]),
            "persisted": False,
        }

    def prepare(self, need: AgentTaskRequest, *, replay: Mapping[str, Any] | None = None) -> JobRecord:
        """Gate, approve and durably persist a job. Idempotent. Never contacts the Hub."""

        existing = self.store.find_job_by_request(need.request_id)
        if existing is not None:
            if existing.pins.get("request_pin_sha256") != request_pin_digest(need):
                raise HostBoundaryError("HOST_REQUEST_ID_CONFLICT")
            return self.load_job(existing.host_job_id)
        plan = self._plan(need)
        self.store.insert_job(
            host_job_id=plan["host_job_id"],
            request=need,
            request_bytes=plan["request_bytes"],
            pins=plan["pins"],
            origin=plan["origin"],
            dispatch=plan["dispatch"],
            prompt_bytes=plan["prompt_bytes"],
            source_digests=plan["source_digests"],
            replay=dict(replay or {}),
        )
        return self.load_job(plan["host_job_id"])

    def dispatch(self, need: AgentTaskRequest) -> str:
        """ExecutorPort.dispatch: persist the approved job only. The Hub is not contacted."""

        return self.prepare(need).host_job_id

    def authoritative_dispatch(self, *, job_id: str) -> AgentTaskRequest:
        return self.load_job(job_id).request()

    # -- Hub result ingest -------------------------------------------------------------

    def evaluate_hub_result(
        self,
        *,
        host_job_id: str,
        record: HubJobRecord,
        stdout: bytes,
    ) -> IngestOutcome:
        """Verify a Hub record against host-held state; no write. Forgeries raise."""

        job = self.load_job(host_job_id)
        request = job.request()
        spec = self._spec(job)
        self.registry.verify_record(record=record, spec=spec, stdout=stdout)
        if record.status in NON_TERMINAL_STATUSES:
            return IngestOutcome("WAITING", record.status.value, "", None, None, False)
        if record.status is HubJobStatus.COMPLETED:
            try:
                payload = parse_model_output(
                    stdout, need=request, limits=self.limits, environ=self._env()
                )
            except HostBoundaryError as exc:
                return IngestOutcome("OUTPUT_REJECTED", exc.code, "", None, None, False)
            return IngestOutcome("COMPLETED", "", material_hash(payload), payload, None, False)
        return IngestOutcome(record.status.value.upper(), record.status.value, "", None, None, False)

    def ingest_hub_result(
        self,
        *,
        host_job_id: str,
        record: HubJobRecord,
        stdout: bytes,
    ) -> IngestOutcome:
        """Verify and, if terminal, durably CAS the terminal row (first writer wins)."""

        outcome = self.evaluate_hub_result(host_job_id=host_job_id, record=record, stdout=stdout)
        if outcome.state == "WAITING":
            return outcome
        terminal = self.store.record_terminal(
            host_job_id=host_job_id,
            status=outcome.state,
            hub_record=record.model_dump(mode="json"),
            stdout_bytes=stdout,
            stdout_sha256=sha256_hex(stdout),
            result_digest=outcome.result_digest,
            payload=outcome.payload,
            receipt_sha256=record.receipt_sha256(),
            detail=outcome.detail,
        )
        return IngestOutcome(
            outcome.state, outcome.detail, outcome.result_digest, outcome.payload, terminal, True
        )

    # -- evidence return ---------------------------------------------------------------

    def _host_job_evidence(
        self,
        *,
        job: JobRecord,
        request: AgentTaskRequest,
        record: HubJobRecord,
        terminal: TerminalRecord,
    ) -> HostJobEvidence:
        spec = self._spec(job)
        return HostJobEvidence(
            job_id=job.host_job_id,
            host_scope=request.worker_ref.host_scope,
            request_id=request.request_id,
            started_at=record.started_at,
            ended_at=record.ended_at,
            result_provenance=(
                "HUB_JOB_VERIFIED",
                f"hub_job:{record.job_id}",
                f"ticket:{record.ticket}",
                f"provider:{record.provider}",
                f"model:{record.model}",
                f"role:{record.role}",
                f"issuer:{record.issuer_id}",
                f"issuer_auth:{self.registry.authentication_mode(record.issuer_id)}",
                f"hub_receipt:{record.receipt_id}",
                f"stdout_sha256:{terminal.stdout_sha256}",
                f"spec_sha256:{spec.spec_sha256()}",
                f"request_pin_sha256:{spec.request_pin_sha256}",
            ),
            result_digest=terminal.result_digest,
            allowed_source_rights=request.source_rights,
        )

    def assert_hub_attested_for_export(self, host_job_id: str) -> None:
        """Require an independently verified Hub chain before labelling transport as Hub-attested."""

        # Normalized spool records and local ACK rows can be minted by an operator. Until a
        # native Hub-issued ID and immutable issuer ledger are verified against the original
        # host request, neither the CLI nor the library may claim HUB_SPOOL_RECORD.
        raise HostBoundaryError("HUB_TRANSPORT_UNATTESTED")

    def build_evidence_return(self, host_job_id: str) -> AgentEvidenceReturn:
        """Deterministically rebuild the E5 return for a COMPLETED terminal."""

        job = self.load_job(host_job_id)
        request = job.request()
        terminal = self.store.get_terminal(host_job_id)
        if terminal is None:
            raise HostBoundaryError("TERMINAL_RESULT_MISSING")
        if terminal.status != "COMPLETED" or terminal.payload is None:
            raise HostBoundaryError("HOST_JOB_NOT_COMPLETED")
        record = parse_hub_record(terminal.hub_record)
        host_job = self._host_job_evidence(
            job=job, request=request, record=record, terminal=terminal
        )
        receipt = HostJobReceipt(
            receipt_id=f"hostrcpt-{host_job_id}",
            authorized=True,
            host_job=host_job,
            binding_hash=compute_host_binding_hash(
                request=request, host_job=host_job, worker_ref=request.worker_ref
            ),
            worker_ref=request.worker_ref,
        )
        return AgentEvidenceReturn(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            run_id=request.run_id,
            worker_ref=request.worker_ref,
            epistemic_level=EpistemicLevel.E5,
            proposal_payload=dict(terminal.payload),
            source_claim_refs=tuple(request.source_carrier_ids),
            method_call_receipt_hash=terminal.receipt_sha256,
            result_digest=terminal.result_digest,
            host_receipt=receipt,
        )

    def assert_sources_current(self, job: JobRecord, request: AgentTaskRequest) -> None:
        carriers = tuple(request.source_carrier_ids)
        current = self._authority.current_source_versions(carriers)
        for carrier_id in carriers:
            if carrier_id not in current:
                raise HostBoundaryError("SOURCE_CARRIER_UNKNOWN")
            if current[carrier_id] != request.source_versions.get(carrier_id):
                raise HostBoundaryError("SOURCE_VERSION_STALE")
            digest = self._authority.pin_content_digest(
                carrier_id, pinned_version=request.source_versions[carrier_id]
            )
            if digest != job.source_digests.get(carrier_id):
                raise HostBoundaryError("SOURCE_CONTENT_STALE")

    def recheck_outbound(self, job: JobRecord) -> None:
        """Re-run the full outbound gate; the rebuilt prompt must equal the persisted prompt.

        Called before any chargeable submission: sources must still be current and readable
        and the exact bytes that will be sent must be the bytes the owner approved.
        """

        request = job.request()
        spec = self._spec(job)
        package = build_outbound(
            request,
            host_job_id=job.host_job_id,
            source_authority=self._authority,
            limits=self.limits,
            environ=self._env(),
        )
        if package.prompt_sha256 != spec.prompt_sha256 or package.prompt_bytes != job.prompt_bytes:
            raise HostBoundaryError("OUTBOUND_PROMPT_DRIFT")
        if package.source_digests != job.source_digests:
            raise HostBoundaryError("SOURCE_CONTENT_STALE")

    def verify_return(
        self,
        *,
        need: AgentTaskRequest,
        evidence: AgentEvidenceReturn,
    ) -> HostJobReceipt:
        """Independent verification. Raises a stable code; never trusts ``authorized`` alone."""

        host_job = evidence.host_receipt.host_job
        try:
            job = self.load_job(host_job.job_id)
        except HostBoundaryError as exc:
            if exc.code == "UNKNOWN_JOB_ID":
                raise HostBoundaryError("UNISSUED_HOST_JOB") from None
            raise
        request = job.request()
        if not evidence.host_receipt.authorized:
            raise HostBoundaryError("FORGED_AUTHORIZED_FLAG")
        if not dispatch_pins_match(need, request) or request_pin_digest(need) != job.pins.get(
            "request_pin_sha256"
        ):
            raise HostBoundaryError("LEDGER_DISPATCH_PIN_MISMATCH")
        if host_job.request_id != request.request_id:
            raise HostBoundaryError("JOB_REQUEST_ID_MISMATCH")
        if (
            evidence.host_receipt.worker_ref != request.worker_ref
            or evidence.worker_ref != request.worker_ref
        ):
            raise HostBoundaryError("WORKER_REF_MISMATCH")
        if request.worker_ref.host_scope not in self._scopes:
            raise HostBoundaryError("HOST_SCOPE_NOT_ALLOWED")
        if host_job.host_scope != request.worker_ref.host_scope:
            raise HostBoundaryError("HOST_SCOPE_MISMATCH")
        if evidence.idempotency_key != request.idempotency_key:
            raise HostBoundaryError("JOB_IDEMPOTENCY_MISMATCH")
        if evidence.run_id != request.run_id:
            raise HostBoundaryError("EVIDENCE_RUN_ID_MISMATCH")
        terminal = self.store.get_terminal(job.host_job_id)
        if terminal is None:
            raise HostBoundaryError("TERMINAL_RESULT_MISSING")
        if terminal.status != "COMPLETED":
            raise HostBoundaryError("HOST_JOB_NOT_COMPLETED")
        record = parse_hub_record(terminal.hub_record)
        if record.receipt_sha256() != terminal.receipt_sha256:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        spec = self._spec(job)
        self.registry.verify_record(record=record, spec=spec, stdout=terminal.stdout_bytes)
        payload = parse_model_output(
            terminal.stdout_bytes, need=request, limits=self.limits, environ=self._env()
        )
        if material_hash(payload) != terminal.result_digest or payload != terminal.payload:
            raise HostBoundaryError("HOST_STORE_ROW_TAMPERED")
        if (
            evidence.result_digest != terminal.result_digest
            or material_hash(evidence.proposal_payload) != terminal.result_digest
        ):
            raise HostBoundaryError("FORGED_TERMINAL_RESULT")
        if evidence.method_call_receipt_hash != terminal.receipt_sha256:
            raise HostBoundaryError("FORGED_METHOD_RECEIPT")
        if host_job.allowed_source_rights != request.source_rights:
            raise HostBoundaryError("HOST_JOB_RIGHTS_ESCALATION")
        expected_job = self._host_job_evidence(
            job=job, request=request, record=record, terminal=terminal
        )
        if host_job != expected_job:
            raise HostBoundaryError("FORGED_HOST_JOB_TERMINAL")
        expected_binding = compute_host_binding_hash(
            request=request, host_job=expected_job, worker_ref=request.worker_ref
        )
        if evidence.host_receipt.binding_hash != expected_binding:
            raise HostBoundaryError("BINDING_HASH_INVALID")
        if evidence.host_receipt.receipt_id != f"hostrcpt-{job.host_job_id}":
            raise HostBoundaryError("FORGED_RECEIPT_ID")
        if evidence.epistemic_level is not EpistemicLevel.E5:
            raise HostBoundaryError("E5_ONLY_EXTERNAL_RETURN")
        if evidence.forged_human_decision:
            raise HostBoundaryError("FORGED_HUMAN_DECISION_REJECTED")
        if not set(evidence.source_claim_refs) <= set(request.source_carrier_ids):
            raise HostBoundaryError("E5_SOURCE_CLAIM_OUTSIDE_REQUEST_SCOPE")
        self.assert_sources_current(job, request)
        return evidence.host_receipt


__all__ = [
    "APPROVAL_SCHEMA",
    "APPROVAL_SCOPE",
    "DispatchPolicy",
    "IngestOutcome",
    "OwnerApprovals",
    "TrustedHubHostAdapter",
]
