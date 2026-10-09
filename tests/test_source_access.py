import hashlib

import pytest

from seshat.adapters.records import RecordSourceProvider
from seshat.adapters.testing import DeterministicOperationProvider
from seshat.contracts import (
    AcceptanceState,
    AnalyticObjectSpec,
    DerivedObject,
    EvidenceAccessProfile,
    Observation,
    OperationSpec,
    RawAccessPolicy,
    SourceAccessErrorCode,
    SourceAddress,
)
from seshat.runtime import EvidenceAccessError, Runtime


def _spec(policy: RawAccessPolicy) -> OperationSpec:
    return OperationSpec(
        operation_id=f"test.{policy.value.lower()}",
        name=policy.value,
        target=AnalyticObjectSpec(object_type="analysis", object_class="synthetic"),
        methodological_frame="synthetic-fixture",
        evidence_access_profile=EvidenceAccessProfile.FULL_RECONSTRUCTION,
        raw_access_policy=policy,
        output_type="analysis",
        acceptance_right="fixture-owner",
    )


def _source_provider(
    contents: dict[str, bytes] | None,
    *,
    carrier_ids: tuple[str, ...] = ("c1",),
    versions: dict[str, str] | None = None,
    content_versions: dict[str, str] | None = None,
    expected_hashes: dict[str, str] | None = None,
    complete: dict[str, bool] | None = None,
    authorized: dict[str, bool] | None = None,
    media_types: dict[str, str] | None = None,
) -> RecordSourceProvider:
    contents = contents or {}
    versions = versions or {}
    content_versions = content_versions or {}
    expected_hashes = expected_hashes or {}
    complete = complete or {}
    authorized = authorized or {}
    media_types = media_types or {}
    carriers = {}
    content_records = {}
    for carrier_id in carrier_ids:
        data = contents.get(carrier_id)
        version = versions.get(carrier_id, "1")
        media_type = media_types.get(carrier_id, "text/plain")
        carriers[carrier_id] = {
            "carrier_id": carrier_id,
            "source_identity": f"source:{carrier_id}",
            "version": version,
            "media_type": media_type,
            "content_sha256": (
                expected_hashes.get(carrier_id)
                or (hashlib.sha256(data).hexdigest() if data is not None else None)
            ),
            "byte_length": len(data) if data is not None else None,
        }
        if data is not None:
            content_records[carrier_id] = {
                "carrier_id": carrier_id,
                "source_version": content_versions.get(carrier_id, version),
                "media_type": media_type,
                "content": data,
                "content_sha256": hashlib.sha256(data).hexdigest(),
                "byte_length": len(data),
                "complete": complete.get(carrier_id, True),
                "authorized": authorized.get(carrier_id, True),
            }
    return RecordSourceProvider(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
                "carrier_ids": list(carrier_ids),
            }
        },
        carriers=carriers,
        observations={"r1": []},
        contents=content_records,
    )


def _derived(spec, research_object, payload) -> DerivedObject:
    return DerivedObject(
        derived_id=f"d-{spec.raw_access_policy.value.lower()}",
        object_type=spec.output_type,
        version="1",
        operation_id=spec.operation_id,
        research_object_id=research_object.object_id,
        payload=payload,
    )


def _provider(spec: OperationSpec, fn):
    return DeterministicOperationProvider(
        {spec.operation_id},
        lambda op, ro, observations, prior, access: _derived(op, ro, fn(access)),
    )


def test_full_required_validates_and_exposes_complete_content() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    data = b"section one\nsection two contains the finding"
    result = Runtime(_source_provider({"c1": data})).run(
        spec,
        _provider(spec, lambda access: {"seen": access.read_all("c1").decode()}),
        research_object_id="r1",
    )

    assert result.payload == {"seen": data.decode()}
    assert result.acceptance_state is AcceptanceState.WORKING
    assert result.source_access_manifest is not None
    assert result.source_access_manifest.all_declared_sources_verified is True
    assert {receipt.content_sha256 for receipt in result.source_access_manifest.receipts} == {
        hashlib.sha256(data).hexdigest()
    }


def test_full_required_blocks_when_one_of_two_contents_is_missing() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    calls = []
    provider = _provider(spec, lambda access: calls.append(access) or {})

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(_source_provider({"c1": b"one"}, carrier_ids=("c1", "c2"))).run(
            spec, provider, research_object_id="r1"
        )

    assert caught.value.code is SourceAccessErrorCode.CONTENT_UNAVAILABLE
    assert calls == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("version", SourceAccessErrorCode.SOURCE_DRIFT),
        ("digest", SourceAccessErrorCode.INTEGRITY_ERROR),
    ],
)
def test_full_required_rejects_version_or_digest_drift(mutation, expected_code) -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    data = b"stable bytes"
    sources = _source_provider(
        {"c1": data},
        content_versions={"c1": "2"} if mutation == "version" else None,
        expected_hashes={"c1": "0" * 64} if mutation == "digest" else None,
    )

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(sources).run(spec, _provider(spec, lambda access: {}), research_object_id="r1")

    assert caught.value.code is expected_code


