"""Room compilation: a pure capability compiler over the thread registry.

The Room decides *which capabilities a question needs*; the Carpet (engine)
executes them.  This module is the Room half and it is deliberately pure: it
reads the declared thread registry (read_set / write_set state types), the
desired output state(s), the source/capability state that is actually
available, the granted rights and a bounded budget.

It MUST NOT read the fixture's ``must_wave`` field.  ``must_wave`` is the
acceptance oracle for the plan; compiling from it would make the oracle
assert itself.  The plan is derived by recursive backwards dependency
closure from the desired output states instead, so erasing or corrupting
``must_wave`` cannot change a plan for the same legitimate input.

Admission is applied to the *actual* run through :func:`admitted_threads`,
not merely recorded as metadata.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from seshat.fabric_waves.contracts import ActivationRecord

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seshat.fabric_waves.engine import WaveEngine

# -- admission verdicts -------------------------------------------------------

ADMITTED = "ADMITTED"
BLOCKED_MISSING_INPUT = "BLOCKED_MISSING_INPUT"
DENIED_RIGHTS = "DENIED_RIGHTS"
DROPPED_BUDGET = "DROPPED_BUDGET"

#: Reason codes for a state that no admitted capability can produce.
UNPRODUCIBLE = "UNPRODUCIBLE_NO_WRITER"


@dataclass(frozen=True)
class CapabilitySpec:
    """One declared capability (a registry thread), independent of any engine."""

    registry_id: str
    role: str
    read_set: tuple[str, ...]
    write_set: tuple[str, ...]
    requires_rights: str = ""

    @classmethod
    def from_registry_entry(cls, entry: Mapping[str, Any]) -> CapabilitySpec:
        return cls(
            registry_id=str(entry["thread_id"]),
            role=str(entry.get("role") or ""),
            read_set=tuple(str(item) for item in entry.get("read_set") or ()),
            write_set=tuple(str(item) for item in entry.get("write_set") or ()),
            requires_rights=str(entry.get("requires_rights") or ""),
        )


def load_registry(fixture: Mapping[str, Any]) -> tuple[CapabilitySpec, ...]:
    """Capabilities declared by the fixture, in declaration order."""

    return tuple(
        CapabilitySpec.from_registry_entry(entry)
        for entry in fixture.get("thread_registry") or ()
    )


@dataclass(frozen=True)
class RoomRequest:
    """What the operator's question needs, and what the host currently has."""

    desired_output_states: tuple[str, ...]
    available_base_states: tuple[str, ...] = ()
    granted_rights: frozenset[str] = frozenset()
    max_capabilities: int = 32
    delta_scope_carrier: str | None = None

    def __post_init__(self) -> None:
        if not self.desired_output_states:
            raise ValueError("ROOM_REQUEST_REQUIRES_DESIRED_OUTPUT")
        if self.max_capabilities < 1:
            raise ValueError("ROOM_REQUEST_BUDGET_MUST_BE_POSITIVE")


@dataclass(frozen=True)
class PlannedCapability:
    """One capability the compiler considered, with an explicit verdict."""

    registry_id: str
    admission: str
    depth: int
    produces: tuple[str, ...] = ()
    needed_for: tuple[str, ...] = ()
    missing_input_states: tuple[str, ...] = ()
    engine_thread_ids: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_admitted(self) -> bool:
        return self.admission == ADMITTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "admission": self.admission,
            "depth": self.depth,
            "produces": list(self.produces),
            "needed_for": list(self.needed_for),
            "missing_input_states": list(self.missing_input_states),
            "engine_thread_ids": list(self.engine_thread_ids),
            "detail": self.detail,
        }


# -- the compiler -------------------------------------------------------------


