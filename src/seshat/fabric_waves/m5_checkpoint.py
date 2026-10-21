"""Durable M5 run checkpoint: real continuation state, not a progress note.

Modelled directly on the existing
:class:`~seshat.fabric_waves.external_carrier.wait_checkpoint.ExternalWaitCheckpoint`
donor (pydantic body, canonical checksum, atomic write, read-back
verification) and on :meth:`RunLedger.serialize` / :meth:`verify_serialized`.
No second scheduler is introduced: continuation re-enters the same
:class:`WaveEngine` with its ledger, sediment, source versions, dispatcher
queue and budget restored.

Scope limitation, stated plainly: a checkpoint is only taken at a *quiescent*
point — between stones, when no run is mid-wave.  A process that dies inside
a stone leaves ``completed=False`` with that stone recorded as
``pending_stone_id``; continuation does **not** blindly re-run it, because
the work it may already have paid for cannot be observed from here.  Such a
checkpoint must be reconciled explicitly (``reconcile_pending``) before the
remaining stones continue.

A checkpoint is self-owned host state.  Verifying its checksum proves
integrity only.  It is never external attestation and never upgrades
anything to ACCEPTED.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from seshat.fabric_waves.contracts import StoneEvent, WaveBudget
from seshat.fabric_waves.external_carrier.contracts import material_hash
from seshat.fabric_waves.ledger import (
    LedgerConsistencyError,
    RunLedger,
)
from seshat.fabric_waves.sediment import SedimentRecord

SCHEMA_VERSION = "seshat.m5_run_checkpoint.v1"

#: Views restored verbatim; ``accepted`` is deliberately included so that a
#: checkpoint can never quietly *gain* an acceptance across a restart.
RESTORED_VIEWS: tuple[str, ...] = ("working", "candidate", "accepted", "stale")


class CheckpointRejected(ValueError):
    """The checkpoint is corrupted, foreign, or inconsistent with this host."""


class AppliedDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    carrier_id: str
    old_version: str
    new_version: str
    new_text: str


class StoredRunResult(BaseModel):
    """What a completed stone produced, kept so a duplicate does no fresh work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    stone_id: str
    stone_fingerprint: str
    outcome: str
    stop_reason: str
    ledger_head_after: str
    produced_sediment_ids: tuple[str, ...] = ()
    activation_ids: tuple[str, ...] = ()


class M5Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    host_id: str
    world_slug: str
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_token: str = Field(pattern=r"^[0-9a-f]{64}$")

    stone_cursor: int = Field(ge=0)
    processed_stone_ids: tuple[str, ...] = ()
    stone_fingerprints: dict[str, str] = Field(default_factory=dict)
    completed: bool = True
    pending_stone_id: str | None = None

    applied_source_deltas: tuple[AppliedDelta, ...] = ()
    source_versions: dict[str, str] = Field(default_factory=dict)
    source_digests: dict[str, str] = Field(default_factory=dict)

    sediment_records: tuple[dict[str, Any], ...] = ()
    sediment_views: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    sediment_producers: dict[str, str] = Field(default_factory=dict)

    ledger: dict[str, Any] = Field(default_factory=dict)
    ledger_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    pending_stones: tuple[dict[str, Any], ...] = ()
    budget: dict[str, Any] = Field(default_factory=dict)
    run_results: tuple[StoredRunResult, ...] = ()

    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    # -- integrity ----------------------------------------------------------

    def _body(self) -> dict[str, Any]:
        data = self.model_dump(mode="python")
        data.pop("checksum")
        return data

    def verify_checksum(self) -> None:
        if material_hash(self._body()) != self.checksum:
            raise CheckpointRejected("M5_CHECKPOINT_CHECKSUM_INVALID")

    def verify_owner(self, *, host_id: str, fixture_sha256: str) -> None:
        """Refuse a checkpoint belonging to a different host or fixture.

        This is an ownership check on this host's own state, not a trust
        decision about an external party.
        """

        if self.schema_version != SCHEMA_VERSION:
            raise CheckpointRejected("M5_CHECKPOINT_SCHEMA_UNKNOWN")
        if self.host_id != host_id:
            raise CheckpointRejected(
                f"M5_CHECKPOINT_FOREIGN_HOST owner={self.host_id!r} reader={host_id!r}"
            )
        if self.fixture_sha256 != fixture_sha256:
            raise CheckpointRejected("M5_CHECKPOINT_FOREIGN_FIXTURE")
        if owner_token(host_id=host_id, fixture_sha256=fixture_sha256) != self.owner_token:
            raise CheckpointRejected("M5_CHECKPOINT_OWNER_TOKEN_MISMATCH")

    def verify_ledger(self) -> None:
        try:
            RunLedger.verify_serialized(self.ledger, expected_head=self.ledger_head_hash)
        except LedgerConsistencyError as exc:
            raise CheckpointRejected("M5_CHECKPOINT_LEDGER_INVALID") from exc

    def verify_all(self, *, host_id: str, fixture_sha256: str) -> None:
        self.verify_checksum()
        self.verify_owner(host_id=host_id, fixture_sha256=fixture_sha256)
        self.verify_ledger()

    def result_for_fingerprint(self, fingerprint: str) -> StoredRunResult | None:
        for item in self.run_results:
            if item.stone_fingerprint == fingerprint:
                return item
        return None


