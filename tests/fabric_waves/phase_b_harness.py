"""Shared MOCK Hub harness for Phase B host-adapter tests. TEST ONLY.

Nothing here contacts a provider, spawns a model CLI or uses a credential. ``MockHub`` stands in
for the AORUS Hub transport and fabricates normalized records for the host adapter to verify.
The MAC key below is a public test literal, not a secret.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.external_carrier.host_adapter import (
    APPROVAL_SCOPE,
    DispatchPolicy,
    IngestOutcome,
    OwnerApprovals,
    TrustedHubHostAdapter,
)
from seshat.fabric_waves.external_carrier.host_envelope import (
    FabricStoreSourceAuthority,
    request_pin_digest,
)
from seshat.fabric_waves.external_carrier.host_security import (
    HostIntegrityKey,
    sha256_hex,
)
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.hub_protocol import (
    HUB_RECORD_SCHEMA,
    HubIssuer,
    HubIssuerRegistry,
    HubJobRecord,
    HubJobSpec,
    HubJobStatus,
    HubTransportError,
)
from seshat.fabric_waves.external_carrier.phase_b import OriginManifest, start_waiting_run

BUDGET = WaveBudget(max_waves=40, max_activations=80, max_stone_events=80)
ISSUER_ID = "mock-hub-issuer"
HUB_INSTANCE = "mock-hub-instance-1"
PROVIDER = "mock-provider"
MODEL = "mock-model-1"
MAC_KEY_BYTES = b"public-test-literal-mac-key-0001"

TOPICS = {
    "campus": "campus-facility-utilization",
    "meteorology": "winter-operations-wind-icing",
}


def stone(topic: str) -> StoneEvent:
    return StoneEvent(
        event_id="phaseb-q",
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={
            "topic": topic,
            "query": "reconcile divergent branches with external research carrier",
        },
    )


def good_stdout(carriers: tuple[str, ...], text: str = "Branch signals diverge") -> bytes:
    body = {
        "hypothesis": f"{text} because the two branches use different measurement windows.",
        "rationale": "The excerpts report different values for the same quantity.",
        "cited_source_ids": list(carriers),
        "uncertainty": "Only two short excerpts were available.",
    }
    return json.dumps(body).encode("utf-8")


def make_record(
    spec: HubJobSpec,
    stdout: bytes,
    *,
    status: HubJobStatus = HubJobStatus.COMPLETED,
    mac_key: HostIntegrityKey | None = None,
    **overrides: object,
) -> HubJobRecord:
    terminal = status not in {HubJobStatus.QUEUED, HubJobStatus.RUNNING}
    body: dict[str, object] = {
        "schema_id": HUB_RECORD_SCHEMA,
        "job_id": spec.hub_job_id,
        "ticket": spec.ticket,
        "status": status,
        "decision": spec.decision,
        "role": spec.role,
        "mode": spec.mode,
        "provider": spec.provider,
        "model": spec.model,
        "spec_sha256": spec.spec_sha256(),
        "stdout_sha256": sha256_hex(stdout),
        "stdout_len": len(stdout),
        "exit_code": (0 if status is HubJobStatus.COMPLETED else 1) if terminal else None,
        "started_at": "2026-10-18T01:00:00+00:00",
        "ended_at": "2026-10-18T01:00:05+00:00" if terminal else "",
        "receipt_id": f"hubrcpt-{spec.hub_job_id}",
        "issuer_id": ISSUER_ID,
        "hub_instance_id": HUB_INSTANCE,
        "cost_cents": 5,
        "tokens_used": 300,
    }
    body.update(overrides)
    record = HubJobRecord(**body)  # type: ignore[arg-type]
    if mac_key is not None and "issuer_mac" not in overrides:
        record = record.model_copy(update={"issuer_mac": mac_key.mac(record.mac_material())})
    return record


LIVE_AUTH_SCHEMA_ID = "seshat.live_dispatch_authorization.v1"


def make_auth(spec: HubJobSpec, **over: object) -> dict[str, object]:
    """A coordinator authorization document bound to ``spec`` (test literal, no credential)."""

    doc: dict[str, object] = {
        "schema": LIVE_AUTH_SCHEMA_ID,
        "authorized_by": "coordinator-test",
        "host_job_id": spec.host_job_id,
        "spec_sha256": spec.spec_sha256(),
        "prompt_sha256": spec.prompt_sha256,
        "source_review_sha256": "ab" * 32,
        "nonce": "nonce-0001",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    doc.update(over)
    return doc


class MockHub:
    """Mock transport: records submissions, serves staged records. Never talks to a provider."""

    def __init__(self) -> None:
        self.submitted: list[tuple[HubJobSpec, bytes]] = []
        self.records: dict[str, tuple[HubJobRecord, bytes]] = {}
        self.fail_with: str | None = None

    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        if self.fail_with:
            raise HubTransportError(self.fail_with)
        self.submitted.append((spec, prompt))

    def fetch(self, *, hub_job_id: str) -> tuple[HubJobRecord, bytes] | None:
        return self.records.get(hub_job_id)


def make_adapter(
    tmp_path: Path,
    need,
    authority,
    *,
    extra_needs: tuple = (),
    mac: bool = False,
    store_name: str = "store",
    scopes: frozenset[str] | None = None,
    environ: dict[str, str] | None = None,
) -> TrustedHubHostAdapter:
    entries = [
        {
            "request_pin_sha256": request_pin_digest(item),
            "request_id": item.request_id,
            "run_id": item.run_id,
            "approved_by": "owner-test",
            "scope": APPROVAL_SCOPE,
        }
        for item in (need, *extra_needs)
    ]
    registry = HubIssuerRegistry(
        [
            HubIssuer(
                issuer_id=ISSUER_ID,
                hub_instance_id=HUB_INSTANCE,
                allowed_providers=frozenset({PROVIDER}),
                allowed_models=frozenset({MODEL}),
                mac_key=HostIntegrityKey(MAC_KEY_BYTES) if mac else None,
            )
        ]
    )
    return TrustedHubHostAdapter(
        store=HostJobStore(
            tmp_path / store_name,
            integrity_key=HostIntegrityKey(MAC_KEY_BYTES) if mac else None,
        ),
        registry=registry,
        source_authority=authority,
        approvals=OwnerApprovals(entries),
        policy=DispatchPolicy(provider=PROVIDER, model=MODEL),
        allowed_host_scopes=scopes or frozenset({need.worker_ref.host_scope}),
        environ=environ if environ is not None else {},
    )


@dataclass
class Harness:
    engine_kind: str
    origin: OriginManifest
    waiting: object
    need: object
    authority: FabricStoreSourceAuthority
    adapter: TrustedHubHostAdapter
    mac_key: HostIntegrityKey | None
    job: object = None
    spec: HubJobSpec | None = None

    @property
    def job_id(self) -> str:
        return self.job.host_job_id  # type: ignore[union-attr]

    @property
    def carriers(self) -> tuple[str, ...]:
        return tuple(self.need.source_carrier_ids)  # type: ignore[attr-defined]

    def complete(
        self,
        stdout: bytes | None = None,
        *,
        status: HubJobStatus = HubJobStatus.COMPLETED,
        **overrides: object,
    ) -> IngestOutcome:
        data = stdout if stdout is not None else good_stdout(self.carriers)
        record = make_record(self.spec, data, status=status, mac_key=self.mac_key, **overrides)
        return self.adapter.ingest_hub_result(
            host_job_id=self.job_id, record=record, stdout=data
        )

    def evidence(self):
        return self.adapter.build_evidence_return(self.job_id)


def make_harness(
    tmp_path: Path,
    engine_kind: str = "campus",
    *,
    mac: bool = False,
    prepare: bool = True,
    with_replay: bool = True,
    run_id: str | None = None,
    store_name: str = "store",
) -> Harness:
    origin = OriginManifest(
        engine_kind=engine_kind,
        run_id=run_id or f"phaseb-test-{engine_kind}",
        stone=stone(TOPICS[engine_kind]),
        budget=BUDGET,
    )
    waiting = start_waiting_run(origin)
    need = waiting.need
    authority = FabricStoreSourceAuthority(waiting.engine.carrier_store)
    adapter = make_adapter(tmp_path, need, authority, mac=mac, store_name=store_name)
    harness = Harness(
        engine_kind=engine_kind,
        origin=origin,
        waiting=waiting,
        need=need,
        authority=authority,
        adapter=adapter,
        mac_key=HostIntegrityKey(MAC_KEY_BYTES) if mac else None,
    )
    if prepare:
        harness.job = adapter.prepare(need, replay=origin.replay_dict() if with_replay else None)
        harness.spec = adapter.spec_for(harness.job)
    return harness