def test_full_required_rejects_partial_snippet() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    sources = _source_provider({"c1": b"snippet"}, complete={"c1": False})

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(sources).run(spec, _provider(spec, lambda access: {}), research_object_id="r1")

    assert caught.value.code is SourceAccessErrorCode.PARTIAL_SOURCE


def test_full_required_rejects_unauthorized_content() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    sources = _source_provider({"c1": b"restricted"}, authorized={"c1": False})

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(sources).run(spec, _provider(spec, lambda access: {}), research_object_id="r1")

    assert caught.value.code is SourceAccessErrorCode.UNAUTHORIZED


def test_drillback_returns_exact_versioned_bounded_span_and_receipt() -> None:
    spec = _spec(RawAccessPolicy.DRILLBACK)
    data = "alpha βeta omega".encode()
    address = SourceAddress(
        carrier_id="c1",
        source_version="1",
        address_type="char_range",
        start=6,
        end=10,
    )
    result = Runtime(_source_provider({"c1": data})).run(
        spec,
        _provider(spec, lambda access: {"span": access.read(address).decode()}),
        research_object_id="r1",
    )

    assert result.payload == {"span": "βeta"}
    receipt = result.source_access_manifest.receipts[0]
    assert receipt.address == address
    assert receipt.source_version == "1"
    assert receipt.returned_byte_length == len("βeta".encode())
    assert result.source_access_manifest.all_declared_sources_verified is False


@pytest.mark.parametrize(
    "address",
    [
        SourceAddress(
            carrier_id="c1",
            source_version="1",
            address_type="byte_range",
            start=0,
            end=999,
        ),
        SourceAddress(
            carrier_id="other",
            source_version="1",
            address_type="byte_range",
            start=0,
            end=1,
        ),
    ],
)
def test_drillback_rejects_out_of_range_or_wrong_carrier(address) -> None:
    spec = _spec(RawAccessPolicy.DRILLBACK)

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(_source_provider({"c1": b"short"})).run(
            spec,
            _provider(spec, lambda access: access.read(address)),
            research_object_id="r1",
        )

    assert caught.value.code is SourceAccessErrorCode.INVALID_ADDRESS


def test_never_denies_raw_fetch_but_allows_observation_only_operation() -> None:
    spec = _spec(RawAccessPolicy.NEVER)
    sources = _source_provider({"c1": b"secret"})
    address = SourceAddress(
        carrier_id="c1",
        source_version="1",
        address_type="byte_range",
        start=0,
        end=1,
    )

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(sources).run(
            spec,
            _provider(spec, lambda access: access.read(address)),
            research_object_id="r1",
        )
    assert caught.value.code is SourceAccessErrorCode.POLICY_DENIED

    result = Runtime(sources).run(
        spec,
        _provider(spec, lambda access: {"observation_only": True}),
        research_object_id="r1",
    )
    assert result.payload == {"observation_only": True}
    assert result.source_access_manifest.policy is RawAccessPolicy.NEVER


def test_unsupported_medium_fails_without_fabricated_reader() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    sources = _source_provider({"c1": b"%PDF fixture"}, media_types={"c1": "application/pdf"})

    with pytest.raises(EvidenceAccessError) as caught:
        Runtime(sources).run(spec, _provider(spec, lambda access: {}), research_object_id="r1")

    assert caught.value.code is SourceAccessErrorCode.UNSUPPORTED_MEDIA


def test_observation_remains_non_sovereign_and_result_remains_working() -> None:
    observation = Observation(
        observation_id="candidate",
        observation_type="candidate-address",
        producer="fixture",
    )
    result = _derived(_spec(RawAccessPolicy.NEVER), _source_provider({}).get_research_object("r1"), {})

    assert not hasattr(observation, "acceptance_state")
    assert result.acceptance_state is AcceptanceState.WORKING


def test_repeated_full_reads_are_stable_and_side_effect_free() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    data = b"repeatable"
    result = Runtime(_source_provider({"c1": data})).run(
        spec,
        _provider(
            spec,
            lambda access: {
                "same": access.read_all("c1") == access.read_all("c1") == data,
            },
        ),
        research_object_id="r1",
    )

    assert result.payload == {"same": True}
    assert all(
        receipt.content_sha256 == hashlib.sha256(data).hexdigest()
        for receipt in result.source_access_manifest.receipts
    )


def test_source_read_error_persists_no_misleading_derived_object() -> None:
    spec = _spec(RawAccessPolicy.FULL_REQUIRED)
    sources = _source_provider({"c1": b"available metadata"})

    class RaisingContentProvider:
        def open_content(self, carrier_id):
            raise OSError("synthetic reader failure")

    runtime = Runtime(sources, source_content_provider=RaisingContentProvider())
    with pytest.raises(EvidenceAccessError) as caught:
        runtime.run(spec, _provider(spec, lambda access: {}), research_object_id="r1")

    assert caught.value.code is SourceAccessErrorCode.READ_ERROR
    assert caught.value.manifest.receipts[0].error_code is SourceAccessErrorCode.READ_ERROR
    assert runtime.blackboard.latest("r1", "analysis") is None
