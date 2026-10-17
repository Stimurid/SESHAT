"""Contract-level tests for the additive fabric_waves package."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import (
    ACCEPTANCE_DECISION_RIGHT,
    ActivationOutcome,
    EdgeCondition,
    MethodBodyRef,
    PropagationLaw,
    StoneEvent,
    StoneEventKind,
    ThreadNodeSpec,
    WaveBudget,
    WorkflowThreadSpec,
)


def test_thread_spec_requires_unique_node_ids() -> None:
    with pytest.raises(ValidationError):
        WorkflowThreadSpec(
            thread_id="t",
            name="t",
            purpose="p",
            nodes=(
                ThreadNodeSpec(
                    node_id="dup",
                    operation_id="o",
                    output_sediment_type="x",
                ),
                ThreadNodeSpec(
                    node_id="dup",
                    operation_id="o",
                    output_sediment_type="x",
                ),
            ),
            exit_criterion="x",
        )


def test_thread_spec_rejects_duplicate_method_body_refs() -> None:
    body = MethodBodyRef(method_body_id="safe-fixture.no-op", version="1")
    with pytest.raises(ValidationError):
        WorkflowThreadSpec(
            thread_id="t",
            name="t",
            purpose="p",
            method_body_refs=(body, body),
            nodes=(),
            exit_criterion="x",
        )


def test_propagation_law_defaults_to_query_only() -> None:
    law = PropagationLaw(thread_id="t")
    assert law.wakes_on_stone_kinds == (StoneEventKind.QUERY,)


def test_edge_condition_must_match_by_value_not_name() -> None:
    cond = EdgeCondition(
        description="needs sediment",
        requires_sediment_id="a",
        requires_sediment_version_at_least="v9",
    )
    assert cond.requires_sediment_id == "a"
    assert cond.requires_sediment_version_at_least == "v9"


def test_stone_event_carries_carrier_target() -> None:
    event = StoneEvent(
        event_id="e1",
        kind=StoneEventKind.SOURCE_DELTA,
        issued_at_tick=3,
        payload={"old": "v1", "new": "v2"},
        target_carrier_id="c1",
    )
    assert event.target_carrier_id == "c1"


def test_wave_budget_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WaveBudget(max_waves=0, max_activations=4, max_stone_events=2)


def test_activation_outcome_enum_exhaustiveness() -> None:
    seen = {item.value for item in ActivationOutcome}
    assert seen == {
        "FIRED",
        "SKIPPED_GUARD",
        "SKIPPED_INACTIVE",
        "BLOCKED_SOURCE",
        "BLOCKED_PROVIDER",
        "SATURATED_NO_DELTA",
        "BUDGET_EXHAUSTED",
        "ERROR",
        "WAITING_EXTERNAL",
    }


def test_thread_spec_inherits_default_raw_access_policy() -> None:
    spec = WorkflowThreadSpec(
        thread_id="t",
        name="t",
        purpose="p",
        exit_criterion="x",
    )
    assert spec.raw_access_policy is RawAccessPolicy.DRILLBACK


def test_acceptance_decision_right_is_reserved_handle() -> None:
    assert ACCEPTANCE_DECISION_RIGHT == "seshat:fabric:human-acceptance"


def test_workflow_thread_spec_fourteen_properties_present() -> None:
    WorkflowThreadSpec(
        thread_id="t",
        name="t",
        purpose="p",
        exit_criterion="x",
        output_rationale="r",
        state_transfer_rule="s",
        decision_right="owner",
        next_decision_right="owner",
        constraints=("c1",),
        canon_status="DRAFT",
        bounded_budget_hint=8,
        stop_rule="halt",
    )
    fields = set(WorkflowThreadSpec.model_fields)
    required = {
        "thread_id",
        "name",
        "purpose",
        "input_state",
        "admissible_source_carriers",
        "raw_access_policy",
        "method_body_refs",
        "nodes",
        "exit_criterion",
        "output_state",
        "output_rationale",
        "state_transfer_rule",
        "decision_right",
        "next_decision_right",
        "constraints",
        "canon_status",
        "bounded_budget_hint",
        "stop_rule",
    }
    assert required.issubset(fields)


def test_thread_spec_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        WorkflowThreadSpec.model_validate(
            {
                "thread_id": "t",
                "name": "t",
                "purpose": "p",
                "exit_criterion": "x",
                "made_up_field": True,
            }
        )


def test_acceptance_state_routing_through_thread_spec() -> None:
    # Acceptance is never set on the spec; the engine never self-certifies it.
    spec = WorkflowThreadSpec(
        thread_id="t",
        name="t",
        purpose="p",
        exit_criterion="x",
    )
    payload = spec.model_dump()
    assert "acceptance_state" not in payload


def test_stone_event_kind_values_are_distinct() -> None:
    values = [item.value for item in StoneEventKind]
    assert len(values) == len(set(values))