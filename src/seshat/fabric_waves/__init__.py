"""SESHAT executable analytic fabric — agent-thread wave engine.

This is an additive, namespaced prototype layer.  It composes with the existing
S2A Blackboard, S2B Runtime and S2B ReconciliationController without modifying
them.  It does not invent MethodBodies for protected profiles.

Three semantic layers, mirroring the owner charter:

* Stone  -- typed external or internal events that the operator or a frontier
  return drops onto the carpet.  Kinds: QUERY, SOURCE_DELTA, APORIA,
  HUMAN_DECISION, FRONTIER_RETURN.  Stone never decides; it perturbs.
* Carpet -- the WorkflowThread graph.  Threads are explicit; nodes inside a
  thread are explicit; conditional edges and bounded budgets are explicit.
* Sediment -- the versioned stable analytic substrate, separately named from
  Blackboard candidate state.  A SedimentRecord is keyed by its sediment_id and
  carries source carrier refs, method-body refs, read/write dependencies and
  acceptance state.  Source deltas wake only the threads whose read set touches
  the changed carrier; promoted-to-ACCEPTED is human authority, never
  self-certified.

Everything below is deterministic, hash-receipted and append-only.  No real
protected MethodBodies, donor data, secrets or production writes are involved.
"""

from __future__ import annotations

from seshat.fabric_waves.contracts import (
    ACCEPTANCE_DECISION_RIGHT,
    ACTIVATION_OUTCOMES,
    F07_GAP,
    ActivationOutcome,
    ActivationRecord,
    DecisionRecord,
    EdgeCondition,
    EventRecord,
    FabricRunOutcome,
    FabricStopReason,
    MethodBodyRef,
    PropagationLaw,
    ResonanceKind,
    ResonanceRecord,
    RunRecord,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WaveBudget,
    WaveRecord,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import (
    MethodBody,
    MethodBodyRegistry,
    MethodBodyViolation,
    SafeFixtureBodies,
    build_safe_fixture_registry,
)
from seshat.fabric_waves.resonance import ResonanceComposer
from seshat.fabric_waves.sediment import SedimentState, SedimentView
from seshat.fabric_waves.stone import StoneDispatcher, StoneQueueFull

__all__ = [
    "ACCEPTANCE_DECISION_RIGHT",
    "ACTIVATION_OUTCOMES",
    "F07_GAP",
    "ActivationOutcome",
    "ActivationRecord",
    "DecisionRecord",
    "EdgeCondition",
    "EventRecord",
    "FabricRunOutcome",
    "FabricStopReason",
    "MethodBody",
    "MethodBodyRef",
    "MethodBodyRegistry",
    "MethodBodyViolation",
    "PropagationLaw",
    "ResonanceComposer",
    "ResonanceKind",
    "ResonanceRecord",
    "RunLedger",
    "RunRecord",
    "SafeFixtureBodies",
    "SedimentState",
    "SedimentView",
    "StoneDispatcher",
    "StoneEvent",
    "StoneEventKind",
    "StoneQueueFull",
    "ThreadNodeSpec",
    "WaveBudget",
    "WaveEngine",
    "WaveRecord",
    "WorkflowThreadSpec",
    "build_safe_fixture_registry",
]