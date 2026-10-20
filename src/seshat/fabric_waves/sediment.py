"""Versioned stable analytic substrate — the sediment.

A :class:`SedimentState` is the durable second layer of the fabric.  It is
separate from S2A's :class:`Blackboard` so the prototype can be exercised
without claiming authority over existing state.  Sediment:

* is keyed by ``sediment_id``, not by append order;
* tracks source carrier refs and method-body refs as provenance;
* records ``read_dependencies`` and ``write_dependencies`` so a SOURCE_DELTA
  can selectively wake only the threads whose read set touched a changed
  carrier;
* stores an explicit ``acceptance_state`` — promotion to ACCEPTED requires a
  :class:`DecisionRecord` from the human acceptance decision right, never the
  engine itself.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import AcceptanceState, SourceAccessManifest
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef, StoneEventKind


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


def _material_hash(material: Any) -> str:
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


class SedimentRecord(BaseModel):
    """A versioned, fully-provenanced analytic record in the sediment.

    ``version`` is content-addressed; two records with the same payload and
    provenance hash to the same content hash.  ``version_tag`` is the
    human-visible label that the engine stamps, while ``version`` is the strict
    content identity.
    """

    model_config = ConfigDict(extra="forbid")

    sediment_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    version: str = Field(min_length=1)
    research_object_id: str = Field(min_length=1)
    payload: Any = None
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: tuple[str, ...] = Field(min_length=1)
    method_body_refs: tuple[MethodBodyRef, ...] = Field(default_factory=tuple)
    source_carrier_refs: tuple[str, ...] = Field(default_factory=tuple)
    read_dependencies: tuple[str, ...] = Field(default_factory=tuple)
    write_dependencies: tuple[str, ...] = Field(default_factory=tuple)
    applicability: tuple[str, ...] = Field(default_factory=tuple)
    uncertainty: tuple[str, ...] = Field(default_factory=tuple)
    acceptance_state: AcceptanceState = AcceptanceState.WORKING
    produced_by_thread: str = Field(min_length=1)
    produced_at_tick: int = Field(ge=0)
    produced_in_wave: int = Field(ge=1)
    produced_by_stone_kind: StoneEventKind
    source_access_manifest: SourceAccessManifest | None = None
    epistemic_level: EpistemicLevel = EpistemicLevel.E3
    dependency_versions: dict[str, str] = Field(default_factory=dict)


class SedimentCollisionError(ValueError):
    """The same ``sediment_id`` already identifies different content."""


class SedimentView:
    """One observable slice of the sediment.

    Multiple views can co-exist (working, candidate, accepted, archived).  Each
    is a stable, named subset.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._records: dict[str, SedimentRecord] = {}

    def put(self, record: SedimentRecord) -> SedimentRecord:
        # Collision validation belongs to the canonical store, before publication.
        self._records[record.sediment_id] = record.model_copy(deep=True)
        return record

    def drop(self, sediment_id: str) -> None:
        self._records.pop(sediment_id, None)

    def get(self, sediment_id: str) -> SedimentRecord | None:
        record = self._records.get(sediment_id)
        return record.model_copy(deep=True) if record is not None else None

    def __contains__(self, sediment_id: str) -> bool:
        return sediment_id in self._records

    def __len__(self) -> int:
        return len(self._records)

    def values(self) -> tuple[SedimentRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._records.values())

    def for_research_object(
        self, research_object_id: str
    ) -> tuple[SedimentRecord, ...]:
        return tuple(
            record.model_copy(deep=True)
            for record in self._records.values()
            if record.research_object_id == research_object_id
        )

    def for_object_type(self, object_type: str) -> tuple[SedimentRecord, ...]:
        return tuple(
            record.model_copy(deep=True)
            for record in self._records.values()
            if record.object_type == object_type
        )


