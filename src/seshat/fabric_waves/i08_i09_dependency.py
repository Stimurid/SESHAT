"""Source-bound I08 claim evidence and I09 resource dependency overlays.

These are OPERATOR/REVIEWER DERIVATIVES. Original I11 stdout and frozen
MethodBody remain immutable. No scientific/customer acceptance is issued here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from seshat.fabric_waves.i11_r03_report_adapter import I11R03V2Projection
from seshat.fabric_waves.i11_two_real_r03 import (
    VerifiedTwoRunAdmission, _GATE_ISSUER,
)

EVIDENCE_MODES = frozenset({
    "S0_SOURCE_META",
    "S1_REPORTED_RESEARCH_OPERATION",
    "S2_PARTICIPANT_REPORTED_STUDIED_ACTION",
    "S3_AUTHOR_REPORTED_FIELD_OBSERVATION",
    "S4_DERIVED_ANALYTIC_THEME",
    "S5_SOURCE_EXTERNAL_NORM",
    "S6_AUTHORIAL_COUNTERFACTUAL",
    "S7_INDEPENDENTLY_TESTED_EFFECT",
})
REPRODUCTION_SCOPES = frozenset({"P1_PUBLIC_SOURCE_RECONSTRUCTION",
                                  "P2_NEW_FIELD_RESEARCH",
                                  "P3_INDEPENDENT_EFFECT_TEST"})
RESOURCE_MODES = frozenset({"SOURCE_REPORTED_USED", "AUTHORIAL_REQUIRED_FOR_REPLICATION"})
ALLOWED_RESOURCE_STATES = frozenset({"TARGET_UNKNOWN", "TARGET_AVAILABLE_ATTESTED", "TARGET_UNAVAILABLE"})
ALLOWED_CLAIM_STATES = frozenset({"SOURCE_ADDRESSED_UNREVIEWED", "UNDER_REVIEW"})
REVIEW_FAILURES = frozenset({"FALSE_ATTRIBUTION", "LOCATOR_INVALID",
                             "MODE_WRONG", "INFERENCE_UNSUPPORTED",
                             "MISSINGNESS_UNACKNOWLEDGED", "RESOURCE_UNAVAILABLE"})


class EvidenceLedgerError(ValueError):
    pass


def _verify_v2_evidence_source(
    r03: Mapping[str, Any],
    source_admission: VerifiedTwoRunAdmission | None,
) -> None:
    """A self-hashed v2 JSON is not evidence; bind it to the live byte gate.

    This gate is self-observed in-process integrity, not independent publisher
    authorization, scholarly acceptance, or customer release.
    """
    try:
        source = I11R03V2Projection.model_validate(r03)
    except ValueError as exc:
        raise EvidenceLedgerError("UNACCEPTABLE_R03_V2_SHAPE") from exc
    if (
        source.status != "BYTE_CONSISTENT_UNATTESTED_REVIEW_PENDING"
        or not isinstance(source_admission, VerifiedTwoRunAdmission)
        or source_admission._issuer is not _GATE_ISSUER
    ):
        raise EvidenceLedgerError("R03_V2_GATE_ADMISSION_REQUIRED")
    if (
        source.admission_digest != source_admission.admission_digest
        or source.run_manifest_digests != source_admission.run_digests
        or source.event_ledger_digests != source_admission.event_ledger_digests
        or source.terminal_receipt_digests != source_admission.receipt_digests
    ):
        raise EvidenceLedgerError("R03_V2_ADMISSION_BINDING_MISMATCH")
    for claim in source.comparison_claims:
        if claim.status != "SOURCE_ADDRESSED_REVIEW_PENDING":
            raise EvidenceLedgerError("R03_V2_EXACT_SOURCE_EVIDENCE_REQUIRED")
        for index, evidence in enumerate(claim.evidence):
            pin = source_admission.source_identity_pins[index]
            if (
                evidence.work_id != pin.work_id
                or evidence.job_id != pin.job_id
                or evidence.source_pdf_sha256 != pin.source_pdf_sha256
                or evidence.model_page_text_sha256 != pin.model_page_text_sha256
                or evidence.event_ledger_sha256
                != source_admission.event_ledger_digests[index]
                or evidence.terminal_receipt_sha256
                != source_admission.receipt_digests[index]
            ):
                raise EvidenceLedgerError("R03_V2_SOURCE_IDENTITY_MISMATCH")
            if (
                evidence.evidence_verification != "VERIFIED_EXACT"
                or evidence.page not in source_admission.page_maps[index]
                or evidence.excerpt
                not in source_admission.page_maps[index][evidence.page]
            ):
                raise EvidenceLedgerError("R03_V2_EXACT_SOURCE_EVIDENCE_REQUIRED")


def _hash(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceLedgerError("MISSING_" + name)
    return value.strip()


def build_evidence_ledger(
    r03: Mapping[str, Any], *,
    claim_specs: Sequence[Mapping[str, Any]],
    source_admission: VerifiedTwoRunAdmission | None = None,
    derived_claims: Sequence[Mapping[str, Any]] = (),
    resource_cards: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Explicitly register epistemic modes, claims and infrastructure cuts.

    Neither a comparison page number nor a publisher license upgrades source
    evidence to independently tested effect or owner acceptance.
    """
    schema = r03.get("schema")
    if (
        schema not in {
            "seshat.i11.two_real_run_r03.v1",
            "seshat.i11.two_real_run_r03.v2",
        }
        or r03.get("actual_real_model_runs") != 2
        or r03.get("scientific_acceptance") != "NOT_PERFORMED"
        or r03.get("customer_release") != "BLOCKED"
    ):
        raise EvidenceLedgerError("UNACCEPTABLE_R03_SOURCE")
    if schema == "seshat.i11.two_real_run_r03.v2":
        _verify_v2_evidence_source(r03, source_admission)
        source_provenance = "V2_BYTE_COHERENT_SELF_OBSERVED_UNATTESTED"
    else:
        # Legacy v1 is retained for historical review overlays, never as
        # proof of a byte-verified new authorial ModelRun.
        source_provenance = "V1_LEGACY_ARCHIVAL_UNATTESTED"
    claims = r03.get("comparison_claims", [])
    if not isinstance(claims, list) or len(claims) != len(claim_specs):
        raise EvidenceLedgerError("CLAIM_SPEC_COUNT_MISMATCH")
    registered: dict[str, dict[str, Any]] = {}
    for i, (claim, spec) in enumerate(zip(claims, claim_specs), 1):
        claim_id = f"R03.C{i:02}"
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != 2:
            raise EvidenceLedgerError("TWO_SOURCE_EVIDENCE_REQUIRED")
        modes = spec.get("evidence_modes")
        if not isinstance(modes, list) or len(modes) != 2:
            raise EvidenceLedgerError("TWO_SOURCE_EVIDENCE_MODES_REQUIRED")
        if any(mode not in EVIDENCE_MODES for mode in modes):
            raise EvidenceLedgerError("UNKNOWN_EVIDENCE_MODE")
        if any(mode == "S7_INDEPENDENTLY_TESTED_EFFECT" for mode in modes):
            raise EvidenceLedgerError("S7_REQUIRES_SEPARATE_ATTESTED_EFFECT")
        for e in evidence:
            if not all(e.get(key) for key in
                       ("work_id", "job_id", "source_pdf_sha256",
                        "model_page_text_sha256", "event_id", "page")):
                raise EvidenceLedgerError("UNBOUND_SOURCE_EVENT")
        scope = spec.get("reproduction_scope")
        if scope not in REPRODUCTION_SCOPES:
            raise EvidenceLedgerError("UNKNOWN_REPRODUCTION_SCOPE")
        registered[claim_id] = {
            "claim_id": claim_id,
            "source_evidence": copy.deepcopy(evidence),
            "evidence_modes": list(modes),
            "claim_scope": _required(spec.get("claim_scope"), "CLAIM_SCOPE"),
            "inferential_step": _required(spec.get("inferential_step"), "INFERENTIAL_STEP"),
            "missing_evidence": _required(spec.get("missing_evidence"), "MISSING_EVIDENCE"),
            "allowed_conclusion": _required(spec.get("allowed_conclusion"), "ALLOWED_CONCLUSION"),
            "forbidden_promotion": _required(spec.get("forbidden_promotion"), "FORBIDDEN_PROMOTION"),
            "reproduction_scope": scope,
            "status": "SOURCE_ADDRESSED_UNREVIEWED",
            "reviewer_overlays": [],
            "provenance": (
                "OPERATOR_AUTHORED_WITH_SOURCE_EVENT_POINTERS"
                if source_provenance.startswith("V2_")
                else "OPERATOR_AUTHORED_WITH_UNVERIFIED_LEGACY_V1_POINTERS"
            ),
        }
    for claim in derived_claims:
        name = _required(claim.get("claim_id"), "DERIVED_CLAIM_ID")
        if name in registered:
            raise EvidenceLedgerError("DUPLICATE_CLAIM_ID")
        scope = claim.get("reproduction_scope")
        if scope not in REPRODUCTION_SCOPES:
            raise EvidenceLedgerError("UNKNOWN_REPRODUCTION_SCOPE")
        if scope != "P1_PUBLIC_SOURCE_RECONSTRUCTION" and claim.get("target_available") is True:
            raise EvidenceLedgerError("TARGET_AVAILABILITY_NOT_ATTESTED")
        registered[name] = {
            "claim_id": name,
            "depends_on": list(claim.get("depends_on", ())),
            "reproduction_scope": scope,
            "status": "SOURCE_ADDRESSED_UNREVIEWED",
            "provenance": "AUTHORIAL_NEXT_STEP_NOT_IMPLEMENTED",
            "reviewer_overlays": [],
        }
    for entry in registered.values():
        for parent in entry.get("depends_on", []):
            if parent not in registered or parent == entry["claim_id"]:
                raise EvidenceLedgerError("INVALID_CLAIM_DEPENDENCY")
    # Every graph must be a DAG, otherwise selective invalidation is ambiguous.
    for cid in registered:
        stack = [(cid, frozenset())]
        while stack:
            node, seen = stack.pop()
            if node in seen:
                raise EvidenceLedgerError("CYCLIC_CLAIM_DEPENDENCY")
            stack.extend((parent, seen | {node})
                         for parent in registered[node].get("depends_on", []))
    resources: dict[str, dict[str, Any]] = {}
    for card in resource_cards:
        rid = _required(card.get("resource_id"), "RESOURCE_ID")
        if rid in resources:
            raise EvidenceLedgerError("DUPLICATE_RESOURCE_ID")
        mode = card.get("resource_mode")
        if mode not in RESOURCE_MODES:
            raise EvidenceLedgerError("UNKNOWN_RESOURCE_MODE")
        if card.get("criticality") not in ("CRITICAL", "SUPPORTING"):
            raise EvidenceLedgerError("UNKNOWN_RESOURCE_CRITICALITY")
        status = card.get("target_availability", "TARGET_UNKNOWN")
        if status != "TARGET_UNKNOWN":
            raise EvidenceLedgerError("TARGET_AVAILABILITY_NOT_ATTESTED")
        if mode == "SOURCE_REPORTED_USED" and not card.get("source_event"):
            raise EvidenceLedgerError("SOURCE_REPORTED_USE_NEEDS_EVENT")
        scope = card.get("reproduction_scope")
        if scope not in REPRODUCTION_SCOPES:
            raise EvidenceLedgerError("UNKNOWN_REPRODUCTION_SCOPE")
        dependent_ids = list(card.get("dependent_claim_ids", ()))
        if any(cid not in registered for cid in dependent_ids):
            raise EvidenceLedgerError("UNKNOWN_RESOURCE_DEPENDENT")
        resources[rid] = {
            "resource_id": rid, "resource_mode": mode,
            "source_event": copy.deepcopy(card.get("source_event")),
            "material": _required(card.get("material"), "MATERIAL"),
            "people_skill": _required(card.get("people_skill"), "PEOPLE_SKILL"),
            "site_or_tool": _required(card.get("site_or_tool"), "SITE_OR_TOOL"),
            "rights": _required(card.get("rights"), "RIGHTS"),
            "source_address": _required(card.get("source_address"), "SOURCE_ADDRESS"),
            "failure_mode": _required(card.get("failure_mode"), "FAILURE_MODE"),
            "criticality": card["criticality"], "reproduction_scope": scope,
            "substitute_is_equivalent": False,
            "target_availability": status,
            "dependent_claim_ids": dependent_ids,
        }
    original = {
        "schema": "seshat.i08_i09.evidence_resource_overlay.v1",
        "based_on_r03_projection_sha256": r03.get("projection_sha256"),
        "claim_cards": registered,
        "resource_cards": resources,
        "source_model_outputs_modified": False,
        "source_admission_provenance": source_provenance,
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
    }
    return {**original, "projection_sha256": _hash(original)}


