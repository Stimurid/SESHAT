"""Phase B orchestration: verified resume of a WAITING run and machine artifact export.

Resume modes (reported verbatim in ``resume_receipt.json``; never blurred):

``PHASE_B_LIVE_IN_PROCESS_ONLY``
    ONE in-memory WaveEngine stayed alive while the host job ran. The engine's own
    ``resume_external_evidence`` consumed an untrusted-mailbox return that the host adapter
    independently re-verified. Valid only inside that single process; nothing is persisted.

``PHASE_B_REPLAY_VERIFIED``
    Restart-safe. The host persisted the ORIGINAL machine StoneEvent, budget and request bytes.
    A fresh engine replays that exact event with the same run_id against CURRENT immutable
    source, and must regenerate a ResearchNeed whose pin digest and source content digests equal
    the host-held originals before any return is admitted. No cross-process engine state is
    pretended to be restored: it is deterministically re-derived and compared.

``PHASE_B_REQUIRED``
    Neither is possible (no replay material persisted). The adapter refuses rather than faking.
"""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seshat.fabric_waves.carpet_export import (
    all_run_events,
    operator_stone_events,
    run_ledger_head_hash,
    sediment_records_for_run,
)
from seshat.fabric_waves.contracts import (
    ActivationOutcome,
    ActivationRecord,
    EpistemicLevel,
    FabricRunOutcome,
    RunRecord,
    StoneEvent,
    WaveBudget,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.external_carrier.contracts import (
    AgentEvidenceReturn,
    AgentTaskRequest,
    ExternalResumeReceipt,
)
from seshat.fabric_waves.external_carrier.host_adapter import TrustedHubHostAdapter
from seshat.fabric_waves.external_carrier.host_envelope import request_pin_digest
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError,
    atomic_write_bytes,
)
from seshat.fabric_waves.external_carrier.hosts import (
    campus_external_host_engine,
    meteorology_external_host_engine,
)
from seshat.fabric_waves.trace import render_html

PHASE_B_LIVE_IN_PROCESS_ONLY = "PHASE_B_LIVE_IN_PROCESS_ONLY"
PHASE_B_REPLAY_VERIFIED = "PHASE_B_REPLAY_VERIFIED"
PHASE_B_REQUIRED = "PHASE_B_REQUIRED"
# Library-API transport labels. ``HUB_SPOOL_RECORD`` requires an attested Hub chain on the
# adapter; ``UNATTESTED_MANUAL_IMPORT`` is the safe default for manual snapshots. Any other
# caller-supplied label is rejected so a mocked Hub transport cannot be confused with a live one.
TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT = "UNATTESTED_MANUAL_IMPORT"
TRANSPORT_KIND_HUB_SPOOL_RECORD = "HUB_SPOOL_RECORD"
_PHASE_B_KNOWN_TRANSPORTS = frozenset(
    {TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT, TRANSPORT_KIND_HUB_SPOOL_RECORD}
)

ENGINE_FACTORIES: dict[str, Callable[[], WaveEngine]] = {
    "campus": campus_external_host_engine,
    "meteorology": meteorology_external_host_engine,
}

HOST_MODULES = (
    "host_security",
    "hub_protocol",
    "host_envelope",
    "host_store",
    "host_adapter",
    "host_dispatcher",
    "phase_b",
    "host_cli",
)

PHASE_B_ARTIFACTS: tuple[str, ...] = (
    "stones.json",
    "events.jsonl",
    "waves.jsonl",
    "activations.jsonl",
    "sediment.json",
    "resonances.json",
    "carpet.html",
    "research_needs.jsonl",
    "job_dispatch.jsonl",
    "independent_host_job_receipts.jsonl",
    "terminal_output_sha.jsonl",
    "evidence_returns.jsonl",
    "resume_receipt.json",
)


