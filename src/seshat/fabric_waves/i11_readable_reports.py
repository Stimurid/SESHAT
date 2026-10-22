"""Human-readable private R01/R02 from typed ActionEvents.

This is an observed-mode projection of already-typed state, not a new model
run and not a substitute for the original stdout. Layer qualifications stay
with the typed relation_mode. A listed editor is not a performed research
operation; a proposal is not an operational alliance.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from seshat.fabric_waves.i11_activity_network import (
    ActionEvent,
    ActivityNetworkState,
    Actor,
)

LAYER_TITLES = {
    "RP": "Research production (RP)",
    "SS": "Studied system (SS)",
    "FT": "Formal / institutional titles (FT)",
    "PO": "Publication or patent listing (PO)",
    "BR": "Bridges between layers (BR)",
    "IM": "Implementation (IM)",
    "PR": "Proposed cooperation (PR)",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _actor_map(state: ActivityNetworkState) -> dict[str, Actor]:
    return {actor.actor_id: actor for actor in state.actors}


def _pages(event: ActionEvent) -> list[int]:
    return [address.page for address in event.source_addresses if address.page is not None]


def _locator_phrase(event: ActionEvent) -> str:
    pages = _pages(event)
    if pages:
        shown = ", ".join(f"p.{page}" for page in pages)
        return shown
    return "page UNKNOWN"


def _mentions_figure(text: str) -> bool:
    folded = text.casefold()
    return "figure 1" in folded or "fig 1" in folded or "fig. 1" in folded


def refuse_false_event_promotions(event: ActionEvent, actors: dict[str, Actor]) -> None:
    editorial = False
    for actor_id in event.actor_ids:
        actor = actors.get(actor_id)
        if actor and "EDITOR" in actor.actor_type.upper():
            editorial = True
    verb = event.verb.casefold()
    if editorial and event.layer == "RP":
        raise ValueError("I11_EDITOR_PROMOTION")
    if editorial and event.layer != "FT" and "editor" in verb:
        raise ValueError("I11_EDITOR_PROMOTION")
    if event.layer == "PR" and event.relation_mode == "SOURCE_ASSERTED_OPERATION":
        raise ValueError("I11_PLANNED_NOT_ACTIVE")


def qualify_event(event: ActionEvent, actors: dict[str, Actor]) -> list[str]:
    refuse_false_event_promotions(event, actors)
    marks: list[str] = []
    editorial = any(
        "EDITOR" in (actors.get(actor_id).actor_type.upper() if actors.get(actor_id) else "")
        for actor_id in event.actor_ids
    )
    if event.layer == "FT" or event.relation_mode == "SOURCE_ASSERTED_FORMAL_ROLE":
        marks.append("LISTED_FORMAL_ROLE_NOT_PERFORMED_RESEARCH_OPERATION")
    if editorial:
        marks.append("LISTED_EDITOR_NOT_PERFORMED_MANUSCRIPT_ACTION")
    if event.layer == "PR" or event.relation_mode == "SOURCE_PROPOSED_COOPERATION":
        marks.append("PROPOSAL_NOT_OPERATIONAL_ALLIANCE")
    if event.layer == "IM":
        marks.append("IMPLEMENTATION_EMPTY_OR_UNKNOWN")
    inferential = False
    for actor_id in event.actor_ids:
        actor = actors.get(actor_id)
        if actor is None:
            continue
        blob = " ".join((actor.work_scoped_identity, *actor.unknowns)).casefold()
        if "initial" in blob or "infer" in blob:
            inferential = True
    if inferential:
        marks.append("ANALYST_INITIALS_IDENTITY_INFERENTIAL")
    figure_bits = [event.verb, *(address.excerpt for address in event.source_addresses)]
    figure_bits.extend(address.locator or "" for address in event.source_addresses)
    if any(_mentions_figure(bit) for bit in figure_bits):
        marks.append("FIGURE_GRAPHIC_UNREAD_UNKNOWN")
    if event.relation_mode == "UNKNOWN":
        marks.append("OPERATOR_OR_OUTCOME_UNKNOWN")
    return marks


def _actor_labels(event: ActionEvent, actors: dict[str, Actor]) -> str:
    names: list[str] = []
    for actor_id in event.actor_ids:
        actor = actors.get(actor_id)
        if actor is None:
            names.append(f"{actor_id} (UNKNOWN)")
            continue
        names.append(f"{actor.work_scoped_identity} [{actor.actor_type}]")
    return "; ".join(names) if names else "UNKNOWN operator"


def _event_paragraph(event: ActionEvent, actors: dict[str, Actor]) -> dict[str, Any]:
    qualifications = qualify_event(event, actors)
    excerpt = event.source_addresses[0].excerpt if event.source_addresses else ""
    paragraph = (
        f"{event.event_id} ({_locator_phrase(event)}; {event.layer}/{event.relation_mode}): "
        f"{_actor_labels(event, actors)} — {event.verb}."
    )
    if "LISTED_EDITOR_NOT_PERFORMED_MANUSCRIPT_ACTION" in qualifications:
        paragraph += (
            " The source lists an editorial name; this is not evidence that the editor "
            "performed a research operation on the manuscript."
        )
    if "LISTED_FORMAL_ROLE_NOT_PERFORMED_RESEARCH_OPERATION" in qualifications:
        paragraph += " Treat this as a listed formal or institutional role, not RP labor."
    if "PROPOSAL_NOT_OPERATIONAL_ALLIANCE" in qualifications:
        paragraph += " This remains a proposal, not an operational alliance."
    if "ANALYST_INITIALS_IDENTITY_INFERENTIAL" in qualifications:
        paragraph += " Initials-to-person mapping stays inferential."
    if "FIGURE_GRAPHIC_UNREAD_UNKNOWN" in qualifications:
        paragraph += " Figure graphic content is unread and stays UNKNOWN."
    if "IMPLEMENTATION_EMPTY_OR_UNKNOWN" in qualifications:
        paragraph += " No measured implementation efficacy is evidenced."
    return {
        "event_id": event.event_id,
        "layer": event.layer,
        "relation_mode": event.relation_mode,
        "verb": event.verb,
        "actors": _actor_labels(event, actors),
        "pages": _pages(event),
        "locator": _locator_phrase(event),
        "excerpt_sha256": _sha(excerpt.encode("utf-8")) if excerpt else None,
        "qualifications": qualifications,
        "paragraph": paragraph,
    }


def _next_tests(state: ActivityNetworkState, records: list[dict[str, Any]]) -> list[str]:
    tests = [
        "Read any referenced figure as an image; caption text is not graphic content.",
        "Run the same authorial method on a second admitted original, not an invented control.",
        "Keep person, role, operation, product and planned-link identity tests separate.",
        "Owner science review remains required; this projection is not acceptance.",
    ]
    if not any(event.layer == "IM" and event.relation_mode != "UNKNOWN" for event in state.action_events):
        tests.insert(0, "Implementation stays empty/unknown until a source reports measured uptake.")
    if any("FIGURE_GRAPHIC_UNREAD_UNKNOWN" in item["qualifications"] for item in records):
        tests.insert(0, "Figure-1 geometry cannot be inferred from nearby prose.")
    return tests


def compose_readable_r01r02(
    state: ActivityNetworkState,
    *,
    job_id: str,
    stdout_sha256: str,
    source_sha256: str,
    hub_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    if state.customer_release != "BLOCKED":
        raise ValueError("I11_CUSTOMER_RELEASE_BLOCKED")
    if state.scientific_acceptance != "NOT_ASSERTED":
        raise ValueError("I11_HUMAN_APPROVAL_FORBIDDEN")
    actors = _actor_map(state)
    records = [_event_paragraph(event, actors) for event in state.action_events]
    by_layer: dict[str, list[dict[str, Any]]] = {key: [] for key in LAYER_TITLES}
    for record in records:
        by_layer.setdefault(record["layer"], []).append(record)
    im_events = by_layer.get("IM") or []
    im_status = "EMPTY_OR_UNKNOWN"
    if im_events and all(
        "IMPLEMENTATION_EMPTY_OR_UNKNOWN" in item["qualifications"] or item["relation_mode"] == "UNKNOWN"
        for item in im_events
    ):
        im_status = "EMPTY_OR_UNKNOWN"
    elif im_events:
        im_status = "REPORTED_NOT_EFFICACY"

    r01_lines = [
        "# R01. How the research result was produced",
        "",
        "This reconstruction is a network of typed ActionEvents, not a byline list. "
        "Each event keeps performer or UNKNOWN, operation, page locator, and statement type.",
        "",
    ]
    for layer, title in LAYER_TITLES.items():
        r01_lines.append(f"## {title}")
        items = by_layer.get(layer) or []
        if not items:
            if layer == "IM":
                r01_lines.append(
                    "IM is empty/unknown: the typed network does not evidence a measured "
                    "implementation outcome."
                )
            else:
                r01_lines.append("No typed events in this layer; absence is not negative proof.")
        for item in items:
            r01_lines.append(item["paragraph"])
        r01_lines.append("")

    r02_lines = [
        "# R02. Relation types and source grounding",
        "",
        "Edges remain typed. A listed formal role is not RP labor. A studied-system "
        "report is not an independently measured organizational fact. A publication "
        "listing is not proof of every empirical act. A proposal is not an alliance.",
        "",
    ]
    for relation in state.relations:
        pages = [
            f"p.{address.page}" for address in relation.source_addresses if address.page is not None
        ]
        r02_lines.append(
            f"{relation.from_id} —{relation.relation_type}/{relation.layer}/{relation.relation_mode}→ "
            f"{relation.to_id} ({', '.join(pages) if pages else 'page UNKNOWN'})."
        )
    r02_lines.append("")
    r02_lines.append("## Explicit non-equivalences and contradictions")
    if state.explicit_non_equivalences:
        for item in state.explicit_non_equivalences:
            r02_lines.append(f"- {item}")
    else:
        r02_lines.append("- None were typed beyond layer qualifications.")
    next_tests = _next_tests(state, records)
    r02_lines.append("")
    r02_lines.append("## Next source-differentiating tests")
    for item in next_tests:
        r02_lines.append(f"- {item}")

    markdown = "\n".join(
        [
            *r01_lines,
            *r02_lines,
            "",
            "# Provenance",
            f"job_id={job_id}",
            f"stdout_sha256={stdout_sha256}",
            f"source_sha256={source_sha256}",
            f"hub_receipt_sha256={hub_receipt_sha256 or 'UNKNOWN'}",
            "provenance=SELF_OBSERVED_UNATTESTED",
            "scientific_acceptance=NOT_PERFORMED",
            "customer_release=BLOCKED",
            "license_note=Publication CC BY is not independent F07 attestation.",
            "Original model stdout is preserved and not rewritten.",
            "",
        ]
    )
    content = {
        "schema": "seshat.operator_private_r01r02.readable.v1",
        "visibility": "OWNER_PRIVATE_ONLY",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "source_rights": "OPERATOR_DECLARED_UNATTESTED",
        "publication_license": "CC_BY_NOT_F07_ATTESTATION",
        "model_run_attested": False,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "job_id": job_id,
        "stdout_sha256": stdout_sha256,
        "source_sha256": source_sha256,
        "hub_receipt_sha256": hub_receipt_sha256,
        "im_status": im_status,
        "reports": [
            {
                "report_id": "R01",
                "status": "SOURCE_GROUNDED_UNREVIEWED",
                "events": records,
                "narrative": "\n".join(r01_lines),
            },
            {
                "report_id": "R02",
                "status": "SOURCE_GROUNDED_UNREVIEWED",
                "relation_count": len(state.relations),
                "non_equivalences": list(state.explicit_non_equivalences),
                "next_tests": next_tests,
                "narrative": "\n".join(r02_lines),
            },
        ],
        "markdown": markdown,
    }
    return {**content, "projection_sha256": _sha(_canonical(content))}
