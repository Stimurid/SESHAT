"""Adversarial closure oracles. Execute only in authorized isolated CI."""
from copy import deepcopy
import json

import pytest

from seshat.contracts import AcceptanceState, RawAccessPolicy
from seshat.fabric_waves.contracts import (
    ActivationOutcome, EdgeCondition, EpistemicLevel, FabricRunOutcome,
    MethodBodyRef, StoneEvent, StoneEventKind, WaveBudget,
)
from seshat.fabric_waves.decision_gate import TrustedDecisionAttestation
from seshat.fabric_waves.engine import WaveEngineConfigurationError
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.ledger import LedgerConsistencyError, RunLedger
from seshat.fabric_waves.method_body import BodyResult
from seshat.fabric_waves.propagation import invalidate_cascade
from seshat.fabric_waves.scenarios import (
    bundle, corpus_engine, engine_for, output, repair_engine, revision_engine, source_store,
)
from seshat.fabric_waves.sediment import SedimentCollisionError, SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.fabric_waves.trace import render_html, render_svg

SECRET = "SYNTHETIC_SECRET_DO_NOT_PERSIST"
BUDGET = WaveBudget(max_waves=30, max_activations=40, max_stone_events=40)


def event(eid="event", **kwargs):
    return StoneEvent(event_id=eid, issued_at_tick=0, kind=kwargs.pop("kind", StoneEventKind.QUERY), **kwargs)


def rec(sid, *, reads=(), source=(), state=AcceptanceState.WORKING, version="1", payload=None):
    payload = {"value": sid} if payload is None else payload
    return SedimentRecord(sediment_id=sid, object_type="synthetic.state", version=version,
        research_object_id="synthetic", payload=payload, payload_hash=payload_hash(payload),
        provenance=("fixture",), read_dependencies=reads, source_carrier_refs=source,
        produced_by_thread="fixture", produced_at_tick=0, produced_in_wave=1,
        produced_by_stone_kind=StoneEventKind.QUERY, acceptance_state=state)


@pytest.mark.parametrize("policy", [RawAccessPolicy.FULL_REQUIRED, RawAccessPolicy.DRILLBACK])
def test_missing_store_denies_body_execution(policy):
    called = []
    spec, law, body = bundle("probe", lambda inv: called.append(inv) or BodyResult(), source="c")
    spec.raw_access_policy = policy
    engine = engine_for([(spec, law, body)])
    run = engine.run(run_id="r", budget=BUDGET, initial_stone=event(payload={"text": SECRET}))
    assert called == []
    assert run.outcome is FabricRunOutcome.BLOCKED
    assert engine.ledger.activations[0].outcome is ActivationOutcome.BLOCKED_SOURCE


def test_never_cannot_read_nested_event_raw_or_undeclared_sediment():
    observed = []
    engine = engine_for([bundle("probe", lambda inv: observed.append(inv.carried_payload) or BodyResult())])
    engine.sediment.deposit(rec("private", payload={"raw": SECRET}))
    engine.run(run_id="r", budget=BUDGET, initial_stone=event(payload={
        "text": SECRET, "values": [SECRET], "nested": {"stone_payload": {"raw": SECRET}}}))
    assert len(observed) == 1
    assert SECRET not in repr(observed)


@pytest.mark.parametrize("failure", ["missing-address", "wrong-carrier", "wrong-version", "unauthorized"])
def test_drillback_fail_closed(failure):
    src, content = carrier(carrier_id="c", version="1", text="abc" + SECRET)
    if failure == "unauthorized":
        content.authorized = False
    store = FabricCarrierStore(carriers={"c": src}, contents={"c": content})
    address = {"carrier_id": "c", "source_version": "1", "address_type": "byte_range", "start": 0, "end": 3}
    if failure == "wrong-carrier":
        address["carrier_id"] = "other"
    if failure == "wrong-version":
        address["source_version"] = "2"
    with pytest.raises(Exception):
        store.resolve_payload(policy=RawAccessPolicy.DRILLBACK, carrier_ids=("c",),
            stone_payload={} if failure == "missing-address" else {"drillback_address": address},
            operation_id="probe")


def test_target_carrier_not_admitted_even_if_store_has_it():
    called = []
    engine = engine_for([bundle("probe", lambda inv: called.append(inv) or BodyResult(), source="c")],
                        source_store({"c": "ok", "other": SECRET}))
    engine.run(run_id="r", budget=BUDGET, initial_stone=event(target_carrier_id="other"))
    assert called == []


