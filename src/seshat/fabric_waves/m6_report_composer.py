"""Compose grounded R01–R07 report sections from an executed M5/M6 world run."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from seshat.fabric_waves.m4_transport_boundary import assess_output_sections
from seshat.fabric_waves.m5_room_carpet import REQUIRED_REPORT_SECTIONS, WorldRun, _lookup_sediment, _operator_sections
from seshat.fabric_waves.m6_w2_cycle import w2_observations
from seshat.fabric_waves.m5_synthetic_hosts import carrier_id_from_uri

ReportAvailability = Literal[
    "AVAILABLE",
    "PARTIAL",
    "BLOCKED_METHOD_RUNTIME",
    "BLOCKED_EXTERNAL_EVIDENCE",
    "PRELIMINARY",
]

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


def _w2_primary(world: WorldRun) -> Mapping[str, Any] | None:
    obs = w2_observations(world)
    if not obs:
        return None
    return obs[-1].payload or {}


def _revised_question(world: WorldRun, profile: str, divergent: bool, w2: Mapping[str, Any] | None) -> str:
    initial = _initial_question(world)
    if profile == "university_transfer" and w2:
        if w2.get("sample_overlap_with_beta"):
            return (
                "Under label-overlap between an external programme and Group Beta "
                f"(source `{w2.get('carrier_id')}`@{w2.get('source_version')}), "
                "what independent labels are required before any transfer recommendation?"
            )
        if w2.get("independent_labels_claimed"):
            return initial
    if profile == "service_calibration" and w2:
        return (
            "Given a signed synthetic test observation without maintenance escalation authority "
            f"(`{w2.get('carrier_id')}`@{w2.get('source_version')}), "
            "which bounded check is authorized without owner DecisionRight?"
        )
    if profile == "university_transfer" and divergent:
        return (
            "With divergent local coverage_proxy readings only, what external evidence "
            "is required before comparing groups?"
        )
    return initial


def _coverage_axes_from_sources(world: WorldRun) -> list[str]:
    """Current, actually stored source revisions, never stale fixture declarations."""
    store = world.engine.carrier_store
    if store is None:
        return []
    axes: list[str] = []
    for item in world.host.get("source_versions") or ():
        uri = str(item["id"])
        cid = carrier_id_from_uri(uri)
        version = store.current_source_versions((cid,)).get(cid)
        entry = store._contents.get(cid)  # synthetic in-memory test host
        if version is None or entry is None:
            continue
        content = entry.content.decode("utf-8") if isinstance(entry.content, bytes) else str(entry.content)
        if "COVERAGE_PROXY" in content:
            m = re.search(r"denominator=([^;]+)", content)
            denom = m.group(1).strip() if m else "UNKNOWN_DENOMINATOR"
            axes.append(f"{uri}@{version}: coverage_proxy denominator={denom}")
    return axes


def _r07_routes(profile: str, w2: Mapping[str, Any] | None, operator_next: str) -> list[str]:
    if profile == "university_transfer":
        routes = [
            "direct handoff with explicit caveat on label independence",
            "requalification using independent labels before transfer",
            "new comparative inquiry with harmonised denominator",
        ]
        if w2 and not w2.get("sample_overlap_with_beta") and w2.get("independent_labels_claimed"):
            routes[0] = "direct handoff where independent labels are evidenced in returned W2"
    elif profile == "service_calibration":
        routes = [
            "immediate bounded instrument check (no escalation)",
            "requalification against revised calibration protocol O2",
            "new monitoring programme pending owner DecisionRight",
        ]
    else:
        routes = ["scope requalification", "new inquiry", "pause pending rights"]
    return routes


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
    w2 = _w2_primary(world)
    anchors: list[str] = []
    if projection:
        anchors.append(f"projection-{world.slug}")
    if w2:
        anchors.append(str(w2.get("sediment_id") or f"external-w2-{world.slug}"))

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
        status = "AVAILABLE" if world.run_ids else "PARTIAL"
    elif report_id == "R03":
        axes = _coverage_axes_from_sources(world)
        status = "AVAILABLE" if axes else "PARTIAL"
        body = "Substantive metadata from admitted carriers: " + (
            "; ".join(axes) if axes else "no coverage_proxy tagged sources"
        )
    elif report_id == "R04":
        body = operator_sections.get("observed_facts") or "_no grounded facts recorded_"
        status = "AVAILABLE" if body.strip() and body != "_no grounded facts recorded_" else "PARTIAL"
    elif report_id == "R05":
        if w2:
            body = (
                "Fictional external W2 test observation (self-asserted simulator receipt; "
                "NO independently attested F07 owner rights): "
                f"carrier `{w2.get('carrier_id')}` version `{w2.get('source_version')}` "
                f"({w2.get('byte_length')} bytes, digest `{w2.get('content_sha256')}`). "
                f"Producer run: `{w2.get('producer_run_id') or 'n/a'}`. "
                "Coverage caveat: synthetic invented programme only; no world coverage claim."
            )
            status = "AVAILABLE"
        elif frontier_probe and frontier_probe.get("trigger_activation_id"):
            body = (
                "External field need witnessed at activation "
                f"`{frontier_probe.get('trigger_activation_id')}`; "
                "no W2 return admitted yet — external configurations remain PARTIAL."
            )
            status = "PARTIAL"
        else:
            body = "No witnessed external research need; external field UNKNOWN."
            status = "BLOCKED_EXTERNAL_EVIDENCE"
    elif report_id == "R06":
        if profile == "university_transfer":
            # The two denominators and editions are read from current admitted
            # synthetic carrier bytes, not from source declarations or profile text.
            observed_axes = _coverage_axes_from_sources(world)
            observed_denominators = [
                int(m.group(1))
                for axis in observed_axes
                for m in [re.search(r"denominator=(\\d+)", axis)]
                if m is not None
            ]
            sufficient = len(observed_denominators) >= 2
            overlap = bool(w2 and w2.get("sample_overlap_with_beta"))
            independent = bool(w2 and w2.get("independent_labels_claimed"))
            comparison = (
                "Status: NONCOMPARABLE — returned W2 reports overlapping Beta labels, "
                "so the external sample is not an independent observation."
                if overlap else
                "Status: NONCOMPARABLE — local sources use different label definitions; "
                "independence and harmonised units are not established."
            )
            body = (
                "Observed current synthetic carriers: " + ("; ".join(observed_axes) if observed_axes else "UNKNOWN")
                + ". Comparison axes: object=local labelled groups vs external programme; "
                + "operation=coverage-proxy sampling; metric=labelled count/denominator; "
                + "unit=toy-labelled sample (label harmonisation UNKNOWN); "
                + "purpose=transfer or ranking (ranking NOT_AUTHORIZED). "
                + comparison
                + (" W2 independent-label claim is recorded, but is not a human acceptance."
                   if independent else " Counterexample: apparent percentages can share Beta labels.")
            )
            status = "AVAILABLE" if sufficient and w2 else "PARTIAL"
        elif profile == "service_calibration":
            sources = world.engine.carrier_store
            actual_versions = {}
            if sources is not None:
                ids = [carrier_id_from_uri(str(x["id"])) for x in world.host.get("source_versions") or ()]
                actual_versions = sources.current_source_versions(tuple(ids))
            current = ", ".join(f"{k}@{v}" for k, v in sorted(actual_versions.items()))
            body = (
                "Observed current source editions: " + (current or "UNKNOWN") + ". "
                "Comparison axes: object=toy sensor condition vs calibration rule; "
                "operation=standard-read before maintenance; "
                "metric=reported drift vs procedure compliance; "
                "unit=different measurement/decision domains (no common scalar); "
                "purpose=bounded service action vs escalation. "
                + (
                    "Returned W2 supplies no owner authority for escalation. "
                    "Counterexample: absence of an escalation assertion is not calibration clearance."
                    if w2 else "W2 independent standard observation UNKNOWN; escalation remains blocked."
                )
            )
            status = "AVAILABLE" if w2 and actual_versions else "PARTIAL"
        else:
            body = "Comparison axes: UNKNOWN (no m6_profile)."
            status = "PARTIAL"
    elif report_id == "R07":
        revised = _revised_question(world, profile, divergent, w2)
        routes = _r07_routes(profile, w2, operator_sections.get("next_action", ""))
        next_action = operator_sections.get("next_action", "_none_")[:400]
        if w2 and profile == "university_transfer" and w2.get("sample_overlap_with_beta"):
            discriminating = (
                "requalification using independent labels before transfer "
                f"(grounded in W2 sediment `{w2.get('carrier_id')}`)"
            )
        elif w2 and profile == "service_calibration":
            discriminating = "immediate bounded instrument check (no escalation)"
        else:
            discriminating = next_action
        body = (
            f"Revised question: {revised}\n\n"
            "Alternative routes (synthetic, not authorized actions):\n"
            + "\n".join(f"- {r}" for r in routes)
            + f"\n\nDiscriminating next action: {discriminating}"
        )
        if profile == "service_calibration":
            body += "\n\nDecisionRight: owner approval required before maintenance escalation."
        status = "PRELIMINARY" if not w2 and frontier_probe else "AVAILABLE"
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
        "w2_provenance": w2,
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
    w2 = _w2_primary(world)
    profile = str(world.host.get("m6_profile") or "generic")
    reports = [
        compose_report_section(rid, world, sections, frontier_probe=frontier_probe)
        for rid in M6_MANDATORY_REPORT_IDS
    ]
    missing = [r["report_id"] for r in reports if r["status"] in {"BLOCKED_METHOD_RUNTIME"}]
    triad = [r for r in reports if r["report_id"] in {"R05", "R06", "R07"}]
    return {
        "schema": "seshat.m6_report_bundle.v1",
        "host_id": world.host["host_id"],
        "m6_profile": world.host.get("m6_profile"),
        "operator_report_status": op_status,
        "operator_report_reason": op_reason,
        "initial_question": _initial_question(world),
        "revised_question": _revised_question(world, profile, divergent, w2),
        "reports": reports,
        "report_triad": triad,
        "report_completeness": "REPORT_INCOMPLETE" if missing else "REPORT_COMPLETE",
        "missing_mandatory_reports": missing,
        "w2_admitted": w2 is not None,
        "w2_authority": "SYNTHETIC_SELF_ASSERTED_NOT_REAL_F07" if w2 else "NO_W2",
        "w2_receipts": list(world.oracle_inputs_extra.get("m6_w2_receipts") or ()),
        "synthetic_only": True,
    }


def render_public_markdown(bundle: Mapping[str, Any]) -> str:
    lines = [
        f"# M6 research report — {bundle['host_id']}",
        "",
        "SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / NOT_CUSTOMER_RELEASE",
        "",
        f"Completeness: **{bundle['report_completeness']}**",
        f"W2 admitted: **{bundle.get('w2_admitted')}**",
        f"Initial question: {bundle.get('initial_question', '')}",
        f"Revised question: {bundle.get('revised_question', '')}",
        "",
        "## Provenance drillback (W2)",
        "",
    ]
    w2 = None
    for report in bundle.get("reports") or ():
        if report.get("w2_provenance"):
            w2 = report["w2_provenance"]
            break
    if w2:
        lines.append(
            f"- carrier `{w2.get('carrier_id')}` @ `{w2.get('source_version')}` "
            f"sha256 `{w2.get('content_sha256')}` ({w2.get('byte_length')} bytes)"
        )
    else:
        lines.append("- no external W2 sediment on record")
    lines.append("")
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
