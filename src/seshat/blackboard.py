"""Versioned, non-canonical state views for SESHAT.

The in-memory blackboard retains every derived object under its stable ID.
Candidate, accepted, and historical views are deliberately separate: append
order never decides semantic authority, and providers only receive admissible
candidate state.  Dependency invalidation changes status but never erases an
object, its lineage, or an unrelated branch.
"""

from __future__ import annotations

from collections import defaultdict

from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject


class StateVersionError(ValueError):
    """A version-pinned state reference no longer matches stored state."""


class InadmissibleStateError(ValueError):
    """A stored object is not admissible in the requested state view."""


class AmbiguousStateError(ValueError):
    """A singular view was requested when multiple candidates exist."""


class Blackboard:
    _CANDIDATE_STATES = frozenset(
        {AcceptanceState.WORKING, AcceptanceState.PROPOSED}
    )

    def __init__(self) -> None:
        self._objects: dict[str, DerivedObject] = {}
        self._versions_by_type: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._edges: list[DependencyEdge] = []

    @staticmethod
    def _snapshot(obj: DerivedObject) -> DerivedObject:
        return obj.model_copy(deep=True)

    def put(self, obj: DerivedObject) -> DerivedObject:
        existing = self._objects.get(obj.derived_id)
        if existing is not None:
            if existing == obj:
                return self._snapshot(existing)
            raise ValueError(
                f"derived_id {obj.derived_id!r} already identifies different content; "
                "use a new derived_id for a new version"
            )
        stored = self._snapshot(obj)
        self._objects[obj.derived_id] = stored
        key = (obj.research_object_id, obj.object_type)
        self._versions_by_type[key].append(obj.derived_id)
        return self._snapshot(stored)

    def get(self, derived_id: str, *, version: str | None = None) -> DerivedObject:
        obj = self._objects[derived_id]
        if version is not None and obj.version != version:
            raise StateVersionError(
                f"version drift for {derived_id!r}: requested {version!r}, "
                f"stored {obj.version!r}"
            )
        return self._snapshot(obj)

    def get_candidate(self, derived_id: str, *, version: str | None = None) -> DerivedObject:
        obj = self.get(derived_id, version=version)
        if obj.acceptance_state not in self._CANDIDATE_STATES:
            raise InadmissibleStateError(
                f"{derived_id!r} is not an admissible candidate "
                f"({obj.acceptance_state.value})"
            )
        return obj

    def versions(self, research_object_id: str, object_type: str) -> list[DerivedObject]:
        ids = self._versions_by_type[(research_object_id, object_type)]
        return [self._snapshot(self._objects[i]) for i in ids]

    def history(
        self, research_object_id: str, object_type: str | None = None
    ) -> tuple[DerivedObject, ...]:
        """Return all retained objects, including stale and rejected history."""
        return tuple(
            self._snapshot(obj)
            for obj in self._objects.values()
            if obj.research_object_id == research_object_id
            and (object_type is None or obj.object_type == object_type)
        )

    def candidate_state(
        self, research_object_id: str, object_type: str | None = None
    ) -> tuple[DerivedObject, ...]:
        """Return independently addressable WORKING and PROPOSED candidates."""
        return tuple(
            obj
            for obj in self.history(research_object_id, object_type)
            if obj.acceptance_state in self._CANDIDATE_STATES
        )

    def accepted_state(
        self, research_object_id: str, object_type: str | None = None
    ) -> tuple[DerivedObject, ...]:
        """Return accepted history without treating it as provider prior-state."""
        return tuple(
            obj
            for obj in self.history(research_object_id, object_type)
            if obj.acceptance_state is AcceptanceState.ACCEPTED
        )

    def latest(self, research_object_id: str, object_type: str) -> DerivedObject | None:
        """Return the sole current candidate, never an append-order winner."""
        candidates = self.candidate_state(research_object_id, object_type)
        if len(candidates) > 1:
            raise AmbiguousStateError(
                f"multiple candidate states exist for {research_object_id!r} "
                f"and {object_type!r}; use candidate_state()"
            )
        return candidates[0] if candidates else None

    def add_dependency(self, edge: DependencyEdge) -> None:
        self._edges.append(edge.model_copy(deep=True))

    def dependencies(self) -> tuple[DependencyEdge, ...]:
        return tuple(edge.model_copy(deep=True) for edge in self._edges)

    def invalidate_descendants(self, upstream_id: str) -> set[str]:
        """Mark transitively dependent descendants STALE, preserving history."""
        invalidated: set[str] = set()
        frontier = [upstream_id]
        visited = {upstream_id}
        while frontier:
            current = frontier.pop()
            for edge in self._edges:
                if (
                    edge.upstream_id == current
                    and edge.invalidates_on_change
                    and edge.downstream_id not in visited
                ):
                    visited.add(edge.downstream_id)
                    invalidated.add(edge.downstream_id)
                    frontier.append(edge.downstream_id)

        for derived_id in invalidated:
            obj = self._objects.get(derived_id)
            if obj is not None and obj.acceptance_state is not AcceptanceState.STALE:
                self._objects[derived_id] = obj.model_copy(
                    update={"acceptance_state": AcceptanceState.STALE}
                )
        return invalidated

    def mark_changed(self, upstream_id: str) -> set[str]:
        """Compatibility alias for explicit descendant invalidation."""
        return self.invalidate_descendants(upstream_id)

    def supersede(self, prior_id: str, replacement_id: str) -> set[str]:
        """Explicitly supersede one candidate and invalidate its descendants.

        Supersession is not inferred from append order.  The replacement must
        declare the prior object in its lineage and must itself be a candidate.
        Accepted state is protected from this non-authoritative transition.
        """
        prior = self._objects[prior_id]
        replacement = self._objects[replacement_id]
        if replacement.acceptance_state not in self._CANDIDATE_STATES:
            raise InadmissibleStateError(
                f"{replacement_id!r} is not an admissible candidate "
                f"({replacement.acceptance_state.value})"
            )
        if prior.acceptance_state not in self._CANDIDATE_STATES:
            raise InadmissibleStateError(
                f"{prior_id!r} cannot be superseded from "
                f"{prior.acceptance_state.value} without an authorized workflow"
            )
        if (
            prior.research_object_id != replacement.research_object_id
            or prior.object_type != replacement.object_type
        ):
            raise ValueError("a replacement must have the same research object and object type")
        if prior_id not in replacement.parent_derived_ids:
            raise ValueError("a replacement must declare the superseded object in its lineage")

        self._objects[prior_id] = prior.model_copy(
            update={"acceptance_state": AcceptanceState.STALE}
        )
        return self.invalidate_descendants(prior_id)

    def working_state(self, research_object_id: str) -> tuple[DerivedObject, ...]:
        """Backward-compatible safe alias; raw history is available via history()."""
        return self.candidate_state(research_object_id)