def test_drillback_reads_only_pinned_permitted_span():
    store = source_store({"c": "abc" + SECRET})
    payload, manifest = store.resolve_payload(policy=RawAccessPolicy.DRILLBACK,
        carrier_ids=("c",), operation_id="probe", stone_payload={"text": SECRET,
            "drillback_address": {"carrier_id": "c", "source_version": "1",
                "address_type": "byte_range", "start": 0, "end": 3}})
    assert payload["text"] == "abc"
    assert SECRET not in repr(payload)
    assert manifest.receipts[-1].returned_byte_length == 3


@pytest.mark.parametrize("field,value", [("authorized", False), ("complete", False),
    ("content_sha256", "0" * 64), ("source_version", "wrong")])
def test_full_required_rejects_untrusted_incomplete_or_drifted_content(field, value):
    src, content = carrier(carrier_id="c", version="1", text=SECRET)
    content = content.model_copy(update={field: value})
    called = []
    engine = engine_for([bundle("probe", lambda inv: called.append(inv) or BodyResult(), source="c")],
        FabricCarrierStore(carriers={"c": src}, contents={"c": content}))
    engine.run(run_id="r", budget=BUDGET)
    assert called == []
    assert engine.ledger.activations[0].outcome is ActivationOutcome.BLOCKED_SOURCE


@pytest.mark.parametrize("mode", ["no-provider", "wrong-old", "wrong-bytes", "unauthorized", "incomplete", "bad-hash"])
def test_delta_cannot_manufacture_authorization(mode):
    old_src, old_content = carrier(carrier_id="c", version="1", text="old")
    new_src, new_content = carrier(carrier_id="c", version="2", text="new")
    if mode == "unauthorized":
        new_content.authorized = False
    if mode == "incomplete":
        new_content.complete = False
    if mode == "bad-hash":
        new_content.content_sha256 = "0" * 64
    store = FabricCarrierStore(carriers={"c": old_src}, contents={"c": old_content},
        revision_provider=None if mode == "no-provider" else lambda *args: (new_src, new_content))
    engine = engine_for([bundle("A", lambda inv: output(inv, {"value": 1}), source="c")], store)
    run = engine.run(run_id="r", budget=BUDGET, initial_stone=event(kind=StoneEventKind.SOURCE_DELTA,
        target_carrier_id="c", payload={"old_version": "bad" if mode == "wrong-old" else "1",
            "new_version": "2", "text": "forged" if mode == "wrong-bytes" else "new",
            "authorized": True, "complete": True}))
    assert run.outcome is FabricRunOutcome.BLOCKED
    assert not engine.ledger.activations
    assert store.carriers_for(("c",))[0].version == "1"
    assert all(e.kind is not StoneEventKind.QUERY for e in engine.ledger.events)


def decision_engine():
    engine = engine_for([])
    engine.sediment.deposit(rec("s"))
    att = TrustedDecisionAttestation(decision_id="d", subject_sediment_id="s", subject_version="1",
        choice="ACCEPT", issuer="external-human-idp", decided_by="human-17",
        decision_right="seshat:fabric:human-acceptance", nonce="nonce-1", attestation_token="opaque-signature")
    # Synthetic external verifier checks the entire authenticated envelope.
    engine.decision_verifier = lambda envelope: envelope == att
    return engine, att


@pytest.mark.parametrize("field,value", [("choice", "REJECT"), ("subject_version", "2"),
    ("subject_sediment_id", "other"), ("issuer", "forged"), ("decided_by", "admin"),
    ("decision_right", "admin"), ("nonce", "forged"), ("attestation_token", "forged")])
def test_decision_all_fields_bound_and_invalid_attempt_not_recorded(field, value):
    engine, att = decision_engine()
    forged = att.model_copy(update={field: value})
    with pytest.raises((SedimentCollisionError, WaveEngineConfigurationError)):
        engine.record_human_decision(run_id="r", decision_id="d", subject_sediment_id="s",
            choice="ACCEPT", rationale=SECRET, attestation=forged)
    assert not engine.ledger.decisions
    assert "s" in engine.sediment.views["working"]