@dataclass(frozen=True)
class OriginManifest:
    """The ORIGINAL machine event material needed for restart-safe verified replay."""

    engine_kind: str
    run_id: str
    stone: StoneEvent
    budget: WaveBudget

    def replay_dict(self) -> dict[str, Any]:
        return {
            "engine_kind": self.engine_kind,
            "run_id": self.run_id,
            "stone": self.stone.model_dump(mode="json"),
            "budget": self.budget.model_dump(mode="json"),
        }

    @classmethod
    def from_replay(cls, data: Mapping[str, Any]) -> OriginManifest:
        try:
            return cls(
                engine_kind=str(data["engine_kind"]),
                run_id=str(data["run_id"]),
                stone=StoneEvent.model_validate(data["stone"]),
                budget=WaveBudget.model_validate(data["budget"]),
            )
        except (KeyError, ValueError, TypeError):
            raise HostBoundaryError("PHASE_B_REQUIRED_NO_REPLAY_MATERIAL") from None


@dataclass
class WaitingRun:
    engine: WaveEngine
    need: AgentTaskRequest
    origin: OriginManifest
    run_record: RunRecord


@dataclass
class ResumeResult:
    mode: str
    engine: WaveEngine
    run_record: RunRecord
    need: AgentTaskRequest
    evidence: AgentEvidenceReturn
    wait_activation: ActivationRecord
    activation_ids_before: set[str]
    observation_versions_before: dict[str, str | None]
    facts: dict[str, Any]


def _factory(kind: str, factories: Mapping[str, Callable[[], WaveEngine]] | None):
    table = factories if factories is not None else ENGINE_FACTORIES
    factory = table.get(kind)
    if factory is None:
        raise HostBoundaryError("PHASE_B_ENGINE_KIND_UNKNOWN")
    return factory


def start_waiting_run(
    origin: OriginManifest,
    *,
    factories: Mapping[str, Callable[[], WaveEngine]] | None = None,
) -> WaitingRun:
    """Run the original machine event on a fresh engine until it parks WAITING_EXTERNAL."""

    engine = _factory(origin.engine_kind, factories)()
    record = engine.run(run_id=origin.run_id, budget=origin.budget, initial_stone=origin.stone)
    if record.outcome is not FabricRunOutcome.WAITING_EXTERNAL:
        raise HostBoundaryError("PHASE_B_NO_EXTERNAL_WAIT")
    needs = [n for n in engine.external_ledger.research_needs if n.run_id == origin.run_id]
    if not needs:
        raise HostBoundaryError("PHASE_B_NO_EXTERNAL_WAIT")
    return WaitingRun(engine=engine, need=needs[-1], origin=origin, run_record=record)


def _wait_activation(engine: WaveEngine, need: AgentTaskRequest) -> ActivationRecord:
    for activation in engine.ledger.activations_for_run(need.run_id):
        if (
            activation.outcome is ActivationOutcome.WAITING_EXTERNAL
            and activation.error_detail == need.request_id
        ):
            return activation
    raise HostBoundaryError("PHASE_B_WAIT_ACTIVATION_MISSING")


def _observation_ids(engine: WaveEngine) -> list[str]:
    return sorted(t for t in engine.thread_specs if t.startswith("obs-"))


def _host_suffix(engine: WaveEngine) -> str:
    for thread_id in engine.thread_specs:
        if thread_id.startswith("external-integrate-"):
            return thread_id.removeprefix("external-integrate-")
    raise HostBoundaryError("PHASE_B_ENGINE_TOPOLOGY_UNSUPPORTED")


