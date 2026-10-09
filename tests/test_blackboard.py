from seshat.blackboard import Blackboard
from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject


def _derived(derived_id: str, object_type: str) -> DerivedObject:
    return DerivedObject(
        derived_id=derived_id,
        object_type=object_type,
        version="1",
        operation_id=f"op.{object_type}",
        research_object_id="r1",
        payload={},
    )


def test_invalidation_is_transitive() -> None:
    board = Blackboard()
    board.put(_derived("object-v1", "object"))
    board.put(_derived("method-v1", "method"))
    board.put(_derived("novelty-v1", "novelty"))

    board.add_dependency(
        DependencyEdge(
            upstream_id="object-v1",
            downstream_id="method-v1",
            dependency_type="mutual_constraint",
        )
    )
    board.add_dependency(
        DependencyEdge(
            upstream_id="method-v1",
            downstream_id="novelty-v1",
            dependency_type="evidence_dependency",
        )
    )

    assert board.mark_changed("object-v1") == {"method-v1", "novelty-v1"}
    assert board.get("method-v1").acceptance_state is AcceptanceState.STALE
    assert board.get("novelty-v1").acceptance_state is AcceptanceState.STALE


def test_non_invalidating_edge_does_not_stale() -> None:
    board = Blackboard()
    board.put(_derived("a", "a"))
    board.put(_derived("b", "b"))
    board.add_dependency(
        DependencyEdge(
            upstream_id="a",
            downstream_id="b",
            dependency_type="advisory",
            invalidates_on_change=False,
        )
    )

    assert board.mark_changed("a") == set()
    assert board.get("b").acceptance_state is AcceptanceState.WORKING