def test_reject_is_rejected_and_nonce_cannot_replay():
    engine, att = decision_engine()
    att = att.model_copy(update={"choice": "REJECT"})
    engine.decision_verifier = lambda envelope: envelope == att
    engine.record_human_decision(run_id="r", decision_id="d", subject_sediment_id="s",
        choice="REJECT", rationale=SECRET, attestation=att)
    assert engine.sediment.all_records()[0].acceptance_state is AcceptanceState.REJECTED
    assert SECRET not in json.dumps(engine.ledger.serialize())
    with pytest.raises(WaveEngineConfigurationError):
        engine.record_human_decision(run_id="r", decision_id="d2", subject_sediment_id="s",
            choice="REJECT", rationale="", attestation=att.model_copy(update={"decision_id": "d2"}))


def test_no_default_verifier_and_valid_accept_positive_control():
    engine, att = decision_engine()
    verifier = engine.decision_verifier
    engine.decision_verifier = None
    with pytest.raises(SedimentCollisionError):
        engine.record_human_decision(run_id="r", decision_id="d", subject_sediment_id="s",
            choice="ACCEPT", rationale="", attestation=att)
    engine.decision_verifier = verifier
    engine.record_human_decision(run_id="r", decision_id="d", subject_sediment_id="s",
        choice="ACCEPT", rationale="", attestation=att)
    assert "s" in engine.sediment.views["accepted"]


def test_late_node_guard_evaluated_after_earlier_write():
    seen = []
    def body(inv):
        seen.append(inv.node_id)
        return output(inv, {"node": inv.node_id})
    spec, law, registered = bundle("thread", body)
    first = spec.nodes[0].model_copy(update={"node_id": "first", "produces_sediment_id": "first"})
    second = first.model_copy(update={"node_id": "second", "produces_sediment_id": "second",
        "consumes_sediment_ids": ("first",), "conditions": (EdgeCondition(requires_sediment_id="first"),)})
    spec.nodes = (first, second)
    engine = engine_for([(spec, law, registered)])
    engine.run(run_id="r", budget=BUDGET)
    assert seen == ["first", "second"]
    assert engine.sediment.views["working"].get("second").dependency_versions["first"]


def test_unchanged_first_output_does_not_silence_changed_later_node():
    value = [1]
    def producer(inv):
        return output(inv, {"value": 0 if inv.node_id == "first" else value[0]})
    spec, law, body = bundle("producer", producer)
    first = spec.nodes[0].model_copy(update={"node_id": "first", "produces_sediment_id": "first"})
    second = first.model_copy(update={"node_id": "second", "produces_sediment_id": "second"})
    spec.nodes = (first, second)
    def consumer(inv):
        return output(inv, inv.carried_payload["candidate_sediments"][0].payload)
    engine = engine_for([(spec, law, body), bundle("consumer", consumer, reads=("second",))])
    engine.run(run_id="r1", budget=BUDGET)
    value[0] = 2
    engine.run(run_id="r2", budget=BUDGET)
    assert engine.sediment.views["working"].get("consumer").payload == {"value": 2}
    assert any(e.parent_activation_id and ":second" in e.parent_activation_id
               for e in engine.ledger.events if e.run_id == "r2")


def test_two_outputs_one_activation_unchanged_a_changed_b_wakes_consumer():
    value = [1]
    def producer(inv):
        template = output(inv, {"value": 0}).produced_sediments[0]
        changed = {"value": value[0]}
        return BodyResult(produced_sediments=(
            template.model_copy(update={"sediment_id": "A"}),
            template.model_copy(update={"sediment_id": "B", "payload": changed,
                "payload_hash": payload_hash(changed), "version": payload_hash(changed)})))
    spec, law, body = bundle("producer", producer)
    spec.nodes = (spec.nodes[0].model_copy(update={"output_contracts": {
        "A": "synthetic.state", "B": "synthetic.state"}}),)
    engine = engine_for([(spec, law, body), bundle("consumer",
        lambda inv: output(inv, inv.carried_payload["candidate_sediments"][0].payload), reads=("B",))])
    engine.run(run_id="r1", budget=BUDGET)
    value[0] = 2
    engine.run(run_id="r2", budget=BUDGET)
    assert engine.sediment.views["working"].get("consumer").payload == {"value": 2}
    activation = engine.ledger.activations_for_run("r2")[0]
    assert activation.produced_sediment_ids == ("B",)
    assert any(e.parent_activation_id == activation.activation_id for e in engine.ledger.events
               if e.run_id == "r2")


