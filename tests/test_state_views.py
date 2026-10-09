import pytest

from seshat.adapters.records import RecordSourceProvider
from seshat.adapters.testing import DeterministicOperationProvider
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
from seshat.runtime import Runtime

SPEC = OperationSpec(
    operation_id="test.state-view",
    name="State view",
    target=AnalyticObjectSpec(object_type="analysis", object_class="fixture"),
    methodological_frame="fixture",
    evidence_access_profile=EvidenceAccessProfile.META,
    raw_access_policy=RawAccessPolicy.NEVER,
    output_type="analysis",
    acceptance_right="fixture-owner",
)


def _derived(
    derived_id: str,
    *,
    object_type: str = "analysis",
    version: str = "1",
    state: AcceptanceState = AcceptanceState.WORKING,
    parents: tuple[str, ...] = (),
) -> DerivedObject:
    return DerivedObject(
        derived_id=derived_id,
        object_type=object_type,
        version=version,
        operation_id=f"test.{object_type}",
        research_object_id="r1",
        payload={"id": derived_id},
        parent_derived_ids=list(parents),
        provenance=["synthetic:test"],
        acceptance_state=state,
    )


def _sources() -> RecordSourceProvider:
    return RecordSourceProvider(
        research_objects={
            "r1": {
                "object_id": "r1",
                "object_type": "document",
                "version": "1",
            }
        },
        carriers={},
        observations={"r1": []},
    )


def test_runtime_prior_state_excludes_stale_downstream() -> None:
    board = Blackboard()
    for derived_id, state in (
        ("working", AcceptanceState.WORKING),
        ("proposed", AcceptanceState.PROPOSED),
        ("accepted", AcceptanceState.ACCEPTED),
        ("contested", AcceptanceState.CONTESTED),
        ("rejected", AcceptanceState.REJECTED),
        ("stale-method", AcceptanceState.STALE),
    ):
        board.put(_derived(derived_id, object_type="method", state=state))
    seen_prior_ids: list[str] = []
    provider = DeterministicOperationProvider(
        {SPEC.operation_id},
        lambda spec, ro, observations, prior, access: (
            seen_prior_ids.extend(obj.derived_id for obj in prior)
            or DerivedObject(
                derived_id="fresh-analysis",
                object_type=spec.output_type,
                version="1",
                operation_id=spec.operation_id,
                research_object_id=ro.object_id,
                payload={},
            )
        ),
    )

    Runtime(_sources(), blackboard=board).run(SPEC, provider, research_object_id="r1")

    assert seen_prior_ids == ["working", "proposed"]


def test_stale_rejected_and_superseded_history_remains_addressable() -> None:
    board = Blackboard()
    stale = board.put(_derived("stale", version="1", state=AcceptanceState.STALE))
    rejected = board.put(
        _derived("rejected", version="2", state=AcceptanceState.REJECTED)
    )
    prior = board.put(_derived("prior", version="3"))
    replacement = board.put(_derived("replacement", version="4", parents=(prior.derived_id,)))

    board.supersede(prior.derived_id, replacement.derived_id)

    assert board.get(stale.derived_id, version="1") == stale
    assert board.get(rejected.derived_id, version="2") == rejected
    assert board.get(prior.derived_id, version="3").acceptance_state is AcceptanceState.STALE
    assert {obj.derived_id for obj in board.history("r1", "analysis")} == {
        "stale",
        "rejected",
        "prior",
        "replacement",
    }


def test_rival_candidates_remain_visible_without_auto_acceptance_or_latest_winner() -> None:
    board = Blackboard()
    board.put(_derived("candidate-a", state=AcceptanceState.WORKING))
    board.put(_derived("candidate-b", version="2", state=AcceptanceState.PROPOSED))

    candidates = board.candidate_state("r1")

    assert {obj.derived_id for obj in candidates} == {"candidate-a", "candidate-b"}
    assert all(obj.acceptance_state is not AcceptanceState.ACCEPTED for obj in candidates)
    with pytest.raises(ValueError, match="multiple candidate"):
        board.latest("r1", "analysis")


def test_accepted_history_is_explicit_and_not_replaced_by_new_proposal() -> None:
    board = Blackboard()
    accepted = board.put(_derived("accepted-v1", state=AcceptanceState.ACCEPTED))
    proposal = board.put(
        _derived("proposal-v2", version="2", state=AcceptanceState.PROPOSED)
    )

    assert board.accepted_state("r1") == (accepted,)
    assert board.candidate_state("r1") == (proposal,)
    assert board.get("accepted-v1", version="1") == accepted


def test_non_authoritative_supersession_cannot_replace_accepted_state() -> None:
    board = Blackboard()
    accepted = board.put(_derived("accepted-v1", state=AcceptanceState.ACCEPTED))
    proposal = board.put(
        _derived(
            "proposal-v2",
            version="2",
            state=AcceptanceState.PROPOSED,
            parents=(accepted.derived_id,),
        )
    )

    with pytest.raises(ValueError, match="authorized workflow"):
        board.supersede(accepted.derived_id, proposal.derived_id)
    assert board.accepted_state("r1") == (accepted,)


def test_transitive_invalidation_preserves_unrelated_branch_and_lineage() -> None:
    board = Blackboard()
    upstream = board.put(_derived("upstream", object_type="object"))
    child = board.put(
        _derived("child", object_type="method", parents=(upstream.derived_id,))
    )
    grandchild = board.put(
        _derived("grandchild", object_type="novelty", parents=(child.derived_id,))
    )
    unrelated = board.put(_derived("unrelated", object_type="limitations"))
    board.add_dependency(
        DependencyEdge(
            upstream_id=upstream.derived_id,
            downstream_id=child.derived_id,
            dependency_type="derived",
        )
    )
    board.add_dependency(
        DependencyEdge(
            upstream_id=child.derived_id,
            downstream_id=grandchild.derived_id,
            dependency_type="derived",
        )
    )

    assert board.invalidate_descendants(upstream.derived_id) == {"child", "grandchild"}
    assert board.get("child").parent_derived_ids == ["upstream"]
    assert board.get("grandchild").parent_derived_ids == ["child"]
    assert board.get(unrelated.derived_id).acceptance_state is AcceptanceState.WORKING
    assert {obj.derived_id for obj in board.history("r1")} == {
        "upstream",
        "child",
        "grandchild",
        "unrelated",
    }


def test_version_addressed_get_rejects_version_drift_and_stale_candidate_use() -> None:
    board = Blackboard()
    board.put(_derived("candidate", version="7", state=AcceptanceState.STALE))

    with pytest.raises(ValueError, match="version drift"):
        board.get("candidate", version="6")
    with pytest.raises(ValueError, match="not an admissible candidate"):
        board.get_candidate("candidate", version="7")


def test_put_rejects_ambiguous_exact_id_overwrite() -> None:
    board = Blackboard()
    original = board.put(_derived("same-id", version="1"))

    assert board.put(original.model_copy()) == original
    with pytest.raises(ValueError, match="already identifies different content"):
        board.put(original.model_copy(update={"version": "2"}))


def test_candidate_view_is_detached_from_provider_mutation() -> None:
    board = Blackboard()
    board.put(_derived("candidate"))
    snapshot = board.candidate_state("r1")

    snapshot[0].acceptance_state = AcceptanceState.ACCEPTED
    snapshot[0].payload["forged"] = True

    stored = board.get("candidate")
    assert stored.acceptance_state is AcceptanceState.WORKING
    assert "forged" not in stored.payload
