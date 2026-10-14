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
    select_frontier,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import (
    BodyInvocation,
    MethodBodyRegistry,
    MethodBodyViolation,
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
    report as compose_report,
)
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.fabric_waves.stone import StoneDispatcher


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
    ) -> RunRecord:
        self._validate_specs()
        if any(item.run_id == run_id for item in self.ledger.runs):
            raise WaveEngineConfigurationError(f"run_id {run_id!r} already used")
        start_tick = self._tick()
        if initial_stone is not None:
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

        initial_versions = self.sediment.version_map()
        activations_total = 0
        stone_events_used = len(self.dispatcher.consumed)
        waves_emitted = 0
        decision_ids: list[str] = []
        consecutive_no_delta_waves = 0
        waves_with_aporia = 0
        last_wave_thread_ids: tuple[str, ...] = ()
        stop_reason: FabricStopReason = FabricStopReason.NO_DELTA
        outcome: FabricRunOutcome = FabricRunOutcome.SATURATED
        ledger_head_at_start = self.ledger.head_hash

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
                stop_reason = FabricStopReason.NO_DELTA
                outcome = FabricRunOutcome.SATURATED
                break
            if stone_events_used >= budget.max_stone_events:
                stop_reason = FabricStopReason.BUDGET_EXHAUSTED
                outcome = FabricRunOutcome.EXHAUSTED
                break

            waves_emitted += 1
            trigger_event = self.dispatcher.consume_next(
                run_id=run_id,
                wave=WaveRecord(
                    wave_id=f"{run_id}:wave:{waves_emitted}",
                    run_id=run_id,
                    wave_index=waves_emitted,
                    triggered_by=initial_event.kind,
                    triggering_event_id=initial_event.event_id,
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
                self._apply_source_delta(trigger_event)

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
                    if activations_total >= budget.max_activations:
                        blocked.append(proposal.thread_id)
                        thread_blocked = True
                        break
                    activations_total += 1
                    wave_activations += 1
                    activation = self._invoke_node(
                        run_id=run_id,
                        wave_id=wave_record_id,
                        spec=spec,
                        node=node,
                        stone=trigger_event,
                    )
                    self.ledger.append_activation(activation)
                    if activation.outcome is ActivationOutcome.FIRED:
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
                    break
                # An aporia wave counts as a saturation wave for NO_DELTA bookkeeping.
                consecutive_no_delta_waves += 1
                continue

            if wave.no_delta_thread_ids and not wave.fired_thread_ids:
                consecutive_no_delta_waves += 1
            else:
                consecutive_no_delta_waves = 0

            if consecutive_no_delta_waves >= 2:
                stop_reason = FabricStopReason.NO_DELTA
                outcome = FabricRunOutcome.SATURATED
                break

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
        self.ledger.append_run(run_record)

        if auto_answer:
            self._autoresonance(run_id, run_record)
            run_record = self.ledger.runs[-1]

        return run_record

    def _drop_stone(self, event: StoneEvent, *, budget: WaveBudget) -> None:
        if len(self.dispatcher.consumed) + len(self.dispatcher.pending) >= budget.max_stone_events:
            raise WaveEngineConfigurationError("max_stone_events budget exhausted before run")
        self.dispatcher.drop(event)

    def _apply_source_delta(self, event: StoneEvent) -> None:
        carrier_id = event.target_carrier_id
        if carrier_id is None or self.carrier_store is None:
            return
        payload = event.payload
        new_version = str(payload.get("new_version", payload.get("new", "v2")))
        new_text = str(payload.get("text", payload.get("new_text", "")))
        self.carrier_store.apply_delta(
            carrier_id,
            new_version=new_version,
            new_text=new_text,
        )

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
            if stone_events_used >= budget.max_stone_events:
                return stone_events_used
            event = StoneEvent(
                event_id=f"{run_id}:sediment:{sediment_id}:{record.version}",
                kind=StoneEventKind.SEDIMENT_AVAILABLE,
                issued_at_tick=tick,
                payload={
                    "sediment_id": sediment_id,
                    "object_type": record.object_type,
                    "version": record.version,
                },
            )
            self.dispatcher.drop(event)
            stone_events_used += 1
            if record.object_type == "safe.repair_signal":
                target = record.payload.get("target_thread_id")
                if target and stone_events_used < budget.max_stone_events:
                    repair = StoneEvent(
                        event_id=f"{run_id}:repair:{sediment_id}",
                        kind=StoneEventKind.RECONCILE_REQUEST,
                        issued_at_tick=tick,
                        target_thread_id=str(target),
                        payload={"subject_sediment_id": sediment_id},
                    )
                    self.dispatcher.drop(repair)
                    stone_events_used += 1
        return stone_events_used

    def _resolve_body_ref(
        self, spec: WorkflowThreadSpec, node: ThreadNodeSpec
    ) -> Any:
        if node.method_body_ref is not None and self.bodies.has(node.method_body_ref):
            return node.method_body_ref
        for ref in spec.method_body_refs:
            if ref.method_body_id.endswith(node.operation_id.split(".")[-1]) and self.bodies.has(ref):
                return ref
        return next(
            (candidate for candidate in spec.method_body_refs if self.bodies.has(candidate)),
            None,
        )

    def _validate_and_deposit(
        self,
        *,
        node: ThreadNodeSpec,
        record: SedimentRecord,
        consumed_ids: tuple[str, ...],
    ) -> SedimentRecord:
        if record.object_type != node.output_sediment_type:
            raise MethodBodyViolation(
                f"object_type {record.object_type!r} != declared {node.output_sediment_type!r}"
            )
        if node.produces_sediment_id is not None and record.sediment_id != node.produces_sediment_id:
            record = record.model_copy(update={"sediment_id": node.produces_sediment_id}, deep=True)
        dep_versions = {
            sid: self.sediment.version_map().get(sid, "")
            for sid in consumed_ids
            if sid in self.sediment.version_map()
        }
        if record.epistemic_level is EpistemicLevel.E1 and not record.source_carrier_refs:
            record = record.model_copy(update={"epistemic_level": EpistemicLevel.E2}, deep=True)
        record = record.model_copy(
            update={"dependency_versions": dep_versions},
            deep=True,
        )
        return record

    # -- per-node invocation -------------------------------------------------

    def _invoke_node(
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
                if record is not None:
                    candidate_sediments.append(record)
        elif not node.consumes_sediment_ids:
            # An empty ``consumes_sediment_ids`` means the body decides
            # which sediments to consume; the engine hands over all working
            # records.  Bodies must filter by object_type themselves.
            candidate_sediments.extend(self.sediment.views["working"].values())
        carriers = self._carriers_for_thread(spec, stone)
        try:
            if self.carrier_store is not None and carriers:
                source_payload, manifest = self.carrier_store.resolve_payload(
                    policy=spec.raw_access_policy,
                    carrier_ids=carriers,
                    stone_payload=stone.payload,
                    operation_id=node.operation_id,
                )
            elif spec.raw_access_policy.value == "NEVER":
                source_payload = {"text": "", "values": list(stone.payload.get("values", ()))}
                manifest = None
            else:
                source_payload = {
                    "text": stone.payload.get("text", ""),
                    "values": list(stone.payload.get("values", ())),
                }
                manifest = None
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
        carried_payload = {
            "stone_payload": dict(stone.payload),
            "research_object_id": stone.target_research_object_id or spec.thread_id,
            "carriers": carriers,
            "text": source_payload.get("text", ""),
            "values": source_payload.get("values", []),
            "candidate_sediments": candidate_sediments,
            "source_access_manifest": manifest,
        }
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
            result = body(invocation)
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

        if result.aporia is not None:
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
        for record in result.produced_sediments:
            if record.payload_hash == "":
                raise MethodBodyViolation(
                    "body returned a sediment with empty payload_hash"
                )
            try:
                produced_sediment = self._validate_and_deposit(
                    node=node,
                    record=record,
                    consumed_ids=consumed_ids,
                )
            except MethodBodyViolation as exc:
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
                    "read_dependencies": produced_sediment.read_dependencies + consumed_ids,
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
            self.sediment.deposit(produced_sediment)
            produced_ids.append(produced_sediment.sediment_id)

        # NO_DELTA detection: same content was already in the sediment
        no_delta = False
        if not produced_ids:
            no_delta = True
        else:
            self.sediment.version_map()
            for sid in produced_ids:
                history = self.sediment.history(sid)
                if len(history) > 1 and history[-1].payload_hash == history[-2].payload_hash:
                    no_delta = True

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
        when = tick if tick is not None else self._tick()
        record = DecisionRecord(
            decision_id=decision_id,
            run_id=run_id,
            decided_at_tick=when,
            decided_by=attestation.decided_by,
            subject_sediment_id=subject_sediment_id,
            choice=choice,
            rationale=rationale,
            accepts_sediment_ids=tuple(accepts),
            rejects_sediment_ids=tuple(rejects),
        )
        self.ledger.append_decision(record)
        accept_with_attestation(
            self.sediment,
            attestation,
            decided_at_tick=when,
        )
        return record.model_copy(deep=True)

    # -- auto resonance for the demo CLI -------------------------------------

    def _autoresonance(self, run_id: str, run_record: RunRecord) -> None:
        activations = self.ledger.activations_for_run(run_id)
        waves = tuple(item for item in self.ledger.waves if item.run_id == run_id)
        events = tuple(item for item in self.ledger.events if item.run_id == run_id)
        sediments = self.sediment.all_records()
        summary = (
            f"Run {run_id} finished as {run_record.outcome.value} after "
            f"{run_record.waves_emitted} wave(s) and {run_record.activations_total} activation(s)."
        )
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