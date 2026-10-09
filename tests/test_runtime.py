import hashlib

import pytest

from seshat.adapters.records import RecordSourceProvider
from seshat.adapters.testing import DeterministicOperationProvider
from seshat.contracts import (
    AcceptanceState,
    AnalyticObjectSpec,
    DerivedObject,
    EvidenceAccessProfile,
    OperationSpec,
    RawAccessPolicy,
)
from seshat.runtime import EvidenceAccessError, Runtime

SPEC = OperationSpec(
    operation_id="profile.object",
    name="Object",
    target=AnalyticObjectSpec(
        object_type="object",
        object_class="distributed",
        distributed=True,
    ),
    methodological_frame="fixture",
    evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
    raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
    output_type="object",
    acceptance_right="owner",
)


def provider_for(derived_id: str):
    return DeterministicOperationProvider(
        {SPEC.operation_id},
        lambda spec, ro, obs, prior, source_access: DerivedObject(
            derived_id=derived_id,
            object_type=spec.output_type,
            version=derived_id,
            operation_id=spec.operation_id,
            research_object_id=ro.object_id,
            payload={"observation_count": len(obs), "prior_count": len(prior)},
        ),
    )


def test_full_required_fails_when_carrier_record_is_missing() -> None:
    sources = RecordSourceProvider(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
                "carrier_ids": ["c1"],
            }
        },
        carriers={},
        observations={},
    )
    runtime = Runtime(sources)

    with pytest.raises(EvidenceAccessError, match="missing carriers") as caught:
        runtime.run(SPEC, provider_for("d1"), research_object_id="r1")
    assert caught.value.code.value == "MISSING_CARRIER"


def test_full_required_rejects_metadata_only_carrier() -> None:
    sources = RecordSourceProvider(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
                "carrier_ids": ["c1"],
            }
        },
        carriers={
            "c1": {
                "carrier_id": "c1",
                "source_identity": "source:1",
                "version": "1",
                "media_type": "text/plain",
            }
        },
        observations={"r1": []},
    )
    runtime = Runtime(sources)
    with pytest.raises(EvidenceAccessError, match="content") as caught:
        runtime.run(SPEC, provider_for("d1"), research_object_id="r1")
    assert caught.value.code.value == "CONTENT_UNAVAILABLE"


def test_revised_upstream_invalidates_linked_downstream() -> None:
    content = b"complete synthetic source"
    digest = hashlib.sha256(content).hexdigest()
    sources = RecordSourceProvider(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
                "carrier_ids": ["c1"],
            }
        },
        carriers={
            "c1": {
                "carrier_id": "c1",
                "source_identity": "source:1",
                "version": "1",
                "media_type": "text/plain",
                "content_sha256": digest,
                "byte_length": len(content),
            }
        },
        observations={"r1": []},
        contents={
            "c1": {
                "carrier_id": "c1",
                "source_version": "1",
                "media_type": "text/plain",
                "content": content,
                "content_sha256": digest,
                "byte_length": len(content),
            }
        },
    )
    runtime = Runtime(sources)

    first = runtime.run(SPEC, provider_for("object-v1"), research_object_id="r1")
    downstream = DerivedObject(
        derived_id="method-v1",
        object_type="method",
        version="1",
        operation_id="profile.method",
        research_object_id="r1",
        payload={},
    )
    runtime.blackboard.put(downstream)
    runtime.link(first, downstream, dependency_type="mutual_constraint")

    runtime.run(SPEC, provider_for("object-v2"), research_object_id="r1")

    assert runtime.blackboard.get("method-v1").acceptance_state is AcceptanceState.STALE
