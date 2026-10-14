"""Deterministic synthetic SAFE fixture builders.

The fixtures here are deliberately plain: synthetic text carriers, synthetic
observations and synthetic research objects.  No donor data, no production
adapters, no secrets.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from seshat.contracts import (
    Observation,
    ResearchObject,
    SourceCarrier,
    SourceContent,
)
from seshat.fabric_waves.contracts import (
    EdgeCondition,
    MethodBodyRef,
    PropagationLaw,
    StoneEventKind,
    ThreadNodeSpec,
    WorkflowThreadSpec,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def carrier(
    *, carrier_id: str, version: str, text: str, media_type: str = "text/plain"
) -> tuple[SourceCarrier, SourceContent]:
    digest = sha256_text(text)
    src = SourceCarrier(
        carrier_id=carrier_id,
        source_identity=carrier_id,
        version=version,
        media_type=media_type,
        uri=None,
        content_sha256=digest,
        byte_length=len(text.encode("utf-8")),
        metadata={},
    )
    content = SourceContent(
        carrier_id=carrier_id,
        source_version=version,
        media_type=media_type,
        content=text.encode("utf-8"),
        content_sha256=digest,
        byte_length=len(text.encode("utf-8")),
        complete=True,
        authorized=True,
    )
    return src, content


def observation(*, observation_id: str, producer: str, content: Any) -> Observation:
    return Observation(
        observation_id=observation_id,
        observation_type="safe.fixture",
        producer=producer,
        content=content,
        addresses=(),
        provenance=("safe-fixture",),
    )


def research_object(
    *, object_id: str, carrier_ids: Iterable[str], observation_ids: Iterable[str]
) -> ResearchObject:
    return ResearchObject(
        object_id=object_id,
        object_type="safe.document",
        version="1",
        carrier_ids=list(carrier_ids),
        parent_object_ids=[],
        metadata={"observations": list(observation_ids)},
    )


# -- Thread / propagation law factories -------------------------------------


def uppercase_thread(
    *,
    carrier_id: str,
    text: str,
    thread_id: str = "t-uppercase",
) -> tuple[WorkflowThreadSpec, PropagationLaw]:
    body = MethodBodyRef(method_body_id="safe-fixture.uppercase", version="1")
    node = ThreadNodeSpec(
        node_id="upper",
        operation_id="safe.uppercase",
        output_sediment_type="safe.uppercase_text",
        produces_sediment_id=f"{thread_id}:upper",
        method_body_ref=body,
        consumes_sediment_ids=(),
        conditions=(),
    )
    spec = WorkflowThreadSpec(
        thread_id=thread_id,
        name="uppercase text reconstruction",
        purpose="convert a raw text carrier into an uppercase sediment",
        admissible_source_carriers=(carrier_id,),
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="produced at least one uppercase sediment",
        output_state=(f"{thread_id}:upper",),
        output_rationale="single safe-fixture uppercase body produces the deterministic sediment",
        state_transfer_rule="stone.payload['text'] becomes body input",
        decision_right="profile_owner",
        next_decision_right="profile_owner",
        canon_status="DRAFT",
        bounded_budget_hint=2,
        stop_rule="budget exceeded OR sandbox noise",
    )
    law = PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(carrier_id,),
        wakes_on_stone_kinds=(
            StoneEventKind.QUERY,
            StoneEventKind.SOURCE_DELTA,
        ),
    )
    return spec, law


def sum_thread(
    *,
    carrier_id: str,
    thread_id: str = "t-sum",
) -> tuple[WorkflowThreadSpec, PropagationLaw]:
    body = MethodBodyRef(method_body_id="safe-fixture.sum", version="1")
    node = ThreadNodeSpec(
        node_id="sum",
        operation_id="safe.sum",
        output_sediment_type="safe.sum",
        produces_sediment_id=f"{thread_id}:sum",
        method_body_ref=body,
        consumes_sediment_ids=(),
        conditions=(),
    )
    spec = WorkflowThreadSpec(
        thread_id=thread_id,
        name="integer sum",
        purpose="sum the values carried in the stone payload",
        admissible_source_carriers=(carrier_id,),
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="sum sediment produced",
        output_state=(f"{thread_id}:sum",),
        output_rationale="deterministic safe-fixture sum",
        decision_right="profile_owner",
        next_decision_right="profile_owner",
        canon_status="DRAFT",
        bounded_budget_hint=2,
    )
    law = PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(carrier_id,),
        wakes_on_stone_kinds=(StoneEventKind.QUERY,),
    )
    return spec, law


def corpus_aggregate_thread(
    *,
    corpus_id: str,
    thread_id: str = "t-corpus",
) -> tuple[WorkflowThreadSpec, PropagationLaw]:
    body = MethodBodyRef(
        method_body_id="safe-fixture.aggregate-corpus", version="1"
    )
    node = ThreadNodeSpec(
        node_id="aggregate",
        operation_id="safe.corpus-aggregate",
        output_sediment_type="safe.corpus_aggregate",
        produces_sediment_id=f"{corpus_id}:aggregate",
        consumes_sediment_ids=(),
        conditions=(
            EdgeCondition(
                description="requires at least one existing safe.sum sediment",
                requires_sediment_acceptance=None,
            ),
        ),
    )
    spec = WorkflowThreadSpec(
        thread_id=thread_id,
        name="corpus aggregation (C12 / C04 reuse)",
        purpose="aggregate safe.sum sediments into a corpus view",
        admissible_source_carriers=(),
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="corpus sediment produced",
        output_state=(f"{corpus_id}:aggregate",),
        output_rationale="C12/C04-corpus-aggregation applicability",
        applicability=("C12-corpus-aggregation", "C04-individual-reuse"),
        decision_right="profile_owner",
        next_decision_right="profile_owner",
        canon_status="DRAFT",
        bounded_budget_hint=4,
    )
    law = PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(),
        wakes_on_stone_kinds=(StoneEventKind.SEDIMENT_AVAILABLE,),
        wakes_on_sediment_types=("safe.sum",),
        initial_state=(),
    )
    return spec, law


def no_op_thread(thread_id: str = "t-noop") -> tuple[WorkflowThreadSpec, PropagationLaw]:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    node = ThreadNodeSpec(
        node_id="noop",
        operation_id="safe.no-op",
        output_sediment_type="safe.noop",
        produces_sediment_id=f"{thread_id}:noop",
        consumes_sediment_ids=(),
        conditions=(),
    )
    spec = WorkflowThreadSpec(
        thread_id=thread_id,
        name="noop",
        purpose="never produces a sediment",
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="body returned empty",
        output_state=(),
        canon_status="DRAFT",
    )
    law = PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(),
        wakes_on_stone_kinds=(StoneEventKind.QUERY,),
    )
    return spec, law


def fail_closed_thread(
    thread_id: str = "t-fail",
) -> tuple[WorkflowThreadSpec, PropagationLaw]:
    body = MethodBodyRef(method_body_id="safe-fixture.fail-closed", version="1")
    node = ThreadNodeSpec(
        node_id="fail",
        operation_id="safe.fail-closed",
        output_sediment_type="safe.aporia",
        produces_sediment_id=f"{thread_id}:aporia",
        consumes_sediment_ids=(),
        conditions=(),
    )
    spec = WorkflowThreadSpec(
        thread_id=thread_id,
        name="fail-closed",
        purpose="records an APORIA and stops the wave engine's bounded run",
        method_body_refs=(body,),
        nodes=(node,),
        exit_criterion="aporia recorded",
        output_state=(),
        canon_status="DRAFT",
    )
    law = PropagationLaw(
        thread_id=thread_id,
        wakes_on_carrier_ids=(),
        wakes_on_stone_kinds=(StoneEventKind.QUERY,),
    )
    return spec, law


__all__ = [
    "carrier",
    "corpus_aggregate_thread",
    "fail_closed_thread",
    "no_op_thread",
    "observation",
    "research_object",
    "sha256_text",
    "sum_thread",
    "uppercase_thread",
]


def known_carrier_ids(*specs: WorkflowThreadSpec) -> tuple[str, ...]:
    seen: list[str] = []
    for spec in specs:
        for carrier_id in spec.admissible_source_carriers:
            if carrier_id not in seen:
                seen.append(carrier_id)
    return tuple(seen)


def assemble_spec_law_map(
    pairs: Iterable[tuple[WorkflowThreadSpec, PropagationLaw]],
) -> tuple[Mapping[str, WorkflowThreadSpec], Mapping[str, PropagationLaw]]:
    specs: dict[str, WorkflowThreadSpec] = {}
    laws: dict[str, PropagationLaw] = {}
    for spec, law in pairs:
        specs[spec.thread_id] = spec
        laws[spec.thread_id] = law
    return specs, laws