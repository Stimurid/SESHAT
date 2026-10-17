"""Fabric contracts.

All types are Pydantic v2 ``BaseModel`` so they validate against the existing
``SourceAccessManifest`` / ``AcceptanceState`` / ``RawAccessPolicy`` contracts.
Each is intentionally host-neutral; donor systems connect through method-body
registrations.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from seshat.contracts import (
    AcceptanceState,
    RawAccessPolicy,
)

ACCEPTANCE_DECISION_RIGHT: str = "seshat:fabric:human-acceptance"
"""Reserved decision-right handle.  Acceptance to ACCEPTED is human authority."""

F07_GAP: str = "F07"
"""Marker of the F07 frontier gap: real scientific cartridge not wired in."""


class StoneEventKind(StrEnum):
    QUERY = "QUERY"
    SOURCE_DELTA = "SOURCE_DELTA"
    SEDIMENT_AVAILABLE = "SEDIMENT_AVAILABLE"
    RECONCILE_REQUEST = "RECONCILE_REQUEST"
    APORIA = "APORIA"
    HUMAN_DECISION = "HUMAN_DECISION"
    FRONTIER_RETURN = "FRONTIER_RETURN"


OPERATOR_STONE_KINDS: frozenset[StoneEventKind] = frozenset(
    {
        StoneEventKind.QUERY,
        StoneEventKind.SOURCE_DELTA,
        StoneEventKind.APORIA,
        StoneEventKind.HUMAN_DECISION,
        StoneEventKind.FRONTIER_RETURN,
    }
)
"""External operator ingress kinds; internal causal kinds belong in events.jsonl only."""


class EpistemicLevel(StrEnum):
    """E1 is source-witnessed; E5 is projective proposal, never accepted canon."""

    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class FabricRunOutcome(StrEnum):
    CONVERGED = "CONVERGED"
    SATURATED = "SATURATED"
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"
    APORIA = "APORIA"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"


class FabricStopReason(StrEnum):
    CONVERGED = "CONVERGED"
    NO_DELTA = "NO_DELTA"
    MAX_WAVES = "MAX_WAVES"
    MAX_ACTIVATIONS = "MAX_ACTIVATIONS"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    SOURCE_DENIED = "SOURCE_DENIED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_THREAD = "INVALID_THREAD"
    INVALID_STONE = "INVALID_STONE"
    APORIA_RECORDED = "APORIA_RECORDED"
    STRATEGY_STOPPED = "STRATEGY_STOPPED"
    HUMAN_HALT = "HUMAN_HALT"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"


class ActivationOutcome(StrEnum):
    FIRED = "FIRED"
    SKIPPED_GUARD = "SKIPPED_GUARD"
    SKIPPED_INACTIVE = "SKIPPED_INACTIVE"
    BLOCKED_SOURCE = "BLOCKED_SOURCE"
    BLOCKED_PROVIDER = "BLOCKED_PROVIDER"
    SATURATED_NO_DELTA = "SATURATED_NO_DELTA"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ERROR = "ERROR"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"


ACTIVATION_OUTCOMES: tuple[ActivationOutcome, ...] = tuple(ActivationOutcome)


class ResonanceKind(StrEnum):
    ANSWER = "ANSWER"
    QUESTION = "QUESTION"
    MAP = "MAP"
    ACTIONABLE_PLAN = "ACTIONABLE_PLAN"
    FRONTIER_GAP = "FRONTIER_GAP"
    DECISION_REQUEST = "DECISION_REQUEST"
    REPORT = "REPORT"


class MethodBodyRef(BaseModel):
    """A reference to a registered MethodBody.

    A reference alone is inert; the engine resolves it through the
    :class:`MethodBodyRegistry`.  ``version`` is pinned at registration so the
    thread spec never silently changes behaviour.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_body_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EdgeCondition(BaseModel):
    """A single guard for an edge between nodes or waves.

    A node fires only when every supplied condition is satisfied.  Conditions
    are explicit by design; "transitive analogy" is rejected on purpose.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = ""
    requires_event_kind: StoneEventKind | None = None
    requires_sediment_id: str | None = None
    requires_sediment_version_at_least: str | None = None
    requires_sediment_acceptance: AcceptanceState | None = None
    requires_thread_id_fired_in_last_wave: str | None = None
    requires_carrier_id: str | None = None


class ThreadNodeSpec(BaseModel):
    """One operation node inside a WorkflowThread."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    output_sediment_type: str = Field(min_length=1)
    consumes_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    produces_sediment_id: str | None = None
    output_contracts: dict[str, str] = Field(default_factory=dict)
    method_body_ref: MethodBodyRef | None = None
    conditions: tuple[EdgeCondition, ...] = Field(default_factory=tuple)
    notes: str = ""


