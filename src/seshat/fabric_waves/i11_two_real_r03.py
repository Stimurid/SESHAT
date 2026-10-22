"""Bounded, source-addressed R03 from TWO distinct real I11 ModelRuns.

Only an operator-private candidate. The scientific and customer decision gates
cannot be minted by this report formatter.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = frozenset({
    "COMMON_OPERATION", "MATERIAL_DIFFERENCE", "INCOMPARABLE",
    "UNKNOWN", "AUTHORIAL_HYPOTHESIS",
})


class TwoRealI11R03Error(ValueError):
    """Input does not demonstrate two distinct model runs and grounded claims."""


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _check_run(run: Mapping[str, Any]) -> None:
    if run.get("run_state") != "SUCCEEDED" or run.get("source_kind") != "REAL_PUBLISHED":
        raise TwoRealI11R03Error("I11_REAL_TERMINAL_REQUIRED")
    for field in ("source_pdf_sha256", "model_page_text_sha256",
                  "stdout_sha256", "method_sha256"):
        if not _sha(run.get(field)):
            raise TwoRealI11R03Error("I11_INVALID_PIN_" + field.upper())
    if not str(run.get("job_id", "")).startswith("jx-"):
        raise TwoRealI11R03Error("I11_ORIGINAL_JOB_ID_REQUIRED")
    if run.get("scientific_acceptance") not in ("NOT_ASSERTED", "NOT_PERFORMED"):
        raise TwoRealI11R03Error("I11_OWNER_ACCEPTANCE_SPOOF")
    if run.get("customer_release") != "BLOCKED":
        raise TwoRealI11R03Error("I11_CUSTOMER_RELEASE_SPOOF")


def build_two_real_i11_r03(
    run_a: Mapping[str, Any],
    run_b: Mapping[str, Any],
    events_a: Sequence[Mapping[str, Any]],
    events_b: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a private R03 candidate with a page/event address in BOTH works.

    The caller owns actual byte verification and material content judgement.
    No state from test-only / fictional comparison may enter either run.
    """
    for run in (run_a, run_b):
        _check_run(run)
    if (run_a["job_id"] == run_b["job_id"]
            or run_a["source_pdf_sha256"] == run_b["source_pdf_sha256"]
            or run_a["model_page_text_sha256"] == run_b["model_page_text_sha256"]):
        raise TwoRealI11R03Error("I11_NOT_TWO_DISTINCT_RUNS")
    if run_a["method_sha256"] != run_b["method_sha256"]:
        raise TwoRealI11R03Error("I11_METHOD_VERSION_MISMATCH")
    if not comparisons:
        raise TwoRealI11R03Error("I11_COMPARATIVE_CLAIMS_MISSING")
    indexed = [
        {e.get("event_id"): e for e in events}
        for events in (events_a, events_b)
    ]
    if any(None in ix or len(ix) != len(events) for ix, events in
           zip(indexed, (events_a, events_b))):
        raise TwoRealI11R03Error("I11_EVENT_ID_DUPLICATED")
    validated = []
    for claim in comparisons:
        kind = claim.get("kind")
        if kind not in _ALLOWED:
            raise TwoRealI11R03Error("I11_INVALID_COMPARISON_KIND")
        evidence = []
        for side, events, run in (("a", indexed[0], run_a),
                                  ("b", indexed[1], run_b)):
            event_id = claim.get("event_" + side)
            if event_id not in events:
                raise TwoRealI11R03Error("I11_COMPARISON_EVENT_NOT_FOUND")
            event = events[event_id]
            pages = event.get("pages")
            page = claim.get("page_" + side)
            if (type(page) is not int or page < 1
                    or type(pages) is not list or page not in pages
                    or page > run.get("page_count", 0)):
                raise TwoRealI11R03Error("I11_COMPARISON_PAGE_UNVERIFIED")
            evidence.append({
                "work_id": run["work_id"],
                "job_id": run["job_id"],
                "source_pdf_sha256": run["source_pdf_sha256"],
                "model_page_text_sha256": run["model_page_text_sha256"],
                "event_id": event_id,
                "layer": event.get("layer"),
                "page": page,
            })
        statement = str(claim.get("statement") or "").strip()
        if not statement:
            raise TwoRealI11R03Error("I11_EMPTY_COMPARISON")
        validated.append({
            "kind": kind,
            "statement": statement,
            "evidence": evidence,
            "limits": str(claim.get("limits") or "Interpretation is provisional."),
        })
    content = {
        "schema": "seshat.i11.two_real_run_r03.v1",
        "report_id": "R03",
        "status": "SOURCE_GROUNDED_UNREVIEWED",
        "actual_real_model_runs": 2,
        "jobs": [run_a["job_id"], run_b["job_id"]],
        "method_sha256": run_a["method_sha256"],
        "comparison_claims": validated,
        "original_sources_only": True,
        "source_evidence_status": "PAGE_EVENT_ADDRESSED_SELF_OBSERVED",
        "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED",
        "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "provenance": "SELF_OBSERVED_UNATTESTED",
    }
    return {**content, "projection_sha256": _digest(content)}
