"""M6 counterexample oracles (RX*) atop executed worlds and report bundles."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from seshat.fabric_waves.m5_oracles import FAIL, NOT_TESTED, PASS, _row
from seshat.fabric_waves.m5_room_carpet import WorldRun, _operator_known_identifiers
from seshat.fabric_waves.m6_w2_cycle import w2_observations
from seshat.fabric_waves.m6_report_composer import _coverage_axes_from_sources

_LEAKED_REFERENCE_MARKERS: tuple[str, ...] = (
    "DEVELOPMENT_EXPOSED_REFERENCE_ANSWER",
    "AUTHORIAL_WORKED_ANSWER",
    "AUTHORIAL_REFERENCE_RESULT_NOT_FOR_EXECUTION",
)


def evaluate_m6_oracles(
    world: WorldRun,
    bundle: Mapping[str, Any],
    *,
    operator_markdown: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    profile = str(world.host.get("m6_profile") or "")
    triad = {r["report_id"]: r for r in bundle.get("report_triad") or ()}
    report_text = "\n".join(str(r.get("markdown") or "") for r in bundle.get("reports") or ())
    public_text = operator_markdown + "\n" + str(bundle.get("revised_question") or "") + "\n" + report_text
    w2 = w2_observations(world)
    w2_payload = w2[-1].payload if w2 else None
    receipts = list(world.oracle_inputs_extra.get("m6_w2_receipts") or ())

    for marker in _LEAKED_REFERENCE_MARKERS:
        if marker in public_text:
            rows.append(_row("RX01", "RX01_NO_REFERENCE_ANSWER_LEAK", FAIL, f"marker={marker}"))
            break
    else:
        rows.append(_row("RX01", "RX01_NO_REFERENCE_ANSWER_LEAK", PASS, "no banned markers"))

    if profile == "university_transfer":
        r06 = triad.get("R06", {}).get("markdown", "")
        axes = _coverage_axes_from_sources(world)
        observed_denominators = [
            m.group(1)
            for axis in axes
            for m in [re.search(r"denominator=(\d+)", axis)]
            if m is not None
        ]
        source_coverage_ok = (
            len(observed_denominators) >= 2
            and all(axis in r06 for axis in axes)
            and all(value in r06 for value in observed_denominators)
            and "NONCOMPARABLE" in r06
        )
        if source_coverage_ok:
            rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", PASS, "current source denominators and refusal match"))
        else:
            rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", FAIL, "R06 lacks actual current source axes"))
        initial = str(bundle.get("initial_question") or "")
        revised = str(bundle.get("revised_question") or "")
        overlap = bool(w2_payload and w2_payload.get("sample_overlap_with_beta"))
        if overlap and revised != initial and "independent labels" in revised.lower():
            rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_W2", PASS, "overlap-driven reframe"))
        elif not overlap and w2_payload and revised == initial:
            rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_W2", PASS, "independent W2 keeps question"))
        elif not w2_payload and revised != initial:
            rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_W2", NOT_TESTED, "no W2 yet"))
        else:
            rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_W2", FAIL, "unexpected question state"))
    else:
        rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", NOT_TESTED, profile))
        rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_W2", NOT_TESTED, profile))

    if bundle.get("report_completeness") == "REPORT_COMPLETE":
        rows.append(_row("RX04", "RX04_MANDATORY_REPORT_SECTIONS", PASS, "R01-R07 present"))
    else:
        rows.append(
            _row(
                "RX04",
                "RX04_MANDATORY_REPORT_SECTIONS",
                FAIL,
                f"missing={bundle.get('missing_mandatory_reports')}",
            )
        )

    # A word in the report or an APORIA event is NOT a witnessed refusal.
    human = world.oracle_inputs_extra.get("m6_human_refusal")
    if not human or not human.get("attempted"):
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", NOT_TESTED, "no actual human-refusal probe"))
    elif human.get("rejected") and human.get("accepted_view_size_after") == 0:
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", PASS, "two real unauthorized decision operations rejected"))
    else:
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", FAIL, "unauthorized decision not refused"))

    phantom = re.findall(r"`([^`]+)`", public_text)
    known = set(bundle.get("anchors") or ())
    known.add(str(world.host.get("host_id") or ""))
    # Only allow literal source versions and digests witnessed in the actual W2
    # sediment, not arbitrary backticks or synthetic:// URL-shaped guesses.
    for observed_w2 in w2:
        payload = observed_w2.payload or {}
        for key in ("source_version", "content_sha256", "producer_run_id", "source_uri"):
            if payload.get(key):
                known.add(str(payload[key]))
    for record in world.engine.sediment.all_records():
        known.add(record.sediment_id)
        known.add(record.version)
    for manifest in world.manifests:
        known.add(manifest.room_id)
    for activation in world.engine.ledger.activations:
        known.add(activation.activation_id)
    for world_outcome in world.outcomes:
        if world_outcome.run_id:
            known.add(world_outcome.run_id)
        known.add(world_outcome.stone_id)
        if world_outcome.manifest is not None:
            known.add(world_outcome.manifest.room_id)
    known.update(_operator_known_identifiers(world))
    for src in world.host.get("source_versions") or ():
        known.add(str(src.get("id") or ""))
    for rec in receipts:
        known.add(str(rec.get("return_id") or ""))
        known.add(str(rec.get("carrier_id") or ""))
        known.add(str(rec.get("source_uri") or ""))
    bad = [p for p in phantom if p and p not in known]
    if bad:
        rows.append(_row("RX06", "RX06_PHANTOM_CITATION", FAIL, f"unknown={bad[:3]}"))
    else:
        rows.append(_row("RX06", "RX06_PHANTOM_CITATION", PASS, "citations bounded"))

    if "PRIVATE_" in public_text or "manifest_sha256" in public_text.lower():
        rows.append(_row("RX07", "RX07_NO_PRIVATE_MANIFEST_LEAK", FAIL, "private token in public view"))
    else:
        rows.append(_row("RX07", "RX07_NO_PRIVATE_MANIFEST_LEAK", PASS, "no manifest leak"))

    r07 = triad.get("R07", {}).get("markdown", "")
    if profile == "service_calibration" and "DecisionRight" in r07:
        rows.append(_row("RX08", "RX08_SERVICE_RIGHTS_EXPLICIT", PASS, "R07 names rights"))
    elif profile == "service_calibration":
        rows.append(_row("RX08", "RX08_SERVICE_RIGHTS_EXPLICIT", FAIL, "R07 missing DecisionRight"))
    else:
        rows.append(_row("RX08", "RX08_SERVICE_RIGHTS_EXPLICIT", NOT_TESTED, profile))

    r05 = triad.get("R05", {})
    if w2_payload and r05.get("status") == "AVAILABLE":
        prov = w2_payload.get("content_sha256")
        traces = list(world.oracle_inputs_extra.get("m6_w2_actual_activations") or ())
        trace = traces[0] if len(traces) == 1 else None
        actual = (
            next(
                (a for a in world.engine.ledger.activations
                 if trace and a.activation_id == trace["activation_id"]
                 and a.run_id == trace["run_id"] and a.outcome.value == "FIRED"),
                None,
            )
            if trace else None
        )
        observed = (
            next(
                (rec for rec in world.engine.sediment.all_records()
                 if trace and rec.sediment_id == trace["sediment_id"]
                 and rec.version == trace["sediment_version"]
                 and rec.payload.get("content_sha256") == prov),
                None,
            )
            if trace else None
        )
        supported = (
            prov and str(prov) in str(r05.get("markdown", ""))
            and trace and trace["source_sha256"] == prov
            and actual is not None and observed is not None
            and trace["activation_id"] in r05.get("markdown", "")
        )
        if supported:
            rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", PASS, f"actual activation={trace['activation_id']}"))
        else:
            rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", FAIL, "missing source-bound FIRED activation/sediment in R05"))
    elif not w2_payload and r05.get("status") in ("PARTIAL", "BLOCKED_EXTERNAL_EVIDENCE"):
        rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", PASS, "no W2 partial correctly"))
    else:
        rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", FAIL, f"r05={r05.get('status')}"))

    if w2_payload:
        store = world.engine.carrier_store
        carrier_id = str(w2_payload.get("carrier_id") or "")
        entry = store._contents.get(carrier_id) if store is not None else None
        raw = (entry.content if isinstance(entry.content, bytes) else str(entry.content).encode("utf-8")) if entry else b""
        bytes_match = (
            bool(raw)
            and hashlib.sha256(raw).hexdigest() == w2_payload.get("content_sha256")
            and len(raw) == w2_payload.get("byte_length")
            and w2_payload.get("reading_extent") == "FULL_SYNTHETIC_FIXTURE"
        )
        if bytes_match:
            rows.append(_row("RX10", "RX10_SYNTHETIC_BYTE_EXTENT", PASS, f"actual synthetic bytes={len(raw)}"))
        else:
            rows.append(_row("RX10", "RX10_SYNTHETIC_BYTE_EXTENT", FAIL, "stored bytes/digest/version do not match W2"))
    else:
        rows.append(_row("RX10", "RX10_SYNTHETIC_BYTE_EXTENT", NOT_TESTED, "no W2"))

    if receipts and any(
        r.get("status") == "IDEMPOTENT_REPLAY" and r.get("verified_no_new_evidence") is True
        for r in receipts
    ):
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", PASS, "duplicate observed with no new ledger/sediment"))
    elif receipts:
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", NOT_TESTED, "single pass"))
    else:
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", NOT_TESTED, "no returns"))

    # Attach concrete run/source/report witnesses. A PASS without its own
    # evidence is never accepted by the strict M6 gate.
    public_digest = hashlib.sha256(public_text.encode("utf-8")).hexdigest()
    for row in rows:
        if row["observed"] != PASS:
            continue
        oid = row["oracle_id"]
        evidence: dict[str, Any] = {
            "host_id": str(world.host.get("host_id") or ""),
            "report_sha256": public_digest,
        }
        if oid == "RX02":
            evidence["current_source_axes"] = _coverage_axes_from_sources(world)
        elif oid in ("RX03", "RX09", "RX10"):
            evidence["w2_carrier_id"] = w2_payload.get("carrier_id") if w2_payload else None
            evidence["w2_source_digest"] = w2_payload.get("content_sha256") if w2_payload else None
            evidence["w2_bytes"] = w2_payload.get("byte_length") if w2_payload else None
            if oid == "RX09":
                evidence["w2_actual_activation"] = (
                    world.oracle_inputs_extra.get("m6_w2_actual_activations") or [None]
                )[0]
        elif oid == "RX04":
            evidence["report_ids"] = [r["report_id"] for r in bundle.get("reports") or ()]
        elif oid == "RX05":
            evidence["human_gate"] = dict(human or {})
        elif oid == "RX06":
            evidence["resolved_backtick_refs"] = len(phantom)
        elif oid == "RX08":
            evidence["service_decision_right"] = "DecisionRight" in r07
        elif oid == "RX11":
            evidence["idempotent_return_ids"] = [
                r.get("return_id") for r in receipts
                if r.get("status") == "IDEMPOTENT_REPLAY" and r.get("verified_no_new_evidence")
            ]
        elif oid in ("RX01", "RX07"):
            evidence["scanned_text_sha256"] = public_digest
        row["evidence"] = evidence
    return rows
