"""The deterministic wave engine.

This is the heart of the fabric prototype.  It composes the stone dispatcher,
the frontier selector, the propagation layer, the method-body registry and the
sediment ledger into a single bounded, deterministic run.

Invariants:

* No universal mandatory ``cut → derive → analyze`` pipeline.
* A thread fires only if its propagation law and edge conditions are satisfied.
* Acceptance to ACCEPTED is human authority; the engine never promotes.
* Activation outcomes are typed; SATURATED_NO_DELTA is the engine's honest
  signal that a thread has nothing new to add.
* Replay is byte-for-byte identical for the same input and seed.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    F07_GAP,
    ActivationOutcome,
    ActivationRecord,
    DecisionRecord,
    EpistemicLevel,
    FabricRunOutcome,
    FabricStopReason,
    PropagationLaw,
    RunRecord,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WaveBudget,
    WaveRecord,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.decision_gate import (
    TrustedDecisionAttestation,
    accept_with_attestation,
)
from seshat.fabric_waves.errors import sanitize_provider_error, sanitize_receipt_material
from seshat.fabric_waves.frontier import (
    LexicographicFrontierStrategy,
    _condition_holds,
    select_frontier,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import (
    BodyInvocation,
    BodyResult,
    MethodBodyRegistry,
    MethodBodyViolation,
)
from seshat.fabric_waves.operator_ingress import (
    AdmittedOperatorQuery,
    OperatorAdmissionError,
    admit_aporia_context_note,
    admit_operator_query,
)
from seshat.fabric_waves.propagation import (
    invalidate_cascade,
    threads_woken_by_carrier_delta,
)
from seshat.fabric_waves.resonance import (
    ResonanceComposer,
    frontier_gap,
    map_view,
)
from seshat.fabric_waves.resonance import (
    answer as compose_answer,
)
from seshat.fabric_waves.resonance import (
    decision_request as compose_decision_request,
)
from seshat.fabric_waves.resonance import (
    question as compose_question,
)
from seshat.fabric_waves.resonance import (
    report as compose_report,
)
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.fabric_waves.stone import StoneDispatcher, StoneQueueFull
from seshat.fabric_waves.external_carrier.contracts import (
    ExternalResumeReceipt,
    material_hash,
)
from seshat.fabric_waves.external_carrier.ledger import ExternalCarrierLedger
from seshat.fabric_waves.external_carrier.port import (
    ExecutorPort,
    ExternalAdmissionError,
    verify_resume_receipt,
)


@dataclass
class _WaitingRunState:
    budget: WaveBudget
    waves_emitted: int
    activations_total: int
    stone_events_used: int
    thread_activations: dict[str, int]
    last_wave_thread_ids: tuple[str, ...]
    initial_versions: dict[str, str]
    start_tick: int
    decision_ids: list[str]
    request_id: str


class WaveEngineConfigurationError(ValueError):
    """Engine misconfigured: missing propagation law, unknown thread, etc."""


class WaveEngineStateError(RuntimeError):
    """Engine found itself in an internally inconsistent state."""


def _canonical_json(value: Any) -> str:
    def default(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="python", exclude_none=False)
        raise TypeError(f"non-JSON value of type {type(value).__name__}")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=default,
    )


def _material_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class WaveEngine:
    """Drive one bounded run over the carpet."""

    def __init__(
        self,
        *,
        thread_specs: Mapping[str, WorkflowThreadSpec],
        propagation_laws: Mapping[str, PropagationLaw],
        sediment: SedimentState,
        bodies: MethodBodyRegistry,
        ledger: RunLedger | None = None,
        dispatcher: StoneDispatcher | None = None,
        resonance_composer: ResonanceComposer | None = None,
        carrier_store: FabricCarrierStore | None = None,
        decision_verifier: Any = None,
    ) -> None:
        if set(thread_specs) != set(propagation_laws):
            raise WaveEngineConfigurationError(
                "thread_specs and propagation_laws must share keys"
            )
        for spec in thread_specs.values():
            for ref in spec.method_body_refs:
                if not bodies.has(ref):
                    raise WaveEngineConfigurationError(
                        f"method body {ref.method_body_id}@{ref.version} "
                        f"is not registered (thread {spec.thread_id})"
                    )
        self.thread_specs = dict(thread_specs)
        self.propagation_laws = dict(propagation_laws)
        self.sediment = sediment
        self.bodies = bodies
        self.ledger = ledger or RunLedger()
        self.dispatcher = dispatcher or StoneDispatcher()
        self.resonance_composer = resonance_composer or ResonanceComposer()
        self.carrier_store = carrier_store
        self.decision_verifier = decision_verifier
        self._decision_nonces: set[tuple[str, str]] = set()
        self._snapshots: dict[str, Any] = {}
        self._event_limit_hit = False
        self._governance_hold = False
        self._operator_query_by_event: dict[tuple[str, str], AdmittedOperatorQuery] = {}
        self._run_prior_aporia: set[str] = set()
        self.external_ledger: ExternalCarrierLedger = ExternalCarrierLedger()
        self.executor_port: ExecutorPort | None = None
        self.external_proposal_sediment_id: str | None = None
        self._waiting_runs: dict[str, _WaitingRunState] = {}

    # -- helpers -------------------------------------------------------------

    def _validate_specs(self) -> None:
        for spec in self.thread_specs.values():
            seen_outputs: set[str] = set()
            for node in spec.nodes:
                if node.produces_sediment_id is not None:
                    if node.produces_sediment_id in seen_outputs:
                        raise WaveEngineConfigurationError(
                            f"thread {spec.thread_id!r} has duplicate output sediment_id "
                            f"{node.produces_sediment_id!r}"
                        )
                    seen_outputs.add(node.produces_sediment_id)

    def _tick(self) -> int:
        run = self.ledger.runs[-1] if self.ledger.runs else None
        activations = self.ledger.activations
        ticks = [
            run.started_at_tick if run else 0,
            *(act.ended_at_tick for act in activations),
            *(wave_record.wave_index for wave_record in self.ledger.waves),
        ]
        return (max(ticks) if ticks else 0) + 1

    # -- run -----------------------------------------------------------------

    def run(
        self,
        *,
        run_id: str,
        budget: WaveBudget,
        initial_stone: StoneEvent | None = None,
        auto_answer: bool = True,
        resume_continuation: bool = False,
    ) -> RunRecord:
        self._validate_specs()
        self._event_limit_hit = False
        self._governance_hold = False
        if not resume_continuation and any(item.run_id == run_id for item in self.ledger.runs):
            raise WaveEngineConfigurationError(f"run_id {run_id!r} already used")
        waiting_state = self._waiting_runs.pop(run_id, None) if resume_continuation else None
        start_tick = self._tick()
        if resume_continuation and waiting_state is not None:
            start_tick = waiting_state.start_tick
            initial_event = self.dispatcher.pending[0] if self.dispatcher.pending else StoneEvent(
                event_id=f"{run_id}:resume",
                kind=StoneEventKind.SEDIMENT_AVAILABLE,
                issued_at_tick=start_tick,
                payload={"resume": True},
            )
        elif initial_stone is not None:
            initial_event = initial_stone.model_copy(deep=True)
            self._drop_stone(initial_event, budget=budget)
        elif not self.dispatcher.pending:
            initial_event = StoneEvent(
                event_id=f"{run_id}:init",
                kind=StoneEventKind.QUERY,
                issued_at_tick=start_tick,
                payload={"auto": True},
            )
            self._drop_stone(initial_event, budget=budget)
        else:
            initial_event = self.dispatcher.pending[0].model_copy(deep=True)

        if waiting_state is not None:
            initial_versions = waiting_state.initial_versions
            activations_total = waiting_state.activations_total
            stone_events_used = waiting_state.stone_events_used
            thread_activations = dict(waiting_state.thread_activations)
            waves_emitted = waiting_state.waves_emitted
            decision_ids = list(waiting_state.decision_ids)
            last_wave_thread_ids = waiting_state.last_wave_thread_ids
        else:
            initial_versions = self.sediment.version_map()
            activations_total = 0
            stone_events_used = 0
            thread_activations = dict.fromkeys(self.thread_specs, 0)
            waves_emitted = 0
            decision_ids = []
            last_wave_thread_ids = ()
        thread_limit_hit = False
        waves_with_aporia = 0
        stop_reason: FabricStopReason = FabricStopReason.NO_DELTA
        outcome: FabricRunOutcome = FabricRunOutcome.SATURATED
        ledger_head_at_start = self.ledger.head_hash
        external_wait_requested = False

        while True:
            if waves_emitted >= budget.max_waves:
                stop_reason = FabricStopReason.MAX_WAVES
                outcome = FabricRunOutcome.EXHAUSTED
                break
            if activations_total >= budget.max_activations:
                stop_reason = FabricStopReason.MAX_ACTIVATIONS
                outcome = FabricRunOutcome.EXHAUSTED
                break
            if not self.dispatcher.pending:
                acts = self.ledger.activations_for_run(run_id)
                if external_wait_requested:
                    stop_reason = FabricStopReason.WAITING_EXTERNAL
                    outcome = FabricRunOutcome.WAITING_EXTERNAL
                    break
                if self._event_limit_hit:
                    stop_reason, outcome = FabricStopReason.BUDGET_EXHAUSTED, FabricRunOutcome.EXHAUSTED
                elif thread_limit_hit:
                    stop_reason, outcome = FabricStopReason.MAX_ACTIVATIONS, FabricRunOutcome.EXHAUSTED
                elif not acts:
                    stop_reason, outcome = FabricStopReason.INVALID_THREAD, FabricRunOutcome.BLOCKED
                elif any(a.outcome in (ActivationOutcome.ERROR, ActivationOutcome.BLOCKED_SOURCE,
                                     ActivationOutcome.BLOCKED_PROVIDER) for a in acts):
                    stop_reason, outcome = FabricStopReason.PROVIDER_ERROR, FabricRunOutcome.BLOCKED
                elif any(a.error_code == "BODY_APORIA" for a in acts):
                    stop_reason, outcome = FabricStopReason.APORIA_RECORDED, FabricRunOutcome.APORIA
                elif all(a.outcome is ActivationOutcome.SATURATED_NO_DELTA
                         for a in acts if a.wave_id == acts[-1].wave_id):
                    stop_reason, outcome = FabricStopReason.NO_DELTA, FabricRunOutcome.SATURATED
                else:
                    stop_reason, outcome = FabricStopReason.CONVERGED, FabricRunOutcome.CONVERGED
                break
            if stone_events_used >= budget.max_stone_events:
                stop_reason = FabricStopReason.BUDGET_EXHAUSTED
                outcome = FabricRunOutcome.EXHAUSTED
                break

            waves_emitted += 1
            if not self.dispatcher.pending:
                stop_reason = FabricStopReason.NO_DELTA
                outcome = FabricRunOutcome.SATURATED
                break
            next_stone = self.dispatcher.pending[0]
            trigger_event = self.dispatcher.consume_next(
                run_id=run_id,
                wave=WaveRecord(
                    wave_id=f"{run_id}:wave:{waves_emitted}",
                    run_id=run_id,
                    wave_index=waves_emitted,
                    triggered_by=next_stone.kind,
                    triggering_event_id=next_stone.event_id,
                    eligible_thread_ids=(),
                    fired_thread_ids=(),
                    no_delta_thread_ids=(),
                    skipped_thread_ids=(),
                    blocked_thread_ids=(),
                    budget_used=0,
                    sediment_versions_after={},
                ),
            )
            if trigger_event is None:
                stop_reason = FabricStopReason.NO_DELTA
                outcome = FabricRunOutcome.SATURATED
                break
            consumed_record = self.dispatcher.last_consumed()
            if consumed_record is not None:
                self.ledger.append_event(consumed_record)
                stone_events_used += 1

            if trigger_event.kind is StoneEventKind.SOURCE_DELTA:
                try:
                    self._apply_source_delta(trigger_event)
                except Exception:
                    stop_reason, outcome = FabricStopReason.SOURCE_DENIED, FabricRunOutcome.BLOCKED
                    self.ledger.append_wave(WaveRecord(
                        wave_id=f"{run_id}:wave:{waves_emitted}", run_id=run_id,
                        wave_index=waves_emitted, triggered_by=trigger_event.kind,
                        triggering_event_id=trigger_event.event_id,
                        sediment_versions_after=self.sediment.version_map()))
                    break

            if trigger_event.kind is StoneEventKind.APORIA:
                self._governance_hold = True
                try:
                    admit_aporia_context_note(trigger_event.payload)
                    self._run_prior_aporia.add(run_id)
                except OperatorAdmissionError:
                    stop_reason = FabricStopReason.INVALID_STONE
                    outcome = FabricRunOutcome.BLOCKED
                    self.ledger.append_wave(
                        WaveRecord(
                            wave_id=f"{run_id}:wave:{waves_emitted}",
                            run_id=run_id,
                            wave_index=waves_emitted,
                            triggered_by=trigger_event.kind,
                            triggering_event_id=trigger_event.event_id,
                            sediment_versions_after=self.sediment.version_map(),
                        )
                    )
                    break
                self.ledger.append_wave(
                    WaveRecord(
                        wave_id=f"{run_id}:wave:{waves_emitted}",
                        run_id=run_id,
                        wave_index=waves_emitted,
                        triggered_by=trigger_event.kind,
                        triggering_event_id=trigger_event.event_id,
                        sediment_versions_after=self.sediment.version_map(),
                    )
                )
                continue

            if trigger_event.kind is StoneEventKind.HUMAN_DECISION:
                self._apply_human_decision_stone(
                    run_id=run_id,
                    event=trigger_event,
                    decision_ids=decision_ids,
                    ended_tick=self._tick(),
                )
                self.ledger.append_wave(
                    WaveRecord(
                        wave_id=f"{run_id}:wave:{waves_emitted}",
                        run_id=run_id,
                        wave_index=waves_emitted,
                        triggered_by=trigger_event.kind,
                        triggering_event_id=trigger_event.event_id,
                        sediment_versions_after=self.sediment.version_map(),
                    )
                )
                continue

            admits_operator_query = any(
                spec.accepts_operator_query for spec in self.thread_specs.values()
            )
            if (
                admits_operator_query
                and trigger_event.kind is StoneEventKind.QUERY
                and trigger_event.payload != {"auto": True}
            ):
                try:
                    prior_aporia = run_id in self._run_prior_aporia
                    if prior_aporia:
                        self._run_prior_aporia.discard(run_id)
                    admitted = admit_operator_query(
                        run_id=run_id,
                        event=trigger_event,
                        prior_aporia_context=prior_aporia,
                    )
                    if admitted.scope_thread_id is not None:
                        scope_spec = self.thread_specs.get(admitted.scope_thread_id)
                        if scope_spec is None or not scope_spec.accepts_operator_query:
                            raise OperatorAdmissionError("OPERATOR_QUERY_SCOPE_DENIED")
                except OperatorAdmissionError:
                    stop_reason = FabricStopReason.INVALID_STONE
                    outcome = FabricRunOutcome.BLOCKED
                    self.ledger.append_wave(
                        WaveRecord(
                            wave_id=f"{run_id}:wave:{waves_emitted}",
                            run_id=run_id,
                            wave_index=waves_emitted,
                            triggered_by=trigger_event.kind,
                            triggering_event_id=trigger_event.event_id,
                            sediment_versions_after=self.sediment.version_map(),
                        )
                    )
                    break
                self._operator_query_by_event[(run_id, trigger_event.event_id)] = admitted

            # The engine respects the budget on activations, not on waves.
            if activations_total >= budget.max_activations:
                stop_reason = FabricStopReason.MAX_ACTIVATIONS
                outcome = FabricRunOutcome.EXHAUSTED
                break

            wave_record_id = f"{run_id}:wave:{waves_emitted}"
            wave = WaveRecord(
                wave_id=wave_record_id,
                run_id=run_id,
                wave_index=waves_emitted,
                triggered_by=trigger_event.kind,
                triggering_event_id=trigger_event.event_id,
                eligible_thread_ids=(),
                fired_thread_ids=(),
                no_delta_thread_ids=(),
                skipped_thread_ids=(),
                blocked_thread_ids=(),
                budget_used=0,
                sediment_versions_after={},
            )
            frontier = select_frontier(
                thread_specs=self.thread_specs,
                propagation_laws=self.propagation_laws,
                sediment=self.sediment,
                event=trigger_event,
                last_wave_thread_ids=last_wave_thread_ids,
                strategy=LexicographicFrontierStrategy(),
            )

            if trigger_event.kind is StoneEventKind.SOURCE_DELTA:
                carrier_id = trigger_event.target_carrier_id
                if carrier_id is not None:
                    invalidate_cascade(carrier_id=carrier_id, sediment=self.sediment)
                    affected_ids = set(
                        threads_woken_by_carrier_delta(
                            carrier_id=carrier_id,
                            thread_specs=self.thread_specs,
                            propagation_laws=self.propagation_laws,
                            sediment=self.sediment,
                        )
                    )
                    frontier = tuple(
                        proposal
                        for proposal in frontier
                        if proposal.thread_id in affected_ids
                    )

            fired: list[str] = []
            no_delta: list[str] = []
            skipped: list[str] = []
            blocked: list[str] = []
            wave_activations = 0
            for proposal in frontier:
                spec = self.thread_specs[proposal.thread_id]
                if not spec.nodes:
                    skipped.append(proposal.thread_id)
                    continue
                thread_blocked = False
                for node in spec.nodes:
                    if not all(_condition_holds(c, self.sediment, set(last_wave_thread_ids),
                                                trigger_event) for c in node.conditions):
                        skipped.append(spec.thread_id)
                        continue
                    if not all(
                        sid in self.sediment.views["working"]
                        or sid in self.sediment.views["candidate"]
                        for sid in node.consumes_sediment_ids
                    ):
                        skipped.append(spec.thread_id)
                        continue
                    if thread_activations[spec.thread_id] >= spec.bounded_budget_hint:
                        thread_limit_hit = True
                        blocked.append(spec.thread_id)
                        thread_blocked = True
                        break
                    if activations_total >= budget.max_activations:
                        blocked.append(proposal.thread_id)
                        thread_blocked = True
                        break
                    activations_total += 1
                    thread_activations[spec.thread_id] += 1
                    wave_activations += 1
                    activation = self._invoke_node(
                        run_id=run_id,
                        wave_id=wave_record_id,
                        spec=spec,
                        node=node,
                        stone=trigger_event,
                    )
                    self.ledger.append_activation(activation)
                    if activation.outcome is ActivationOutcome.WAITING_EXTERNAL:
                        external_wait_requested = True
                        fired.append(spec.thread_id)
                    elif activation.outcome is ActivationOutcome.FIRED:
                        fired.append(spec.thread_id)
                        stone_events_used = self._enqueue_causal_events(
                            run_id=run_id,
                            wave_id=wave_record_id,
                            activation=activation,
                            budget=budget,
                            stone_events_used=stone_events_used,
                        )
                    elif activation.outcome is ActivationOutcome.SATURATED_NO_DELTA:
                        no_delta.append(spec.thread_id)
                    elif activation.outcome in (
                        ActivationOutcome.BLOCKED_SOURCE,
                        ActivationOutcome.BLOCKED_PROVIDER,
                    ):
                        blocked.append(proposal.thread_id)
                        thread_blocked = True
                    else:
                        skipped.append(spec.thread_id)
                if thread_blocked:
                    continue

            wave = wave.model_copy(
                update={
                    "eligible_thread_ids": tuple(p.thread_id for p in frontier),
                    "fired_thread_ids": tuple(sorted(set(fired))),
                    "no_delta_thread_ids": tuple(sorted(set(no_delta))),
                    "skipped_thread_ids": tuple(sorted(set(skipped))),
                    "blocked_thread_ids": tuple(sorted(set(blocked))),
                    "budget_used": wave_activations,
                    "sediment_versions_after": self.sediment.version_map(),
                }
            )
            self.ledger.append_wave(wave)
            last_wave_thread_ids = wave.fired_thread_ids

            if external_wait_requested:
                stop_reason = FabricStopReason.WAITING_EXTERNAL
                outcome = FabricRunOutcome.WAITING_EXTERNAL
                break

            # Bookkeeping of saturation / aporia
            # APORIA detection: any activation recorded an aporia note
            aporia_seen = any(
                act.error_code == "BODY_APORIA"
                for act in self.ledger.activations_for_wave(wave.wave_id)
            )
            if aporia_seen:
                waves_with_aporia += 1
                if waves_with_aporia >= budget.aporia_after_waves:
                    stop_reason = FabricStopReason.APORIA_RECORDED
                    outcome = FabricRunOutcome.APORIA
                    self.resonance_composer.add(
                        frontier_gap(
                            run_id=run_id,
                            resonance_id=f"{run_id}:resonance:gap:{waves_emitted}",
                            tick=wave.wave_index,
                            gap_id=F07_GAP,
                            description="Bodies reported aporia; refusing to continue past the bounded threshold.",
                            blocked_thread_ids=tuple(sorted(set(blocked))),
                        )
                    )
                    self.ledger.append_resonance(self.resonance_composer.values()[-1])
                    break
                continue

        end_tick = self._tick()
        run_record = RunRecord(
            run_id=run_id,
            started_at_tick=start_tick,
            ended_at_tick=end_tick,
            outcome=outcome,
            stop_reason=stop_reason,
            budget=budget,
            sediment_initial_versions=initial_versions,
            sediment_final_versions=self.sediment.version_map(),
            waves_emitted=waves_emitted,
            activations_total=activations_total,
            decision_ids=tuple(decision_ids),
            resonance_ids=tuple(
                record.resonance_id for record in self.resonance_composer.values()
            ),
            ledger_head_hash=self.ledger.head_hash,
            notes=("deterministic_run",) if ledger_head_at_start else (),
        )
        if auto_answer and outcome is not FabricRunOutcome.WAITING_EXTERNAL:
            self._autoresonance(run_id, run_record)
        run_record = run_record.model_copy(update={
            "resonance_ids": tuple(r.resonance_id for r in self.ledger.resonances_for_run(run_id)),
            "ledger_head_hash": self.ledger.head_hash,
        }, deep=True)
        if outcome is FabricRunOutcome.WAITING_EXTERNAL:
            self._waiting_runs[run_id] = _WaitingRunState(
                budget=budget,
                waves_emitted=waves_emitted,
                activations_total=activations_total,
                stone_events_used=stone_events_used,
                thread_activations=thread_activations,
                last_wave_thread_ids=last_wave_thread_ids,
                initial_versions=initial_versions,
                start_tick=start_tick,
                decision_ids=decision_ids,
                request_id=next(
                    (
                        need.request_id
                        for need in reversed(self.external_ledger.research_needs)
                        if need.run_id == run_id
                    ),
                    "",
                ),
            )
            self._snapshots[run_id] = deepcopy(
                (self.ledger, self.sediment, self.resonance_composer)
            )
            if auto_answer:
                self._autoresonance(run_id, run_record)
            return run_record.model_copy(
                update={
                    "resonance_ids": tuple(
                        r.resonance_id for r in self.ledger.resonances_for_run(run_id)
                    ),
                    "ledger_head_hash": self.ledger.head_hash,
                },
                deep=True,
            )
        self.ledger.append_run(run_record)
        self._snapshots[run_id] = deepcopy((self.ledger, self.sediment, self.resonance_composer))
        return run_record

    def snapshot(self, run_id: str) -> Any:
        """Detached end-of-run state; subsequent runs cannot alter exports."""
        return deepcopy(self._snapshots[run_id])

    def _drop_stone(self, event: StoneEvent, *, budget: WaveBudget) -> None:
        if len(self.dispatcher.pending) >= budget.max_stone_events:
            raise WaveEngineConfigurationError("max_stone_events budget exhausted before run")
        self.dispatcher.drop(event)

    def _apply_source_delta(self, event: StoneEvent) -> None:
        carrier_id = event.target_carrier_id
        if carrier_id is None or self.carrier_store is None:
            raise ValueError("SOURCE_REVISION_UNVERIFIED")
        payload = event.payload
        if not all(isinstance(payload.get(k), str) and payload[k]
                   for k in ("old_version", "new_version", "text")):
            raise ValueError("SOURCE_REVISION_INCOMPLETE")
        new_version = payload["new_version"]
        new_text = payload["text"]
        self.carrier_store.apply_delta(
            carrier_id,
            new_version=new_version,
            new_text=new_text,
            old_version=payload["old_version"],
        )
        for need in self.external_ledger.research_needs:
            if carrier_id in need.source_carrier_ids:
                self.external_ledger.mark_stale(need.request_id)

    def _enqueue_causal_events(
        self,
        *,
        run_id: str,
        wave_id: str,
        activation: ActivationRecord,
        budget: WaveBudget,
        stone_events_used: int,
    ) -> int:
        tick = self._tick()
        for sediment_id in activation.produced_sediment_ids:
            record = self.sediment.views["working"].get(sediment_id)
            if record is None:
                record = self.sediment.views["candidate"].get(sediment_id)
            if record is None:
                continue
            if stone_events_used + len(self.dispatcher.pending) >= budget.max_stone_events:
                self._event_limit_hit = True
                return stone_events_used
            event = StoneEvent(
                event_id=f"{activation.activation_id}:sediment:{sediment_id}:{record.version}",
                kind=StoneEventKind.SEDIMENT_AVAILABLE,
                parent_activation_id=activation.activation_id,
                issued_at_tick=tick,
                payload={
                    "sediment_id": sediment_id,
                    "object_type": record.object_type,
                    "version": record.version,
                    "parent_activation_id": activation.activation_id,
                    "parent_wave_id": wave_id,
                },
            )
            try:
                self.dispatcher.drop(event)
            except StoneQueueFull:
                self._event_limit_hit = True
                return stone_events_used
            if record.object_type == "safe.repair_signal":
                target = record.payload.get("target_thread_id")
                if target and stone_events_used + len(self.dispatcher.pending) < budget.max_stone_events:
                    repair = StoneEvent(
                        event_id=f"{run_id}:repair:{sediment_id}",
                        kind=StoneEventKind.RECONCILE_REQUEST,
                        issued_at_tick=tick,
                        target_thread_id=str(target),
                        parent_activation_id=activation.activation_id,
                        payload={"subject_sediment_id": sediment_id},
                    )
                    self.dispatcher.drop(repair)
                elif target:
                    self._event_limit_hit = True
        return stone_events_used

    def _resolve_body_ref(
        self, spec: WorkflowThreadSpec, node: ThreadNodeSpec
    ) -> Any:
        ref = node.method_body_ref
        if ref is None or ref not in spec.method_body_refs or not self.bodies.has(ref):
            return None
        if not self.bodies.supports(ref, node.operation_id):
            return None
        return ref

    def _validate_and_deposit(
        self,
        *,
        node: ThreadNodeSpec,
        record: SedimentRecord,
        consumed_ids: tuple[str, ...],
    ) -> SedimentRecord:
        record = SedimentRecord.model_validate(record.model_dump())
        declared = node.output_contracts or {node.produces_sediment_id: node.output_sediment_type}
        if record.sediment_id not in declared:
            raise MethodBodyViolation("OUTPUT_ID_MISMATCH")
        if record.object_type != declared[record.sediment_id]:
            raise MethodBodyViolation(
                f"object_type {record.object_type!r} != declared {node.output_sediment_type!r}"
            )
        if record.payload_hash != payload_hash(record.payload):
            raise MethodBodyViolation("OUTPUT_HASH_MISMATCH")
        if record.version != record.payload_hash:
            raise MethodBodyViolation("OUTPUT_VERSION_MISMATCH")
        if record.method_body_refs != (node.method_body_ref,):
            raise MethodBodyViolation("OUTPUT_METHOD_MISMATCH")
        dep_versions = {
            sid: self.sediment.version_map().get(sid, "")
            for sid in consumed_ids
            if sid in self.sediment.version_map()
        }
        record = record.model_copy(
            update={"dependency_versions": dep_versions},
            deep=True,
        )
        return record

    # -- per-node invocation -------------------------------------------------

    def _invoke_node(
        self, *, run_id: str, wave_id: str, spec: WorkflowThreadSpec,
        node: ThreadNodeSpec, stone: StoneEvent,
    ) -> ActivationRecord:
        """Contain all provider, serializer and late-deposit diagnostics."""
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                return self._invoke_node_inner(run_id=run_id, wave_id=wave_id,
                                                spec=spec, node=node, stone=stone)
        except Exception:
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:boundary",
                run_id=run_id, wave_id=wave_id, thread_id=spec.thread_id,
                started_at_tick=self._tick(), ended_at_tick=self._tick(),
                outcome=ActivationOutcome.ERROR, error_code="BODY_EXCEPTION",
                error_detail="BODY_EXCEPTION", receipts_hash=_material_hash({"code": "BODY_EXCEPTION"}))

    def _invoke_node_inner(
        self,
        *,
        run_id: str,
        wave_id: str,
        spec: WorkflowThreadSpec,
        node: ThreadNodeSpec,
        stone: StoneEvent,
    ) -> ActivationRecord:
        resolved_ref = self._resolve_body_ref(spec, node)
        if resolved_ref is None:
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:bad",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=self._tick(),
                ended_at_tick=self._tick(),
                outcome=ActivationOutcome.BLOCKED_PROVIDER,
                stop_reason=FabricStopReason.PROVIDER_ERROR.value,
                receipts_hash=_material_hash({"error": "no_method_body_resolved"}),
                error_code="MISSING_METHOD_BODY",
                error_detail=f"thread {spec.thread_id!r} could not resolve any method body",
            )
        body = self.bodies.resolve(resolved_ref)
        consumed_ids = self._consumed_sediments_for(node, spec.thread_id)
        candidate_sediments: list[Any] = []
        if consumed_ids:
            for sid in consumed_ids:
                record = self.sediment.views["working"].get(sid)
                if record is None:
                    record = self.sediment.views["candidate"].get(sid)
                if record is not None:
                    candidate_sediments.append(record)
        carriers = self._carriers_for_thread(spec, stone)
        try:
            if stone.target_carrier_id and stone.target_carrier_id not in spec.admissible_source_carriers:
                raise ValueError("SOURCE_TARGET_DENIED")
            if self.carrier_store is not None and carriers:
                source_payload, manifest = self.carrier_store.resolve_payload(
                    policy=spec.raw_access_policy,
                    carrier_ids=carriers,
                    stone_payload=stone.payload,
                    operation_id=node.operation_id,
                )
            elif spec.raw_access_policy.value == "NEVER":
                source_payload = {"text": "", "values": []}
                manifest = None
            else:
                raise ValueError("TRUSTED_SOURCE_ACCESS_REQUIRED")
        except Exception as exc:  # noqa: BLE001
            code, detail = sanitize_provider_error(
                code="SOURCE_ACCESS_DENIED",
                internal_message=str(exc),
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}",
            )
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:src",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=self._tick(),
                ended_at_tick=self._tick(),
                outcome=ActivationOutcome.BLOCKED_SOURCE,
                stop_reason=FabricStopReason.SOURCE_DENIED.value,
                receipts_hash=_material_hash({"code": code}),
                error_code=code,
                error_detail=detail,
            )
        pin_carriers, pin_versions = self._transitive_source_pins(consumed_ids)
        carried_payload = {
            "run_id": run_id,
            "wave_id": wave_id,
            "stone_payload": {},
            "output_sediment_id": node.produces_sediment_id,
            "research_object_id": stone.target_research_object_id or spec.thread_id,
            "carriers": carriers,
            "text": source_payload.get("text", ""),
            "values": source_payload.get("values", []),
            "candidate_sediments": candidate_sediments,
            "source_access_manifest": manifest,
            "transitive_source_carrier_ids": pin_carriers,
            "transitive_source_versions": pin_versions,
            "governance_hold": self._governance_hold,
        }
        if spec.accepts_operator_query and stone.kind is StoneEventKind.QUERY:
            admitted = self._operator_query_by_event.get((run_id, stone.event_id))
            if admitted is not None and (
                admitted.scope_thread_id is None or admitted.scope_thread_id == spec.thread_id
            ):
                carried_payload["operator_query"] = admitted.model_dump(mode="python")
                carried_payload["topic"] = admitted.topic
                carried_payload["query"] = admitted.query
        invocation = BodyInvocation(
            thread_id=spec.thread_id,
            node_id=node.node_id,
            method_body_ref=resolved_ref,
            stone_kind=stone.kind,
            tick=self._tick(),
            wave_index=int(wave_id.rsplit(":", 1)[-1]),
            consumed_sediment_ids=consumed_ids,
            carried_payload=carried_payload,
        )
        try:
            # Provider console output is untrusted, just like its exceptions.
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                result = body(invocation)
            if not isinstance(result, BodyResult):
                raise MethodBodyViolation("INVALID_BODY_RESULT")
        except MethodBodyViolation as exc:
            code, detail = sanitize_provider_error(
                code="BODY_VIOLATION",
                internal_message=str(exc),
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}",
            )
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:err",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=invocation.tick,
                ended_at_tick=invocation.tick,
                outcome=ActivationOutcome.ERROR,
                stop_reason=FabricStopReason.PROVIDER_ERROR.value,
                receipts_hash=_material_hash(
                    sanitize_receipt_material({"error": str(exc)})
                ),
                method_body_refs=(resolved_ref,),
                error_code=code,
                error_detail=detail,
            )
        except Exception as exc:  # noqa: BLE001 - bodies may raise on bad input
            code, detail = sanitize_provider_error(
                code="BODY_EXCEPTION",
                internal_message=f"{type(exc).__name__}: {exc}",
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}",
            )
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:exc",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=invocation.tick,
                ended_at_tick=invocation.tick,
                outcome=ActivationOutcome.ERROR,
                stop_reason=FabricStopReason.PROVIDER_ERROR.value,
                receipts_hash=_material_hash(
                    sanitize_receipt_material({"error": f"{type(exc).__name__}: {exc}"})
                ),
                method_body_refs=(resolved_ref,),
                error_code=code,
                error_detail=detail,
            )

        if result.external_wait is not None:
            need = result.external_wait.request
            prior = [
                item
                for item in self.external_ledger.research_needs
                if item.run_id == run_id and item.thread_id == spec.thread_id
            ]
            if prior:
                return ActivationRecord(
                    activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:external-done",
                    run_id=run_id,
                    wave_id=wave_id,
                    thread_id=spec.thread_id,
                    started_at_tick=invocation.tick,
                    ended_at_tick=invocation.tick,
                    outcome=ActivationOutcome.SATURATED_NO_DELTA,
                    stop_reason=FabricStopReason.NO_DELTA.value,
                    read_sediment_ids=consumed_ids,
                    receipts_hash=_material_hash({"external": "already_requested"}),
                    method_body_refs=(resolved_ref,),
                )
            self.external_ledger.register_need(need)
            if self.executor_port is not None:
                job_id = self.executor_port.dispatch(need)
                self.external_ledger.agent_jobs.append(
                    {
                        "job_id": job_id,
                        "request_id": need.request_id,
                        "host_scope": need.worker_ref.host_scope,
                    }
                )
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:external-wait",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=invocation.tick,
                ended_at_tick=invocation.tick,
                outcome=ActivationOutcome.WAITING_EXTERNAL,
                stop_reason=FabricStopReason.WAITING_EXTERNAL.value,
                read_sediment_ids=consumed_ids,
                receipts_hash=_material_hash({"request_id": need.request_id}),
                method_body_refs=(resolved_ref,),
                error_code="EXTERNAL_WAIT",
                error_detail=need.request_id,
            )

        if result.aporia is not None:
            # An APORIA explanation is untrusted provider output, not public text.
            result = result.model_copy(update={"aporia": "BODY_APORIA"})
            self.sediment.deposit(
                SedimentRecord(
                    sediment_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:aporia",
                    object_type="safe.aporia",
                    version="1",
                    research_object_id=invocation.carried_payload.get(
                        "research_object_id", spec.thread_id
                    ),
                    payload={"aporia": result.aporia},
                    payload_hash=payload_hash({"aporia": result.aporia}),
                    provenance=("safe-fixture.fail-closed", f"thread={spec.thread_id}"),
                    method_body_refs=(resolved_ref,),
                    read_dependencies=consumed_ids,
                    write_dependencies=(),
                    produced_by_thread=spec.thread_id,
                    produced_at_tick=invocation.tick,
                    produced_in_wave=invocation.wave_index,
                    produced_by_stone_kind=stone.kind,
                    acceptance_state=AcceptanceState.WORKING,
                )
            )
            return ActivationRecord(
                activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:aporia",
                run_id=run_id,
                wave_id=wave_id,
                thread_id=spec.thread_id,
                started_at_tick=invocation.tick,
                ended_at_tick=invocation.tick,
                outcome=ActivationOutcome.SATURATED_NO_DELTA,
                stop_reason=FabricStopReason.APORIA_RECORDED.value,
                produced_sediment_ids=(),
                read_sediment_ids=consumed_ids,
                write_sediment_ids=(),
                source_carrier_ids=invocation.carried_payload.get("carriers", ()),
                receipts_hash=_material_hash({"aporia": result.aporia}),
                method_body_refs=(resolved_ref,),
                error_code="BODY_APORIA",
                error_detail=result.aporia,
            )

        produced_ids: list[str] = []
        before = {r.sediment_id: (r.version, r.payload_hash, r.acceptance_state)
                  for r in self.sediment.all_records()}
        # Stage all output writes so a late invalid record cannot partially commit.
        staged = deepcopy(self.sediment)
        for record in result.produced_sediments:
            try:
                if record.sediment_id in produced_ids:
                    raise MethodBodyViolation("DUPLICATE_OUTPUT_ID")
                produced_sediment = self._validate_and_deposit(
                    node=node,
                    record=record,
                    consumed_ids=consumed_ids,
                )
            except Exception as exc:
                code, detail = sanitize_provider_error(
                    code="SEDIMENT_CONTRACT_VIOLATION",
                    internal_message=str(exc),
                    activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}",
                )
                return ActivationRecord(
                    activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:contract",
                    run_id=run_id,
                    wave_id=wave_id,
                    thread_id=spec.thread_id,
                    started_at_tick=invocation.tick,
                    ended_at_tick=invocation.tick,
                    outcome=ActivationOutcome.ERROR,
                    stop_reason=FabricStopReason.PROVIDER_ERROR.value,
                    receipts_hash=_material_hash({"code": code}),
                    error_code=code,
                    error_detail=detail,
                )
            manifest = carried_payload.get("source_access_manifest")
            produced_sediment = produced_sediment.model_copy(
                update={
                    "read_dependencies": consumed_ids,
                    "write_dependencies": (),
                    "source_carrier_refs": carriers if manifest is not None else (),
                    "produced_by_thread": spec.thread_id,
                    "produced_at_tick": invocation.tick,
                    "produced_in_wave": invocation.wave_index,
                    "produced_by_stone_kind": stone.kind,
                    "source_access_manifest": manifest,
                    "provenance": produced_sediment.provenance
                    + (
                        f"thread={spec.thread_id}",
                        f"node={node.node_id}",
                        f"wave={wave_id}",
                    ),
                },
                deep=True,
            )
            if manifest is not None:
                produced_sediment = produced_sediment.model_copy(update={
                    "source_carrier_refs": carriers,
                })
            elif produced_sediment.epistemic_level is EpistemicLevel.E1:
                produced_sediment = produced_sediment.model_copy(update={"epistemic_level": EpistemicLevel.E2})
            if produced_sediment.epistemic_level is EpistemicLevel.E5:
                produced_sediment = produced_sediment.model_copy(update={"acceptance_state": AcceptanceState.PROPOSED})
            produced_sediment = produced_sediment.model_copy(update={"version": _material_hash({
                "payload_hash": produced_sediment.payload_hash,
                "dependencies": produced_sediment.dependency_versions,
                "method": resolved_ref,
                "sources": [(r.carrier_id, r.source_version, r.content_sha256)
                            for r in manifest.receipts] if manifest else [],
            })})
            try:
                staged.deposit(produced_sediment)
            except Exception:
                return ActivationRecord(
                    activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}:deposit",
                    run_id=run_id, wave_id=wave_id, thread_id=spec.thread_id,
                    started_at_tick=invocation.tick, ended_at_tick=invocation.tick,
                    outcome=ActivationOutcome.ERROR, error_code="SEDIMENT_CONTRACT_VIOLATION",
                    error_detail="SEDIMENT_CONTRACT_VIOLATION",
                    receipts_hash=_material_hash({"code": "SEDIMENT_CONTRACT_VIOLATION"}))
            produced_ids.append(produced_sediment.sediment_id)
        self.sediment._replace_from(staged)
        after = {r.sediment_id: (r.version, r.payload_hash, r.acceptance_state)
                 for r in self.sediment.all_records()}
        produced_ids = [sid for sid in produced_ids if before.get(sid) != after[sid]]
        no_delta = not produced_ids

        return ActivationRecord(
            activation_id=f"{wave_id}:{spec.thread_id}:{node.node_id}",
            run_id=run_id,
            wave_id=wave_id,
            thread_id=spec.thread_id,
            started_at_tick=invocation.tick,
            ended_at_tick=self._tick(),
            outcome=(
                ActivationOutcome.SATURATED_NO_DELTA
                if no_delta
                else ActivationOutcome.FIRED
            ),
            stop_reason=(
                FabricStopReason.NO_DELTA.value if no_delta else ""
            ),
            fired_node_ids=(node.node_id,),
            produced_sediment_ids=tuple(produced_ids),
            read_sediment_ids=consumed_ids,
            write_sediment_ids=tuple(produced_ids),
            source_carrier_ids=invocation.carried_payload.get("carriers", ()),
            receipts_hash=_material_hash(
                {
                    "produced": produced_ids,
                    "consumed": list(consumed_ids),
                    "carriers": list(invocation.carried_payload.get("carriers", ())),
                }
            ),
            method_body_refs=(resolved_ref,),
        )

    def _consumed_sediments_for(
        self, node: Any, thread_id: str
    ) -> tuple[str, ...]:
        consumed: list[str] = []
        for sid in node.consumes_sediment_ids:
            record = self.sediment.views["working"].get(sid)
            if record is not None:
                consumed.append(record.sediment_id)
            else:
                archived = self.sediment.views["stale"].get(sid)
                if archived is not None:
                    consumed.append(archived.sediment_id)
        return tuple(consumed)

    def _transitive_source_pins(
        self, consumed_ids: tuple[str, ...]
    ) -> tuple[tuple[str, ...], dict[str, str]]:
        carriers: list[str] = []
        versions: dict[str, str] = {}
        seen: set[str] = set()
        queue = list(consumed_ids)
        while queue:
            sid = queue.pop()
            if sid in seen:
                continue
            seen.add(sid)
            record = self.sediment.views["working"].get(sid)
            if record is None:
                record = self.sediment.views["candidate"].get(sid)
            if record is None:
                continue
            for cid in record.source_carrier_refs:
                if cid not in carriers:
                    carriers.append(cid)
            manifest = record.source_access_manifest
            if manifest is not None:
                for receipt in manifest.receipts:
                    versions[receipt.carrier_id] = receipt.source_version
            queue.extend(record.read_dependencies)
        return tuple(carriers), versions

    def _carriers_for_thread(
        self, spec: WorkflowThreadSpec, stone: StoneEvent
    ) -> tuple[str, ...]:
        carriers: list[str] = []
        if stone.target_carrier_id:
            carriers.append(stone.target_carrier_id)
        carriers.extend(spec.admissible_source_carriers)
        # de-dup, preserve order
        seen: set[str] = set()
        out: list[str] = []
        for carrier in carriers:
            if carrier in seen:
                continue
            seen.add(carrier)
            out.append(carrier)
        return tuple(out)

    def _deposit_external_proposal(
        self,
        *,
        sediment_id: str,
        run_id: str,
        evidence_return: Any,
        parent_activation_id: str,
    ) -> SedimentRecord:
        payload = dict(evidence_return.proposal_payload)
        digest = material_hash(payload)
        record = SedimentRecord(
            sediment_id=sediment_id,
            object_type="external.proposal",
            version=digest,
            research_object_id=run_id,
            payload=payload,
            payload_hash=digest,
            provenance=("HOST_VERIFIED_EXTERNAL_RETURN",),
            method_body_refs=(),
            source_carrier_refs=tuple(evidence_return.source_claim_refs),
            epistemic_level=EpistemicLevel.E5,
            read_dependencies=(),
            write_dependencies=(),
            produced_by_thread="external-carrier",
            produced_at_tick=self._tick(),
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.SEDIMENT_AVAILABLE,
            acceptance_state=AcceptanceState.WORKING,
        )
        self.sediment.deposit(record)
        return record

    def resume_external_evidence(
        self,
        *,
        receipt: ExternalResumeReceipt,
        budget: WaveBudget,
        port: ExecutorPort | None = None,
    ) -> RunRecord:
        run_id = receipt.run_id
        if run_id not in self._waiting_runs:
            raise WaveEngineConfigurationError(f"run {run_id!r} is not waiting for external evidence")
        try:
            evidence = verify_resume_receipt(
                ledger=self.external_ledger,
                receipt=receipt,
                port=port if port is not None else self.executor_port,
            )
        except ExternalAdmissionError as exc:
            raise WaveEngineConfigurationError(str(exc)) from exc
        proposal_id = self.external_proposal_sediment_id or f"external-proposal-{run_id}"
        record = self._deposit_external_proposal(
            sediment_id=proposal_id,
            run_id=run_id,
            evidence_return=evidence,
            parent_activation_id=f"{run_id}:external-resume",
        )
        tick = self._tick()
        self._drop_stone(
            StoneEvent(
                event_id=f"{run_id}:external-return:{evidence.request_id}",
                kind=StoneEventKind.SEDIMENT_AVAILABLE,
                issued_at_tick=tick,
                parent_activation_id=f"{run_id}:external-resume",
                payload={
                    "sediment_id": record.sediment_id,
                    "object_type": record.object_type,
                    "version": record.version,
                    "parent_activation_id": f"{run_id}:external-resume",
                    "parent_wave_id": self._waiting_runs[run_id].request_id,
                },
            ),
            budget=budget,
        )
        record = self.run(
            run_id=run_id,
            budget=budget,
            auto_answer=False,
            resume_continuation=True,
        )
        if record.outcome not in {
            FabricRunOutcome.APORIA,
            FabricRunOutcome.BLOCKED,
            FabricRunOutcome.EXHAUSTED,
            FabricRunOutcome.WAITING_EXTERNAL,
        }:
            self._autoresonance(run_id, record)
            record = record.model_copy(
                update={
                    "resonance_ids": tuple(
                        r.resonance_id for r in self.ledger.resonances_for_run(run_id)
                    ),
                    "ledger_head_hash": self.ledger.head_hash,
                },
                deep=True,
            )
        return record

    # -- human acceptance decision right ------------------------------------

    def record_human_decision(
        self,
        *,
        run_id: str,
        decision_id: str,
        subject_sediment_id: str,
        choice: str,
        rationale: str,
        accepts: Iterable[str] = (),
        rejects: Iterable[str] = (),
        tick: int | None = None,
        attestation: TrustedDecisionAttestation | None = None,
    ) -> DecisionRecord:
        if attestation is None:
            raise WaveEngineConfigurationError(
                "human acceptance requires a TrustedDecisionAttestation"
            )
        if decision_id in {item.decision_id for item in self.ledger.decisions}:
            raise WaveEngineConfigurationError(
                f"decision_id {decision_id!r} already used"
            )
        accepts, rejects = tuple(accepts), tuple(rejects)
        if (attestation.decision_id != decision_id
                or attestation.subject_sediment_id != subject_sediment_id
                or attestation.choice != choice
                or choice not in ("ACCEPT", "REJECT")
                or (accepts and accepts != (subject_sediment_id,))
                or (rejects and rejects != (subject_sediment_id,))
                or (choice == "REJECT" and accepts)
                or (choice == "ACCEPT" and rejects)
                or (attestation.issuer, attestation.nonce) in self._decision_nonces):
            raise WaveEngineConfigurationError("DECISION_BINDING_INVALID")
        if any(d.issuer == attestation.issuer and d.nonce == attestation.nonce
               for d in self.ledger.decisions):
            raise WaveEngineConfigurationError("DECISION_REPLAY")
        when = tick if tick is not None else self._tick()
        record = DecisionRecord(
            decision_id=decision_id,
            run_id=run_id,
            decided_at_tick=when,
            decided_by=attestation.decided_by,
            subject_sediment_id=subject_sediment_id,
            choice=choice,
            rationale="EXTERNALLY_ATTESTED_DECISION",
            accepts_sediment_ids=(subject_sediment_id,) if choice == "ACCEPT" else (),
            rejects_sediment_ids=(subject_sediment_id,) if choice == "REJECT" else (),
            issuer=attestation.issuer, nonce=attestation.nonce,
            subject_version=attestation.subject_version, decision_right=attestation.decision_right,
        )
        staged = deepcopy(self.sediment)
        accept_with_attestation(
            staged,
            attestation,
            decided_at_tick=when,
            verifier=self.decision_verifier,
        )
        self.ledger.append_decision(record)
        self.sediment._replace_from(staged)
        self._decision_nonces.add((attestation.issuer, attestation.nonce))
        return record.model_copy(deep=True)

    def _apply_human_decision_stone(
        self,
        *,
        run_id: str,
        event: StoneEvent,
        decision_ids: list[str],
        ended_tick: int,
    ) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        choice = str(payload.get("choice", "REJECT"))
        subject_sediment_id = str(
            payload.get("subject_sediment_id", event.target_research_object_id or "")
        )
        attestation_raw = payload.get("attestation")
        if not isinstance(attestation_raw, dict) or not subject_sediment_id:
            blocked = compose_decision_request(
                run_id=run_id,
                resonance_id=f"{run_id}:resonance:decision-blocked:{event.event_id}",
                tick=ended_tick,
                subject_sediment_id=subject_sediment_id or "unknown",
                reason="HUMAN_DECISION rejected: missing authenticated attestation envelope",
                sediments=self.sediment.all_records(),
            )
            self.resonance_composer.add(blocked)
            self.ledger.append_resonance(blocked)
            return
        attestation = TrustedDecisionAttestation.model_validate(attestation_raw)
        try:
            record = self.record_human_decision(
                run_id=run_id,
                decision_id=attestation.decision_id,
                subject_sediment_id=subject_sediment_id,
                choice=choice,
                rationale=str(payload.get("rationale", "operator_stone")),
                attestation=attestation,
                tick=ended_tick,
            )
            decision_ids.append(record.decision_id)
        except WaveEngineConfigurationError:
            blocked = compose_decision_request(
                run_id=run_id,
                resonance_id=f"{run_id}:resonance:decision-blocked:{event.event_id}",
                tick=ended_tick,
                subject_sediment_id=subject_sediment_id,
                reason="HUMAN_DECISION rejected: attestation failed host verification",
                sediments=self.sediment.all_records(),
            )
            self.resonance_composer.add(blocked)
            self.ledger.append_resonance(blocked)

    # -- auto resonance for the demo CLI -------------------------------------

    def _autoresonance(self, run_id: str, run_record: RunRecord) -> None:
        existing_ids = {r.resonance_id for r in self.ledger.resonances_for_run(run_id)}
        activations = self.ledger.activations_for_run(run_id)
        waves = tuple(item for item in self.ledger.waves if item.run_id == run_id)
        events = tuple(item for item in self.ledger.events if item.run_id == run_id)
        produced_ids = {
            sediment_id
            for activation in activations
            for sediment_id in activation.produced_sediment_ids
        }
        sediments = tuple(
            record
            for record in self.sediment.all_records()
            if record.sediment_id in produced_ids
        )
        summary = (
            f"Run {run_id} finished as {run_record.outcome.value} after "
            f"{run_record.waves_emitted} wave(s) and {run_record.activations_total} activation(s)."
        )
        blocked_outcomes = {
            FabricRunOutcome.APORIA,
            FabricRunOutcome.BLOCKED,
            FabricRunOutcome.EXHAUSTED,
            FabricRunOutcome.WAITING_EXTERNAL,
        }
        if run_record.outcome in blocked_outcomes:
            if f"{run_id}:resonance:question" in existing_ids:
                return
            question_record = compose_question(
                run_id=run_id,
                resonance_id=f"{run_id}:resonance:question",
                tick=run_record.ended_at_tick,
                question_text=summary,
                blocked_thread_ids=tuple(
                    sorted({act.thread_id for act in activations if act.error_code == "BODY_APORIA"})
                ),
                events=events,
                activations=activations,
            )
            self.resonance_composer.add(question_record)
            self.ledger.append_resonance(question_record)
        else:
            if f"{run_id}:resonance:answer" in existing_ids:
                return
            answer_record = compose_answer(
                run_id=run_id,
                resonance_id=f"{run_id}:resonance:answer",
                tick=run_record.ended_at_tick,
                summary=summary,
                activations=activations,
                sediments=sediments,
                events=events,
                waves=waves,
            )
            self.resonance_composer.add(answer_record)
            self.ledger.append_resonance(answer_record)

        nodes = [
            {"id": spec.thread_id, "label": spec.name}
            for spec in self.thread_specs.values()
        ]
        edges = []
        for wave in waves:
            for thread_id in wave.fired_thread_ids:
                edges.append({"from": f"event:{wave.triggering_event_id}", "to": thread_id})
        if f"{run_id}:resonance:map" in existing_ids:
            return
        map_record = map_view(
            run_id=run_id,
            resonance_id=f"{run_id}:resonance:map",
            tick=run_record.ended_at_tick,
            nodes=nodes,
            edges=edges,
            activations=activations,
            sediments=sediments,
        )
        self.resonance_composer.add(map_record)
        self.ledger.append_resonance(map_record)
        report_record = compose_report(
            run_id=run_id,
            resonance_id=f"{run_id}:resonance:report",
            tick=run_record.ended_at_tick,
            headline=f"SESHAT fabric run {run_id}",
            sections=[
                {
                    "outcome": run_record.outcome.value,
                    "stop_reason": run_record.stop_reason.value,
                    "waves_emitted": run_record.waves_emitted,
                    "activations_total": run_record.activations_total,
                }
            ],
        )
        self.resonance_composer.add(report_record)
        self.ledger.append_resonance(report_record)


__all__ = [
    "WaveEngine",
    "WaveEngineConfigurationError",
    "WaveEngineStateError",
]
