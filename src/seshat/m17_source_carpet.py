"""M17 source-bound Carpet execution and sanitized persistence.

This adapter executes the existing deterministic WaveEngine over the selected
source carriers.  It persists causal hashes and typed claim sediment, never raw
source text and never a claim of scientific acceptance.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from seshat.authorial_oracle import AuthorialStudyOracle, oracle_pins
from seshat.contracts import SourceCarrier, SourceContent
from seshat.fabric_waves.contracts import ActivationOutcome, WaveBudget
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import assemble_spec_law_map, uppercase_thread
from seshat.fabric_waves.ledger import RunLedger
from seshat.fabric_waves.method_body import build_safe_fixture_registry
from seshat.fabric_waves.sediment import SedimentState
from seshat.fabric_waves.source_access import FabricCarrierStore
from seshat.fabric_waves.stone import StoneDispatcher


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "study"


def _report_view_pins(reports: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for report_id in ("R01", "R02"):
        narratives = reports.get(report_id, {}).get("scientific_narratives", ())
        if narratives:
            pins[report_id] = _digest([
                item.get("view_fingerprint") for item in narratives
            ])
    return pins


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _carrier_store(readable: Mapping[str, Mapping[str, Any]]) -> FabricCarrierStore:
    carriers: dict[str, SourceCarrier] = {}
    contents: dict[str, SourceContent] = {}
    for source_id, item in readable.items():
        body = str(item["text"]).encode("utf-8")
        text_sha = hashlib.sha256(body).hexdigest()
        version = str(item.get("version") or "")
        carriers[source_id] = SourceCarrier(
            carrier_id=source_id,
            source_identity=f"{item.get('study_id')}:{source_id}",
            version=version,
            media_type="text/plain",
            content_sha256=text_sha,
            byte_length=len(body),
            metadata={"original_byte_sha256": item.get("byte_sha256")},
        )
        contents[source_id] = SourceContent(
            carrier_id=source_id,
            source_version=version,
            media_type="text/plain",
            content=body,
            content_sha256=text_sha,
            byte_length=len(body),
            complete=True,
            authorized=True,
        )
    return FabricCarrierStore(carriers=carriers, contents=contents)


def run_source_bound_carpet(
    output: Path,
    sources: Sequence[Mapping[str, Any]],
    analyses: Sequence[AuthorialStudyOracle],
    reports: Mapping[str, Mapping[str, Any]],
    *,
    resume: bool,
) -> dict[str, Any]:
    """Execute at least the available study and APORIA threads, then persist proof."""

    root = output / "carpet" / "m17_source_bound"
    root.mkdir(parents=True, exist_ok=True)
    receipt_path = root / "receipt.json"
    readable = {
        str(item["source_id"]): item for item in sources
        if item.get("status") == "WORKS" and item.get("text")
    }
    source_pins = {
        source_id: str(item.get("byte_sha256") or "")
        for source_id, item in readable.items()
    }
    analysis_pins = oracle_pins(analyses)
    report_pins = _report_view_pins(reports)
    fingerprint = _digest({
        "source_pins": source_pins,
        "analysis_pins": analysis_pins,
        "report_view_pins": report_pins,
    })
    prior: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            prior = {}
    if resume and prior.get("input_fingerprint") == fingerprint:
        replay = dict(prior)
        replay.update(
            status="REPLAYED_SOURCE_BOUND_NO_MODEL_CALL",
            replayed=True,
            duplicate_model_calls=0,
        )
        return replay

    pairs = []
    thread_roles: dict[str, str] = {}
    thread_studies: dict[str, str] = {}
    for analysis in analyses:
        selected = [carrier.source_id for carrier in analysis.carriers if carrier.source_id in readable]
        if not selected:
            continue
        study_thread = f"m17-{_slug(analysis.study_id)}-study-state"
        pair = uppercase_thread(carrier_id=selected[0], text="", thread_id=study_thread)
        pairs.append(pair)
        thread_roles[study_thread] = "STUDY_EVIDENCE_STATE"
        thread_studies[study_thread] = analysis.study_id
        contradiction_sources = [
            claim.source_id for conflict in analysis.contradictions
            for claim in analysis.claims if claim.claim_id in conflict.claim_ids
            and claim.source_id in readable
        ]
        if contradiction_sources:
            aporia_thread = f"m17-{_slug(analysis.study_id)}-aporia-review"
            pair = uppercase_thread(
                carrier_id=contradiction_sources[0], text="", thread_id=aporia_thread
            )
            pairs.append(pair)
            thread_roles[aporia_thread] = "CLAIM_CONTRADICTION_APORIA"
            thread_studies[aporia_thread] = analysis.study_id

    if not pairs:
        return {
            "schema": "seshat.m17.source-bound-carpet.v0.1",
            "status": "PARTIAL_NO_SOURCE_BOUND_THREAD",
            "input_fingerprint": fingerprint,
            "source_pins": source_pins,
            "analysis_pins": analysis_pins,
            "activation_witnesses": [],
            "at_least_two_distinct_activations": False,
            "model_calls": 0,
        }

    specs, laws = assemble_spec_law_map(pairs)
    engine = WaveEngine(
        thread_specs=specs,
        propagation_laws=laws,
        sediment=SedimentState(),
        bodies=build_safe_fixture_registry(),
        ledger=RunLedger(),
        dispatcher=StoneDispatcher(),
        carrier_store=_carrier_store(readable),
    )
    run_id = f"m17-{fingerprint[:16]}"
    run = engine.run(
        run_id=run_id,
        budget=WaveBudget(max_waves=8, max_activations=16, max_stone_events=8),
    )
    activations = [
        item for item in engine.ledger.activations_for_run(run_id)
        if item.outcome is ActivationOutcome.FIRED
    ]
    witnesses = []
    for item in activations:
        carrier_ids = list(item.source_carrier_ids)
        affected = [
            report_id for report_id, report in reports.items()
            if set(carrier_ids) & set(report.get("selection_members", ()))
        ]
        witnesses.append({
            "activation_id": item.activation_id,
            "run_id": item.run_id,
            "thread_id": item.thread_id,
            "thread_role": thread_roles.get(item.thread_id, "UNKNOWN"),
            "research_object_id": thread_studies.get(item.thread_id),
            "source_carrier_ids": carrier_ids,
            "source_sha256": {cid: source_pins.get(cid) for cid in carrier_ids},
            "source_versions": {
                cid: readable[cid].get("version") for cid in carrier_ids
            },
            "produced_sediment_ids": list(item.produced_sediment_ids),
            "reports_affected": affected,
            "outcome": item.outcome.value,
        })

    claim_sediments = []
    for analysis in analyses:
        for claim in analysis.claims:
            if claim.source_id not in readable:
                continue
            payload = claim.model_dump(mode="json")
            claim_sediments.append({
                "sediment_id": f"m17:claim:{claim.claim_id}",
                "sediment_type": "typed.claim_evidence",
                "research_object_id": analysis.research_object_id,
                "source_carrier_refs": [claim.source_id],
                "source_sha256": source_pins[claim.source_id],
                "payload_hash": _digest(payload),
                "acceptance_state": "WORKING",
                "modality": claim.modality,
                "review_state": claim.review_state,
                "reports_affected": [
                    report_id for report_id, report in reports.items()
                    if claim.source_id in report.get("selection_members", ())
                ],
            })
    contradiction_sediments = []
    claim_sources = {
        claim.claim_id: claim.source_id
        for analysis in analyses for claim in analysis.claims
    }
    for analysis in analyses:
        for conflict in analysis.contradictions:
            refs = sorted({claim_sources[cid] for cid in conflict.claim_ids})
            if not set(refs) <= set(readable):
                continue
            payload = conflict.model_dump(mode="json")
            contradiction_sediments.append({
                "sediment_id": f"m17:aporia:{conflict.contradiction_id}",
                "sediment_type": "typed.contradiction_aporia",
                "research_object_id": analysis.research_object_id,
                "claim_sediment_ids": [f"m17:claim:{cid}" for cid in conflict.claim_ids],
                "source_carrier_refs": refs,
                "payload_hash": _digest(payload),
                "acceptance_state": "WORKING",
                "role": "APORIA",
                "review_state": conflict.review_state,
                "reports_affected": [
                    report_id for report_id, report in reports.items()
                    if set(refs) <= set(report.get("selection_members", ()))
                ],
            })

    prior_analysis = prior.get("analysis_pins") or {}
    changed_analyses = sorted(
        study_id for study_id, sha in analysis_pins.items()
        if study_id in prior_analysis and prior_analysis[study_id] != sha
    )
    prior_report_pins = prior.get("report_view_pins") or {}
    invalidated_reports = sorted(
        report_id for report_id, pin in report_pins.items()
        if prior_report_pins.get(report_id) not in {None, pin}
    )
    receipt = {
        "schema": "seshat.m17.source-bound-carpet.v0.1",
        "status": (
            "WORKS_SOURCE_BOUND_ENGINE_EXECUTED"
            if len({item["thread_id"] for item in witnesses}) >= 2
            else "PARTIAL_FEWER_THAN_TWO_SOURCE_BOUND_ACTIVATIONS"
        ),
        "input_fingerprint": fingerprint,
        "source_pins": source_pins,
        "analysis_pins": analysis_pins,
        "report_view_pins": report_pins,
        "run_id": run_id,
        "run_outcome": run.outcome.value,
        "activation_witnesses": witnesses,
        "at_least_two_distinct_activations": len({
            item["thread_id"] for item in witnesses
        }) >= 2,
        "typed_claim_sediments": claim_sediments,
        "typed_contradiction_sediments": contradiction_sediments,
        "changed_analysis_ids": changed_analyses,
        "targeted_invalidated_reports": invalidated_reports,
        "source_gated_replay": True,
        "model_calls": 0,
        "duplicate_model_calls": 0,
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "replayed": False,
    }
    event_rows = [item.model_dump(mode="json") for item in engine.ledger.events]
    activation_rows = [item.model_dump(mode="json") for item in engine.ledger.activations]
    _write_jsonl(root / "events.jsonl", event_rows)
    _write_jsonl(root / "activations.jsonl", activation_rows)
    (root / "claim_sediment.json").write_text(json.dumps(
        {"claims": claim_sediments, "contradictions": contradiction_sediments},
        ensure_ascii=False, sort_keys=True, indent=2,
    ), encoding="utf-8")
    (root / "ledger.json").write_text(json.dumps(
        engine.ledger.serialize(), ensure_ascii=False, sort_keys=True, indent=2,
    ), encoding="utf-8")
    receipt_path.write_text(json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, indent=2,
    ), encoding="utf-8")
    return receipt
