"""Portfolio artifact export helpers (operator stones vs internal ledger events)."""

from __future__ import annotations

from typing import Any

from seshat.fabric_waves.contracts import OPERATOR_STONE_KINDS
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState


def operator_stone_events(ledger: RunLedger, run_id: str) -> list[dict[str, Any]]:
    return [
        event.model_dump(mode="python")
        for event in ledger.events
        if event.run_id == run_id and event.kind in OPERATOR_STONE_KINDS
    ]


def all_run_events(ledger: RunLedger, run_id: str) -> list[dict[str, Any]]:
    return [
        event.model_dump(mode="python")
        for event in ledger.events
        if event.run_id == run_id
    ]


def sediment_records_for_run(
    ledger: RunLedger,
    sediment: SedimentState,
    run_id: str,
) -> list[dict[str, Any]]:
    touched: set[str] = set()
    for activation in ledger.activations_for_run(run_id):
        touched.update(activation.produced_sediment_ids)
        touched.update(activation.read_sediment_ids)
    latest: dict[str, SedimentRecord] = {}
    for record in sediment.all_records():
        if record.sediment_id not in touched:
            continue
        current = latest.get(record.sediment_id)
        if current is None or record.produced_at_tick >= current.produced_at_tick:
            latest[record.sediment_id] = record
    return [
        record.model_dump(mode="python")
        for record in sorted(latest.values(), key=lambda item: item.sediment_id)
    ]


def run_ledger_head_hash(ledger: RunLedger, run_id: str) -> str | None:
    for run in ledger.runs:
        if run.run_id == run_id:
            return run.ledger_head_hash
    return None
