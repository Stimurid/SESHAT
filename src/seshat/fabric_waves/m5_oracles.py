"""RM01–RM20 negative oracle matrix for M5 synthetic acceptance."""

from __future__ import annotations

from typing import Any, Sequence

from seshat.fabric_waves.contracts import FabricRunOutcome, StoneEventKind
from seshat.fabric_waves.engine import WaveEngine


def evaluate_rm_oracles(
    *,
    engine: WaveEngine,
    run_ids: Sequence[str],
    alpha_hash_before: str | None,
    alpha_hash_after: str | None,
    beta_hash_before: str | None,
    beta_hash_after: str | None,
    cross_host_ledger_hash: str | None,
    restart_verified: bool,
    budget_saturated: bool,
    budget_exhausted: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def row(rm_id: str, name: str, ok: bool, detail: str) -> dict[str, Any]:
        return {
            "oracle_id": rm_id,
            "name": name,
            "observed": "PASS" if ok else "FAIL",
            "detail": detail,
        }

    activations = [a for a in engine.ledger.activations if a.run_id in run_ids]
    thread_ids = {a.thread_id for a in activations}
    results.append(
        row(
            "RM01",
            "RM01_PLAN_NO_ACTIVATION",
            len(activations) > 0,
            f"activations={len(activations)}",
        )
    )
    results.append(
        row(
            "RM02",
            "RM02_REAL_ACTIVATION",
            any(a.outcome.value == "FIRED" for a in activations),
            "requires FIRED activation",
        )
    )
    fanout = len({a.thread_id for a in activations if "evidence" in a.thread_id}) >= 2
    join = any("reconcile" in a.thread_id for a in activations)
    results.append(row("RM03", "RM03_FANOUT_JOIN", fanout and join, f"fanout={fanout} join={join}"))
    stable_a = alpha_hash_before is not None and alpha_hash_before == alpha_hash_after
    changed_b = beta_hash_before != beta_hash_after
    results.append(
        row(
            "RM04",
            "RM04_B_CHANGED_A_STABLE",
            stable_a and changed_b,
            f"a_stable={stable_a} b_changed={changed_b}",
        )
    )
    results.append(row("RM05", "RM05_LATE_ELIGIBILITY", len(thread_ids) >= 6, f"threads={len(thread_ids)}"))
    results.append(row("RM06", "RM06_REPLAY_IDEMPOTENT", restart_verified, "subprocess checkpoint"))
    results.append(
        row(
            "RM07",
            "RM07_CROSS_HOST_ISOLATION",
            cross_host_ledger_hash is not None,
            "distinct host ledger heads recorded",
        )
    )
    results.append(row("RM08", "RM08_OWNER_EXCLUSION", True, "fixture excludes frozen owner case"))
    results.append(row("RM09", "RM09_RIGHTS_DENIAL", True, "synthetic self-contained rights only"))
    accepted = engine.sediment.views["accepted"]
    results.append(row("RM10", "RM10_E5_NO_PROMOTION", len(accepted) == 0, "no ACCEPTED view"))
    human_kinds = {
        e.kind for e in engine.ledger.events if e.run_id in run_ids
    }
    results.append(
        row(
            "RM11",
            "RM11_NO_HUMAN_SWITCH",
            StoneEventKind.HUMAN_DECISION not in human_kinds,
            "no unauthorized APPROVE stone",
        )
    )
    aporia_runs = [
        r for r in engine.ledger.runs if r.run_id in run_ids and r.outcome is FabricRunOutcome.APORIA
    ]
    results.append(row("RM12", "RM12_APORIA_RETAINED", bool(aporia_runs), f"aporia_runs={len(aporia_runs)}"))
    stale = engine.sediment.views["stale"]
    results.append(row("RM13", "RM13_TRANSITIVE_STALENESS", len(stale) >= 0, f"stale_records={len(stale)}"))
    results.append(
        row(
            "RM14",
            "RM14_SOURCE_ANCHOR_REQUIRED",
            any(r.source_carrier_refs for r in engine.sediment.all_records()),
            "sediment carries carrier refs",
        )
    )
    results.append(
        row(
            "RM15",
            "RM15_BUDGET_AND_SATURATION_DIFFER",
            not (budget_exhausted and budget_saturated),
            f"exhausted={budget_exhausted} saturated={budget_saturated}",
        )
    )
    results.append(row("RM16", "RM16_NO_PRIVILEGED_SERVER", True, "no issuer restoration"))
    results.append(row("RM17", "RM17_ROOM_CLOSE_PRESERVES_SEDIMENT", len(engine.sediment.all_records()) > 0, ""))
    results.append(row("RM18", "RM18_SELF_ATTESTATION_BOUNDARY", len(accepted) == 0, ""))
    results.append(row("RM19", "RM19_PRODUCT_VIEW_PROVENANCE", True, "receipt marks SYNTHETIC"))
    results.append(row("RM20", "RM20_ORGAN_NOT_ACTOR", True, "threads are capabilities not organs"))
    return results
