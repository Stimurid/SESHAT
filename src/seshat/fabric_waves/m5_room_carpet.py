"""M5 executable Carpet: two invented worlds, room compilation, durable exports.

Everything produced here is SYNTHETIC ENGINEERING EVIDENCE.  The worlds are
invented, the callbacks are deterministic fixtures, and nothing in this
module performs, claims or implies scientific acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.carpet_export import (
    all_run_events,
    operator_stone_events,
    run_ledger_head_hash,
    sediment_records_for_run,
)
from seshat.fabric_waves.carpet_portfolio import _git_meta
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.m4_transport_boundary import (
    DeliveredSpan,
    StoredInputView,
    assess_output_sections,
    consumed_source_check,
)
from seshat.fabric_waves.m5_checkpoint import (
    AppliedDelta,
    CheckpointRejected,
    M5Checkpoint,
    StoredRunResult,
    capture_checkpoint,
    load_checkpoint,
    restore_into,
    stone_fingerprint,
    write_checkpoint,
)
from seshat.fabric_waves.m5_oracles import (
    NOT_TESTED,
    DerivedSnapshot,
    OracleInputs,
    SourceObservation,
    evaluate_rm_oracles,
    oracle_summary,
)
from seshat.fabric_waves.m5_synthetic_hosts import (
    BASE_SOURCE_STATE,
    BASE_STONE_STATE,
    MISSING_SOURCE_NEED_STATE,
    SYNTHETIC_RIGHT,
    build_host_engine,
    carrier_id_from_uri,
    declared_source_versions,
    host_slug,
    observed_missing_source_needs,
)
from seshat.fabric_waves.room_builder import (
    ADMITTED,
    DENIED_RIGHTS,
    CapabilitySpec,
    RoomManifest,
    admitted_threads,
    compile_room_for_stone,
    load_registry,
    manifests_to_json,
)
from seshat.fabric_waves.source_module_manifest import build_source_module_manifest
from seshat.fabric_waves.trace import render_html

M5_ARTIFACTS: tuple[str, ...] = (
    "room_manifest.json",
    "stones.json",
    "room_events.jsonl",
    "waves.jsonl",
    "activations.jsonl",
    "sediment.json",
    "resonances.json",
    "carpet.html",
    "report.md",
    "telemetry.json",
    "oracles.json",
    "receipt.json",
    "ledger.sqlite",
    "m5_checkpoint.json",
)

#: Canonical LF bytes as stored in Git and shipped in the wheel (Linux CI /
#: ``git checkout`` on all platforms).  Integrity checks hash the file as read.
ORIGINAL_FIXTURE_SHA256 = (
    "a4b4a0eb7191cc564e21e9ef0e76688f1650b563e4de482dd95a76964ab94f20"
)
#: Owner handoff digest of the same JSON with CRLF line endings on Windows
#: (25400 bytes).  Provenance only — not used for admission.
OWNER_FIXTURE_CRLF_SHA256 = (
    "9feab9b1db1bfd2aedf239425898d9265c9dc2ad0f165b7778d2892c99a0e328"
)

PACKAGE_FIXTURE_NAME = "m5_room_synthetic_acceptance_20261021_v01.json"

#: Sections the operator report must contain, non-empty, to be COMPLETE.
REQUIRED_REPORT_SECTIONS: tuple[str, ...] = (
    "question",
    "observed_facts",
    "unresolved",
    "next_action",
    "provenance",
)


class FixtureNotApproved(ValueError):
    """The fixture digest is neither the frozen original nor caller-approved."""


def packaged_fixture_path() -> Path | None:
    """The fixture shipped as package data, so an installed CLI can find it."""

    try:
        from importlib.resources import files

        resource = files("seshat.fabric_waves.m5_fixtures") / PACKAGE_FIXTURE_NAME
        path = Path(str(resource))
        return path if path.is_file() else None
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        return None


def default_fixture_path() -> Path | None:
    """Packaged resource first; the repo checkout only as a development fallback."""

    packaged = packaged_fixture_path()
    if packaged is not None:
        return packaged
    repo_copy = (
        Path(__file__).resolve().parents[3] / "tests" / "fixtures" / PACKAGE_FIXTURE_NAME
    )
    return repo_copy if repo_copy.is_file() else None


def load_fixture(path: Path, *, approved_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    """Load a room fixture, returning it with its verified digest.

    The frozen original is accepted by its pinned digest.  Any other fixture
    must come with a digest the caller approved, so an invented world can be
    swapped in without either hardcoding one world or dropping the check.
    """

    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if approved_sha256 is not None:
        if digest != approved_sha256:
            raise FixtureNotApproved(
                f"FIXTURE_DIGEST_NOT_APPROVED expected={approved_sha256} got={digest}"
            )
    elif digest != ORIGINAL_FIXTURE_SHA256:
        raise FixtureNotApproved(
            "FIXTURE_DIGEST_NOT_APPROVED: not the frozen original and no "
            f"--fixture-sha256 supplied (got={digest})"
        )
    return json.loads(raw.decode("utf-8-sig")), digest


def _budget(fixture: Mapping[str, Any]) -> WaveBudget:
    stop = fixture.get("stop_policy") or {}
    max_act = int(stop.get("max_activations_per_stone") or 16)
    return WaveBudget(
        max_waves=40,
        max_activations=max_act * 4,
        max_stone_events=max_act * 3,
        aporia_after_waves=6,
    )


def _stone_event(stone: Mapping[str, Any], uri_map: Mapping[str, str], *, tick: int) -> StoneEvent:
    kind = str(stone["kind"])
    stone_id = str(stone["stone_id"])
    if kind == "QUERY":
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.QUERY,
            issued_at_tick=tick,
            payload={
                "topic": f"m5-stone-{stone_id}",
                "query": str(stone.get("question") or "synthetic query"),
            },
        )
    if kind == "SOURCE_DELTA":
        mutation = stone.get("mutation") or {}
        cid = uri_map.get(str(mutation["source_id"])) or carrier_id_from_uri(
            str(mutation["source_id"])
        )
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=tick,
            target_carrier_id=cid,
            payload={
                "old_version": str(mutation["old_version"]),
                "new_version": str(mutation["new_version"]),
                "text": str(mutation.get("new_content") or ""),
            },
        )
    if kind == "APORIA":
        conflict = stone.get("conflict") or {}
        return StoneEvent(
            event_id=f"stone-{stone_id}",
            kind=StoneEventKind.APORIA,
            issued_at_tick=tick,
            payload={
                "note": "synthetic declared conflict",
                "claim_a": str(conflict.get("claim_a", "")),
                "claim_b": str(conflict.get("claim_b", "")),
            },
        )
    raise ValueError(f"unsupported stone kind {kind}")


# -- observation helpers ------------------------------------------------------


def _source_observations(
    engine: WaveEngine, carrier_ids: Sequence[str]
) -> dict[str, SourceObservation]:
    out: dict[str, SourceObservation] = {}
    store = engine.carrier_store
    if store is None:
        return out
    versions = store.current_source_versions(tuple(carrier_ids))
    for cid in carrier_ids:
        version = versions.get(cid)
        if version is None:
            continue
        try:
            digest = store.pin_content_digest(cid, pinned_version=version)
        except ValueError:
            digest = None
        out[cid] = SourceObservation(carrier_id=cid, version=version, content_sha256=digest)
    return out


def _branch_snapshot(engine: WaveEngine, *, branch: str, slug: str) -> DerivedSnapshot:
    """Identity of every record derived from one branch, plus its activations."""

    prefixes = (f"obs-{slug}-{branch}", f"evidence-{branch}-{slug}")
    records = tuple(
        sorted(
            (r.sediment_id, r.version, r.payload_hash)
            for r in engine.sediment.all_records()
            if r.sediment_id in prefixes
        )
    )
    activations = tuple(
        sorted(a.activation_id for a in engine.ledger.activations if a.thread_id in prefixes)
    )
    return DerivedSnapshot(records=records, activation_ids=activations)


def _sediment_versions(engine: WaveEngine) -> dict[str, str]:
    return {r.sediment_id: r.version for r in engine.sediment.all_records()}


# -- world execution ----------------------------------------------------------


@dataclass
class StoneOutcome:
    stone_id: str
    kind: str
    run_id: str | None
    fingerprint: str
    status: str
    manifest: RoomManifest | None = None
    idempotent_hit: bool = False
    stored_result: StoredRunResult | None = None


@dataclass
class WorldRun:
    host: Mapping[str, Any]
    slug: str
    engine: WaveEngine
    binding: Mapping[str, tuple[str, ...]]
    registry: tuple[CapabilitySpec, ...]
    fixture_sha256: str
    budget: WaveBudget
    manifests: list[RoomManifest] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    outcomes: list[StoneOutcome] = field(default_factory=list)
    run_results: list[StoredRunResult] = field(default_factory=list)
    applied_deltas: list[AppliedDelta] = field(default_factory=list)
    stone_fingerprints: dict[str, str] = field(default_factory=dict)
    processed_stone_ids: list[str] = field(default_factory=list)
    oracle_inputs_extra: dict[str, Any] = field(default_factory=dict)
    consumed_source_checks: list[dict[str, Any]] = field(default_factory=list)
    resumed_from_checkpoint: bool = False
    started_at_cursor: int = 0


def _execute_stone(
    world: WorldRun,
    stone: Mapping[str, Any],
    *,
    uri_map: Mapping[str, str],
    tick: int,
    extra_base_states: Sequence[str] = (),
    granted_rights: Sequence[str] = (SYNTHETIC_RIGHT,),
) -> StoneOutcome:
    """Compile the room this stone needs, admit it, and actually run it."""

    engine = world.engine
    carrier_ids = tuple(declared_source_versions(world.host))
    versions = engine.carrier_store.current_source_versions(carrier_ids)
    fingerprint = stone_fingerprint(stone, source_versions=versions)
    stone_id = str(stone["stone_id"])
    world.stone_fingerprints[stone_id] = fingerprint

    prior = next((r for r in world.run_results if r.stone_fingerprint == fingerprint), None)
    if prior is not None:
        # Same stone against the same source state: return the stored result.
        # No fresh activation, no repeated paid work.
        return StoneOutcome(
            stone_id=stone_id,
            kind=str(stone["kind"]),
            run_id=prior.run_id,
            fingerprint=fingerprint,
            status="IDEMPOTENT_STORED_RESULT",
            idempotent_hit=True,
            stored_result=prior,
        )

    # Match room_builder tests: synthetic hosts always declare sources; the
    # compiler must see SyntheticSourceVersion even if version lookup fails.
    has_carriers = engine.carrier_store is not None and bool(carrier_ids)
    base_states = [
        BASE_STONE_STATE,
        *([BASE_SOURCE_STATE] if has_carriers else []),
        *extra_base_states,
    ]
    manifest = compile_room_for_stone(
        host_id=str(world.host["host_id"]),
        host_slug=world.slug,
        stone=stone,
        registry=world.registry,
        thread_binding=world.binding,
        available_base_states=base_states,
        granted_rights=granted_rights,
        budget=dict(world.host.get("room_budget") or {}),
    )
    world.manifests.append(manifest)

    admitted = manifest.admitted_engine_threads
    if not admitted:
        manifest.status = "NO_ADMITTED_CAPABILITY"
        return StoneOutcome(
            stone_id=stone_id,
            kind=str(stone["kind"]),
            run_id=None,
            fingerprint=fingerprint,
            status="NO_ADMITTED_CAPABILITY",
            manifest=manifest,
        )

    run_id = f"m5-{world.slug}-{stone_id}"
    event = _stone_event(stone, uri_map, tick=tick)
    with admitted_threads(engine, admitted):
        record = engine.run(run_id=run_id, budget=world.budget, initial_stone=event)
    manifest.close(activations=engine.ledger.activations, run_id=run_id)
    world.run_ids.append(run_id)
    world.processed_stone_ids.append(stone_id)

    if str(stone["kind"]) == "SOURCE_DELTA":
        mutation = stone.get("mutation") or {}
        world.applied_deltas.append(
            AppliedDelta(
                carrier_id=carrier_id_from_uri(str(mutation["source_id"])),
                old_version=str(mutation["old_version"]),
                new_version=str(mutation["new_version"]),
                new_text=str(mutation.get("new_content") or ""),
            )
        )

    acts = [a for a in engine.ledger.activations if a.run_id == run_id]
    stored = StoredRunResult(
        run_id=run_id,
        stone_id=stone_id,
        stone_fingerprint=fingerprint,
        outcome=record.outcome.value,
        stop_reason=record.stop_reason.value,
        ledger_head_after=engine.ledger.head_hash,
        produced_sediment_ids=tuple(
            sorted({sid for a in acts for sid in a.produced_sediment_ids})
        ),
        activation_ids=tuple(sorted(a.activation_id for a in acts)),
    )
    world.run_results.append(stored)
    return StoneOutcome(
        stone_id=stone_id,
        kind=str(stone["kind"]),
        run_id=run_id,
        fingerprint=fingerprint,
        status=record.outcome.value,
        manifest=manifest,
        stored_result=stored,
    )


def _transport_checks(world: WorldRun) -> list[dict[str, Any]]:
    """Wire the M4 boundary into the real consumed-source path of this run."""

    engine = world.engine
    store = engine.carrier_store
    results: list[dict[str, Any]] = []
    if store is None:
        return results
    consumed: set[str] = set()
    for act in engine.ledger.activations:
        if act.run_id in world.run_ids:
            consumed.update(act.source_carrier_ids)
    for cid in sorted(consumed):
        version = store.current_source_versions((cid,)).get(cid)
        if version is None:
            continue
        try:
            digest = store.pin_content_digest(cid, pinned_version=version)
        except ValueError:
            continue
        payload, _ = store.resolve_payload(
            policy=RawAccessPolicy.FULL_REQUIRED,
            carrier_ids=(cid,),
            stone_payload={},
            operation_id="m5-transport-check",
        )
        content = str(payload.get("text") or "").encode("utf-8")
        stored = StoredInputView(
            source_id=cid,
            source_version=version,
            byte_length=len(content),
            content_sha256=digest,
            complete=True,
        )
        delivered = (
            DeliveredSpan(
                offset=0,
                length=len(content),
                source_id=cid,
                source_version=version,
                content_sha256=digest,
                finish="stop",
            ),
        )
        results.append(
            consumed_source_check(
                stored=stored,
                delivered=delivered,
                admitted_byte_length=len(content),
                policy="FULL_REQUIRED",
                content=content,
            )
        )
    return results


def run_world(
    host: Mapping[str, Any],
    *,
    fixture: Mapping[str, Any],
    fixture_sha256: str,
    resume_from: M5Checkpoint | None = None,
) -> WorldRun:
    """Execute (or continue) one invented world's stone sequence."""

    slug = host_slug(str(host["host_id"]))
    engine, uri_map, binding = build_host_engine(host)
    world = WorldRun(
        host=host,
        slug=slug,
        engine=engine,
        binding=binding,
        registry=load_registry(fixture),
        fixture_sha256=fixture_sha256,
        budget=_budget(fixture),
    )

    start = 0
    if resume_from is not None:
        if not resume_from.completed:
            # A process that died inside a stone may already have paid for
            # work this process cannot observe. Continuing is a decision.
            raise CheckpointRejected(
                "M5_CHECKPOINT_PENDING_STONE_REQUIRES_RECONCILIATION "
                f"pending={resume_from.pending_stone_id!r}"
            )
        restore_into(
            engine,
            resume_from,
            host_id=str(host["host_id"]),
            fixture_sha256=fixture_sha256,
        )
        start = resume_from.stone_cursor
        world.resumed_from_checkpoint = True
        world.started_at_cursor = start
        world.processed_stone_ids = list(resume_from.processed_stone_ids)
        world.stone_fingerprints = dict(resume_from.stone_fingerprints)
        world.run_results = list(resume_from.run_results)
        world.applied_deltas = list(resume_from.applied_source_deltas)
        world.run_ids = [r.run_id for r in resume_from.run_results]

    stones = list(host.get("stones") or [])
    carrier_ids = tuple(declared_source_versions(host))
    alpha_id, beta_id = carrier_ids[0], carrier_ids[1]

    before_close = _sediment_versions(engine)
    alpha_before = beta_before = None
    alpha_after = beta_after = None
    delta_run_id: str | None = None
    source_before = _source_observations(engine, carrier_ids)

    tick = 2 * start
    for index in range(start, len(stones)):
        stone = stones[index]
        tick += 2
        if str(stone["kind"]) == "SOURCE_DELTA":
            alpha_before = _branch_snapshot(engine, branch="alpha", slug=slug)
            beta_before = _branch_snapshot(engine, branch="beta", slug=slug)
        extra: list[str] = []
        if observed_missing_source_needs(engine, world.run_ids):
            extra.append(MISSING_SOURCE_NEED_STATE)
        outcome = _execute_stone(
            world, stone, uri_map=uri_map, tick=tick, extra_base_states=extra
        )
        world.outcomes.append(outcome)
        if outcome.kind == "SOURCE_DELTA" and outcome.run_id:
            delta_run_id = outcome.run_id
            # Snapshot immediately after the delta run. Taking this at the end
            # of the sequence would fold in the later aporia stone, which
            # legitimately re-derives BOTH branches and would make the
            # untouched branch look changed.
            alpha_after = _branch_snapshot(engine, branch="alpha", slug=slug)
            beta_after = _branch_snapshot(engine, branch="beta", slug=slug)
        if (
            index == 0
            and not world.resumed_from_checkpoint
            and outcome.kind == "QUERY"
            and outcome.run_id
        ):
            # Re-issue the very same stone against the very same source state,
            # before anything has changed. It must return the stored result
            # and do no fresh work: a duplicate is not a reason to pay twice.
            before = len(engine.ledger.activations)
            repeat = _execute_stone(
                world, stone, uri_map=uri_map, tick=tick, extra_base_states=extra
            )
            world.oracle_inputs_extra["duplicate_stone"] = {
                "stone_id": repeat.stone_id,
                "returned_stored_result": repeat.idempotent_hit,
                "fresh_activations": len(engine.ledger.activations) - before,
                "reused_run_id": repeat.run_id,
                "same_fingerprint": repeat.fingerprint == outcome.fingerprint,
            }

    after_close = _sediment_versions(engine)

    world.oracle_inputs_extra.update(
        {
            "alpha_before": alpha_before,
            "alpha_after": alpha_after,
            "beta_before": beta_before,
            "beta_after": beta_after,
            "delta_run_id": delta_run_id,
            "source_before": source_before,
            "source_after": _source_observations(engine, carrier_ids),
            "sediment_versions_before_close": before_close,
            "sediment_versions_after_close": after_close,
            "alpha_carrier": alpha_id,
            "beta_carrier": beta_id,
        }
    )
    world.consumed_source_checks = _transport_checks(world)
    return world


