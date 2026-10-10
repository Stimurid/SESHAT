"""Versioned, non-canonical state views for SESHAT.

The in-memory blackboard retains every derived object under its stable ID.
Candidate, accepted, and historical views are deliberately separate: append
order never decides semantic authority, and providers only receive admissible
candidate state.  Dependency invalidation changes status but never erases an
object, its lineage, or an unrelated branch.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject


class StateVersionError(ValueError):
    """A version-pinned state reference no longer matches stored state."""


class InadmissibleStateError(ValueError):
    """A stored object is not admissible in the requested state view."""


class AmbiguousStateError(ValueError):
    """A singular view was requested when multiple candidates exist."""


@dataclass(frozen=True)
class StateRevision:
    """One in-memory status snapshot for an immutable content version.

    ``DerivedObject.version`` identifies content. ``state_revision`` identifies
    a status transition of that content; this is a minimal S2A receipt, not a
    durable S6 event record.
    """

    state_revision: int
    obj: DerivedObject
    reason: str


class Blackboard:
    _CANDIDATE_STATES = frozenset(
        {AcceptanceState.WORKING, AcceptanceState.PROPOSED}
    )

    def __init__(self) -> None:
        self._objects: dict[str, DerivedObject] = {}
        self._versions_by_type: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._edges: list[DependencyEdge] = []
        self._state_history: dict[str, list[StateRevision]] = {}

    @staticmethod
    def _snapshot(obj: DerivedObject) -> DerivedObject:
        return obj.model_copy(deep=True)

    @classmethod
    def _snapshot_revision(cls, revision: StateRevision) -> StateRevision:
        return StateRevision(
            state_revision=revision.state_revision,
            obj=cls._snapshot(revision.obj),
            reason=revision.reason,
        )

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
        self._state_history[obj.derived_id] = [
            StateRevision(state_revision=0, obj=self._snapshot(stored), reason="put")
        ]
        return self._snapshot(stored)

    def get(
        self,
        derived_id: str,
        *,
        version: str | None = None,
        state_revision: int | None = None,
    ) -> DerivedObject:
        """Read content by version and, optionally, an exact status revision.

        Without ``state_revision``, this returns the current status of the
        content version. A content version pin alone is not a historical status
        snapshot.
        """
        if state_revision is None:
            obj = self._objects[derived_id]
        else:
            revisions = self._state_history[derived_id]
            match = next(
                (
                    revision
                    for revision in revisions
                    if revision.state_revision == state_revision
                ),
                None,
            )
            if match is None:
                raise StateVersionError(
                    f"state revision drift for {derived_id!r}: "
                    f"requested {state_revision!r}"
                )
            obj = match.obj
        if version is not None and obj.version != version:
            raise StateVersionError(
                f"version drift for {derived_id!r}: requested {version!r}, "
                f"stored {obj.version!r}"
            )
        return self._snapshot(obj)

    def state_history(self, derived_id: str) -> tuple[StateRevision, ...]:
        """Return numbered status snapshots and their transition reasons."""
        return tuple(
            self._snapshot_revision(revision)
            for revision in self._state_history[derived_id]
        )

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
        """Return each retained content object at its current status."""
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
            self._snapshot(obj)
            for obj in self._objects.values()
            if obj.research_object_id == research_object_id
            and (object_type is None or obj.object_type == object_type)
            if obj.acceptance_state in self._CANDIDATE_STATES
        )

    def accepted_state(
        self, research_object_id: str, object_type: str | None = None
    ) -> tuple[DerivedObject, ...]:
        """Return historical accepted admissions, including now-stale content."""
        return tuple(
            self._snapshot(revision.obj)
            for revisions in self._state_history.values()
            for revision in revisions
            if revision.obj.research_object_id == research_object_id
            and (object_type is None or revision.obj.object_type == object_type)
            and revision.obj.acceptance_state is AcceptanceState.ACCEPTED
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

    def _invalidated_descendants(self, upstream_id: str) -> set[str]:
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
        return invalidated

    def _transition(
        self, derived_id: str, state: AcceptanceState, *, reason: str
    ) -> None:
        obj = self._objects[derived_id]
        if obj.acceptance_state is state:
            return
        transitioned = obj.model_copy(update={"acceptance_state": state}, deep=True)
        self._objects[derived_id] = transitioned
        revisions = self._state_history[derived_id]
        revisions.append(
            StateRevision(
                state_revision=len(revisions),
                obj=self._snapshot(transitioned),
                reason=reason,
            )
        )

    def invalidate_descendants(self, upstream_id: str) -> set[str]:
        """Stale descendants linked by explicit invalidation edges only.

        ``parent_derived_ids`` records lineage and does not itself imply a
        validity dependency.
        """
        invalidated = self._invalidated_descendants(upstream_id)

        for derived_id in invalidated:
            obj = self._objects.get(derived_id)
            if obj is not None and obj.acceptance_state is not AcceptanceState.STALE:
                self._transition(
                    derived_id,
                    AcceptanceState.STALE,
                    reason=f"dependency_invalidation:{upstream_id}",
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
        if prior_id == replacement_id:
            raise ValueError("an object cannot supersede itself")
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
        if replacement_id in self._invalidated_descendants(prior_id):
            raise ValueError(
                "supersession would invalidate the replacement through an active "
                "dependency edge"
            )

        self._transition(
            prior_id,
            AcceptanceState.STALE,
            reason=f"supersession:{replacement_id}",
        )
        return self.invalidate_descendants(prior_id)

    def working_state(self, research_object_id: str) -> tuple[DerivedObject, ...]:
        """Backward-compatible safe alias; raw history is available via history()."""
        return self.candidate_state(research_object_id)
