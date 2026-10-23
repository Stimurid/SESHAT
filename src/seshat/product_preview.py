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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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



def _historical_i11_actions(outputs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Recover events from original I11 model states; no invented actions."""
    rows = []
    for item in outputs:
        payload = item.get("payload")
        if item.get("status") != "WORKS" or not isinstance(payload, dict):
            continue
        network = payload.get("typed_activity_network") or payload
        events = network.get("action_events", []) if isinstance(network, dict) else []
        for e in events:
            if not isinstance(e, dict):
                continue
            locators = []
            for src in e.get("source_addresses", []):
                if isinstance(src, dict):
                    page = src.get("page")
                    segment = str(src.get("quote") or "")
                    section = str(src.get("section") or "")
                    loc = f"p.{page}" if page is not None else "page UNKNOWN"
                    if section:
                        loc += f" / {section}"
                    if segment:
                        loc += f": {segment}"
                else:
                    loc = str(src)
                if loc.strip():
                    locators.append(loc)
            rows.append({
                "event_id": str(e.get("id") or e.get("event_id") or "UNKNOWN"),
                "layer": str(e.get("layer") or "UNKNOWN"),
                "relation_mode": str(e.get("relation_mode") or "UNKNOWN"),
                "verb": str(e.get("verb") or "UNKNOWN_ACTION"),
                "addresses": locators,
                "actor_ids": list(e.get("actor_ids") or []),
                "method_output_sha256": item.get("sha256"),
                "scientific_state": "ORIGINAL_I11_MODEL_EVENT_NOT_OWNER_ACCEPTED",
            })
    return rows


def _layer_census(actions: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(e["layer"]) for e in actions).items()))


def _short(value: object, max_length: int = 220) -> str:
    out = re.sub(r"\s+", " ", str(value or "")).strip()
    return out if len(out)<=max_length else out[:max_length-1]+"…"

def build_reports(
    manifest: Mapping[str, Any], sources: list[dict[str, Any]],
    selections: Mapping[str, Mapping[str, Any]], method_outputs: list[dict[str, Any]],
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
                    "historical_actions": _historical_i11_actions(method_by_study[study]),
                    "historical_layer_counts": _layer_census(
                        _historical_i11_actions(method_by_study[study])
                    ),
                }
                for study in studies
            ]
        elif report_id == "R02":
            base["object_method_evidence"] = [
                {"study_id": study,
                 "objects": sorted({v for x in chosen if x["study_id"] == study for v in x["objects"]}),
                 "methods": sorted({v for x in chosen if x["study_id"] == study for v in x["methods"]}),
                 "evidence": _source_refs(x for x in chosen if x["study_id"] == study),
                 "status": "SOURCE_ADDRESSED_UNREVIEWED",
                 "historical_actions": _historical_i11_actions(method_by_study[study])}
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
                "i11_action_layer_census": {
                    study: _layer_census(_historical_i11_actions(method_by_study[study]))
                    for study in studies
                },
                "generalization": "NOT_SUPPORTED_BEYOND_SELECTED_WORKS",
            }
            if len(studies) < 2:
                base["limitations"].append("CORPUS_TOO_SMALL_FOR_FIELD_PATTERN")
            elif len(studies) == 2:
                base["limitations"].append("TWO_STUDY_FIELD_ONLY_NOT_INSTITUTIONAL_COVERAGE")
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
            if chosen and all(x["source_kind"] == "ARTICLE" for x in chosen):
                base["opportunities"] = [
                    {"opportunity_id": "O1", "type": "unresolved_research_gap",
                     "proposal": "Study unresolved authorial actions or outcomes in this selected corpus, citing the unanswered source passage"},
                    {"opportunity_id": "O2", "type": "method_transfer",
                     "proposal": "Design a bounded method comparison on another compatible object; check participant and evidence-unit comparability"},
                    {"opportunity_id": "O3", "type": "outside_evidence_test",
                     "proposal": "Retrieve an independently sourced external analogue before novelty or transfer claims"},
                ]
            else:
                base["opportunities"] = [
                    {"opportunity_id": "O1", "type": "coverage", "proposal": "Obtain missing A/D counterpart for unpaired studies"},
                    {"opportunity_id": "O2", "type": "method", "proposal": "Review recurring object-method gaps with source-addressed evidence"},
                    {"opportunity_id": "O3", "type": "external", "proposal": "Build the missing external dossier before novelty claims"},
                ]
            base["opportunity_status"] = "CANDIDATES_REQUIRE_RESOURCE_AND_EXTERNAL_CHECK"
        elif report_id == "R08":
            base["learning_projection"] = {
                "cases": studies,
                "six_zones": [
                    {"zone": "Challenge Room",
                     "task": "Distinguish the studied-system problem from the research-production problem in an I11 action"},
                    {"zone": "Hypothesis Lab",
                     "task": "Propose and compare two possible object reconstructions with evidence that could discriminate them"},
                    {"zone": "Test Zone",
                     "task": "Challenge the mapping interview to observation to coding and locate methodological gaps"},
                    {"zone": "Prototype Factory",
                     "task": "Design a minimal evidence-addressed research activity, explicitly still proposed"},
                    {"zone": "Outside Environment",
                     "task": "Find comparable external claims before extending the selected findings to another context"},
                    {"zone": "Arena",
                     "task": "Debate incompatible action interpretations and record a human decision question"},
                ],
                "historical_i11_action_counts": {
                    study: len(_historical_i11_actions(method_by_study[study]))
                    for study in studies
                },
                "human_function": "learner performs a consequential interpretation",
                "curriculum_adoption": "NOT_AUTHORIZED",
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
            if supplied is None and method_id == "I11":
                supplied = methods.get((study, "I11_ACTIVITY_NETWORK"))
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
    return {
        "route": "source→typed operations→events→wave→activation→sediment→report",
        "typed_operations": operations,
        "cross_thread_activation_witnesses": carpet.get("activation_witnesses", []),
        "selective_source_delta_replay": carpet.get("selective_source_delta_replay"),
        "engine_status": carpet.get("status", "PARTIAL_NOT_RUN"),
        "selected_sources_causally_bound_to_engine_activations": False,
        "binding_status": "PARTIAL_SYNTHETIC_ENGINE_DEMONSTRATION",
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
    """Write a readable scientific preview; structured model traces live in JSON."""
    rid = str(report["report_id"])
    lines = [
        f"# {rid} — {report['purpose']}", "",
        f"Status: **{report['status']}**. Selected subset: {report['selector_id']}.", "",
        "## Substance", "",
    ]

    def event_section(actions: list[dict[str, Any]], *, max_events: int = 60) -> None:
        if not actions:
            lines.extend(["No archived I11 action state has been admitted for this study.", ""])
            return
        counts = _layer_census(actions)
        count_text = ", ".join(f"{layer}: {count}" for layer,count in counts.items())
        lines.extend([
            f"The archived I11 method reconstruction contains {len(actions)} "
            "reported events across action layers (" + count_text + ").",
            "Each entry below retains its original action type and a short source "
            "locator. These are historical model interpretations; original "
            "model output has not been rewritten or independently accepted.",
            "",
        ])
        for event in actions[:max_events]:
            locators = "; ".join(_short(x, 180) for x in event["addresses"][:2])
            lines.append(
                f"- **{event['event_id']} / {event['layer']} / "
                f"{event['relation_mode']}**: {_short(event['verb'], 220)}."
                + (f" Source: {locators}." if locators else " Source address not observed.")
            )
        if len(actions)>max_events:
            lines.append(
                f"- {len(actions)-max_events} more events remain in the JSON "
                "report with their original source locators."
            )
        lines.append("")

    if rid == "R01":
        lines.extend([
            "The unit of analysis is a performed research activity. A publication "
            "byline, a studied hospital action, a reported research procedure, "
            "and a proposal for future collaboration represent different "
            "kinds of evidence and action.",
            "",
        ])
        for study in report.get("study_assemblies", []):
            lines.extend([
                f"### Study {study['study_id']}", "",
                "**Research object:** " + "; ".join(study["objects"]) + ".",
                "**Named research methods:** " + "; ".join(study["methods"]) + ".",
                "",
            ])
            event_section(study.get("historical_actions") or [])
            lines.extend([
                "Interpretive boundary: RP designates acts producing the "
                "research. SS designates activities of the studied system; "
                "BR is the connection between them. FT and PO roles do not "
                "prove who performed a particular empirical act. A suggested "
                "future course is PR, not a measured implementation IM.",
                "",
            ])
    elif rid == "R02":
        lines.extend([
            "This report relates a stated object to an empirical operation "
            "and its source locator. Cited text can support a report of an "
            "operation without proving every attribution or causal effect.",
            "",
        ])
        for study in report.get("object_method_evidence", []):
            lines.extend([
                f"### Study {study['study_id']}", "",
                "**Object:** " + "; ".join(study["objects"]) + ".",
                "**Method and recording apparatus:** " + "; ".join(study["methods"]) + ".",
                "",
            ])
            event_section(study.get("historical_actions") or [])
            lines.extend([
                "Uncertainties to retain: actual individual operators of "
                "unnamed procedures, limits of sampling, possible alternative "
                "analytical interpretations and evidence not actually collected.",
                "",
            ])
    elif rid == "R03":
        fm = report.get("field_map", {})
        lines.extend([
            f"**Perimeter:** {fm.get('study_count',0)} selected studies from "
            f"{fm.get('source_count',0)} source carriers. The selection does "
            "not stand for a university or institutional population.",
            "",
        ])
        for key, title in [
            ("objects", "Research objects"),
            ("methods", "Research-method configurations"),
            ("infrastructure", "Mentioned infrastructure and recording means"),
        ]:
            lines.extend([f"### {title}", ""])
            for label,count in (fm.get(key) or {}).items():
                lines.append(f"- {label}: {count} source(s) within this selection")
            lines.append("")
        lines.extend(["### Documented research-action layer counts", ""])
        for study,counts in (fm.get("i11_action_layer_census") or {}).items():
            lines.append(f"- {study}: " + ", ".join(f"{k}={v}" for k,v in counts.items()))
        lines.extend([
            "", "The observed methods and objects can be contrasted, "
            "but do not establish comparative treatment effects, dominant "
            "university research lines, or the absence of other approaches.", "",
        ])
    elif rid == "R04":
        lines.extend([
            "An atlas of declared objects, used or reported methods, and "
            "mentioned instruments or work settings. Whether the institution "
            "currently owns or can use a mentioned resource remains unknown.",
            "",
        ])
        for item in report.get("atlas_rows", []):
            lines.extend([
                f"### {item['study_id']}", "",
                "- Research object: " + "; ".join(item["objects"]),
                "- Method: " + "; ".join(item["methods"]),
                "- Means and setting: " + "; ".join(item["infrastructure"]),
                "- Current institutional capacity: UNKNOWN without SRC-C.", "",
            ])
    elif rid == "R05":
        lines.extend([
            "The seven kinds of external knowledge are separate dossiers. "
            "Missing material is marked explicitly and is not proof that "
            "no international analogue or method exists.",
            "",
        ])
        for item in report.get("dossiers", []):
            lines.append(f"- **{item['entity']}**: {item['status']}.")
            if item.get("evidence"):
                lines.append("  Available evidence: " + _short(
                    json.dumps(item["evidence"],ensure_ascii=False), 260
                ))
    elif rid == "R06":
        if report.get("comparisons"):
            for item in report["comparisons"]:
                lines.append(
                    f"- {item.get('local_entity')}: "
                    f"{item.get('claim')} ({item.get('external_status')})"
                )
        else:
            lines.extend([
                "No external observation and comparability test are currently "
                "available. A classification as novel, mainstream, outdated "
                "or transferable would be ungrounded.",
            ])
    elif rid == "R07":
        lines.extend([
            "These are different proposals for future investigation, "
            "not demonstrated outcomes or signed projects.", "",
        ])
        for item in report.get("opportunities", []):
            lines.append(
                f"- **{item['opportunity_id']} / {item['type']}**: "
                + item["proposal"] + "."
            )
    elif rid == "R08":
        lp = report.get("learning_projection",{})
        lines.extend([
            "A proposed educational adaptation of research-analysis cases. "
            "Learners compare accounts of the same evidence and decide how "
            "to proceed. No curriculum adoption or person-ranking is implied.", "",
        ])
        for zone in lp.get("six_zones", []):
            lines.append(f"- **{zone['zone']}**: {zone['task']}.")
    else:
        lines.extend([
            "These are possible institutional decisions, with neither "
            "delegated authority nor budgetary approval asserted.", "",
        ])
        for item in report.get("decision_options", []):
            lines.append(f"- **{item['option_id']}**: {item['option']} (human-only).")
        lines.extend(["", "Institutional capacity and actual decision: UNKNOWN."])

    lines.extend(["", "## Source drillback", ""])
    for ref in report["source_references"]:
        lines.append(
            f"- {ref['study_id']} / {ref['source_id']}; "
            f"version {ref['version']}, SHA-256 {ref['byte_sha256'] or 'UNKNOWN'}; "
            f"operator-local file {ref['drillback']}"
        )
    lines.extend(["", "## Open limitations", ""])
    if report.get("limitations"):
        lines.extend(f"- {item}" for item in report["limitations"])
    else:
        lines.append("- The interpretations have not received owner scientific acceptance.")
    lines.extend([
        "", "**Scientific acceptance:** NOT PERFORMED. "
        "**Customer release:** BLOCKED.",
        "The linked JSON retains the full typed method-event data, "
        "selection and digest details.", "",
    ])
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
        + (
            "<p><a href='owner_source_carpet/owner-source-baseline/carpet.html'>"
            "Source-bound Carpet (actual owner-selected documents)</a></p>"
            "<p><a href='owner_source_carpet/owner-source-counterfactual-delta/carpet.html'>"
            "Selective-replay test (hypothetical source revision)</a></p>"
            if receipt["route"].get("selected_sources_causally_bound_to_engine_activations")
            and receipt["route"].get("counterfactual_delta")
            else ""
        )
    )


def write_product(
    output: Path, manifest: Mapping[str, Any], sources: list[dict[str, Any]],
    selections: Mapping[str, Mapping[str, Any]], reports: dict[str, dict[str, Any]],
    route: Mapping[str, Any], carpet: Mapping[str, Any],
    archive_census: Mapping[str, Any] | None,
    host_batches: Mapping[str, Any], *, resume: bool,
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
            "relative_paths": [f"reports/{report_id}.{ext}" for ext in ("json", "md", "html")],
            "model_calls": 0,
        }
    prior_sources = old.get("source_pins") or {}
    current_sources = {x["source_id"]: x["byte_sha256"] for x in sources if not x["excluded"]}
    revised_sources = sorted(
        source_id for source_id, digest in current_sources.items()
        if source_id in prior_sources and prior_sources[source_id] != digest
    )
    ledger = {
        "schema": "seshat.product-preview.f09a.v1", "product_id": manifest["product_id"],
        "source_pins": current_sources, "items": items, "executed_items": executed,
        "replayed_items": replayed, "revised_source_ids": revised_sources,
        "selectively_invalidated_items": executed if revised_sources else [],
        "duplicate_model_calls": 0,
        "archive_census": archive_census,
        "archive_census_is_not_analysed_count": True,
    }
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2),
                           encoding="utf-8")
    matrix = {
        # Existing M5/M6 witnesses are genuine engine records, but this slice
        # does not pretend the owner-selected files caused those synthetic
        # fixture activations. A real source-bound Carpet adapter remains M13.
        "M13": (
            "WORKS_SOURCE_BOUND_ENGINE_I11_INDEX_NOT_FULL_CARTRIDGE"
            if route.get("selected_sources_causally_bound_to_engine_activations")
            else "PARTIAL_NO_SOURCE_BOUND_ENGINE"
        ),
        "M13_authorial_method_coverage": "PARTIAL_I08_I09_I12_C09_NATIVE",
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
        "route": route, "carpet": carpet,
        "source_bound_carpet": route.get("source_bound_carpet_receipt"),
        "f09a_ledger": "f09a_preview_ledger.json",
        "f09a_host_batches": host_batches,
        "scientific_acceptance": "NOT_PERFORMED", "customer_release": "BLOCKED",
        "product_in_use": "not_observed",
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


def run_preview(manifest_path: Path, output: Path, *, resume: bool = False) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _read_json(manifest_path)
    validate_manifest(manifest)
    sources = ingest_sources(manifest, manifest_path.parent)
    selections = build_selections(manifest, sources)
    methods = load_method_outputs(manifest, manifest_path.parent)
    archive_census = load_archive_census(manifest, manifest_path.parent)
    reports = build_reports(manifest, sources, selections, methods)
    carpet = run_carpet(output, manifest, manifest_path.parent)
    from seshat.source_bound_carpet import run_source_bound_carpet
    selected = selections[str(manifest.get("default_selector")
                              or next(iter(selections)))]["members"]
    source_bound = run_source_bound_carpet(
        output / "owner_source_carpet", sources, methods, selected
    )
    host_batches = run_f09a_host_batches(output)
    route = build_operation_route(sources, methods, carpet)
    route["selected_sources_causally_bound_to_engine_activations"] = (
        source_bound["selected_sources_causally_bound_to_engine_activations"]
    )
    route["binding_status"] = source_bound["status"]
    route["source_bound_activation_witnesses"] = source_bound["activation_witnesses"]
    route["source_bound_carpet_receipt"] = "owner_source_carpet/receipt.json"
    route["counterfactual_delta"] = source_bound.get("counterfactual_delta")
    route["model_provider_calls_source_bound_carpet"] = source_bound.get(
        "model_provider_calls", 0
    )
    return write_product(
        output, manifest, sources, selections, reports, route, carpet,
        archive_census, host_batches, resume=resume
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SESHAT M13-M16 product preview")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = run_preview(args.manifest, args.output, resume=args.resume)
    except (ProductPreviewError, OSError, ValueError) as exc:
        print(f"PRODUCT_PREVIEW_ERROR: {exc}")
        return 2
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
