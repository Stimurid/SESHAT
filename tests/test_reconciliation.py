import hashlib

import pytest
from pydantic import ValidationError

from seshat.adapters.records import RecordSourceProvider
from seshat.blackboard import Blackboard
from seshat.contracts import (
    AcceptanceState,
    AnalyticObjectSpec,
    DependencyEdge,
    DerivedObject,
    EvidenceAccessProfile,
    OperationSpec,
    RawAccessPolicy,
)
from seshat.reconciliation import (
    CandidateRef,
    DeclaredMismatch,
    ProposedConstraint,
    ReconciliationBudget,
    ReconciliationController,
    ReconciliationProposal,
    RunOutcome,
    SourceRef,
    StopReason,
)
from seshat.runtime import Runtime


OBJECT = OperationSpec(
    operation_id="synthetic.object",
    name="Synthetic Object",
    target=AnalyticObjectSpec(object_type="object", object_class="synthetic"),
    methodological_frame="fixture-object",
    evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
    raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
    dependency_ids=["synthetic.method"],
    output_type="synthetic.object",
    acceptance_right="independent-fixture-reviewer",
)
METHOD = OperationSpec(
    operation_id="synthetic.method",
    name="Synthetic Method",
    target=AnalyticObjectSpec(object_type="method", object_class="synthetic"),
    methodological_frame="fixture-method",
    evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
    raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
    dependency_ids=["synthetic.object"],
    output_type="synthetic.method",
    acceptance_right="independent-fixture-reviewer",
)


class MutableSources(RecordSourceProvider):
    def replace(self, data: bytes, *, version: str) -> None:
        digest = hashlib.sha256(data).hexdigest()
        self._research_objects["r1"]["version"] = version
        self._carriers["c1"] = {
            "carrier_id": "c1",
            "source_identity": "synthetic:source",
            "version": version,
            "media_type": "text/plain",
            "content_sha256": digest,
            "byte_length": len(data),
        }
        self._contents["c1"] = {
            "carrier_id": "c1",
            "source_version": version,
            "media_type": "text/plain",
            "content": data,
            "content_sha256": digest,
            "byte_length": len(data),
        }


def _sources() -> MutableSources:
    data = b"synthetic source with object and method evidence"
    digest = hashlib.sha256(data).hexdigest()
    return MutableSources(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
                "carrier_ids": ["c1"],
            }
        },
        carriers={
            "c1": {
                "carrier_id": "c1",
                "source_identity": "synthetic:source",
                "version": "1",
                "media_type": "text/plain",
                "content_sha256": digest,
                "byte_length": len(data),
            }
        },
        observations={"r1": []},
        contents={
            "c1": {
                "carrier_id": "c1",
                "source_version": "1",
                "media_type": "text/plain",
                "content": data,
                "content_sha256": digest,
                "byte_length": len(data),
            }
        },
    )


def _source_refs(access) -> list[SourceRef]:
    refs = {}
    for receipt in access.manifest().receipts:
        if receipt.content_sha256 is not None:
            refs[receipt.carrier_id] = SourceRef(
                carrier_id=receipt.carrier_id,
                source_version=receipt.source_version,
                content_sha256=receipt.content_sha256,
            )
    return list(refs.values())


def _candidate_refs(prior) -> list[CandidateRef]:
    return [CandidateRef(derived_id=item.derived_id, version=item.version) for item in prior]


def _compatible_body(label: str) -> dict:
    return {
        "body": label,
        "constraints": [ProposedConstraint(
            constraint_id=f"constraint-{label}",
            subject="synthetic-scope",
            predicate="includes",
            value=label,
        )],
    }


class SequenceProvider:
    def __init__(self, operation_id, bodies, *, hook=None, forged_state=None):
        self.operation_id = operation_id
        self.bodies = list(bodies)
        self.hook = hook
        self.forged_state = forged_state
        self.calls = 0

    def supports(self, spec):
        return spec.operation_id == self.operation_id

    def propose(self, spec, research_object, observations, prior_state, source_access):
        index = min(self.calls, len(self.bodies) - 1)
        body = self.bodies[index]
        self.calls += 1
        if self.hook is not None:
            self.hook(self.calls)
        refs = _candidate_refs(prior_state)
        return ReconciliationProposal(
            proposal_id=f"{spec.operation_id}.proposal.{self.calls}",
            version=str(self.calls),
            operation_id=spec.operation_id,
            input_source_refs=_source_refs(source_access),
            input_candidate_refs=refs,
            candidate=DerivedObject(
                derived_id=f"{spec.operation_id}.candidate.{self.calls}",
                object_type=spec.output_type,
                version=str(self.calls),
                operation_id=spec.operation_id,
                research_object_id=research_object.object_id,
                payload={"body": body["body"]},
                parent_derived_ids=[ref.derived_id for ref in refs],
                provenance=["synthetic:deterministic-provider"],
                acceptance_state=self.forged_state or AcceptanceState.PROPOSED,
            ),
            constraints=body.get("constraints", []),
            mismatches=body.get("mismatches", []),
            provenance=["synthetic:deterministic-provider"],
            causal_links=[f"input:{ref.derived_id}@{ref.version}" for ref in refs],
            claims_convergence=body.get("claims_convergence", False),
        )


