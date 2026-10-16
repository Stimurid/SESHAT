"""HTML and SVG renderers for the fabric trace.

The trace is a flat list of the run's ledger plus the sediment map and the
auto-resonance.  It is intentionally minimal: no external CSS, no JavaScript,
inline SVG only.  The output is meant for human review on a clean checkout
without a build step.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping
from typing import Any

from seshat.fabric_waves.contracts import (
    ActivationOutcome,
    ResonanceKind,
    StoneEventKind,
    WorkflowThreadSpec,
)
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.resonance import ResonanceComposer
from seshat.fabric_waves.sediment import SedimentState


def _color_for_outcome(outcome: ActivationOutcome) -> str:
    return {
        ActivationOutcome.FIRED: "#1a7f37",
        ActivationOutcome.SATURATED_NO_DELTA: "#9a6700",
        ActivationOutcome.SKIPPED_GUARD: "#6e7781",
        ActivationOutcome.SKIPPED_INACTIVE: "#6e7781",
        ActivationOutcome.BLOCKED_SOURCE: "#cf222e",
        ActivationOutcome.BLOCKED_PROVIDER: "#cf222e",
        ActivationOutcome.BUDGET_EXHAUSTED: "#8250df",
        ActivationOutcome.ERROR: "#cf222e",
    }.get(outcome, "#57606a")


def _color_for_stone_kind(kind: StoneEventKind) -> str:
    return {
        StoneEventKind.QUERY: "#0969da",
        StoneEventKind.SOURCE_DELTA: "#cf222e",
        StoneEventKind.APORIA: "#9a6700",
        StoneEventKind.HUMAN_DECISION: "#1a7f37",
        StoneEventKind.FRONTIER_RETURN: "#8250df",
    }.get(kind, "#57606a")


def render_html(
    *,
    run_record: Any,
    ledger: RunLedger,
    sediment: SedimentState,
    resonances: ResonanceComposer,
    title: str = "SESHAT fabric trace",
    thread_specs: Mapping[str, WorkflowThreadSpec] | None = None,
) -> str:
    """Render the run as a self-contained HTML document."""

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append("<html lang=\"en\">")
    parts.append("<head>")
    parts.append(f"<meta charset=\"utf-8\"><title>{html.escape(title)}</title>")
    parts.append("<style>")
    parts.append(
        "body{font-family:ui-monospace,Consolas,Menlo,monospace;color:#1f2328;"
        "background:#f6f8fa;margin:24px;}"
        "h1,h2,h3{font-weight:600;}"
        "table{border-collapse:collapse;margin:8px 0;}"
        "th,td{border:1px solid #d0d7de;padding:4px 8px;text-align:left;font-size:13px;}"
        "th{background:#eaeef2;}"
        ".chip{display:inline-block;padding:1px 6px;border-radius:4px;color:#fff;font-size:12px;}"
        ".block{border:1px solid #d0d7de;border-radius:6px;padding:12px;background:#fff;margin:12px 0;}"
    )
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"<h1>{html.escape(title)}</h1>")
    parts.append("<div class=\"block\">")
    parts.append("<h2>Run summary</h2>")
    parts.append(
        f"<div><strong>run_id:</strong> {html.escape(run_record.run_id)}</div>"
    )
    parts.append(
        f"<div><strong>outcome:</strong> "
        f"<span class=\"chip\" style=\"background:#0969da\">{html.escape(run_record.outcome.value)}</span></div>"
    )
    parts.append(
        f"<div><strong>stop_reason:</strong> {html.escape(run_record.stop_reason.value)}</div>"
    )
    parts.append(
        f"<div><strong>waves:</strong> {run_record.waves_emitted}</div>"
    )
    parts.append(
        f"<div><strong>activations:</strong> {run_record.activations_total}</div>"
    )
    parts.append(
        f"<div><strong>ledger head:</strong> <code>{html.escape(run_record.ledger_head_hash[:16])}…</code></div>"
    )
    budget = run_record.budget
    parts.append(
        f"<div><strong>budget:</strong> waves≤{budget.max_waves}, "
        f"activations≤{budget.max_activations}, "
        f"stone_events≤{budget.max_stone_events}, "
        f"aporia_after_waves={budget.aporia_after_waves}</div>"
    )
    parts.append(
        "<div><strong>decision_right:</strong> "
        "<code>seshat:fabric:human-acceptance</code> (acceptance never self-certified)</div>"
    )
    parts.append("</div>")

    run_id = run_record.run_id
    run_events = tuple(event for event in ledger.events if event.run_id == run_id)
    parts.append("<div class=\"block\">")
    parts.append("<h2>Stone events (this run)</h2>")
    if run_events:
        parts.append("<table>")
        parts.append(
            "<thead><tr><th>event</th><th>kind</th><th>tick</th><th>carrier</th><th>payload hash</th></tr></thead>"
        )
        parts.append("<tbody>")
        for event in run_events:
            color = _color_for_stone_kind(event.kind)
            parts.append(
                "<tr>"
                f"<td>{html.escape(event.event_id)}</td>"
                f"<td><span class=\"chip\" style=\"background:{color}\">{html.escape(event.kind.value)}</span></td>"
                f"<td>{event.issued_at_tick}</td>"
                f"<td>{html.escape(event.target_carrier_id or '')}</td>"
                f"<td><code>{html.escape(event.payload_hash[:16])}…</code></td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<div>no stone events recorded for this run</div>")
    parts.append("</div>")

    run_decisions = tuple(dec for dec in ledger.decisions if dec.run_id == run_id)
    parts.append("<div class=\"block\">")
    parts.append("<h2>Human decisions (this run)</h2>")
    if run_decisions:
        parts.append("<table>")
        parts.append(
            "<thead><tr><th>decision</th><th>by</th><th>choice</th><th>sediment</th></tr></thead>"
        )
        parts.append("<tbody>")
        for decision in run_decisions:
            parts.append(
                "<tr>"
                f"<td>{html.escape(decision.decision_id)}</td>"
                f"<td>{html.escape(decision.decided_by)}</td>"
                f"<td>{html.escape(decision.choice)}</td>"
                f"<td>{html.escape(decision.subject_sediment_id or '')}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<div>none — engine did not self-certify acceptance</div>")
    parts.append("</div>")

    if thread_specs:
        parts.append("<div class=\"block\">")
        parts.append("<h2>Workflow threads (configured)</h2>")
        parts.append("<table>")
        parts.append(
            "<thead><tr><th>thread</th><th>purpose</th><th>carriers</th><th>nodes</th></tr></thead>"
        )
        parts.append("<tbody>")
        for thread_id in sorted(thread_specs):
            spec = thread_specs[thread_id]
            carriers = ", ".join(spec.admissible_source_carriers) or "—"
            parts.append(
                "<tr>"
                f"<td>{html.escape(thread_id)}</td>"
                f"<td>{html.escape(spec.purpose)}</td>"
                f"<td>{html.escape(carriers)}</td>"
                f"<td>{len(spec.nodes)}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        parts.append("</div>")

    parts.append("<div class=\"block\">")
    parts.append("<h2>Sediment (final)</h2>")
    parts.append("<table>")
    parts.append(
        "<thead><tr><th>sediment_id</th><th>object_type</th><th>version</th><th>state</th>"
        "<th>thread</th><th>reads</th><th>stone</th></tr></thead>"
    )
    parts.append("<tbody>")
    for record in sediment.all_records():
        reads = ", ".join(record.read_dependencies) or "—"
        parts.append(
            "<tr>"
            f"<td>{html.escape(record.sediment_id)}</td>"
            f"<td>{html.escape(record.object_type)}</td>"
            f"<td>{html.escape(record.version)}</td>"
            f"<td>{html.escape(record.acceptance_state.value)}</td>"
            f"<td>{html.escape(record.produced_by_thread)}</td>"
            f"<td>{html.escape(reads)}</td>"
            f"<td>{html.escape(record.produced_by_stone_kind.value)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")

    parts.append("<div class=\"block\">")
    parts.append("<h2>Waves</h2>")
    parts.append("<table>")
    parts.append(
        "<thead><tr><th>wave</th><th>trigger</th><th>eligible</th><th>fired</th>"
        "<th>no_delta</th><th>skipped</th><th>blocked</th><th>budget</th></tr></thead>"
    )
    parts.append("<tbody>")
    run_id = run_record.run_id
    waves = tuple(wave for wave in ledger.waves if wave.run_id == run_id)
    activations = tuple(
        act for act in ledger.activations if act.run_id == run_id
    )
    for wave in waves:
        color = _color_for_stone_kind(wave.triggered_by)
        parts.append(
            "<tr>"
            f"<td>w{wave.wave_index}</td>"
            f"<td><span class=\"chip\" style=\"background:{color}\">{html.escape(wave.triggered_by.value)}</span></td>"
            f"<td>{len(wave.eligible_thread_ids)}</td>"
            f"<td>{len(wave.fired_thread_ids)}</td>"
            f"<td>{len(wave.no_delta_thread_ids)}</td>"
            f"<td>{len(wave.skipped_thread_ids)}</td>"
            f"<td>{len(wave.blocked_thread_ids)}</td>"
            f"<td>{wave.budget_used}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")

    parts.append("<div class=\"block\">")
    parts.append("<h2>Activations</h2>")
    parts.append("<table>")
    parts.append(
        "<thead><tr><th>activation</th><th>thread</th><th>outcome</th><th>produced</th><th>invalidated</th><th>read</th></tr></thead>"
    )
    parts.append("<tbody>")
    for act in activations:
        color = _color_for_outcome(act.outcome)
        parts.append(
            "<tr>"
            f"<td>{html.escape(act.activation_id.rsplit(':', 1)[-1])}</td>"
            f"<td>{html.escape(act.thread_id)}</td>"
            f"<td><span class=\"chip\" style=\"background:{color}\">{html.escape(act.outcome.value)}</span></td>"
            f"<td>{len(act.produced_sediment_ids)}</td>"
            f"<td>{len(act.invalidated_sediment_ids)}</td>"
            f"<td>{len(act.read_sediment_ids)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")

    parts.append("<div class=\"block\">")
    parts.append("<h2>Resonance</h2>")
    parts.append("<table>")
    parts.append(
        "<thead><tr><th>kind</th><th>payload_hash</th><th>traced events</th><th>traced activations</th></tr></thead>"
    )
    parts.append("<tbody>")
    for record in resonances.values():
        parts.append(
            "<tr>"
            f"<td>{html.escape(record.kind.value)}</td>"
            f"<td><code>{html.escape(record.payload_hash[:16])}…</code></td>"
            f"<td>{len(record.trace_event_ids)}</td>"
            f"<td>{len(record.trace_activation_ids)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")

    parts.append(
        f"<div class=\"block\"><h2>Thread topology</h2>"
        f"<div>{render_svg(run_record=run_record, ledger=ledger)}</div></div>"
    )

    parts.append("</body></html>")
    return "".join(parts)


def render_svg(
    *,
    run_record: Any,
    ledger: RunLedger,
) -> str:
    """Render the wave timeline as inline SVG."""

    run_id = run_record.run_id
    waves = tuple(wave for wave in ledger.waves if wave.run_id == run_id)
    if not waves:
        return "<svg width=\"600\" height=\"80\"><text x=\"20\" y=\"40\">no waves emitted</text></svg>"

    width = max(600, 120 + 90 * len(waves))
    height = 200
    parts: list[str] = [
        f"<svg width=\"{width}\" height=\"{height}\" xmlns=\"http://www.w3.org/2000/svg\">"
    ]
    parts.append(f"<text x=\"20\" y=\"20\" font-family=\"monospace\" font-size=\"14\">run {html.escape(run_record.run_id)} — {len(waves)} waves</text>")
    parts.append("<line x1=\"20\" y1=\"60\" x2=\"" + str(width - 20) + "\" y2=\"60\" stroke=\"#d0d7de\" stroke-width=\"2\"/>")
    for index, wave in enumerate(waves):
        x = 60 + 90 * index
        color = _color_for_stone_kind(wave.triggered_by)
        parts.append(
            f"<circle cx=\"{x}\" cy=\"60\" r=\"14\" fill=\"{color}\" stroke=\"#1f2328\" stroke-width=\"1\"/>"
        )
        parts.append(
            f"<text x=\"{x}\" y=\"100\" text-anchor=\"middle\" font-size=\"11\">{html.escape(wave.triggered_by.value)}</text>"
        )
        parts.append(
            f"<text x=\"{x}\" y=\"118\" text-anchor=\"middle\" font-size=\"11\">{len(wave.fired_thread_ids)} fired / {len(wave.eligible_thread_ids)} eligible</text>"
        )
        parts.append(
            f"<text x=\"{x}\" y=\"136\" text-anchor=\"middle\" font-size=\"11\" fill=\"#57606a\">no_delta={len(wave.no_delta_thread_ids)} skipped={len(wave.skipped_thread_ids)} blocked={len(wave.blocked_thread_ids)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render_html", "render_svg"]


def resonance_summary(resonances: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in resonances:
        if record.kind is ResonanceKind.ANSWER:
            summary = record.payload.get("summary", "") if isinstance(record.payload, dict) else ""
        else:
            summary = record.kind.value
        out.append(
            {
                "kind": record.kind.value,
                "summary": summary,
                "payload_hash": record.payload_hash,
            }
        )
    return out