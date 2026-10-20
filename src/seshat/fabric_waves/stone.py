"""Stone dispatcher — typed external/internal events that perturb the carpet.

A Stone is an event; the dispatcher holds an ordered queue, hashes each event,
and exposes the next event for the wave engine.  Stone never decides; it
provides input.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from pydantic import BaseModel

from seshat.fabric_waves.contracts import (
    EventRecord,
    StoneEvent,
    StoneEventKind,
    WaveRecord,
)


class StoneQueueFull(RuntimeError):
    """The dispatcher cannot accept more events at this time."""


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


def _payload_hash(event: StoneEvent) -> str:
    material = {
        "event_id": event.event_id,
        "kind": event.kind.value,
        "target_research_object_id": event.target_research_object_id,
        "target_carrier_id": event.target_carrier_id,
        "target_thread_id": event.target_thread_id,
        "issued_at_tick": event.issued_at_tick,
        "payload": event.payload,
    }
    return hashlib.sha256(
        _canonical_json(material).encode("utf-8")
    ).hexdigest()


class StoneDispatcher:
    """A bounded FIFO of StoneEvents for one run."""

    def __init__(self, *, max_pending: int = 1024) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        self._max_pending = max_pending
        self._queue: deque[StoneEvent] = deque()
        self._seen: set[str] = set()
        self._consumed: list[EventRecord] = []

    @property
    def pending(self) -> tuple[StoneEvent, ...]:
        return tuple(self._queue)

    @property
    def consumed(self) -> tuple[EventRecord, ...]:
        return tuple(self._consumed)

    def drop(self, event: StoneEvent) -> EventRecord:
        """Push a stone onto the queue.

        Each event_id must be unique within the run; otherwise the dispatcher
        rejects it.  This protects replay determinism.  No EventRecord is
        appended to ``consumed`` here — consumption happens via
        :meth:`consume_next`.
        """

        if event.event_id in self._seen:
            raise ValueError(
                f"duplicate stone event_id {event.event_id!r}; stones are append-only"
            )
        if len(self._queue) >= self._max_pending:
            raise StoneQueueFull(
                f"stone dispatcher full at {self._max_pending}; "
                "let the engine consume pending events first"
            )
        self._seen.add(event.event_id)
        self._queue.append(event.model_copy(deep=True))
        return EventRecord(
            event_id=event.event_id,
            run_id="",
            issued_at_tick=event.issued_at_tick,
            kind=event.kind,
            payload_hash=_payload_hash(event),
            target_research_object_id=event.target_research_object_id,
            target_carrier_id=event.target_carrier_id,
            kind_enum=event.kind,
        )

    def consume_next(self, *, run_id: str, wave: WaveRecord) -> StoneEvent | None:
        """Pop the next event and bind its EventRecord to the run/wave."""

        if not self._queue:
            return None
        event = self._queue.popleft()
        record = EventRecord(
            event_id=event.event_id,
            run_id=run_id,
            issued_at_tick=event.issued_at_tick,
            kind=event.kind,
            payload_hash=_payload_hash(event),
            target_research_object_id=event.target_research_object_id,
            target_carrier_id=event.target_carrier_id,
            consumed_by_wave_id=wave.wave_id,
            parent_activation_id=event.parent_activation_id,
            kind_enum=event.kind,
        )
        self._consumed.append(record)
        return event

    def last_consumed(self) -> EventRecord | None:
        """Return the most recently consumed EventRecord, if any."""

        if not self._consumed:
            return None
        return self._consumed[-1].model_copy(deep=True)

    def reject(self, event: StoneEvent, *, reason: str) -> EventRecord:
        """Mark an event as rejected without consuming it (used by validate-only)."""

        if event.event_id in self._seen:
            raise ValueError(
                f"duplicate stone event_id {event.event_id!r}; stones are append-only"
            )
        self._seen.add(event.event_id)
        record = EventRecord(
            event_id=event.event_id,
            run_id="",
            issued_at_tick=event.issued_at_tick,
            kind=event.kind,
            payload_hash=_payload_hash(event),
            target_research_object_id=event.target_research_object_id,
            target_carrier_id=event.target_carrier_id,
            kind_enum=event.kind,
        )
        # Side-effect marker; intentionally not in consumed chain.
        return record


__all__ = [
    "StoneDispatcher",
    "StoneQueueFull",
]


VALID_STONE_KINDS: frozenset[StoneEventKind] = frozenset(StoneEventKind)