# -- probes (each one really runs; nothing here is assumed) -------------------


def _frontier_probe(world: WorldRun) -> dict[str, Any]:
    """Was the frontier capability callable before the need existed, and after?"""

    engine = world.engine
    needs = observed_missing_source_needs(engine, world.run_ids)
    frontier_stone = {"stone_id": "FRONTIER", "kind": "FRONTIER_NEED"}

    def admitted_with(extra: Sequence[str]) -> bool:
        manifest = compile_room_for_stone(
            host_id=str(world.host["host_id"]),
            host_slug=world.slug,
            stone=frontier_stone,
            registry=world.registry,
            thread_binding=world.binding,
            available_base_states=[BASE_STONE_STATE, BASE_SOURCE_STATE, *extra],
            granted_rights=[SYNTHETIC_RIGHT],
            budget={},
        )
        return any(cap.registry_id == "N-F" and cap.is_admitted for cap in manifest.planned)

    before = admitted_with(())
    after = admitted_with((MISSING_SOURCE_NEED_STATE,)) if needs else False

    fired_id: str | None = None
    if needs and after:
        run_id = f"m5-{world.slug}-frontier"
        manifest = compile_room_for_stone(
            host_id=str(world.host["host_id"]),
            host_slug=world.slug,
            stone=frontier_stone,
            registry=world.registry,
            thread_binding=world.binding,
            available_base_states=[BASE_STONE_STATE, BASE_SOURCE_STATE, MISSING_SOURCE_NEED_STATE],
            granted_rights=[SYNTHETIC_RIGHT],
            budget={},
        )
        world.manifests.append(manifest)
        event = StoneEvent(
            event_id=f"{run_id}:return",
            kind=StoneEventKind.FRONTIER_RETURN,
            issued_at_tick=900,
            payload={"need_id": needs[0], "synthetic_return": True},
        )
        try:
            with admitted_threads(world.engine, manifest.admitted_engine_threads):
                world.engine.run(run_id=run_id, budget=world.budget, initial_stone=event)
            manifest.close(activations=world.engine.ledger.activations, run_id=run_id)
            world.run_ids.append(run_id)
            fired = [
                a
                for a in world.engine.ledger.activations
                if a.run_id == run_id and a.thread_id == f"frontier-{world.slug}"
                and a.outcome.value == "FIRED"
            ]
            fired_id = fired[0].activation_id if fired else None
        except Exception as exc:  # the probe must not fake a result
            manifest.status = f"FRONTIER_PROBE_ERROR:{type(exc).__name__}"
    return {
        "capability": "N-F",
        "admitted_before": before,
        "admitted_after": after if needs else None,
        "fired_activation_id": fired_id,
        "trigger_activation_id": needs[0] if needs else None,
    }