def apply_review_overlay(
    ledger: Mapping[str, Any], *,
    job_id: str,
    event_id: str,
    defect: str,
    note: str,
    overlay_id: str,
) -> dict[str, Any]:
    """Downgrade only claims depending on a disputed event, transitively."""
    if defect not in REVIEW_FAILURES:
        raise EvidenceLedgerError("INVALID_DEFECT")
    if ledger.get("source_model_outputs_modified") is not False:
        raise EvidenceLedgerError("ORIGINAL_MODEL_IMMUTABILITY_REQUIRED")
    revision = copy.deepcopy(dict(ledger))
    cards = revision["claim_cards"]
    affected = {
        cid for cid, card in cards.items()
        if any(e.get("job_id") == job_id and e.get("event_id") == event_id
               for e in card.get("source_evidence", []))
    }
    if not affected:
        raise EvidenceLedgerError("SOURCE_EVENT_NOT_FOUND")
    changed = set(affected)
    while True:
        grown = changed | {
            cid for cid, card in cards.items()
            if set(card.get("depends_on", [])) & changed
        }
        if grown == changed:
            break
        changed = grown
    for cid in changed:
        card = cards[cid]
        card["status"] = "UNDER_REVIEW"
        card["reviewer_overlays"].append({
            "overlay_id": overlay_id, "defect": defect,
            "note": _required(note, "REVIEW_NOTE"),
            "source_job_id": job_id, "source_event_id": event_id,
            "directly_impacted": cid in affected,
        })
    revision.pop("projection_sha256", None)
    return {**revision, "projection_sha256": _hash(revision)}


