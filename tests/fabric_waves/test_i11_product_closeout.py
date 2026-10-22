"""Red mutants for PR87 source-bound scientific product closeout.

Public fixtures only. No owner-excluded names, private method bytes,
real paper body, or customer release are admitted here.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    CCBY_PAGES_SHA256,
    CCBY_PDF_SHA256,
    ActionEvent,
    Actor,
    activity_state_from_model_payload,
    fictional_method_bytes,
    interpret_labeled_world,
    parse_page_map,
    validate_activity_network,
    world_bytes,
)
from seshat.fabric_waves.i11_model_evidence import (
    AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED,
    assert_state_derived_from_stdout,
    extract_bounded_json_from_stdout,
)
from seshat.fabric_waves.i11_readable_reports import (
    compose_readable_r01r02,
    refuse_false_event_promotions,
)
from seshat.fabric_waves.i11_real_admission import (
    guard_real_source_pre_read,
    read_real_source_after_pre_read_guard,
)
from seshat.fabric_waves.i11_vertical import (
    _identity_excluded,
    admit_source,
    compose_private_i11_r03,
    fictional_corpus_selection,
    load_exclusion_policy,
    load_f07_permission,
    main,
)


def _policy(**excluded: object) -> dict:
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


def _ccby_permission(source_id: str = "plos-one-e0293107-ccby") -> dict:
    return {
        "schema": "seshat.f07_per_operation_permission.v1",
        "permission_id": "test-perm-ccby",
        "operation_id": AUTHORIAL_I11_ID,
        "source_id": source_id,
        "source_sha256": CCBY_PDF_SHA256,
        "pages_sha256": CCBY_PAGES_SHA256,
        "rights_class": "FULL_REQUIRED",
        "grant": "OPERATOR_DECLARED_UNATTESTED",
        "independent_attestation": "NONE",
    }


def _state(world: str = "world_a"):
    return interpret_labeled_world(
        world=world,
        source_bytes=world_bytes(world),
        method_bytes=fictional_method_bytes(),
    )


def _payload_from_state(state) -> dict:
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
                    {"page": addr.page or 1, "quote": addr.excerpt, "section": "line"}
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
                    {"page": addr.page or 1, "quote": addr.excerpt, "section": "line"}
                    for addr in rel.source_addresses
                ],
            }
            for rel in state.relations
        ],
    }


def _wrap_stdout(payload: dict) -> bytes:
    body = json.dumps(payload, ensure_ascii=False)
    return f"preamble\n```json\n{body}\n```\ntrailer\n".encode("utf-8")


def test_forged_owner_explicit_json_cannot_admit_swapped_bytes():
    with pytest.raises(ValueError, match="I11_SOURCE_NOT_PREDECLARED"):
        admit_source(
            source_id="swapped-claimant-id",
            source_name="swapped.pdf",
            source_bytes=b"not-the-predeclared-paper",
            exclusion_policy=_policy(),
            f07_full_read_granted=True,
            f07_permission={
                **_ccby_permission("swapped-claimant-id"),
                "source_sha256": sha256(b"not-the-predeclared-paper").hexdigest(),
            },
        )


def test_predeclared_permission_still_rejects_wrong_bytes():
    with pytest.raises(ValueError, match="I11_VERSION_DRIFT"):
        admit_source(
            source_id="plos-one-e0293107-ccby",
            source_bytes=b"not-the-predeclared-paper",
            exclusion_policy=_policy(),
            f07_full_read_granted=False,
            f07_permission=_ccby_permission(),
        )


def test_swapped_source_path_is_never_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    evil = tmp_path / "swapped.pdf"
    evil.write_bytes(b"do-not-open-me")
    opened: list[str] = []
    original = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self.name)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy()), encoding="utf-8")
    permission = tmp_path / "perm.json"
    permission.write_text(json.dumps(_ccby_permission()), encoding="utf-8")
    with pytest.raises(ValueError, match="I11_SOURCE_NOT_PREDECLARED"):
        main([
            "--mode", "admit-candidate",
            "--out", str(tmp_path / "out"),
            "--exclusion-policy", str(policy),
            "--f07-permission", str(permission),
            "--source-id", "plos-one-e0293107-ccby",
            "--source-file", str(evil),
        ])
    assert "swapped.pdf" not in opened


def test_pre_read_guard_blocks_alias_and_excluded_hash_before_open(tmp_path: Path):
    path = tmp_path / "open_source.pdf"
    path.write_bytes(b"unused")
    with pytest.raises(ValueError, match="I11_SOURCE_EXCLUDED"):
        guard_real_source_pre_read(
            source_id="plos-one-e0293107-ccby",
            source_name="open_source.pdf",
            source_path=path,
            exclusion_policy=_policy(aliases=["plos-one-e0293107-ccby"]),
            f07_permission=_ccby_permission(),
            identity_excluded=_identity_excluded,
        )
    with pytest.raises(ValueError, match="I11_SOURCE_EXCLUDED"):
        guard_real_source_pre_read(
            source_id="plos-one-e0293107-ccby",
            source_name="open_source.pdf",
            source_path=path,
            exclusion_policy=_policy(source_sha256=[CCBY_PDF_SHA256]),
            f07_permission=_ccby_permission(),
            identity_excluded=_identity_excluded,
        )
    assert path.read_bytes() == b"unused"


def test_read_after_guard_opens_only_predeclared_name(tmp_path: Path):
    path = tmp_path / "open_source.pdf"
    path.write_bytes(b"digest-only")
    with pytest.raises(ValueError, match="I11_SOURCE_NOT_PREDECLARED"):
        read_real_source_after_pre_read_guard(
            path=tmp_path / "other.pdf",
            source_id="plos-one-e0293107-ccby",
            source_name="other.pdf",
            exclusion_policy=_policy(),
            f07_permission=_ccby_permission(),
            identity_excluded=_identity_excluded,
        )
    raw = read_real_source_after_pre_read_guard(
        path=path,
        source_id="plos-one-e0293107-ccby",
        source_name="open_source.pdf",
        exclusion_policy=_policy(),
        f07_permission=_ccby_permission(),
        identity_excluded=_identity_excluded,
    )
    assert raw == b"digest-only"


def test_stdout_json_must_match_typed_file():
    payload = _payload_from_state(_state("world_a"))
    stdout = _wrap_stdout(payload)
    extracted = extract_bounded_json_from_stdout(stdout)
    proof = assert_state_derived_from_stdout(extracted, payload)
    assert proof["status"] == "AUTHENTIC_STDOUT_DERIVED"
    swapped = json.loads(json.dumps(payload))
    swapped["action_events"][0]["verb"] = "forged-semantic-verb"
    with pytest.raises(ValueError, match=AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED):
        assert_state_derived_from_stdout(extracted, swapped)


def test_typographic_patch_outside_page_one_is_rejected():
    payload = _payload_from_state(_state("world_a"))
    file_payload = json.loads(json.dumps(payload))
    file_payload["action_events"][0]["source_addresses"][0]["page"] = 2
    file_payload["action_events"][0]["source_addresses"][0]["quote"] = "glyph-fix"
    payload["action_events"][0]["source_addresses"][0]["page"] = 2
    derivative = {
        "action_events": [{
            "id": file_payload["action_events"][0]["id"],
            "source_addresses": [{"page": 2, "quote": "glyph-fix"}],
        }]
    }
    with pytest.raises(ValueError, match=AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED):
        assert_state_derived_from_stdout(payload, file_payload, typographic_derivative=derivative)


def test_four_witnessed_page_one_typography_patches_are_allowed():
    payload = _payload_from_state(_state("world_a"))
    file_payload = json.loads(json.dumps(payload))
    derivative_events = []
    for index in range(4):
        file_payload["action_events"][index]["source_addresses"][0]["page"] = 1
        file_payload["action_events"][index]["source_addresses"][0]["quote"] = f"p1-glyph-{index}"
        payload["action_events"][index]["source_addresses"][0]["page"] = 1
        derivative_events.append({
            "id": file_payload["action_events"][index]["id"],
            "source_addresses": [{"page": 1, "quote": f"p1-glyph-{index}"}],
        })
    proof = assert_state_derived_from_stdout(
        payload, file_payload, typographic_derivative={"action_events": derivative_events}
    )
    assert proof["typographic_p1_patches"] == 4
    extra = json.loads(json.dumps(file_payload))
    extra["action_events"][4]["source_addresses"][0]["page"] = 1
    extra["action_events"][4]["source_addresses"][0]["quote"] = "fifth-patch"
    payload["action_events"][4]["source_addresses"][0]["page"] = 1
    derivative_events.append({
        "id": extra["action_events"][4]["id"],
        "source_addresses": [{"page": 1, "quote": "fifth-patch"}],
    })
    with pytest.raises(ValueError, match=AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED):
        assert_state_derived_from_stdout(
            payload, extra, typographic_derivative={"action_events": derivative_events}
        )


def test_unwitnessed_page_one_quote_change_is_not_authentic():
    payload = _payload_from_state(_state("world_a"))
    file_payload = json.loads(json.dumps(payload))
    file_payload["action_events"][0]["source_addresses"][0]["quote"] = "silent-edit"
    with pytest.raises(ValueError, match=AUTHENTIC_MODEL_OUTPUT_NOT_DERIVED):
        assert_state_derived_from_stdout(payload, file_payload)


def test_readable_report_is_not_generic_rp_verb():
    state = _state("world_a")
    report = compose_readable_r01r02(
        state,
        job_id="local-fictional",
        stdout_sha256="a" * 64,
        source_sha256=sha256(world_bytes("world_a")).hexdigest(),
    )
    markdown = report["markdown"]
    assert "Research production (RP)" in markdown
    assert "Studied system (SS)" in markdown
    assert "Formal / institutional titles (FT)" in markdown
    assert "IM is empty/unknown" in markdown or report["im_status"] == "EMPTY_OR_UNKNOWN"
    assert "p." in markdown or "page UNKNOWN" in markdown
    assert "PROPOSAL_NOT_OPERATIONAL_ALLIANCE" in {
        mark for event in report["reports"][0]["events"] for mark in event["qualifications"]
    }
    assert "LISTED_FORMAL_ROLE_NOT_PERFORMED_RESEARCH_OPERATION" in {
        mark for event in report["reports"][0]["events"] for mark in event["qualifications"]
    }
    claim_only = {f"{event.layer}:{event.verb}" for event in state.action_events}
    assert markdown.strip() not in claim_only
    assert report["customer_release"] == "BLOCKED"
    assert report["scientific_acceptance"] == "NOT_PERFORMED"
    assert "SELF_OBSERVED_UNATTESTED" in markdown
    assert report["reports"][1]["next_tests"]


def test_editor_promotion_and_customer_state_fail_closed():
    state = _state("world_a")
    actors = {actor.actor_id: actor for actor in state.actors}
    editor = Actor(
        actor_id="ft-editor",
        actor_type="PERSON_EDITORIAL_ROLE",
        work_scoped_identity="listed editor",
        source_addresses=state.actors[0].source_addresses,
        unknowns=(),
    )
    actors["ft-editor"] = editor
    promoted = ActionEvent(
        event_id="E19",
        actor_ids=("ft-editor",),
        verb="handled the manuscript as journal Editor",
        affected_entities=("WORK",),
        layer="RP",
        source_addresses=state.action_events[0].source_addresses,
        relation_mode="SOURCE_ASSERTED_OPERATION",
    )
    with pytest.raises(ValueError, match="I11_EDITOR_PROMOTION"):
        refuse_false_event_promotions(promoted, actors)
    listed = promoted.model_copy(
        update={"layer": "FT", "relation_mode": "SOURCE_ASSERTED_FORMAL_ROLE"}
    )
    refuse_false_event_promotions(listed, actors)
    with pytest.raises(ValueError, match="I11_CUSTOMER_RELEASE_BLOCKED"):
        validate_activity_network(
            state, world_bytes("world_a"), customer_release_authorized=True
        )


def test_incomplete_page_range_is_rejected():
    pages = (
        "=== PRINTED PDF PAGE 1 / 3 ===\none\n"
        "=== PRINTED PDF PAGE 2 / 3 ===\ntwo\n"
    ).encode("utf-8")
    with pytest.raises(ValueError, match="I11_INCOMPLETE_PAGE_RANGE"):
        parse_page_map(pages)


def test_r03_stays_honest_test_only_without_second_original():
    selection = fictional_corpus_selection(world_bytes("world_a"), world_bytes("world_b"))
    r03 = compose_private_i11_r03(_state("world_a"), _state("world_b"), selection)
    assert r03["coverage"]["membership_kinds"]["invented-world_a"] == "TEST_ONLY_FICTIONAL"
    assert r03["coverage"]["membership_kinds"]["invented-world_b"] == "TEST_ONLY_FICTIONAL"
    assert r03["customer_release"] == "BLOCKED"


def test_redacted_exclusion_names_do_not_appear_in_admission_error(tmp_path: Path):
    secret = "owner-private-excluded-token-not-for-git"
    with pytest.raises(ValueError, match="I11_SOURCE_EXCLUDED") as err:
        admit_source(
            source_id=secret,
            source_bytes=None,
            exclusion_policy=_policy(source_drive_ids=[secret]),
            f07_full_read_granted=True,
            f07_permission=_ccby_permission(),
        )
    assert secret not in str(err.value)


def test_cli_observe_without_package_still_has_one_command(tmp_path: Path):
    assert main(["--mode", "observe-existing", "--out", str(tmp_path / "obs")]) == 0
    assert (tmp_path / "obs" / "test_only_fictional" / "private_r03.json").is_file()


def test_default_empty_policy_and_invalid_permission_remain_blocked(tmp_path: Path):
    assert load_exclusion_policy(None)["status"] == "DEFAULT_EMPTY"
    path = tmp_path / "perm.json"
    path.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="I11_F07_PERMISSION_INVALID"):
        load_f07_permission(path)


def test_model_payload_still_grounds_after_stdout_extract():
    source = world_bytes("world_a")
    payload = _payload_from_state(_state("world_a"))
    extracted = extract_bounded_json_from_stdout(_wrap_stdout(payload))
    bound = activity_state_from_model_payload(
        extracted, source_bytes=source, page_map=parse_page_map(source)
    )
    assert bound.work_id == "invented-world_a"
    assert bound.action_events[0].source_addresses[0].byte_offset is not None
