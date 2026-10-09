"""Adapter protocols.

Adapters preserve host authority.  They translate into or out of SESHAT
contracts but do not silently transfer semantic ownership to SESHAT.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from seshat.contracts import (
    DerivedObject,
    EvidenceReturn,
    Observation,
    OperationSpec,
    ResearchNeed,
    ResearchObject,
    SourceCarrier,
)


class SourceProvider(Protocol):
    def get_research_object(self, object_id: str) -> ResearchObject: ...

    def get_carriers(self, object_id: str) -> Iterable[SourceCarrier]: ...

    def get_observations(self, object_id: str) -> Iterable[Observation]: ...


class OperationProvider(Protocol):
    def supports(self, spec: OperationSpec) -> bool: ...

    def execute(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        observations: Iterable[Observation],
        prior_state: Iterable[DerivedObject],
    ) -> DerivedObject: ...


class ResearchBroker(Protocol):
    def dispatch(self, need: ResearchNeed) -> str: ...

    def collect(self, research_run_id: str) -> EvidenceReturn: ...


class AcceptanceProvider(Protocol):
    def propose(self, derived: DerivedObject) -> str: ...

    def status(self, proposal_id: str) -> str: ...
