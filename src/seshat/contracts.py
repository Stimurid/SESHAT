"""Core SESHAT contracts.

These models are intentionally host-neutral.  Donor systems connect through
adapters; no donor package is imported here.

A SourceAddress or Observation is evidence addressing, not semantic truth.
A DerivedObject is versioned and lineage-bearing.  An OperationSpec declares
its evidence-access requirements explicitly instead of inheriting them from
pipeline position.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceAccessProfile(StrEnum):
    META = "EAP_META"
    FULL_RECONSTRUCTION = "EAP_FULL_RECON"
    FULL_WITH_STATE = "EAP_FULL_WITH_STATE"
    LOCAL_WITH_CHECK = "EAP_LOCAL_WITH_CHECK"
    CORPUS = "EAP_CORPUS"
    EXTERNAL_JOIN = "EAP_EXTERNAL_JOIN"
    DECISION = "EAP_DECISION"


class RawAccessPolicy(StrEnum):
    NEVER = "NEVER"
    DRILLBACK = "DRILLBACK"
    FULL_REQUIRED = "FULL_REQUIRED"


class AcceptanceState(StrEnum):
    WORKING = "WORKING"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    CONTESTED = "CONTESTED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class SourceAddress(BaseModel):
    carrier_id: str
    address_type: str
    start: str | int | None = None
    end: str | int | None = None
    selector: dict[str, Any] = Field(default_factory=dict)


class SourceCarrier(BaseModel):
    carrier_id: str
    source_identity: str
    version: str
    media_type: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchObject(BaseModel):
    object_id: str
    object_type: str
    version: str
    carrier_ids: list[str] = Field(default_factory=list)
    parent_object_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    observation_id: str
    observation_type: str
    addresses: list[SourceAddress] = Field(default_factory=list)
    content: Any = None
    producer: str
    method_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)


class AnalyticObjectSpec(BaseModel):
    object_type: str
    object_class: str
    description: str = ""
    distributed: bool = False


class OperationSpec(BaseModel):
    operation_id: str
    name: str
    target: AnalyticObjectSpec
    methodological_frame: str
    evidence_access_profile: EvidenceAccessProfile
    raw_access_policy: RawAccessPolicy
    dependency_ids: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_type: str
    applicability_conditions: list[str] = Field(default_factory=list)
    acceptance_right: str
    implementation_ref: str | None = None


class DerivedObject(BaseModel):
    derived_id: str
    object_type: str
    version: str
    operation_id: str
    research_object_id: str
    payload: Any
    source_observation_ids: list[str] = Field(default_factory=list)
    parent_derived_ids: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    acceptance_state: AcceptanceState = AcceptanceState.WORKING


class DependencyEdge(BaseModel):
    upstream_id: str
    downstream_id: str
    dependency_type: str
    invalidates_on_change: bool = True
    rationale: str = ""


class Aporia(BaseModel):
    aporia_id: str
    subject_id: str
    kind: str
    evidence_ids: list[str] = Field(default_factory=list)
    description: str
    blocks_operation_ids: list[str] = Field(default_factory=list)
    proposed_reentry_ids: list[str] = Field(default_factory=list)
    resolved: bool = False


class ResearchNeed(BaseModel):
    need_id: str
    blocked_operation_id: str
    research_object_id: str
    question: str
    requested_outputs: list[str]
    semantic_action_mode: str
    return_address: str
    evidence_requirements: list[str] = Field(default_factory=list)


class EvidenceReturn(BaseModel):
    need_id: str
    research_run_id: str
    run_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_records: list[dict[str, Any]] = Field(default_factory=list)
    negative_findings: list[str] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)
    stop_reason: str
    semantic_action_mode: str
    return_address: str


class ProjectionSpec(BaseModel):
    projection_id: str
    name: str
    input_ids: list[str]
    output_schema: str
    decision_right: str | None = None
    rebuildable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