def resume_live(
    waiting: WaitingRun,
    *,
    adapter: TrustedHubHostAdapter,
    host_job_id: str,
    budget: WaveBudget | None = None,
    mode: str = PHASE_B_LIVE_IN_PROCESS_ONLY,
) -> ResumeResult:
    """Resume a parked engine with an adapter-rebuilt, adapter-verified E5 return."""

    engine, need = waiting.engine, waiting.need
    job = adapter.load_job(host_job_id)
    ledger_need = engine.external_ledger.need_by_id(need.request_id)
    # The engine ledger compares only 14 dispatch pins; also bind question text, budgets and
    # priority to what the owner approved and the host persisted before the return is admitted.
    if ledger_need is None or request_pin_digest(ledger_need) != job.pins.get(
        "request_pin_sha256"
    ):
        raise HostBoundaryError("LEDGER_NEED_PIN_DRIFT")
    evidence = adapter.build_evidence_return(host_job_id)
    receipt = ExternalResumeReceipt(
        request_id=evidence.request_id, run_id=evidence.run_id, evidence_return=evidence
    )
    wait_activation = _wait_activation(engine, need)
    before = {a.activation_id for a in engine.ledger.activations_for_run(need.run_id)}
    versions = engine.sediment.version_map()
    obs_before = {oid: versions.get(oid) for oid in _observation_ids(engine)}
    record = engine.resume_external_evidence(
        receipt=receipt, budget=budget or waiting.origin.budget, port=adapter
    )
    result = ResumeResult(
        mode=mode,
        engine=engine,
        run_record=record,
        need=need,
        evidence=evidence,
        wait_activation=wait_activation,
        activation_ids_before=before,
        observation_versions_before=obs_before,
        facts={},
    )
    result.facts = causal_facts(result)
    return result


def resume_by_replay(
    *,
    adapter: TrustedHubHostAdapter,
    host_job_id: str,
    factories: Mapping[str, Callable[[], WaveEngine]] | None = None,
) -> ResumeResult:
    """PHASE_B_REPLAY_VERIFIED: re-derive the WAIT state from persisted original material."""

    job = adapter.load_job(host_job_id)
    if not job.replay:
        raise HostBoundaryError("PHASE_B_REQUIRED_NO_REPLAY_MATERIAL")
    origin = OriginManifest.from_replay(job.replay)
    waiting = start_waiting_run(origin, factories=factories)
    need = waiting.need
    if request_pin_digest(need) != job.pins.get("request_pin_sha256"):
        raise HostBoundaryError("REPLAY_REQUEST_DRIFT")
    store = waiting.engine.carrier_store
    if store is None:
        raise HostBoundaryError("REPLAY_SOURCE_AUTHORITY_UNAVAILABLE")
    if set(job.source_digests) != set(need.source_carrier_ids):
        raise HostBoundaryError("REPLAY_SOURCE_DRIFT")
    for carrier_id, expected in job.source_digests.items():
        try:
            actual = store.pin_content_digest(
                carrier_id, pinned_version=need.source_versions[carrier_id]
            )
        except (ValueError, KeyError):
            raise HostBoundaryError("REPLAY_SOURCE_DRIFT") from None
        if actual != expected:
            raise HostBoundaryError("REPLAY_SOURCE_DRIFT")
    return resume_live(
        waiting, adapter=adapter, host_job_id=host_job_id, mode=PHASE_B_REPLAY_VERIFIED
    )


