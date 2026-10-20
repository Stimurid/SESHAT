"""Bounded built-in MethodBody interpreter for invented local corpus fixtures.

This is a deliberately small, auditable operation. It interprets the exact
pinned JSON MethodBody bytes supplied in OperatorInvocation instead of
accepting a callable that silently ignores the MethodBody. It never imports,
executes or evaluates code from the method. It is NOT a research LLM model.
"""
from __future__ import annotations

import json

from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorClaim,
    OperatorInvocation,
)


def execute_literal_method(invocation: OperatorInvocation) -> OperatorBodyResult:
    try:
        spec = json.loads(invocation.method_body_invocation_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OPERATOR_METHOD_INSTRUCTIONS_INVALID") from exc
    if not isinstance(spec, dict) or set(spec) != {"schema", "operation", "needle"}:
        raise ValueError("OPERATOR_METHOD_INSTRUCTIONS_INVALID")
    if spec["schema"] != "SESHAT_OPERATOR_METHOD_V1" or spec["operation"] != "literal_span_find":
        raise ValueError("OPERATOR_METHOD_OPERATION_NOT_ALLOWED")
    needle = spec["needle"]
    if not isinstance(needle, str) or not needle or len(needle) > 256:
        raise ValueError("OPERATOR_METHOD_NEEDLE_INVALID")
    raw_needle = needle.encode("utf-8")
    offset = invocation.source_bytes.find(raw_needle)
    if offset < 0:
        raise ValueError("OPERATOR_METHOD_NEEDLE_NOT_FOUND")
    return OperatorBodyResult(
        research_object_id=invocation.source_id,
        claims=(OperatorClaim(
            text="The source contains the requested literal span.",
            evidence_excerpt=needle,
            byte_offset=offset,
            byte_length=len(raw_needle),
        ),),
        notes=("instructions_interpreted_from_pinned_method_bytes",),
    )


__all__ = ["execute_literal_method"]
