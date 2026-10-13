"""Propagation — selective dependency invalidation and replay.

The owner charter requires that a source revision wakes only the threads whose
read set touches the changed carrier.  Propagation owns:

* the ``SOURCE_DELTA → affected threads`` projection;
* the WRITE-set append on each activation;
* the STALE propagation through the sediment when an upstream is invalidated.

It does not own acceptance promotion and does not own engine scheduling.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    PropagationLaw,
    StoneEvent,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState


def threads_woken_by_carrier_delta(
    *,
    carrier_id: str,
    thread_specs: Mapping[str, WorkflowThreadSpec],
    propagation_laws: Mapping[str, PropagationLaw],
    sediment: SedimentState,
) -> tuple[str, ...]:
    """Return the threads whose read set touches ``carrier_id``.

    The carrier matches if the thread declares it in
    :attr:`PropagationLaw.wakes_on_carrier_ids` *and* there is at least one
    live WORKING sediment record that consumed it.  Name-equal threads whose
    carrier is unused are *not* woken — transitive analogy is rejected.
    """

    woken: list[str] = []
    for thread_id, law in propagation_laws.items():
        if carrier_id not in law.wakes_on_carrier_ids:
            continue
        spec = thread_specs.get(thread_id)
        if spec is None:
            continue
        if not _law_alive(law, sediment):
            continue
        woken.append(thread_id)
    return tuple(woken)


def threads_woken_by_event(
    *,
    event: StoneEvent,
    thread_specs: Mapping[str, WorkflowThreadSpec],
    propagation_laws: Mapping[str, PropagationLaw],
) -> tuple[str, ...]:
    """Return the threads whose :attr:`PropagationLaw.wakes_on_stone_kinds`
    match ``event.kind``, and (when the event carries a carrier) whose
    ``wakes_on_carrier_ids`` includes that carrier.
    """

    woken: list[str] = []
    for thread_id, law in propagation_laws.items():
        spec = thread_specs.get(thread_id)
        if spec is None:
            continue
        if law.wakes_on_stone_kinds and event.kind not in law.wakes_on_stone_kinds:
            continue
        if (
            event.target_carrier_id is not None
            and event.target_carrier_id not in law.wakes_on_carrier_ids
        ):
            continue
        if (
            event.target_thread_id is not None
            and event.target_thread_id != thread_id
        ):
            continue
        woken.append(thread_id)
    return tuple(woken)


def _law_alive(law: PropagationLaw, sediment: SedimentState) -> bool:
    if not law.initial_state:
        return True
    working = sediment.views["working"].values()
    working_ids = {record.sediment_id for record in working}
    return set(law.initial_state).issubset(working_ids)


def append_write_set(
    *,
    thread_id: str,
    record: SedimentRecord,
    written_sediment_ids: Iterable[str],
) -> SedimentRecord:
    """Return a new record with ``write_dependencies`` extended.

    Re-activation of a thread must register its new write set; this is what
    makes a SOURCE_DELTA able to reach a downstream thread whose only input is
    a downstream-written record.
    """

    extras = tuple(written_sediment_ids)
    if not extras:
        return record
    return record.model_copy(
        update={"write_dependencies": record.write_dependencies + extras},
        deep=True,
    )


def invalidate_cascade(
    *,
    carrier_id: str,
    sediment: SedimentState,
) -> tuple[SedimentRecord, ...]:
    """Mark every WORKING record that touched ``carrier_id`` as STALE.

    The cascade covers both records that directly read ``carrier_id`` *and*
    records that depend on those readers.  Acceptance transitions are
    append-only; the sediment keeps a history.
    """

    affected: list[SedimentRecord] = []
    direct_targets: list[str] = []
    for record in sediment.all_records():
        if record.acceptance_state is AcceptanceState.STALE:
            continue
        if carrier_id not in record.source_carrier_refs:
            continue
        direct_targets.append(record.sediment_id)
    for sediment_id in direct_targets:
        sediment.invalidate_dependents(
            sediment_id,
            reason=f"carrier_revision:{carrier_id}",
        )
    # Invalidate the direct carriers themselves too.
    for sediment_id in direct_targets:
        record = sediment.views["working"].get(sediment_id)
        if record is None:
            record = next(
                (
                    item
                    for item in sediment.all_records()
                    if item.sediment_id == sediment_id
                ),
                None,
            )
        if record is None:
            continue
        if record.acceptance_state is AcceptanceState.STALE:
            affected.append(record)
            continue
        updated = record.model_copy(
            update={
                "acceptance_state": AcceptanceState.STALE,
                "uncertainty": record.uncertainty
                + (f"carrier_revision:{carrier_id}",),
            },
            deep=True,
        )
        sediment.deposit(updated)
        affected.append(updated)
    return tuple(affected)


__all__ = [
    "append_write_set",
    "invalidate_cascade",
    "threads_woken_by_carrier_delta",
    "threads_woken_by_event",
]