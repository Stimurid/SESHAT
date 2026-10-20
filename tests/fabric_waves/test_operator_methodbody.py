"""Tests for the operator-local, source-agnostic MethodBody execution route.

All sources/methods here are entirely invented in-memory fixtures (source A,
source B). None of them, nor any identifier in this file, names any real
research case -- this keeps the suite correct regardless of the exact
contents of the owner's GitHub issue #65 exclusion set, which this bounded
session could not fetch (see OPEN QUESTIONS in the task receipt).
"""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import EpistemicLevel
from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorClaim,
    OperatorInvocation,
    OperatorMethodBodyPin,
    OperatorRunLedger,
    OperatorSourcePin,
    export_rights_reviewed_prose,
    invoke_operator_method_body,
    replay_and_verify_operator_run,
)

_raw_invoke_operator_method_body = invoke_operator_method_body


def invoke_operator_method_body(**kwargs):
    # Only invented fixtures; no real corpus may omit the loaded private policy.
    kwargs.setdefault("owner_excluded_source_ids", frozenset())
    kwargs.setdefault("owner_excluded_source_sha256", frozenset())
    return _raw_invoke_operator_method_body(**kwargs)


SOURCE_A_TEXT = "INVENTED SOURCE A: the quick brown fox jumps over the lazy dog."
SOURCE_B_TEXT = "field,value\nalpha,1\nbeta,2\nINVENTED SOURCE B marker present here.\n"