class WorkflowThreadSpec(BaseModel):
    """A thread in the carpet, with the 14 owner-charter properties.

    The 14 are expressed as model fields; the docstring documents the mapping.
    """

    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    # (2) input state
    input_state: tuple[str, ...] = Field(default_factory=tuple)
    # (3) admissible sources
    admissible_source_carriers: tuple[str, ...] = Field(default_factory=tuple)
    raw_access_policy: RawAccessPolicy = RawAccessPolicy.DRILLBACK
    accepts_operator_query: bool = False
    # (4) distinctions / operations
    method_body_refs: tuple[MethodBodyRef, ...] = Field(default_factory=tuple)
    # (5) carriers / nodes
    nodes: tuple[ThreadNodeSpec, ...] = Field(default_factory=tuple)
    # (6) completion criterion
    exit_criterion: str = Field(min_length=1)
    # (7) output state
    output_state: tuple[str, ...] = Field(default_factory=tuple)
    # (8) output rationale
    output_rationale: str = ""
    # (9) state-transfer rule
    state_transfer_rule: str = ""
    # (10) decision right
    decision_right: str = ""
    # (11) next-decision right
    next_decision_right: str = ""
    # (12) constraints
    constraints: tuple[str, ...] = Field(default_factory=tuple)
    applicability: tuple[str, ...] = Field(default_factory=tuple)
    # (13) canon status
    canon_status: str = "DRAFT"
    # (14) cost (here: bounded budget hint)
    bounded_budget_hint: int = Field(default=16, ge=1)
    stop_rule: str = ""

    @field_validator("nodes")
    @classmethod
    def _unique_nodes(cls, value: tuple[ThreadNodeSpec, ...]) -> tuple[ThreadNodeSpec, ...]:
        seen: set[str] = set()
        for node in value:
            if node.node_id in seen:
                raise ValueError(f"duplicate node_id {node.node_id!r} in thread")
            seen.add(node.node_id)
        return value

    @field_validator("method_body_refs")
    @classmethod
    def _unique_method_bodies(
        cls, value: tuple[MethodBodyRef, ...]
    ) -> tuple[MethodBodyRef, ...]:
        seen: set[tuple[str, str]] = set()
        for ref in value:
            key = (ref.method_body_id, ref.version)
            if key in seen:
                raise ValueError(
                    f"duplicate method body reference {ref.method_body_id}@{ref.version}"
                )
            seen.add(key)
        return value


