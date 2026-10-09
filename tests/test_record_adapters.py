from seshat.adapters.records import (
    d20_entity_observation,
    litops_segment_observation,
    tinkuy_fabric_observation,
)


def test_litops_segment_preserves_address() -> None:
    obs = litops_segment_observation(
        observation_id="o1",
        carrier_id="c1",
        segment_id="seg-7",
        char_start=100,
        char_end=200,
        content="text",
    )
    assert obs.producer == "litops"
    assert obs.addresses[0].selector["segment_id"] == "seg-7"
    assert obs.addresses[0].start == 100


def test_tinkuy_unit_is_observation_not_truth() -> None:
    obs = tinkuy_fabric_observation(
        observation_id="o2",
        carrier_id="c1",
        unit_id="u9",
        content={"move": "distinction"},
    )
    assert obs.observation_type == "tinkuy.fabric_unit"
    assert not hasattr(obs, "acceptance_state")


def test_d20_entity_stays_source_scoped() -> None:
    obs = d20_entity_observation(
        observation_id="o3",
        carrier_id="field-rev-3",
        entity_id="ENT:1",
        payload={"label": "Object"},
        anchor_ids=["ANC:1"],
    )
    assert obs.addresses[0].selector["entity_id"] == "ENT:1"
    assert obs.producer == "d20.fieldcore"
