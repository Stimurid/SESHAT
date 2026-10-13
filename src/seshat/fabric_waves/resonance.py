"""Typed resonance projections.

The owner charter reserves six resonance kinds: answer, question, map,
actionable plan, frontier gap, decision request.  The fabric also exposes a
seventh, ``REPORT``, for combined view bundles.  Each :class:`ResonanceRecord`
carries the run id, the kind, the trace event/activation/sediment ids and a
content hash so the projection is traceable end-to-end.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from seshat.fabric_waves.contracts import (
    ActivationRecord,
    EventRecord,
    ResonanceKind,
    ResonanceRecord,
    RunRecord,
    WaveRecord,
)


class ResonanceCompositionError(RuntimeError):
    """A projection could not be composed because of missing or invalid input."""


def _canonical_payload(value: Any) -> str:
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


def payload_digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()


def answer(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    summary: str,
    activations: Iterable[ActivationRecord],
    sediments: Iterable[Any],
    events: Iterable[EventRecord],
    waves: Iterable[WaveRecord],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.ANSWER.value,
        "summary": summary,
        "evidence": [
            {
                "sediment_id": getattr(record, "sediment_id", None),
                "object_type": getattr(record, "object_type", None),
                "version": getattr(record, "version", None),
                "acceptance_state": getattr(
                    getattr(record, "acceptance_state", None), "value", None
                ),
            }
            for record in sediments
        ],
    }
    digest = payload_digest(payload)
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.ANSWER,
        produced_at_tick=tick,
        trace_event_ids=tuple(event.event_id for event in events),
        trace_activation_ids=tuple(act.activation_id for act in activations),
        trace_wave_ids=tuple(wave.wave_id for wave in waves),
        trace_sediment_ids=tuple(
            getattr(record, "sediment_id", "") for record in sediments
        ),
        payload=payload,
        payload_hash=digest,
    )


def question(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    question_text: str,
    blocked_thread_ids: Iterable[str],
    events: Iterable[EventRecord],
    activations: Iterable[ActivationRecord],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.QUESTION.value,
        "text": question_text,
        "blocked_thread_ids": sorted(set(blocked_thread_ids)),
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.QUESTION,
        produced_at_tick=tick,
        trace_event_ids=tuple(event.event_id for event in events),
        trace_activation_ids=tuple(act.activation_id for act in activations),
        trace_wave_ids=(),
        trace_sediment_ids=(),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


def map_view(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    activations: Iterable[ActivationRecord],
    sediments: Iterable[Any],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.MAP.value,
        "nodes": list(nodes),
        "edges": list(edges),
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.MAP,
        produced_at_tick=tick,
        trace_event_ids=(),
        trace_activation_ids=tuple(act.activation_id for act in activations),
        trace_wave_ids=(),
        trace_sediment_ids=tuple(
            getattr(record, "sediment_id", "") for record in sediments
        ),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


def actionable_plan(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    steps: Iterable[Mapping[str, Any]],
    sediments: Iterable[Any],
    activations: Iterable[ActivationRecord],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.ACTIONABLE_PLAN.value,
        "steps": list(steps),
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.ACTIONABLE_PLAN,
        produced_at_tick=tick,
        trace_event_ids=(),
        trace_activation_ids=tuple(act.activation_id for act in activations),
        trace_wave_ids=(),
        trace_sediment_ids=tuple(
            getattr(record, "sediment_id", "") for record in sediments
        ),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


def frontier_gap(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    gap_id: str,
    description: str,
    blocked_thread_ids: Iterable[str],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.FRONTIER_GAP.value,
        "gap_id": gap_id,
        "description": description,
        "blocked_thread_ids": sorted(set(blocked_thread_ids)),
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.FRONTIER_GAP,
        produced_at_tick=tick,
        trace_event_ids=(),
        trace_activation_ids=(),
        trace_wave_ids=(),
        trace_sediment_ids=(),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


def decision_request(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    subject_sediment_id: str,
    reason: str,
    sediments: Iterable[Any],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.DECISION_REQUEST.value,
        "subject_sediment_id": subject_sediment_id,
        "reason": reason,
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.DECISION_REQUEST,
        produced_at_tick=tick,
        trace_event_ids=(),
        trace_activation_ids=(),
        trace_wave_ids=(),
        trace_sediment_ids=tuple(
            (subject_sediment_id,)
            + tuple(getattr(record, "sediment_id", "") for record in sediments)
        ),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


def report(
    *,
    run_id: str,
    resonance_id: str,
    tick: int,
    headline: str,
    sections: Iterable[Mapping[str, Any]],
) -> ResonanceRecord:
    payload = {
        "kind": ResonanceKind.REPORT.value,
        "headline": headline,
        "sections": list(sections),
    }
    return ResonanceRecord(
        resonance_id=resonance_id,
        run_id=run_id,
        kind=ResonanceKind.REPORT,
        produced_at_tick=tick,
        trace_event_ids=(),
        trace_activation_ids=(),
        trace_wave_ids=(),
        trace_sediment_ids=(),
        payload=payload,
        payload_hash=payload_digest(payload),
    )


class ResonanceComposer:
    """Bundles multiple resonances from a single run for HTML/SVG rendering."""

    def __init__(self) -> None:
        self._resonances: list[ResonanceRecord] = []

    def add(self, record: ResonanceRecord) -> ResonanceRecord:
        if record.run_id == "":
            raise ResonanceCompositionError(
                "resonance record must have an explicit run_id"
            )
        self._resonances.append(record.model_copy(deep=True))
        return record.model_copy(deep=True)

    def values(self) -> tuple[ResonanceRecord, ...]:
        return tuple(self._resonances)

    def bundle(self, run_record: RunRecord) -> ResonanceRecord:
        return report(
            run_id=run_record.run_id,
            resonance_id=f"{run_record.run_id}:resonance:bundle",
            tick=run_record.ended_at_tick,
            headline=f"SESHAT fabric run {run_record.run_id}",
            sections=[
                {
                    "outcome": run_record.outcome.value,
                    "stop_reason": run_record.stop_reason.value,
                    "waves_emitted": run_record.waves_emitted,
                    "activations_total": run_record.activations_total,
                    "kinds": [record.kind.value for record in self._resonances],
                }
            ],
        )


__all__ = [
    "ResonanceComposer",
    "ResonanceCompositionError",
    "actionable_plan",
    "answer",
    "decision_request",
    "frontier_gap",
    "map_view",
    "payload_digest",
    "question",
    "report",
]