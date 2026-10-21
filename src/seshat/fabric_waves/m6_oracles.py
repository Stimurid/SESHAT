"""M6 counterexample oracles (RX*) atop executed worlds and report bundles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from seshat.fabric_waves.m5_oracles import FAIL, NOT_TESTED, PASS, _row
from seshat.fabric_waves.m5_room_carpet import WorldRun, _operator_known_identifiers
from seshat.fabric_waves.m6_w2_cycle import w2_observations

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
        if "NONCOMPARABLE" in r06:
            rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", PASS, "R06 refuses rank"))
        else:
            rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", FAIL, "R06 missing noncompare"))
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
        if prov and str(prov) in str(r05.get("markdown", "")):
            rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", PASS, f"digest={prov[:12]}"))
        else:
            rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", FAIL, "R05 missing W2 digest"))
    elif not w2_payload and r05.get("status") in ("PARTIAL", "BLOCKED_EXTERNAL_EVIDENCE"):
        rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", PASS, "no W2 partial correctly"))
    else:
        rows.append(_row("RX09", "RX09_W2_PROVENANCE_IN_R05", FAIL, f"r05={r05.get('status')}"))

    if w2_payload:
        if w2_payload.get("byte_length", 0) > 0 and w2_payload.get("reading_extent") == "FULL_REQUIRED":
            rows.append(_row("RX10", "RX10_F07_BYTE_EXTENT", PASS, f"bytes={w2_payload.get('byte_length')}"))
        else:
            rows.append(_row("RX10", "RX10_F07_BYTE_EXTENT", FAIL, "incomplete F07 extent"))
    else:
        rows.append(_row("RX10", "RX10_F07_BYTE_EXTENT", NOT_TESTED, "no W2"))

    if receipts and any(r.get("status") == "IDEMPOTENT_REPLAY" for r in receipts):
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", PASS, "replay observed"))
    elif receipts:
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", NOT_TESTED, "single pass"))
    else:
        rows.append(_row("RX11", "RX11_W2_IDEMPOTENT", NOT_TESTED, "no returns"))

    return rows
