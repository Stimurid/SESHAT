"""Frontier selection — which threads are eligible to fire in the next wave.

The owner charter states that there is no universal mandatory
``cut → derive → analyze`` pipeline.  Frontier selection is therefore explicit:
a strategy receives the current state of the carpet and returns a typed
:class:`FrontierProposal`.  Conditional edges and read/write dependencies are
*enforced*, not "transitively equal" by name.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from seshat.fabric_waves.contracts import (
    EdgeCondition,
    FrontierProposal,
    PropagationLaw,
    StoneEvent,
    StoneEventKind,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState


class FrontierStrategy(Protocol):
    """Deterministic selection of the next eligible frontier."""

    def choose(
        self,
        *,
        thread_specs: Mapping[str, WorkflowThreadSpec],
        propagation_laws: Mapping[str, PropagationLaw],
        sediment: SedimentState,
        event: StoneEvent | None,
        last_wave_thread_ids: tuple[str, ...],
    ) -> tuple[FrontierProposal, ...]: ...


def _thread_satisfies_conditions(
    spec: WorkflowThreadSpec,
    law: PropagationLaw,
    sediment: SedimentState,
    event: StoneEvent | None,
    last_wave_thread_ids: tuple[str, ...],
) -> bool:
    """Apply the propagation law guards to a single thread.

    Conditions are *explicit* — name-collision with a satisfied condition is
    not a substitute for value equality.
    """

    if event is not None:
        if law.wakes_on_stone_kinds and event.kind not in law.wakes_on_stone_kinds:
            return False
        if (
            law.requires_research_object_id is not None
            and event.target_research_object_id is not None
            and law.requires_research_object_id != event.target_research_object_id
        ):
            return False
        if (
            event.target_thread_id is not None
            and event.target_thread_id != spec.thread_id
        ):
            return False
        if (
            event.target_carrier_id is not None
            and law.wakes_on_carrier_ids
            and event.target_carrier_id not in law.wakes_on_carrier_ids
        ):
            return False
        if event.kind is StoneEventKind.SEDIMENT_AVAILABLE:
            sediment_id = event.payload.get("sediment_id")
            object_type = event.payload.get("object_type")
            if law.wakes_on_sediment_types and object_type not in law.wakes_on_sediment_types:
                return False
            if law.initial_state and sediment_id not in law.initial_state:
                return False
        if (
            event.kind is StoneEventKind.RECONCILE_REQUEST
            and event.target_thread_id is not None
            and event.target_thread_id != spec.thread_id
        ):
            return False

    # The whole-thread ``initial_state`` must be present in the working view.
    if law.initial_state:
        working_ids = {record.sediment_id for record in sediment.views["working"].values()}
        if not set(law.initial_state).issubset(working_ids):
            return False
    # Node guards are evaluated immediately before each operation. A later
    # node may depend on state produced by an earlier node in this activation.
    return True


def _condition_holds(
    condition: EdgeCondition,
    sediment: SedimentState,
    last_wave_thread_ids: set[str],
    event: StoneEvent | None,
) -> bool:
    if (
        condition.requires_event_kind is not None
        and (event is None or event.kind is not condition.requires_event_kind)
    ):
        return False
    if condition.requires_sediment_id is not None:
        record = sediment.views["working"].get(condition.requires_sediment_id)
        if record is None:
            return False
        if (
            condition.requires_sediment_version_at_least is not None
            and record.version < condition.requires_sediment_version_at_least
        ):
            return False
        if (
            condition.requires_sediment_acceptance is not None
            and record.acceptance_state is not condition.requires_sediment_acceptance
        ):
            return False
    if condition.requires_thread_id_fired_in_last_wave is not None and (
        condition.requires_thread_id_fired_in_last_wave not in last_wave_thread_ids
    ):
        return False
    return not (
        condition.requires_carrier_id is not None
        and not any(
            condition.requires_carrier_id in record.source_carrier_refs
            for record in sediment.views["working"].values()
        )
    )


def select_frontier(
    *,
    thread_specs: Mapping[str, WorkflowThreadSpec],
    propagation_laws: Mapping[str, PropagationLaw],
    sediment: SedimentState,
    event: StoneEvent | None,
    last_wave_thread_ids: tuple[str, ...] = (),
    strategy: FrontierStrategy | None = None,
) -> tuple[FrontierProposal, ...]:
    """Compute the eligible frontier.

    When ``strategy`` is provided, the strategy's output is intersected with
    the explicit propagation-law filter so that ``transient everything
    equals'' is rejected.  The strategy MAY propose threads that are not
    currently admissible (we silently drop them); it MAY NOT silently remove
    an admissible thread.
    """

    if set(thread_specs) != set(propagation_laws):
        missing_in_laws = set(thread_specs) - set(propagation_laws)
        missing_in_specs = set(propagation_laws) - set(thread_specs)
        if missing_in_laws or missing_in_specs:
            raise ValueError(
                "thread_specs and propagation_laws must have the same keys; "
                f"missing in laws: {sorted(missing_in_laws)}; "
                f"missing in specs: {sorted(missing_in_specs)}"
            )

    eligible: list[FrontierProposal] = []
    for thread_id, spec in thread_specs.items():
        law = propagation_laws[thread_id]
        if _thread_satisfies_conditions(spec, law, sediment, event, last_wave_thread_ids):
            eligible.append(
                FrontierProposal(thread_id=thread_id, reason="propagation_law_satisfied")
            )

    if strategy is None:
        return tuple(eligible)

    strategy_selection = strategy.choose(
        thread_specs=thread_specs,
        propagation_laws=propagation_laws,
        sediment=sediment,
        event=event,
        last_wave_thread_ids=last_wave_thread_ids,
    )
    strategy_ids = {item.thread_id for item in strategy_selection}
    eligible_ids = {proposal.thread_id for proposal in eligible}
    # Strategy MUST NOT silently remove threads that are admissible.
    if not eligible_ids.issubset(strategy_ids):
        missing = sorted(eligible_ids - strategy_ids)
        raise ValueError(
            f"strategy removed admissible threads from the frontier: {missing}"
        )
    by_id = {proposal.thread_id: proposal for proposal in eligible}
    return tuple(by_id[item.thread_id] for item in strategy_selection
                 if item.thread_id in by_id)


class LexicographicFrontierStrategy:
    """Deterministic, content-independent ordering by ``thread_id``."""

    def choose(
        self,
        *,
        thread_specs: Mapping[str, WorkflowThreadSpec],
        propagation_laws: Mapping[str, PropagationLaw],
        sediment: SedimentState,
        event: StoneEvent | None,
        last_wave_thread_ids: tuple[str, ...],
    ) -> tuple[FrontierProposal, ...]:
        del sediment
        del event
        del last_wave_thread_ids
        return tuple(
            FrontierProposal(thread_id=thread_id, reason="lexicographic")
            for thread_id in sorted(thread_specs)
            if thread_id in propagation_laws
        )


__all__ = [
    "FrontierStrategy",
    "LexicographicFrontierStrategy",
    "select_frontier",
]


def carriers_in_read_set(
    records: Iterable[SedimentRecord],
) -> tuple[str, ...]:
    seen: list[str] = []
    for record in records:
        for carrier_id in record.source_carrier_refs:
            if carrier_id not in seen:
                seen.append(carrier_id)
    return tuple(seen)


WAKEABLE_STONE_KINDS: tuple[StoneEventKind, ...] = (
    StoneEventKind.QUERY,
    StoneEventKind.SOURCE_DELTA,
    StoneEventKind.SEDIMENT_AVAILABLE,
    StoneEventKind.RECONCILE_REQUEST,
    StoneEventKind.APORIA,
    StoneEventKind.HUMAN_DECISION,
    StoneEventKind.FRONTIER_RETURN,
)
