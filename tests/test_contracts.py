import pytest
from pydantic import ValidationError

from seshat.contracts import (
    AcceptanceState,
    AnalyticObjectSpec,
    DerivedObject,
    EvidenceAccessProfile,
    Observation,
    OperationSpec,
    RawAccessPolicy,
    SourceAddress,
)


def test_operation_must_declare_evidence_and_raw_access() -> None:
    spec = OperationSpec(
        operation_id="sechenovka.object",
        name="Object reconstruction",
        target=AnalyticObjectSpec(
            object_type="research_object",
            object_class="distributed",
            distributed=True,
        ),
        methodological_frame="AGENT_OBJECT_CORE",
        evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
        raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
        output_type="object_reconstruction",
        acceptance_right="profile_owner",
    )
    assert spec.raw_access_policy is RawAccessPolicy.FULL_REQUIRED
    assert spec.target.distributed is True


def test_observation_is_addressed_but_not_accepted_truth() -> None:
    observation = Observation(
        observation_id="obs-1",
        observation_type="method_fragment",
        addresses=[
            SourceAddress(
                carrier_id="carrier-1",
                address_type="char_range",
                start=10,
                end=50,
            )
        ],
        content="fragment",
        producer="litops",
    )
    assert observation.addresses[0].start == 10
    assert not hasattr(observation, "acceptance_state")


def test_derived_object_defaults_to_working() -> None:
    obj = DerivedObject(
        derived_id="d-1",
        object_type="object_reconstruction",
        version="1",
        operation_id="sechenovka.object",
        research_object_id="r-1",
        payload={"candidate": "x"},
    )
    assert obj.acceptance_state is AcceptanceState.WORKING


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs-bad",
            observation_type="x",
            producer="test",
            confidence=1.5,
        )
