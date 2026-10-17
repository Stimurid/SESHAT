"""Phase-III P1 fixes: operator QUERY admission and portable receipt digests."""

from __future__ import annotations

import hashlib
import json

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.carpet_hosts import campus_host_engine
from seshat.fabric_waves.carpet_portfolio import (
    PORTFOLIO_HASHED_ARTIFACTS,
    _git_meta,
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
    assert git["attestation"] in {
        "GIT_ATTESTED",
        "GIT_NOT_ATTESTED",
        "GIT_REPORTED_UNVERIFIED",
    }
    if git["attestation"] == "GIT_NOT_ATTESTED":
        assert git["head_sha"] is None or git["tree_sha"] is None


_APORIA_LEAK_SECRET = "SYNTHETIC_SECRET_DO_NOT_PERSIST"


def _export_blob(tmp_path) -> str:
    runs = execute_portfolio()
    export_artifacts(runs, tmp_path)
    parts: list[str] = []
    for name in (*PORTFOLIO_HASHED_ARTIFACTS, "receipt.json", "events.jsonl"):
        parts.append((tmp_path / name).read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_aporia_note_hash_only_never_in_portfolio_exports(tmp_path) -> None:
    engine = campus_host_engine()
    engine.dispatcher.drop(
        StoneEvent(
            event_id="aporia-secret",
            kind=StoneEventKind.APORIA,
            issued_at_tick=0,
            payload={"note": _APORIA_LEAK_SECRET},
        )
    )
    engine.dispatcher.drop(
        StoneEvent(
            event_id="query-after-aporia",
            kind=StoneEventKind.QUERY,
            issued_at_tick=1,
            payload={
                "topic": "campus-facility-utilization",
                "query": "trace aporia without leaking note text",
            },
        )
    )
    engine.run(run_id="aporia-leak-guard", budget=BUDGET)
    question = engine.sediment.views["working"].get("question-campus")
    assert question is not None
    assert _APORIA_LEAK_SECRET not in json.dumps(question.payload, ensure_ascii=False)
    assert "context_note" not in question.payload
    blob = _export_blob(tmp_path)
    assert _APORIA_LEAK_SECRET not in blob


def test_aporia_note_absent_from_events_and_stones_after_t3_path(tmp_path) -> None:
    runs = execute_portfolio()
    export_artifacts(runs, tmp_path)
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    stones = (tmp_path / "stones.json").read_text(encoding="utf-8")
    assert "operator holds promotion" not in events
    assert "operator holds promotion" not in stones
    assert "payload_hash" in events


def test_manifest_rejects_forged_module_sha_with_unchanged_digest() -> None:
    good = build_source_module_manifest()
    modules = [dict(item) for item in good["modules"]]
    modules[0]["sha256"] = "f" * 64
    forged = {**good, "modules": modules}
    assert verify_source_module_manifest(forged) is False


def test_manifest_rejects_recomputed_digest_with_tampered_entry_bytes() -> None:
    good = build_source_module_manifest()
    modules = [dict(item) for item in good["modules"]]
    modules[0]["sha256"] = "f" * 64
    modules[0]["byte_length"] = int(modules[0]["byte_length"]) + 1
    material = json.dumps(modules, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    forged = {
        **good,
        "modules": modules,
        "manifest_sha256": hashlib.sha256(material.encode("utf-8")).hexdigest(),
    }
    assert verify_source_module_manifest(forged) is False


def test_git_meta_unavailable_is_not_attested(monkeypatch) -> None:
    import seshat.fabric_waves.carpet_portfolio as portfolio

    monkeypatch.setattr(portfolio, "_git_run", lambda *args, **kwargs: None)
    meta = portfolio._git_meta()
    assert meta["attestation"] == "GIT_NOT_ATTESTED"


def test_git_meta_dirty_worktree_is_not_git_attested() -> None:
    meta = _git_meta()
    assert meta["attestation"] in {"GIT_REPORTED_UNVERIFIED", "GIT_NOT_ATTESTED"}
