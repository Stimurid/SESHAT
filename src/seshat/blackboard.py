"""Versioned working state for SESHAT.

The blackboard stores derived analytic objects without pretending that every
working projection is canonical truth.  Dependencies are explicit and a new
accepted/working version can mark downstream objects stale.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject


class Blackboard:
    def __init__(self) -> None:
        self._objects: dict[str, DerivedObject] = {}
        self._versions_by_type: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._edges: list[DependencyEdge] = []

    def put(self, obj: DerivedObject) -> DerivedObject:
        self._objects[obj.derived_id] = obj
        key = (obj.research_object_id, obj.object_type)
        if obj.derived_id not in self._versions_by_type[key]:
            self._versions_by_type[key].append(obj.derived_id)
        return obj

    def get(self, derived_id: str) -> DerivedObject:
        return self._objects[derived_id]

    def versions(self, research_object_id: str, object_type: str) -> list[DerivedObject]:
        ids = self._versions_by_type[(research_object_id, object_type)]
        return [self._objects[i] for i in ids]

    def latest(self, research_object_id: str, object_type: str) -> DerivedObject | None:
        versions = self.versions(research_object_id, object_type)
        return versions[-1] if versions else None

    def add_dependency(self, edge: DependencyEdge) -> None:
        self._edges.append(edge)

    def dependencies(self) -> tuple[DependencyEdge, ...]:
        return tuple(self._edges)

    def mark_changed(self, upstream_id: str) -> set[str]:
        """Mark all transitively invalidated downstream objects STALE."""
        invalidated: set[str] = set()
        frontier = [upstream_id]
        while frontier:
            current = frontier.pop()
            for edge in self._edges:
                if (
                    edge.upstream_id == current
                    and edge.invalidates_on_change
                    and edge.downstream_id not in invalidated
                ):
                    invalidated.add(edge.downstream_id)
                    frontier.append(edge.downstream_id)

        for derived_id in invalidated:
            obj = self._objects.get(derived_id)
            if obj is not None and obj.acceptance_state is not AcceptanceState.STALE:
                self._objects[derived_id] = obj.model_copy(
                    update={"acceptance_state": AcceptanceState.STALE}
                )
        return invalidated

    def working_state(self, research_object_id: str) -> Iterable[DerivedObject]:
        for obj in self._objects.values():
            if obj.research_object_id == research_object_id:
                yield obj