def apply_resource_cut(
    ledger: Mapping[str, Any], *, resource_id: str, evidence_note: str
) -> dict[str, Any]:
    """Resource cut affects its eligible target-scope claims, never source P1."""
    revision = copy.deepcopy(dict(ledger))
    resources = revision.get("resource_cards", {})
    if resource_id not in resources:
        raise EvidenceLedgerError("RESOURCE_NOT_FOUND")
    card = resources[resource_id]
    if card["criticality"] != "CRITICAL":
        raise EvidenceLedgerError("RESOURCE_NOT_CRITICAL")
    if card["reproduction_scope"] == "P1_PUBLIC_SOURCE_RECONSTRUCTION":
        raise EvidenceLedgerError("SOURCE_PUBLICATION_NOT_REVOKED_BY_SITE_CUT")
    card["target_availability"] = "TARGET_UNAVAILABLE"
    cards = revision["claim_cards"]
    touched = set()
    for cid in card["dependent_claim_ids"]:
        if cards[cid]["reproduction_scope"] != "P1_PUBLIC_SOURCE_RECONSTRUCTION":
            touched.add(cid)
    while True:
        grown = touched | {cid for cid, item in cards.items()
                           if set(item.get("depends_on", [])) & touched}
        if grown == touched:
            break
        touched = grown
    for cid in touched:
        cards[cid]["status"] = "UNDER_REVIEW"
        cards[cid]["reviewer_overlays"].append({
            "overlay_id": "CUT:" + resource_id,
            "defect": "RESOURCE_UNAVAILABLE",
            "note": _required(evidence_note, "REVIEW_NOTE"),
        })
    revision.pop("projection_sha256", None)
    return {**revision, "projection_sha256": _hash(revision)}