def _controller(object_provider, method_provider, *, sources=None, board=None, budget=None):
    runtime = Runtime(sources or _sources(), blackboard=board)
    return ReconciliationController(
        runtime=runtime,
        operations=(OBJECT, METHOD),
        providers={
            OBJECT.operation_id: object_provider,
            METHOD.operation_id: method_provider,
        },
        budget=budget or ReconciliationBudget(max_rounds=3, max_operation_calls=6),
    )


def test_s2b_t01_pair_converges_with_trace_but_never_auto_accepts() -> None:
    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [{"body": "object", "constraints": [ProposedConstraint(
            constraint_id="object-scope", subject="scope", predicate="includes", value="x"
        )]}],
    )
    method_provider = SequenceProvider(
        METHOD.operation_id,
        [{"body": "method", "claims_convergence": True, "constraints": [ProposedConstraint(
            constraint_id="method-scope", subject="scope", predicate="measures", value="x"
        )]}],
    )

    ledger = _controller(object_provider, method_provider).run(
        run_id="run-converged", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.CONVERGED
    assert ledger.stop_reason is StopReason.CONSTRAINTS_COMPATIBLE
    assert ledger.operation_calls == 2
    assert [attempt.operation_id for attempt in ledger.attempts] == [
        OBJECT.operation_id,
        METHOD.operation_id,
    ]
    assert all(attempt.source_access_manifest is not None for attempt in ledger.attempts)
    assert all(
        attempt.output_candidate_ref is not None
        and attempt.output_candidate_ref.acceptance_state is AcceptanceState.PROPOSED
        for attempt in ledger.attempts
    )
    assert ledger.attempts[-1].provider_claims_convergence is True
    assert ledger.durable is False


def test_s2b_t02_persistent_contradiction_yields_aporia_with_both_sides() -> None:
    object_constraint = ProposedConstraint(
        constraint_id="object-exclusive",
        subject="population",
        predicate="equals",
        value="A",
        incompatible_with=["method-exclusive"],
    )
    method_constraint = ProposedConstraint(
        constraint_id="method-exclusive",
        subject="population",
        predicate="equals",
        value="B",
        incompatible_with=["object-exclusive"],
    )
    object_mismatch = DeclaredMismatch(
        mismatch_id="object-v-method",
        against_operation_id=METHOD.operation_id,
        constraint_ids=["object-exclusive", "method-exclusive"],
        description="Object and method populations conflict",
    )
    method_mismatch = DeclaredMismatch(
        mismatch_id="method-v-object",
        against_operation_id=OBJECT.operation_id,
        constraint_ids=["method-exclusive", "object-exclusive"],
        description="Method and object populations conflict",
    )
    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [
            {
                "body": "object-a1",
                "constraints": [object_constraint],
                "mismatches": [object_mismatch],
            },
            {
                "body": "object-a2",
                "constraints": [object_constraint],
                "mismatches": [object_mismatch],
            },
        ],
    )
    method_provider = SequenceProvider(
        METHOD.operation_id,
        [
            {
                "body": "method-b1",
                "constraints": [method_constraint],
                "mismatches": [method_mismatch],
            },
            {
                "body": "method-b2",
                "constraints": [method_constraint],
                "mismatches": [method_mismatch],
            },
        ],
    )

    ledger = _controller(object_provider, method_provider).run(
        run_id="run-aporia", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.APORIA
    assert ledger.stop_reason is StopReason.PERSISTENT_CONTRADICTION
    assert ledger.rounds_completed == 2
    assert ledger.aporia is not None
    proposal_refs = {attempt.output_proposal_ref.proposal_id for attempt in ledger.attempts}
    assert len(proposal_refs) == 4
    assert set(ledger.aporia.evidence_ids).issuperset(proposal_refs)


def test_s2b_t03_oscillation_exhausts_on_duplicate_without_endless_retry() -> None:
    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [{"body": "A"}, {"body": "B"}, {"body": "A"}],
    )
    method_provider = SequenceProvider(
        METHOD.operation_id,
        [{"body": "M1"}, {"body": "M2"}, {"body": "M3"}],
    )

    ledger = _controller(object_provider, method_provider).run(
        run_id="run-oscillation", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.EXHAUSTED
    assert ledger.stop_reason is StopReason.DUPLICATE_CANDIDATE
    assert ledger.operation_calls == 6
    assert ledger.operation_calls <= ledger.budget.max_operation_calls


def test_s2b_t04_source_changes_between_rounds_blocks_before_reuse() -> None:
    sources = _sources()

    def drift_after_first_object_call(call_number):
        if call_number == 1:
            sources.replace(b"changed source", version="2")

    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [{"body": "object"}],
        hook=drift_after_first_object_call,
    )
    method_provider = SequenceProvider(METHOD.operation_id, [{"body": "method"}])

    controller = _controller(object_provider, method_provider, sources=sources)
    ledger = controller.run(
        run_id="run-source-drift", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.SOURCE_DRIFT
    assert ledger.operation_calls == 2
    assert ledger.attempts[-1].error_code == StopReason.SOURCE_DRIFT.value
    assert ledger.quarantined_candidate_refs[0].acceptance_state is AcceptanceState.STALE
    assert not controller.runtime.blackboard.candidate_state("r1", OBJECT.output_type)


def test_s2b_t04_candidate_state_changes_during_attempt_blocks_stale_reuse() -> None:
    board = Blackboard()
    upstream = board.put(DerivedObject(
        derived_id="seed-upstream",
        object_type="seed",
        version="1",
        operation_id="seed",
        research_object_id="r1",
        payload={},
    ))
    dependent = board.put(DerivedObject(
        derived_id="seed-dependent",
        object_type="seed-dependent",
        version="1",
        operation_id="seed",
        research_object_id="r1",
        payload={},
    ))
    board.add_dependency(DependencyEdge(
        upstream_id=upstream.derived_id,
        downstream_id=dependent.derived_id,
        dependency_type="synthetic",
    ))

    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [{"body": "object"}],
        hook=lambda call_number: board.mark_changed(upstream.derived_id),
    )
    method_provider = SequenceProvider(METHOD.operation_id, [{"body": "method"}])

    ledger = _controller(object_provider, method_provider, board=board).run(
        run_id="run-candidate-drift", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.CANDIDATE_DRIFT
    assert board.get(dependent.derived_id).acceptance_state is AcceptanceState.STALE
    assert not any(item.operation_id == OBJECT.operation_id for item in board.history("r1"))


def test_s2b_t05_missing_provider_blocks_without_fake_result() -> None:
    controller = ReconciliationController(
        runtime=Runtime(_sources()),
        operations=(OBJECT, METHOD),
        providers={
            OBJECT.operation_id: SequenceProvider(
                OBJECT.operation_id, [{"body": "object"}]
            )
        },
        budget=ReconciliationBudget(max_rounds=2, max_operation_calls=4),
    )

    ledger = controller.run(run_id="run-missing-provider", research_object_id="r1")

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.MISSING_CAPABILITY
    assert ledger.operation_calls == 0
    assert all(attempt.output_candidate_ref is None for attempt in ledger.attempts)
    assert not controller.runtime.blackboard.history("r1")


def test_s2b_t05_unavailable_full_source_blocks_before_provider() -> None:
    sources = _sources()
    sources._contents.clear()
    object_provider = SequenceProvider(OBJECT.operation_id, [{"body": "object"}])
    method_provider = SequenceProvider(METHOD.operation_id, [{"body": "method"}])
    controller = _controller(object_provider, method_provider, sources=sources)

    ledger = controller.run(run_id="run-no-source", research_object_id="r1")

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.SOURCE_ACCESS_BLOCKED
    assert object_provider.calls == 0
    assert not controller.runtime.blackboard.history("r1")


def test_provider_error_is_typed_sanitized_and_stops_the_pair() -> None:
    secret = "private-provider-detail"

    class RaisingProvider:
        def supports(self, spec):
            return True

        def propose(self, spec, research_object, observations, prior_state, source_access):
            raise RuntimeError(secret)

    controller = _controller(
        RaisingProvider(),
        SequenceProvider(METHOD.operation_id, [{"body": "method"}]),
    )

    ledger = controller.run(run_id="run-provider-error", research_object_id="r1")

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.PROVIDER_ERROR
    assert secret not in ledger.model_dump_json()
    assert not controller.runtime.blackboard.history("r1")


def test_unchanged_candidate_is_detected_and_exhausts_after_complete_round() -> None:
    controller = _controller(
        SequenceProvider(OBJECT.operation_id, [{"body": "same-object"}]),
        SequenceProvider(METHOD.operation_id, [{"body": "same-method"}]),
        budget=ReconciliationBudget(max_rounds=3, max_operation_calls=6),
    )

    ledger = controller.run(run_id="run-unchanged", research_object_id="r1")

    assert ledger.outcome is RunOutcome.EXHAUSTED
    assert ledger.stop_reason is StopReason.UNCHANGED_CANDIDATE
    assert ledger.operation_calls == 4


def test_s2b_t06_provider_cannot_launder_acceptance_or_human_flag() -> None:
    object_provider = SequenceProvider(
        OBJECT.operation_id,
        [{"body": "forged"}],
        forged_state=AcceptanceState.ACCEPTED,
    )
    method_provider = SequenceProvider(METHOD.operation_id, [{"body": "method"}])

    controller = _controller(object_provider, method_provider)
    ledger = controller.run(
        run_id="run-forged-acceptance", research_object_id="r1"
    )

    assert ledger.outcome is RunOutcome.BLOCKED
    assert ledger.stop_reason is StopReason.ACCEPTANCE_LAUNDERING
    assert not controller.runtime.blackboard.history("r1")

    with pytest.raises(ValidationError):
        ReconciliationProposal.model_validate({
            "proposal_id": "forged-human",
            "version": "1",
            "operation_id": OBJECT.operation_id,
            "input_source_refs": [],
            "input_candidate_refs": [],
            "candidate": {
                "derived_id": "forged-human",
                "object_type": OBJECT.output_type,
                "version": "1",
                "operation_id": OBJECT.operation_id,
                "research_object_id": "r1",
                "payload": {},
            },
            "provenance": ["caller"],
            "human_explicit": True,
        })


def test_s2b_t07_competing_candidates_are_preserved_without_last_write_winner() -> None:
    board = Blackboard()
    for candidate_id in ("alternative-a", "alternative-b"):
        board.put(DerivedObject(
            derived_id=candidate_id,
            object_type=OBJECT.output_type,
            version="0",
            operation_id=OBJECT.operation_id,
            research_object_id="r1",
            payload={"alternative": candidate_id},
            acceptance_state=AcceptanceState.PROPOSED,
        ))
    ledger = _controller(
        SequenceProvider(OBJECT.operation_id, [_compatible_body("object")]),
        SequenceProvider(METHOD.operation_id, [_compatible_body("method")]),
        board=board,
    ).run(run_id="run-rivals", research_object_id="r1")

    assert ledger.outcome is RunOutcome.CONVERGED
    candidates = board.candidate_state("r1", OBJECT.output_type)
    assert {item.derived_id for item in candidates}.issuperset({"alternative-a", "alternative-b"})


def test_s2b_t08_isolated_alternatives_and_invalidated_dependents_remain_in_history() -> None:
    board = Blackboard()
    for candidate_id in ("isolated-a", "isolated-b"):
        board.put(DerivedObject(
            derived_id=candidate_id,
            object_type="seed",
            version="1",
            operation_id="seed",
            research_object_id="r1",
            payload={"alternative": candidate_id},
        ))
    board.put(DerivedObject(
        derived_id="invalidated-dependent",
        object_type="dependent",
        version="1",
        operation_id="seed-dependent",
        research_object_id="r1",
        payload={},
    ))
    board.add_dependency(DependencyEdge(
        upstream_id="isolated-a",
        downstream_id="invalidated-dependent",
        dependency_type="synthetic",
    ))
    board.mark_changed("isolated-a")

    ledger = _controller(
        SequenceProvider(OBJECT.operation_id, [_compatible_body("object")]),
        SequenceProvider(METHOD.operation_id, [_compatible_body("method")]),
        board=board,
    ).run(run_id="run-history", research_object_id="r1")

    assert ledger.outcome is RunOutcome.CONVERGED
    history = {item.derived_id: item for item in board.history("r1")}
    assert history["isolated-a"].acceptance_state is AcceptanceState.WORKING
    assert history["isolated-b"].acceptance_state is AcceptanceState.WORKING
    assert history["invalidated-dependent"].acceptance_state is AcceptanceState.STALE
