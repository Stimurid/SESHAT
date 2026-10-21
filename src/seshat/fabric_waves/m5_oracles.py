"""RM01-RM20 negative oracle matrix for M5 synthetic acceptance.

Every row is decided by a *specific observation* taken from a scenario that
actually ran.  There are no constant ``True`` verdicts: an oracle whose
scenario was not exercised reports ``NOT_TESTED``, which is a distinct and
non-passing state.  A counted metric is never accepted as a substitute for
the property it is supposed to witness (a fan-in is proven by the identity of
the consumed parent activations, not by a count of threads).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from seshat.fabric_waves.contracts import (
    ActivationOutcome,
    FabricRunOutcome,
    FabricStopReason,
    StoneEventKind,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.room_builder import DENIED_RIGHTS, RoomManifest

PASS = "PASS"
FAIL = "FAIL"
NOT_TESTED = "NOT_TESTED"

RM_IDS: tuple[str, ...] = tuple(f"RM{i:02d}" for i in range(1, 21))

_BACKTICK_REF = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class SourceObservation:
    """What a carrier actually held at one point of the run."""

    carrier_id: str
    version: str
    content_sha256: str | None


@dataclass(frozen=True)
class DerivedSnapshot:
    """Identity of the records derived from one branch at a point in time."""

    records: tuple[tuple[str, str, str], ...] = ()  # (sediment_id, version, payload_hash)
    activation_ids: tuple[str, ...] = ()


@dataclass
class OracleInputs:
    """Observations the runner collected.  Anything absent stays NOT_TESTED."""

    engine: WaveEngine
    run_ids: Sequence[str]
    manifests: Sequence[RoomManifest] = ()
    # RM04 / RM13: per-branch derived identity before and after the delta stone.
    alpha_before: DerivedSnapshot | None = None
    alpha_after: DerivedSnapshot | None = None
    beta_before: DerivedSnapshot | None = None
    beta_after: DerivedSnapshot | None = None
    delta_run_id: str | None = None
    source_before: Mapping[str, SourceObservation] = field(default_factory=dict)
    source_after: Mapping[str, SourceObservation] = field(default_factory=dict)
    # RM05: frontier eligibility observed before and after the need existed.
    frontier_capability_id: str | None = None
    frontier_admitted_before: bool | None = None
    frontier_admitted_after: bool | None = None
    frontier_fired_activation_id: str | None = None
    frontier_trigger_activation_id: str | None = None
    # RM06: real new-process continuation + duplicate-stone idempotence.
    resume_evidence: Mapping[str, Any] | None = None
    duplicate_stone_evidence: Mapping[str, Any] | None = None
    # RM07: a foreign-host reference presented to this host.
    foreign_reference_rejection: Mapping[str, Any] | None = None
    # RM08 / RM09 / RM11 / RM18: explicit negative probes.
    excluded_source_rejection: Mapping[str, Any] | None = None
    rights_denied_probe: Mapping[str, Any] | None = None
    unauthorized_decision_rejection: Mapping[str, Any] | None = None
    self_attestation_probe: Mapping[str, Any] | None = None
    # RM15: two runs whose stop reasons must differ in kind.
    budget_exhausted_run_id: str | None = None
    saturated_run_id: str | None = None
    # RM17: sediment identity captured immediately before/after room close.
    sediment_versions_before_close: Mapping[str, str] | None = None
    sediment_versions_after_close: Mapping[str, str] | None = None
    # RM19: citations extracted from the rendered operator answer (not pre-filtered).
    operator_answer_refs: Sequence[str] | None = None
    operator_report_markdown: str | None = None
    # RM20: the capability binding the host declared.
    capability_binding: Mapping[str, tuple[str, ...]] | None = None


def extract_operator_answer_refs(markdown: str) -> list[str]:
    """Backtick citations from the operator report, including unknown ids."""

    return list(dict.fromkeys(_BACKTICK_REF.findall(markdown)))


def _row(rm_id: str, name: str, observed: str, detail: str, **evidence: Any) -> dict[str, Any]:
    if observed not in (PASS, FAIL, NOT_TESTED):
        raise ValueError(f"ORACLE_INVALID_OBSERVED {observed!r}")
    return {
        "oracle_id": rm_id,
        "name": name,
        "observed": observed,
        "detail": detail,
        "evidence": {k: v for k, v in sorted(evidence.items())},
    }


def _verdict(ok: bool, *, when_true: str = PASS) -> str:
    return when_true if ok else FAIL


def evaluate_rm_oracles(inputs: OracleInputs) -> list[dict[str, Any]]:  # noqa: C901, PLR0915
    engine = inputs.engine
    run_ids = tuple(inputs.run_ids)
    acts = [a for a in engine.ledger.activations if a.run_id in run_ids]
    fired = [a for a in acts if a.outcome is ActivationOutcome.FIRED]
    by_id = {a.activation_id: a for a in engine.ledger.activations}
    rows: list[dict[str, Any]] = []
    # An engine that was never asked to run has not demonstrated anything.
    # Oracles whose property is only observable during execution report
    # NOT_TESTED rather than passing vacuously on an empty collection.
    exercised = bool(run_ids) and bool(acts)

    # -- RM01: a plan is not work -------------------------------------------
    if not inputs.manifests:
        rows.append(_row("RM01", "RM01_PLAN_NO_ACTIVATION", NOT_TESTED, "no room manifest supplied"))
    else:
        leaked: list[str] = []
        for manifest in inputs.manifests:
            if not manifest.run_id:
                # A room that was compiled but never admitted to a run is
                # exactly the case this oracle cares about: it must have
                # produced nothing, and it has no run to attribute work to.
                continue
            blocked_threads = {
                tid for cap in manifest.blocked for tid in cap.engine_thread_ids
            }
            run_fired = {a.thread_id for a in fired if a.run_id == manifest.run_id}
            leaked.extend(sorted(blocked_threads & run_fired))
        rows.append(
            _row(
                "RM01",
                "RM01_PLAN_NO_ACTIVATION",
                _verdict(not leaked),
                "no capability that the room refused produced an activation",
                planned_but_not_admitted_threads_that_fired=leaked,
                rooms_checked=[m.room_id for m in inputs.manifests],
            )
        )

    # -- RM02: an activation is backed by a real produced record -------------
    if not exercised:
        rows.append(_row("RM02", "RM02_REAL_ACTIVATION", NOT_TESTED, "no run was executed"))
    elif not fired:
        rows.append(_row("RM02", "RM02_REAL_ACTIVATION", FAIL, "no FIRED activation at all"))
    else:
        unbacked: list[str] = []
        for act in fired:
            if not act.produced_sediment_ids:
                continue
            for sid in act.produced_sediment_ids:
                record = engine.sediment.views["working"].get(sid) or engine.sediment.views[
                    "candidate"
                ].get(sid)
                history = engine.sediment.history(sid)
                if record is None and not history:
                    unbacked.append(f"{act.activation_id}:{sid}")
        producing = [a for a in fired if a.produced_sediment_ids]
        rows.append(
            _row(
                "RM02",
                "RM02_REAL_ACTIVATION",
                _verdict(bool(producing) and not unbacked),
                "every producing activation is backed by a retained sediment record",
                producing_activations=len(producing),
                unbacked=unbacked,
            )
        )

    # -- RM03: fan-out then join on two DISTINCT upstream activations --------
    join_evidence: dict[str, Any] = {}
    joined = False
    for act in fired:
        if not act.read_sediment_ids or len(act.read_sediment_ids) < 2:
            continue
        parents: set[str] = set()
        for sid in act.read_sediment_ids:
            for candidate in fired:
                if sid in candidate.produced_sediment_ids and candidate.activation_id != act.activation_id:
                    parents.add(candidate.activation_id)
        parent_threads = {by_id[p].thread_id for p in parents if p in by_id}
        if len(parents) >= 2 and len(parent_threads) >= 2:
            joined = True
            join_evidence = {
                "join_activation_id": act.activation_id,
                "join_thread_id": act.thread_id,
                "consumed_parent_activation_ids": sorted(parents),
                "consumed_parent_thread_ids": sorted(parent_threads),
            }
            break
    rows.append(
        _row(
            "RM03",
            "RM03_FANOUT_JOIN",
            _verdict(joined) if exercised else NOT_TESTED,
            "a join consumed records produced by two distinct upstream activations",
            **join_evidence,
        )
    )

    # -- RM04: independent branch A untouched while B changes ----------------
    have_delta = all(
        item is not None
        for item in (inputs.alpha_before, inputs.alpha_after, inputs.beta_before, inputs.beta_after)
    )
    if not have_delta or inputs.delta_run_id is None:
        rows.append(
            _row("RM04", "RM04_B_CHANGED_A_STABLE", NOT_TESTED, "delta snapshots not captured")
        )
    else:
        a_identical = inputs.alpha_before.records == inputs.alpha_after.records
        b_changed = inputs.beta_before.records != inputs.beta_after.records
        a_reexecuted = sorted(
            a.activation_id
            for a in fired
            if a.run_id == inputs.delta_run_id
            and a.activation_id in set(inputs.alpha_after.activation_ids)
            and a.activation_id not in set(inputs.alpha_before.activation_ids)
        )
        rows.append(
            _row(
                "RM04",
                "RM04_B_CHANGED_A_STABLE",
                _verdict(a_identical and b_changed and not a_reexecuted),
                "A kept record ids/versions/hashes and never re-fired; B's derived records changed",
                alpha_records_identical=a_identical,
                beta_records_changed=b_changed,
                alpha_reexecuted_activation_ids=a_reexecuted,
                alpha_records_before=[list(r) for r in inputs.alpha_before.records],
                alpha_records_after=[list(r) for r in inputs.alpha_after.records],
            )
        )

    # -- RM05: late eligibility is state-dependent, with a real trigger ------
    if inputs.frontier_admitted_before is None or inputs.frontier_admitted_after is None:
        rows.append(
            _row("RM05", "RM05_LATE_ELIGIBILITY", NOT_TESTED, "frontier eligibility not probed")
        )
    else:
        became_eligible = (
            inputs.frontier_admitted_before is False and inputs.frontier_admitted_after is True
        )
        really_fired = inputs.frontier_fired_activation_id is not None and (
            inputs.frontier_fired_activation_id in by_id
        )
        has_trigger = inputs.frontier_trigger_activation_id is not None
        rows.append(
            _row(
                "RM05",
                "RM05_LATE_ELIGIBILITY",
                _verdict(became_eligible and really_fired and has_trigger),
                "capability was not callable before the need existed and fired after it",
                capability=inputs.frontier_capability_id,
                admitted_before=inputs.frontier_admitted_before,
                admitted_after=inputs.frontier_admitted_after,
                fired_activation_id=inputs.frontier_fired_activation_id,
                triggering_predecessor_activation_id=inputs.frontier_trigger_activation_id,
            )
        )

    # -- RM06: durable new-process continuation + idempotent duplicate -------
    if inputs.resume_evidence is None:
        rows.append(
            _row("RM06", "RM06_REPLAY_IDEMPOTENT", NOT_TESTED, "no new-process resume evidence")
        )
    else:
        ev = dict(inputs.resume_evidence)
        resumed_ok = bool(ev.get("child_process_completed")) and bool(
            ev.get("matches_uninterrupted_control")
        )
        dup = dict(inputs.duplicate_stone_evidence or {})
        dup_ok = bool(dup) and dup.get("fresh_activations") == 0 and bool(dup.get("returned_stored_result"))
        observed = PASS if (resumed_ok and dup_ok) else (NOT_TESTED if not dup else FAIL)
        rows.append(
            _row(
                "RM06",
                "RM06_REPLAY_IDEMPOTENT",
                observed,
                "a child process continued from the checkpoint and a duplicate stone did no fresh work",
                resume=ev,
                duplicate_stone=dup,
            )
        )

    # -- RM07: a FOREIGN reference is rejected (not merely a hash difference)-
    if inputs.foreign_reference_rejection is None:
        rows.append(
            _row("RM07", "RM07_CROSS_HOST_ISOLATION", NOT_TESTED, "no foreign reference presented")
        )
    else:
        ev = dict(inputs.foreign_reference_rejection)
        rows.append(
            _row(
                "RM07",
                "RM07_CROSS_HOST_ISOLATION",
                _verdict(bool(ev.get("rejected")) and bool(ev.get("reason"))),
                "a reference owned by the other host was refused on admission",
                **ev,
            )
        )

    # -- RM08: an excluded source is refused ---------------------------------
    if inputs.excluded_source_rejection is None:
        rows.append(
            _row("RM08", "RM08_OWNER_EXCLUSION", NOT_TESTED, "no excluded-source admission attempted")
        )
    else:
        ev = dict(inputs.excluded_source_rejection)
        rows.append(
            _row(
                "RM08",
                "RM08_OWNER_EXCLUSION",
                _verdict(bool(ev.get("rejected"))),
                "an owner-excluded carrier was refused and produced no record",
                **ev,
            )
        )

    # -- RM09: a withheld right denies the capability and it never fires -----
    if inputs.rights_denied_probe is None:
        rows.append(_row("RM09", "RM09_RIGHTS_DENIAL", NOT_TESTED, "no rights-denial probe"))
    else:
        ev = dict(inputs.rights_denied_probe)
        rows.append(
            _row(
                "RM09",
                "RM09_RIGHTS_DENIAL",
                _verdict(
                    ev.get("admission") == DENIED_RIGHTS
                    and ev.get("activations") == 0
                    and ev.get("run_attempted")
                    and ev.get("outcome_status") == "NO_ADMITTED_CAPABILITY"
                ),
                "withholding the declared right refuses the run and yields zero fresh activations",
                **ev,
            )
        )

    # -- RM10: nothing is promoted to ACCEPTED -------------------------------
    accepted = engine.sediment.views["accepted"].values()
    rows.append(
        _row(
            "RM10",
            "RM10_E5_NO_PROMOTION",
            _verdict(len(accepted) == 0) if exercised else NOT_TESTED,
            "no record reached the ACCEPTED view without a human decision",
            accepted_sediment_ids=sorted(r.sediment_id for r in accepted),
            proposal_records=sorted(
                r.sediment_id
                for r in engine.sediment.all_records()
                if r.object_type == "synthetic.hypothesis_proposal"
            ),
        )
    )

    # -- RM11: no human-decision switch, and an unauthorized one is rejected -
    human_events = [
        e.event_id
        for e in engine.ledger.events
        if e.run_id in run_ids and e.kind is StoneEventKind.HUMAN_DECISION
    ]
    if inputs.unauthorized_decision_rejection is None:
        rows.append(
            _row(
                "RM11",
                "RM11_NO_HUMAN_SWITCH",
                NOT_TESTED,
                "absence of a decision event is not proof; no rejection probe was run",
                human_decision_events=human_events,
            )
        )
    else:
        ev = dict(inputs.unauthorized_decision_rejection)
        rows.append(
            _row(
                "RM11",
                "RM11_NO_HUMAN_SWITCH",
                _verdict(not human_events and bool(ev.get("rejected"))),
                "an unauthorized acceptance was actively refused and no decision entered the run",
                human_decision_events=human_events,
                **ev,
            )
        )

    # -- RM12: a declared conflict is retained as an aporia ------------------
    aporia_acts = [a for a in acts if a.error_code == "BODY_APORIA"]
    aporia_runs = [
        r.run_id
        for r in engine.ledger.runs
        if r.run_id in run_ids and r.outcome is FabricRunOutcome.APORIA
    ]
    rows.append(
        _row(
            "RM12",
            "RM12_APORIA_RETAINED",
            _verdict(bool(aporia_acts) and bool(aporia_runs)) if exercised else NOT_TESTED,
            "an aporia was recorded on an activation and ended its run as APORIA",
            aporia_activation_ids=sorted(a.activation_id for a in aporia_acts),
            aporia_runs=sorted(aporia_runs),
            aporia_details=sorted({a.error_detail or "" for a in aporia_acts}),
        )
    )

    # -- RM13: staleness is transitive AND bounded to the changed branch -----
    stale = engine.sediment.views["stale"].values()
    stale_ids = sorted(r.sediment_id for r in stale)
    if inputs.alpha_after is None or inputs.beta_after is None:
        rows.append(
            _row(
                "RM13",
                "RM13_TRANSITIVE_STALENESS",
                NOT_TESTED,
                "no delta snapshots; a stale count alone proves nothing",
                stale_sediment_ids=stale_ids,
            )
        )
    else:
        alpha_ids = {sid for sid, _, _ in inputs.alpha_after.records}
        beta_ids = {sid for sid, _, _ in inputs.beta_after.records}
        wrongly_stale = sorted(set(stale_ids) & alpha_ids)
        rows.append(
            _row(
                "RM13",
                "RM13_TRANSITIVE_STALENESS",
                _verdict(not wrongly_stale),
                "no record on the untouched branch was invalidated by the other branch's delta",
                stale_sediment_ids=stale_ids,
                untouched_branch_marked_stale=wrongly_stale,
                changed_branch_ids=sorted(beta_ids),
            )
        )

    # -- RM14: every source-witnessed record carries a pinned receipt --------
    e1 = [r for r in engine.sediment.all_records() if r.epistemic_level.value == "E1"]
    unanchored = sorted(
        r.sediment_id
        for r in e1
        if r.source_access_manifest is None or not r.source_access_manifest.receipts
    )
    rows.append(
        _row(
            "RM14",
            "RM14_SOURCE_ANCHOR_REQUIRED",
            _verdict(bool(e1) and not unanchored) if exercised else NOT_TESTED,
            "each source-witnessed record carries a version-pinned access receipt",
            e1_records=len(e1),
            unanchored=unanchored,
        )
    )

    # -- RM15: budget exhaustion and saturation are distinguishable ----------
    runs_by_id = {r.run_id: r for r in engine.ledger.runs}
    exhausted = runs_by_id.get(inputs.budget_exhausted_run_id or "")
    saturated = runs_by_id.get(inputs.saturated_run_id or "")
    if exhausted is None or saturated is None:
        rows.append(
            _row(
                "RM15",
                "RM15_BUDGET_AND_SATURATION_DIFFER",
                NOT_TESTED,
                "both a budget-capped run and a settled run are required",
                observed_stop_reasons=sorted(
                    {r.stop_reason.value for r in engine.ledger.runs if r.run_id in run_ids}
                ),
            )
        )
    else:
        ok = (
            exhausted.outcome is FabricRunOutcome.EXHAUSTED
            and exhausted.stop_reason
            in (
                FabricStopReason.MAX_WAVES,
                FabricStopReason.MAX_ACTIVATIONS,
                FabricStopReason.BUDGET_EXHAUSTED,
            )
            and saturated.outcome is not FabricRunOutcome.EXHAUSTED
        )
        rows.append(
            _row(
                "RM15",
                "RM15_BUDGET_AND_SATURATION_DIFFER",
                _verdict(ok),
                "a run stopped by budget is recorded differently from one that settled",
                budget_run=[exhausted.run_id, exhausted.outcome.value, exhausted.stop_reason.value],
                settled_run=[saturated.run_id, saturated.outcome.value, saturated.stop_reason.value],
            )
        )

    # -- RM16: no privileged issuer/server was used --------------------------
    external = engine.external_ledger
    rows.append(
        _row(
            "RM16",
            "RM16_NO_PRIVILEGED_SERVER",
            _verdict(
                engine.executor_port is None
                and not external.admitted_idempotency_keys
                and not external.research_needs
            )
            if exercised
            else NOT_TESTED,
            "no executor port bound and no external carrier admission occurred",
            executor_port_bound=engine.executor_port is not None,
            admitted_external_keys=len(external.admitted_idempotency_keys),
            research_needs=len(external.research_needs),
        )
    )

    # -- RM17: closing a room preserves sediment identity --------------------
    if inputs.sediment_versions_before_close is None or inputs.sediment_versions_after_close is None:
        rows.append(
            _row("RM17", "RM17_ROOM_CLOSE_PRESERVES_SEDIMENT", NOT_TESTED, "no close snapshots")
        )
    else:
        before = dict(inputs.sediment_versions_before_close)
        after = dict(inputs.sediment_versions_after_close)
        lost = sorted(k for k in before if k not in after)
        mutated = sorted(k for k in before if k in after and before[k] != after[k])
        rows.append(
            _row(
                "RM17",
                "RM17_ROOM_CLOSE_PRESERVES_SEDIMENT",
                _verdict(not lost and not mutated),
                "room close dropped no record and rewrote no version",
                lost_sediment_ids=lost,
                mutated_sediment_ids=mutated,
                retained=len(before),
            )
        )

    # -- RM18: a self-made receipt is not external authority -----------------
    if inputs.self_attestation_probe is None:
        rows.append(
            _row("RM18", "RM18_SELF_ATTESTATION_BOUNDARY", NOT_TESTED, "no self-attestation probe")
        )
    else:
        ev = dict(inputs.self_attestation_probe)
        rows.append(
            _row(
                "RM18",
                "RM18_SELF_ATTESTATION_BOUNDARY",
                _verdict(
                    bool(ev.get("checkpoint_verified_as_own"))
                    and not ev.get("granted_external_authority", True)
                    and len(accepted) == 0
                ),
                "a self-owned checkpoint verified as integrity only, never as external attestation",
                **ev,
            )
        )

    # -- RM19: the operator answer cites records that exist ------------------
    if inputs.operator_report_markdown is None and inputs.operator_answer_refs is None:
        rows.append(
            _row("RM19", "RM19_PRODUCT_VIEW_PROVENANCE", NOT_TESTED, "no operator answer rendered")
        )
    else:
        known = {r.sediment_id for r in engine.sediment.all_records()} | {
            a.activation_id for a in engine.ledger.activations
        }
        if inputs.operator_report_markdown is not None:
            refs = extract_operator_answer_refs(inputs.operator_report_markdown)
        else:
            refs = list(inputs.operator_answer_refs or ())
        dangling = sorted(set(refs) - known)
        rows.append(
            _row(
                "RM19",
                "RM19_PRODUCT_VIEW_PROVENANCE",
                _verdict(bool(refs) and not dangling),
                "every backtick citation in the operator answer resolves to a real record or activation",
                references=len(refs),
                dangling=dangling,
            )
        )

    # -- RM20: threads are bound capabilities, not named actors --------------
    if inputs.capability_binding is None:
        rows.append(_row("RM20", "RM20_ORGAN_NOT_ACTOR", NOT_TESTED, "no capability binding supplied"))
    else:
        bound = {tid for ids in inputs.capability_binding.values() for tid in ids}
        unbound = sorted({a.thread_id for a in fired} - bound)
        rows.append(
            _row(
                "RM20",
                "RM20_ORGAN_NOT_ACTOR",
                _verdict(bool(fired) and not unbound),
                "every thread that fired is bound to a declared registry capability",
                capabilities=sorted(inputs.capability_binding),
                unbound_threads_that_fired=unbound,
            )
        )

    observed_ids = [row["oracle_id"] for row in rows]
    if observed_ids != list(RM_IDS):
        raise ValueError(f"ORACLE_MATRIX_INCOMPLETE {observed_ids}")
    return rows


def oracle_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {PASS: 0, FAIL: 0, NOT_TESTED: 0}
    for row in rows:
        counts[str(row["observed"])] += 1
    return {
        "pass": counts[PASS],
        "fail": counts[FAIL],
        "not_tested": counts[NOT_TESTED],
        "not_tested_ids": [r["oracle_id"] for r in rows if r["observed"] == NOT_TESTED],
        "failed_ids": [r["oracle_id"] for r in rows if r["observed"] == FAIL],
        "all_passed": counts[FAIL] == 0 and counts[NOT_TESTED] == 0,
    }


__all__ = [
    "FAIL",
    "NOT_TESTED",
    "PASS",
    "RM_IDS",
    "DerivedSnapshot",
    "OracleInputs",
    "SourceObservation",
    "evaluate_rm_oracles",
    "extract_operator_answer_refs",
    "oracle_summary",
]
