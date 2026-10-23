"""M13-M16 report-first product preview.

The preview is deliberately an operator-local, no-server product.  It reads
owner-selected PDF/TXT files, records immutable source and optional historical
method-output pins, projects nine different report purposes, and keeps a
durable replay ledger.  It never turns an engineering run into scientific or
customer acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from seshat.authorial_oracle import (
    AuthorialStudyOracle,
    analysis_view,
    load_study_analyses,
    oracle_pins,
)
from seshat.m17_source_carpet import run_source_bound_carpet

SCHEMA = "seshat.product-preview.v1"
REPORT_PURPOSES = {
    "R01": "Study assembly reconstruction",
    "R02": "Object-method-evidence",
    "R03": "Map of the selected research field",
    "R04": "Object-method-infrastructure atlas",
    "R05": "Seven external-field entity dossiers",
    "R06": "Local-to-external comparison",
    "R07": "Research opportunities",
    "R08": "Learning-program projection",
    "R09": "Institution decision options",
}
EXTERNAL_DOSSIERS = (
    "problems", "objects", "methods", "instruments_and_infrastructure",
    "norms_and_evidence", "concepts", "result_and_translation_forms",
)
SOURCE_KINDS = {"A", "D", "ARTICLE", "EXTERNAL", "INTERNAL"}
SELECTOR_MODES = {"A_ONLY", "D_ONLY", "A_PLUS_D", "ARTICLE_ONLY", "ARBITRARY"}


class ProductPreviewError(ValueError):
    """Typed, operator-readable manifest or replay error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _json_bytes(value)
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductPreviewError(f"MANIFEST_UNREADABLE: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProductPreviewError("MANIFEST_OBJECT_REQUIRED")
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if not str(manifest.get("product_id") or "").strip():
        raise ProductPreviewError("PRODUCT_ID_REQUIRED")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ProductPreviewError("SOURCES_REQUIRED")
    source_ids: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ProductPreviewError("SOURCE_OBJECT_REQUIRED")
        source_id = str(source.get("source_id") or "")
        study_id = str(source.get("study_id") or "")
        version = str(source.get("version") or "")
        if not source_id or not study_id or not version:
            raise ProductPreviewError("SOURCE_ID_STUDY_ID_VERSION_REQUIRED")
        if source_id == study_id:
            raise ProductPreviewError("STUDY_ID_MUST_DIFFER_FROM_SOURCE_CARRIER_ID")
        if source_id in source_ids:
            raise ProductPreviewError("DUPLICATE_SOURCE_CARRIER_ID")
        source_ids.add(source_id)
        identity = (study_id, str(source.get("path") or ""), version)
        if identity in identities:
            raise ProductPreviewError("DUPLICATE_STUDY_CARRIER")
        identities.add(identity)
        if str(source.get("source_kind") or "") not in SOURCE_KINDS:
            raise ProductPreviewError("UNKNOWN_SOURCE_KIND")
    selectors = manifest.get("selectors")
    if not isinstance(selectors, list) or len(selectors) < 3:
        raise ProductPreviewError("AT_LEAST_THREE_SELECTORS_REQUIRED")
    if "archive_census_count" in manifest:
        raise ProductPreviewError(
            "DECLARED_ARCHIVE_COUNT_FORBIDDEN_USE_ARCHIVE_MANIFEST"
        )
    selector_ids: set[str] = set()
    for selector in selectors:
        selector_id = str(selector.get("selector_id") or "")
        if not selector_id or selector_id in selector_ids:
            raise ProductPreviewError("SELECTOR_ID_INVALID_OR_DUPLICATE")
        selector_ids.add(selector_id)
        if selector.get("mode") not in SELECTOR_MODES:
            raise ProductPreviewError("UNKNOWN_SELECTOR_MODE")


def _extract_source(path: Path) -> tuple[str, int | None, str]:
    suffix = path.suffix.casefold()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8-sig"), None, "TEXT_EXTRACTED"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency is pinned by project
            raise ProductPreviewError("PDF_READER_UNAVAILABLE") from exc
        reader = PdfReader(path)
        pages = []
        for number, page in enumerate(reader.pages, 1):
            pages.append(f"\n=== PAGE {number} ===\n{page.extract_text() or ''}")
        text = "".join(pages)
        status = "TEXT_EXTRACTED" if text.strip() else "PARTIAL_NO_EXTRACTED_TEXT"
        return text, len(reader.pages), status
    raise ProductPreviewError(f"UNSUPPORTED_SOURCE_FORMAT: {suffix or '<none>'}")


def ingest_sources(manifest: Mapping[str, Any], base: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in manifest["sources"]:
        record = {
            "source_id": spec["source_id"],
            "study_id": spec["study_id"],
            "source_kind": spec["source_kind"],
            "version": spec["version"],
            "title": spec.get("title") or spec["source_id"],
            "year": spec.get("year"),
            "tags": sorted(set(str(x) for x in spec.get("tags", ()))),
            "objects": sorted(set(str(x) for x in spec.get("objects", ()))),
            "methods": sorted(set(str(x) for x in spec.get("methods", ()))),
            "infrastructure": sorted(
                set(str(x) for x in spec.get("infrastructure", ()))
            ),
            "excluded": bool(spec.get("excluded", False)),
            "path": str(spec.get("path") or ""),
            "status": "PARTIAL",
            "byte_sha256": None,
            "byte_length": None,
            "page_count": None,
            "text_extraction": "NOT_ATTEMPTED",
            "text": "",
            "limitations": [],
        }
        if record["excluded"]:
            record["status"] = "EXCLUDED_BY_OWNER_POLICY"
            record["text_extraction"] = "NOT_READ"
            records.append(record)
            continue
        path = Path(record["path"])
        if not path.is_absolute():
            path = base / path
        try:
            raw = path.read_bytes()
            text, pages, extraction = _extract_source(path)
            record.update(
                status="WORKS" if extraction == "TEXT_EXTRACTED" else "PARTIAL",
                byte_sha256=hashlib.sha256(raw).hexdigest(),
                byte_length=len(raw),
                page_count=pages,
                text_extraction=extraction,
                text=text,
            )
            if extraction != "TEXT_EXTRACTED":
                record["limitations"].append("NO_EXTRACTED_TEXT")
        except Exception as exc:
            # pypdf raises several format-specific exceptions.  Intake remains
            # inspectable and partial; it never invents text or silently drops.
            record["text_extraction"] = "FAILED"
            record["limitations"].append(f"FILE_UNREADABLE: {type(exc).__name__}: {exc}")
        records.append(record)
    return records


def select_sources(
    selector: Mapping[str, Any], sources: Iterable[Mapping[str, Any]]
) -> list[str]:
    mode = selector["mode"]
    filters = selector.get("filters") or {}
    members: list[str] = []
    for source in sources:
        if source.get("excluded"):
            continue
        kind = source["source_kind"]
        include = (
            (mode == "A_ONLY" and kind == "A")
            or (mode == "D_ONLY" and kind == "D")
            or (mode == "A_PLUS_D" and kind in {"A", "D"})
            or (mode == "ARTICLE_ONLY" and kind == "ARTICLE")
            or mode == "ARBITRARY"
        )
        if not include:
            continue
        if filters.get("study_ids") and source["study_id"] not in filters["study_ids"]:
            continue
        if filters.get("source_ids") and source["source_id"] not in filters["source_ids"]:
            continue
        if filters.get("source_kinds") and kind not in filters["source_kinds"]:
            continue
        if filters.get("tags") and not set(filters["tags"]) <= set(source.get("tags", ())):
            continue
        members.append(source["source_id"])
    return sorted(members)


def build_selections(
    manifest: Mapping[str, Any], sources: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    result = {}
    for selector in manifest["selectors"]:
        members = select_sources(selector, sources)
        result[selector["selector_id"]] = {
            "selector_id": selector["selector_id"],
            "mode": selector["mode"],
            "members": members,
            "membership_sha256": _digest(members),
            "status": "WORKS" if members else "PARTIAL_EMPTY_SELECTION",
            "missing_members_not_assumed": True,
        }
    distinct = {tuple(item["members"]) for item in result.values()}
    if len(distinct) < 3:
        raise ProductPreviewError("SELECTORS_DO_NOT_HAVE_THREE_DISTINCT_MEMBERSHIPS")
    return result


def load_method_outputs(manifest: Mapping[str, Any], base: Path) -> list[dict[str, Any]]:
    outputs = []
    for item in manifest.get("method_outputs", ()):
        path = Path(str(item.get("path") or ""))
        if not path.is_absolute():
            path = base / path
        record = {
            "study_id": item.get("study_id"),
            "method_id": item.get("method_id"),
            "version": item.get("version"),
            "path": str(item.get("path") or ""),
            "status": "PARTIAL_METHOD_OUTPUT_MISSING",
            "sha256": None,
            "payload": None,
            "immutable_input": True,
        }
        try:
            raw = path.read_bytes()
            record.update(status="WORKS", sha256=hashlib.sha256(raw).hexdigest())
            record["payload"] = json.loads(raw.decode("utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        outputs.append(record)
    return outputs


def load_archive_census(manifest: Mapping[str, Any], base: Path) -> dict[str, Any] | None:
    """Count only records actually present in an optional owner manifest."""

    value = manifest.get("archive_manifest")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProductPreviewError("ARCHIVE_MANIFEST_UNREADABLE") from exc
    records = payload if isinstance(payload, list) else payload.get("records")
    if not isinstance(records, list):
        raise ProductPreviewError("ARCHIVE_MANIFEST_RECORDS_REQUIRED")
    return {
        "path": str(value), "sha256": hashlib.sha256(raw).hexdigest(),
        "record_count": len(records), "records_read_or_analysed": False,
        "meaning": "ARCHIVE_CENSUS_ONLY",
    }


def _words(records: Iterable[Mapping[str, Any]]) -> Counter[str]:
    stop = {"this", "that", "with", "from", "were", "have", "into", "using", "study"}
    words: Counter[str] = Counter()
    for record in records:
        for token in re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{3,}", record.get("text", "")):
            folded = token.casefold()
            if folded not in stop:
                words[folded] += 1
    return words


def _source_refs(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": r["source_id"], "study_id": r["study_id"],
            "version": r["version"], "byte_sha256": r["byte_sha256"],
            "status": r["status"], "drillback": r["path"],
        }
        for r in records
    ]


def build_reports(
    manifest: Mapping[str, Any], sources: list[dict[str, Any]],
    selections: Mapping[str, Mapping[str, Any]], method_outputs: list[dict[str, Any]],
    analyses: Sequence[AuthorialStudyOracle] = (),
) -> dict[str, dict[str, Any]]:
    by_id = {s["source_id"]: s for s in sources}
    default_selector = str(manifest.get("default_selector") or next(iter(selections)))
    report_selectors = dict(manifest.get("report_selectors") or {})
    method_by_study = defaultdict(list)
    for output in method_outputs:
        method_by_study[output["study_id"]].append(output)
    external = list(manifest.get("external_evidence") or ())
    reports: dict[str, dict[str, Any]] = {}

    def context(report_id: str) -> tuple[str, list[dict[str, Any]]]:
        selector_id = str(report_selectors.get(report_id) or default_selector)
        if selector_id not in selections:
            raise ProductPreviewError(f"UNKNOWN_REPORT_SELECTOR: {report_id}:{selector_id}")
        return selector_id, [by_id[x] for x in selections[selector_id]["members"]]

    for report_id, purpose in REPORT_PURPOSES.items():
        selector_id, chosen = context(report_id)
        limitations = []
        if any(x["status"] != "WORKS" for x in chosen):
            limitations.append("ONE_OR_MORE_SELECTED_SOURCES_PARTIAL")
        if not chosen:
            limitations.append("NO_SELECTED_SOURCE")
        base = {
            "report_id": report_id, "purpose": purpose, "selector_id": selector_id,
            "selection_members": [x["source_id"] for x in chosen],
            "source_regimes_present": sorted({x["source_kind"] for x in chosen}),
            "source_references": _source_refs(chosen), "limitations": limitations,
            "scientific_acceptance": "NOT_PERFORMED", "customer_release": "BLOCKED",
        }
        studies = sorted({x["study_id"] for x in chosen})
        if report_id == "R01":
            base["study_assemblies"] = [
                {
                    "study_id": study,
                    "source_ids": [x["source_id"] for x in chosen if x["study_id"] == study],
                    "objects": sorted({v for x in chosen if x["study_id"] == study for v in x["objects"]}),
                    "methods": sorted({v for x in chosen if x["study_id"] == study for v in x["methods"]}),
                    "method_outputs": [
                        {k: out.get(k) for k in ("method_id", "version", "status", "sha256")}
                        for out in method_by_study[study]
                    ],
                    "unfinished": "METHOD_OUTPUT_MISSING" if not method_by_study[study] else None,
                }
                for study in studies
            ]
        elif report_id == "R02":
            base["object_method_evidence"] = [
                {"study_id": study,
                 "objects": sorted({v for x in chosen if x["study_id"] == study for v in x["objects"]}),
                 "methods": sorted({v for x in chosen if x["study_id"] == study for v in x["methods"]}),
                 "evidence": _source_refs(x for x in chosen if x["study_id"] == study),
                 "status": "SOURCE_ADDRESSED_UNREVIEWED"}
                for study in studies
            ]
        elif report_id == "R03":
            base["field_map"] = {
                "scope": "SELECTED_CORPUS_FIELD_NOT_GLOBAL_FIELD",
                "study_count": len(studies), "source_count": len(chosen),
                "objects": Counter(v for x in chosen for v in x["objects"]),
                "methods": Counter(v for x in chosen for v in x["methods"]),
                "infrastructure": Counter(v for x in chosen for v in x["infrastructure"]),
                "recurring_terms": _words(chosen).most_common(12),
                "years": Counter(str(x.get("year") or "UNKNOWN") for x in chosen),
            }
            if len(studies) < 2:
                base["limitations"].append("CORPUS_TOO_SMALL_FOR_FIELD_PATTERN")
        elif report_id == "R04":
            base["atlas_rows"] = [
                {"study_id": study,
                 "objects": sorted({v for x in chosen if x["study_id"] == study for v in x["objects"]}),
                 "methods": sorted({v for x in chosen if x["study_id"] == study for v in x["methods"]}),
                 "infrastructure": sorted({v for x in chosen if x["study_id"] == study for v in x["infrastructure"]}),
                 "actual_resource_availability": "UNKNOWN_WITHOUT_INTERNAL_SRC_C"}
                for study in studies
            ]
        elif report_id == "R05":
            provided = {str(x.get("entity")): x for x in external}
            base["dossiers"] = [
                {"entity": entity, "status": "WORKS" if entity in provided else "PARTIAL_MISSING_EXTERNAL_SRC_D",
                 "evidence": provided.get(entity),
                 "line_modes": (provided.get(entity) or {}).get("line_modes", [])}
                for entity in EXTERNAL_DOSSIERS
            ]
            if len(provided) < 7:
                base["limitations"].append("EXTERNAL_SRC_D_INCOMPLETE")
        elif report_id == "R06":
            base["comparisons"] = [] if not external else [
                {"local_entity": x.get("entity"), "external_status": x.get("status", "UNREVIEWED"),
                 "claim": "COMPARISON_CANDIDATE_NOT_GLOBAL_NOVELTY"} for x in external
            ]
            if not external:
                base["limitations"].append("NO_EXTERNAL_SRC_D_NO_POSITIONING")
        elif report_id == "R07":
            base["opportunities"] = [
                {"opportunity_id": "O1", "type": "coverage", "proposal": "Obtain missing A/D counterpart for unpaired studies"},
                {"opportunity_id": "O2", "type": "method", "proposal": "Review recurring object-method gaps with source-addressed evidence"},
                {"opportunity_id": "O3", "type": "external", "proposal": "Build the missing external dossier before novelty claims"},
            ]
            base["opportunity_status"] = "CANDIDATES_REQUIRE_RESOURCE_AND_EXTERNAL_CHECK"
        elif report_id == "R08":
            base["learning_projection"] = {
                "cases": studies, "activities": ["object reconstruction", "method-evidence drillback", "field-map critique"],
                "human_function": "participant performs consequential interpretation",
                "person_ranking": "FORBIDDEN",
            }
        else:
            base["decision_options"] = [
                {"option_id": "D1", "option": "Commission missing-source acquisition", "decision_status": "HUMAN_ONLY"},
                {"option_id": "D2", "option": "Fund source-grounded method review", "decision_status": "HUMAN_ONLY"},
                {"option_id": "D3", "option": "Defer external positioning until SRC-D exists", "decision_status": "HUMAN_ONLY"},
            ]
            base["authorized_decision"] = None
            if not external:
                base["limitations"].append("NO_EXTERNAL_SRC_D")
            base["limitations"].append("NO_INTERNAL_SRC_C_FOR_CAPACITY_CLAIMS")
        if report_id in {"R01", "R02"} and analyses:
            views = [
                view for analysis in analyses
                if analysis.study_id in studies
                for view in [analysis_view(
                    analysis, [item["source_id"] for item in chosen], report_id
                )]
                if view is not None
            ]
            if views:
                base["study_analyses"] = [view["evidence_state"] for view in views]
                base["scientific_narratives"] = [
                    {
                        "study_id": view["evidence_state"]["study_id"],
                        "origin": view["narrative_origin"],
                        "text": view["narrative"],
                        "view_fingerprint": view["view_fingerprint"],
                    }
                    for view in views
                ]
                base["method_run_performed"] = False
                if any(view["evidence_state"]["local_state"] == "PARTIAL" for view in views):
                    base["limitations"].append("STUDY_ANALYSIS_SELECTOR_SCOPED_PARTIAL")
                if any(view["evidence_state"].get("omitted_answer_count", 0) for view in views):
                    base["limitations"].append("STUDY_ANALYSIS_ANSWERS_OMITTED")
        base["status"] = "PARTIAL" if base["limitations"] else "WORKS_UNREVIEWED"
        reports[report_id] = base
    return reports


def build_operation_route(
    sources: list[dict[str, Any]], method_outputs: list[dict[str, Any]],
    carpet: Mapping[str, Any],
) -> dict[str, Any]:
    methods = {(x["study_id"], x["method_id"]): x for x in method_outputs}
    studies = sorted({x["study_id"] for x in sources if not x["excluded"]})
    operations = []
    for study in studies:
        study_sources = [x for x in sources if x["study_id"] == study and not x["excluded"]]
        readable = [x for x in study_sources if x["status"] == "WORKS"]
        for method_id in ("I11", "I08", "I09", "I12", "C09"):
            supplied = methods.get((study, method_id))
            operations.append({
                "study_id": study, "method_id": method_id,
                "input_source_ids": [x["source_id"] for x in study_sources],
                "status": (
                    "WORKS_IMMUTABLE_SUPPLIED_OUTPUT" if supplied and supplied["status"] == "WORKS"
                    else "PARTIAL_METHOD_OUTPUT_MISSING" if readable
                    else "PARTIAL_SOURCE_UNREADABLE"
                ),
                "method_output_sha256": supplied.get("sha256") if supplied else None,
            })
    source_bound = carpet.get("source_bound") or {}
    source_witnesses = source_bound.get("activation_witnesses", [])
    bound = bool(source_bound.get("at_least_two_distinct_activations"))
    return {
        "route": "source→typed operations→events→wave→activation→sediment→report",
        "typed_operations": operations,
        "cross_thread_activation_witnesses": source_witnesses or carpet.get(
            "activation_witnesses", []
        ),
        "selective_source_delta_replay": carpet.get("selective_source_delta_replay"),
        "engine_status": carpet.get("status", "PARTIAL_NOT_RUN"),
        "selected_sources_causally_bound_to_engine_activations": bound,
        "binding_status": (
            "WORKS_SOURCE_BOUND" if bound
            else "PARTIAL_SYNTHETIC_ENGINE_DEMONSTRATION"
        ),
        "no_manually_fabricated_engine_events": True,
    }


def run_carpet(output: Path, manifest: Mapping[str, Any], base: Path) -> dict[str, Any]:
    carpet_dir = output / "carpet"
    receipt_path = carpet_dir / "m6_portfolio_receipt.json"
    if receipt_path.is_file():
        status = "REPLAYED_EXISTING_ENGINE_ARTIFACTS"
    else:
        fixture_value = manifest.get("carpet_fixture")
        if fixture_value:
            fixture = Path(str(fixture_value))
            if not fixture.is_absolute():
                fixture = base / fixture
        else:
            from seshat.fabric_waves.m6_research_engine import default_fixture_path
            fixture = default_fixture_path()
        if fixture is None or not Path(fixture).is_file():
            return {"status": "PARTIAL_CARPET_FIXTURE_UNAVAILABLE", "activation_witnesses": []}
        from seshat.fabric_waves.m6_research_engine import ORIGINAL_FIXTURE_SHA256, run_m6_portfolio
        run_m6_portfolio(
            Path(fixture), carpet_dir, approved_sha256=ORIGINAL_FIXTURE_SHA256,
            verify_subprocess_resume=False,
        )
        status = "WORKS_ENGINE_EXECUTED"
    witnesses: list[dict[str, Any]] = []
    selective = []
    for activation_path in sorted(carpet_dir.glob("*/activations.jsonl")):
        for line in activation_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("outcome") == "FIRED" and row.get("thread_id") not in {
                x.get("thread_id") for x in witnesses
            }:
                witnesses.append({
                    "host": activation_path.parent.name,
                    "activation_id": row.get("activation_id"),
                    "run_id": row.get("run_id"), "thread_id": row.get("thread_id"),
                    "source_carrier_ids": row.get("source_carrier_ids", []),
                    "produced_sediment_ids": row.get("produced_sediment_ids", []),
                })
    for oracle_path in sorted(carpet_dir.glob("*/oracles.json")):
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        for row in oracle.get("rows", []):
            if row.get("oracle_id") in {"RM04", "RM13"}:
                selective.append({"host": oracle_path.parent.name, **row})
    return {
        "status": status,
        "activation_witnesses": witnesses[:8],
        "at_least_two_cross_thread_activations": len(witnesses) >= 2,
        "selective_source_delta_replay": selective,
        "artifact_root": str(carpet_dir),
    }


def run_f09a_host_batches(output: Path) -> dict[str, Any]:
    """Run/replay the existing durable F09A on two explicit host profiles."""

    from tempfile import TemporaryDirectory

    from seshat.batch import BatchManifest, resume_batch, run_batch
    from seshat.batch_demo import demo_manifest
    from seshat.report_demo import install_fixture

    results: dict[str, Any] = {}
    for host in ("sechenovka-like", "meteorology"):
        target = output / "f09a_hosts" / host
        with TemporaryDirectory(prefix=f"seshat-preview-{host}-") as scratch:
            runtime = install_fixture(Path(scratch), host)
            manifest_path = target / "manifest.json"
            if manifest_path.is_file():
                batch_manifest = BatchManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
                receipt = resume_batch(
                    target, batch_manifest, runtime, caller_id="demo",
                    rights_scope="synthetic-public",
                )
                mode = "REPLAYED"
            else:
                batch_manifest = demo_manifest(
                    host, runtime, batch_id=f"product-preview-{host}"
                )
                receipt = run_batch(
                    target, batch_manifest, runtime, resume=False, caller_id="demo",
                    rights_scope="synthetic-public",
                )
                mode = "EXECUTED"
        results[host] = {
            "mode": mode, "batch_id": receipt.batch_id,
            "item_count": receipt.item_count, "code_pass": receipt.code_pass,
            "relative_path": f"f09a_hosts/{host}",
            "item_paths": [item.relative_path for item in receipt.items],
            "scientific_accepted": receipt.scientific_accepted,
        }
    return results


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [f"# {report['report_id']} — {report['purpose']}", "",
             f"Status: **{report['status']}**", "",
             f"Selector: `{report['selector_id']}`", "",
             "## Evidence drillback", ""]
    for ref in report["source_references"]:
        lines.append(
            f"- `{ref['source_id']}` study `{ref['study_id']}`, version `{ref['version']}`, "
            f"SHA-256 `{ref['byte_sha256'] or 'UNAVAILABLE'}`, path `{ref['drillback']}`"
        )
    narratives = report.get("scientific_narratives") or ()
    if narratives:
        lines.extend([
            "", "## Scientific narrative", "",
            "Epistemic legend: **SOURCE_REPORTED** fixes what a source says; "
            "**E2_RECONSTRUCTION_CANDIDATE** is an AIYE/authorial analytical candidate; "
            "**PROPOSED** is not admitted; **scientifically admitted: NOT PERFORMED**.", "",
        ])
        states = {item["study_id"]: item for item in report.get("study_analyses", ())}
        for narrative in narratives:
            state = states[narrative["study_id"]]
            lines.extend([
                f"### Study `{narrative['study_id']}`", "",
                str(narrative["text"]), "",
                f"Local evidence state: **{state['local_state']}**. "
                f"MethodRun: **{state['method_execution_status']}**. "
                f"Scientific acceptance: **{state['scientific_acceptance']}**.", "",
                "#### Source-fixed strong claims", "",
            ])
            for claim in state["claims"]:
                address = claim["page_address"]
                number = (
                    f"; {claim['numerator']}/{claim['denominator']}"
                    if claim.get("numerator") is not None else ""
                )
                lines.append(
                    f"- `{claim['claim_id']}` — {claim['proposition']} "
                    f"[`{claim['source_id']}`, PDF page index `{address['pdf_page_index']}`, "
                    f"{claim['modality']}{number}; review `{claim['review_state']}`]"
                )
            lines.extend(["", "#### Preserved APORIA", ""])
            if state["contradictions"]:
                for conflict in state["contradictions"]:
                    lines.append(
                        f"- **{conflict['contradiction_id']}** ({conflict['contradiction_type']}): "
                        f"{conflict['interpretation']} Status: `{conflict['status']}`; "
                        f"claims: {', '.join(conflict['claim_ids'])}."
                    )
            else:
                lines.append("- None available in the selected source regime; this is local UNKNOWN, not absence.")
            lines.extend(["", "#### Local unknowns", ""])
            lines.extend(f"- {value}" for value in state["unknowns"])
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- {item}" for item in report["limitations"])
        if not report["limitations"]:
            lines.append("- Scientific review and publication acceptance remain open.")
        lines.extend(["", "Scientific acceptance: **NOT PERFORMED**.",
                      "Customer release: **BLOCKED**.", ""])
        return "\n".join(lines)
    lines.extend(["", "## Findings", "", "```json",
                  json.dumps({k: v for k, v in report.items() if k not in {
                      "source_references", "scientific_acceptance", "customer_release"
                  }}, ensure_ascii=False, sort_keys=True, indent=2, default=list),
                  "```", "", "## Limits", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    if not report["limitations"]:
        lines.append("- No additional engineering limitation recorded; scientific review remains open.")
    lines.extend(["", "Scientific acceptance: **NOT PERFORMED**.",
                  "Customer release: **BLOCKED**.", ""])
    return "\n".join(lines)


def _html_index(reports: Mapping[str, Mapping[str, Any]], receipt: Mapping[str, Any]) -> str:
    rows = "".join(
        f'<li><a href="reports/{rid}.html">{rid}: {html.escape(r["purpose"])}</a> '
        f'— {html.escape(r["status"])}</li>' for rid, r in reports.items()
    )
    return (
        "<!doctype html><meta charset=utf-8><title>SESHAT product preview</title>"
        "<h1>SESHAT M13–M16 product preview</h1>"
        f"<p>Status: <strong>{html.escape(str(receipt['status']))}</strong>. "
        "Scientific acceptance not performed; customer release blocked.</p>"
        f"<ul>{rows}</ul><p><a href='product.json'>Structured JSON</a></p>"
    )


def write_product(
    output: Path, manifest: Mapping[str, Any], sources: list[dict[str, Any]],
    selections: Mapping[str, Mapping[str, Any]], reports: dict[str, dict[str, Any]],
    route: Mapping[str, Any], carpet: Mapping[str, Any],
    archive_census: Mapping[str, Any] | None,
    host_batches: Mapping[str, Any], analyses: Sequence[AuthorialStudyOracle], *, resume: bool,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    reports_dir = output / "reports"
    reports_dir.mkdir(exist_ok=True)
    ledger_path = output / "f09a_preview_ledger.json"
    old = _read_json(ledger_path) if resume and ledger_path.is_file() else {"items": {}}
    old_items = old.get("items") or {}
    items = {}
    executed: list[str] = []
    replayed: list[str] = []
    for report_id, report in reports.items():
        fingerprint = _digest({
            "report": report,
            "sources": {r["source_id"]: r["byte_sha256"] for r in report["source_references"]},
        })
        json_path = reports_dir / f"{report_id}.json"
        md_path = reports_dir / f"{report_id}.md"
        html_path = reports_dir / f"{report_id}.html"
        prior = old_items.get(report_id) or {}
        if resume and prior.get("input_fingerprint") == fingerprint and all(
            p.is_file() for p in (json_path, md_path, html_path)
        ):
            state = "REPLAYED_NO_MODEL_CALL"
            replayed.append(report_id)
        else:
            json_path.write_bytes(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                             indent=2, default=list).encode("utf-8"))
            markdown = _markdown(report)
            md_path.write_text(markdown, encoding="utf-8")
            html_path.write_text(
                "<!doctype html><meta charset=utf-8><pre>" + html.escape(markdown) + "</pre>",
                encoding="utf-8",
            )
            state = "DONE_" + report["status"]
            executed.append(report_id)
        items[report_id] = {
            "state": state, "input_fingerprint": fingerprint,
            "report_version": fingerprint,
            "relative_paths": [f"reports/{report_id}.{ext}" for ext in ("json", "md", "html")],
            "model_calls": 0,
        }
    prior_sources = old.get("source_pins") or {}
    current_sources = {x["source_id"]: x["byte_sha256"] for x in sources if not x["excluded"]}
    revised_sources = sorted(
        source_id for source_id, digest in current_sources.items()
        if source_id in prior_sources and prior_sources[source_id] != digest
    )
    current_analysis_pins = oracle_pins(analyses)
    prior_analysis_pins = old.get("study_analysis_pins") or {}
    revised_analysis_ids = sorted(
        study_id for study_id, digest in current_analysis_pins.items()
        if study_id in prior_analysis_pins and prior_analysis_pins[study_id] != digest
    )
    ledger = {
        "schema": "seshat.product-preview.f09a.v1", "product_id": manifest["product_id"],
        "source_pins": current_sources, "items": items, "executed_items": executed,
        "replayed_items": replayed, "revised_source_ids": revised_sources,
        "revised_analysis_ids": revised_analysis_ids,
        "selectively_invalidated_items": (
            executed if revised_sources or revised_analysis_ids else []
        ),
        "duplicate_model_calls": 0,
        "archive_census": archive_census,
        "archive_census_is_not_analysed_count": True,
        "study_analysis_pins": current_analysis_pins,
        "source_binding_status": (
            carpet.get("source_bound", {}).get("status")
            if analyses else "NOT_REQUESTED"
        ),
    }
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2),
                           encoding="utf-8")
    matrix = {
        "M13": (
            "WORKS" if carpet.get("source_bound", {}).get(
                "at_least_two_distinct_activations"
            ) else "PARTIAL"
        ),
        "M14": "WORKS",
        "M15": "WORKS" if len(reports) == 9 else "MISSING",
        "M16": "WORKS" if len(items) == 9 and {
            "sechenovka-like", "meteorology"
        } <= set(host_batches) else "PARTIAL",
        "real_owner_sources": "WORKS" if any(x["status"] == "WORKS" and not manifest.get("synthetic_fixture") for x in sources) else "PARTIAL_SYNTHETIC_OR_UNREADABLE",
        "external_SRC_D": "WORKS" if manifest.get("external_evidence") else "MISSING",
        "internal_SRC_C": "WORKS" if manifest.get("internal_evidence") else "MISSING",
    }
    receipt = {
        "schema": SCHEMA, "product_id": manifest["product_id"],
        "status": "WORKS_WITH_PARTIALS" if any(
            str(value).startswith(("PARTIAL", "MISSING")) for value in matrix.values()
        ) else "WORKS_UNREVIEWED",
        "generated_at": _utc_now(), "resume": resume, "matrix": matrix,
        "selector_memberships": selections, "source_intake": [
            {k: v for k, v in source.items() if k != "text"} for source in sources
        ],
        "route": route, "carpet": carpet, "f09a_ledger": "f09a_preview_ledger.json",
        "f09a_host_batches": host_batches,
        "scientific_acceptance": "NOT_PERFORMED", "customer_release": "BLOCKED",
        "study_analysis_pins": oracle_pins(analyses),
        "product_in_use": "verified_local_execution",
    }
    (output / "product.json").write_text(
        json.dumps({"receipt": receipt, "reports": reports}, ensure_ascii=False,
                   sort_keys=True, indent=2, default=list), encoding="utf-8"
    )
    (output / "index.html").write_text(_html_index(reports, receipt), encoding="utf-8")
    (output / "WORKS_PARTIAL_MISSING.json").write_text(
        json.dumps(matrix, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
    )
    return receipt


def run_preview(
    manifest_path: Path,
    output: Path,
    *,
    resume: bool = False,
    study_analysis_paths: Sequence[Path] = (),
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _read_json(manifest_path)
    validate_manifest(manifest)
    sources = ingest_sources(manifest, manifest_path.parent)
    selections = build_selections(manifest, sources)
    methods = load_method_outputs(manifest, manifest_path.parent)
    analyses = load_study_analyses(
        manifest, manifest_path.parent, sources, override_paths=study_analysis_paths
    )
    archive_census = load_archive_census(manifest, manifest_path.parent)
    reports = build_reports(manifest, sources, selections, methods, analyses)
    carpet = run_carpet(output, manifest, manifest_path.parent)
    carpet["source_bound"] = run_source_bound_carpet(
        output, sources, analyses, reports, resume=resume
    ) if analyses else {
        "status": "NOT_REQUESTED_NO_STUDY_ANALYSIS",
        "activation_witnesses": [],
        "at_least_two_distinct_activations": False,
    }
    host_batches = run_f09a_host_batches(output)
    route = build_operation_route(sources, methods, carpet)
    return write_product(
        output, manifest, sources, selections, reports, route, carpet,
        archive_census, host_batches, analyses, resume=resume
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SESHAT M13-M16 product preview")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--study-analysis", action="append", type=Path, default=[],
        help="owner-controlled AuthorialStudyOracle JSON (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        receipt = run_preview(
            args.manifest, args.output, resume=args.resume,
            study_analysis_paths=args.study_analysis,
        )
    except (ProductPreviewError, OSError, ValueError) as exc:
        print(f"PRODUCT_PREVIEW_ERROR: {exc}")
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