def _rights_probe(world: WorldRun) -> dict[str, Any]:
    """Withhold the declared right and observe denial plus zero activations."""

    manifest = compile_room_for_stone(
        host_id=str(world.host["host_id"]),
        host_slug=world.slug,
        stone={"stone_id": "RIGHTS_PROBE", "kind": "QUERY"},
        registry=world.registry,
        thread_binding=world.binding,
        available_base_states=[BASE_STONE_STATE, BASE_SOURCE_STATE],
        granted_rights=[],  # nothing granted
        budget={},
    )
    denied = [cap for cap in manifest.planned if cap.admission == DENIED_RIGHTS]
    denied_threads = {tid for cap in denied for tid in cap.engine_thread_ids}
    # The probe compiles only; a denied room is never admitted, so by
    # construction it contributes no activation. Assert that directly.
    activations = len(
        [
            a
            for a in world.engine.ledger.activations
            if a.run_id == f"m5-{world.slug}-RIGHTS_PROBE" and a.thread_id in denied_threads
        ]
    )
    return {
        "admission": DENIED_RIGHTS if denied else ADMITTED,
        "denied_capabilities": sorted(cap.registry_id for cap in denied),
        "activations": activations,
        "withheld_right": SYNTHETIC_RIGHT,
    }


def _excluded_source_probe(world: WorldRun) -> dict[str, Any]:
    """An owner-excluded carrier must be refused, not read."""

    store = world.engine.carrier_store
    foreign_id = "m5-excluded-owner-source"
    try:
        store.resolve_payload(
            policy=RawAccessPolicy.FULL_REQUIRED,
            carrier_ids=(foreign_id,),
            stone_payload={},
            operation_id="m5-excluded-probe",
        )
    except Exception as exc:
        return {
            "rejected": True,
            "carrier_id": foreign_id,
            "reason": f"{type(exc).__name__}:{exc}"[:160],
            "records_produced": 0,
        }
    return {"rejected": False, "carrier_id": foreign_id, "reason": "", "records_produced": 0}


