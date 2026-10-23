"""Typed, source-bound import for owner-controlled authorial study overlays.

The overlay is an analytical candidate, not a model run and not scientific
acceptance.  It may point at private sources, but only hashes, addresses and
typed candidate state are returned to the product receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator


ORACLE_SCHEMA = "seshat.m17.owner_authorial_candidate.v0.1"
QUESTION_IDS = tuple(f"5.{number}" for number in range(1, 15))


class AuthorialOracleError(ValueError):
    """The private overlay is malformed or is not bound to the loaded sources."""


class SourcePageAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    pdf_page_index: int | None = Field(default=None, ge=0)
    printed_page: str | None = None
    location: str = ""
    address_grade: str = "SOURCE_REPORTED_PAGE"


class OracleCarrier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(A|D|ARTICLE|EXTERNAL|INTERNAL)$")
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: str | None = None


class ResearchAnswerCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    candidate_answer: str = Field(min_length=1)
    assertion_modality: str = "E2_RECONSTRUCTION_CANDIDATE"
    role: str = "AUTHORIAL_ANALYTIC_CANDIDATE"
    review_state: str = "SOURCE_DIRECT_AUTHORIAL_DRAFT_NOT_MODEL_RUN"
    source_addresses: tuple[SourcePageAddress, ...] = ()
    requires_source_ids: tuple[str, ...] = ()
    address_state: str = "PARTIAL_SOURCE_ADDRESS"


class ClaimEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1)
    research_object_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    page_address: SourcePageAddress
    variable: str = Field(min_length=1)
    proposition: str = Field(min_length=1)
    numerator: int | float | None = None
    denominator: int | float | None = None
    modality: str = Field(min_length=1)
    role: str = "SOURCE_REPORTED_CLAIM"
    review_state: str = "UNREVIEWED_SOURCE_FIXATION"


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contradiction_id: str = Field(min_length=1)
    research_object_id: str = Field(min_length=1)
    contradiction_type: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = Field(min_length=2)
    status: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    desired_reports: dict[str, str] = Field(default_factory=dict)
    modality: str = "E2_ANALYTIC_INTERPRETATION"
    role: str = "APORIA"
    review_state: str = "UNRESOLVED_HUMAN_REVIEW_REQUIRED"


class AuthorialStudyOracle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: str
    oracle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    study_id: str = Field(min_length=1)
    research_object_id: str = Field(min_length=1)
    research_object_type: str = "STUDY"
    source_state: str
    method_execution_status: str
    scientific_acceptance: str
    avoid_claim: str
    carriers: tuple[OracleCarrier, ...]
    answers: tuple[ResearchAnswerCandidate, ...]
    claims: tuple[ClaimEvidence, ...]
    contradictions: tuple[Contradiction, ...]
    authored_reports: dict[str, str]
    nonnegotiable_test_rules: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> "AuthorialStudyOracle":
        if self.schema_id != ORACLE_SCHEMA:
            raise ValueError("AUTHORIAL_ORACLE_SCHEMA_UNSUPPORTED")
        if tuple(answer.question_id for answer in self.answers) != QUESTION_IDS:
            raise ValueError("AUTHORIAL_ORACLE_REQUIRES_ORDERED_14_QUESTIONS")
        carrier_ids = {carrier.source_id for carrier in self.carriers}
        claim_ids = {claim.claim_id for claim in self.claims}
        if len(claim_ids) != len(self.claims):
            raise ValueError("DUPLICATE_CLAIM_ID")
        if any(claim.source_id not in carrier_ids for claim in self.claims):
            raise ValueError("CLAIM_SOURCE_NOT_IN_ORACLE_CARRIERS")
        if any(
            claim.page_address.pdf_page_index is None
            and claim.page_address.printed_page is None
            for claim in self.claims
        ):
            raise ValueError("CLAIM_SOURCE_PAGE_ADDRESS_REQUIRED")
        if any(not set(item.claim_ids) <= claim_ids for item in self.contradictions):
            raise ValueError("CONTRADICTION_REFERENCES_UNKNOWN_CLAIM")
        if self.method_execution_status != "NOT_MODEL_RUN":
            raise ValueError("AUTHORIAL_ORACLE_MUST_NOT_IMPLY_MODEL_RUN")
        if self.scientific_acceptance == "ACCEPTED":
            raise ValueError("AUTHORIAL_ORACLE_CANNOT_SELF_ACCEPT")
        return self


_PAGE_RE = re.compile(
    r"(?P<kind>[AD])(?:\s+PDF)?\s+p(?:p)?\.\s*(?P<first>\d+)(?:\s*[–-]\s*(?P<last>\d+))?",
    re.IGNORECASE,
)


def _answer_addresses(text: str, carriers: Mapping[str, OracleCarrier]) -> tuple[SourcePageAddress, ...]:
    by_kind = {carrier.kind: carrier.source_id for carrier in carriers.values()}
    addresses: list[SourcePageAddress] = []
    seen: set[tuple[str, int]] = set()
    for match in _PAGE_RE.finditer(text):
        source_id = by_kind.get(match.group("kind").upper())
        if source_id is None:
            continue
        first = int(match.group("first"))
        last = int(match.group("last") or first)
        for printed in range(first, last + 1):
            # Printed references are preserved literally.  No PDF-index offset
            # is invented where the oracle did not provide one.
            key = (source_id, printed)
            if key not in seen:
                addresses.append(SourcePageAddress(
                    source_id=source_id,
                    printed_page=str(printed),
                    location=match.group(0),
                    address_grade="PRINTED_PAGE_FROM_AUTHORIAL_CANDIDATE",
                ))
                seen.add(key)
    return tuple(addresses)


def _source_map(source_records: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(record["source_id"]): record for record in source_records}


def _load_required_source_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw = item.get("required_carrier_ids")
    if raw is None:
        raw = item.get("requires_source_ids")
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise AuthorialOracleError("AUTHORIAL_ORACLE_REQUIRED_CARRIER_IDS_INVALID")
    return tuple(str(value) for value in raw if str(value))


def load_authorial_study_oracle(
    path: Path,
    source_records: Sequence[Mapping[str, Any]],
    *,
    expected_sha256: str | None = None,
) -> AuthorialStudyOracle:
    """Load and validate an owner-controlled overlay against actual source bytes."""

    try:
        raw = Path(path).read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorialOracleError(f"AUTHORIAL_ORACLE_UNREADABLE: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuthorialOracleError("AUTHORIAL_ORACLE_OBJECT_REQUIRED")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and digest != expected_sha256.casefold():
        raise AuthorialOracleError("AUTHORIAL_ORACLE_SHA256_MISMATCH")

    records = _source_map(source_records)
    raw_carriers = tuple(
        OracleCarrier.model_validate(item) for item in payload.get("carriers", ())
    )
    study_id = str(payload.get("study_id") or "")
    carriers: list[OracleCarrier] = []
    for carrier in raw_carriers:
        record = records.get(carrier.source_id)
        if record is None or record.get("study_id") != study_id:
            raise AuthorialOracleError("AUTHORIAL_ORACLE_SOURCE_CARRIER_NOT_LOADED")
        if record.get("status") != "WORKS" or record.get("byte_sha256") != carrier.sha256:
            raise AuthorialOracleError("AUTHORIAL_ORACLE_SOURCE_BINDING_MISMATCH")
        if record.get("source_kind") != carrier.kind:
            raise AuthorialOracleError("AUTHORIAL_ORACLE_SOURCE_KIND_MISMATCH")
        carriers.append(carrier.model_copy(update={"version": str(record.get("version") or "")}))
    carrier_tuple = tuple(carriers)
    carrier_map = {carrier.source_id: carrier for carrier in carrier_tuple}

    answers = []
    for item in payload.get("questions", ()):
        answer = str(item.get("candidate_answer") or "")
        addresses = _answer_addresses(answer, carrier_map)
        required = _load_required_source_ids(item)
        if any(source_id not in carrier_map for source_id in required):
            raise AuthorialOracleError("AUTHORIAL_ORACLE_REQUIRED_CARRIER_UNKNOWN")
        answers.append(ResearchAnswerCandidate(
            question_id=str(item.get("question_id") or ""),
            question=str(item.get("question") or ""),
            candidate_answer=answer,
            assertion_modality=str(item.get("assertion_modality") or "E2_RECONSTRUCTION_CANDIDATE"),
            review_state=str(item.get("review_status") or "SOURCE_DIRECT_AUTHORIAL_DRAFT_NOT_MODEL_RUN"),
            source_addresses=addresses,
            requires_source_ids=required,
            address_state="SOURCE_ADDRESSED" if addresses else "PARTIAL_SOURCE_ADDRESS",
        ))

    claims = []
    for item in payload.get("asserted_source_claims", ()):
        source_id = str(item.get("carrier") or "")
        claims.append(ClaimEvidence(
            claim_id=str(item.get("claim_id") or ""),
            research_object_id=study_id,
            source_id=source_id,
            page_address=SourcePageAddress(
                source_id=source_id,
                pdf_page_index=item.get("pdf_page_index"),
                location=str(item.get("location") or ""),
                address_grade=str(item.get("address_grade") or "EXACT_PDF_PAGE_INDEX"),
            ),
            variable=str(item.get("metric") or "UNSPECIFIED_VARIABLE"),
            proposition=str(item.get("asserted_proposition") or ""),
            numerator=item.get("numerator"),
            denominator=item.get("denominator"),
            modality=str(item.get("source_modality") or "E1_SOURCE_FIXATION"),
        ))
    contradictions = tuple(Contradiction(
        contradiction_id=str(item.get("conflict_id") or ""),
        research_object_id=study_id,
        contradiction_type=str(item.get("type") or ""),
        claim_ids=tuple(str(value) for value in item.get("claim_ids", ())),
        status=str(item.get("status") or ""),
        interpretation=str(item.get("interpretation") or ""),
        desired_reports={
            key.removeprefix("desired_"): str(value)
            for key, value in item.items() if key.startswith("desired_")
        },
    ) for item in payload.get("scientific_conflicts", ()))
    try:
        return AuthorialStudyOracle(
            schema_id=str(payload.get("schema") or ""),
            oracle_sha256=digest,
            study_id=study_id,
            research_object_id=study_id,
            source_state=str(payload.get("source_state") or "UNKNOWN"),
            method_execution_status=str(payload.get("method_execution_status") or ""),
            scientific_acceptance=str(payload.get("scientific_acceptance") or ""),
            avoid_claim=str(payload.get("avoid_claim") or ""),
            carriers=carrier_tuple,
            answers=tuple(answers),
            claims=tuple(claims),
            contradictions=contradictions,
            authored_reports={
                str(key): str(value)
                for key, value in (payload.get("authored_prototype_reports") or {}).items()
            },
            nonnegotiable_test_rules=tuple(
                str(value) for value in payload.get("nonnegotiable_test_rules", ())
            ),
        )
    except ValueError as exc:
        raise AuthorialOracleError(f"AUTHORIAL_ORACLE_INVALID: {exc}") from exc


def load_study_analyses(
    manifest: Mapping[str, Any],
    base: Path,
    source_records: Sequence[Mapping[str, Any]],
    *,
    override_paths: Sequence[Path] = (),
) -> list[AuthorialStudyOracle]:
    """Load optional manifest ``study_analyses`` plus CLI-supplied private paths."""

    specs: list[dict[str, Any]] = []
    for item in manifest.get("study_analyses", ()):
        if not isinstance(item, Mapping):
            raise AuthorialOracleError("STUDY_ANALYSIS_REFERENCE_OBJECT_REQUIRED")
        specs.append(dict(item))
    specs.extend({"path": str(path)} for path in override_paths)
    analyses: list[AuthorialStudyOracle] = []
    seen: set[str] = set()
    for spec in specs:
        path = Path(str(spec.get("path") or ""))
        if not path.is_absolute():
            path = base / path
        analysis = load_authorial_study_oracle(
            path, source_records, expected_sha256=spec.get("sha256")
        )
        if analysis.study_id in seen:
            raise AuthorialOracleError("DUPLICATE_STUDY_ANALYSIS")
        if spec.get("study_id") and spec["study_id"] != analysis.study_id:
            raise AuthorialOracleError("STUDY_ANALYSIS_ID_MISMATCH")
        seen.add(analysis.study_id)
        analyses.append(analysis)
    return analyses


def _answer_allowed(
    answer: ResearchAnswerCandidate,
    selected_ids: set[str],
) -> bool:
    required = set(answer.requires_source_ids)
    if not required:
        return False
    return required <= selected_ids


def analysis_view(
    analysis: AuthorialStudyOracle,
    selected_source_ids: Sequence[str],
    report_id: str,
) -> dict[str, Any] | None:
    """Project one overlay into a source-selector-scoped report view."""

    selected = set(selected_source_ids) & {carrier.source_id for carrier in analysis.carriers}
    if not selected:
        return None
    claims = [claim for claim in analysis.claims if claim.source_id in selected]
    claim_ids = {claim.claim_id for claim in claims}
    contradictions = [
        item for item in analysis.contradictions if set(item.claim_ids) <= claim_ids
    ]
    allowed: list[ResearchAnswerCandidate] = []
    omitted: list[ResearchAnswerCandidate] = []
    for answer in analysis.answers:
        if _answer_allowed(answer, selected):
            allowed.append(answer)
        else:
            omitted.append(answer)
    all_carriers = selected == {carrier.source_id for carrier in analysis.carriers}
    authored = (
        analysis.authored_reports.get(report_id)
        if all_carriers and not omitted else None
    )
    if authored:
        narrative = authored
        narrative_origin = "OWNER_AUTHORIAL_PROTOTYPE_SOURCE_BOUND"
    else:
        paragraphs = [
            "Это рабочая источниково-связанная реконструкция, а не независимое "
            "научное принятие и не результат нового ModelRun."
        ]
        paragraphs.extend(
            f"{answer.question} {answer.candidate_answer} "
            f"[{answer.assertion_modality}; {answer.address_state}]"
            for answer in allowed
        )
        narrative = "\n\n".join(paragraphs)
        narrative_origin = "SELECTOR_SCOPED_AUTHORIAL_CANDIDATES"
    unknowns = [
        "independent scientific acceptance",
        "unaddressed or excluded carrier assertions",
    ]
    if omitted:
        unknowns.append(
            f"{len(omitted)} curated answers omitted because required_carrier_ids "
            "are not a subset of the selected sources "
            "(PARTIAL/UNKNOWN; no lexical provenance guess)"
        )
    state = {
        "schema": "seshat.m17.study-evidence-state.v0.1",
        "study_id": analysis.study_id,
        "research_object": {
            "research_object_id": analysis.research_object_id,
            "object_type": analysis.research_object_type,
            "source_carrier_ids": sorted(selected),
        },
        "source_bindings": [
            carrier.model_dump(mode="json")
            for carrier in analysis.carriers if carrier.source_id in selected
        ],
        "method_execution_status": analysis.method_execution_status,
        "scientific_acceptance": analysis.scientific_acceptance,
        "answers": [answer.model_dump(mode="json") for answer in allowed],
        "omitted_answer_count": len(omitted),
        "omitted_question_ids": [answer.question_id for answer in omitted],
        "answer_scope_rule": "REQUIRED_CARRIER_IDS_SUBSET",
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "contradictions": [item.model_dump(mode="json") for item in contradictions],
        "local_state": (
            "PARTIAL"
            if len(selected) < len(analysis.carriers) or omitted
            else "WORKING_UNREVIEWED"
        ),
        "unknowns": unknowns,
    }
    projection_sha = hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    state["analysis_projection_sha256"] = projection_sha
    return {
        "narrative": narrative,
        "narrative_origin": narrative_origin,
        "evidence_state": state,
        "view_fingerprint": projection_sha,
    }


def oracle_pins(analyses: Sequence[AuthorialStudyOracle]) -> dict[str, str]:
    return {analysis.study_id: analysis.oracle_sha256 for analysis in analyses}
