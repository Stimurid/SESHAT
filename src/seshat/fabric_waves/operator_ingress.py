"""Bounded operator QUERY admission for NEVER-policy question threads.

Raw stone payloads are not passed into method bodies under RawAccessPolicy.NEVER.
This module validates a narrow QUERY schema (topic/query strings only), labels
intent as E5 proposal, and rejects common secret/forgery carrier keys.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from seshat.fabric_waves.contracts import EpistemicLevel, StoneEvent, StoneEventKind

_MAX_TOPIC_LEN = 128
_MAX_QUERY_LEN = 512
_MAX_CONTEXT_NOTE_LEN = 256

_FORBIDDEN_KEYS = frozenset(
    {
        "raw",
        "text",
        "content",
        "authorization",
        "secret",
        "credentials",
        "token",
        "password",
        "api_key",
    }
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class OperatorAdmissionError(ValueError):
    """Admission rejected; message is a stable code only."""


AporiaOccurrenceMarker = Literal["PRIOR_APORIA_CONTEXT"]


class AdmittedOperatorQuery(BaseModel):
    """Typed operator intent admitted for a single QUERY stone consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    scope_thread_id: str | None = None
    topic: str = Field(min_length=1)
    query: str = Field(min_length=1)
    aporia_occurrence_marker: AporiaOccurrenceMarker | None = None
    aporia_context_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    epistemic_level: EpistemicLevel = EpistemicLevel.E5
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _normalize_label(value: str) -> str:
    collapsed = " ".join(value.strip().split())
    if _CONTROL_CHARS.search(collapsed):
        raise OperatorAdmissionError("OPERATOR_QUERY_CONTROL_CHAR")
    return collapsed


def _payload_has_forbidden_keys(payload: Mapping[str, Any], *, depth: int = 0) -> bool:
    if depth > 4:
        return True
    for key, item in payload.items():
        lowered = str(key).lower()
        if lowered in _FORBIDDEN_KEYS:
            return True
        if isinstance(item, Mapping):
            if _payload_has_forbidden_keys(item, depth=depth + 1):
                return True
        elif isinstance(item, (list, tuple)):
            for entry in item:
                if isinstance(entry, Mapping) and _payload_has_forbidden_keys(entry, depth=depth + 1):
                    return True
    return False


def admit_aporia_context_fingerprint(payload: Mapping[str, Any]) -> str | None:
    """Hash-only fingerprint for a bounded APORIA note (never returns plaintext)."""
    if _payload_has_forbidden_keys(payload):
        raise OperatorAdmissionError("OPERATOR_APORIA_FORBIDDEN_KEY")
    note = payload.get("note")
    if note is None:
        return None
    if not isinstance(note, str):
        raise OperatorAdmissionError("OPERATOR_APORIA_NOTE_INVALID")
    normalized = _normalize_label(note)
    if not normalized:
        return None
    if len(normalized) > _MAX_CONTEXT_NOTE_LEN:
        raise OperatorAdmissionError("OPERATOR_APORIA_NOTE_TOO_LONG")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def admit_aporia_context_note(payload: Mapping[str, Any]) -> str | None:
    """Backward-compatible alias; returns SHA256 fingerprint only."""
    return admit_aporia_context_fingerprint(payload)


def _intent_digest(
    *,
    event_id: str,
    run_id: str,
    topic: str,
    query: str,
    scope_thread_id: str | None,
    aporia_context_sha256: str | None,
) -> str:
    material = {
        "event_id": event_id,
        "run_id": run_id,
        "scope_thread_id": scope_thread_id,
        "topic": topic,
        "query": query,
        "aporia_context_sha256": aporia_context_sha256,
        "epistemic_level": EpistemicLevel.E5.value,
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def admit_operator_query(
    *,
    run_id: str,
    event: StoneEvent,
    aporia_context_sha256: str | None = None,
) -> AdmittedOperatorQuery:
    if event.kind is not StoneEventKind.QUERY:
        raise OperatorAdmissionError("OPERATOR_QUERY_KIND_MISMATCH")
    payload = event.payload
    if not isinstance(payload, dict):
        raise OperatorAdmissionError("OPERATOR_QUERY_PAYLOAD_INVALID")
    if _payload_has_forbidden_keys(payload):
        raise OperatorAdmissionError("OPERATOR_QUERY_FORBIDDEN_KEY")
    topic_raw = payload.get("topic")
    query_raw = payload.get("query")
    if topic_raw is None and query_raw is None:
        raise OperatorAdmissionError("OPERATOR_QUERY_EMPTY")
    if topic_raw is not None and not isinstance(topic_raw, str):
        raise OperatorAdmissionError("OPERATOR_QUERY_TOPIC_INVALID")
    if query_raw is not None and not isinstance(query_raw, str):
        raise OperatorAdmissionError("OPERATOR_QUERY_QUERY_INVALID")
    topic = _normalize_label(topic_raw if isinstance(topic_raw, str) else "")
    query = _normalize_label(query_raw if isinstance(query_raw, str) else "")
    if not topic and not query:
        raise OperatorAdmissionError("OPERATOR_QUERY_EMPTY")
    if not topic:
        topic = "operator-query"
    if not query:
        query = "synthesize divergent operational readings"
    if len(topic) > _MAX_TOPIC_LEN:
        raise OperatorAdmissionError("OPERATOR_QUERY_TOPIC_TOO_LONG")
    if len(query) > _MAX_QUERY_LEN:
        raise OperatorAdmissionError("OPERATOR_QUERY_TOO_LONG")
    scope = event.target_thread_id
    if scope is not None and not isinstance(scope, str):
        raise OperatorAdmissionError("OPERATOR_QUERY_SCOPE_INVALID")
    marker: AporiaOccurrenceMarker | None = (
        "PRIOR_APORIA_CONTEXT" if aporia_context_sha256 else None
    )
    return AdmittedOperatorQuery(
        event_id=event.event_id,
        run_id=run_id,
        scope_thread_id=scope,
        topic=topic,
        query=query,
        aporia_occurrence_marker=marker,
        aporia_context_sha256=aporia_context_sha256,
        intent_hash=_intent_digest(
            event_id=event.event_id,
            run_id=run_id,
            topic=topic,
            query=query,
            scope_thread_id=scope,
            aporia_context_sha256=aporia_context_sha256,
        ),
    )
