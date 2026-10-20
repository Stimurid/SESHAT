"""Tests for the operator Stone-event CLI surface."""

from __future__ import annotations

import json

from seshat.fabric_waves.contracts import StoneEventKind, WaveBudget
from seshat.fabric_waves.operator import load_stone_events, run_operator


def test_load_stone_events_accepts_all_public_kinds() -> None:
    payload = [
        {"kind": "QUERY", "event_id": "e-query", "payload": {"values": [1]}},
        {"kind": "SOURCE_DELTA", "target_carrier_id": "c-upper", "payload": {}},
        {"kind": "APORIA", "payload": {"note": "synthetic"}},
        {"kind": "FRONTIER_RETURN", "payload": {"gap": "none"}},
        {"kind": "HUMAN_DECISION", "payload": {"choice": "defer"}},
    ]
    events = load_stone_events(payload)
    assert {event.kind for event in events} == {
        StoneEventKind.QUERY,
        StoneEventKind.SOURCE_DELTA,
        StoneEventKind.APORIA,
        StoneEventKind.FRONTIER_RETURN,
        StoneEventKind.HUMAN_DECISION,
    }


def test_run_operator_repair_profile_writes_trace(tmp_path) -> None:
    events = load_stone_events(
        [
            {
                "kind": "QUERY",
                "event_id": "op:query",
                "issued_at_tick": 0,
                "payload": {"text": "hello", "values": [1, 2, 3]},
            }
        ]
    )
    trace = run_operator(
        events=events,
        profile="repair",
        run_id="op-repair",
        budget=WaveBudget(max_waves=6, max_activations=12, max_stone_events=8),
        output_dir=tmp_path,
    )
    assert trace["run"]["run_id"] == "op-repair"
    assert (tmp_path / "op-repair.json").is_file()
    html = (tmp_path / "op-repair.html").read_text(encoding="utf-8")
    assert "Stone events (this run)" in html
    assert "Workflow threads (configured)" in html
    dumped = json.loads((tmp_path / "op-repair.json").read_text(encoding="utf-8"))
    assert dumped["stone_kinds_observed"] == ["QUERY"]
