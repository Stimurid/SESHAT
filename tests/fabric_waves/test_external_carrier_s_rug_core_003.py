"""S-RUG-CORE-003 Phase A: external worker carrier negative and demo gates."""

import json

import pytest

from seshat.fabric_waves.contracts import FabricRunOutcome, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngineConfigurationError
from seshat.fabric_waves.external_carrier.contracts import (
    EpistemicLevel,
    ExternalResumeReceipt,
)
from seshat.fabric_waves.external_carrier.fake_host import FakeHostExecutor
from seshat.fabric_waves.external_carrier.hosts import campus_external_host_engine
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError, verify_resume_receipt
from seshat.fabric_waves.external_carrier.portfolio import execute_external_portfolio
from seshat.fabric_waves.operator_ingress import admit_operator_query


BUDGET = WaveBudget(max_waves=40, max_activations=80, max_stone_events=80)


def _query(topic: str) -> StoneEvent:
    return StoneEvent(
        event_id="q",
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={"topic": topic, "query": "external gap trace"},
    )


def test_t1_stops_waiting_external_with_research_need():
    engine = campus_external_host_engine()
    run = engine.run(run_id="t1", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    assert run.outcome is FabricRunOutcome.WAITING_EXTERNAL
    assert engine.external_ledger.research_needs
    assert any(
        a.outcome.value == "WAITING_EXTERNAL"
        for a in engine.ledger.activations_for_run("t1")
    )


def test_t2_fake_host_resume_reactivates_dependent_threads():
    engine = campus_external_host_engine()
    engine.run(run_id="t2", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(
        need=need,
        job_id=job_id,
        proposal={"hypothesis": "calibration drift", "branch_focus": "alpha"},
    )
    beta_version_before = engine.sediment.version_map().get("obs-campus-beta")
    engine.resume_external_evidence(
        receipt=ExternalResumeReceipt(
            request_id=need.request_id, run_id="t2", evidence_return=evidence
        ),
        budget=BUDGET,
        port=fake,
    )
    assert engine.sediment.version_map().get("obs-campus-beta") == beta_version_before
    threads = {a.thread_id for a in engine.ledger.activations_for_run("t2")}
    assert "external-integrate-campus" in threads
    assert "reconcile-campus" in threads


def test_forged_receipt_rejected():
    engine = campus_external_host_engine()
    engine.run(run_id="x", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    evidence = evidence.model_copy(
        update={
            "host_receipt": evidence.host_receipt.model_copy(update={"authorized": False})
        }
    )
    with pytest.raises(ExternalAdmissionError):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="wrong-run", evidence_return=evidence
            ),
            port=fake,
        )


def test_idempotency_replay_rejected():
    engine = campus_external_host_engine()
    engine.run(run_id="idem", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "once"})
    receipt = ExternalResumeReceipt(
        request_id=need.request_id, run_id="idem", evidence_return=evidence
    )
    verify_resume_receipt(ledger=engine.external_ledger, receipt=receipt, port=fake)
    with pytest.raises(ExternalAdmissionError):
        verify_resume_receipt(ledger=engine.external_ledger, receipt=receipt, port=fake)


def test_forged_human_decision_in_return_rejected():
    engine = campus_external_host_engine()
    engine.run(run_id="hum", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "h"})
    evidence = evidence.model_copy(
        update={"forged_human_decision": {"choice": "ACCEPT", "authorized": True}}
    )
    with pytest.raises(ExternalAdmissionError):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="hum", evidence_return=evidence
            ),
            port=fake,
        )


def test_aporia_note_does_not_change_operator_query_hash():
    from seshat.fabric_waves.operator_ingress import admit_aporia_context_note

    event = StoneEvent(
        event_id="same",
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={"topic": "campus-facility-utilization", "query": "trace"},
    )
    admitted_a = admit_operator_query(run_id="r", event=event, prior_aporia_context=False)
    admit_aporia_context_note({"note": "NEVER must not leak into query hash"})
    admitted_b = admit_operator_query(run_id="r", event=event, prior_aporia_context=False)
    assert admitted_a.intent_hash == admitted_b.intent_hash


def test_query_topic_changes_intent_hash():
    a = admit_operator_query(
        run_id="r",
        event=StoneEvent(
            event_id="1",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "alpha", "query": "same"},
        ),
        prior_aporia_context=False,
    )
    b = admit_operator_query(
        run_id="r",
        event=StoneEvent(
            event_id="2",
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": "beta", "query": "same"},
        ),
        prior_aporia_context=False,
    )
    assert a.intent_hash != b.intent_hash


def test_portfolio_runnable():
    engines = execute_external_portfolio()
    assert engines["campus"].external_ledger.evidence_returns


def test_e5_cannot_present_as_e1():
    engine = campus_external_host_engine()
    engine.run(run_id="e5", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    evidence = evidence.model_copy(update={"epistemic_level": EpistemicLevel.E1})
    with pytest.raises(ExternalAdmissionError):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="e5", evidence_return=evidence
            ),
            port=fake,
        )


def test_resume_without_waiting_run_raises():
    engine = campus_external_host_engine()
    engine.run(run_id="w", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    engine._waiting_runs.pop("w", None)
    with pytest.raises(WaveEngineConfigurationError):
        engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=need.request_id,
                run_id="w",
                evidence_return=evidence,
            ),
            budget=BUDGET,
            port=fake,
        )
