"""In-process byte-consistency gate for two caller-supplied I11 runs.

Checks recompute hashes and page excerpts over supplied bytes. Source identity,
rights, production provenance, and publisher originalness are NOT attested:
the terminal-receipt and REAL_PUBLISHED fields can be caller-authored. The gate
issuer is an in-process integrity marker, NOT a security credential. The
real archived Hub receipt schema currently does not satisfy this synthetic
receipt protocol. No scientific, owner, or customer acceptance follows.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    AUTHORIAL_I11_SHA256,
    parse_page_map,
)

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = frozenset({
    "COMMON_OPERATION", "MATERIAL_DIFFERENCE", "INCOMPARABLE",
    "UNKNOWN", "AUTHORIAL_HYPOTHESIS",
})
_LAYERS = frozenset({"RP", "SS", "FT", "PO", "BR", "IM", "PR"})
_REAL_ADMISSION = "IN_PROCESS_BYTE_COHERENCE_ONLY"
_GATE_ISSUER = object()


class TwoRealI11R03Error(ValueError):
    """Inputs do not demonstrate two distinct, byte-verified model runs."""


@dataclass(frozen=True)
class RunArtifactBytes:
    """Owner-private bytes; this object must never be serialized into R03."""

    source_pdf: bytes
    model_page_text: bytes
    stdout: bytes
    method: bytes
    terminal_receipt: bytes


@dataclass(frozen=True)
class SourceIdentityPin:
    """Byte-recomputed run identity, not an attested publisher provenance."""

    work_id: str
    job_id: str
    source_pdf_sha256: str
    model_page_text_sha256: str


@dataclass(frozen=True, init=False)
class VerifiedTwoRunAdmission:
    """Caller-byte integrity result, not independent source authorization."""

    admission_digest: str
    run_digests: tuple[str, str]
    event_ledger_digests: tuple[str, str]
    receipt_digests: tuple[str, str]
    source_identity_pins: tuple[SourceIdentityPin, SourceIdentityPin]
    page_maps: tuple[Mapping[int, str], Mapping[int, str]]
    provenance: str = "SELF_OBSERVED_UNATTESTED"
    _issuer: object = _GATE_ISSUER

    def __init__(
        self, *, admission_digest: str, run_digests: tuple[str, str],
        event_ledger_digests: tuple[str, str], receipt_digests: tuple[str, str],
        source_identity_pins: tuple[SourceIdentityPin, SourceIdentityPin],
        page_maps: tuple[Mapping[int, str], Mapping[int, str]],
        _issuer: object,
    ) -> None:
        if _issuer is not _GATE_ISSUER:
            raise TwoRealI11R03Error("I11_ADMISSION_NOT_GATE_ISSUED")
        object.__setattr__(self, "admission_digest", admission_digest)
        object.__setattr__(self, "run_digests", run_digests)
        object.__setattr__(self, "event_ledger_digests", event_ledger_digests)
        object.__setattr__(self, "receipt_digests", receipt_digests)
        object.__setattr__(self, "source_identity_pins", source_identity_pins)
        object.__setattr__(self, "page_maps", page_maps)
        object.__setattr__(self, "provenance", "SELF_OBSERVED_UNATTESTED")
        object.__setattr__(self, "_issuer", _issuer)


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _bytes_sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return _bytes_sha(_canonical_bytes(value))


def _check_run(run: Mapping[str, Any]) -> None:
    if run.get("run_state") != "SUCCEEDED" or run.get("source_kind") != "REAL_PUBLISHED":
        raise TwoRealI11R03Error("I11_REAL_TERMINAL_REQUIRED")
    for field in (
        "source_pdf_sha256", "model_page_text_sha256", "stdout_sha256",
        "method_sha256", "terminal_receipt_sha256", "event_ledger_sha256",
    ):
        if not _is_sha(run.get(field)):
            raise TwoRealI11R03Error("I11_INVALID_PIN_" + field.upper())
    if not str(run.get("job_id", "")).startswith("jx-"):
        raise TwoRealI11R03Error("I11_ORIGINAL_JOB_ID_REQUIRED")
    if not str(run.get("work_id", "")).strip():
        raise TwoRealI11R03Error("I11_WORK_ID_REQUIRED")
    if (
        run.get("methodbody_id") != AUTHORIAL_I11_ID
        or run.get("method_sha256") != AUTHORIAL_I11_SHA256
    ):
        raise TwoRealI11R03Error("I11_WRONG_FROZEN_METHOD")
    if run.get("scientific_acceptance") not in ("NOT_ASSERTED", "NOT_PERFORMED"):
        raise TwoRealI11R03Error("I11_OWNER_ACCEPTANCE_SPOOF")
    if run.get("owner_acceptance", "NOT_PERFORMED") != "NOT_PERFORMED":
        raise TwoRealI11R03Error("I11_OWNER_ACCEPTANCE_SPOOF")
    if run.get("customer_release") != "BLOCKED":
        raise TwoRealI11R03Error("I11_CUSTOMER_RELEASE_SPOOF")


def _event_id(event: Mapping[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def _validate_event_discipline(event: Mapping[str, Any]) -> None:
    layer = event.get("layer")
    mode = event.get("relation_mode")
    actor_types = {str(item).upper() for item in event.get("actor_types", ())}
    if layer not in _LAYERS or not isinstance(mode, str) or not mode:
        raise TwoRealI11R03Error("I11_EVENT_TAXONOMY_INVALID")
    if layer == "RP" and any("EDITOR" in item for item in actor_types):
        raise TwoRealI11R03Error("I11_EDITOR_PROMOTED_TO_RP")
    if layer == "RP" and any("FUNDER" in item for item in actor_types):
        raise TwoRealI11R03Error("I11_FUNDER_PROMOTED_TO_RP_OPERATION")
    if layer == "RP" and any("NORM_PRODUCER" in item for item in actor_types):
        raise TwoRealI11R03Error("I11_EXTERNAL_GUIDE_PRODUCER_PROMOTED_TO_RP")
    if layer == "IM" and (
        any("CLINICAL" in item or "CARE_" in item for item in actor_types)
        or "PROPOS" in mode.upper()
    ):
        raise TwoRealI11R03Error("I11_FALSE_IMPLEMENTATION_EVENT")


def _load_terminal_receipt(
    raw: bytes, run: Mapping[str, Any], ledger_digest: str,
) -> Mapping[str, Any]:
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TwoRealI11R03Error("I11_TERMINAL_RECEIPT_INVALID") from exc
    if not isinstance(receipt, dict):
        raise TwoRealI11R03Error("I11_TERMINAL_RECEIPT_INVALID")
    expected = {
        "schema": "seshat.aiye.hub_terminal_receipt.v1",
        "job_id": run["job_id"],
        "status": "SUCCEEDED",
        "source_pdf_sha256": run["source_pdf_sha256"],
        "model_page_text_sha256": run["model_page_text_sha256"],
        "stdout_sha256": run["stdout_sha256"],
        "method_sha256": run["method_sha256"],
        "event_ledger_sha256": ledger_digest,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise TwoRealI11R03Error("I11_TERMINAL_RECEIPT_MISMATCH")
    if not str(receipt.get("receipt_id") or "").strip() or not str(
        receipt.get("completed_at_utc") or ""
    ).strip():
        raise TwoRealI11R03Error("I11_TERMINAL_RECEIPT_INCOMPLETE")
    if receipt.get("original_source_bytes_observed") is not True:
        raise TwoRealI11R03Error("I11_ORIGINAL_SOURCE_ABSENT")
    if receipt.get("source_rights_status") not in {
        "VERIFIED_PUBLISHED_LICENSE", "AUTHORIZED_PRIVATE_SOURCE",
    }:
        raise TwoRealI11R03Error("I11_SOURCE_RIGHTS_UNVERIFIED")
    return receipt


def _verify_one_run(
    run: Mapping[str, Any], artifacts: RunArtifactBytes,
    events: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, Mapping[int, str], str]:
    _check_run(run)
    byte_fields = {
        "source_pdf_sha256": artifacts.source_pdf,
        "model_page_text_sha256": artifacts.model_page_text,
        "stdout_sha256": artifacts.stdout,
        "method_sha256": artifacts.method,
        "terminal_receipt_sha256": artifacts.terminal_receipt,
    }
    if not artifacts.source_pdf:
        raise TwoRealI11R03Error("I11_ORIGINAL_SOURCE_ABSENT")
    for field, raw in byte_fields.items():
        if _bytes_sha(raw) != run[field]:
            raise TwoRealI11R03Error("I11_RECOMPUTED_" + field.upper() + "_MISMATCH")
    ledger = [dict(item) for item in events]
    for event in ledger:
        if not _event_id(event):
            raise TwoRealI11R03Error("I11_EVENT_ID_REQUIRED")
        _validate_event_discipline(event)
    ledger_digest = _digest(ledger)
    if ledger_digest != run["event_ledger_sha256"]:
        raise TwoRealI11R03Error("I11_EVENT_LEDGER_MISMATCH")
    receipt = _load_terminal_receipt(artifacts.terminal_receipt, run, ledger_digest)
    try:
        page_map = parse_page_map(artifacts.model_page_text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise TwoRealI11R03Error("I11_MODEL_PAGE_MAP_INVALID") from exc
    if len(page_map) != run.get("page_count"):
        raise TwoRealI11R03Error("I11_MODEL_PAGE_MAP_STALE")
    return (
        _digest(dict(run)), ledger_digest, _bytes_sha(artifacts.terminal_receipt),
        MappingProxyType({number: chunk for number, (_start, _end, chunk) in page_map.items()}),
        str(receipt["receipt_id"]),
    )


def verify_two_run_source_admission(
    run_a: Mapping[str, Any], run_b: Mapping[str, Any],
    artifacts_a: RunArtifactBytes, artifacts_b: RunArtifactBytes,
    events_a: Sequence[Mapping[str, Any]], events_b: Sequence[Mapping[str, Any]],
) -> VerifiedTwoRunAdmission:
    """Recompute every pin and return a private gate token."""
    first = _verify_one_run(run_a, artifacts_a, events_a)
    second = _verify_one_run(run_b, artifacts_b, events_b)
    if run_a["work_id"] == run_b["work_id"]:
        raise TwoRealI11R03Error("I11_NOT_TWO_DISTINCT_WORKS")
    if (
        run_a["job_id"] == run_b["job_id"]
        or run_a["source_pdf_sha256"] == run_b["source_pdf_sha256"]
        or run_a["model_page_text_sha256"] == run_b["model_page_text_sha256"]
    ):
        raise TwoRealI11R03Error("I11_NOT_TWO_DISTINCT_RUNS")
    if first[4] == second[4] or first[2] == second[2]:
        raise TwoRealI11R03Error("I11_DUPLICATE_OR_STALE_RECEIPT")
    source_pins = tuple(
        SourceIdentityPin(
            work_id=run["work_id"], job_id=run["job_id"],
            source_pdf_sha256=run["source_pdf_sha256"],
            model_page_text_sha256=run["model_page_text_sha256"],
        )
        for run in (run_a, run_b)
    )
    bound = {
        "status": _REAL_ADMISSION,
        "source_identity_pins": [asdict(pin) for pin in source_pins],
        "run_digests": [first[0], second[0]],
        "event_ledger_digests": [first[1], second[1]],
        "receipt_digests": [first[2], second[2]],
    }
    return VerifiedTwoRunAdmission(
        admission_digest=_digest(bound), run_digests=(first[0], second[0]),
        event_ledger_digests=(first[1], second[1]),
        receipt_digests=(first[2], second[2]),
        source_identity_pins=source_pins,
        page_maps=(first[3], second[3]),
        _issuer=_GATE_ISSUER,
    )


def _normal_text(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _verify_excerpt(excerpt: str, page_text: str) -> str:
    if excerpt and excerpt in page_text:
        return "VERIFIED_EXACT"
    if excerpt and _normal_text(excerpt) in _normal_text(page_text):
        return "NORMALIZED_ONLY"
    return "NOT_VERIFIED"


def _unverified_projection(run_a: Mapping[str, Any], run_b: Mapping[str, Any]) -> dict[str, Any]:
    content = {
        "schema": "seshat.i11.two_real_run_r03.v2", "report_id": "R03",
        "status": "UNVERIFIED_INPUTS", "actual_real_model_runs": 0,
        "candidate_jobs": [run_a.get("job_id"), run_b.get("job_id")],
        "comparison_claims": [], "admission_status": "UNVERIFIED_CALLER_ASSERTIONS",
        "product_wiring": "NOT_PRODUCT_WIRED", "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED", "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED", "provenance": "SELF_OBSERVED_UNATTESTED",
    }
    return {**content, "projection_sha256": _digest(content)}


def build_two_real_i11_r03(
    run_a: Mapping[str, Any], run_b: Mapping[str, Any],
    events_a: Sequence[Mapping[str, Any]], events_b: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]], *,
    admission: VerifiedTwoRunAdmission | None = None,
) -> dict[str, Any]:
    """Build a private R03 candidate, retaining explicit unattested provenance."""
    if admission is None:
        return _unverified_projection(run_a, run_b)
    if admission._issuer is not _GATE_ISSUER:
        raise TwoRealI11R03Error("I11_ADMISSION_NOT_GATE_ISSUED")
    for run in (run_a, run_b):
        _check_run(run)
    if admission.run_digests != (_digest(dict(run_a)), _digest(dict(run_b))):
        raise TwoRealI11R03Error("I11_ADMISSION_RUN_MISMATCH")
    expected_source_pins = tuple(
        SourceIdentityPin(
            work_id=run["work_id"], job_id=run["job_id"],
            source_pdf_sha256=run["source_pdf_sha256"],
            model_page_text_sha256=run["model_page_text_sha256"],
        )
        for run in (run_a, run_b)
    )
    if admission.source_identity_pins != expected_source_pins:
        raise TwoRealI11R03Error("I11_ADMISSION_SOURCE_IDENTITY_MISMATCH")
    ledgers = (events_a, events_b)
    current_ledgers = tuple(_digest([dict(e) for e in ledger]) for ledger in ledgers)
    if admission.event_ledger_digests != current_ledgers:
        raise TwoRealI11R03Error("I11_ADMISSION_LEDGER_MISMATCH")
    if not comparisons:
        raise TwoRealI11R03Error("I11_COMPARATIVE_CLAIMS_MISSING")
    indexed = [{_event_id(e): e for e in events} for events in ledgers]
    if any("" in ix or len(ix) != len(events) for ix, events in zip(indexed, ledgers)):
        raise TwoRealI11R03Error("I11_EVENT_ID_DUPLICATED")
    validated = []
    for claim in comparisons:
        if claim.get("kind") not in _ALLOWED:
            raise TwoRealI11R03Error("I11_INVALID_COMPARISON_KIND")
        evidence = []
        verification_states = []
        for index, (side, events, run) in enumerate((
            ("a", indexed[0], run_a), ("b", indexed[1], run_b),
        )):
            event_id = claim.get("event_" + side)
            if event_id not in events:
                raise TwoRealI11R03Error("I11_COMPARISON_EVENT_NOT_FOUND")
            event = events[event_id]
            page = claim.get("page_" + side)
            pages = event.get("pages")
            if type(page) is not int or page < 1 or not isinstance(pages, list) or page not in pages:
                raise TwoRealI11R03Error("I11_COMPARISON_PAGE_UNVERIFIED")
            excerpt = str(claim.get("excerpt_" + side) or "").strip()
            if not excerpt:
                raise TwoRealI11R03Error("I11_COMPARISON_EXCERPT_REQUIRED")
            verification = _verify_excerpt(excerpt, admission.page_maps[index].get(page, ""))
            verification_states.append(verification)
            evidence.append({
                "work_id": run["work_id"], "job_id": run["job_id"],
                "source_pdf_sha256": run["source_pdf_sha256"],
                "model_page_text_sha256": run["model_page_text_sha256"],
                "event_ledger_sha256": run["event_ledger_sha256"],
                "terminal_receipt_sha256": run["terminal_receipt_sha256"],
                "event_id": event_id, "layer": event.get("layer"), "page": page,
                "excerpt": excerpt, "excerpt_sha256": _bytes_sha(excerpt.encode("utf-8")),
                "evidence_verification": verification,
            })
        statement = str(claim.get("statement") or "").strip()
        if not statement:
            raise TwoRealI11R03Error("I11_EMPTY_COMPARISON")
        validated.append({
            "kind": claim["kind"], "statement": statement, "evidence": evidence,
            "status": (
                "SOURCE_ADDRESSED_REVIEW_PENDING"
                if all(item == "VERIFIED_EXACT" for item in verification_states)
                else "EVIDENCE_VERIFICATION_REVIEW_PENDING"
            ),
            "limits": str(claim.get("limits") or "Interpretation is provisional."),
        })
    content = {
        "schema": "seshat.i11.two_real_run_r03.v2", "report_id": "R03",
         "status": "BYTE_CONSISTENT_UNATTESTED_REVIEW_PENDING", "actual_real_model_runs": 2,
        "jobs": [run_a["job_id"], run_b["job_id"]], "method_sha256": AUTHORIAL_I11_SHA256,
        "comparison_claims": validated, "admission_status": _REAL_ADMISSION,
        "admission_digest": admission.admission_digest,
        "run_manifest_digests": list(admission.run_digests),
        "event_ledger_digests": list(admission.event_ledger_digests),
        "terminal_receipt_digests": list(admission.receipt_digests),
        "original_sources_only": None,
        "source_evidence_status": "CALLER_BYTES_PAGE_EXCERPTS_SELF_CHECKED_REVIEW_PENDING",
        "sampling_rule": "TWO_CALLER_SUPPLIED_I11_RUNS_NOT_A_POPULATION_SAMPLE",
        "coverage_status": "BOUNDED_TWO_WORK_COMPARISON",
        "implementation_missingness": {
            "source_a": "UNKNOWN", "source_b": "UNKNOWN",
            "absence_is_not_performed_im_event": True,
        },
        "product_wiring": "NOT_PRODUCT_WIRED", "independent_science_review": "PENDING",
        "scientific_acceptance": "NOT_PERFORMED", "owner_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED", "provenance": admission.provenance,
    }
    return {**content, "projection_sha256": _digest(content)}
