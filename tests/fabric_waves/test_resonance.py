"""Tests for resonance composition."""

from __future__ import annotations

import hashlib

from seshat.fabric_waves.contracts import (
    ActivationOutcome,
    ActivationRecord,
    EventRecord,
    ResonanceKind,
    StoneEventKind,
    WaveRecord,
)
from seshat.fabric_waves.resonance import (
    ResonanceComposer,
    ResonanceCompositionError,
    actionable_plan,
    answer,
    decision_request,
    frontier_gap,
    map_view,
    payload_digest,
    question,
    report,
)


def _activation(activation_id: str = "a1") -> ActivationRecord:
    return ActivationRecord(
        activation_id=activation_id,
        run_id="r1",
        wave_id="w1",
        thread_id="t1",
        started_at_tick=1,
        ended_at_tick=2,
        outcome=ActivationOutcome.FIRED,
        receipts_hash="0" * 64,
    )


def _event(event_id: str = "e1") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        run_id="r1",
        issued_at_tick=1,
        kind=StoneEventKind.QUERY,
        payload_hash=hashlib.sha256(b"{}").hexdigest(),
        kind_enum=StoneEventKind.QUERY,
    )


def _wave(wave_id: str = "w1") -> WaveRecord:
    return WaveRecord(
        wave_id=wave_id,
        run_id="r1",
        wave_index=1,
        triggered_by=StoneEventKind.QUERY,
        triggering_event_id="e1",
    )


def test_answer_carries_summary_and_payload_hash() -> None:
    record = answer(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        summary="x",
        activations=[_activation()],
        sediments=[],
        events=[_event()],
        waves=[_wave()],
    )
    assert record.kind is ResonanceKind.ANSWER
    assert record.payload_hash == payload_digest(record.payload)


def test_question_lists_blocked_threads() -> None:
    record = question(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        question_text="why?",
        blocked_thread_ids=("t-b", "t-a", "t-b"),
        events=[],
        activations=[],
    )
    assert record.payload["blocked_thread_ids"] == ["t-a", "t-b"]


def test_decision_request_requires_subject() -> None:
    record = decision_request(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        subject_sediment_id="s1",
        reason="r",
        sediments=[],
    )
    assert "s1" in record.trace_sediment_ids


def test_map_view_carries_nodes_and_edges() -> None:
    record = map_view(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        nodes=[{"id": "t1"}],
        edges=[{"from": "t1", "to": "t2"}],
        activations=[_activation()],
        sediments=[],
    )
    assert record.payload["nodes"] == [{"id": "t1"}]


def test_actionable_plan_preserves_steps() -> None:
    record = actionable_plan(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        steps=[{"step": 1}, {"step": 2}],
        sediments=[],
        activations=[_activation()],
    )
    assert [item["step"] for item in record.payload["steps"]] == [1, 2]


def test_frontier_gap_routed_to_run() -> None:
    record = frontier_gap(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        gap_id="F07",
        description="d",
        blocked_thread_ids=("t1",),
    )
    assert record.kind is ResonanceKind.FRONTIER_GAP
    assert record.payload["gap_id"] == "F07"


def test_report_bundles_sections() -> None:
    record = report(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        headline="h",
        sections=[{"k": "v"}],
    )
    assert record.payload["headline"] == "h"


def test_resonance_composer_requires_run_id() -> None:
    composer = ResonanceComposer()
    record = answer(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        summary="x",
        activations=[],
        sediments=[],
        events=[],
        waves=[],
    )
    composer.add(record)
    assert any(r.run_id == "r1" for r in composer.values())


def test_resonance_composer_adds_and_returns_copy() -> None:
    composer = ResonanceComposer()
    record = report(
        run_id="r1",
        resonance_id="res1",
        tick=1,
        headline="h",
        sections=[],
    )
    composer.add(record)
    with __import__("pytest").raises(ResonanceCompositionError):
        composer.add(record.model_copy(update={"run_id": ""}))