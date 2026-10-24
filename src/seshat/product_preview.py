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
from seshat.m17_source_carpet import run_source_bound_carpet as run_authorial_carpet

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


_PAGE_BANNER_RE = re.compile(r"===\s*PAGE\s+\d+\s*===", re.IGNORECASE)


def _pdf_body_has_text(text: str) -> bool:
    """True when extracted PDF text has body content, not only page banners."""

    return bool(_PAGE_BANNER_RE.sub(" ", text).strip())


def _format_pdf_pages(page_texts: Iterable[str]) -> tuple[str, int]:
    pages = [
        f"\n=== PAGE {number} ===\n{text}"
        for number, text in enumerate(page_texts, 1)
    ]
    return "".join(pages), len(pages)


def _extract_pdf_pypdf(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return _format_pdf_pages(page.extract_text() or "" for page in reader.pages)


def _import_optional_pymupdf() -> Any:
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
            return pymupdf
        except ImportError as exc:
            raise ProductPreviewError("PDF_FALLBACK_UNAVAILABLE") from exc


def _extract_pdf_pymupdf(path: Path) -> tuple[str, int]:
    pymupdf = _import_optional_pymupdf()
    doc = pymupdf.open(path)
    try:
        return _format_pdf_pages(page.get_text() or "" for page in doc)
    finally:
        close = getattr(doc, "close", None)
        if close is not None:
            close()


def _extract_source(path: Path) -> tuple[str, int | None, str]:
    suffix = path.suffix.casefold()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8-sig"), None, "TEXT_EXTRACTED"
    if suffix == ".pdf":
        pypdf_error: Exception | None = None
        pypdf_text: str | None = None
        pypdf_pages: int | None = None
        try:
            pypdf_text, pypdf_pages = _extract_pdf_pypdf(path)
        except ImportError as exc:  # pragma: no cover - dependency is pinned by project
            raise ProductPreviewError("PDF_READER_UNAVAILABLE") from exc
        except Exception as exc:
            pypdf_error = exc
        if pypdf_text is not None and _pdf_body_has_text(pypdf_text):
            return pypdf_text, pypdf_pages, "TEXT_EXTRACTED"
        try:
            text, pages = _extract_pdf_pymupdf(path)
        except Exception:
            if pypdf_error is not None:
                raise pypdf_error
            if pypdf_text is not None:
                return pypdf_text, pypdf_pages, "PARTIAL_NO_EXTRACTED_TEXT"
            raise
        if _pdf_body_has_text(text):
            return text, pages, "TEXT_EXTRACTED"
        return text, pages, "PARTIAL_NO_EXTRACTED_TEXT"
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
            "defense_year": spec.get("defense_year"),
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
            record["byte_sha256"] = hashlib.sha256(raw).hexdigest()
            record["byte_length"] = len(raw)
            text, pages, extraction = _extract_source(path)
            record.update(
                status="WORKS" if extraction == "TEXT_EXTRACTED" else "PARTIAL",
                page_count=pages,
                text_extraction=extraction,
                text=text,
            )
            if extraction != "TEXT_EXTRACTED":
                record["limitations"].append("NO_EXTRACTED_TEXT")
        except Exception as exc:
            # pypdf raises several format-specific exceptions.  Intake remains
            # inspectable and partial; it never invents text or silently drops.
            # Byte identity is kept whenever the original file was readable.
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


_SOURCE_TEXT_NOISE_STOPWORDS = {
    "this", "that", "with", "from", "were", "have", "into", "using", "study",
    # PDF-extraction and bibliographic boilerplate: never scientific concepts.
    "page", "pages", "pmid", "issn", "isbn", "doi",
}


def _words(records: Iterable[Mapping[str, Any]]) -> Counter[str]:
    """Raw source-text lexical frequency. Not a scientific-concept extraction."""

    words: Counter[str] = Counter()
    for record in records:
        text = _PAGE_BANNER_RE.sub(" ", record.get("text", ""))
        for token in re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{3,}", text):
            folded = token.casefold()
            if folded not in _SOURCE_TEXT_NOISE_STOPWORDS:
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

def _study_year(items: Sequence[Mapping[str, Any]]) -> tuple[str, str | None, list[str]]:
    """Resolve one authoritative per-study year, preferring ``defense_year``.

    Never arbitrarily picks between disagreeing carriers: a disagreement is
    reported as a discrepancy, not silently resolved.  Returns
    ``(year_label, field_used, conflicting_values)``.
    """

    defense_values = sorted({
        str(x["defense_year"]) for x in items if x.get("defense_year") not in (None, "")
    })
    if len(defense_values) == 1:
        return defense_values[0], "defense_year", []
    if len(defense_values) > 1:
        return "CONFLICT", "defense_year", defense_values
    source_values = sorted({
        str(x["year"]) for x in items if x.get("year") not in (None, "")
    })
    if len(source_values) == 1:
        return source_values[0], "year", []
    if len(source_values) > 1:
        return "CONFLICT", "year", source_values
    return "UNKNOWN", None, []


def _per_study_field_metadata(
    chosen: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Per-study-deduped object/method/infrastructure/year counts.

    A tag or year present on both the A and D carrier of the same study must
    count once, not once per carrier; a study's upload-year metadata (per
    carrier) is tracked separately from its authoritative defense/study year.
    """

    by_study: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in chosen:
        by_study[item["study_id"]].append(item)

    objects: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    infrastructure: Counter[str] = Counter()
    years: Counter[str] = Counter()
    source_upload_years: Counter[str] = Counter()
    year_discrepancies: list[dict[str, Any]] = []

    for study_id, items in sorted(by_study.items()):
        for value in {v for x in items for v in x["objects"]}:
            objects[value] += 1
        for value in {v for x in items for v in x["methods"]}:
            methods[value] += 1
        for value in {v for x in items for v in x["infrastructure"]}:
            infrastructure[value] += 1
        for x in items:
            source_upload_years[str(x.get("year") or "UNKNOWN")] += 1
        year_label, field_used, conflicts = _study_year(items)
        years[year_label] += 1
        if conflicts:
            year_discrepancies.append({
                "study_id": study_id, "field": field_used,
                "conflicting_values": conflicts,
                "status": "DISCREPANCY_NOT_ARBITRARILY_RESOLVED",
            })
    return {
        "objects": objects, "methods": methods, "infrastructure": infrastructure,
        "years": years, "source_upload_years": source_upload_years,
        "year_discrepancies": year_discrepancies,
    }


SCIENCE_FIELD_SECTION_QUESTION_IDS: dict[str, str] = {
    "5.2": "problem",
    "5.3": "objects",
    "5.5": "performed_research_methods",
    "5.7": "recording",
    "5.8": "evidence",
    "5.9": "infrastructure",
    "5.11": "labor",
    "5.12": "result_form",
    "5.13": "unfinished",
}
SCIENCE_ATLAS_QUESTION_IDS: dict[str, str] = {
    "5.3": "objects",
    "5.5": "performed_research_methods",
    "5.9": "infrastructure",
}


def _science_field_sections(
    overlay_by_study: Mapping[str, AuthorialStudyOracle],
    selected_source_ids: Sequence[str],
    report_id: str,
    question_labels: Mapping[str, str],
) -> dict[str, Any]:
    """Project owner-authored study overlays into report-section comparisons.

    This reuses the existing M17 ``analysis_view`` selector-scoped overlay
    import; it never invents a cross-study comparison from title/keyword
    similarity, and it never claims comparability beyond NEEDS_REVIEW.
    """

    views: dict[str, dict[str, Any]] = {}
    for study_id, analysis in sorted(overlay_by_study.items()):
        view = analysis_view(analysis, selected_source_ids, report_id)
        if view is not None:
            views[study_id] = view
    if not views:
        return {
            "status": "NO_STUDY_OVERLAY_AVAILABLE",
            "sections": {}, "contributing_study_count": 0,
            "contributing_study_ids": [],
            "cross_study_comparability": "NOT_APPLICABLE_NO_OVERLAY",
            "comparability_rationale": (
                "No selected ResearchObject carries a source-bound scientific "
                "study-analysis overlay; this is metadata-only, not field science."
            ),
            "any_overlay": False,
        }
    sections: dict[str, list[dict[str, Any]]] = {
        f"{qid}_{label}": [] for qid, label in question_labels.items()
    }
    for study_id, view in sorted(views.items()):
        state = view["evidence_state"]
        answers_by_id = {a["question_id"]: a for a in state["answers"]}
        omitted = set(state["omitted_question_ids"])
        for qid, label in question_labels.items():
            key = f"{qid}_{label}"
            answer = answers_by_id.get(qid)
            if answer is not None:
                sections[key].append({
                    "study_id": study_id,
                    "question": answer["question"],
                    "candidate_answer": answer["candidate_answer"],
                    "assertion_modality": answer["assertion_modality"],
                    "address_state": answer["address_state"],
                    "source_addresses": answer["source_addresses"],
                    "carrier_selection_status": "INCLUDED_IN_SELECTED_CARRIERS",
                })
            elif qid in omitted:
                sections[key].append({
                    "study_id": study_id, "candidate_answer": None,
                    "carrier_selection_status": "OMITTED_REQUIRED_CARRIER_NOT_SELECTED",
                })
            else:
                sections[key].append({
                    "study_id": study_id, "candidate_answer": None,
                    "carrier_selection_status": "NOT_AUTHORED_FOR_THIS_QUESTION",
                })
    contributing = len(views)
    if contributing >= 2:
        status = "AGGREGATED_TWO_OR_MORE_STUDY_OVERLAYS"
        comparability = "NEEDS_REVIEW"
        rationale = (
            "Two or more distinct ResearchObjects contribute source-bound "
            "evidence to this bounded corpus subset. Shared or similar wording "
            "across studies is not evidence of shared method, object, or "
            "population; formal comparability requires explicit human "
            "scientific review."
        )
    else:
        status = "SINGLE_STUDY_OVERLAY_ONLY"
        comparability = "NOT_APPLICABLE_SINGLE_STUDY"
        rationale = (
            "Only one selected ResearchObject carries a scientific "
            "study-analysis overlay in this selection; no cross-study "
            "comparison is possible."
        )
    return {
        "status": status,
        "sections": sections,
        "contributing_study_count": contributing,
        "contributing_study_ids": sorted(views),
        "cross_study_comparability": comparability,
        "comparability_rationale": rationale,
        "any_overlay": True,
    }


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
            metadata = _per_study_field_metadata(chosen)
            overlay_by_study = {
                a.study_id: a for a in analyses if a.study_id in studies
            }
            science = _science_field_sections(
                overlay_by_study, [x["source_id"] for x in chosen], report_id,
                SCIENCE_FIELD_SECTION_QUESTION_IDS,
            )
            corpus_readable = bool(chosen) and all(x["status"] == "WORKS" for x in chosen)
            has_declared_tags = any(
                x["objects"] or x["methods"] or x["infrastructure"] for x in chosen
            )
            if not has_declared_tags and not science["any_overlay"]:
                tagging_status = "SCIENTIFIC_STUDY_ANALYSIS_MISSING"
            elif not science["any_overlay"]:
                tagging_status = "SCIENTIFIC_STUDY_ANALYSIS_METADATA_TAGS_ONLY"
            else:
                tagging_status = "SCIENTIFIC_STUDY_ANALYSIS_OVERLAY_PRESENT"
            base["field_map"] = {
                "scope": "SELECTED_CORPUS_FIELD_NOT_GLOBAL_FIELD",
                "study_count": len(studies), "source_count": len(chosen),
                "objects": metadata["objects"], "methods": metadata["methods"],
                "infrastructure": metadata["infrastructure"],
                "source_text_recurring_terms": _words(chosen).most_common(12),
                "source_text_recurring_terms_meaning": (
                    "RAW_SOURCE_TEXT_LEXICAL_FREQUENCY_NOT_SCIENTIFIC_CONCEPT"
                ),
                "years": metadata["years"],
                "source_upload_years": metadata["source_upload_years"],
                "year_discrepancies": metadata["year_discrepancies"],
                "source_corpus_status": (
                    "SOURCE_CORPUS_READABLE" if corpus_readable
                    else "SOURCE_CORPUS_NOT_FULLY_READABLE"
                ),
                "scientific_study_analysis_status": tagging_status,
                "science_overlay": science,
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
            if metadata["year_discrepancies"]:
                base["limitations"].append("YEAR_METADATA_DISCREPANCY_UNRESOLVED")
            if not corpus_readable:
                base["limitations"].append("SOURCE_CORPUS_NOT_FULLY_READABLE")
            if tagging_status == "SCIENTIFIC_STUDY_ANALYSIS_MISSING":
                base["limitations"].append("SCIENTIFIC_STUDY_ANALYSIS_MISSING")
        elif report_id == "R04":
            overlay_by_study = {
                a.study_id: a for a in analyses if a.study_id in studies
            }
            atlas_science = _science_field_sections(
                overlay_by_study, [x["source_id"] for x in chosen], report_id,
                SCIENCE_ATLAS_QUESTION_IDS,
            )
            resource_availability = (
                "RESOURCE_AVAILABLE_FROM_SRC_C" if manifest.get("internal_evidence")
                else "RESOURCE_AVAILABLE_UNKNOWN"
            )
            base["atlas_rows"] = [
                {"study_id": study,
                 "objects": sorted({v for x in chosen if x["study_id"] == study for v in x["objects"]}),
                 "methods": sorted({v for x in chosen if x["study_id"] == study for v in x["methods"]}),
                 "infrastructure": sorted({v for x in chosen if x["study_id"] == study for v in x["infrastructure"]}),
                 "actual_resource_availability": resource_availability,
                 "science_overlay_sections": {
                     key: [row for row in rows if row["study_id"] == study]
                     for key, rows in atlas_science["sections"].items()
                 } if study in overlay_by_study else {},
                 }
                for study in studies
            ]
            base["method_object_instrument_science_overlay"] = atlas_science
            has_declared_tags = any(
                x["objects"] or x["methods"] or x["infrastructure"] for x in chosen
            )
            corpus_readable = bool(chosen) and all(x["status"] == "WORKS" for x in chosen)
            base["source_corpus_status"] = (
                "SOURCE_CORPUS_READABLE" if corpus_readable
                else "SOURCE_CORPUS_NOT_FULLY_READABLE"
            )
            if not corpus_readable:
                base["limitations"].append("SOURCE_CORPUS_NOT_FULLY_READABLE")
            if not has_declared_tags and not atlas_science["any_overlay"]:
                base["scientific_study_analysis_status"] = "SCIENTIFIC_STUDY_ANALYSIS_MISSING"
                base["limitations"].append("SCIENTIFIC_STUDY_ANALYSIS_MISSING")
            elif not atlas_science["any_overlay"]:
                base["scientific_study_analysis_status"] = (
                    "SCIENTIFIC_STUDY_ANALYSIS_METADATA_TAGS_ONLY"
                )
            else:
                base["scientific_study_analysis_status"] = (
                    "SCIENTIFIC_STUDY_ANALYSIS_OVERLAY_PRESENT"
                )
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
        # Existing M5/M6 witnesses are genuine engine records, but this slice
        # does not pretend the owner-selected files caused those synthetic
        # fixture activations. A real source-bound Carpet adapter remains M13.
        "M13": (
            "WORKS_SOURCE_BOUND_ENGINE_I11_INDEX_NOT_FULL_CARTRIDGE"
            if route.get("selected_sources_causally_bound_to_engine_activations")
            else "PARTIAL_NO_SOURCE_BOUND_ENGINE"
        ),
        "M13_authorial_method_coverage": "PARTIAL_I08_I09_I12_C09_NATIVE",
        "M17_source_science": (
            "WORKS_SOURCE_BOUND_AUTHORIAL_CANDIDATE_ENGINE"
            if carpet.get("source_bound", {}).get("at_least_two_distinct_activations")
            else "PARTIAL_NO_AUTHORIAL_OVERLAY_ENGINE"
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
        "route": route, "carpet": carpet,
        "source_bound_carpet": route.get("source_bound_carpet_receipt"),
        "f09a_ledger": "f09a_preview_ledger.json",
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
    from seshat.source_bound_carpet import (
        run_source_bound_carpet as run_original_i11_carpet,
    )
    selected = selections[str(manifest.get("default_selector")
                              or next(iter(selections)))]["members"]
    source_bound = run_original_i11_carpet(
        output / "owner_source_carpet", sources, methods, selected
    )

    carpet["source_bound"] = run_authorial_carpet(
        output, sources, analyses, reports, resume=resume
    ) if analyses else {
        "status": "NOT_REQUESTED_NO_STUDY_ANALYSIS",
        "activation_witnesses": [],
        "at_least_two_distinct_activations": False,
    }
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
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
