"""Tests for the method-body registry and safe built-ins."""

from __future__ import annotations

import dataclasses

import pytest

from seshat.fabric_waves.contracts import MethodBodyRef, StoneEventKind
from seshat.fabric_waves.method_body import (
    BodyInvocation,
    MethodBodyRegistry,
    MethodBodyViolation,
    SafeFixtureBodies,
    build_safe_fixture_registry,
    describe_signature,
)


def _invocation(
    *, method_body_id: str = "safe-fixture.uppercase", version: str = "1"
) -> BodyInvocation:
    return BodyInvocation(
        thread_id="t",
        node_id="n",
        method_body_ref=MethodBodyRef(method_body_id=method_body_id, version=version),
        stone_kind=StoneEventKind.QUERY,
        tick=1,
        wave_index=1,
        consumed_sediment_ids=(),
        carried_payload={"text": "hello"},
    )


def test_registry_pre_populates_safe_fixtures() -> None:
    registry = build_safe_fixture_registry()
    for body in SafeFixtureBodies:
        assert registry.has(
            MethodBodyRef(method_body_id=body.method_body_id, version=body.version)
        )


def test_registry_rejects_duplicate_registration() -> None:
    registry = MethodBodyRegistry()
    body = SafeFixtureBodies[0]
    registry.register(body)
    with pytest.raises(ValueError):
        registry.register(body)


def test_registry_resolves_unknown_ref() -> None:
    registry = MethodBodyRegistry()
    with pytest.raises(MethodBodyViolation):
        registry.resolve(MethodBodyRef(method_body_id="x", version="1"))


def test_uppercase_body_produces_known_payload() -> None:
    registry = build_safe_fixture_registry()
    body = registry.resolve(
        MethodBodyRef(method_body_id="safe-fixture.uppercase", version="1")
    )
    result = body(_invocation())
    assert result.produced_sediments
    record = result.produced_sediments[0]
    assert record.payload["value"] == "HELLO"


def test_sum_body_handles_integer_sequence() -> None:
    registry = build_safe_fixture_registry()
    body = registry.resolve(
        MethodBodyRef(method_body_id="safe-fixture.sum", version="1")
    )
    base = _invocation(method_body_id="safe-fixture.sum")
    invocation = dataclasses.replace(
        base,
        carried_payload={
            "values": [4, 5, 6],
            "research_object_id": "r",
            "carriers": (),
        },
    )
    result = body(invocation)
    assert result.produced_sediments[0].payload["total"] == 15


def test_fail_closed_body_records_aporia() -> None:
    registry = build_safe_fixture_registry()
    body = registry.resolve(
        MethodBodyRef(method_body_id="safe-fixture.fail-closed", version="1")
    )
    result = body(_invocation(method_body_id="safe-fixture.fail-closed"))
    assert result.aporia is not None


def test_aggregate_corpus_reads_sum_sediments() -> None:
    registry = build_safe_fixture_registry()
    body = registry.resolve(
        MethodBodyRef(method_body_id="safe-fixture.aggregate-corpus", version="1")
    )
    base = _invocation(method_body_id="safe-fixture.aggregate-corpus")
    invocation = dataclasses.replace(
        base,
        carried_payload={
            "research_object_id": "r",
            "candidate_sediments": (),
        },
    )
    result = body(invocation)
    assert result.produced_sediments[0].payload["count"] == 0


def test_describe_signature_deterministic() -> None:
    body = build_safe_fixture_registry().resolve(
        MethodBodyRef(method_body_id="safe-fixture.uppercase", version="1")
    )
    s1 = describe_signature(body(_invocation()))
    s2 = describe_signature(body(_invocation()))
    assert s1 == s2