def compile_room(
    *,
    registry: Sequence[CapabilitySpec],
    request: RoomRequest,
    thread_binding: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[tuple[PlannedCapability, ...], dict[str, str]]:
    """Minimal recursive backwards dependency closure over declared capabilities.

    Returns the planned capabilities (deterministically ordered) and a map of
    every state the closure touched to how it is satisfied.  Pure: no engine,
    no I/O, no ``must_wave``.
    """

    writers: dict[str, list[CapabilitySpec]] = {}
    for cap in registry:
        for state in cap.write_set:
            writers.setdefault(state, []).append(cap)

    base = set(request.available_base_states)
    state_status: dict[str, str] = {}
    chosen: dict[str, PlannedCapability] = {}
    # Guard against a registry whose read/write sets form a cycle.
    resolving_states: set[str] = set()
    resolving_caps: set[str] = set()

    def resolve_state(state: str, depth: int, goal: str) -> bool:
        """True when some admitted capability (or a base state) supplies ``state``."""

        if state in base:
            state_status[state] = "SATISFIED_BY_AVAILABLE_INPUT"
            return True
        if state in resolving_states:
            state_status.setdefault(state, "CYCLIC_DEPENDENCY")
            return False
        candidates = writers.get(state) or []
        if not candidates:
            state_status[state] = UNPRODUCIBLE
            return False
        resolving_states.add(state)
        try:
            satisfied = False
            for cap in candidates:
                if require_capability(cap, depth, goal):
                    satisfied = True
            # One admitted writer is enough; other writers keep their own verdict.
            state_status[state] = (
                "SATISFIED_BY_CAPABILITY" if satisfied else "BLOCKED_NO_ADMITTED_WRITER"
            )
            return satisfied
        finally:
            resolving_states.discard(state)

    def require_capability(cap: CapabilitySpec, depth: int, goal: str) -> bool:
        prior = chosen.get(cap.registry_id)
        if prior is not None:
            merged_goals = tuple(sorted({*prior.needed_for, goal}))
            chosen[cap.registry_id] = PlannedCapability(
                registry_id=prior.registry_id,
                admission=prior.admission,
                depth=min(prior.depth, depth),
                produces=prior.produces,
                needed_for=merged_goals,
                missing_input_states=prior.missing_input_states,
                engine_thread_ids=prior.engine_thread_ids,
                detail=prior.detail,
            )
            return prior.is_admitted
        if cap.registry_id in resolving_caps:
            return False

        bound = tuple((thread_binding or {}).get(cap.registry_id, ()))

        if cap.requires_rights and cap.requires_rights not in request.granted_rights:
            chosen[cap.registry_id] = PlannedCapability(
                registry_id=cap.registry_id,
                admission=DENIED_RIGHTS,
                depth=depth,
                produces=cap.write_set,
                needed_for=(goal,),
                engine_thread_ids=bound,
                detail=f"rights {cap.requires_rights!r} not granted to this room",
            )
            return False

        resolving_caps.add(cap.registry_id)
        try:
            missing = [
                state
                for state in cap.read_set
                if not resolve_state(state, depth + 1, goal)
            ]
        finally:
            resolving_caps.discard(cap.registry_id)

        if missing:
            chosen[cap.registry_id] = PlannedCapability(
                registry_id=cap.registry_id,
                admission=BLOCKED_MISSING_INPUT,
                depth=depth,
                produces=cap.write_set,
                needed_for=(goal,),
                missing_input_states=tuple(missing),
                engine_thread_ids=bound,
                detail="no admitted producer for " + ", ".join(missing),
            )
            return False

        if not bound:
            chosen[cap.registry_id] = PlannedCapability(
                registry_id=cap.registry_id,
                admission=BLOCKED_MISSING_INPUT,
                depth=depth,
                produces=cap.write_set,
                needed_for=(goal,),
                missing_input_states=("<engine-binding>",),
                engine_thread_ids=(),
                detail="capability declared but not bound to any runtime thread",
            )
            return False

        chosen[cap.registry_id] = PlannedCapability(
            registry_id=cap.registry_id,
            admission=ADMITTED,
            depth=depth,
            produces=cap.write_set,
            needed_for=(goal,),
            engine_thread_ids=bound,
        )
        return True

    for goal in request.desired_output_states:
        resolve_state(goal, 0, goal)

    ordered = sorted(chosen.values(), key=lambda item: (-item.depth, item.registry_id))

    # Budget is applied to admitted capabilities only, deepest-first so the
    # independent shallow branches that are already satisfiable keep running.
    admitted_order = [item for item in ordered if item.is_admitted]
    if len(admitted_order) > request.max_capabilities:
        overflow = {item.registry_id for item in admitted_order[request.max_capabilities :]}
        ordered = [
            PlannedCapability(
                registry_id=item.registry_id,
                admission=DROPPED_BUDGET,
                depth=item.depth,
                produces=item.produces,
                needed_for=item.needed_for,
                missing_input_states=item.missing_input_states,
                engine_thread_ids=item.engine_thread_ids,
                detail=f"room budget {request.max_capabilities} capabilities exceeded",
            )
            if item.registry_id in overflow
            else item
            for item in ordered
        ]

    return tuple(ordered), dict(state_status)


# -- manifest -----------------------------------------------------------------


@dataclass
class RoomManifest:
    """Planned vs actual room admission for one stone-driven compilation.

    ``status`` stays ``PLANNED`` until the room is actually admitted to a run
    and only then reflects observed activations.
    """

    room_id: str
    host_id: str
    stone_id: str
    desired_output_states: tuple[str, ...]
    planned: tuple[PlannedCapability, ...]
    state_status: Mapping[str, str] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)
    actual_activated_threads: tuple[str, ...] = field(default_factory=tuple)
    unplanned_activated_threads: tuple[str, ...] = field(default_factory=tuple)
    status: str = "PLANNED"
    run_id: str = ""

    @property
    def admitted(self) -> tuple[PlannedCapability, ...]:
        return tuple(item for item in self.planned if item.is_admitted)

    @property
    def admitted_engine_threads(self) -> tuple[str, ...]:
        out: list[str] = []
        for item in self.admitted:
            for tid in item.engine_thread_ids:
                if tid not in out:
                    out.append(tid)
        return tuple(out)

    @property
    def blocked(self) -> tuple[PlannedCapability, ...]:
        return tuple(item for item in self.planned if not item.is_admitted)

    @property
    def planned_registry_threads(self) -> tuple[str, ...]:
        return tuple(item.registry_id for item in self.admitted)

    def close(self, *, activations: Sequence[ActivationRecord], run_id: str) -> None:
        """Record what actually fired. Only call after the room really ran."""

        self.run_id = run_id
        fired = {
            act.thread_id
            for act in activations
            if act.run_id == run_id and act.outcome.value == "FIRED"
        }
        self.actual_activated_threads = tuple(sorted(fired))
        planned_ids = set(self.admitted_engine_threads)
        self.unplanned_activated_threads = tuple(sorted(fired - planned_ids))
        missing = planned_ids - fired
        if self.unplanned_activated_threads:
            self.status = "ADMISSION_BREACH"
        elif not fired:
            self.status = "NO_ACTIVATION"
        elif missing:
            self.status = "PARTIAL_ADMISSION"
        else:
            self.status = "QUIESCENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "host_id": self.host_id,
            "stone_id": self.stone_id,
            "run_id": self.run_id,
            "desired_output_states": list(self.desired_output_states),
            "status": self.status,
            "budget": dict(self.budget),
            "planned_capabilities": [item.to_dict() for item in self.planned],
            "planned_registry_threads": list(self.planned_registry_threads),
            "planned_engine_threads": list(self.admitted_engine_threads),
            "blocked_capabilities": [item.to_dict() for item in self.blocked],
            "state_status": dict(sorted(self.state_status.items())),
            "actual_activated_threads": list(self.actual_activated_threads),
            "unplanned_activated_threads": list(self.unplanned_activated_threads),
            "planned_vs_actual": {
                "planned_only": sorted(
                    set(self.admitted_engine_threads) - set(self.actual_activated_threads)
                ),
                "actual_only": list(self.unplanned_activated_threads),
            },
        }