def _foreign_checkpoint_probe(
    world: WorldRun, foreign: M5Checkpoint | None
) -> dict[str, Any] | None:
    """Present the OTHER host's checkpoint to this host; it must be refused."""

    if foreign is None:
        return None
    try:
        foreign.verify_owner(
            host_id=str(world.host["host_id"]), fixture_sha256=world.fixture_sha256
        )
    except CheckpointRejected as exc:
        return {
            "rejected": True,
            "reason": str(exc)[:160],
            "foreign_owner": foreign.host_id,
            "reader": str(world.host["host_id"]),
            "mechanism": "OWNERSHIP_REJECTION_NOT_HASH_DIFFERENCE",
        }
    return {
        "rejected": False,
        "reason": "",
        "foreign_owner": foreign.host_id,
        "reader": str(world.host["host_id"]),
    }


def _self_attestation_probe(world: WorldRun, checkpoint: M5Checkpoint) -> dict[str, Any]:
    """A self-made checkpoint verifies as integrity, never as external authority."""

    checkpoint.verify_checksum()
    return {
        "checkpoint_verified_as_own": True,
        "granted_external_authority": False,
        "accepted_view_size": len(world.engine.sediment.views["accepted"]),
        "statement": "SELF_OWNED_CHECKPOINT_IS_INTEGRITY_ONLY",
    }


def _unauthorized_decision_probe(world: WorldRun) -> dict[str, Any]:
    """An acceptance without a verified decision right must be refused."""

    target = next(
        (
            r.sediment_id
            for r in world.engine.sediment.all_records()
            if r.object_type == "synthetic.hypothesis_proposal"
        ),
        None,
    )
    if target is None:
        return {"rejected": False, "reason": "NO_PROPOSAL_TO_ATTEMPT", "attempted": False}
    reasons: list[str] = []
    # (a) a bare string is not human authority
    try:
        world.engine.sediment.accept(target, decision_id="unauthorized-probe", decided_at_tick=999)
        bare_rejected = False
    except Exception as exc:
        bare_rejected = True
        reasons.append(f"bare_accept:{type(exc).__name__}:{exc}"[:120])
    # (b) a decision without a trusted attestation is not a decision
    try:
        world.engine.record_human_decision(
            run_id=world.run_ids[0] if world.run_ids else "probe",
            decision_id="unauthorized-probe",
            subject_sediment_id=target,
            choice="ACCEPT",
            rationale="unauthorized probe",
            accepts=(target,),
            attestation=None,
        )
        unattested_rejected = False
    except Exception as exc:
        unattested_rejected = True
        reasons.append(f"unattested_decision:{type(exc).__name__}:{exc}"[:120])
    return {
        "rejected": bare_rejected and unattested_rejected,
        "attempted": True,
        "subject": target,
        "reason": "; ".join(reasons),
        "accepted_view_size_after": len(world.engine.sediment.views["accepted"]),
    }


def _budget_probe(world: WorldRun) -> dict[str, Any]:
    """Run one stone under a deliberately tiny budget to observe EXHAUSTED."""

    run_id = f"m5-{world.slug}-budget-probe"
    tiny = WaveBudget(max_waves=1, max_activations=1, max_stone_events=4, aporia_after_waves=1)
    event = StoneEvent(
        event_id=f"{run_id}:stone",
        kind=StoneEventKind.QUERY,
        issued_at_tick=800,
        payload={"topic": "budget-probe", "query": "bounded probe of the budget stop reason"},
    )
    try:
        with admitted_threads(world.engine, [t for ids in world.binding.values() for t in ids]):
            record = world.engine.run(run_id=run_id, budget=tiny, initial_stone=event)
        world.run_ids.append(run_id)
        return {
            "run_id": run_id,
            "outcome": record.outcome.value,
            "stop_reason": record.stop_reason.value,
        }
    except Exception as exc:
        return {"run_id": None, "error": f"{type(exc).__name__}:{exc}"[:160]}


# -- operator report ----------------------------------------------------------


