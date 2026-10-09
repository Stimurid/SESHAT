"""Read-only record adapters.

These adapters deliberately translate donor-shaped records into SESHAT
contracts without importing donor repositories.  Direct repository/runtime
bindings can be added later behind the same protocols.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from seshat.contracts import Observation, ResearchObject, SourceAddress, SourceCarrier


class RecordSourceProvider:
    """Minimal provider over already-loaded host records."""

    def __init__(
        self,
        research_objects: Mapping[str, Mapping[str, Any]],
        carriers: Mapping[str, Mapping[str, Any]],
        observations: Mapping[str, Iterable[Mapping[str, Any]]],
    ) -> None:
        self._research_objects = research_objects
        self._carriers = carriers
        self._observations = observations

    def get_research_object(self, object_id: str) -> ResearchObject:
        return ResearchObject.model_validate(self._research_objects[object_id])

    def get_carriers(self, object_id: str) -> Iterable[SourceCarrier]:
        ro = self.get_research_object(object_id)
        for carrier_id in ro.carrier_ids:
            yield SourceCarrier.model_validate(self._carriers[carrier_id])

    def get_observations(self, object_id: str) -> Iterable[Observation]:
        for record in self._observations.get(object_id, ()):
            yield Observation.model_validate(record)


def litops_segment_observation(
    *,
    observation_id: str,
    carrier_id: str,
    segment_id: str,
    char_start: int,
    char_end: int,
    content: Any = None,
    provenance: list[str] | None = None,
) -> Observation:
    """Translate a LitOps-style addressed segment into a non-sovereign observation."""
    return Observation(
        observation_id=observation_id,
        observation_type="litops.segment",
        addresses=[
            SourceAddress(
                carrier_id=carrier_id,
                address_type="char_range",
                start=char_start,
                end=char_end,
                selector={"segment_id": segment_id},
            )
        ],
        content=content,
        producer="litops",
        provenance=list(provenance or []),
    )


def tinkuy_fabric_observation(
    *,
    observation_id: str,
    carrier_id: str,
    unit_id: str,
    char_start: int | None = None,
    char_end: int | None = None,
    content: Any = None,
    provenance: list[str] | None = None,
) -> Observation:
    """Translate one Fabric unit/evidence fragment into a SESHAT observation."""
    return Observation(
        observation_id=observation_id,
        observation_type="tinkuy.fabric_unit",
        addresses=[
            SourceAddress(
                carrier_id=carrier_id,
                address_type="char_range" if char_start is not None else "unit_ref",
                start=char_start,
                end=char_end,
                selector={"unit_id": unit_id},
            )
        ],
        content=content,
        producer="tinkuy.fabric",
        provenance=list(provenance or []),
    )


def d20_entity_observation(
    *,
    observation_id: str,
    carrier_id: str,
    entity_id: str,
    payload: Any,
    anchor_ids: list[str] | None = None,
) -> Observation:
    """Expose a D20 entity snapshot as evidence/state, not universal truth."""
    return Observation(
        observation_id=observation_id,
        observation_type="d20.entity_snapshot",
        addresses=[
            SourceAddress(
                carrier_id=carrier_id,
                address_type="entity_ref",
                selector={"entity_id": entity_id, "anchor_ids": list(anchor_ids or [])},
            )
        ],
        content=payload,
        producer="d20.fieldcore",
        provenance=list(anchor_ids or []),
    )