class PropagationLaw(BaseModel):
    """Per-thread propagation law.

    ``wakes_on_carrier_ids`` is the read set; threads that depend on those
    carriers are eligible to re-fire when a SOURCE_DELTA arrives.  Empty means
    the thread never wakes from a SOURCE_DELTA.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str = Field(min_length=1)
    wakes_on_carrier_ids: tuple[str, ...] = Field(default_factory=tuple)
    wakes_on_stone_kinds: tuple[StoneEventKind, ...] = Field(
        default_factory=lambda: (StoneEventKind.QUERY,)
    )
    requires_research_object_id: str | None = None
    initial_state: tuple[str, ...] = Field(default_factory=tuple)
    wakes_on_sediment_types: tuple[str, ...] = Field(default_factory=tuple)


class WaveBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_waves: int = Field(ge=1)
    max_activations: int = Field(ge=1)
    max_stone_events: int = Field(ge=1)
    aporia_after_waves: int = Field(default=2, ge=1)


class StoneEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    kind: StoneEventKind
    issued_at_tick: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    target_research_object_id: str | None = None
    target_carrier_id: str | None = None
    target_thread_id: str | None = None
    parent_activation_id: str | None = None


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    run_id: str = ""
    issued_at_tick: int = Field(ge=0)
    kind: StoneEventKind
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_research_object_id: str | None = None
    target_carrier_id: str | None = None
    consumed_by_wave_id: str | None = None
    parent_activation_id: str | None = None
    # Linkage to the corresponding StoneEvent for traceability
    kind_enum: StoneEventKind = StoneEventKind.QUERY


class ActivationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    activation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    wave_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    started_at_tick: int = Field(ge=0)
    ended_at_tick: int = Field(ge=0)
    outcome: ActivationOutcome
    stop_reason: str = ""
    fired_node_ids: tuple[str, ...] = Field(default_factory=tuple)
    produced_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    invalidated_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    read_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    write_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_carrier_ids: tuple[str, ...] = Field(default_factory=tuple)
    receipts_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_body_refs: tuple[MethodBodyRef, ...] = Field(default_factory=tuple)
    error_code: str | None = None
    error_detail: str | None = None


class WaveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wave_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    wave_index: int = Field(ge=1)
    triggered_by: StoneEventKind
    triggering_event_id: str = Field(min_length=1)
    eligible_thread_ids: tuple[str, ...] = Field(default_factory=tuple)
    fired_thread_ids: tuple[str, ...] = Field(default_factory=tuple)
    no_delta_thread_ids: tuple[str, ...] = Field(default_factory=tuple)
    skipped_thread_ids: tuple[str, ...] = Field(default_factory=tuple)
    blocked_thread_ids: tuple[str, ...] = Field(default_factory=tuple)
    budget_used: int = Field(default=0, ge=0)
    sediment_versions_after: dict[str, str] = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decided_at_tick: int = Field(ge=0)
    decided_by: str = Field(min_length=1)
    subject_sediment_id: str | None = None
    subject_thread_id: str | None = None
    choice: str = Field(min_length=1)
    rationale: str = ""
    accepts_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    rejects_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    issuer: str = ""
    nonce: str = ""
    subject_version: str = ""
    decision_right: str = ""


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    started_at_tick: int = Field(ge=0)
    ended_at_tick: int = Field(ge=0)
    outcome: FabricRunOutcome
    stop_reason: FabricStopReason
    budget: WaveBudget
    sediment_initial_versions: dict[str, str] = Field(default_factory=dict)
    sediment_final_versions: dict[str, str] = Field(default_factory=dict)
    waves_emitted: int = Field(ge=0)
    activations_total: int = Field(ge=0)
    decision_ids: tuple[str, ...] = Field(default_factory=tuple)
    resonance_ids: tuple[str, ...] = Field(default_factory=tuple)
    ledger_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: tuple[str, ...] = Field(default_factory=tuple)


class ResonanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resonance_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    kind: ResonanceKind
    produced_at_tick: int = Field(ge=0)
    trace_event_ids: tuple[str, ...] = Field(default_factory=tuple)
    trace_activation_ids: tuple[str, ...] = Field(default_factory=tuple)
    trace_wave_ids: tuple[str, ...] = Field(default_factory=tuple)
    trace_sediment_ids: tuple[str, ...] = Field(default_factory=tuple)
    payload: Any = None
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FrontierProposal(BaseModel):
    """A candidate selection for the next activation.

    The engine decides; this is a typed proposal a strategy returns.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str = Field(min_length=1)
    node_id: str | None = None
    reason: str = ""


__all__ = [
    "ACCEPTANCE_DECISION_RIGHT",
    "ACTIVATION_OUTCOMES",
    "F07_GAP",
    "ActivationOutcome",
    "ActivationRecord",
    "DecisionRecord",
    "EdgeCondition",
    "EpistemicLevel",
    "EventRecord",
    "FabricRunOutcome",
    "FabricStopReason",
    "FrontierProposal",
    "MethodBodyRef",
    "PropagationLaw",
    "ResonanceKind",
    "ResonanceRecord",
    "RunRecord",
    "StoneEvent",
    "StoneEventKind",
    "ThreadNodeSpec",
    "WaveBudget",
    "WaveRecord",
    "WorkflowThreadSpec",
]