def causal_facts(result: ResumeResult) -> dict[str, Any]:
    """Assert and describe the causal re-entry. Raises HostBoundaryError if it did not hold."""

    engine, need, wait = result.engine, result.need, result.wait_activation
    run_id = need.run_id
    host = _host_suffix(engine)
    integrate_thread = f"external-integrate-{host}"
    reconcile_thread = f"reconcile-{host}"
    new_fired = [
        a
        for a in engine.ledger.activations_for_run(run_id)
        if a.activation_id not in result.activation_ids_before
        and a.outcome is ActivationOutcome.FIRED
    ]
    downstream = [a for a in new_fired if a.thread_id in {integrate_thread, reconcile_thread}]
    if sorted(a.thread_id for a in downstream) != sorted([integrate_thread, reconcile_thread]):
        raise HostBoundaryError("PHASE_B_DOWNSTREAM_THREADS_NOT_FIRED")
    events = [
        e for e in engine.ledger.events if e.run_id == run_id and "external-return" in e.event_id
    ]
    if not events or events[-1].parent_activation_id != wait.activation_id:
        raise HostBoundaryError("PHASE_B_RETURN_EVENT_NOT_PARENTED")
    proposals = [r for r in engine.sediment.all_records() if r.object_type == "external.proposal"]
    if not proposals or proposals[-1].epistemic_level is not EpistemicLevel.E5:
        raise HostBoundaryError("PHASE_B_PROPOSAL_NOT_E5")
    versions = engine.sediment.version_map()
    for oid, before in result.observation_versions_before.items():
        if versions.get(oid) != before:
            raise HostBoundaryError("PHASE_B_BRANCH_DISTURBED")
    resonances = engine.ledger.resonances_for_run(run_id)
    if not any(wait.activation_id in r.trace_activation_ids for r in resonances):
        raise HostBoundaryError("PHASE_B_RESONANCE_NOT_CAUSAL")
    return {
        "downstream_fired_threads": sorted(a.thread_id for a in downstream),
        "downstream_activation_ids": sorted(a.activation_id for a in downstream),
        "wait_activation_id": wait.activation_id,
        "wait_wave_id": wait.wave_id,
        "external_return_event_id": events[-1].event_id,
        "proposal_sediment_id": proposals[-1].sediment_id,
        "proposal_epistemic_level": proposals[-1].epistemic_level.value,
        "proposal_provenance": list(proposals[-1].provenance),
        "stable_observation_versions": dict(sorted(result.observation_versions_before.items())),
        "resonance_ids_tracing_wait": sorted(
            r.resonance_id for r in resonances if wait.activation_id in r.trace_activation_ids
        ),
    }


# -- artifacts -------------------------------------------------------------------------------


def _jsonl(items: list[Any]) -> bytes:
    if not items:
        return b""
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in items]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _json_doc(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode(
        "utf-8"
    )


def _provenance_html(facts: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in facts.items()
    )
    return (
        '<div class="block"><h2>Phase B external provenance</h2>'
        "<div>Every value below is read from the host store / verified ledger, "
        "not from the model.</div>"
        f"<table><tbody>{rows}</tbody></table></div>"
    )


def host_module_digests() -> dict[str, dict[str, Any]]:
    base = Path(__file__).resolve().parent
    out: dict[str, dict[str, Any]] = {}
    for name in HOST_MODULES:
        path = base / f"{name}.py"
        if path.is_file():
            data = path.read_bytes()
            out[f"seshat/fabric_waves/external_carrier/{name}.py"] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_length": len(data),
            }
    return out


def _git_meta_safe() -> dict[str, Any]:
    try:
        from seshat.fabric_waves.carpet_portfolio import _git_meta

        return dict(_git_meta())
    except Exception:  # noqa: BLE001 - provenance is best effort and labelled
        return {"attestation": "GIT_NOT_ATTESTED"}


