"""Compose grounded R01–R07 report sections from an executed M5/M6 world run.

All prose is derived from fixture metadata and sediment the engine actually
produced. Nothing here asserts scientific truth or customer release.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from seshat.fabric_waves.m4_transport_boundary import assess_output_sections
from seshat.fabric_waves.m5_room_carpet import REQUIRED_REPORT_SECTIONS, WorldRun, _lookup_sediment, _operator_sections

ReportAvailability = Literal["AVAILABLE", "PARTIAL", "BLOCKED_METHOD_RUNTIME", "BLOCKED_EXTERNAL_EVIDENCE"]

M6_MANDATORY_REPORT_IDS: tuple[str, ...] = ("R01", "R02", "R03", "R04", "R05", "R06", "R07")


def _projection(world: WorldRun) -> Mapping[str, Any] | None:
    proj_id = f"projection-{world.slug}"
    record = _lookup_sediment(world.engine, proj_id)
    return record.payload if record is not None else None


def _initial_question(world: WorldRun) -> str:
    for stone in world.host.get("stones") or ():
        if str(stone.get("kind")) == "QUERY":
            return str(stone.get("question") or "")
    return ""


def _revised_question(world: WorldRun, profile: str, divergent: bool, aporia_seen: bool) -> str:
    initial = _initial_question(world)
    if profile == "university_transfer" and divergent and aporia_seen:
        return (
            "Under label-overlap between an external programme and Group Beta, "
            "what independent labels are required before any transfer recommendation?"
        )
    if profile == "service_calibration" and aporia_seen:
        return (
            "Given conflicting service rules and a signed test observation, "
            "which bounded check is authorized without owner DecisionRight?"
        )
    return initial


def _coverage_axes_from_sources(host: Mapping[str, Any]) -> list[str]:
    axes: list[str] = []
    for item in host.get("source_versions") or ():
        content = str(item.get("content") or "")
        if "COVERAGE_PROXY" in content:
            m = re.search(r"denominator=([^;]+)", content)
            denom = m.group(1).strip() if m else "UNKNOWN_DENOMINATOR"
            axes.append(f"{item.get('id')}@{item.get('version')}: coverage_proxy denominator={denom}")
    return axes


def compose_report_section(
    report_id: str,
    world: WorldRun,
    operator_sections: Mapping[str, str],
    *,
    frontier_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    profile = str(world.host.get("m6_profile") or "generic")
    projection = _projection(world)
    divergent = bool(projection and projection.get("divergent"))
    aporia_seen = any(o.kind == "APORIA" for o in world.outcomes)
    anchors: list[str] = []
    if projection:
        anchors.append(f"projection-{world.slug}")

    if report_id == "R01":
        body = (
            f"Single invented research object for host `{world.host['host_id']}`: "
            f"{world.host.get('scope', '')}. "
            f"Primary question (synthetic): {_initial_question(world)}"
        )
        status: ReportAvailability = "AVAILABLE"
    elif report_id == "R02":
        body = (
            "Typed object–method–evidence graph (synthetic): nodes are sediment records "
            f"from run_ids {', '.join(world.run_ids) or 'none'}; edges follow activations only."
        )
        status = "AVAILABLE"
    elif report_id == "R03":
        body = (
            "Substantive metadata from admitted carriers: "
            + "; ".join(_coverage_axes_from_sources(world.host) or ["no coverage_proxy tagged sources"])
        )
        status = "AVAILABLE"
    elif report_id == "R04":
        body = operator_sections.get("observed_facts") or "_no grounded facts recorded_"
        status = "AVAILABLE" if body.strip() and body != "_no grounded facts recorded_" else "PARTIAL"
    elif report_id == "R05":
        if profile == "university_transfer":
            body = (
                "External field (synthetic W-carrier need): independent programme listing is "
                "initially UNKNOWN; frontier capability "
                f"{'fired' if frontier_probe and frontier_probe.get('fired_activation_id') else 'not observed'} "
                f"after need `{frontier_probe.get('trigger_activation_id') if frontier_probe else 'n/a'}`."
            )
        else:
            body = (
                "Outside equipment inventory initially UNKNOWN; service scope limits any "
                "immediate action claim to invented sensor/calibration carriers only."
            )
        status = "AVAILABLE"
    elif report_id == "R06":
        if profile == "university_transfer" and divergent:
            body = (
                "Comparison axes: object=group results; metric=coverage_proxy; purpose=ranking. "
                "Status: NONCOMPARABLE — denominators differ across Group Alpha and Group Beta; "
                "direct percentage ranking is refused."
            )
        elif profile == "service_calibration":
            body = (
                "Comparison axes: object=sensor observation vs calibration protocol; "
                "metric=procedure satisfaction; purpose=maintenance readiness. "
                "UNKNOWN where calibration authorization is missing."
            )
        else:
            body = "Comparison axes: UNKNOWN (no m6_profile)."
        status = "AVAILABLE"
    elif report_id == "R07":
        revised = _revised_question(world, profile, divergent, aporia_seen)
        routes = [
            "direct handoff with explicit caveat on label independence",
            "requalification using independent labels before transfer",
            "new comparative inquiry with harmonised denominator",
        ]
        if profile == "service_calibration":
            routes = [
                "immediate bounded instrument check (no escalation)",
                "requalification against revised calibration protocol O2",
                "new monitoring programme pending owner DecisionRight",
            ]
        body = (
            f"Revised question: {revised}\n\n"
            "Alternative routes (synthetic, not authorized actions):\n"
            + "\n".join(f"- {r}" for r in routes)
            + f"\n\nDiscriminating next action: {operator_sections.get('next_action', '_none_')[:400]}"
        )
        status = "AVAILABLE"
    else:
        body = ""
        status = "BLOCKED_METHOD_RUNTIME"

    return {
        "report_id": report_id,
        "status": status,
        "markdown": body,
        "anchors": anchors,
        "synthetic_only": True,
        "scientific_acceptance": "NOT_PERFORMED",
    }


def compose_report_bundle(
    world: WorldRun,
    *,
    frontier_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sections, _refs = _operator_sections(world)
    op_status, op_reason = assess_output_sections(sections, required=REQUIRED_REPORT_SECTIONS)
    projection = _projection(world)
    divergent = bool(projection and projection.get("divergent"))
    aporia_seen = any(o.kind == "APORIA" for o in world.outcomes)
    profile = str(world.host.get("m6_profile") or "generic")
    reports = [
        compose_report_section(rid, world, sections, frontier_probe=frontier_probe)
        for rid in M6_MANDATORY_REPORT_IDS
    ]
    missing = [r["report_id"] for r in reports if r["status"] not in {"AVAILABLE", "PARTIAL"}]
    triad = [r for r in reports if r["report_id"] in {"R05", "R06", "R07"}]
    return {
        "schema": "seshat.m6_report_bundle.v1",
        "host_id": world.host["host_id"],
        "m6_profile": world.host.get("m6_profile"),
        "operator_report_status": op_status,
        "operator_report_reason": op_reason,
        "initial_question": _initial_question(world),
        "revised_question": _revised_question(world, profile, divergent, aporia_seen),
        "reports": reports,
        "report_triad": triad,
        "report_completeness": "REPORT_INCOMPLETE" if missing else "REPORT_COMPLETE",
        "missing_mandatory_reports": missing,
        "synthetic_only": True,
    }


def render_public_markdown(bundle: Mapping[str, Any]) -> str:
    lines = [
        f"# M6 research report — {bundle['host_id']}",
        "",
        "SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / NOT_CUSTOMER_RELEASE",
        "",
        f"Completeness: **{bundle['report_completeness']}**",
        f"Initial question: {bundle.get('initial_question', '')}",
        f"Revised question: {bundle.get('revised_question', '')}",
        "",
    ]
    for report in bundle.get("reports") or ():
        lines.extend(
            [
                f"## {report['report_id']} ({report['status']})",
                "",
                str(report.get("markdown") or ""),
                "",
            ]
        )
    return "\n".join(lines)


def render_public_html(bundle: Mapping[str, Any]) -> str:
    import html

    body = render_public_markdown(bundle)
    escaped = html.escape(body)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>M6 synthetic report</title></head>"
        f"<body><pre>{escaped}</pre></body></html>"
    )


def bundle_to_json(bundle: Mapping[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2)
