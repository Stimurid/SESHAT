"""Deterministic provider used by contract/evaluation tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable

from seshat.contracts import DerivedObject, Observation, OperationSpec, ResearchObject


class DeterministicOperationProvider:
    def __init__(
        self,
        operation_ids: set[str],
        fn: Callable[
            [OperationSpec, ResearchObject, tuple[Observation, ...], tuple[DerivedObject, ...]],
            DerivedObject,
        ],
    ) -> None:
        self.operation_ids = operation_ids
        self.fn = fn

    def supports(self, spec: OperationSpec) -> bool:
        return spec.operation_id in self.operation_ids

    def execute(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        observations: Iterable[Observation],
        prior_state: Iterable[DerivedObject],
    ) -> DerivedObject:
        return self.fn(spec, research_object, tuple(observations), tuple(prior_state))
