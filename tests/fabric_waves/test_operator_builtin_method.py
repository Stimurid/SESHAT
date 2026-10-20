"""Checks for a bounded declarative operator method instruction interpreter."""
from __future__ import annotations
import json
import pytest
from seshat.fabric_waves.operator_builtin_method import execute_literal_method
from seshat.fabric_waves.operator_local_demo import inputs
from seshat.fabric_waves.operator_methodbody import OperatorInvocation


def invocation(sample="materials", needle=None):
    source, data, _, method_data = inputs(sample)
    if needle is not None:
        method_data = json.dumps({
            "schema": "SESHAT_OPERATOR_METHOD_V1",
            "operation": "literal_span_find",
            "needle": needle,
        }).encode("utf-8")
    return OperatorInvocation(
        run_id="fixture-run", job_id="fixture-job", source_id=source.source_id,
        source_bytes=data, source_text=data.decode("utf-8"),
        method_body_id="generic.literal", method_body_version="1",
        method_body_invocation_bytes=method_data,
    )


def test_instructions_control_recovered_span():
    first = execute_literal_method(invocation())
    second = execute_literal_method(invocation(needle="fracture"))
    assert first.claims[0].evidence_excerpt != second.claims[0].evidence_excerpt
    assert first.claims[0].byte_offset != second.claims[0].byte_offset


def test_dissimilar_sources_use_same_interpreter():
    first = execute_literal_method(invocation())
    second = execute_literal_method(invocation(sample="organization"))
    assert first.research_object_id != second.research_object_id
    assert first.claims[0].evidence_excerpt != second.claims[0].evidence_excerpt


def test_unknown_operation_is_rejected():
    old = invocation()
    spec = json.dumps({
        "schema": "SESHAT_OPERATOR_METHOD_V1",
        "operation": "unsupported_operation", "needle": "x"
    }).encode("utf-8")
    item = OperatorInvocation(
        **{**vars(old), "method_body_invocation_bytes": spec}
    )
    with pytest.raises(ValueError, match="OPERATOR_METHOD_OPERATION_NOT_ALLOWED"):
        execute_literal_method(item)


def test_malformed_input_or_missing_literal_is_rejected():
    old = invocation()
    item = OperatorInvocation(
        **{**vars(old), "method_body_invocation_bytes": b"invalid-json"}
    )
    with pytest.raises(ValueError, match="OPERATOR_METHOD_INSTRUCTIONS_INVALID"):
        execute_literal_method(item)
    with pytest.raises(ValueError, match="OPERATOR_METHOD_NEEDLE_NOT_FOUND"):
        execute_literal_method(invocation(needle="LITERAL-NOT-PRESENT"))


def test_unverified_page_label_is_not_accepted_from_plain_text():
    from seshat.fabric_waves.operator_methodbody import (
        OperatorBodyResult, OperatorClaim,
        OperatorRunLedger, invoke_operator_method_body,
    )
    source, source_data, method, method_data = inputs("materials")
    needle = "alloy"
    offset = source_data.index(needle.encode("utf-8"))
    def caller(inv):
        return OperatorBodyResult(
            research_object_id=inv.source_id,
            claims=(OperatorClaim(
                text="unverified page number",
                evidence_excerpt=needle,
                byte_offset=offset,
                byte_length=len(needle),
                page=97,
            ),),
        )
    with pytest.raises(ValueError, match="OPERATOR_PAGE_MAP_REQUIRED"):
        invoke_operator_method_body(
            ledger=OperatorRunLedger(),
            run_id="invalid-page",
            job_id="local-fixture",
            source=source,
            source_bytes=source_data,
            method=method,
            method_body_invocation_bytes=method_data,
            method_callable=caller,
            requested_view="private-operator",
        )
