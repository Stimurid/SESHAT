"""Method-body registry and safe built-in bodies.

A :class:`MethodBody` is a host-neutral callable the engine invokes when a
thread fires.  Bodies are pinned by ``(method_body_id, version)`` so the
thread spec never silently changes behaviour.  Bodies are *fail-closed*:
returning anything other than a :class:`BodyResult` raises
:class:`MethodBodyViolation`.

The built-in bodies in this module are **synthetic SAFE fixtures** — they
operate on the test fixtures and the deterministic sandboxes only.  They are
not backed by the donor systems and never call into production adapters.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    ACCEPTANCE_DECISION_RIGHT,
    MethodBodyRef,
    StoneEventKind,
)
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash


class MethodBodyViolation(RuntimeError):
    """The body returned a value that is not admissible as a BodyResult."""


class BodyResult(BaseModel):
    """Typed return envelope from a MethodBody.

    ``produced_sediments`` are tentatively WORKING records; the engine decides
    whether to publish them.  ``aporia`` is the body's way of saying *this
    thread cannot proceed honestly*.
    """

    model_config = ConfigDict(extra="forbid")

    produced_sediments: tuple[SedimentRecord, ...] = Field(default_factory=tuple)
    aporia: str | None = None
    notes: tuple[str, ...] = Field(default_factory=tuple)


@dataclass(frozen=True)
class BodyInvocation:
    """The inputs a body receives when invoked."""

    thread_id: str
    node_id: str
    method_body_ref: MethodBodyRef
    stone_kind: StoneEventKind
    tick: int
    wave_index: int
    consumed_sediment_ids: tuple[str, ...]
    carried_payload: Mapping[str, Any]


class MethodBody(Protocol):
    method_body_id: str
    version: str

    def __call__(self, invocation: BodyInvocation) -> BodyResult: ...


def _canonical_payload(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda v: v.model_dump(mode="python") if isinstance(v, BaseModel) else v,
    )


def _result_payload_signature(result: BodyResult) -> str:
    material = [
        {
            "sediment_id": record.sediment_id,
            "object_type": record.object_type,
            "version": record.version,
            "payload_hash": record.payload_hash,
            "provenance": list(record.provenance),
            "method_body_refs": [
                {"id": ref.method_body_id, "version": ref.version}
                for ref in record.method_body_refs
            ],
            "read_dependencies": list(record.read_dependencies),
            "write_dependencies": list(record.write_dependencies),
            "source_carrier_refs": list(record.source_carrier_refs),
            "acceptance_state": record.acceptance_state.value,
        }
        for record in result.produced_sediments
    ]
    return hashlib.sha256(_canonical_payload(material).encode("utf-8")).hexdigest()


class MethodBodyRegistry:
    """Pinned registry keyed by ``(method_body_id, version)``."""

    def __init__(self) -> None:
        self._bodies: dict[tuple[str, str], MethodBody] = {}
        self._signatures: dict[tuple[str, str], str] = {}

    def register(self, body: MethodBody, *, signature: str | None = None) -> None:
        key = (body.method_body_id, body.version)
        if key in self._bodies:
            raise ValueError(
                f"method body {body.method_body_id}@{body.version} already registered"
            )
        self._bodies[key] = body
        self._signatures[key] = signature or hashlib.sha256(
            _canonical_payload(
                {
                    "method_body_id": body.method_body_id,
                    "version": body.version,
                    "callable": body.__class__.__qualname__,
                }
            ).encode("utf-8")
        ).hexdigest()

    def resolve(self, ref: MethodBodyRef) -> MethodBody:
        body = self._bodies.get((ref.method_body_id, ref.version))
        if body is None:
            raise MethodBodyViolation(
                f"method body {ref.method_body_id}@{ref.version} is not registered"
            )
        return body

    def has(self, ref: MethodBodyRef) -> bool:
        return (ref.method_body_id, ref.version) in self._bodies

    def known_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._bodies))

    def signature_for(self, ref: MethodBodyRef) -> str | None:
        return self._signatures.get((ref.method_body_id, ref.version))


# -- Safe built-in bodies ----------------------------------------------------
#
# These bodies operate on deterministic synthetic fixtures.  They never import
# any donor system, never touch the network, and never read production secrets.

SAFE_FIXTURE_IDS: tuple[str, ...] = (
    "safe-fixture.no-op",
    "safe-fixture.uppercase",
    "safe-fixture.sum",
    "safe-fixture.aggregate-corpus",
    "safe-fixture.fail-closed",
)


@dataclass(frozen=True)
class _SafeBody:
    method_body_id: str
    version: str
    fn: Callable[[BodyInvocation], BodyResult]

    def __call__(self, invocation: BodyInvocation) -> BodyResult:
        return self.fn(invocation)


def _no_op(invocation: BodyInvocation) -> BodyResult:
    return BodyResult(notes=("safe-fixture.no-op", f"thread={invocation.thread_id}"))


def _uppercase(invocation: BodyInvocation) -> BodyResult:
    text = invocation.carried_payload.get("text", "")
    value = str(text).upper()
    record = SedimentRecord(
        sediment_id=f"{invocation.thread_id}:{invocation.node_id}:{invocation.tick}",
        object_type="safe.uppercase_text",
        version=hashlib.sha256(value.encode("utf-8")).hexdigest()[:16],
        research_object_id=invocation.carried_payload.get(
            "research_object_id", invocation.thread_id
        ),
        payload={"value": value},
        payload_hash=payload_hash({"value": value}),
        provenance=("safe-fixture.uppercase", f"thread={invocation.thread_id}"),
        method_body_refs=(invocation.method_body_ref,),
        source_carrier_refs=tuple(invocation.carried_payload.get("carriers", ())),
        read_dependencies=invocation.consumed_sediment_ids,
        write_dependencies=(),
        produced_by_thread=invocation.thread_id,
        produced_at_tick=invocation.tick,
        produced_in_wave=invocation.wave_index,
        produced_by_stone_kind=invocation.stone_kind,
        acceptance_state=AcceptanceState.WORKING,
    )
    return BodyResult(produced_sediments=(record,))


def _sum(invocation: BodyInvocation) -> BodyResult:
    values = invocation.carried_payload.get("values", [])
    total = sum(int(item) for item in values)
    record = SedimentRecord(
        sediment_id=f"{invocation.thread_id}:{invocation.node_id}:{invocation.tick}",
        object_type="safe.sum",
        version=hashlib.sha256(str(total).encode("utf-8")).hexdigest()[:16],
        research_object_id=invocation.carried_payload.get(
            "research_object_id", invocation.thread_id
        ),
        payload={"total": total},
        payload_hash=payload_hash({"total": total}),
        provenance=("safe-fixture.sum", f"thread={invocation.thread_id}"),
        method_body_refs=(invocation.method_body_ref,),
        source_carrier_refs=tuple(invocation.carried_payload.get("carriers", ())),
        read_dependencies=invocation.consumed_sediment_ids,
        write_dependencies=(),
        produced_by_thread=invocation.thread_id,
        produced_at_tick=invocation.tick,
        produced_in_wave=invocation.wave_index,
        produced_by_stone_kind=invocation.stone_kind,
        acceptance_state=AcceptanceState.WORKING,
    )
    return BodyResult(produced_sediments=(record,))


def _aggregate_corpus(invocation: BodyInvocation) -> BodyResult:
    sums = [
        record
        for record in invocation.carried_payload.get("candidate_sediments", ())
        if record.object_type == "safe.sum"
    ]
    totals = [record.payload.get("total", 0) for record in sums]
    aggregated = {"count": len(sums), "total": sum(totals)}
    record = SedimentRecord(
        sediment_id=f"{invocation.thread_id}:{invocation.node_id}:{invocation.tick}",
        object_type="safe.corpus_aggregate",
        version=hashlib.sha256(
            json.dumps(aggregated, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        research_object_id=invocation.carried_payload.get(
            "research_object_id", invocation.thread_id
        ),
        payload=aggregated,
        payload_hash=payload_hash(aggregated),
        provenance=("safe-fixture.aggregate-corpus", f"thread={invocation.thread_id}"),
        method_body_refs=(invocation.method_body_ref,),
        source_carrier_refs=(),
        read_dependencies=tuple(record.sediment_id for record in sums),
        write_dependencies=(),
        produced_by_thread=invocation.thread_id,
        produced_at_tick=invocation.tick,
        produced_in_wave=invocation.wave_index,
        produced_by_stone_kind=invocation.stone_kind,
        applicability=(
            "C12-corpus-aggregation",
            "C04-individual-reuse",
        ),
        acceptance_state=AcceptanceState.PROPOSED,
    )
    return BodyResult(produced_sediments=(record,))


def _fail_closed(invocation: BodyInvocation) -> BodyResult:
    return BodyResult(
        aporia=f"safe-fixture.fail-closed refused to proceed on thread {invocation.thread_id}"
    )


SafeFixtureBodies: tuple[_SafeBody, ...] = (
    _SafeBody(method_body_id="safe-fixture.no-op", version="1", fn=_no_op),
    _SafeBody(method_body_id="safe-fixture.uppercase", version="1", fn=_uppercase),
    _SafeBody(method_body_id="safe-fixture.sum", version="1", fn=_sum),
    _SafeBody(
        method_body_id="safe-fixture.aggregate-corpus",
        version="1",
        fn=_aggregate_corpus,
    ),
    _SafeBody(method_body_id="safe-fixture.fail-closed", version="1", fn=_fail_closed),
)


def build_safe_fixture_registry() -> MethodBodyRegistry:
    """Return a fresh registry pre-populated with the safe built-ins."""

    registry = MethodBodyRegistry()
    for body in SafeFixtureBodies:
        registry.register(body)
    return registry


def describe_signature(result: BodyResult) -> str:
    return _result_payload_signature(result)


__all__ = [
    "ACCEPTANCE_DECISION_RIGHT",
    "SAFE_FIXTURE_IDS",
    "BodyInvocation",
    "BodyResult",
    "MethodBody",
    "MethodBodyRegistry",
    "MethodBodyViolation",
    "SafeFixtureBodies",
    "build_safe_fixture_registry",
    "describe_signature",
]