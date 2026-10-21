"""Event-scoped Room compilation: planned selection vs actual activation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from seshat.fabric_waves.contracts import ActivationRecord


def registry_thread_to_engine_ids(registry_id: str, host_slug: str) -> tuple[str, ...]:
    """Map fixture registry thread handles (N-S, N-Q, …) to engine thread_ids."""

    mapping: dict[str, tuple[str, ...]] = {
        "N-S": (f"obs-{host_slug}-alpha", f"obs-{host_slug}-beta"),
        "N-Q": (f"question-{host_slug}",),
        "N-K": (f"concepts-{host_slug}",),
        "N-E": (f"evidence-alpha-{host_slug}", f"evidence-beta-{host_slug}"),
        "N-C": (f"reconcile-{host_slug}",),
        "N-P": (f"answer-{host_slug}",),
        "N-H": (f"proposal-{host_slug}",),
        "N-F": (f"frontier-{host_slug}",),
    }
    return mapping.get(registry_id, ())


@dataclass
class RoomManifest:
    """Planned vs actual room admission for one stone-driven compilation."""

    room_id: str
    host_id: str
    stone_id: str
    planned_registry_threads: tuple[str, ...]
    planned_engine_threads: tuple[str, ...]
    actual_activated_threads: tuple[str, ...] = field(default_factory=tuple)
    status: str = "OPEN"
    budget: Mapping[str, Any] = field(default_factory=dict)

    def close(self, *, activations: Sequence[ActivationRecord], run_id: str) -> None:
        activated = {
            act.thread_id
            for act in activations
            if act.run_id == run_id and act.outcome.value != "SKIPPED"
        }
        self.actual_activated_threads = tuple(sorted(activated))
        missing = set(self.planned_engine_threads) - activated
        if missing and self.status == "OPEN":
            self.status = "PARTIAL_ADMISSION"
        elif not missing:
            self.status = "QUIESCENT"
        else:
            self.status = "CLOSED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "host_id": self.host_id,
            "stone_id": self.stone_id,
            "planned_registry_threads": list(self.planned_registry_threads),
            "planned_engine_threads": list(self.planned_engine_threads),
            "actual_activated_threads": list(self.actual_activated_threads),
            "status": self.status,
            "budget": dict(self.budget),
            "planned_vs_actual": {
                "planned_only": sorted(
                    set(self.planned_engine_threads) - set(self.actual_activated_threads)
                ),
                "actual_only": sorted(
                    set(self.actual_activated_threads) - set(self.planned_engine_threads)
                ),
            },
        }


def compile_room_for_stone(
    *,
    host_id: str,
    host_slug: str,
    stone: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> RoomManifest:
    registry_threads = tuple(stone.get("must_wave") or ())
    engine_threads: list[str] = []
    for reg_id in registry_threads:
        engine_threads.extend(registry_thread_to_engine_ids(reg_id, host_slug))
    # Stable dedupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for tid in engine_threads:
        if tid in seen:
            continue
        seen.add(tid)
        ordered.append(tid)
    room_id = f"{host_slug}:{stone['stone_id']}"
    return RoomManifest(
        room_id=room_id,
        host_id=host_id,
        stone_id=str(stone["stone_id"]),
        planned_registry_threads=registry_threads,
        planned_engine_threads=tuple(ordered),
        budget=budget,
    )


def manifests_to_json(manifests: Sequence[RoomManifest]) -> str:
    return json.dumps([m.to_dict() for m in manifests], ensure_ascii=False, sort_keys=True, indent=2)
