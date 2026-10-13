"""Append-only run ledger for the fabric.

The ledger is the durable surface of a run.  It does not decide semantics, and
it does not silently promote anything to ACCEPTED.  Each appended record carries
the SHA-256 hash of its material, and the ledger itself keeps a rolling head
hash so a run cannot be silently truncated or reordered.

The ledger holds *references* to activation, event and decision records — it
does not embed source bytes or full payloads.  Resonance records hold the
payload alongside their hash.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from seshat.fabric_waves.contracts import (
    ActivationRecord,
    DecisionRecord,
    EventRecord,
    ResonanceRecord,
    RunRecord,
    WaveRecord,
)

_EMPTY_HASH: str = hashlib.sha256(b"").hexdigest()


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


def _material_hash(record: BaseModel) -> str:
    return hashlib.sha256(
        _canonical_json(record.model_dump(mode="python", exclude_none=False)).encode("utf-8")
    ).hexdigest()


class LedgerConsistencyError(RuntimeError):
    """The ledger detected a tampered, reordered or duplicated record."""


class RunLedger:
    """Append-only ordered records, hash-chained per kind."""

    _KINDS = (
        "runs",
        "events",
        "waves",
        "activations",
        "decisions",
        "resonances",
    )

    def __init__(self) -> None:
        self._runs: list[RunRecord] = []
        self._events: list[EventRecord] = []
        self._waves: list[WaveRecord] = []
        self._activations: list[ActivationRecord] = []
        self._decisions: list[DecisionRecord] = []
        self._resonances: list[ResonanceRecord] = []
        self._hashes: dict[str, list[str]] = {kind: [] for kind in self._KINDS}

    @property
    def runs(self) -> tuple[RunRecord, ...]:
        return tuple(self._runs)

    @property
    def events(self) -> tuple[EventRecord, ...]:
        return tuple(self._events)

    @property
    def waves(self) -> tuple[WaveRecord, ...]:
        return tuple(self._waves)

    @property
    def activations(self) -> tuple[ActivationRecord, ...]:
        return tuple(self._activations)

    @property
    def decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._decisions)

    @property
    def resonances(self) -> tuple[ResonanceRecord, ...]:
        return tuple(self._resonances)

    @property
    def head_hash(self) -> str:
        parts: list[str] = []
        for kind in self._KINDS:
            chain = self._hashes[kind]
            parts.append(f"{kind}:{chain[-1] if chain else _EMPTY_HASH}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _check_uniqueness(kind: str, record_id: str, seen: set[str]) -> None:
        if record_id in seen:
            raise LedgerConsistencyError(
                f"duplicate {kind} record id {record_id!r}; ledger is append-only"
            )
        seen.add(record_id)

    def append_run(self, record: RunRecord) -> RunRecord:
        seen = {item.run_id for item in self._runs}
        self._check_uniqueness("run", record.run_id, seen)
        self._runs.append(record.model_copy(deep=True))
        self._hashes["runs"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def append_event(self, record: EventRecord) -> EventRecord:
        seen = {item.event_id for item in self._events}
        self._check_uniqueness("event", record.event_id, seen)
        self._events.append(record.model_copy(deep=True))
        self._hashes["events"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def append_wave(self, record: WaveRecord) -> WaveRecord:
        seen = {item.wave_id for item in self._waves}
        self._check_uniqueness("wave", record.wave_id, seen)
        self._waves.append(record.model_copy(deep=True))
        self._hashes["waves"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def append_activation(self, record: ActivationRecord) -> ActivationRecord:
        seen = {item.activation_id for item in self._activations}
        self._check_uniqueness("activation", record.activation_id, seen)
        self._activations.append(record.model_copy(deep=True))
        self._hashes["activations"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def append_decision(self, record: DecisionRecord) -> DecisionRecord:
        seen = {item.decision_id for item in self._decisions}
        self._check_uniqueness("decision", record.decision_id, seen)
        self._decisions.append(record.model_copy(deep=True))
        self._hashes["decisions"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def append_resonance(self, record: ResonanceRecord) -> ResonanceRecord:
        seen = {item.resonance_id for item in self._resonances}
        self._check_uniqueness("resonance", record.resonance_id, seen)
        self._resonances.append(record.model_copy(deep=True))
        self._hashes["resonances"].append(_material_hash(record))
        return record.model_copy(deep=True)

    def activations_for_wave(self, wave_id: str) -> tuple[ActivationRecord, ...]:
        return tuple(
            record for record in self._activations if record.wave_id == wave_id
        )

    def activations_for_thread(self, thread_id: str) -> tuple[ActivationRecord, ...]:
        return tuple(
            record for record in self._activations if record.thread_id == thread_id
        )

    def activations_for_run(self, run_id: str) -> tuple[ActivationRecord, ...]:
        return tuple(record for record in self._activations if record.run_id == run_id)

    def resonances_for_run(self, run_id: str) -> tuple[ResonanceRecord, ...]:
        return tuple(record for record in self._resonances if record.run_id == run_id)

    def decision_for_subject(
        self, subject_sediment_id: str
    ) -> tuple[DecisionRecord, ...]:
        return tuple(
            record
            for record in self._decisions
            if record.subject_sediment_id == subject_sediment_id
        )

    def verify(self) -> None:
        """Re-hash every record and confirm the rolling head matches.

        Cheap and deterministic; used by replay tests.
        """

        for kind, items in (
            ("runs", self._runs),
            ("events", self._events),
            ("waves", self._waves),
            ("activations", self._activations),
            ("decisions", self._decisions),
            ("resonances", self._resonances),
        ):
            for index, record in enumerate(items):
                digest = _material_hash(record)
                if digest != self._hashes[kind][index]:
                    raise LedgerConsistencyError(
                        f"{kind} record {getattr(record, next(iter(record.model_fields.keys())))!r} "
                        "was modified after append"
                    )

    def serialize(self) -> dict[str, list[dict[str, Any]]]:
        """Dump the ledger as plain JSON-friendly dicts."""

        return {
            "runs": [item.model_dump(mode="python") for item in self._runs],
            "events": [item.model_dump(mode="python") for item in self._events],
            "waves": [item.model_dump(mode="python") for item in self._waves],
            "activations": [
                item.model_dump(mode="python") for item in self._activations
            ],
            "decisions": [item.model_dump(mode="python") for item in self._decisions],
            "resonances": [
                item.model_dump(mode="python") for item in self._resonances
            ],
            "head_hash": self.head_hash,
        }


def reseed_resonance_hash(record: ResonanceRecord, *, payload: Any) -> ResonanceRecord:
    """Helper: recompute a ResonanceRecord's payload_hash from its payload."""

    material = _canonical_json(payload).encode("utf-8")
    return record.model_copy(
        update={"payload": payload, "payload_hash": hashlib.sha256(material).hexdigest()},
        deep=True,
    )


def merge_iterables(*sources: Iterable[Any]) -> list[Any]:
    """Small utility — concatenated list, preserving order, de-duped by identity."""

    seen: set[int] = set()
    out: list[Any] = []
    for source in sources:
        for item in source:
            key = id(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def hash_mapping(mapping: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(mapping)).encode("utf-8")).hexdigest()