class SedimentState:
    """Container for the named views of the sediment."""

    _VIEW_NAMES = (
        "working",
        "candidate",
        "accepted",
        "stale",
    )

    def __init__(self) -> None:
        self._views: dict[str, SedimentView] = {
            name: SedimentView(name) for name in self._VIEW_NAMES
        }
        # canonical store; views are projections over it
        self._store: dict[str, SedimentRecord] = {}
        self._history: dict[str, list[SedimentRecord]] = {}
        self._decision_nonces: set[tuple[str, str]] = set()

    def _replace_from(self, staged: SedimentState) -> None:
        """Commit a validated staging state while preserving the host handle."""
        self.__dict__.update(deepcopy(staged.__dict__))

    @property
    def views(self) -> Mapping[str, SedimentView]:
        return self._views

    def _publish(self, record: SedimentRecord) -> SedimentRecord:
        canonical_id = record.sediment_id
        existing = self._store.get(canonical_id)
        # Always update the canonical store so all_records() sees the latest.
        self._store[canonical_id] = record.model_copy(deep=True)
        if existing is None:
            self._history[canonical_id] = []
        self._history[canonical_id].append(record.model_copy(deep=True))
        # Place the record in exactly one view (matching its current state).
        for view_name in self._VIEW_NAMES:
            view = self._views[view_name]
            if self._in_view(view_name, record):
                view.put(record)
            else:
                view.drop(canonical_id)
        return record

    @staticmethod
    def _in_view(view_name: str, record: SedimentRecord) -> bool:
        if view_name == "working":
            return record.acceptance_state is AcceptanceState.WORKING
        if view_name == "candidate":
            return record.acceptance_state is AcceptanceState.PROPOSED
        if view_name == "accepted":
            return record.acceptance_state is AcceptanceState.ACCEPTED
        if view_name == "stale":
            return record.acceptance_state is AcceptanceState.STALE
        return False

    def deposit(self, record: SedimentRecord) -> SedimentRecord:
        """Add a new versioned record to the sediment.

        Promotion to ACCEPTED requires :meth:`accept`; this method only writes
        WORKING/PROPOSED/STALE/CONTESTED/REJECTED records.
        """

        if record.acceptance_state is AcceptanceState.ACCEPTED:
            raise SedimentCollisionError(
                "deposit() cannot write ACCEPTED; use accept() with a decision record"
            )
        if record.payload_hash != payload_hash(record.payload):
            raise SedimentCollisionError("SEDIMENT_HASH_MISMATCH")
        previous = self._store.get(record.sediment_id)
        if previous is not None:
            if previous.version == record.version and previous.payload_hash != record.payload_hash:
                raise SedimentCollisionError("SEDIMENT_VERSION_COLLISION")
            if previous.version != record.version:
                self.invalidate_dependents(record.sediment_id, reason="UPSTREAM_VERSION_CHANGED")
        return self._publish(record)

    def invalidate_dependents(
        self, sediment_id: str, *, reason: str
    ) -> tuple[SedimentRecord, ...]:
        """Transitively mark descendants that depend on ``sediment_id`` as STALE."""

        invalidated: list[SedimentRecord] = []
        if sediment_id not in self._store:
            return tuple(invalidated)
        frontier: list[str] = [sediment_id]
        visited: set[str] = set()
        while frontier:
            current = frontier.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for record in list(self._store.values()):
                if record.sediment_id == current:
                    continue
                if current not in record.read_dependencies and current not in record.write_dependencies:
                    continue
                if record.acceptance_state is AcceptanceState.STALE:
                    frontier.append(record.sediment_id)
                    continue
                updated = record.model_copy(
                    update={
                        "acceptance_state": AcceptanceState.STALE,
                        "uncertainty": record.uncertainty + (reason,),
                    },
                    deep=True,
                )
                self._publish(updated)
                invalidated.append(updated)
                frontier.append(record.sediment_id)
        return tuple(invalidated)

    def carriers_touched_by(self, record: SedimentRecord) -> set[str]:
        return set(record.source_carrier_refs)

    def records_reading_carrier(self, carrier_id: str) -> tuple[SedimentRecord, ...]:
        return tuple(
            record
            for record in self._store.values()
            if carrier_id in record.source_carrier_refs
            or carrier_id in record.read_dependencies
        )

    def _accept_verified(
        self,
        sediment_id: str,
        *,
        decision_id: str,
        decided_at_tick: int,
    ) -> SedimentRecord:
        """Promote a single sediment record to ACCEPTED with a decision id.

        The ``decision_id`` is mandatory: a fabric engine must never silently
        self-certify acceptance.  This mirrors the S2A rule that acceptance is
        not inferred from append order.
        """

        if not decision_id:
            raise SedimentCollisionError("acceptance requires an explicit decision_id")
        record = self._store.get(sediment_id)
        if record is None:
            raise SedimentCollisionError(f"unknown sediment_id {sediment_id!r}")
        if record.acceptance_state is AcceptanceState.ACCEPTED:
            return record
        if record.acceptance_state is AcceptanceState.STALE:
            raise SedimentCollisionError(
                f"sediment_id {sediment_id!r} is STALE; reconcile before acceptance"
            )
        accepted = record.model_copy(
            update={
                "acceptance_state": AcceptanceState.ACCEPTED,
                "provenance": record.provenance + (f"accepted_by:{decision_id}", f"at_tick:{decided_at_tick}"),
            },
            deep=True,
        )
        self._publish(accepted)
        return accepted

    def accept(self, sediment_id: str, *, decision_id: str, decided_at_tick: int) -> SedimentRecord:
        """Bare strings are not human authority. Use the authenticated decision gate."""
        raise SedimentCollisionError("AUTHENTICATED_DECISION_REQUIRED")

    def version_map(self) -> dict[str, str]:
        return {
            record.sediment_id: record.version for record in self._store.values()
        }

    def history(self, sediment_id: str) -> tuple[SedimentRecord, ...]:
        return tuple(
            record.model_copy(deep=True)
            for record in self._history.get(sediment_id, ())
        )

    def all_records(self) -> tuple[SedimentRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._store.values())


__all__ = [
    "SedimentCollisionError",
    "SedimentRecord",
    "SedimentState",
    "SedimentView",
]


def payload_hash(payload: Any) -> str:
    """Content-addressed payload hash for :class:`SedimentRecord`."""

    return _material_hash(payload)