def test_late_deposit_failure_is_atomic_and_opaque():
    def provider(inv):
        valid = output(inv, {"value": 1}).produced_sediments[0]
        bad_payload = {"private": SECRET}
        bad = valid.model_copy(update={"sediment_id": "second", "payload": bad_payload,
            "version": payload_hash(bad_payload), "payload_hash": payload_hash(bad_payload),
            "acceptance_state": AcceptanceState.ACCEPTED})
        return BodyResult(produced_sediments=(valid, bad))
    spec, law, body = bundle("first", provider)
    spec.nodes = (spec.nodes[0].model_copy(update={"output_contracts": {
        "first": "synthetic.state", "second": "synthetic.state"}}),)
    engine = engine_for([(spec, law, body)])
    engine.run(run_id="r", budget=BUDGET)
    assert not engine.sediment.all_records()
    assert engine.ledger.activations[0].error_code == "SEDIMENT_CONTRACT_VIOLATION"
    assert SECRET not in json.dumps(engine.ledger.serialize())


def test_bare_accept_string_has_no_authority():
    sediment = SedimentState()
    sediment.deposit(rec("s"))
    with pytest.raises(SedimentCollisionError):
        sediment.accept("s", decision_id="pretend-human", decided_at_tick=1)
    assert "s" in sediment.views["working"]


@pytest.mark.parametrize("direct_stale", [False, True])
def test_invalidation_crosses_stale_middle_and_preserves_unrelated(direct_stale):
    sediment = SedimentState()
    sediment.deposit(rec("A", source=("source",), state=AcceptanceState.STALE if direct_stale else AcceptanceState.WORKING))
    sediment.deposit(rec("B", reads=("A",), state=AcceptanceState.STALE))
    sediment.deposit(rec("C", reads=("B",)))
    sediment.deposit(rec("U"))
    invalidate_cascade(carrier_id="source", sediment=sediment)
    assert "C" in sediment.views["stale"]
    assert "U" in sediment.views["working"]
    assert sediment.history("C")[0].acceptance_state is AcceptanceState.WORKING


def test_new_derived_version_invalidates_only_descendants():
    sediment = SedimentState()
    for record in (rec("A"), rec("B", reads=("A",)), rec("C", reads=("B",)), rec("U")):
        sediment.deposit(record)
    sediment.deposit(rec("A", version="2", payload={"new": True}))
    assert {r.sediment_id for r in sediment.views["stale"].values()} == {"B", "C"}
    assert len(sediment.history("A")) == 2


def test_event_budget_counts_consumption_once_and_fresh_run_resets():
    engine = engine_for([bundle("A", lambda inv: output(inv, {"value": 1}))])
    budget = WaveBudget(max_waves=4, max_activations=4, max_stone_events=2)
    first = engine.run(run_id="r1", budget=budget)
    assert len([e for e in engine.ledger.events if e.run_id == "r1"]) == 2
    assert first.outcome is FabricRunOutcome.CONVERGED
    second = engine.run(run_id="r2", budget=budget)
    assert second.activations_total == 1
    assert second.outcome is FabricRunOutcome.SATURATED


def test_two_node_global_budget_one_executes_one_body():
    seen = []
    spec, law, body = bundle("A", lambda inv: seen.append(inv.node_id) or BodyResult())
    spec.nodes += (spec.nodes[0].model_copy(update={"node_id": "second", "produces_sediment_id": "second"}),)
    engine = engine_for([(spec, law, body)])
    run = engine.run(run_id="r", budget=WaveBudget(max_waves=5, max_activations=1, max_stone_events=5))
    assert len(seen) == run.activations_total == 1
    assert run.outcome is FabricRunOutcome.EXHAUSTED


def test_thread_budget_stops_before_second_node_and_resets_next_run():
    seen = []
    spec, law, body = bundle("A", lambda inv: seen.append(inv.node_id) or BodyResult())
    spec.bounded_budget_hint = 1
    spec.nodes += (spec.nodes[0].model_copy(update={"node_id": "second", "produces_sediment_id": "second"}),)
    engine = engine_for([(spec, law, body)])
    for run_id in ("one", "two"):
        run = engine.run(run_id=run_id, budget=BUDGET)
        assert run.outcome is FabricRunOutcome.EXHAUSTED
    assert seen == ["compute", "compute"]


