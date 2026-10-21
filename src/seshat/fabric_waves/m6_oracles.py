"""M6 counterexample oracles (RX*) atop executed worlds and report bundles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from seshat.fabric_waves.m5_oracles import FAIL, NOT_TESTED, PASS, _row
from seshat.fabric_waves.m5_room_carpet import WorldRun, _operator_known_identifiers

# Substrings that must never appear as synthetic ground truth in public output.
_LEAKED_REFERENCE_MARKERS: tuple[str, ...] = (
    "DEVELOPMENT_EXPOSED_REFERENCE_ANSWER",
    "AUTHORIAL_WORKED_ANSWER",
    "Z45HEMH2eHSr3DAM2tRGyawadS5",
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
    public_text = operator_markdown + "\n" + str(bundle.get("revised_question") or "")

    for marker in _LEAKED_REFERENCE_MARKERS:
        if marker in public_text:
            rows.append(
                _row("RX01", "RX01_NO_REFERENCE_ANSWER_LEAK", FAIL, f"marker={marker}")
            )
            break
    else:
        rows.append(_row("RX01", "RX01_NO_REFERENCE_ANSWER_LEAK", PASS, "no banned markers"))

    if profile == "university_transfer":
        r06 = triad.get("R06", {}).get("markdown", "")
        if "NONCOMPARABLE" in r06 and "denominator" in r06.lower():
            rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", PASS, "R06 refuses rank"))
        else:
            rows.append(
                _row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", FAIL, "R06 missing noncompare")
            )
        initial = str(bundle.get("initial_question") or "")
        revised = str(bundle.get("revised_question") or "")
        if revised != initial and "label" in revised.lower():
            rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_APORIA", PASS, "question reframed"))
        else:
            rows.append(
                _row("RX03", "RX03_REVISED_QUESTION_AFTER_APORIA", FAIL, "no revised question")
            )
    else:
        rows.append(_row("RX02", "RX02_METRIC_DENOMINATOR_NONCOMPARABLE", NOT_TESTED, profile))
        rows.append(_row("RX03", "RX03_REVISED_QUESTION_AFTER_APORIA", NOT_TESTED, profile))

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

    if re.search(r"DecisionRight", operator_markdown, re.I) and "NOT_AUTHORIZED" in operator_markdown:
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", PASS, "reject boundary preserved"))
    elif any(o.kind == "APORIA" for o in world.outcomes):
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", PASS, "aporia without spoof right"))
    else:
        rows.append(_row("RX05", "RX05_HUMAN_REJECT_NOT_PROMOTED", NOT_TESTED, "no aporia"))

    phantom = re.findall(r"`([^`]+)`", operator_markdown)
    known = set(bundle.get("anchors") or ())
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
    bad = [p for p in phantom if p not in known]
    if bad:
        rows.append(_row("RX06", "RX06_PHANTOM_CITATION", FAIL, f"unknown={bad[:3]}"))
    else:
        rows.append(_row("RX06", "RX06_PHANTOM_CITATION", PASS, "citations bounded"))

    if "PRIVATE_" in operator_markdown or "manifest_sha256" in operator_markdown.lower():
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

    return rows