def owner_token(*, host_id: str, fixture_sha256: str) -> str:
    return material_hash(
        {"schema": SCHEMA_VERSION, "host_id": host_id, "fixture_sha256": fixture_sha256}
    )


def stone_fingerprint(stone: Mapping[str, Any], *, source_versions: Mapping[str, str]) -> str:
    """Identity of a stone *in the state it is applied to*.

    The same stone against different source versions is a different unit of
    work; the same stone against the same state is a duplicate.
    """

    return material_hash(
        {
            "stone_id": str(stone.get("stone_id")),
            "kind": str(stone.get("kind")),
            "question": str(stone.get("question") or ""),
            "mutation": dict(stone.get("mutation") or {}),
            "conflict": dict(stone.get("conflict") or {}),
            "source_versions": dict(sorted(source_versions.items())),
        }
    )


# -- capture ------------------------------------------------------------------


def capture_checkpoint(
    *,
    engine: Any,
    host_id: str,
    world_slug: str,
    fixture_sha256: str,
    stone_cursor: int,
    processed_stone_ids: Sequence[str],
    stone_fingerprints: Mapping[str, str],
    source_versions: Mapping[str, str],
    source_digests: Mapping[str, str],
    applied_source_deltas: Sequence[AppliedDelta],
    budget: WaveBudget,
    run_results: Sequence[StoredRunResult],
    completed: bool = True,
    pending_stone_id: str | None = None,
) -> M5Checkpoint:
    """Freeze everything a new process needs to continue this world."""

    records = engine.sediment.all_records()
    views = {
        name: tuple(sorted(r.sediment_id for r in engine.sediment.views[name].values()))
        for name in RESTORED_VIEWS
    }
    producers: dict[str, str] = {}
    for act in engine.ledger.activations:
        for sid in act.produced_sediment_ids:
            producers[sid] = act.activation_id

    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "host_id": host_id,
        "world_slug": world_slug,
        "fixture_sha256": fixture_sha256,
        "owner_token": owner_token(host_id=host_id, fixture_sha256=fixture_sha256),
        "stone_cursor": stone_cursor,
        "processed_stone_ids": tuple(processed_stone_ids),
        "stone_fingerprints": dict(stone_fingerprints),
        "completed": completed,
        "pending_stone_id": pending_stone_id,
        "applied_source_deltas": tuple(applied_source_deltas),
        "source_versions": dict(source_versions),
        "source_digests": {k: v for k, v in source_digests.items() if v is not None},
        "sediment_records": tuple(r.model_dump(mode="json") for r in records),
        "sediment_views": views,
        "sediment_producers": producers,
        "ledger": engine.ledger.serialize(),
        "ledger_head_hash": engine.ledger.head_hash,
        "pending_stones": tuple(
            e.model_dump(mode="json") for e in engine.dispatcher.pending
        ),
        "budget": budget.model_dump(mode="json"),
        "run_results": tuple(run_results),
    }
    checkpoint = M5Checkpoint(**body, checksum="0" * 64)
    return checkpoint.model_copy(update={"checksum": material_hash(checkpoint._body())})


def write_checkpoint(path: Path, checkpoint: M5Checkpoint) -> None:
    """Atomic write with read-back verification (same discipline as the donor)."""

    checkpoint.verify_checksum()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        checkpoint.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    restored = M5Checkpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))
    restored.verify_checksum()


def load_checkpoint(path: Path) -> M5Checkpoint:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointRejected("M5_CHECKPOINT_UNREADABLE") from exc
    try:
        checkpoint = M5Checkpoint.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise CheckpointRejected("M5_CHECKPOINT_MALFORMED") from exc
    checkpoint.verify_checksum()
    return checkpoint


# -- restore ------------------------------------------------------------------


