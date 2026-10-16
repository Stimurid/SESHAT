"""Phase-III P1 fixes: operator QUERY admission and portable receipt digests."""

from __future__ import annotations

import hashlib
import json

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.carpet_hosts import campus_host_engine
from seshat.fabric_waves.carpet_portfolio import (
    PORTFOLIO_HASHED_ARTIFACTS,
    artifact_file_digests,
    execute_portfolio,
    export_artifacts,
)
from seshat.fabric_waves.contracts import FabricRunOutcome, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.source_module_manifest import build_source_module_manifest, verify_source_module_manifest

BUDGET = WaveBudget(max_waves=40, max_activations=60, max_stone_events=60)


def _run_campus_query(query: str) -> tuple[str, str]:
    engine = campus_host_engine()
    engine.run(
        run_id="q-run",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="q-event",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "campus-facility-utilization", "query": query},
        ),
    )
    question = engine.sediment.views["working"].get("question-campus")
    answer = engine.sediment.views["working"].get("answer-campus")
    assert question is not None and answer is not None
    return question.version, answer.version


def test_operator_query_changes_question_and_answer_versions() -> None:
    q1, a1 = _run_campus_query("compare alpha branch utilization signals")
    q2, a2 = _run_campus_query("compare beta branch maintenance memo signals")
    assert q1 != q2
    assert a1 != a2
    q3, _ = _run_campus_query("compare alpha branch utilization signals")
    assert q1 == q3


def test_operator_query_rejects_nested_secret_and_forged_rights() -> None:
    engine = campus_host_engine()
    run = engine.run(
        run_id="bad",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="bad-query",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={
                "topic": "campus-facility-utilization",
                "query": "legitimate question",
                "nested": {"secret": "must-not-admit"},
            },
        ),
    )
    assert run.outcome is FabricRunOutcome.BLOCKED
    assert engine.sediment.views["working"].get("question-campus") is None

    engine2 = campus_host_engine()
    run2 = engine2.run(
        run_id="forged",
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="forged-query",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={
                "topic": "campus-facility-utilization",
                "query": "legitimate question",
                "authorization": "ACCEPT_ALL",
            },
        ),
    )
    assert run2.outcome is FabricRunOutcome.BLOCKED
    for record in engine2.sediment.all_records():
        assert record.acceptance_state is not AcceptanceState.ACCEPTED


def test_portfolio_receipt_includes_per_file_sha256_and_detects_tamper(tmp_path) -> None:
    runs = execute_portfolio()
    receipt = export_artifacts(runs, tmp_path)
    assert receipt["portfolio_digest_sha256"]
    assert set(receipt["artifact_file_digests"]) == set(PORTFOLIO_HASHED_ARTIFACTS)
    for name in PORTFOLIO_HASHED_ARTIFACTS:
        on_disk = (tmp_path / name).read_bytes()
        entry = receipt["artifact_file_digests"][name]
        assert entry["byte_length"] == len(on_disk)
        assert entry["sha256"] == hashlib.sha256(on_disk).hexdigest()
    recomputed = artifact_file_digests(tmp_path)
    assert recomputed == receipt["artifact_file_digests"]
    stones_path = tmp_path / "stones.json"
    stones_path.write_text(stones_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    tampered = artifact_file_digests(tmp_path)
    assert tampered["stones.json"]["sha256"] != receipt["artifact_file_digests"]["stones.json"]["sha256"]


def test_source_module_manifest_in_receipt_is_self_consistent(tmp_path) -> None:
    runs = execute_portfolio()
    receipt = export_artifacts(runs, tmp_path)
    modules = receipt["source_modules"]
    assert modules["attestation"] == "SOURCE_MODULE_BYTES_VERIFIED"
    assert verify_source_module_manifest(modules)
    assert modules == build_source_module_manifest()
    git = receipt["git"]
    assert git["attestation"] in {"GIT_ATTESTED", "GIT_NOT_ATTESTED"}
    if git["attestation"] == "GIT_NOT_ATTESTED":
        assert git["head_sha"] is None or git["tree_sha"] is None
