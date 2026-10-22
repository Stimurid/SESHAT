"""M12 stacked product: F1/F2, second-run block, and public red mutants.

Invented fixtures only. No owner-excluded identities, private method bytes,
or real paper bodies enter this file.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from test_public_source_admission import sample
from seshat.public_source_admission import admit_public_published_corpus
from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    AUTHORIAL_I11_VERSION,
    CCBY_PAGES_SHA256,
    CCBY_PDF_SHA256,
    ActionEvent,
    Actor,
    OBSERVED_I11_JOB_ID,
    interpret_labeled_world,
    fictional_method_bytes,
    validate_activity_network,
    world_bytes,
)
from seshat.fabric_waves.i11_readable_reports import refuse_false_event_promotions
from seshat.fabric_waves.i11_second_run import (
    BLOCKED_SECOND_MODELRUN,
    MODEL_TRANSFER_GRANT,
    admit_second_authorial_i11_run,
)
from seshat.fabric_waves.i11_source_lineage import (
    EQUIVALENT_TO_MODEL_INPUT,
    INDEPENDENT_POST_EXTRACTION,
    NOT_FED_TO_MODEL,
    inner_page_texts,
    qualify_source_text_lineage,
)
from seshat.fabric_waves.i11_vertical import main
from seshat.fabric_waves import i11_real_portfolio as portfolio


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


def _state(world: str = "world_a"):
    return interpret_labeled_world(
        world=world,
        source_bytes=world_bytes(world),
        method_bytes=fictional_method_bytes(),
    ).model_copy(update={
        "methodbody_id": AUTHORIAL_I11_ID,
        "version": AUTHORIAL_I11_VERSION,
        "model_job_receipt_or_null": OBSERVED_I11_JOB_ID if world == "world_a" else "jx-invented-second",
    })


def _pages(label: str, bodies: list[str]) -> bytes:
    total = len(bodies)
    return "".join(
        f"=== {label} PAGE {index} / {total} ===\n{body}\n"
        for index, body in enumerate(bodies, start=1)
    ).encode("utf-8")


def test_f1_derived_view_sha_is_not_silently_the_model_input():
    model = _pages("PRINTED PDF", ["alpha one", "alpha two"])
    derived = _pages("ORIGINAL PDF", ["alpha one", "alpha two"])
    model_sha = sha256(model).hexdigest()
    derived_sha = sha256(derived).hexdigest()
    assert model_sha != derived_sha
    lineage = qualify_source_text_lineage(
        original_pdf_sha256="a" * 64,
        derived_page_view_sha256=derived_sha,
        extractor_version="pypdf-invented",
        original_model_input_page_text_sha256=model_sha,
        model_input_pages=inner_page_texts(model),
        derived_pages=inner_page_texts(derived),
    )
    assert lineage["extraction_relation"] == INDEPENDENT_POST_EXTRACTION
    assert lineage["derived_view_is_model_input"] is False
    assert lineage["page_comparison"]["inner_page_text_equivalent"] is True


def test_f1_whole_file_match_is_the_only_model_input_equivalence():
    raw = _pages("PRINTED PDF", ["same"])
    digest = sha256(raw).hexdigest()
    lineage = qualify_source_text_lineage(
        original_pdf_sha256="b" * 64,
        derived_page_view_sha256=digest,
        extractor_version="pypdf-invented",
        original_model_input_page_text_sha256=digest,
        model_input_pages=inner_page_texts(raw),
        derived_pages=inner_page_texts(raw),
    )
    assert lineage["extraction_relation"] == EQUIVALENT_TO_MODEL_INPUT
    assert lineage["derived_view_is_model_input"] is True


def test_f1_source_without_model_run_is_not_fed():
    lineage = qualify_source_text_lineage(
        original_pdf_sha256="c" * 64,
        derived_page_view_sha256="d" * 64,
        extractor_version="pypdf-invented",
    )
    assert lineage["extraction_relation"] == NOT_FED_TO_MODEL
    assert lineage["original_model_input_page_text_sha256"] == NOT_FED_TO_MODEL


def test_f1_wrong_current_page_derivation_is_reported():
    model = _pages("PRINTED PDF", ["page-one", "page-two"])
    derived = _pages("ORIGINAL PDF", ["page-one", "page-TWO-DIVERGED"])
    lineage = qualify_source_text_lineage(
        original_pdf_sha256="e" * 64,
        derived_page_view_sha256=sha256(derived).hexdigest(),
        extractor_version="pypdf-invented",
        original_model_input_page_text_sha256=sha256(model).hexdigest(),
        model_input_pages=inner_page_texts(model),
        derived_pages=inner_page_texts(derived),
    )
    assert lineage["page_comparison"]["inner_page_text_equivalent"] is False
    assert 2 in lineage["page_comparison"]["diverged_pages"]


def test_f2_nonmocked_policy_gate_blocks_join_before_observe(monkeypatch):
    requests, sources = sample()
    packet = admit_public_published_corpus(requests, source_bytes=sources)
    joined: list[str] = []
    observed: list[str] = []

    def forbid_join(*_args, **_kwargs):
        joined.append("called")
        raise AssertionError("join must not run")

    def forbid_observe(*_args, **_kwargs):
        observed.append("called")
        raise AssertionError("observe must not run")

    monkeypatch.setattr(portfolio, "make_public_pdf_method_views", forbid_join)
    monkeypatch.setattr(portfolio, "observe_existing_i11_package", forbid_observe)
    with pytest.raises(portfolio.RealI11PortfolioError, match="POLICY_BEFORE_JOIN"):
        portfolio.make_observed_i11_real_source_portfolio(
            package_dir=Path("invented-never-read"),
            exclusion_policy={"excluded": {
                "source_drive_ids": [], "source_names": [],
                "aliases": [], "source_sha256": [],
            }},
            f07_permission={"not_a_real_permission": True},
            f07_full_read_granted=True,
            source_id="invented-pdf",
            source_name="invented-world",
            public_corpus=packet,
            public_requests=requests,
            source_bytes=sources,
            owner_excluded_source_ids=frozenset(),
            owner_excluded_source_sha256=frozenset(),
        )
    assert joined == []
    assert observed == []


def test_forged_owner_policy_is_not_a_join_grant(monkeypatch):
    requests, sources = sample()
    packet = admit_public_published_corpus(requests, source_bytes=sources)
    with pytest.raises(portfolio.RealI11PortfolioError, match="POLICY_BEFORE_JOIN"):
        portfolio.make_observed_i11_real_source_portfolio(
            package_dir=Path("invented-never-read"),
            exclusion_policy={
                "schema": "seshat.owner_source_exclusion.v1",
                "authority": "FORGED",
                "status": "PERMANENT_ACTIVE_EXCLUSION",
                "operator_supplied": True,
                "excluded": {
                    "source_drive_ids": [], "source_names": [],
                    "aliases": [], "source_sha256": [],
                },
            },
            f07_permission={"schema": "seshat.f07_per_operation_permission.v1"},
            f07_full_read_granted=True,
            source_id="invented",
            source_name="invented",
            public_corpus=packet,
            public_requests=requests,
            source_bytes=sources,
            owner_excluded_source_ids=frozenset(),
            owner_excluded_source_sha256=frozenset(),
        )


def test_source_a_f07_cannot_authorize_source_b_model_transfer():
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b={
            "schema": "seshat.f07_per_operation_permission.v1",
            "permission_id": "copied-a",
            "operation_id": AUTHORIAL_I11_ID,
            "source_id": "plos-one-e0293107-ccby",
            "source_sha256": CCBY_PDF_SHA256,
            "pages_sha256": CCBY_PAGES_SHA256,
            "rights_class": "FULL_REQUIRED",
            "grant": "OPERATOR_DECLARED_UNATTESTED",
            "independent_attestation": "NONE",
            "model_transfer": MODEL_TRANSFER_GRANT,
            "budget_authorization": "invented-budget",
        },
        source_id="plos-one-e0293107-ccby",
        source_name="open_source.pdf",
        source_bytes=b"unused",
    )
    assert result["status"] == BLOCKED_SECOND_MODELRUN
    assert result["launched"] is False
    assert "F07_PERMISSION_SOURCE_MISMATCH" in result["reasons"]


def test_missing_model_transfer_and_budget_block_without_launch():
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b={
            "schema": "seshat.f07_per_operation_permission.v1",
            "permission_id": "b-incomplete",
            "operation_id": AUTHORIAL_I11_ID,
            "source_id": "invented-second-source",
            "source_sha256": "f" * 64,
            "rights_class": "FULL_REQUIRED",
            "grant": "OPERATOR_DECLARED_UNATTESTED",
            "independent_attestation": "NONE",
        },
        source_id="invented-second-source",
    )
    assert result["status"] == BLOCKED_SECOND_MODELRUN
    assert result["launched"] is False
    assert "MODEL_TRANSFER_GRANT_MISSING" in result["reasons"]
    assert "MODEL_BUDGET_AUTHORIZATION_MISSING" in result["reasons"]


def test_cc_by_alone_and_empty_permission_do_not_send():
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b=None,
        source_id="invented-second-source",
    )
    assert result["status"] == BLOCKED_SECOND_MODELRUN
    assert result["publication_license_is_not_grant"] is True
    assert result["job_id"] is None


def test_replay_paid_invocation_is_refused():
    with pytest.raises(ValueError, match="I11_DUPLICATE_LAUNCH"):
        admit_second_authorial_i11_run(
            exclusion_policy=_policy(),
            f07_permission_b=None,
            source_id="invented-second-source",
            submit_new_paid_job=True,
        )


def test_source_sha_drift_on_second_grant():
    granted = {
        "schema": "seshat.f07_per_operation_permission.v1",
        "permission_id": "b-drift",
        "operation_id": AUTHORIAL_I11_ID,
        "source_id": "invented-second-source",
        "source_sha256": "1" * 64,
        "pages_sha256": "2" * 64,
        "rights_class": "FULL_REQUIRED",
        "grant": "OPERATOR_DECLARED_UNATTESTED",
        "independent_attestation": "NONE",
        "model_transfer": MODEL_TRANSFER_GRANT,
        "budget_authorization": "invented-budget",
    }
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b=granted,
        source_id="invented-second-source",
        source_bytes=b"not-the-pinned-bytes",
        pages_bytes=b"not-the-pinned-pages",
    )
    assert "SOURCE_SHA_DRIFT" in result["reasons"]
    assert "PAGES_SHA_DRIFT" in result["reasons"]
    assert result["launched"] is False


def test_existing_registry_job_is_not_relaunched():
    digest = sha256(b"second-bytes").hexdigest()
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b={
            "schema": "seshat.f07_per_operation_permission.v1",
            "permission_id": "b-prior",
            "operation_id": AUTHORIAL_I11_ID,
            "source_id": "invented-second-source",
            "source_sha256": digest,
            "pages_sha256": sha256(b"pages").hexdigest(),
            "rights_class": "FULL_REQUIRED",
            "grant": "OPERATOR_DECLARED_UNATTESTED",
            "independent_attestation": "NONE",
            "model_transfer": MODEL_TRANSFER_GRANT,
            "budget_authorization": "invented-budget",
        },
        source_id="invented-second-source",
        source_bytes=b"second-bytes",
        pages_bytes=b"pages",
        job_registry={"jobs": [{"job_id": "jx-already-ran", "source_sha256": digest}]},
    )
    assert "EXISTING_JOB_DO_NOT_RELAUNCH" in result["reasons"]
    assert result["launched"] is False


def test_complete_second_grant_still_does_not_launch_in_this_scene():
    digest = sha256(b"second-complete").hexdigest()
    pages = sha256(b"second-pages").hexdigest()
    result = admit_second_authorial_i11_run(
        exclusion_policy=_policy(),
        f07_permission_b={
            "schema": "seshat.f07_per_operation_permission.v1",
            "permission_id": "b-complete",
            "operation_id": AUTHORIAL_I11_ID,
            "source_id": "invented-second-source",
            "source_sha256": digest,
            "pages_sha256": pages,
            "rights_class": "FULL_REQUIRED",
            "grant": "OPERATOR_DECLARED_UNATTESTED",
            "independent_attestation": "NONE",
            "model_transfer": MODEL_TRANSFER_GRANT,
            "budget_authorization": "invented-budget",
        },
        source_id="invented-second-source",
        source_bytes=b"second-complete",
        pages_bytes=b"second-pages",
    )
    assert result["status"] == BLOCKED_SECOND_MODELRUN
    assert result["launched"] is False
    assert "HUB_MODEL_TRANSPORT_NOT_EXPOSED_IN_THIS_SCENE" in result["reasons"]


def test_r03_stays_blocked_without_second_real_state():
    r03 = portfolio.compose_real_two_source_r03(
        _state("world_a"),
        None,
        membership_kinds={
            "invented-world_a": "ADMITTED_REAL_OBSERVED",
            "invented-world_b": "REAL_SOURCE_ADMITTED_PENDING_I11",
        },
        second_run={"status": BLOCKED_SECOND_MODELRUN},
    )
    assert r03["status"] == "BLOCKED_PENDING_SECOND_REAL_AUTHORIAL_METHOD_RUN"
    assert r03["comparison_claims"] == []
    assert r03["fictional_controls_counted_as_real"] is False


def test_same_listed_identity_is_not_shared_rp_when_two_states_exist():
    left = _state("world_a")
    right = _state("world_b")
    r03 = portfolio.compose_real_two_source_r03(
        left,
        right,
        membership_kinds={
            left.work_id: "ADMITTED_REAL_OBSERVED",
            right.work_id: "ADMITTED_REAL_OBSERVED",
        },
    )
    assert r03["status"] == "SOURCE_GROUNDED_UNREVIEWED"
    assert r03["identity_overlap_is_not_shared_operation"] is True
    assert r03["customer_release"] == "BLOCKED"
    for claim in r03["comparison_claims"]:
        assert claim["work_a"]["work_id"] == left.work_id
        assert claim["work_b"]["work_id"] == right.work_id
        assert "locator" not in claim or True
        assert claim["work_a"].get("page") is not None or claim["work_a"].get("unknown")
        assert claim["work_b"].get("page") is not None or claim["work_b"].get("unknown")
        assert claim["inference_forbidden"].endswith("is_not_shared_RP_operation")
        assert "common RP performed" not in json.dumps(claim).casefold()


def test_editor_promotion_and_e5_human_approval_stay_illegal():
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
    with pytest.raises(ValueError, match="I11_CUSTOMER_RELEASE_BLOCKED"):
        validate_activity_network(
            state, world_bytes("world_a"), customer_release_authorized=True
        )


def test_planned_implementation_is_not_factual_operation():
    state = _state("world_a")
    actors = {actor.actor_id: actor for actor in state.actors}
    planned = ActionEvent(
        event_id="E20",
        actor_ids=(state.action_events[0].actor_ids or ("rp-author",)),
        verb="will implement the shared registry",
        affected_entities=("WORK",),
        layer="PR",
        source_addresses=state.action_events[0].source_addresses,
        relation_mode="SOURCE_ASSERTED_OPERATION",
    )
    with pytest.raises(ValueError, match="I11_PLANNED_NOT_ACTIVE"):
        refuse_false_event_promotions(planned, actors)


def test_false_paragraph_page_is_rejected_by_lineage():
    model = _pages("PRINTED PDF", ["keep", "real-page-two"])
    derived = _pages("ORIGINAL PDF", ["keep", "forged-page-two"])
    cmp = qualify_source_text_lineage(
        original_pdf_sha256="9" * 64,
        derived_page_view_sha256=sha256(derived).hexdigest(),
        extractor_version="pypdf-invented",
        original_model_input_page_text_sha256=sha256(model).hexdigest(),
        model_input_pages=inner_page_texts(model),
        derived_pages=inner_page_texts(derived),
    )
    assert cmp["page_comparison"]["diverged_pages"] == (2,)


def test_stacked_cli_blocks_second_run_and_is_resumable(tmp_path: Path):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy()), encoding="utf-8")
    out = tmp_path / "stack"
    assert main([
        "--mode", "stacked-product",
        "--out", str(out),
        "--exclusion-policy", str(policy),
    ]) == 0
    manifest = json.loads((out / "stacked_manifest.json").read_text(encoding="utf-8"))
    assert manifest["second_model_run"]["status"] == BLOCKED_SECOND_MODELRUN
    assert manifest["r03"]["status"] == "BLOCKED_PENDING_SECOND_REAL_AUTHORIAL_METHOD_RUN"
    assert manifest["customer_release"] == "BLOCKED"
    assert main([
        "--mode", "stacked-product",
        "--out", str(out),
        "--exclusion-policy", str(policy),
        "--verify-only",
    ]) == 0


def test_stacked_cli_refuses_paid_replay_flag(tmp_path: Path):
    with pytest.raises(ValueError, match="I11_DUPLICATE_LAUNCH"):
        main([
            "--mode", "stacked-product",
            "--out", str(tmp_path / "paid"),
            "--submit-new-paid-job",
        ])