def restore_ledger(serialized: Mapping[str, Any], *, expected_head: str) -> RunLedger:
    """Rebuild a ledger by replaying its recorded append order.

    Using only the public ``append_*`` API means the hash chain is
    recomputed rather than asserted, so a tampered export cannot restore to
    the head it claims.
    """

    RunLedger.verify_serialized(serialized, expected_head=expected_head)
    from seshat.fabric_waves.contracts import (
        ActivationRecord,
        DecisionRecord,
        EventRecord,
        ResonanceRecord,
        RunRecord,
        WaveRecord,
    )

    models = {
        "runs": (RunRecord, "append_run"),
        "events": (EventRecord, "append_event"),
        "waves": (WaveRecord, "append_wave"),
        "activations": (ActivationRecord, "append_activation"),
        "decisions": (DecisionRecord, "append_decision"),
        "resonances": (ResonanceRecord, "append_resonance"),
    }
    parsed = {
        kind: [model.model_validate(item) for item in serialized[kind]]
        for kind, (model, _) in models.items()
    }
    ledger = RunLedger()
    for kind, index in serialized["append_order"]:
        model_cls, method = models[str(kind)]
        getattr(ledger, method)(parsed[str(kind)][int(index)])
    if ledger.head_hash != expected_head:
        raise CheckpointRejected("M5_CHECKPOINT_LEDGER_HEAD_MISMATCH")
    ledger.verify(expected_head=expected_head)
    return ledger


def restore_into(
    engine: Any,
    checkpoint: M5Checkpoint,
    *,
    host_id: str,
    fixture_sha256: str,
) -> None:
    """Rehydrate a freshly built engine so it continues the same world.

    The engine must be built from the same fixture host (same threads, same
    initial carriers); this restores the *state*, not the topology.
    """

    checkpoint.verify_all(host_id=host_id, fixture_sha256=fixture_sha256)

    # 1. Source state: replay the deltas through the host's own pinned
    #    revision authority. The checkpoint supplies no content authority.
    for delta in checkpoint.applied_source_deltas:
        engine.carrier_store.apply_delta(
            delta.carrier_id,
            new_version=delta.new_version,
            new_text=delta.new_text,
            old_version=delta.old_version,
        )
    current = engine.carrier_store.current_source_versions(
        tuple(checkpoint.source_versions)
    )
    if current != dict(checkpoint.source_versions):
        raise CheckpointRejected(
            f"M5_CHECKPOINT_SOURCE_VERSION_MISMATCH expected={checkpoint.source_versions} got={current}"
        )

    # 2. Sediment, including which view each record was in.
    for item in checkpoint.sediment_records:
        engine.sediment.deposit(SedimentRecord.model_validate(item))
    for name in RESTORED_VIEWS:
        wanted = set(checkpoint.sediment_views.get(name) or ())
        view = engine.sediment.views[name]
        for record in engine.sediment.all_records():
            if record.sediment_id in wanted:
                view.put(record)
            elif record.sediment_id in view:
                view.drop(record.sediment_id)

    # 3. Ledger with its verified append order.
    engine.ledger = restore_ledger(checkpoint.ledger, expected_head=checkpoint.ledger_head_hash)

    # 4. Dispatcher queue the previous process had not yet consumed.
    for item in checkpoint.pending_stones:
        engine.dispatcher.drop(StoneEvent.model_validate(item))


def reconcile_pending(checkpoint: M5Checkpoint, *, decision: str) -> M5Checkpoint:
    """Explicitly resolve a checkpoint written while a stone was in flight.

    ``decision`` must be ``DISCARD_PENDING_STONE`` (the stone is re-queued as
    unstarted work) or ``ACCEPT_PENDING_AS_DONE``.  There is no automatic
    option: silently re-running an interrupted stone can duplicate paid work,
    and silently skipping it can lose it.
    """

    if checkpoint.completed:
        return checkpoint
    if decision not in ("DISCARD_PENDING_STONE", "ACCEPT_PENDING_AS_DONE"):
        raise CheckpointRejected(f"M5_CHECKPOINT_RECONCILE_UNKNOWN {decision!r}")
    if decision == "ACCEPT_PENDING_AS_DONE":
        pending = checkpoint.pending_stone_id
        updated = checkpoint.model_copy(
            update={
                "completed": True,
                "pending_stone_id": None,
                "processed_stone_ids": tuple(
                    [*checkpoint.processed_stone_ids, pending] if pending else checkpoint.processed_stone_ids
                ),
            }
        )
    else:
        updated = checkpoint.model_copy(
            update={"completed": True, "pending_stone_id": None}
        )
    return updated.model_copy(update={"checksum": material_hash(updated._body())})


__all__ = [
    "RESTORED_VIEWS",
    "SCHEMA_VERSION",
    "AppliedDelta",
    "CheckpointRejected",
    "M5Checkpoint",
    "StoredRunResult",
    "capture_checkpoint",
    "load_checkpoint",
    "owner_token",
    "reconcile_pending",
    "restore_into",
    "restore_ledger",
    "stone_fingerprint",
    "write_checkpoint",
]