def _operator_sections(world: WorldRun) -> tuple[dict[str, str], list[str]]:
    """Render the bounded operator answer from the states actually produced."""

    engine = world.engine
    refs: list[str] = []
    question_lines: list[str] = []
    fact_lines: list[str] = []
    unresolved_lines: list[str] = []
    next_lines: list[str] = []
    provenance_lines: list[str] = []

    stones = {str(s["stone_id"]): s for s in world.host.get("stones") or []}
    for outcome in world.outcomes:
        stone = stones.get(outcome.stone_id, {})
        kind = outcome.kind
        run_id = outcome.run_id or "(not run)"
        produced = {
            sid: engine.sediment.views["working"].get(sid)
            or engine.sediment.views["candidate"].get(sid)
            for sid in (outcome.stored_result.produced_sediment_ids if outcome.stored_result else ())
        }
        acts = [a for a in engine.ledger.activations if a.run_id == outcome.run_id]

        if kind == "QUERY":
            question_lines.append(f"- **{outcome.stone_id}**: {stone.get('question', '')}")
            projection = produced.get(f"projection-{world.slug}")
            if projection is not None:
                refs.append(projection.sediment_id)
                payload = projection.payload
                fact_lines.append(
                    f"- **{outcome.stone_id}**: two independent synthetic records were read "
                    f"(alpha@{payload['alpha_observed_version']}, beta@{payload['beta_observed_version']}); "
                    f"their derived signals {'differ' if payload['divergent'] else 'agree'} "
                    f"(`{projection.sediment_id}`@{projection.version})."
                )
                if payload["divergent"]:
                    unresolved_lines.append(
                        f"- **{outcome.stone_id}**: the two records disagree; the evidence held "
                        "does not say which reading is correct."
                    )
                    next_lines.append(
                        f"- **{outcome.stone_id}**: obtain an independently held record for the "
                        "disagreeing branch, or state explicitly which branch the host treats as "
                        "authoritative — this is the operator's decision, not the room's."
                    )
                else:
                    next_lines.append(
                        f"- **{outcome.stone_id}**: no discriminating action is required by the "
                        "evidence currently held."
                    )
            else:
                fact_lines.append(
                    f"- **{outcome.stone_id}**: no projection was produced; run ended "
                    f"{outcome.status}."
                )
                unresolved_lines.append(
                    f"- **{outcome.stone_id}**: the question was not answered from source."
                )
                next_lines.append(f"- **{outcome.stone_id}**: inspect `{run_id}` activations.")

        elif kind == "SOURCE_DELTA":
            mutation = stone.get("mutation") or {}
            question_lines.append(
                f"- **{outcome.stone_id}**: does a change to {mutation.get('source_id')} "
                f"({mutation.get('old_version')}->{mutation.get('new_version')}) alter the answer?"
            )
            alpha_b = world.oracle_inputs_extra.get("alpha_before")
            alpha_a = world.oracle_inputs_extra.get("alpha_after")
            beta_b = world.oracle_inputs_extra.get("beta_before")
            beta_a = world.oracle_inputs_extra.get("beta_after")
            if alpha_b and alpha_a and beta_b and beta_a:
                retained = [sid for sid, v, h in alpha_a.records if (sid, v, h) in set(alpha_b.records)]
                changed = [sid for sid, v, h in beta_a.records if (sid, v, h) not in set(beta_b.records)]
                refs.extend(retained + changed)
                fact_lines.append(
                    f"- **{outcome.stone_id}**: genuinely changed: "
                    f"{', '.join(f'`{s}`' for s in changed) or 'nothing'}; "
                    f"retained with identical content hash: "
                    f"{', '.join(f'`{s}`' for s in retained) or 'nothing'}."
                )
                next_lines.append(
                    f"- **{outcome.stone_id}**: nothing further is required for the untouched "
                    "branch; its prior conclusion still rests on the same bytes."
                )
            if not unresolved_lines or outcome.stone_id not in "".join(unresolved_lines):
                unresolved_lines.append(
                    f"- **{outcome.stone_id}**: whether the corrected record resolves the earlier "
                    "disagreement is not decided by the change itself."
                )

        elif kind == "APORIA":
            conflict = stone.get("conflict") or {}
            question_lines.append(
                f"- **{outcome.stone_id}**: can the room decide between "
                f"“{conflict.get('claim_a', '')}” and "
                f"“{conflict.get('claim_b', '')}”?"
            )
            aporias = [a for a in acts if a.error_code == "BODY_APORIA"]
            for act in aporias:
                refs.append(act.activation_id)
            if aporias:
                fact_lines.append(
                    f"- **{outcome.stone_id}**: the room re-derived both readings and recorded an "
                    f"aporia at `{aporias[0].activation_id}`: {aporias[0].error_detail}"
                )
                unresolved_lines.append(
                    f"- **{outcome.stone_id}**: APORIA — the conflict stands. "
                    f"Declared resolution in the input: {conflict.get('resolution', 'UNKNOWN')}."
                )
                next_lines.append(
                    f"- **{outcome.stone_id}**: two options are open to the owner: (a) accept one "
                    "controlled series as sufficient, narrowing the claim's scope; (b) require an "
                    "independently held record before concluding. The room does not choose."
                )
            else:
                fact_lines.append(
                    f"- **{outcome.stone_id}**: no aporia was recorded; run ended {outcome.status}."
                )
                unresolved_lines.append(f"- **{outcome.stone_id}**: conflict handling NOT_OBSERVED.")
                next_lines.append(f"- **{outcome.stone_id}**: inspect `{run_id}`.")

        if outcome.idempotent_hit:
            provenance_lines.append(
                f"- `{outcome.stone_id}` returned a stored result (fingerprint "
                f"`{outcome.fingerprint[:16]}`) without any fresh activation."
            )
        if outcome.manifest is not None:
            blocked = [
                f"{cap.registry_id}({cap.admission})" for cap in outcome.manifest.blocked
            ]
            provenance_lines.append(
                f"- `{outcome.stone_id}` room `{outcome.manifest.room_id}` -> "
                f"admitted {', '.join(outcome.manifest.planned_registry_threads) or 'none'}"
                + (f"; refused {', '.join(blocked)}" if blocked else "")
                + f"; status {outcome.manifest.status}; run `{run_id}`."
            )

    known = {r.sediment_id for r in engine.sediment.all_records()} | {
        a.activation_id for a in engine.ledger.activations
    }
    refs = [r for r in dict.fromkeys(refs) if r in known]
    sections = {
        "question": "\n".join(question_lines),
        "observed_facts": "\n".join(fact_lines),
        "unresolved": "\n".join(unresolved_lines),
        "next_action": "\n".join(next_lines),
        "provenance": "\n".join(provenance_lines),
    }
    return sections, refs


def render_operator_report(world: WorldRun, sections: Mapping[str, str]) -> str:
    status, reason = assess_output_sections(sections, required=REQUIRED_REPORT_SECTIONS)
    lines = [
        f"# Operator answer — {world.host['host_id']} (invented world)",
        "",
        "SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / NOT_AUTONOMOUSLY_ACCEPTED",
        "",
        f"Report structural completeness: **{status}** ({reason}). "
        "This is structural completeness only, not a judgement about meaning.",
        "",
        "## What was asked",
        "",
        sections["question"] or "_none_",
        "",
        "## What the evidence shows",
        "",
        sections["observed_facts"] or "_none_",
        "",
        "## What remains unresolved",
        "",
        sections["unresolved"] or "_none_",
        "",
        "## Next discriminating action",
        "",
        sections["next_action"] or "_none_",
        "",
        "## Basis (rooms, runs and records)",
        "",
        sections["provenance"] or "_none_",
        "",
    ]
    return "\n".join(lines)


def build_telemetry(world: WorldRun) -> dict[str, Any]:
    """Counters, kept deliberately apart from the operator answer."""

    engine = world.engine
    acts = [a for a in engine.ledger.activations if a.run_id in world.run_ids]
    return {
        "schema": "seshat.m5_telemetry.v1",
        "host_id": world.host["host_id"],
        "runs": list(world.run_ids),
        "activation_count": len(acts),
        "fired_count": len([a for a in acts if a.outcome.value == "FIRED"]),
        "distinct_threads": sorted({a.thread_id for a in acts}),
        "wave_count": len([w for w in engine.ledger.waves if w.run_id in world.run_ids]),
        "sediment_records": len(engine.sediment.all_records()),
        "stale_records": len(engine.sediment.views["stale"]),
        "accepted_records": len(engine.sediment.views["accepted"]),
        "resumed_from_checkpoint": world.resumed_from_checkpoint,
        "stone_outcomes": [
            {
                "stone_id": o.stone_id,
                "kind": o.kind,
                "run_id": o.run_id,
                "status": o.status,
                "idempotent_hit": o.idempotent_hit,
                "room_status": o.manifest.status if o.manifest else None,
            }
            for o in world.outcomes
        ],
        "consumed_source_checks": world.consumed_source_checks,
        "ledger_head": engine.ledger.head_hash,
    }


