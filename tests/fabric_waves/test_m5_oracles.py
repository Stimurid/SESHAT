"""No oracle may report PASS without a specific observation behind it.

These fail against a matrix that hardcodes ``True`` for RM08/09/16/19/20,
accepts ``len(stale) >= 0`` for RM13, or treats a thread count as a fan-in.
"""

from pathlib import Path

import pytest

from seshat.fabric_waves.contracts import StoneEventKind
from seshat.fabric_waves.m5_oracles import (
    FAIL,
    NOT_TESTED,
    PASS,
    RM_IDS,
    DerivedSnapshot,
    OracleInputs,
    evaluate_rm_oracles,
    oracle_summary,
)
from seshat.fabric_waves.m5_room_carpet import load_fixture
from seshat.fabric_waves.m5_synthetic_hosts import build_host_engine
from seshat.fabric_waves.sediment import SedimentRecord

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m5_room_synthetic_acceptance_20261021_v01.json"
)


@pytest.fixture()
def idle_engine():
    data, _ = load_fixture(FIXTURE)
    engine, _uri, binding = build_host_engine(data["hosts"][0])
    return engine, binding


def rows_by_id(rows):
    return {row["oracle_id"]: row for row in rows}


def test_every_oracle_id_is_reported_exactly_once(idle_engine):
    engine, _ = idle_engine
    rows = evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[]))
    assert [row["oracle_id"] for row in rows] == list(RM_IDS)


@pytest.mark.parametrize("oracle_id", ["RM04", "RM05", "RM06", "RM07", "RM08", "RM09", "RM13", "RM15", "RM17", "RM18", "RM19", "RM20"])
def test_unexercised_oracles_report_not_tested_never_pass(idle_engine, oracle_id):
    """The exact regression: an unrun scenario must not look like a success."""

    engine, _ = idle_engine
    rows = rows_by_id(evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[])))
    assert rows[oracle_id]["observed"] == NOT_TESTED, rows[oracle_id]


def test_nothing_passes_on_an_engine_that_never_ran(idle_engine):
    """No PASS may be produced without execution. The old matrix gave five."""

    engine, _ = idle_engine
    rows = evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[]))
    summary = oracle_summary(rows)
    assert summary["pass"] == 0, [r for r in rows if r["observed"] == PASS]
    assert summary["all_passed"] is False
    assert summary["not_tested"] == len(RM_IDS)


def test_rm11_absence_of_an_event_is_not_proof(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[])))
    assert rows["RM11"]["observed"] == NOT_TESTED
    assert "not proof" in rows["RM11"]["detail"]


def test_rm13_requires_a_delta_not_a_nonnegative_count(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[])))
    assert rows["RM13"]["observed"] == NOT_TESTED
    assert "proves nothing" in rows["RM13"]["detail"]


def test_rm13_fails_when_the_untouched_branch_is_invalidated(idle_engine):
    """Staleness must be scoped to the changed branch, not merely counted."""

    engine, _ = idle_engine
    alpha = DerivedSnapshot(records=(("obs-x-alpha", "1", "h"),))
    beta = DerivedSnapshot(records=(("obs-x-beta", "2", "h2"),))

    def verdict():
        rows = rows_by_id(
            evaluate_rm_oracles(
                OracleInputs(
                    engine=engine,
                    run_ids=[],
                    alpha_before=alpha,
                    alpha_after=alpha,
                    beta_before=beta,
                    beta_after=beta,
                )
            )
        )
        return rows["RM13"]

    clean = verdict()
    assert clean["observed"] == PASS
    assert clean["evidence"]["untouched_branch_marked_stale"] == []

    # Now mark a record belonging to the UNTOUCHED branch as stale.
    engine.sediment.views["stale"].put(
        SedimentRecord(
            sediment_id="obs-x-alpha",
            object_type="synthetic.observation",
            version="1",
            research_object_id="synthetic",
            payload={},
            payload_hash="0" * 64,
            provenance=("TEST_FIXTURE",),
            produced_by_thread="t",
            produced_at_tick=1,
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.QUERY,
        )
    )
    dirty = verdict()
    assert dirty["observed"] == FAIL
    assert dirty["evidence"]["untouched_branch_marked_stale"] == ["obs-x-alpha"]


