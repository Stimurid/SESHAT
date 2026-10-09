"""Minimal SESHAT execution runtime.

The runtime is deliberately small.  It enforces operation contracts and leaves
domain reasoning to OperationProvider implementations.
"""

from __future__ import annotations

from collections.abc import Iterable

from seshat.adapters.base import OperationProvider, SourceProvider
from seshat.blackboard import Blackboard
from seshat.contracts import (
    DependencyEdge,
    DerivedObject,
    Observation,
    OperationSpec,
    RawAccessPolicy,
    ResearchObject,
    SourceCarrier,
)


class EvidenceAccessError(RuntimeError):
    pass


class UnsupportedOperationError(RuntimeError):
    pass


class Runtime:
    def __init__(self, source_provider: SourceProvider, blackboard: Blackboard | None = None):
        self.source_provider = source_provider
        self.blackboard = blackboard or Blackboard()

    def _carriers_for(self, research_object: ResearchObject) -> tuple[SourceCarrier, ...]:
        return tuple(self.source_provider.get_carriers(research_object.object_id))

    def _observations_for(self, research_object: ResearchObject) -> tuple[Observation, ...]:
        return tuple(self.source_provider.get_observations(research_object.object_id))

    def _enforce_access(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        carriers: tuple[SourceCarrier, ...],
    ) -> None:
        if spec.raw_access_policy is RawAccessPolicy.FULL_REQUIRED:
            if not research_object.carrier_ids:
                raise EvidenceAccessError(
                    f"{spec.operation_id} requires full source but ResearchObject has no carriers"
                )
            present = {carrier.carrier_id for carrier in carriers}
            missing = set(research_object.carrier_ids) - present
            if missing:
                raise EvidenceAccessError(
                    f"{spec.operation_id} requires full source; missing carriers: {sorted(missing)}"
                )

    def run(
        self,
        spec: OperationSpec,
        provider: OperationProvider,
        *,
        research_object_id: str,
    ) -> DerivedObject:
        research_object = self.source_provider.get_research_object(research_object_id)
        carriers = self._carriers_for(research_object)
        observations = self._observations_for(research_object)
        self._enforce_access(spec, research_object, carriers)

        if not provider.supports(spec):
            raise UnsupportedOperationError(spec.operation_id)

        prior_state = tuple(self.blackboard.working_state(research_object_id))
        result = provider.execute(spec, research_object, observations, prior_state)
        if result.operation_id != spec.operation_id:
            raise ValueError(
                f"provider returned operation_id={result.operation_id!r}, "
                f"expected {spec.operation_id!r}"
            )
        if result.research_object_id != research_object_id:
            raise ValueError("provider returned result for a different ResearchObject")

        previous = self.blackboard.latest(research_object_id, result.object_type)
        self.blackboard.put(result)

        if previous is not None and previous.derived_id != result.derived_id:
            self.blackboard.mark_changed(previous.derived_id)

        return result

    def link(
        self,
        upstream: DerivedObject,
        downstream: DerivedObject,
        *,
        dependency_type: str,
        invalidates_on_change: bool = True,
    ) -> None:
        self.blackboard.add_dependency(
            DependencyEdge(
                upstream_id=upstream.derived_id,
                downstream_id=downstream.derived_id,
                dependency_type=dependency_type,
                invalidates_on_change=invalidates_on_change,
            )
        )
