"""Bind typed I11 state to original model stdout, not a loose JSON file.

A separately present activity_network_state.json is accepted only when its
canonical network fields match the bounded JSON section in the witnessed
stdout. At most four explicitly witnessed page-1 excerpt corrections are
allowed. Semantic edits are AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED.
"""

from __future__ import annotations

import json
from typing import Any

AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED = "AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED"
MAX_P1_TYPOGRAPHIC_PATCHES = 4


def extract_bounded_json_from_stdout(stdout: bytes) -> dict[str, Any]:
    if not stdout:
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED) from exc
    fence = text.find("```json")
    cursor = text.find("{", fence if fence >= 0 else 0)
    if cursor < 0:
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    try:
        payload, _end = json.JSONDecoder().raw_decode(text[cursor:])
    except json.JSONDecodeError as exc:
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED) from exc
    if not isinstance(payload, dict) or not payload.get("work_id") or not payload.get("action_events"):
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    return payload


def _item_id(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if raw.get(key):
            return str(raw[key])
    return ""


def _addr_quote(raw: dict[str, Any]) -> str:
    return str(raw.get("quote") or raw.get("excerpt") or "")


def _addr_page(raw: dict[str, Any]) -> int | None:
    page = raw.get("page")
    return page if type(page) is int else None


def canonical_network_core(payload: dict[str, Any]) -> dict[str, Any]:
    actors = []
    for raw in payload.get("actors") or ():
        if not isinstance(raw, dict):
            raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
        actors.append({
            "id": _item_id(raw, "id", "actor_id"),
            "type": str(raw.get("type") or raw.get("actor_type") or ""),
            "work_scoped_identity": str(raw.get("work_scoped_identity") or ""),
        })
    events = []
    for raw in payload.get("action_events") or ():
        if not isinstance(raw, dict):
            raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
        events.append({
            "id": _item_id(raw, "id", "event_id"),
            "actor_ids": [str(item) for item in raw.get("actor_ids") or ()],
            "verb": str(raw.get("verb") or ""),
            "affected_entities": [str(item) for item in raw.get("affected_entities") or ()],
            "layer": str(raw.get("layer") or ""),
            "relation_mode": str(raw.get("relation_mode") or ""),
        })
    relations = []
    for raw in payload.get("relations") or ():
        if not isinstance(raw, dict):
            raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
        relations.append({
            "from": str(raw.get("from") or raw.get("from_id") or ""),
            "to": str(raw.get("to") or raw.get("to_id") or ""),
            "relation_type": str(raw.get("relation_type") or ""),
            "layer": str(raw.get("layer") or ""),
            "relation_mode": str(raw.get("relation_mode") or ""),
        })
    return {
        "work_id": str(payload.get("work_id") or ""),
        "methodbody_id": str(payload.get("methodbody_id") or ""),
        "version": str(payload.get("version") or ""),
        "actors": actors,
        "action_events": events,
        "relations": relations,
    }


def _quote_map(payload: dict[str, Any]) -> dict[tuple[str, str, int | None, int], str]:
    mapped: dict[tuple[str, str, int | None, int], str] = {}
    for kind, key in (("event", "action_events"), ("actor", "actors"), ("relation", "relations")):
        for raw in payload.get(key) or ():
            if not isinstance(raw, dict):
                continue
            entity = _item_id(raw, "id", "event_id", "actor_id") or "|".join(
                [
                    str(raw.get("from") or raw.get("from_id") or ""),
                    str(raw.get("to") or raw.get("to_id") or ""),
                    str(raw.get("relation_type") or ""),
                ]
            )
            for index, address in enumerate(raw.get("source_addresses") or ()):
                if not isinstance(address, dict):
                    continue
                mapped[(kind, entity, _addr_page(address), index)] = _addr_quote(address)
    return mapped


def _witnessed_p1_patches(derivative: dict[str, Any] | None) -> set[tuple[str, str, int]]:
    allowed: set[tuple[str, str, int]] = set()
    if not isinstance(derivative, dict):
        return allowed
    for kind, key in (("event", "action_events"), ("actor", "actors"), ("relation", "relations")):
        for raw in derivative.get(key) or ():
            if not isinstance(raw, dict):
                continue
            entity = _item_id(raw, "id", "event_id", "actor_id") or "|".join(
                [
                    str(raw.get("from") or raw.get("from_id") or ""),
                    str(raw.get("to") or raw.get("to_id") or ""),
                    str(raw.get("relation_type") or ""),
                ]
            )
            for index, address in enumerate(raw.get("source_addresses") or ()):
                if not isinstance(address, dict):
                    continue
                if _addr_page(address) != 1:
                    continue
                allowed.add((kind, entity, index))
    return allowed


def assert_state_derived_from_stdout(
    stdout_payload: dict[str, Any],
    file_payload: dict[str, Any],
    *,
    typographic_derivative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if canonical_network_core(stdout_payload) != canonical_network_core(file_payload):
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    original = _quote_map(stdout_payload)
    present = _quote_map(file_payload)
    if set(original) != set(present):
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    diffs = [
        (key[0], key[1], key[3])
        for key, quote in present.items()
        if original[key] != quote
    ]
    if not diffs:
        return {
            "status": "AUTHENTIC_STDOUT_DERIVED",
            "typographic_p1_patches": 0,
            "semantic_modifications": 0,
        }
    witnessed = _witnessed_p1_patches(typographic_derivative)
    if len(diffs) > MAX_P1_TYPOGRAPHIC_PATCHES:
        raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    for kind, entity, index in diffs:
        page_keys = [key for key in present if key[0] == kind and key[1] == entity and key[3] == index]
        if not page_keys or page_keys[0][2] != 1:
            raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
        if (kind, entity, index) not in witnessed:
            raise ValueError(AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED)
    return {
        "status": "AUTHENTIC_STDOUT_DERIVED",
        "typographic_p1_patches": len(diffs),
        "semantic_modifications": 0,
        "patch_policy": "EVIDENCE_ONLY_P1_TYPOGRAPHY",
    }