def test_rm04_requires_record_identity_not_a_hash_pair(idle_engine):
    engine, _ = idle_engine
    same = DerivedSnapshot(records=(("obs-a", "v1", "h1"),), activation_ids=("act-1",))
    changed_before = DerivedSnapshot(records=(("obs-b", "v1", "h1"),))
    changed_after = DerivedSnapshot(records=(("obs-b", "v2", "h2"),))
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                alpha_before=same,
                alpha_after=same,
                beta_before=changed_before,
                beta_after=changed_after,
                delta_run_id="run-delta",
            )
        )
    )
    assert rows["RM04"]["observed"] == PASS
    assert rows["RM04"]["evidence"]["alpha_records_identical"] is True
    assert rows["RM04"]["evidence"]["beta_records_changed"] is True

    # If A's derived records changed too, the oracle must fail.
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                alpha_before=changed_before,
                alpha_after=changed_after,
                beta_before=changed_before,
                beta_after=changed_after,
                delta_run_id="run-delta",
            )
        )
    )
    assert rows["RM04"]["observed"] == FAIL


def test_rm06_needs_both_a_resume_and_a_duplicate_observation(idle_engine):
    engine, _ = idle_engine
    resume_ok = {"child_process_completed": True, "matches_uninterrupted_control": True}
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(engine=engine, run_ids=[], resume_evidence=resume_ok)
        )
    )
    # A resume alone is not replay idempotence.
    assert rows["RM06"]["observed"] == NOT_TESTED

    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                resume_evidence=resume_ok,
                duplicate_stone_evidence={"fresh_activations": 0, "returned_stored_result": True},
            )
        )
    )
    assert rows["RM06"]["observed"] == PASS

    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                resume_evidence=resume_ok,
                duplicate_stone_evidence={"fresh_activations": 3, "returned_stored_result": False},
            )
        )
    )
    assert rows["RM06"]["observed"] == FAIL


def test_rm07_requires_a_rejection_not_a_hash_difference(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                foreign_reference_rejection={"rejected": False, "reason": ""},
            )
        )
    )
    assert rows["RM07"]["observed"] == FAIL
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                foreign_reference_rejection={
                    "rejected": True,
                    "reason": "M5_CHECKPOINT_FOREIGN_HOST",
                },
            )
        )
    )
    assert rows["RM07"]["observed"] == PASS


def test_rm05_requires_a_real_eligibility_change_and_a_trigger(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                frontier_capability_id="N-F",
                frontier_admitted_before=True,
                frontier_admitted_after=True,
                frontier_fired_activation_id="a",
                frontier_trigger_activation_id="t",
            )
        )
    )
    # Always-eligible is not late eligibility.
    assert rows["RM05"]["observed"] == FAIL


def test_rm09_requires_denial_and_zero_activations(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                rights_denied_probe={"admission": "DENIED_RIGHTS", "activations": 2},
            )
        )
    )
    assert rows["RM09"]["observed"] == FAIL


def test_rm09_requires_active_run_refusal_not_vacuous_zero(idle_engine):
    engine, _ = idle_engine
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                rights_denied_probe={
                    "admission": "DENIED_RIGHTS",
                    "activations": 0,
                    "run_attempted": False,
                },
            )
        )
    )
    assert rows["RM09"]["observed"] == FAIL


def test_rm19_fails_when_report_cites_phantom_record(idle_engine):
    engine, _ = idle_engine
    phantom = "m5-phantom-sediment-never-written"
    markdown = f"## Basis\n\nSee `{phantom}` for the claimed evidence.\n"
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                operator_report_markdown=markdown,
            )
        )
    )
    assert rows["RM19"]["observed"] == FAIL
    assert phantom in rows["RM19"]["evidence"]["dangling"]


def test_rm19_filtered_ref_list_cannot_hide_phantom_in_markdown(idle_engine):
    engine, _ = idle_engine
    phantom = "dangling-run-id-not-in-ledger"
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(
                engine=engine,
                run_ids=[],
                operator_answer_refs=[],
                operator_report_markdown=f"Inspect `{phantom}` in the run ledger.",
            )
        )
    )
    assert rows["RM19"]["observed"] == FAIL


def test_rm20_rejects_a_thread_that_is_not_a_declared_capability(idle_engine):
    engine, binding = idle_engine
    rows = rows_by_id(
        evaluate_rm_oracles(
            OracleInputs(engine=engine, run_ids=[], capability_binding=binding)
        )
    )
    # Nothing fired, so this cannot pass either.
    assert rows["RM20"]["observed"] == FAIL


def test_summary_counts_not_tested_separately(idle_engine):
    engine, _ = idle_engine
    rows = evaluate_rm_oracles(OracleInputs(engine=engine, run_ids=[]))
    summary = oracle_summary(rows)
    assert summary["not_tested"] > 0
    assert summary["pass"] + summary["fail"] + summary["not_tested"] == len(RM_IDS)
    assert set(summary["not_tested_ids"]).isdisjoint(summary["failed_ids"])
