"""I11 fictional vertical: two invented worlds, R03, batch replay, red probes.

All inputs are invented public fixtures. No private method bytes, paid model,
excluded historic case, or customer release is exercised here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashlib import sha256

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    AUTHORIAL_I11_SHA256,
    OBSERVED_I11_JOB_ID,
    ActionEvent,
    SourceAddress,
    activity_state_from_model_payload,
    collapse_probe_state,
    execute_fictional_i11,
    fictional_method_bytes,
    interpret_labeled_world,
    parse_page_map,
    validate_activity_network,
    world_bytes,
)
from seshat.fabric_waves.i11_vertical import (
    admit_model_run,
    admit_source,
    compose_private_i11_r03,
    fictional_corpus_selection,
    load_exclusion_policy,
    load_f07_permission,
    observe_existing_i11_package,
    run_fictional_vertical,
)
from seshat.fabric_waves.i11_activity_network import _claim_from_event
from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorInvocation,
    OperatorMethodBodyPin,
    OperatorRunLedger,
    OperatorSourcePin,
    invoke_operator_method_body,
)
from seshat.fabric_waves.operator_private_reports import compose_private_operator_r01r02


def _state(world: str = "world_a"):
    return interpret_labeled_world(
        world=world,
        source_bytes=world_bytes(world),
        method_bytes=fictional_method_bytes(),
    )


def test_two_invented_worlds_keep_distinct_networks():
    first = _state("world_a")
    second = _state("world_b")
    assert first.work_id != second.work_id
    layers_a = {event.layer for event in first.action_events}
    layers_b = {event.layer for event in second.action_events}
    assert "RP" in layers_a and "SS" in layers_a and "FT" in layers_a
    assert "PR" in layers_a and "BR" in layers_a
    assert "IM" in layers_b and "FT" in layers_b
    assert "supervisor-title-is-not-rp-labor" in first.explicit_non_equivalences
    assert "shared-opponent-is-not-shared-research-team" in second.explicit_non_equivalences
    validate_activity_network(first, world_bytes("world_a"))
    validate_activity_network(second, world_bytes("world_b"))


def test_fictional_interpreter_reads_pinned_method_bytes():
    source = world_bytes("world_a")
    invocation = OperatorInvocation(
        run_id="i11-a",
        job_id="local-a",
        source_id="public-invented-world_a",
        source_bytes=source,
        source_text=source.decode("utf-8"),
        method_body_id="seshat.i11.fictional_interpreter",
        method_body_version="v1",
        method_body_invocation_bytes=fictional_method_bytes(),
    )
    result = execute_fictional_i11(invocation)
    assert result.research_object_id == "invented-world_a"
    assert {claim.text.split(":", 1)[0] for claim in result.claims} >= {"RP", "SS", "FT", "PO"}
    with pytest.raises(ValueError, match="I11_METHOD_PIN_MISMATCH"):
        execute_fictional_i11(
            OperatorInvocation(
                run_id="i11-a",
                job_id="local-a",
                source_id="public-invented-world_a",
                source_bytes=source,
                source_text=source.decode("utf-8"),
                method_body_id="seshat.i11.fictional_interpreter",
                method_body_version="v1",
                method_body_invocation_bytes=b'{"schema":"nope"}',
            )
        )


def test_operator_batch_writes_and_replays_private_r01_r02_r03(tmp_path: Path):
    first = run_fictional_vertical(tmp_path)
    assert first["status"] == "EXECUTED_OR_RESUMED_SELF_OBSERVED"
    assert first["customer_release"] == "BLOCKED"
    assert first["indago"] == "NOT_LIVE"
    replay = run_fictional_vertical(tmp_path, verify_only=True)
    assert replay["manifest_sha256"] == first["manifest_sha256"]
    assert replay["r03_sha256"] == first["r03_sha256"]
    resumed = run_fictional_vertical(tmp_path)
    assert resumed["manifest_sha256"] == first["manifest_sha256"]
    r03 = json.loads((tmp_path / "private_r03.json").read_text(encoding="utf-8"))
    assert r03["report_id"] == "R03"
    assert r03["coverage"]["selected_works"] == 2
    assert r03["coverage"]["not_a_186_corpus"] is True
    assert r03["corpus_selection"]["membership"] == [
        "invented-world_a",
        "invented-world_b",
    ]
    assert r03["scientific_acceptance"] == "NOT_PERFORMED"


def test_cli_one_command_fictional_and_replay(tmp_path: Path):
    from seshat.fabric_waves.i11_vertical import main

    assert main(["--mode", "fictional", "--out", str(tmp_path / "batch")]) == 0
    assert main(["--mode", "fictional", "--out", str(tmp_path / "batch"), "--verify-only"]) == 0


def test_r03_refuses_identical_works():
    state = _state("world_a")
    selection = fictional_corpus_selection(world_bytes("world_a"), world_bytes("world_b"))
    with pytest.raises(ValueError, match="I11_R03_SAME_WORK"):
        compose_private_i11_r03(state, state, selection)


def test_denied_corpus_member_fails_closed():
    with pytest.raises(ValueError, match="I11_DENIED_SOURCE"):
        fictional_corpus_selection(
            world_bytes("world_a"),
            world_bytes("world_b"),
            denied=frozenset({"invented-world_b"}),
        )


def test_blocked_source_rights_without_bytes_or_grant():
    result = admit_source(
        source_id="1_DVSA1m-2bqq4sj3AIOYLdnIhUPV03rU",
        source_name="candidate.pdf",
        source_bytes=None,
        exclusion_policy={"excluded": {"source_drive_ids": [], "source_names": [], "aliases": []}},
        f07_full_read_granted=False,
    )
    assert result["status"] == "BLOCKED_SOURCE_RIGHTS"
    assert result["f07_full_read"] is False


def test_exclusion_policy_blocks_listed_id():
    with pytest.raises(ValueError, match="I11_SOURCE_EXCLUDED"):
        admit_source(
            source_id="private-excluded-id",
            source_bytes=b"public-invented",
            exclusion_policy={"excluded": {"source_drive_ids": ["private-excluded-id"],
                                          "source_names": [], "aliases": []}},
            f07_full_read_granted=True,
            invented_public=True,
        )


def test_model_admission_blocks_when_job_missing_and_refuses_new_paid_job():
    blocked = admit_model_run(job_id=None, stdout_bytes=None, method_bytes=None)
    assert blocked["status"] == "BLOCKED_MODEL_ADMISSION"
    assert blocked["indago"] == "NOT_LIVE"
    with pytest.raises(ValueError, match="I11_DUPLICATE_LAUNCH"):
        admit_model_run(
            job_id=None,
            stdout_bytes=None,
            method_bytes=None,
            submit_new_paid_job=True,
        )


def test_observed_job_requires_exact_method_and_job_pins():
    method = b"not-the-authorial-i11-body"
    with pytest.raises(ValueError, match="I11_METHOD_PIN_MISMATCH"):
        admit_model_run(
            job_id=OBSERVED_I11_JOB_ID,
            stdout_bytes=b"stdout",
            method_bytes=method,
            expected_method_sha256=AUTHORIAL_I11_SHA256,
        )
    realish = b"x" * 32
    with pytest.raises(ValueError, match="I11_DUPLICATE_LAUNCH"):
        admit_model_run(
            job_id="jx-ffffffffffff",
            stdout_bytes=realish,
            method_bytes=realish,
            expected_method_sha256=__import__("hashlib").sha256(realish).hexdigest(),
        )


@pytest.mark.parametrize(
    "code",
    [
        "I11_SUPERVISOR_NOT_RESEARCHER",
        "I11_STAFF_NOT_AUTHOR",
        "I11_PLANNED_NOT_ACTIVE",
        "I11_IMPLEMENTATION_NOT_EFFICACY",
        "I11_FALSE_SHARED_TEAM",
        "I11_UNKNOWN_OPERATOR_REQUIRED",
        "I11_CREDIT_NOT_RP",
    ],
)
def test_semantic_red_probes(code: str):
    state = collapse_probe_state(code=code)
    source = world_bytes("world_b" if "world_b" in state.work_id else "world_a")
    with pytest.raises(ValueError, match=code):
        validate_activity_network(state, source)


def test_forged_locator_and_partial_source_and_stale_report():
    state = _state("world_a")
    forged = list(state.action_events)
    address = forged[0].source_addresses[0]
    forged[0] = forged[0].model_copy(
        update={"source_addresses": (
            address.model_copy(update={"excerpt": "this excerpt is not in the source"}),
        )}
    )
    with pytest.raises(ValueError, match="I11_FORGED_LOCATOR"):
        validate_activity_network(state.model_copy(update={"action_events": tuple(forged)}), world_bytes("world_a"))
    with pytest.raises(ValueError, match="I11_PARTIAL_SOURCE"):
        validate_activity_network(state, b"")
    with pytest.raises(ValueError, match="I11_STALE_REPORT"):
        validate_activity_network(state, world_bytes("world_a"), expected_source_sha256="a" * 64)


def test_truncated_model_version_drift_denial_and_false_authority():
    state = _state("world_a")
    with pytest.raises(ValueError, match="I11_TRUNCATED_MODEL_OUTPUT"):
        validate_activity_network(state, world_bytes("world_a"), model_payload={"actors": []})
    with pytest.raises(ValueError, match="I11_VERSION_DRIFT"):
        interpret_labeled_world(
            world="world_a",
            source_bytes=world_bytes("world_a") + b"\nextra",
            method_bytes=fictional_method_bytes(),
        )
    with pytest.raises(ValueError, match="I11_DENIED_SOURCE"):
        validate_activity_network(
            state,
            world_bytes("world_a"),
            denied_source_ids=frozenset({"public-invented-world_a"}),
        )
    with pytest.raises(ValueError, match="I11_HUMAN_APPROVAL_FORBIDDEN"):
        validate_activity_network(state, world_bytes("world_a"), human_accepted=True)
    with pytest.raises(ValueError, match="I11_CUSTOMER_RELEASE_BLOCKED"):
        validate_activity_network(
            state, world_bytes("world_a"), customer_release_authorized=True
        )


def test_page_only_address_requires_page_map():
    state = _state("world_a")
    event = state.action_events[0]
    page_only = ActionEvent(
        event_id=event.event_id,
        actor_ids=event.actor_ids,
        verb=event.verb,
        affected_entities=event.affected_entities,
        layer=event.layer,
        source_addresses=(
            SourceAddress(carrier_id="public-invented-world_a", excerpt=event.source_addresses[0].excerpt, page=1),
        ),
        relation_mode=event.relation_mode,
    )
    with pytest.raises(ValueError, match="I11_PAGE_MAP_REQUIRED"):
        validate_activity_network(
            state.model_copy(update={"action_events": (page_only,) + state.action_events[1:]}),
            world_bytes("world_a"),
        )


def _authorizing_policy(**excluded: object) -> dict:
    payload = {
        "source_drive_ids": [],
        "source_names": [],
        "aliases": [],
        "source_sha256": [],
    }
    payload.update(excluded)
    return {
        "schema": "seshat.owner_source_exclusion.v1",
        "authority": "OWNER_EXPLICIT",
        "status": "PERMANENT_ACTIVE_EXCLUSION",
        "operator_supplied": True,
        "excluded": payload,
    }


def _permission(source_bytes: bytes, source_id: str = "invented-candidate") -> dict:
    return {
        "schema": "seshat.f07_per_operation_permission.v1",
        "permission_id": "test-perm-1",
        "operation_id": AUTHORIAL_I11_ID,
        "source_id": source_id,
        "source_sha256": sha256(source_bytes).hexdigest(),
        "rights_class": "FULL_REQUIRED",
        "grant": "OPERATOR_DECLARED_UNATTESTED",
        "independent_attestation": "NONE",
    }


def test_default_policy_never_authorizes_real_even_with_flag():
    result = admit_source(
        source_id="invented-candidate",
        source_bytes=b"public-invented-bytes",
        exclusion_policy=load_exclusion_policy(None),
        f07_full_read_granted=True,
    )
    assert result["status"] == "BLOCKED_SOURCE_RIGHTS"
    assert result["reason"] == "POLICY_MISSING"
    assert result["cli_flag_is_not_grant"] is True


def test_f07_flag_without_permission_is_not_a_grant():
    result = admit_source(
        source_id="invented-candidate",
        source_bytes=b"public-invented-bytes",
        exclusion_policy=_authorizing_policy(),
        f07_full_read_granted=True,
        f07_permission=None,
    )
    assert result["status"] == "BLOCKED_SOURCE_RIGHTS"
    assert result["reason"] == "F07_FLAG_IS_NOT_GRANT"
    assert result["cli_flag_is_not_grant"] is True


def test_prebyte_exclusion_does_not_need_source_bytes():
    with pytest.raises(ValueError, match="I11_SOURCE_EXCLUDED"):
        admit_source(
            source_id="private-excluded-id",
            source_bytes=None,
            exclusion_policy=_authorizing_policy(source_drive_ids=["private-excluded-id"]),
            f07_full_read_granted=True,
            f07_permission=_permission(b"unused"),
        )


def test_operator_policy_and_permission_admit_real_declared_bytes():
    source = b"public-invented-bytes"
    result = admit_source(
        source_id="invented-candidate",
        source_bytes=source,
        exclusion_policy=_authorizing_policy(),
        f07_full_read_granted=False,
        f07_permission=_permission(source),
    )
    assert result["status"] == "ADMITTED_OPERATOR_DECLARED_UNATTESTED"
    assert result["f07_full_read"] is False
    assert result["source_sha256"] == sha256(source).hexdigest()


def test_load_exclusion_policy_rejects_empty_schema(tmp_path: Path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"excluded": {"source_drive_ids": [], "source_names": [], "aliases": []}}), encoding="utf-8")
    with pytest.raises(ValueError, match="I11_EXCLUSION_POLICY_INVALID"):
        load_exclusion_policy(path)


def test_observe_without_policy_is_blocked_real_binding(tmp_path: Path):
    package = tmp_path / "pkg"
    package.mkdir()
    result = observe_existing_i11_package(
        package,
        exclusion_policy=load_exclusion_policy(None),
        f07_permission=None,
    )
    assert result["status"] == "BLOCKED_REAL_MODEL_BINDING"
    assert result["reason"] == "POLICY_OR_F07_PERMISSION_MISSING"


def test_pointer_without_hub_receipt_is_forged_job(tmp_path: Path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "model_run_pointer.json").write_text(
        json.dumps({"run_id": OBSERVED_I11_JOB_ID, "stdout_sha": "a" * 64, "source_sha": "b" * 64}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="I11_FORGED_JOB"):
        observe_existing_i11_package(
            package,
            exclusion_policy=_authorizing_policy(),
            f07_permission=_permission(b"x"),
            source_id="invented-candidate",
        )


def test_wrong_stdout_digest_is_version_drift():
    method = b"x" * 32
    with pytest.raises(ValueError, match="I11_VERSION_DRIFT"):
        admit_model_run(
            job_id=OBSERVED_I11_JOB_ID,
            stdout_bytes=b"not-the-pinned-stdout",
            method_bytes=method,
            expected_method_sha256=sha256(method).hexdigest(),
            expected_stdout_sha256=AUTHORIAL_I11_SHA256,
        )


def _model_payload_from_state(state) -> dict:
    return {
        "work_id": state.work_id,
        "methodbody_id": state.methodbody_id,
        "version": state.version,
        "input_carriers": [
            {
                "id": carrier.carrier_id,
                "version": carrier.version,
                "scope": carrier.scope,
                "rights": carrier.rights,
            }
            for carrier in state.input_carriers
        ],
        "actors": [
            {
                "id": actor.actor_id,
                "type": actor.actor_type,
                "work_scoped_identity": actor.work_scoped_identity,
                "source_addresses": [
                    {"page": 1, "quote": addr.excerpt, "section": "line"}
                    for addr in actor.source_addresses
                ],
                "unknowns": list(actor.unknowns),
            }
            for actor in state.actors
        ],
        "action_events": [
            {
                "id": event.event_id,
                "actor_ids": list(event.actor_ids),
                "verb": event.verb,
                "affected_entities": list(event.affected_entities),
                "layer": event.layer,
                "relation_mode": event.relation_mode,
                "time_or_unknown": event.time_or_unknown,
                "source_addresses": [
                    {"page": 1, "quote": addr.excerpt, "section": "line"}
                    for addr in event.source_addresses
                ],
            }
            for event in state.action_events
        ],
        "relations": [
            {
                "from": rel.from_id,
                "to": rel.to_id,
                "relation_type": rel.relation_type,
                "layer": rel.layer,
                "relation_mode": rel.relation_mode,
                "source_addresses": [
                    {"page": 1, "quote": addr.excerpt, "section": "line"}
                    for addr in rel.source_addresses
                ],
            }
            for rel in state.relations
        ],
        "bibliographic_outputs": [],
        "explicit_non_equivalences": list(state.explicit_non_equivalences),
        "unknown_roles": list(state.unknown_roles),
    }


def test_model_json_feeds_typed_state_and_private_report():
    source = world_bytes("world_a")
    original = _state("world_a")
    payload = _model_payload_from_state(original)
    bound = activity_state_from_model_payload(
        payload, source_bytes=source, page_map=parse_page_map(source)
    )
    assert bound.work_id == original.work_id
    assert bound.action_events[0].source_addresses[0].byte_offset is not None
    method_bytes = fictional_method_bytes()
    ledger = OperatorRunLedger()
    source_pin = OperatorSourcePin(
        source_id="public-invented-world_a",
        source_version="invented-v1",
        sha256=sha256(source).hexdigest(),
        rights_basis="operator-created-public-test-fixture",
        authorized_view="private-operator",
    )
    method_pin = OperatorMethodBodyPin(
        method_body_id="seshat.i11.fictional_interpreter",
        version="v1",
        invocation_body_sha256=sha256(method_bytes).hexdigest(),
    )

    def _from_model(invocation):
        return OperatorBodyResult(
            research_object_id=bound.work_id,
            claims=tuple(_claim_from_event(event) for event in bound.action_events),
            notes=("model-json-driven",),
        )

    receipt = invoke_operator_method_body(
        ledger=ledger,
        run_id="i11-model-json",
        job_id="local-model-json",
        source=source_pin,
        source_bytes=source,
        method=method_pin,
        method_body_invocation_bytes=method_bytes,
        method_callable=_from_model,
        requested_view="private-operator",
        declared_model_identity="deterministic-local-i11-interpreter-no-LLM",
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )
    preview = compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=source, method_invocation_bytes=method_bytes
    )
    verbs = {event.verb for event in bound.action_events}
    claim_texts = {claim["claim_text"].split(":", 1)[1] for claim in preview["reports"][0]["claims"]}
    assert verbs == claim_texts
    assert preview["scientific_acceptance"] == "NOT_PERFORMED"
    assert preview["customer_release"] == "BLOCKED"


def test_truncated_model_json_and_bad_page_fail_closed():
    source = world_bytes("world_a")
    payload = _model_payload_from_state(_state("world_a"))
    del payload["action_events"]
    with pytest.raises(ValueError, match="I11_TRUNCATED_MODEL_OUTPUT"):
        activity_state_from_model_payload(payload, source_bytes=source, page_map=parse_page_map(source))
    payload = _model_payload_from_state(_state("world_a"))
    payload["action_events"][0]["source_addresses"][0]["page"] = 99
    with pytest.raises(ValueError, match="I11_BAD_PAGE"):
        activity_state_from_model_payload(payload, source_bytes=source, page_map=parse_page_map(source))


def test_r03_labels_test_only_membership():
    selection = fictional_corpus_selection(world_bytes("world_a"), world_bytes("world_b"))
    r03 = compose_private_i11_r03(_state("world_a"), _state("world_b"), selection)
    assert r03["coverage"]["membership_kinds"]["invented-world_a"] == "TEST_ONLY_FICTIONAL"
    assert r03["coverage"]["not_a_186_corpus"] is True


def test_cli_observe_without_package_keeps_test_only_path(tmp_path: Path):
    from seshat.fabric_waves.i11_vertical import main

    assert main(["--mode", "observe-existing", "--out", str(tmp_path / "obs")]) == 0
    assert (tmp_path / "obs" / "test_only_fictional" / "private_r03.json").is_file()


def test_load_f07_permission_none_and_invalid(tmp_path: Path):
    assert load_f07_permission(None) is None
    path = tmp_path / "perm.json"
    path.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="I11_F07_PERMISSION_INVALID"):
        load_f07_permission(path)
