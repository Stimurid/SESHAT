"""The Room must compile from runtime state, never from the plan oracle.

Every test here fails against a compiler that derives the plan from the
fixture's ``must_wave`` field.
"""

import copy
import json
from pathlib import Path

import pytest

from seshat.fabric_waves.m5_room_carpet import load_fixture
from seshat.fabric_waves.m5_synthetic_hosts import (
    BASE_SOURCE_STATE,
    BASE_STONE_STATE,
    MISSING_SOURCE_NEED_STATE,
    SYNTHETIC_RIGHT,
    build_host_engine,
    host_slug,
)
from seshat.fabric_waves.room_builder import (
    ADMITTED,
    BLOCKED_MISSING_INPUT,
    DENIED_RIGHTS,
    DROPPED_BUDGET,
    UNPRODUCIBLE,
    CapabilitySpec,
    RoomRequest,
    compile_room,
    compile_room_for_stone,
    desired_outputs_for_stone,
    load_registry,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / (
    "m5_room_synthetic_acceptance_20261021_v01.json"
)


@pytest.fixture(scope="module")
def fixture_data():
    data, _ = load_fixture(FIXTURE)
    return data


@pytest.fixture(scope="module")
def registry(fixture_data):
    return load_registry(fixture_data)


@pytest.fixture()
def host_binding(fixture_data):
    host = fixture_data["hosts"][0]
    _engine, _uri, binding = build_host_engine(host)
    return host, binding


def _compile(host, binding, registry, stone, **kw):
    params = {
        "available_base_states": [BASE_STONE_STATE, BASE_SOURCE_STATE],
        "granted_rights": [SYNTHETIC_RIGHT],
        "budget": {},
    }
    params.update(kw)
    return compile_room_for_stone(
        host_id=host["host_id"],
        host_slug=host_slug(host["host_id"]),
        stone=stone,
        registry=registry,
        thread_binding=binding,
        **params,
    )


def test_plan_is_identical_when_must_wave_is_erased(host_binding, registry):
    """The discriminating test: the oracle field cannot influence the plan."""

    host, binding = host_binding
    stone = host["stones"][0]
    baseline = _compile(host, binding, registry, stone)

    erased = copy.deepcopy(stone)
    erased.pop("must_wave", None)
    lied = copy.deepcopy(stone)
    lied["must_wave"] = ["N-H"]  # a plausible but wrong plan
    reordered = copy.deepcopy(stone)
    reordered["must_wave"] = list(reversed(stone["must_wave"])) + ["N-F"]

    for variant in (erased, lied, reordered):
        plan = _compile(host, binding, registry, variant)
        assert plan.planned_registry_threads == baseline.planned_registry_threads
        assert plan.admitted_engine_threads == baseline.admitted_engine_threads


def test_capability_irrelevant_to_the_desired_output_does_not_join(host_binding, registry):
    host, binding = host_binding
    plan = _compile(host, binding, registry, host["stones"][0])
    admitted = set(plan.planned_registry_threads)
    # N-P writes the Resonance a QUERY asks for; N-H writes a HypothesisProposal
    # nothing in that closure reads.
    assert "N-P" in admitted
    assert "N-H" not in admitted
    assert "N-H" not in {cap.registry_id for cap in plan.planned}


def test_backwards_closure_pulls_in_exactly_the_producers_it_needs(host_binding, registry):
    host, binding = host_binding
    plan = _compile(host, binding, registry, host["stones"][0])
    assert set(plan.planned_registry_threads) == {"N-S", "N-Q", "N-K", "N-E", "N-C", "N-P"}
    assert plan.state_status["Resonance"] == "SATISFIED_BY_CAPABILITY"
    assert plan.state_status[BASE_SOURCE_STATE] == "SATISFIED_BY_AVAILABLE_INPUT"


def test_aporia_stone_targets_a_different_output_than_a_query(host_binding, registry):
    host, binding = host_binding
    assert desired_outputs_for_stone(host["stones"][0]) == ("Resonance",)
    aporia = host["stones"][2]
    assert desired_outputs_for_stone(aporia) == ("ReconciledStateOrAPORIA",)
    plan = _compile(host, binding, registry, aporia)
    # Derived, not copied from must_wave (which lists only N-E, N-K, N-C).
    assert "N-C" in plan.planned_registry_threads
    assert "N-S" in plan.planned_registry_threads
    assert "N-P" not in plan.planned_registry_threads


def test_missing_capability_blocks_specifically_while_the_other_branch_runs(
    host_binding, registry
):
    host, binding = host_binding
    plan = _compile(
        host,
        binding,
        registry,
        host["stones"][0],
        desired_output_states=["Resonance", "ResearchNeed"],
    )
    by_id = {cap.registry_id: cap for cap in plan.planned}
    frontier = by_id["N-F"]
    assert frontier.admission == BLOCKED_MISSING_INPUT
    assert frontier.missing_input_states == (MISSING_SOURCE_NEED_STATE,)
    assert plan.state_status[MISSING_SOURCE_NEED_STATE] == UNPRODUCIBLE
    # The independent Resonance branch is untouched by that block.
    assert by_id["N-P"].admission == ADMITTED
    assert "N-P" in plan.planned_registry_threads
    assert "N-F" not in plan.planned_registry_threads


def test_frontier_becomes_admissible_once_the_need_actually_exists(host_binding, registry):
    host, binding = host_binding
    stone = {"stone_id": "F", "kind": "FRONTIER_NEED"}
    before = _compile(host, binding, registry, stone)
    after = _compile(
        host,
        binding,
        registry,
        stone,
        available_base_states=[BASE_STONE_STATE, BASE_SOURCE_STATE, MISSING_SOURCE_NEED_STATE],
    )
    assert "N-F" not in before.planned_registry_threads
    assert "N-F" in after.planned_registry_threads


def test_withholding_the_declared_right_denies_admission(host_binding, registry):
    host, binding = host_binding
    plan = _compile(host, binding, registry, host["stones"][0], granted_rights=[])
    assert plan.admitted_engine_threads == ()
    assert all(cap.admission == DENIED_RIGHTS for cap in plan.planned)
    assert plan.planned[0].detail.startswith("rights ")


def test_unbound_capability_cannot_be_admitted(host_binding, registry):
    host, binding = host_binding
    partial = {k: v for k, v in binding.items() if k != "N-E"}
    plan = compile_room_for_stone(
        host_id=host["host_id"],
        host_slug=host_slug(host["host_id"]),
        stone=host["stones"][0],
        registry=registry,
        thread_binding=partial,
        available_base_states=[BASE_STONE_STATE, BASE_SOURCE_STATE],
        granted_rights=[SYNTHETIC_RIGHT],
        budget={},
    )
    by_id = {cap.registry_id: cap for cap in plan.planned}
    assert by_id["N-E"].admission == BLOCKED_MISSING_INPUT
    assert by_id["N-E"].missing_input_states == ("<engine-binding>",)
    assert "N-C" in by_id and by_id["N-C"].admission == BLOCKED_MISSING_INPUT


def test_budget_drops_the_deepest_capabilities_not_arbitrary_ones(host_binding, registry):
    host, binding = host_binding
    plan = _compile(
        host, binding, registry, host["stones"][0], budget={"max_capabilities_per_room": 2}
    )
    dropped = [cap for cap in plan.planned if cap.admission == DROPPED_BUDGET]
    assert dropped
    assert len(plan.planned_registry_threads) == 2
    assert all(cap.detail.startswith("room budget") for cap in dropped)


def test_room_status_stays_planned_until_it_actually_runs(host_binding, registry):
    host, binding = host_binding
    plan = _compile(host, binding, registry, host["stones"][0])
    assert plan.status == "PLANNED"
    assert plan.actual_activated_threads == ()
    assert plan.run_id == ""


def test_compiler_is_pure_over_an_invented_registry():
    """No fixture, no engine: the compiler is just a closure over declarations."""

    registry = (
        CapabilitySpec("A", "reads base", ("Base",), ("Mid",), "R"),
        CapabilitySpec("B", "needs Mid", ("Mid",), ("Goal",), "R"),
        CapabilitySpec("C", "needs a ghost", ("Ghost",), ("Side",), "R"),
    )
    planned, states = compile_room(
        registry=registry,
        request=RoomRequest(
            desired_output_states=("Goal",),
            available_base_states=("Base",),
            granted_rights=frozenset({"R"}),
        ),
        thread_binding={"A": ("a",), "B": ("b",), "C": ("c",)},
    )
    ids = {cap.registry_id: cap.admission for cap in planned}
    assert ids == {"A": ADMITTED, "B": ADMITTED}
    assert "C" not in ids
    assert states["Goal"] == "SATISFIED_BY_CAPABILITY"


def test_cyclic_registry_does_not_hang_or_admit():
    registry = (
        CapabilitySpec("X", "", ("Y",), ("Z",), "R"),
        CapabilitySpec("Y", "", ("Z",), ("Y",), "R"),
    )
    planned, states = compile_room(
        registry=registry,
        request=RoomRequest(desired_output_states=("Z",), granted_rights=frozenset({"R"})),
        thread_binding={"X": ("x",), "Y": ("y",)},
    )
    assert all(cap.admission != ADMITTED for cap in planned)
    assert states["Z"] != "SATISFIED_BY_CAPABILITY"


def test_fixture_copies_do_not_drift():
    """The packaged resource and the test fixture must stay byte-identical."""

    from seshat.fabric_waves.m5_room_carpet import packaged_fixture_path

    packaged = packaged_fixture_path()
    assert packaged is not None, "fixture is not packaged; installed CLI would break"
    assert packaged.read_bytes() == FIXTURE.read_bytes()


def test_manifest_json_round_trips(host_binding, registry):
    host, binding = host_binding
    plan = _compile(host, binding, registry, host["stones"][0])
    data = json.loads(json.dumps(plan.to_dict()))
    assert data["planned_capabilities"]
    assert data["state_status"]["Resonance"] == "SATISFIED_BY_CAPABILITY"
    assert "must_wave" not in json.dumps(data)