#: Which output state each operator stone kind is actually asking for.
#: Derived from the stone's own kind — never from the plan oracle.
DESIRED_OUTPUT_BY_STONE_KIND: Mapping[str, tuple[str, ...]] = {
    "QUERY": ("Resonance",),
    "SOURCE_DELTA": ("Resonance",),
    "APORIA": ("ReconciledStateOrAPORIA",),
    "FRONTIER_NEED": ("ResearchNeed",),
}


def desired_outputs_for_stone(stone: Mapping[str, Any]) -> tuple[str, ...]:
    kind = str(stone.get("kind") or "")
    try:
        return DESIRED_OUTPUT_BY_STONE_KIND[kind]
    except KeyError:
        raise ValueError(f"ROOM_UNKNOWN_STONE_KIND {kind!r}") from None


def compile_room_for_stone(
    *,
    host_id: str,
    host_slug: str,
    stone: Mapping[str, Any],
    registry: Sequence[CapabilitySpec],
    thread_binding: Mapping[str, tuple[str, ...]],
    available_base_states: Sequence[str],
    granted_rights: Sequence[str],
    budget: Mapping[str, Any],
    desired_output_states: Sequence[str] | None = None,
) -> RoomManifest:
    """Compile the room a stone needs from runtime state, not from ``must_wave``."""

    goals = (
        tuple(desired_output_states)
        if desired_output_states is not None
        else desired_outputs_for_stone(stone)
    )
    mutation = stone.get("mutation") or {}
    request = RoomRequest(
        desired_output_states=goals,
        available_base_states=tuple(available_base_states),
        granted_rights=frozenset(granted_rights),
        max_capabilities=int(budget.get("max_capabilities_per_room") or 32),
        delta_scope_carrier=str(mutation["source_id"]) if mutation.get("source_id") else None,
    )
    planned, state_status = compile_room(
        registry=registry, request=request, thread_binding=thread_binding
    )
    return RoomManifest(
        room_id=f"{host_slug}:{stone['stone_id']}",
        host_id=host_id,
        stone_id=str(stone["stone_id"]),
        desired_output_states=goals,
        planned=planned,
        state_status=state_status,
        budget=dict(budget),
    )


