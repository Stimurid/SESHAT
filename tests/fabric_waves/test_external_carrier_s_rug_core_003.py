"""S-RUG-CORE-003 Phase A: external worker carrier negative and demo gates."""

import json

import pytest

from seshat.fabric_waves.contracts import FabricRunOutcome, MethodBodyRef, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngineConfigurationError
from seshat.fabric_waves.external_carrier.contracts import (
    EpistemicLevel,
    ExternalResumeReceipt,
)
from seshat.fabric_waves.external_carrier.fake_host import FakeHostExecutor
from seshat.fabric_waves.external_carrier.hosts import campus_external_host_engine
from seshat.fabric_waves.external_carrier.ledger import compute_host_binding_hash
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


def test_unissued_job_with_empty_host_registry_rejected():
    engine = campus_external_host_engine()
    engine.run(run_id="unissued", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    forged_job = evidence.host_receipt.host_job.model_copy(
        update={"job_id": "UNISSUED_EXTERNAL_JOB"}
    )
    forged_binding = compute_host_binding_hash(
        request=need,
        host_job=forged_job,
        worker_ref=need.worker_ref,
    )
    evidence = evidence.model_copy(
        update={
            "host_receipt": evidence.host_receipt.model_copy(
                update={
                    "host_job": forged_job,
                    "binding_hash": forged_binding,
                }
            )
        }
    )
    with pytest.raises(ExternalAdmissionError, match="UNKNOWN_JOB_ID"):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="unissued", evidence_return=evidence
            ),
            port=fake,
        )


def test_port_absent_fails_closed():
    engine = campus_external_host_engine()
    engine.run(run_id="noport", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    with pytest.raises(ExternalAdmissionError, match="EXECUTOR_PORT_REQUIRED"):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="noport", evidence_return=evidence
            ),
            port=None,
        )


def test_research_need_pins_source_versions():
    engine = campus_external_host_engine()
    engine.run(run_id="pins", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    assert need.source_carrier_ids
    assert need.source_versions
    assert all(cid in need.source_versions for cid in need.source_carrier_ids)


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


def test_ledger_source_pin_tamper_after_dispatch_denied():
    engine = campus_external_host_engine()
    engine.run(run_id="tamper", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    engine.external_ledger.research_needs[-1] = need.model_copy(
        update={"source_versions": {"campus-branch-alpha": "FORGED-LATER-VERSION"}}
    )
    tampered_need = engine.external_ledger.research_needs[-1]
    forged_binding = compute_host_binding_hash(
        request=tampered_need,
        host_job=evidence.host_receipt.host_job,
        worker_ref=tampered_need.worker_ref,
    )
    evidence = evidence.model_copy(
        update={
            "host_receipt": evidence.host_receipt.model_copy(
                update={"binding_hash": forged_binding}
            )
        }
    )
    with pytest.raises(ExternalAdmissionError, match="LEDGER_DISPATCH_PIN_MISMATCH"):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="tamper", evidence_return=evidence
            ),
            port=fake,
        )


def test_method_pin_tamper_after_dispatch_denied():
    engine = campus_external_host_engine()
    engine.run(run_id="mtamper", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    forged_method = MethodBodyRef(method_body_id="synthetic.external", version="FORGED-LATER")
    engine.external_ledger.research_needs[-1] = need.model_copy(update={"method_body_ref": forged_method})
    tampered_need = engine.external_ledger.research_needs[-1]
    forged_binding = compute_host_binding_hash(
        request=tampered_need,
        host_job=evidence.host_receipt.host_job,
        worker_ref=tampered_need.worker_ref,
    )
    evidence = evidence.model_copy(
        update={
            "host_receipt": evidence.host_receipt.model_copy(
                update={"binding_hash": forged_binding}
            )
        }
    )
    with pytest.raises(ExternalAdmissionError, match="LEDGER_DISPATCH_PIN_MISMATCH"):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="mtamper", evidence_return=evidence
            ),
            port=fake,
        )


def test_e5_extra_source_claim_denied():
    engine = campus_external_host_engine()
    engine.run(run_id="scope", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    evidence = evidence.model_copy(
        update={"source_claim_refs": (*need.source_carrier_ids, "UNAUTHORIZED-OTHER-CARRIER")}
    )
    with pytest.raises(ExternalAdmissionError, match="E5_SOURCE_CLAIM_OUTSIDE_REQUEST_SCOPE"):
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="scope", evidence_return=evidence
            ),
            port=fake,
        )


def test_active_wait_rejects_stale_request_id():
    engine = campus_external_host_engine()
    engine.run(run_id="active", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    engine._waiting_runs["active"].request_id = "rn:other-active-need"
    with pytest.raises(WaveEngineConfigurationError, match="ACTIVE_WAIT_REQUEST_MISMATCH"):
        engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="active", evidence_return=evidence
            ),
            budget=BUDGET,
            port=fake,
        )


def test_source_delta_during_wait_fails_closed():
    engine = campus_external_host_engine()
    engine.run(run_id="delta-wait", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    need = engine.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal={"hypothesis": "x"})
    carrier_id = "campus-branch-alpha"
    assert carrier_id in need.source_carrier_ids
    pinned = need.source_versions[carrier_id]
    engine.carrier_store.apply_delta(
        carrier_id,
        old_version=pinned,
        new_version="2",
        new_text="revised lab telemetry: utilization index 79%",
    )
    with pytest.raises(WaveEngineConfigurationError, match="SOURCE_VERSION_STALE"):
        engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=need.request_id, run_id="delta-wait", evidence_return=evidence
            ),
            budget=BUDGET,
            port=fake,
        )


def test_wait_checkpoint_roundtrip(tmp_path):
    from seshat.fabric_waves.external_carrier.wait_checkpoint import (
        ExternalWaitCheckpoint,
        load_wait_checkpoint,
        write_wait_checkpoint,
    )

    engine = campus_external_host_engine()
    engine.run(run_id="chk", budget=BUDGET, initial_stone=_query("campus-facility-utilization"))
    wait = engine._waiting_runs["chk"]
    checkpoint = ExternalWaitCheckpoint.build(
        run_id="chk",
        request_id=wait.request_id,
        dispatch_snapshot=wait.dispatch_snapshot,
        ledger=engine.external_ledger,
    )
    path = tmp_path / "wait_checkpoint.json"
    write_wait_checkpoint(path, checkpoint)
    restored = load_wait_checkpoint(path)
    assert restored.request_id == wait.request_id
    assert restored.ledger.research_needs[0].request_id == wait.request_id


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