def test_changing_self_loop_is_bounded_not_saturated():
    counter = [0]
    def provider(inv):
        counter[0] += 1
        return output(inv, {"counter": counter[0]})
    spec, law, body = bundle("loop", provider,
        kinds=(StoneEventKind.QUERY, StoneEventKind.SEDIMENT_AVAILABLE))
    spec.bounded_budget_hint = 3
    engine = engine_for([(spec, law, body)])
    run = engine.run(run_id="r", budget=BUDGET)
    assert counter[0] == 3
    assert run.outcome is FabricRunOutcome.EXHAUSTED


@pytest.mark.parametrize("mode", ["unknown-ref", "unsupported-operation", "wrong-id", "wrong-type", "wrong-hash", "wrong-method", "wrong-version"])
def test_method_and_output_contract_fail_closed(mode):
    seen = []
    def provider(inv):
        seen.append(True)
        record = output(inv, {"value": 2}).produced_sediments[0]
        changes = {"wrong-id": {"sediment_id": "other"}, "wrong-type": {"object_type": "other"},
            "wrong-hash": {"payload_hash": "0" * 64}, "wrong-method": {"method_body_refs": ()},
            "wrong-version": {"version": "1"}}.get(mode, {})
        return BodyResult(produced_sediments=(record.model_copy(update=changes),))
    spec, law, body = bundle("A", provider)
    if mode == "unknown-ref":
        spec.nodes = (spec.nodes[0].model_copy(update={"method_body_ref": MethodBodyRef(method_body_id="missing", version="1")}),)
    engine = engine_for([(spec, law, body)])
    if mode == "unsupported-operation":
        spec.nodes = (spec.nodes[0].model_copy(update={"operation_id": "not-registered"}),)
    if mode == "wrong-version":
        engine.sediment.deposit(rec("A", version="1"))
    engine.run(run_id="r", budget=BUDGET)
    assert engine.ledger.activations[0].outcome in (ActivationOutcome.ERROR, ActivationOutcome.BLOCKED_PROVIDER)
    if mode in ("unknown-ref", "unsupported-operation"):
        assert not seen


@pytest.mark.parametrize("mode", ["raise", "aporia", "deposit", "serializer", "invalid-result"])
def test_secret_never_persists_in_error_surfaces(mode, capsys):
    def provider(inv):
        print(SECRET)
        if mode == "raise":
            raise RuntimeError(SECRET)
        if mode == "aporia":
            return BodyResult(aporia=SECRET)
        if mode == "invalid-result":
            return {"private": SECRET}
        record = output(inv, {"value": 2}).produced_sediments[0]
        if mode == "serializer":
            return BodyResult(produced_sediments=(record.model_copy(update={"version": {"private": SECRET}}),))
        return BodyResult(produced_sediments=(record.model_copy(update={"object_type": SECRET}),))
    engine = engine_for([bundle("A", provider)])
    run = engine.run(run_id="r", budget=BUDGET)
    blob = json.dumps(engine.ledger.serialize()) + repr(engine.sediment.all_records())
    blob += render_html(run_record=run, ledger=engine.ledger, sediment=engine.sediment,
                        resonances=engine.resonance_composer)
    blob += render_svg(run_record=run, ledger=engine.ledger)
    captured = capsys.readouterr()
    assert SECRET not in blob + captured.out + captured.err


@pytest.mark.parametrize("tamper", ["edit", "reorder", "remove-interior", "remove-tail", "head", "order"])
def test_ledger_verifies_complete_chain_and_head(tamper):
    engine = corpus_engine()
    engine.run(run_id="r", budget=BUDGET)
    ledger = deepcopy(engine.ledger)
    trusted_head = ledger.head_hash
    ledger.verify(expected_head=trusted_head)
    if tamper == "edit":
        ledger._events[0] = ledger._events[0].model_copy(update={"payload_hash": "0" * 64})
    elif tamper == "reorder":
        ledger._events.reverse()
    elif tamper == "remove-interior":
        ledger._events.pop(1)
    elif tamper == "remove-tail":
        ledger._runs.pop()
    elif tamper == "head":
        ledger._chain_head = "0" * 64
    else:
        ledger._order.reverse()
    with pytest.raises(LedgerConsistencyError):
        ledger.verify(expected_head=trusted_head)