def export_phase_b_artifacts(
    output_dir: Path,
    *,
    result: ResumeResult,
    adapter: TrustedHubHostAdapter,
    host_job_id: str,
    transport_kind: str,
) -> dict[str, Any]:
    """Write every Phase B machine artifact from actual code, then a per-file SHA-256 receipt.

    ``transport_kind`` is a caller-supplied, verbatim label (e.g. ``MOCK_HUB_TEST_ONLY``) so a
    mocked Hub can never be mistaken for a live one in the receipt. The label is gated by the
    library itself: ``HUB_SPOOL_RECORD`` requires an independent Hub-attested chain on the
    adapter (``SUBMIT_ACKED`` terminal + registry-verified record); any unknown label is
    refused so a hostile caller cannot bypass the gate by simply claiming a different label.
    """

    if not isinstance(transport_kind, str) or transport_kind not in _PHASE_B_KNOWN_TRANSPORTS:
        raise HostBoundaryError("TRANSPORT_KIND_UNKNOWN")
    output_dir = Path(output_dir)
    engine, need = result.engine, result.need
    run_id = need.run_id
    ledger = engine.ledger
    run_record = next((r for r in ledger.runs if r.run_id == run_id), None)
    if run_record is None:
        raise HostBoundaryError("PHASE_B_RUN_NOT_COMPLETED")
    job = adapter.load_job(host_job_id)
    spec = adapter.spec_for(job)
    terminal = adapter.store.get_terminal(host_job_id)
    if terminal is None:
        raise HostBoundaryError("TERMINAL_RESULT_MISSING")
    if transport_kind == TRANSPORT_KIND_HUB_SPOOL_RECORD:
        # Library-side attestation check: the CLI does the same via
        # ``resolve_export_transport_kind`` but a programmatic caller must not be able to bypass
        # the gate by skipping the CLI.
        adapter.assert_hub_attested_for_export(host_job_id)
    record = terminal.hub_record
    auth_mode = adapter.registry.authentication_mode(str(record.get("issuer_id", "")))
    submissions = adapter.store.submissions(host_job_id)

    facts = {
        "mode": result.mode,
        "run_id": run_id,
        "wave_id_of_wait": need.wave_id,
        "request_id": need.request_id,
        "request_pin_sha256": job.pins.get("request_pin_sha256", ""),
        "original_request_sha256": job.request_sha256,
        "host_job_id": host_job_id,
        "hub_job_id": spec.hub_job_id,
        "ticket": spec.ticket,
        "provider": spec.provider,
        "model": spec.model,
        "issuer_auth": auth_mode,
        "transport_kind": transport_kind,
        "result_digest": terminal.result_digest,
        "stdout_sha256": terminal.stdout_sha256,
        "producer_worker": need.worker_ref.carrier_id,
        "wait_activation_id": result.wait_activation.activation_id,
        "external_return_event_id": result.facts["external_return_event_id"],
        "downstream_fired_threads": ",".join(result.facts["downstream_fired_threads"]),
    }
    resonances = {r.resonance_id: r for r in ledger.resonances_for_run(run_id)}
    page = render_html(
        run_record=run_record,
        ledger=ledger,
        sediment=engine.sediment,
        resonances=resonances,  # type: ignore[arg-type]
        thread_specs=engine.thread_specs,
        title=f"SESHAT Phase B carpet - {run_id}",
    )
    page = page.replace("</body>", _provenance_html(facts) + "</body>", 1)

    files: dict[str, bytes] = {
        "stones.json": _json_doc(operator_stone_events(ledger, run_id)),
        "events.jsonl": _jsonl(all_run_events(ledger, run_id)),
        "waves.jsonl": _jsonl(
            [w.model_dump(mode="python") for w in ledger.waves if w.run_id == run_id]
        ),
        "activations.jsonl": _jsonl(
            [a.model_dump(mode="python") for a in ledger.activations_for_run(run_id)]
        ),
        "sediment.json": _json_doc(sediment_records_for_run(ledger, engine.sediment, run_id)),
        "resonances.json": _json_doc([r.model_dump(mode="python") for r in resonances.values()]),
        "carpet.html": page.encode("utf-8"),
        "research_needs.jsonl": _jsonl(
            [n.model_dump(mode="json") for n in engine.external_ledger.research_needs]
        ),
        "job_dispatch.jsonl": _jsonl(
            [
                {
                    "host_job_id": host_job_id,
                    "hub_job_id": spec.hub_job_id,
                    "ticket": spec.ticket,
                    "spec": spec.model_dump(mode="json"),
                    "spec_sha256": spec.spec_sha256(),
                    "prompt_sha256": spec.prompt_sha256,
                    "original_request_sha256": job.request_sha256,
                    "request_pin_sha256": spec.request_pin_sha256,
                    "origin": job.origin,
                    "submissions": submissions,
                }
            ]
        ),
        "independent_host_job_receipts.jsonl": _jsonl(
            [
                {
                    "host_job_id": host_job_id,
                    "host_receipt": result.evidence.host_receipt.model_dump(mode="json"),
                    "binding_hash_note": "UNKEYED_SHA256_CORRELATION_NOT_AUTHENTICATION",
                    "hub_record": record,
                    "hub_receipt_sha256": terminal.receipt_sha256,
                    "issuer_authentication": auth_mode,
                    "terminal_status": terminal.status,
                }
            ]
        ),
        "terminal_output_sha.jsonl": _jsonl(
            [
                {
                    "host_job_id": host_job_id,
                    "hub_job_id": spec.hub_job_id,
                    "stdout_sha256": terminal.stdout_sha256,
                    "stdout_len": len(terminal.stdout_bytes),
                    "result_digest": terminal.result_digest,
                    "receipt_sha256": terminal.receipt_sha256,
                }
            ]
        ),
        "evidence_returns.jsonl": _jsonl(
            [e.model_dump(mode="json") for e in engine.external_ledger.evidence_returns]
        ),
        "resume_receipt.json": _json_doc(
            {
                "mode": result.mode,
                "run_id": run_id,
                "request_id": need.request_id,
                "host_job_id": host_job_id,
                "resume_outcome": result.run_record.outcome.value,
                "ledger_head_hash": run_ledger_head_hash(ledger, run_id),
                "causal_facts": result.facts,
                "state_restoration": (
                    "NOT_RESTORED_DETERMINISTIC_REPLAY_COMPARED_TO_HOST_ORIGINALS"
                    if result.mode == PHASE_B_REPLAY_VERIFIED
                    else "SINGLE_PROCESS_IN_MEMORY_ENGINE"
                ),
            }
        ),
    }
    if set(files) != set(PHASE_B_ARTIFACTS):
        raise HostBoundaryError("PHASE_B_ARTIFACT_SET_MISMATCH")
    for name in PHASE_B_ARTIFACTS:
        atomic_write_bytes(output_dir / name, files[name])
    digests = {
        name: {
            "sha256": hashlib.sha256((output_dir / name).read_bytes()).hexdigest(),
            "byte_length": len((output_dir / name).read_bytes()),
        }
        for name in PHASE_B_ARTIFACTS
    }
    receipt = {
        "schema": "seshat.phase_b.receipt.v1",
        "mode": result.mode,
        "transport_kind": transport_kind,
        "issuer_authentication": auth_mode,
        "artifact_file_digests": digests,
        "host_module_digests": host_module_digests(),
        "git": _git_meta_safe(),
        "claims": {
            "fake_host_executor_used": False,
            "live_model_call_in_this_authoring_run": False,
            "binding_hash_is_authentication": False,
            "scientific_method_accepted": False,
        },
        "known_limits": [
            "HUB_RECORD_NORMALIZED_SCHEMA_UNVERIFIED_AGAINST_CALLER_PROTOCOL",
            "ISSUER_AUTH_IS_REGISTRY_PINS_ONLY_UNLESS_HMAC_KEY_CONFIGURED",
            "SQLITE_ROW_DIGESTS_DETECT_EDITS_NOT_DELETION_BY_A_TRIGGER_DROPPING_ATTACKER",
        ],
    }
    atomic_write_bytes(output_dir / "receipt.json", _json_doc(receipt))
    return receipt


__all__ = [
    "ENGINE_FACTORIES",
    "PHASE_B_ARTIFACTS",
    "PHASE_B_LIVE_IN_PROCESS_ONLY",
    "PHASE_B_REPLAY_VERIFIED",
    "PHASE_B_REQUIRED",
    "TRANSPORT_KIND_HUB_SPOOL_RECORD",
    "TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT",
    "OriginManifest",
    "ResumeResult",
    "WaitingRun",
    "causal_facts",
    "export_phase_b_artifacts",
    "host_module_digests",
    "resume_by_replay",
    "resume_live",
    "start_waiting_run",
]