@contextmanager
def admitted_threads(engine: WaveEngine, thread_ids: Sequence[str]) -> Iterator[None]:
    """Restrict a run to the room's admitted capabilities, then restore.

    This is what makes the plan binding: a capability the Room did not admit
    has no spec in the engine for the duration of the run, so it cannot fire.
    Sediment, ledger and carrier state are untouched and stay continuous.
    """

    allowed = [tid for tid in thread_ids if tid in engine.thread_specs]
    if not allowed:
        raise ValueError("ROOM_ADMITS_NO_RUNTIME_THREAD")
    saved_specs = engine.thread_specs
    saved_laws = engine.propagation_laws
    engine.thread_specs = {tid: saved_specs[tid] for tid in allowed}
    engine.propagation_laws = {tid: saved_laws[tid] for tid in allowed}
    try:
        yield
    finally:
        engine.thread_specs = saved_specs
        engine.propagation_laws = saved_laws


def manifests_to_json(manifests: Sequence[RoomManifest]) -> str:
    return json.dumps([m.to_dict() for m in manifests], ensure_ascii=False, sort_keys=True, indent=2)


__all__ = [
    "ADMITTED",
    "BLOCKED_MISSING_INPUT",
    "DENIED_RIGHTS",
    "DROPPED_BUDGET",
    "UNPRODUCIBLE",
    "CapabilitySpec",
    "PlannedCapability",
    "RoomManifest",
    "RoomRequest",
    "admitted_threads",
    "compile_room",
    "compile_room_for_stone",
    "desired_outputs_for_stone",
    "load_registry",
    "manifests_to_json",
]