@pytest.mark.parametrize("tamper", ["edit", "reorder", "remove-interior", "remove-tail", "head"])
def test_persisted_ledger_requires_external_checkpoint(tamper):
    engine = corpus_engine()
    engine.run(run_id="r", budget=BUDGET)
    data = json.loads(json.dumps(engine.ledger.serialize()))
    checkpoint = engine.ledger.head_hash
    RunLedger.verify_serialized(data, expected_head=checkpoint)
    if tamper == "edit":
        data["events"][0]["payload_hash"] = "0" * 64
    elif tamper == "reorder":
        data["events"].reverse()
    elif tamper == "remove-interior":
        data["events"].pop(1)
    elif tamper == "remove-tail":
        data["runs"].pop()
        data["append_order"].pop()
    else:
        data["head_hash"] = "0" * 64
    with pytest.raises(LedgerConsistencyError):
        RunLedger.verify_serialized(data, expected_head=checkpoint)


def test_e1_requires_actual_access_and_e5_stays_proposal():
    for level, expected in ((EpistemicLevel.E1, AcceptanceState.WORKING), (EpistemicLevel.E5, AcceptanceState.PROPOSED)):
        def provider(inv):
            record = output(inv, {"value": 1}).produced_sediments[0]
            return BodyResult(produced_sediments=(record.model_copy(update={"epistemic_level": level}),))
        engine = engine_for([bundle("A", provider, source="c")], source_store({"c": "source"}))
        engine.run(run_id="r", budget=BUDGET)
        record = engine.sediment.all_records()[0]
        assert record.epistemic_level is level
        assert record.acceptance_state is expected
        assert record.source_access_manifest.receipts


def test_forged_source_refs_cannot_create_e1_and_e5_cannot_be_accepted():
    def provider(inv):
        record = output(inv, {"value": 1}).produced_sediments[0]
        return BodyResult(produced_sediments=(record.model_copy(update={
            "epistemic_level": EpistemicLevel.E1, "source_carrier_refs": ("pretend",)}),))
    engine = engine_for([bundle("A", provider)])
    engine.run(run_id="r", budget=BUDGET)
    record = engine.sediment.all_records()[0]
    assert record.epistemic_level is not EpistemicLevel.E1
    assert not record.source_carrier_refs
    engine, att = decision_engine()
    engine.sediment.deposit(rec("s").model_copy(update={"epistemic_level": EpistemicLevel.E5}))
    with pytest.raises(SedimentCollisionError):
        engine.record_human_decision(run_id="r", decision_id="d", subject_sediment_id="s",
            choice="ACCEPT", rationale="", attestation=att)
    assert not engine.ledger.decisions


def test_d1_feedback_ends_in_legitimate_unresolved_aporia():
    engine = repair_engine()
    run = engine.run(run_id="r", budget=BUDGET)
    assert [a.thread_id for a in engine.ledger.activations] == ["object", "method-critic", "object-repair"]
    assert run.outcome is FabricRunOutcome.APORIA
    assert len([e for e in engine.ledger.events if e.parent_activation_id]) == 2


def test_d2_selection_is_pinned_and_registration_order_independent():
    results = []
    for reverse in (False, True):
        engine = corpus_engine(reverse=reverse)
        engine.sediment.deposit(rec("similar-but-unselected", payload={"count": 1000}))
        engine.run(run_id="r", budget=BUDGET)
        aggregate = engine.sediment.views["working"].get("aggregate")
        assert aggregate.payload["count"] == 8
        assert set(aggregate.payload["cached_refs"]) == {"study-a", "study-b"}
        assert aggregate.payload["selection"]["version"] == "1"
        for study in ("study-a", "study-b"):
            assert len(engine.ledger.activations_for_thread(study)) == 1
        results.append(aggregate.payload)
    assert results[0] == results[1]


def test_d3_only_affected_react_and_initial_snapshot_cannot_time_travel(tmp_path):
    from seshat.fabric_waves.demo import ScenarioResult, render_result
    engine = revision_engine()
    first = engine.run(run_id="initial", budget=BUDGET)
    result = ScenarioResult("s3", (first,), (engine,))
    render_result(result, tmp_path)
    initial_files = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    final = engine.run(run_id="revision", budget=BUDGET, initial_stone=event("delta",
        kind=StoneEventKind.SOURCE_DELTA, target_carrier_id="source-a",
        payload={"old_version": "1", "new_version": "2", "text": "revised synthetic source"}))
    assert {a.thread_id for a in engine.ledger.activations_for_run("revision")} == {"A", "B", "C"}
    assert final.resonance_ids
    assert first.sediment_final_versions["U"] == final.sediment_final_versions["U"]
    assert any(r.acceptance_state is AcceptanceState.STALE for r in engine.sediment.history("C"))
    render_result(result, tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == initial_files