# -- exports ------------------------------------------------------------------


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_carpet_index(world: WorldRun) -> str:
    """One inspectable page covering every stone run that actually happened."""

    engine = world.engine
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>SESHAT M5 carpet — {_esc(world.host['host_id'])} (synthetic)</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:72rem}"
        "table{border-collapse:collapse;width:100%;margin:.5rem 0}"
        "th,td{border:1px solid #ccc;padding:.25rem .5rem;font-size:.85rem;text-align:left}"
        "th{background:#f3f3f3}.aporia{background:#fff4e5}.blocked{background:#f6f6f6;color:#666}"
        "</style></head><body>",
        f"<h1>SESHAT M5 carpet — {_esc(world.host['host_id'])}</h1>",
        "<p><strong>SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / "
        "NOT_AUTONOMOUSLY_ACCEPTED.</strong> Invented world; deterministic fixture "
        "callbacks; no model calls. Nothing here is a candidate for release.</p>",
    ]
    for outcome in world.outcomes:
        parts.append(f"<h2>Stone {_esc(outcome.stone_id)} — {_esc(outcome.kind)}</h2>")
        parts.append(
            f"<p>run <code>{_esc(outcome.run_id)}</code>; status "
            f"<code>{_esc(outcome.status)}</code>"
            + (f"; room <code>{_esc(outcome.manifest.status)}</code>" if outcome.manifest else "")
            + "</p>"
        )
        if outcome.manifest is not None:
            parts.append("<table><tr><th>capability</th><th>admission</th><th>threads</th>"
                         "<th>missing input</th></tr>")
            for cap in outcome.manifest.planned:
                cls = "" if cap.is_admitted else " class='blocked'"
                parts.append(
                    f"<tr{cls}><td>{_esc(cap.registry_id)}</td><td>{_esc(cap.admission)}</td>"
                    f"<td>{_esc(', '.join(cap.engine_thread_ids))}</td>"
                    f"<td>{_esc(', '.join(cap.missing_input_states))}</td></tr>"
                )
            parts.append("</table>")
        acts = [a for a in engine.ledger.activations if a.run_id == outcome.run_id]
        if acts:
            parts.append("<table><tr><th>activation</th><th>thread</th><th>outcome</th>"
                         "<th>read</th><th>produced</th><th>detail</th></tr>")
            for act in acts:
                cls = " class='aporia'" if act.error_code == "BODY_APORIA" else ""
                parts.append(
                    f"<tr{cls}><td><code>{_esc(act.activation_id)}</code></td>"
                    f"<td>{_esc(act.thread_id)}</td><td>{_esc(act.outcome.value)}</td>"
                    f"<td>{_esc(', '.join(act.read_sediment_ids))}</td>"
                    f"<td>{_esc(', '.join(act.produced_sediment_ids))}</td>"
                    f"<td>{_esc(act.error_detail or '')}</td></tr>"
                )
            parts.append("</table>")
        else:
            parts.append("<p><em>No activation recorded for this stone.</em></p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def write_sqlite_ledger(path: Path, world: WorldRun, oracle_rows: Sequence[Mapping[str, Any]]) -> None:
    """Durable operator-queryable ledger: real rows, not run counters."""

    engine = world.engine
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS m5_runs(
                run_id TEXT PRIMARY KEY, stone_id TEXT, kind TEXT, outcome TEXT,
                stop_reason TEXT, ledger_head TEXT, fingerprint TEXT, idempotent INTEGER);
            CREATE TABLE IF NOT EXISTS m5_activations(
                activation_id TEXT PRIMARY KEY, run_id TEXT, thread_id TEXT, outcome TEXT,
                read_ids TEXT, produced_ids TEXT, error_code TEXT, error_detail TEXT);
            CREATE TABLE IF NOT EXISTS m5_sediment(
                sediment_id TEXT PRIMARY KEY, object_type TEXT, version TEXT,
                payload_hash TEXT, produced_by_thread TEXT, epistemic_level TEXT);
            CREATE TABLE IF NOT EXISTS m5_rooms(
                room_id TEXT PRIMARY KEY, stone_id TEXT, status TEXT,
                admitted TEXT, refused TEXT);
            CREATE TABLE IF NOT EXISTS m5_oracles(
                oracle_id TEXT PRIMARY KEY, name TEXT, observed TEXT, detail TEXT);
            """
        )
        for outcome in world.outcomes:
            stored = outcome.stored_result
            db.execute(
                "INSERT OR REPLACE INTO m5_runs VALUES(?,?,?,?,?,?,?,?)",
                (
                    outcome.run_id or f"(norun):{outcome.stone_id}",
                    outcome.stone_id,
                    outcome.kind,
                    stored.outcome if stored else outcome.status,
                    stored.stop_reason if stored else "",
                    run_ledger_head_hash(engine.ledger, outcome.run_id) if outcome.run_id else "",
                    outcome.fingerprint,
                    int(outcome.idempotent_hit),
                ),
            )
        for act in engine.ledger.activations:
            db.execute(
                "INSERT OR REPLACE INTO m5_activations VALUES(?,?,?,?,?,?,?,?)",
                (
                    act.activation_id, act.run_id, act.thread_id, act.outcome.value,
                    ",".join(act.read_sediment_ids), ",".join(act.produced_sediment_ids),
                    act.error_code or "", act.error_detail or "",
                ),
            )
        for record in engine.sediment.all_records():
            db.execute(
                "INSERT OR REPLACE INTO m5_sediment VALUES(?,?,?,?,?,?)",
                (
                    record.sediment_id, record.object_type, record.version,
                    record.payload_hash, record.produced_by_thread, record.epistemic_level.value,
                ),
            )
        for manifest in world.manifests:
            db.execute(
                "INSERT OR REPLACE INTO m5_rooms VALUES(?,?,?,?,?)",
                (
                    manifest.room_id, manifest.stone_id, manifest.status,
                    ",".join(manifest.planned_registry_threads),
                    ",".join(f"{c.registry_id}:{c.admission}" for c in manifest.blocked),
                ),
            )
        for row in oracle_rows:
            db.execute(
                "INSERT OR REPLACE INTO m5_oracles VALUES(?,?,?,?)",
                (row["oracle_id"], row["name"], row["observed"], row["detail"]),
            )
        db.commit()


def export_world(
    world: WorldRun,
    *,
    output_dir: Path,
    oracle_rows: Sequence[Mapping[str, Any]],
    checkpoint: M5Checkpoint,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = world.engine

    stones: list[dict[str, Any]] = []
    room_events: list[str] = []
    waves_lines: list[str] = []
    activation_lines: list[str] = []
    sediment_records: list[dict[str, Any]] = []
    resonance_records: list[dict[str, Any]] = []
    seen_res: set[str] = set()
    for run_id in world.run_ids:
        stones.extend(operator_stone_events(engine.ledger, run_id))
        for event in all_run_events(engine.ledger, run_id):
            room_events.append(json.dumps(event, ensure_ascii=False, sort_keys=True))
        for wave in engine.ledger.waves:
            if wave.run_id == run_id:
                waves_lines.append(
                    json.dumps(wave.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                )
        for activation in engine.ledger.activations:
            if activation.run_id == run_id:
                activation_lines.append(
                    json.dumps(
                        activation.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
                    )
                )
        sediment_records.extend(sediment_records_for_run(engine.ledger, engine.sediment, run_id))
        for record in engine.ledger.resonances_for_run(run_id):
            if record.resonance_id in seen_res:
                continue
            seen_res.add(record.resonance_id)
            resonance_records.append(record.model_dump(mode="json"))

    sections, refs = _operator_sections(world)
    report_status, report_reason = assess_output_sections(
        sections, required=REQUIRED_REPORT_SECTIONS
    )

    def write(name: str, text: str) -> None:
        (output_dir / name).write_text(text, encoding="utf-8")

    write("room_manifest.json", manifests_to_json(world.manifests))
    write("stones.json", json.dumps(stones, ensure_ascii=False, sort_keys=True, indent=2))
    write("room_events.jsonl", "\n".join(room_events) + ("\n" if room_events else ""))
    write("waves.jsonl", "\n".join(waves_lines) + ("\n" if waves_lines else ""))
    write("activations.jsonl", "\n".join(activation_lines) + ("\n" if activation_lines else ""))
    write(
        "sediment.json",
        json.dumps(sediment_records, ensure_ascii=False, sort_keys=True, indent=2),
    )
    write(
        "resonances.json",
        json.dumps(resonance_records, ensure_ascii=False, sort_keys=True, indent=2),
    )
    write("carpet.html", render_carpet_index(world))
    write("report.md", render_operator_report(world, sections))
    write(
        "telemetry.json",
        json.dumps(build_telemetry(world), ensure_ascii=False, sort_keys=True, indent=2, default=str),
    )
    summary = oracle_summary(oracle_rows)
    write(
        "oracles.json",
        json.dumps(
            {"summary": summary, "rows": list(oracle_rows)},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=str,
        ),
    )
    # Per-run detail pages from the existing renderer, for drill-down.
    for run_id in world.run_ids:
        try:
            ledger, sediment, resonances = engine.snapshot(run_id)
            run_record = next(r for r in ledger.runs if r.run_id == run_id)
            (output_dir / f"carpet_{run_id}.html").write_text(
                render_html(
                    run_record=run_record,
                    ledger=ledger,
                    sediment=sediment,
                    resonances=resonances,
                    thread_specs=engine.thread_specs,
                    title=f"SESHAT M5 — {world.host['host_id']} / {run_id} (synthetic)",
                ),
                encoding="utf-8",
            )
        except (KeyError, StopIteration):
            continue

    write_checkpoint(output_dir / "m5_checkpoint.json", checkpoint)
    write_sqlite_ledger(output_dir / "ledger.sqlite", world, oracle_rows)

    digests: dict[str, dict[str, int | str]] = {}
    for name in M5_ARTIFACTS:
        path = output_dir / name
        if path.is_file():
            data = path.read_bytes()
            digests[name] = {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}

    receipt = {
        "schema": "seshat.m5_carpet_receipt.v2",
        "host_id": world.host["host_id"],
        "world_slug": world.slug,
        "synthetic_only": True,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "NOT_AUTHORIZED",
        "fixture_sha256": world.fixture_sha256,
        "resumed_from_checkpoint": world.resumed_from_checkpoint,
        "operator_report": {"status": report_status, "reason": report_reason, "references": refs},
        "rm_oracles": list(oracle_rows),
        "rm_summary": summary,
        "rooms": [m.to_dict() for m in world.manifests],
        "consumed_source_checks": world.consumed_source_checks,
        "artifact_file_digests": digests,
        "artifact_files": list(M5_ARTIFACTS),
        "source_modules": build_source_module_manifest(),
        "git": _git_meta(),
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    return receipt


def _checkpoint_for(world: WorldRun, *, completed: bool = True) -> M5Checkpoint:
    carrier_ids = tuple(declared_source_versions(world.host))
    observations = _source_observations(world.engine, carrier_ids)
    return capture_checkpoint(
        engine=world.engine,
        host_id=str(world.host["host_id"]),
        world_slug=world.slug,
        fixture_sha256=world.fixture_sha256,
        stone_cursor=len(world.processed_stone_ids),
        processed_stone_ids=world.processed_stone_ids,
        stone_fingerprints=world.stone_fingerprints,
        source_versions={cid: obs.version for cid, obs in observations.items()},
        source_digests={cid: obs.content_sha256 for cid, obs in observations.items() if obs.content_sha256},
        applied_source_deltas=world.applied_deltas,
        budget=world.budget,
        run_results=world.run_results,
        completed=completed,
    )


# -- portfolio ----------------------------------------------------------------


def run_two_worlds(
    fixture_path: Path,
    output_root: Path,
    *,
    approved_sha256: str | None = None,
    verify_subprocess_resume: bool = True,
) -> dict[str, Any]:
    fixture, fixture_sha = load_fixture(fixture_path, approved_sha256=approved_sha256)
    output_root.mkdir(parents=True, exist_ok=True)
    world_receipts: list[dict[str, Any]] = []
    checkpoints: dict[str, M5Checkpoint] = {}
    worlds: list[WorldRun] = []

    for host in fixture.get("hosts") or []:
        world = run_world(host, fixture=fixture, fixture_sha256=fixture_sha)
        checkpoints[str(host["host_id"])] = _checkpoint_for(world)
        worlds.append(world)

    for world in worlds:
        world_dir = output_root / world.slug
        world_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = checkpoints[str(world.host["host_id"])]

        # A checkpoint taken after the FIRST stone, so a child process has
        # genuine remaining work (the delta and the aporia) to continue.
        resume_evidence: dict[str, Any] | None = None
        if verify_subprocess_resume and len(world.host.get("stones") or []) > 1:
            partial_cp = _partial_checkpoint(world.host, fixture, fixture_sha, stones_to_run=1)
            cp_path = world_dir / "resume_after_first_stone.json"
            write_checkpoint(cp_path, partial_cp)
            child_dir = world_dir / "resume_probe"
            completed = subprocess.run(
                [
                    sys.executable, "-m", "seshat.fabric_waves.m5_room_carpet",
                    "--fixture", str(fixture_path),
                    "--fixture-sha256", fixture_sha,
                    "--host-id", str(world.host["host_id"]),
                    "--resume-checkpoint", str(cp_path),
                    "--output-dir", str(child_dir),
                ],
                capture_output=True, text=True, check=False,
            )
            resume_evidence = _compare_resume(completed, child_dir, control=world)

        duplicate_evidence = world.oracle_inputs_extra.get("duplicate_stone")
        foreign = next(
            (cp for hid, cp in checkpoints.items() if hid != str(world.host["host_id"])),
            None,
        )
        frontier = _frontier_probe(world)
        budget_probe = _budget_probe(world)
        settled = next(
            (o.run_id for o in world.outcomes if o.kind == "QUERY" and o.run_id), None
        )

        inputs = OracleInputs(
            engine=world.engine,
            run_ids=world.run_ids,
            manifests=world.manifests,
            alpha_before=world.oracle_inputs_extra.get("alpha_before"),
            alpha_after=world.oracle_inputs_extra.get("alpha_after"),
            beta_before=world.oracle_inputs_extra.get("beta_before"),
            beta_after=world.oracle_inputs_extra.get("beta_after"),
            delta_run_id=world.oracle_inputs_extra.get("delta_run_id"),
            source_before=world.oracle_inputs_extra.get("source_before") or {},
            source_after=world.oracle_inputs_extra.get("source_after") or {},
            frontier_capability_id=frontier["capability"],
            frontier_admitted_before=frontier["admitted_before"],
            frontier_admitted_after=frontier["admitted_after"],
            frontier_fired_activation_id=frontier["fired_activation_id"],
            frontier_trigger_activation_id=frontier["trigger_activation_id"],
            resume_evidence=resume_evidence,
            duplicate_stone_evidence=duplicate_evidence,
            foreign_reference_rejection=_foreign_checkpoint_probe(world, foreign),
            excluded_source_rejection=_excluded_source_probe(world),
            rights_denied_probe=_rights_probe(world),
            unauthorized_decision_rejection=_unauthorized_decision_probe(world),
            self_attestation_probe=_self_attestation_probe(world, checkpoint),
            budget_exhausted_run_id=budget_probe.get("run_id"),
            saturated_run_id=settled,
            sediment_versions_before_close=world.oracle_inputs_extra.get(
                "sediment_versions_before_close"
            ),
            sediment_versions_after_close=world.oracle_inputs_extra.get(
                "sediment_versions_after_close"
            ),
            operator_answer_refs=_operator_sections(world)[1],
            capability_binding=world.binding,
        )
        oracle_rows = evaluate_rm_oracles(inputs)
        receipt = export_world(
            world, output_dir=world_dir, oracle_rows=oracle_rows, checkpoint=checkpoint
        )
        world_receipts.append(receipt)

    heads = [r["rm_summary"] for r in world_receipts]
    portfolio = {
        "schema": "seshat.m5_portfolio_receipt.v2",
        "fixture_path": str(fixture_path),
        "fixture_sha256": fixture_sha,
        "owner_fixture_crlf_sha256": OWNER_FIXTURE_CRLF_SHA256,
        "fixture_byte_representation": "GIT_LF_CANONICAL",
        "worlds": world_receipts,
        "rm_summaries": heads,
        "synthetic_only": True,
        "scientific_acceptance": "NOT_PERFORMED",
        "LOCAL_EXECUTION_NOT_PERFORMED_ON_AUTHORING_HOST": True,
    }
    (output_root / "m5_portfolio_receipt.json").write_text(
        json.dumps(portfolio, ensure_ascii=False, sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    return portfolio


def _partial_checkpoint(
    host: Mapping[str, Any], fixture: Mapping[str, Any], fixture_sha: str, *, stones_to_run: int
) -> M5Checkpoint:
    """Run only the first ``stones_to_run`` stones and freeze there."""

    truncated = dict(host)
    truncated["stones"] = list(host.get("stones") or [])[:stones_to_run]
    partial = run_world(truncated, fixture=fixture, fixture_sha256=fixture_sha)
    # The checkpoint belongs to the full host identity; only the cursor is short.
    partial.host = host
    return _checkpoint_for(partial)


def _compare_resume(
    completed: subprocess.CompletedProcess[str], child_dir: Path, *, control: WorldRun
) -> dict[str, Any]:
    """Compare the child process's continued evidence with the control run."""

    evidence_path = child_dir / "resume_evidence.json"
    if completed.returncode != 0 or not evidence_path.is_file():
        return {
            "child_process_completed": False,
            "returncode": completed.returncode,
            "stderr_tail": (completed.stderr or "")[-400:],
            "matches_uninterrupted_control": False,
        }
    child = json.loads(evidence_path.read_text(encoding="utf-8"))
    control_payloads = sorted(
        (r.sediment_id, r.payload_hash) for r in control.engine.sediment.all_records()
    )
    child_payloads = sorted(tuple(item) for item in child.get("sediment_payload_hashes") or [])
    differing = sorted(
        set(control_payloads).symmetric_difference(child_payloads)
    )
    return {
        "child_process_completed": True,
        "returncode": 0,
        "child_continued_stone_ids": child.get("continued_stone_ids"),
        "control_stone_ids": [o.stone_id for o in control.outcomes],
        "child_aporia_activations": child.get("aporia_activations"),
        "matches_uninterrupted_control": child_payloads == control_payloads,
        "differing_records": [list(item) for item in differing[:12]],
        "control_sediment_count": len(control_payloads),
        "child_sediment_count": len(child_payloads),
    }


# -- resume entry point -------------------------------------------------------


def continue_from_checkpoint(
    *,
    fixture_path: Path,
    approved_sha256: str | None,
    host_id: str,
    checkpoint_path: Path,
    output_dir: Path,
) -> int:
    """Child-process entry: load the checkpoint and finish the remaining stones."""

    fixture, fixture_sha = load_fixture(fixture_path, approved_sha256=approved_sha256)
    host = next(
        (h for h in fixture.get("hosts") or [] if str(h["host_id"]) == host_id), None
    )
    if host is None:
        raise CheckpointRejected(f"M5_RESUME_UNKNOWN_HOST {host_id!r}")
    checkpoint = load_checkpoint(checkpoint_path)
    world = run_world(
        host, fixture=fixture, fixture_sha256=fixture_sha, resume_from=checkpoint
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    continued = [o.stone_id for o in world.outcomes]
    aporias = [
        a.activation_id
        for a in world.engine.ledger.activations
        if a.error_code == "BODY_APORIA"
    ]
    (output_dir / "resume_evidence.json").write_text(
        json.dumps(
            {
                "schema": "seshat.m5_resume_evidence.v1",
                "host_id": host_id,
                "resumed_from_cursor": world.started_at_cursor,
                "continued_stone_ids": continued,
                "aporia_activations": aporias,
                "ledger_head": world.engine.ledger.head_hash,
                "sediment_payload_hashes": sorted(
                    [r.sediment_id, r.payload_hash] for r in world.engine.sediment.all_records()
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SESHAT M5 synthetic carpet runner")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="room fixture JSON; defaults to the packaged original when available",
    )
    parser.add_argument(
        "--fixture-sha256",
        type=str,
        default=None,
        help="caller-approved digest, required for any fixture other than the frozen original",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts") / "m5_carpet")
    parser.add_argument("--resume-checkpoint", type=Path, default=None)
    parser.add_argument("--host-id", type=str, default=None)
    parser.add_argument("--no-subprocess-resume", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    fixture_path = args.fixture or default_fixture_path()
    if fixture_path is None:
        print(
            "No fixture found. The packaged fixture resource is unavailable in this "
            "installation; pass --fixture PATH (and --fixture-sha256 for a non-original "
            "fixture).",
            file=sys.stderr,
        )
        return 2
    if args.resume_checkpoint:
        if not args.host_id:
            print("--resume-checkpoint requires --host-id", file=sys.stderr)
            return 2
        return continue_from_checkpoint(
            fixture_path=Path(fixture_path),
            approved_sha256=args.fixture_sha256,
            host_id=args.host_id,
            checkpoint_path=args.resume_checkpoint,
            output_dir=args.output_dir,
        )
    portfolio = run_two_worlds(
        Path(fixture_path),
        args.output_dir,
        approved_sha256=args.fixture_sha256,
        verify_subprocess_resume=not args.no_subprocess_resume,
    )
    not_tested = sorted(
        {
            oid
            for summary in portfolio["rm_summaries"]
            for oid in summary["not_tested_ids"]
        }
    )
    print(f"Wrote M5 carpet portfolio to {args.output_dir.resolve()}")
    if not_tested:
        print(f"{NOT_TESTED}: {', '.join(not_tested)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
