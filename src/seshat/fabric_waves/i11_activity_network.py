"""Typed I11 ActivityNetworkState, grounding, and a fictional two-world interpreter.

This module never embeds authorial I11 prompt bytes or private corpus text.
The public CI path interprets a tiny pinned JSON MethodAsset against invented
UTF-8 worlds. Real I11_ACTIVITY_NETWORK@v1.0 bytes stay owner-private and are
only accepted when the operator supplies the exact published SHA pin.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import Field, model_validator

from seshat.corpus import FrozenModel
from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorClaim,
    OperatorInvocation,
)

NetworkLayer = Literal["RP", "SS", "FT", "PO", "BR", "IM", "PR"]
RelationMode = Literal[
    "SOURCE_ASSERTED_OPERATION",
    "SOURCE_ASSERTED_FORMAL_ROLE",
    "SOURCE_LISTED_PUBLICATION_OR_PATENT_COAUTHOR",
    "SOURCE_STUDIED_SYSTEM_ACTION",
    "SOURCE_REPORTED_IMPLEMENTATION",
    "SOURCE_PROPOSED_COOPERATION",
    "ANALYTIC_RECONSTRUCTION",
    "CREATIVE_NEXT_ASSEMBLY",
    "UNKNOWN",
]
TemporalStatus = Literal["ACTUAL", "REPORTED", "PROPOSED", "UNKNOWN"]

FICTIONAL_METHOD_SCHEMA = "SESHAT_I11_FICTIONAL_INTERPRETER_V1"
FICTIONAL_METHOD_ID = "seshat.i11.fictional_interpreter"
FICTIONAL_METHOD_VERSION = "v1"
AUTHORIAL_I11_ID = "I11_ACTIVITY_NETWORK"
AUTHORIAL_I11_VERSION = "v1.0"
# Published pin of the frozen authorial body. The bytes themselves are not here.
AUTHORIAL_I11_SHA256 = "4d566aa63d0803cdaf7f8c9ef0cf61ede7450fbf5d081492f92ad29963e55177"
# Published CC BY PLOS ONE 19(6):e0293107 PDF, admitted only as an open paper.
CCBY_PDF_SHA256 = "6977ad95a068674fe81aedc7d535265f36c0523e47c6674ebfebc6772596dc54"
CCBY_PAGES_SHA256 = "bf3adc1e698ea62086be7590e438b613bda924012b428d663fc46500955881f5"
OBSERVED_I11_JOB_ID = "jx-d35ed8af38ce"
OBSERVED_I11_STDOUT_SHA256 = "824be3626429e44d4aa5680f8d3973b3356a3ac1f758ecb0b35e9dc46bdd89fa"

WORLD_A_TEXT = (
    "INVENTED PUBLIC WORLD A — ORGANIZATIONAL SURVEY\n"
    "TITLE_PAGE: supervisor Dana Vale is listed on the title page.\n"
    "RP_AUTHOR: The author designed a questionnaire and analyzed the returned forms.\n"
    "SS_CLINIC: Hospital staff supplied anonymized routine-care entries.\n"
    "PO_PAPER: A listed paper names two publication coauthors: the author and Dana Vale.\n"
    "PR_FUTURE: A future joint registry is proposed, not yet formed.\n"
    "IM_ABSENT: No measured implementation outcome is reported.\n"
    "BR_HANDOFF: The author received the anonymized routine-care entries from hospital staff.\n"
    "UNKNOWN_TECH: The technician who digitized the forms is unnamed.\n"
)
WORLD_B_TEXT = (
    "INVENTED PUBLIC WORLD B — SHARED OPPONENT\n"
    "TITLE_PAGE: formal opponent Evan Cole is listed.\n"
    "RP_MEASURE: Only this study says Evan Cole collected the field measurements.\n"
    "RP_OPERATOR: The measurement operator on the second protocol is not named.\n"
    "IM_MEMO: A later memo reports implementation without a measured outcome.\n"
    "FT_SHARED: Formal opponent Evan Cole appears only as a title-page academic role.\n"
    "PO_NONE: No joint publication with World A is listed.\n"
)

_LABELS_A: tuple[tuple[str, NetworkLayer, RelationMode, str, tuple[str, ...]], ...] = (
    ("TITLE_PAGE", "FT", "SOURCE_ASSERTED_FORMAL_ROLE", "list_formal_supervisor", ("ft-supervisor",)),
    ("RP_AUTHOR", "RP", "SOURCE_ASSERTED_OPERATION", "design_and_analyze", ("rp-author",)),
    ("SS_CLINIC", "SS", "SOURCE_STUDIED_SYSTEM_ACTION", "supply_routine_entries", ("ss-staff",)),
    ("PO_PAPER", "PO", "SOURCE_LISTED_PUBLICATION_OR_PATENT_COAUTHOR", "list_coauthors", ("rp-author", "ft-supervisor")),
    ("PR_FUTURE", "PR", "SOURCE_PROPOSED_COOPERATION", "propose_registry", ("rp-author",)),
    ("IM_ABSENT", "IM", "UNKNOWN", "report_no_measured_outcome", ()),
    ("BR_HANDOFF", "BR", "SOURCE_ASSERTED_OPERATION", "receive_anonymized_entries", ("rp-author", "ss-staff")),
    ("UNKNOWN_TECH", "RP", "UNKNOWN", "digitize_forms", ("unknown-technician",)),
)
_LABELS_B: tuple[tuple[str, NetworkLayer, RelationMode, str, tuple[str, ...]], ...] = (
    ("TITLE_PAGE", "FT", "SOURCE_ASSERTED_FORMAL_ROLE", "list_formal_opponent", ("ft-opponent",)),
    ("RP_MEASURE", "RP", "SOURCE_ASSERTED_OPERATION", "collect_measurements", ("ft-opponent",)),
    ("RP_OPERATOR", "RP", "UNKNOWN", "operate_second_protocol", ("unknown-operator",)),
    ("IM_MEMO", "IM", "SOURCE_REPORTED_IMPLEMENTATION", "report_implementation", ()),
    ("FT_SHARED", "FT", "SOURCE_ASSERTED_FORMAL_ROLE", "remain_title_role", ("ft-opponent",)),
    ("PO_NONE", "PO", "UNKNOWN", "list_no_shared_publication", ()),
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SourceAddress(FrozenModel):
    carrier_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    byte_offset: int | None = Field(default=None, ge=0)
    byte_length: int | None = Field(default=None, ge=1)
    page: int | None = Field(default=None, ge=1)
    locator: str | None = None


class InputCarrier(FrozenModel):
    carrier_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    rights: str = Field(min_length=1)


class Actor(FrozenModel):
    actor_id: str = Field(min_length=1)
    actor_type: str = Field(min_length=1)
    work_scoped_identity: str = Field(min_length=1)
    source_addresses: tuple[SourceAddress, ...] = ()
    unknowns: tuple[str, ...] = ()


class ActionEvent(FrozenModel):
    event_id: str = Field(min_length=1)
    actor_ids: tuple[str, ...] = ()
    verb: str = Field(min_length=1)
    affected_entities: tuple[str, ...] = ()
    layer: NetworkLayer
    source_addresses: tuple[SourceAddress, ...] = Field(min_length=1)
    relation_mode: RelationMode
    time_or_unknown: TemporalStatus = "UNKNOWN"


class RelationEdge(FrozenModel):
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    layer: NetworkLayer
    source_addresses: tuple[SourceAddress, ...] = ()
    relation_mode: RelationMode


class BibliographicOutput(FrozenModel):
    output_id: str = Field(min_length=1)
    output_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    year: str = "UNKNOWN"
    listed_author_ids: tuple[str, ...] = ()
    source_address: SourceAddress | None = None
    distribution_of_labor: Literal["UNKNOWN"] = "UNKNOWN"


class ActivityNetworkState(FrozenModel):
    work_id: str = Field(min_length=1)
    input_carriers: tuple[InputCarrier, ...] = Field(min_length=1)
    methodbody_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model_job_receipt_or_null: str | None = None
    actors: tuple[Actor, ...]
    action_events: tuple[ActionEvent, ...] = Field(min_length=1)
    relations: tuple[RelationEdge, ...] = ()
    bibliographic_outputs: tuple[BibliographicOutput, ...] = ()
    proposed_cooperations: tuple[str, ...] = ()
    cross_work_identity_candidates: tuple[str, ...] = ()
    explicit_non_equivalences: tuple[str, ...] = ()
    unknown_roles: tuple[str, ...] = ()
    alternative_networks: tuple[str, ...] = ()
    downstream_requests: tuple[str, ...] = ()
    stop_reason: str = "COMPLETED_FICTIONAL_INTERPRETER"
    customer_surfaces: tuple[str, ...] = ("I11", "C07", "C13", "R03", "R07", "R08", "R09")
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["BLOCKED"] = "BLOCKED"
    provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"

    @model_validator(mode="after")
    def refuse_false_authority(self) -> ActivityNetworkState:
        if self.scientific_acceptance != "NOT_ASSERTED":
            raise ValueError("I11_HUMAN_APPROVAL_FORBIDDEN")
        if self.customer_release != "BLOCKED":
            raise ValueError("I11_CUSTOMER_RELEASE_BLOCKED")
        return self


def fictional_method_bytes() -> bytes:
    return json.dumps(
        {
            "schema": FICTIONAL_METHOD_SCHEMA,
            "operation": "labeled_activity_network",
            "methodbody_id": FICTIONAL_METHOD_ID,
            "version": FICTIONAL_METHOD_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def world_bytes(world: Literal["world_a", "world_b"]) -> bytes:
    if world == "world_a":
        return WORLD_A_TEXT.encode("utf-8")
    if world == "world_b":
        return WORLD_B_TEXT.encode("utf-8")
    raise ValueError("I11_FIXTURE_UNKNOWN")


def _span(source_bytes: bytes, needle: str, carrier_id: str) -> SourceAddress:
    raw = needle.encode("utf-8")
    offset = source_bytes.find(raw)
    if offset < 0:
        raise ValueError("I11_FORGED_LOCATOR")
    return SourceAddress(
        carrier_id=carrier_id,
        excerpt=needle,
        byte_offset=offset,
        byte_length=len(raw),
    )


def _line_for(source_text: str, label: str) -> str:
    prefix = f"{label}: "
    for line in source_text.splitlines():
        if line.startswith(prefix):
            return line
    raise ValueError("I11_PARTIAL_SOURCE")


def _actors_for(world: str, source_bytes: bytes, carrier_id: str) -> tuple[Actor, ...]:
    if world == "world_a":
        specs = (
            ("rp-author", "person", "author", "RP_AUTHOR", ()),
            ("ft-supervisor", "person", "Dana Vale", "TITLE_PAGE", ("title-only-supervisor",)),
            ("ss-staff", "organization_role", "hospital staff", "SS_CLINIC", ()),
            ("unknown-technician", "person", "unnamed technician", "UNKNOWN_TECH", ("identity",)),
        )
    else:
        specs = (
            ("ft-opponent", "person", "Evan Cole", "TITLE_PAGE", ()),
            ("unknown-operator", "person", "unnamed operator", "RP_OPERATOR", ("identity",)),
        )
    text = source_bytes.decode("utf-8")
    actors = []
    for actor_id, actor_type, identity, label, unknowns in specs:
        actors.append(
            Actor(
                actor_id=actor_id,
                actor_type=actor_type,
                work_scoped_identity=identity,
                source_addresses=(_span(source_bytes, _line_for(text, label), carrier_id),),
                unknowns=unknowns,
            )
        )
    return tuple(actors)


def interpret_labeled_world(
    *,
    world: Literal["world_a", "world_b"],
    source_bytes: bytes,
    method_bytes: bytes,
) -> ActivityNetworkState:
    spec = _require_fictional_method(method_bytes)
    expected = world_bytes(world)
    if source_bytes != expected:
        raise ValueError("I11_VERSION_DRIFT")
    carrier_id = f"public-invented-{world}"
    text = source_bytes.decode("utf-8")
    labels = _LABELS_A if world == "world_a" else _LABELS_B
    events = []
    for label, layer, mode, verb, actor_ids in labels:
        line = _line_for(text, label)
        events.append(
            ActionEvent(
                event_id=f"{world}-{label.lower()}",
                actor_ids=actor_ids,
                verb=verb,
                affected_entities=(label,),
                layer=layer,
                source_addresses=(_span(source_bytes, line, carrier_id),),
                relation_mode=mode,
                time_or_unknown="PROPOSED" if layer == "PR" else "REPORTED",
            )
        )
    relations: list[RelationEdge] = []
    if world == "world_a":
        relations.append(
            RelationEdge(
                from_id="ft-supervisor",
                to_id="rp-author",
                relation_type="FORMAL_SUPERVISOR_NOT_AUTOMATIC_RP",
                layer="FT",
                source_addresses=(_span(source_bytes, _line_for(text, "TITLE_PAGE"), carrier_id),),
                relation_mode="SOURCE_ASSERTED_FORMAL_ROLE",
            )
        )
        relations.append(
            RelationEdge(
                from_id="rp-author",
                to_id="ss-staff",
                relation_type="DOCUMENTED_HANDOFF",
                layer="BR",
                source_addresses=(_span(source_bytes, _line_for(text, "BR_HANDOFF"), carrier_id),),
                relation_mode="SOURCE_ASSERTED_OPERATION",
            )
        )
    else:
        relations.append(
            RelationEdge(
                from_id="ft-opponent",
                to_id="unknown-operator",
                relation_type="SHARED_FORMAL_ROLE_NOT_SHARED_TEAM",
                layer="FT",
                source_addresses=(_span(source_bytes, _line_for(text, "FT_SHARED"), carrier_id),),
                relation_mode="SOURCE_ASSERTED_FORMAL_ROLE",
            )
        )
    outputs = ()
    if world == "world_a":
        outputs = (
            BibliographicOutput(
                output_id="world-a-paper",
                output_type="article",
                title="invented listed paper",
                year="UNKNOWN",
                listed_author_ids=("rp-author", "ft-supervisor"),
                source_address=_span(source_bytes, _line_for(text, "PO_PAPER"), carrier_id),
            ),
        )
    return ActivityNetworkState(
        work_id=f"invented-{world}",
        input_carriers=(
            InputCarrier(
                carrier_id=carrier_id,
                version="invented-v1",
                scope="FULL_UTF8",
                rights="operator-created-public-test-fixture",
            ),
        ),
        methodbody_id=spec["methodbody_id"],
        version=spec["version"],
        actors=_actors_for(world, source_bytes, carrier_id),
        action_events=tuple(events),
        relations=tuple(relations),
        bibliographic_outputs=outputs,
        proposed_cooperations=("future joint registry",) if world == "world_a" else (),
        explicit_non_equivalences=(
            "supervisor-title-is-not-rp-labor",
            "hospital-staff-are-not-publication-authors",
            "proposed-registry-is-not-an-active-alliance",
        ) if world == "world_a" else (
            "shared-opponent-is-not-shared-research-team",
            "reported-implementation-is-not-efficacy",
            "unnamed-operator-stays-unknown",
        ),
        unknown_roles=("unnamed technician",) if world == "world_a" else ("unnamed operator",),
        stop_reason="COMPLETED_FICTIONAL_INTERPRETER",
    )


def _require_fictional_method(method_bytes: bytes) -> dict[str, Any]:
    try:
        spec = json.loads(method_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("I11_METHOD_PIN_MISMATCH") from exc
    expected = {
        "schema": FICTIONAL_METHOD_SCHEMA,
        "operation": "labeled_activity_network",
        "methodbody_id": FICTIONAL_METHOD_ID,
        "version": FICTIONAL_METHOD_VERSION,
    }
    if spec != expected:
        raise ValueError("I11_METHOD_PIN_MISMATCH")
    return spec


def execute_fictional_i11(invocation: OperatorInvocation) -> OperatorBodyResult:
    _require_fictional_method(invocation.method_body_invocation_bytes)
    if invocation.source_id == "public-invented-world_a":
        world: Literal["world_a", "world_b"] = "world_a"
    elif invocation.source_id == "public-invented-world_b":
        world = "world_b"
    else:
        raise ValueError("I11_FIXTURE_UNKNOWN")
    state = interpret_labeled_world(
        world=world,
        source_bytes=invocation.source_bytes,
        method_bytes=invocation.method_body_invocation_bytes,
    )
    validate_activity_network(state, invocation.source_bytes)
    claims = tuple(_claim_from_event(event) for event in state.action_events)
    return OperatorBodyResult(
        research_object_id=state.work_id,
        claims=claims,
        notes=(
            "fictional_i11_interpreter",
            json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False),
        ),
    )


def _claim_from_event(event: ActionEvent) -> OperatorClaim:
    address = event.source_addresses[0]
    if address.byte_offset is None or address.byte_length is None:
        raise ValueError("I11_PAGE_MAP_REQUIRED")
    return OperatorClaim(
        text=f"{event.layer}:{event.verb}",
        evidence_excerpt=address.excerpt,
        byte_offset=address.byte_offset,
        byte_length=address.byte_length,
    )


def ground_address(address: SourceAddress, source_bytes: bytes) -> None:
    if not source_bytes:
        raise ValueError("I11_PARTIAL_SOURCE")
    if address.byte_offset is None or address.byte_length is None:
        raise ValueError("I11_PAGE_MAP_REQUIRED")
    end = address.byte_offset + address.byte_length
    if end > len(source_bytes):
        raise ValueError("I11_FORGED_LOCATOR")
    span = source_bytes[address.byte_offset:end]
    if span != address.excerpt.encode("utf-8"):
        raise ValueError("I11_FORGED_LOCATOR")


def validate_activity_network(
    state: ActivityNetworkState,
    source_bytes: bytes,
    *,
    expected_source_sha256: str | None = None,
    denied_source_ids: frozenset[str] = frozenset(),
    human_accepted: bool = False,
    customer_release_authorized: bool = False,
    required_sections: tuple[str, ...] = ("actors", "action_events", "relations"),
    model_payload: dict[str, Any] | None = None,
) -> None:
    if human_accepted:
        raise ValueError("I11_HUMAN_APPROVAL_FORBIDDEN")
    if customer_release_authorized:
        raise ValueError("I11_CUSTOMER_RELEASE_BLOCKED")
    if not source_bytes:
        raise ValueError("I11_PARTIAL_SOURCE")
    if expected_source_sha256 and _sha(source_bytes) != expected_source_sha256:
        raise ValueError("I11_STALE_REPORT")
    for carrier in state.input_carriers:
        if carrier.carrier_id in denied_source_ids:
            raise ValueError("I11_DENIED_SOURCE")
    if model_payload is not None:
        for section in required_sections:
            if section not in model_payload or not model_payload[section]:
                raise ValueError("I11_TRUNCATED_MODEL_OUTPUT")
    for event in state.action_events:
        for address in event.source_addresses:
            ground_address(address, source_bytes)
        _enforce_layer_negatives(event, state)
    for relation in state.relations:
        for address in relation.source_addresses:
            ground_address(address, source_bytes)
        if relation.relation_type == "SAME_RESEARCH_TEAM" and relation.layer == "FT":
            raise ValueError("I11_FALSE_SHARED_TEAM")
        if relation.relation_mode == "SOURCE_PROPOSED_COOPERATION" and (
            relation.relation_type in {"ACTIVE_ALLIANCE", "EXISTING_CONSORTIUM"}
        ):
            raise ValueError("I11_PLANNED_NOT_ACTIVE")


def _enforce_layer_negatives(event: ActionEvent, state: ActivityNetworkState) -> None:
    actors = {actor.actor_id: actor for actor in state.actors}
    if event.layer == "RP":
        for actor_id in event.actor_ids:
            actor = actors.get(actor_id)
            if actor is None:
                continue
            title_only = (
                actor.actor_id == "ft-supervisor"
                or "title-only-supervisor" in actor.unknowns
            )
            if (
                event.relation_mode == "SOURCE_ASSERTED_FORMAL_ROLE"
                and title_only
                and event.verb not in {"collect_measurements"}
            ):
                raise ValueError("I11_SUPERVISOR_NOT_RESEARCHER")
            if actor.actor_id == "unknown-operator" and event.relation_mode != "UNKNOWN":
                raise ValueError("I11_UNKNOWN_OPERATOR_REQUIRED")
            if "credit-supervision" in event.affected_entities:
                raise ValueError("I11_CREDIT_NOT_RP")
    if event.layer == "PO":
        for actor_id in event.actor_ids:
            actor = actors.get(actor_id)
            if actor and actor.actor_id == "ss-staff":
                raise ValueError("I11_STAFF_NOT_AUTHOR")
    if event.layer == "IM" and "efficacy" in event.verb:
        raise ValueError("I11_IMPLEMENTATION_NOT_EFFICACY")
    if event.layer == "PR" and event.relation_mode == "SOURCE_ASSERTED_OPERATION":
        raise ValueError("I11_PLANNED_NOT_ACTIVE")


def collapse_probe_state(
    *,
    code: str,
    world: Literal["world_a", "world_b"] = "world_a",
) -> ActivityNetworkState:
    """Build an intentionally illegal state for a named red probe."""
    source_bytes = world_bytes(world)
    good = interpret_labeled_world(
        world=world, source_bytes=source_bytes, method_bytes=fictional_method_bytes()
    )
    events = list(good.action_events)
    relations = list(good.relations)
    if code == "I11_SUPERVISOR_NOT_RESEARCHER":
        events[0] = events[0].model_copy(
            update={"layer": "RP", "relation_mode": "SOURCE_ASSERTED_FORMAL_ROLE",
                    "verb": "inferred_researcher", "actor_ids": ("ft-supervisor",)}
        )
    elif code == "I11_STAFF_NOT_AUTHOR":
        paper = next(event for event in events if event.layer == "PO")
        idx = events.index(paper)
        events[idx] = paper.model_copy(update={"actor_ids": ("ss-staff",)})
    elif code == "I11_PLANNED_NOT_ACTIVE":
        proposed = next(event for event in events if event.layer == "PR")
        idx = events.index(proposed)
        events[idx] = proposed.model_copy(update={"relation_mode": "SOURCE_ASSERTED_OPERATION"})
    elif code == "I11_IMPLEMENTATION_NOT_EFFICACY":
        source_bytes = world_bytes("world_b")
        good = interpret_labeled_world(
            world="world_b", source_bytes=source_bytes, method_bytes=fictional_method_bytes()
        )
        events = list(good.action_events)
        im_event = next(event for event in events if event.layer == "IM")
        events[events.index(im_event)] = im_event.model_copy(update={"verb": "prove_efficacy"})
        return good.model_copy(update={"action_events": tuple(events)})
    elif code == "I11_FALSE_SHARED_TEAM":
        source_bytes = world_bytes("world_b")
        good = interpret_labeled_world(
            world="world_b", source_bytes=source_bytes, method_bytes=fictional_method_bytes()
        )
        relations = [
            rel.model_copy(update={"relation_type": "SAME_RESEARCH_TEAM"})
            for rel in good.relations
        ]
        return good.model_copy(update={"relations": tuple(relations)})
    elif code == "I11_UNKNOWN_OPERATOR_REQUIRED":
        source_bytes = world_bytes("world_b")
        good = interpret_labeled_world(
            world="world_b", source_bytes=source_bytes, method_bytes=fictional_method_bytes()
        )
        events = list(good.action_events)
        unknown = next(event for event in events if "unknown-operator" in event.actor_ids)
        events[events.index(unknown)] = unknown.model_copy(
            update={"relation_mode": "SOURCE_ASSERTED_OPERATION"}
        )
        return good.model_copy(update={"action_events": tuple(events)})
    elif code == "I11_CREDIT_NOT_RP":
        events[1] = events[1].model_copy(update={"affected_entities": ("credit-supervision",)})
    else:
        raise ValueError("I11_PROBE_UNKNOWN")
    return good.model_copy(update={"action_events": tuple(events), "relations": tuple(relations)})


__all__ = [
    "AUTHORIAL_I11_ID",
    "AUTHORIAL_I11_SHA256",
    "AUTHORIAL_I11_VERSION",
    "ActivityNetworkState",
    "ActionEvent",
    "Actor",
    "BibliographicOutput",
    "CCBY_PAGES_SHA256",
    "CCBY_PDF_SHA256",
    "FICTIONAL_METHOD_ID",
    "FICTIONAL_METHOD_VERSION",
    "InputCarrier",
    "OBSERVED_I11_JOB_ID",
    "OBSERVED_I11_STDOUT_SHA256",
    "RelationEdge",
    "SourceAddress",
    "WORLD_A_TEXT",
    "WORLD_B_TEXT",
    "collapse_probe_state",
    "execute_fictional_i11",
    "fictional_method_bytes",
    "ground_address",
    "interpret_labeled_world",
    "validate_activity_network",
    "world_bytes",
]