METHOD_SCRIPT = (
    "# invented operator method body v1\n"
    "def extract(invocation):\n"
    "    return locate(invocation.source_text, 'fox')\n"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_pin(text: str, *, source_id: str = "source-a", view: str = "operator-view") -> tuple[OperatorSourcePin, bytes]:
    raw = text.encode("utf-8")
    pin = OperatorSourcePin(
        source_id=source_id,
        source_version="v1",
        sha256=_sha256(raw),
        rights_basis="operator-declared-personal-invented-fixture",
        authorized_view=view,
    )
    return pin, raw


def _method_pin(script: str = METHOD_SCRIPT, *, method_body_id: str = "operator.invented.extract") -> tuple[OperatorMethodBodyPin, bytes]:
    raw = script.encode("utf-8")
    pin = OperatorMethodBodyPin(
        method_body_id=method_body_id,
        version="1",
        invocation_body_sha256=_sha256(raw),
    )
    return pin, raw


def _make_counting_callable(calls: list[int], *, text: str = SOURCE_A_TEXT, epistemic_level: EpistemicLevel = EpistemicLevel.E2):
    needle = "fox"
    offset = text.index(needle)

    def _callable(invocation: OperatorInvocation) -> OperatorBodyResult:
        calls.append(1)
        print("operator method body executed")  # noqa: T201 - real stdout under test
        return OperatorBodyResult(
            research_object_id="invented-object-1",
            epistemic_level=epistemic_level,
            claims=(
                OperatorClaim(
                    text="the source mentions a fox",
                    evidence_excerpt=needle,
                    byte_offset=offset,
                    byte_length=len(needle),
                ),
            ),
            notes=("ran",),
        )

    return _callable


def _authorized_view() -> str:
    return "operator-view"


class TestHappyPath:
    def test_source_a_invented_fixture_real_invocation(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        calls: list[int] = []
        receipt = invoke_operator_method_body(
            ledger=ledger,
            run_id="run-a",
            job_id="job-1",
            source=source,
            source_bytes=source_bytes,
            method=method,
            method_body_invocation_bytes=method_bytes,
            method_callable=_make_counting_callable(calls),
            requested_view=_authorized_view(),
        )
        assert len(calls) == 1, "the callable must actually be invoked exactly once"
        assert receipt.provenance == "SELF_OBSERVED_UNATTESTED"
        assert receipt.scientific_acceptance == "NOT_ASSERTED"
        assert receipt.declared_token_cost == "UNKNOWN"
        assert receipt.declared_model_identity == "UNKNOWN"
        assert receipt.output_sediment.acceptance_state is AcceptanceState.PROPOSED
        assert receipt.source_access_manifest.all_declared_sources_verified is True
        assert receipt.invocation.exit_status == "OK"
        assert receipt.invocation.stdout_sha256 is not None
        assert receipt.invocation.stdout_byte_length and receipt.invocation.stdout_byte_length > 0

    def test_source_b_different_structure_is_source_agnostic(self):
        """A second, structurally distinct invented source exercises the same route."""

        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_B_TEXT, source_id="source-b")
        method, method_bytes = _method_pin()
        needle = "marker"
        offset = SOURCE_B_TEXT.index(needle)

        def _callable(invocation: OperatorInvocation) -> OperatorBodyResult:
            return OperatorBodyResult(
                research_object_id="invented-object-2",
                claims=(
                    OperatorClaim(
                        text="csv-like source carries a marker token",
                        evidence_excerpt=needle,
                        byte_offset=offset,
                        byte_length=len(needle),
                    ),
                ),
            )

        receipt = invoke_operator_method_body(
            ledger=ledger,
            run_id="run-b",
            job_id="job-1",
            source=source,
            source_bytes=source_bytes,
            method=method,
            method_body_invocation_bytes=method_bytes,
            method_callable=_callable,
            requested_view=_authorized_view(),
            declared_model_identity="operator-local-model-x",
            declared_token_cost=42,
        )
        assert receipt.source_id == "source-b"
        assert receipt.declared_model_identity == "operator-local-model-x"
        assert receipt.declared_token_cost == 42

    def test_resume_same_inputs_replays_without_reinvoking(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        calls: list[int] = []
        callable_ = _make_counting_callable(calls)

        first = invoke_operator_method_body(
            ledger=ledger, run_id="run-resume", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=callable_, requested_view=_authorized_view(),
        )
        second = invoke_operator_method_body(
            ledger=ledger, run_id="run-resume", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=callable_, requested_view=_authorized_view(),
        )
        assert len(calls) == 1, "identical resume must not re-invoke the method body"
        assert first.output_digest == second.output_digest

    def test_replay_and_verify_matches_cached_receipt(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        invoke_operator_method_body(
            ledger=ledger, run_id="run-replay", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
        )
        replayed = replay_and_verify_operator_run(
            ledger=ledger, run_id="run-replay",
            source_bytes=source_bytes, method_body_invocation_bytes=method_bytes,
        )
        assert replayed.run_id == "run-replay"

    def test_export_requires_rights_reviewed_prose(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        receipt = invoke_operator_method_body(
            ledger=ledger, run_id="run-export", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
        )
        bundle = export_rights_reviewed_prose(
            receipt=receipt,
            reviewed_prose="A human reviewer wrote this prose about the finding.",
            reviewer_rights_statement="Reviewed under operator-declared-personal-invented-fixture.",
            raw_method_body_invocation_bytes=method_bytes,
            raw_source_bytes=source_bytes,
        )
        assert bundle.receipt_output_digest == receipt.output_digest


class TestNegativeGates:
    def test_wrong_rights_view_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a", view="operator-view")
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_SOURCE_RIGHTS_VIEW_MISMATCH"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-wrong-view", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]),
                requested_view="a-different-unauthorized-view",
            )

    def test_missing_rights_basis_denied_at_construction(self):
        with pytest.raises(ValidationError):
            OperatorSourcePin(
                source_id="source-a", source_version="v1",
                sha256=_sha256(b"x"), rights_basis="", authorized_view="operator-view",
            )

    def test_missing_bytes_denied(self):
        ledger = OperatorRunLedger()
        source, _ = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_SOURCE_BYTES_STALE"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-missing-bytes", job_id="job-1",
                source=source, source_bytes=b"",
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
            )

    def test_source_update_without_repin_denied(self):
        """Simulates a source changing underneath a stale pin ('source update')."""

        ledger = OperatorRunLedger()
        source, _ = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        updated_bytes = (SOURCE_A_TEXT + " updated content").encode("utf-8")
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_SOURCE_BYTES_STALE"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-source-update", job_id="job-1",
                source=source, source_bytes=updated_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
            )

    def test_method_pin_drift_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, _ = _method_pin()
        drifted_bytes = (METHOD_SCRIPT + "\n# silently modified\n").encode("utf-8")
        with pytest.raises(ValueError, match="OPERATOR_METHOD_BODY_DRIFT"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-method-drift", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=drifted_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
            )

    def test_wrong_page_claim_span_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()

        def _callable(invocation: OperatorInvocation) -> OperatorBodyResult:
            return OperatorBodyResult(
                research_object_id="invented-object-1",
                claims=(
                    OperatorClaim(
                        text="misplaced claim",
                        evidence_excerpt="fox",
                        byte_offset=0,  # wrong location: 'fox' is not at offset 0
                        byte_length=3,
                    ),
                ),
            )

        with pytest.raises(ValueError, match="OPERATOR_CLAIM_SPAN_INVALID"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-wrong-page", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_callable, requested_view=_authorized_view(),
            )

    def test_fabricated_claim_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()

        def _callable(invocation: OperatorInvocation) -> OperatorBodyResult:
            return OperatorBodyResult(
                research_object_id="invented-object-1",
                claims=(
                    OperatorClaim(
                        text="a claim about text that was never in the source",
                        evidence_excerpt="this text does not exist in the source",
                        byte_offset=0,
                        byte_length=len("this text does not exist in the source"),
                    ),
                ),
            )

        with pytest.raises(ValueError, match="OPERATOR_CLAIM_SPAN_INVALID"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-fabricated", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_callable, requested_view=_authorized_view(),
            )

    def test_no_invocation_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_INVOCATION_REQUIRED"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-no-invocation", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=None, requested_view=_authorized_view(),
            )

    def test_resumed_ambiguous_duplicate_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        invoke_operator_method_body(
            ledger=ledger, run_id="run-dup", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
        )
        other_source, other_source_bytes = _source_pin(SOURCE_B_TEXT, source_id="source-b")
        with pytest.raises(ValueError, match="OPERATOR_RUN_ID_AMBIGUOUS_DUPLICATE"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-dup", job_id="job-1",
                source=other_source, source_bytes=other_source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
            )

    def test_e5_promotion_attempt_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        calls: list[int] = []
        with pytest.raises(ValueError, match="OPERATOR_EPISTEMIC_PROMOTION_DENIED"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-e5", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable(calls, epistemic_level=EpistemicLevel.E5),
                requested_view=_authorized_view(),
            )

    def test_secret_method_leak_denied(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()
        receipt = invoke_operator_method_body(
            ledger=ledger, run_id="run-leak", job_id="job-1",
            source=source, source_bytes=source_bytes,
            method=method, method_body_invocation_bytes=method_bytes,
            method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
        )
        leaking_prose = f"Here is the exact method body we used:\n{METHOD_SCRIPT}"
        with pytest.raises(ValueError, match="OPERATOR_EXPORT_SECRET_LEAK_DENIED"):
            export_rights_reviewed_prose(
                receipt=receipt,
                reviewed_prose=leaking_prose,
                reviewer_rights_statement="reviewed",
                raw_method_body_invocation_bytes=method_bytes,
                raw_source_bytes=source_bytes,
            )

    def test_owner_excluded_selection_denied_via_private_policy_hook(self):
        """Owner-excluded ids are injected by the caller, never hardcoded here."""

        ledger = OperatorRunLedger()
        excluded_id = "owner-excluded-test-fixture-001"
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id=excluded_id)
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_SOURCE_EXCLUDED_BY_OWNER_POLICY"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-excluded", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
                owner_excluded_source_ids=frozenset({excluded_id}),
            )

    def test_method_invocation_exception_fails_closed(self):
        ledger = OperatorRunLedger()
        source, source_bytes = _source_pin(SOURCE_A_TEXT, source_id="source-a")
        method, method_bytes = _method_pin()

        def _raising_callable(invocation: OperatorInvocation) -> OperatorBodyResult:
            raise RuntimeError("operator code failed")

        with pytest.raises(ValueError, match="OPERATOR_METHOD_INVOCATION_FAILED"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-raises", job_id="job-1",
                source=source, source_bytes=source_bytes,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_raising_callable, requested_view=_authorized_view(),
            )

    def test_non_utf8_source_fails_closed(self):
        ledger = OperatorRunLedger()
        raw = b"\xff\xfe\x00\x01not-utf8"
        source = OperatorSourcePin(
            source_id="source-binary", source_version="v1",
            sha256=_sha256(raw), rights_basis="operator-declared", authorized_view="operator-view",
        )
        method, method_bytes = _method_pin()
        with pytest.raises(ValueError, match="OPERATOR_SOURCE_NOT_UTF8"):
            invoke_operator_method_body(
                ledger=ledger, run_id="run-binary", job_id="job-1",
                source=source, source_bytes=raw,
                method=method, method_body_invocation_bytes=method_bytes,
                method_callable=_make_counting_callable([]), requested_view=_authorized_view(),
            )
