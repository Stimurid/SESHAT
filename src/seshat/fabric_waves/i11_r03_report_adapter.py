"""Private I11 R03 v2 -> ordinary F08 R03 ReportProjection adapter.

The adapter composes with an already authorized metadata projection.  It does
not perform source admission, scientific review, owner acceptance or customer
release.  Serialized I11 data remains owner-private evidence supplied by the
host; validation here only prevents malformed or authority-promoting data from
being projected into the normal F08 consumer.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from seshat.corpus import FrozenModel, _digest
from seshat.fabric_waves.i11_activity_network import AUTHORIAL_I11_SHA256
from seshat.fabric_waves.i11_two_real_r03 import VerifiedTwoRunAdmission, _GATE_ISSUER
from seshat.reports import (
    Claim,
    EvidenceRef,
    ReportBlock,
    ReportProjection,
    ReportSection,
    canonical_bytes,
    render_html,
)


class I11R03ReportAdapterError(ValueError):
    """The private projection cannot safely be exposed through F08."""


class I11R03Evidence(FrozenModel):
    work_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^jx-.+")
    source_pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_page_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_id: str = Field(min_length=1)
    layer: Literal["RP", "SS", "FT", "PO", "BR", "IM", "PR"]
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_verification: Literal["VERIFIED_EXACT", "NORMALIZED_ONLY", "NOT_VERIFIED"]


class I11R03CandidateClaim(FrozenModel):
    kind: Literal[
        "COMMON_OPERATION",
        "MATERIAL_DIFFERENCE",
        "INCOMPARABLE",
        "UNKNOWN",
        "AUTHORIAL_HYPOTHESIS",
    ]
    statement: str = Field(min_length=1)
    evidence: tuple[I11R03Evidence, ...] = Field(min_length=2, max_length=2)
    status: Literal[
        "SOURCE_ADDRESSED_REVIEW_PENDING",
        "EVIDENCE_VERIFICATION_REVIEW_PENDING",
    ]
    limits: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_sources_and_exact_excerpt_hashes(self):
        if len({item.source_pdf_sha256 for item in self.evidence}) != 2:
            raise ValueError("I11_R03_COMPARISON_REQUIRES_TWO_SOURCE_PINS")
        for item in self.evidence:
            actual = hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
            if actual != item.excerpt_sha256:
                raise ValueError("I11_R03_EXCERPT_DIGEST_MISMATCH")
        return self


class I11R03V2Projection(FrozenModel):
    schema: Literal["seshat.i11.two_real_run_r03.v2"]
    report_id: Literal["R03"]
    status: Literal["UNVERIFIED_INPUTS", "VERIFIED_SOURCE_ADMISSION_REVIEW_PENDING"]
    actual_real_model_runs: Literal[0, 2]
    candidate_jobs: tuple[str | None, str | None] | None = None
    jobs: tuple[str, str] | None = None
    method_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    comparison_claims: tuple[I11R03CandidateClaim, ...]
    admission_status: Literal[
        "UNVERIFIED_CALLER_ASSERTIONS", "VERIFIED_REAL_TWO_RUN_SOURCE_ADMISSION"
    ]
    admission_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    run_manifest_digests: tuple[str, str] | None = None
    event_ledger_digests: tuple[str, str] | None = None
    terminal_receipt_digests: tuple[str, str] | None = None
    original_sources_only: bool | None = None
    source_evidence_status: Literal[
        "BYTE_AND_PAGE_EXCERPT_VERIFIED_WITH_REVIEW_PENDING"
    ] | None = None
    sampling_rule: Literal[
        "TWO_OWNER_SELECTED_ORIGINAL_I11_RUNS_NOT_A_POPULATION_SAMPLE"
    ] | None = None
    coverage_status: Literal["BOUNDED_TWO_WORK_COMPARISON"] | None = None
    implementation_missingness: dict[str, Any] | None = None
    product_wiring: Literal["NOT_PRODUCT_WIRED"]
    independent_science_review: Literal["PENDING"]
    scientific_acceptance: Literal["NOT_PERFORMED"]
    owner_acceptance: Literal["NOT_PERFORMED"]
    customer_release: Literal["BLOCKED"]
    provenance: Literal["SELF_OBSERVED_UNATTESTED"]
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def status_shape_and_digest(self):
        payload = self.model_dump(mode="json", exclude={"projection_sha256"}, exclude_unset=True)
        if _digest(payload) != self.projection_sha256:
            raise ValueError("I11_R03_PROJECTION_DIGEST_MISMATCH")
        if self.status == "UNVERIFIED_INPUTS":
            if (
                self.actual_real_model_runs != 0
                or self.admission_status != "UNVERIFIED_CALLER_ASSERTIONS"
                or self.comparison_claims
                or self.jobs is not None
                or self.admission_digest is not None
            ):
                raise ValueError("I11_R03_UNVERIFIED_SHAPE_INVALID")
        elif (
            self.actual_real_model_runs != 2
            or self.admission_status != "VERIFIED_REAL_TWO_RUN_SOURCE_ADMISSION"
            or self.jobs is None
            or len(set(self.jobs)) != 2
            or not self.comparison_claims
            or self.admission_digest is None
            or self.run_manifest_digests is None
            or self.event_ledger_digests is None
            or self.terminal_receipt_digests is None
            or self.original_sources_only is not True
            or self.source_evidence_status
            != "BYTE_AND_PAGE_EXCERPT_VERIFIED_WITH_REVIEW_PENDING"
            or self.sampling_rule
            != "TWO_OWNER_SELECTED_ORIGINAL_I11_RUNS_NOT_A_POPULATION_SAMPLE"
            or self.coverage_status != "BOUNDED_TWO_WORK_COMPARISON"
        ):
            raise ValueError("I11_R03_ADMITTED_SHAPE_INCOMPLETE")
        if self.status == "VERIFIED_SOURCE_ADMISSION_REVIEW_PENDING":
            if self.method_sha256 != AUTHORIAL_I11_SHA256:
                raise ValueError("I11_R03_FROZEN_METHOD_MISMATCH")
            for claim in self.comparison_claims:
                for index, item in enumerate(claim.evidence):
                    if (
                        item.job_id != self.jobs[index]
                        or item.event_ledger_sha256 != self.event_ledger_digests[index]
                        or item.terminal_receipt_sha256 != self.terminal_receipt_digests[index]
                    ):
                        raise ValueError("I11_R03_EVIDENCE_TOP_LEVEL_PIN_MISMATCH")
        for values in (
            self.run_manifest_digests,
            self.event_ledger_digests,
            self.terminal_receipt_digests,
        ):
            if values is not None and any(
                len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
                for value in values
            ):
                raise ValueError("I11_R03_INVALID_SOURCE_PIN")
        return self


class IndependentScienceReview(FrozenModel):
    """Explicit review disposition; still not owner/scientific acceptance."""

    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["PASS", "FAIL"]
    review_id: str = Field(min_length=1)
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


class PrivateReportReadback(FrozenModel):
    schema: Literal["seshat.i11.r03.f08_private_readback.v1"] = (
        "seshat.i11.r03.f08_private_readback.v1"
    )
    projection_digest: str
    report_json_sha256: str
    report_html_sha256: str
    provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    customer_release: Literal["BLOCKED"] = "BLOCKED"


def _safe_validation_error(exc: ValueError) -> str:
    """Return schema locations/messages without echoing owner-private inputs."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return "I11_R03_INVALID_PROJECTION"
    details = []
    for error in errors(include_url=False, include_input=False):
        location = ".".join(str(item) for item in error.get("loc", ())) or "projection"
        details.append(f"{location}: {error.get('msg', 'invalid')}")
    return "I11_R03_INVALID_PROJECTION: " + "; ".join(details)


def _validate_base(report: ReportProjection) -> None:
    if report.report_id != "R03":
        raise I11R03ReportAdapterError("I11_R03_REQUIRES_F08_R03")
    expected = _digest(report.model_dump(mode="json", exclude={"digest"}))
    if report.digest != expected:
        raise I11R03ReportAdapterError("I11_R03_BASE_PROJECTION_DIGEST_MISMATCH")
    if report.scientific_acceptance != "NOT_ASSERTED":
        raise I11R03ReportAdapterError("I11_R03_FALSE_SCIENTIFIC_ACCEPTANCE")
    if report.scientific_asset is not None:
        raise I11R03ReportAdapterError("I11_R03_BASE_SCIENTIFIC_ASSET_CONFLICT")


def _blocked_projection(report: ReportProjection, reason: str) -> ReportProjection:
    section = ReportSection(
        title="I11 source comparison / BLOCKED",
        claims=(Claim(label="comparison availability", value=reason,
                      state="BLOCKED", evidence=()),),
    )
    block = ReportBlock(code="BLOCKED_METHOD", unmet_input=reason)
    projected = report.model_copy(update={
        "status": "BLOCKED",
        "sections": (*report.sections, section),
        "blocks": (*report.blocks, block),
        "digest": "",
    })
    return projected.model_copy(update={
        "digest": _digest(projected.model_dump(mode="json", exclude={"digest"}))
    })


def project_i11_r03_into_f08(
    base_report: ReportProjection,
    i11_projection: I11R03V2Projection | dict[str, Any],
    *,
    admission: VerifiedTwoRunAdmission | None = None,
    independent_review: IndependentScienceReview | dict[str, Any] | None = None,
) -> ReportProjection:
    """Trusted-host adapter; in-process gate token is integrity, not a security credential."""
    try:
        base_report = ReportProjection.model_validate(base_report.model_dump(mode="json"))
    except ValueError as exc:
        raise I11R03ReportAdapterError(_safe_validation_error(exc)) from exc
    _validate_base(base_report)
    if any(s.title.startswith("I11 source comparison /") for s in base_report.sections):
        raise I11R03ReportAdapterError("I11_R03_ALREADY_PROJECTED")
    try:
        source = I11R03V2Projection.model_validate(i11_projection)
        review = (
            IndependentScienceReview.model_validate(independent_review)
            if independent_review is not None else None
        )
    except ValueError as exc:
        raise I11R03ReportAdapterError(_safe_validation_error(exc)) from exc
    if review is not None and review.projection_sha256 != source.projection_sha256:
        raise I11R03ReportAdapterError("I11_R03_REVIEW_PROJECTION_MISMATCH")
    if source.status == "UNVERIFIED_INPUTS":
        return _blocked_projection(base_report, "UNVERIFIED_INPUTS: byte admission is absent")
    if review is not None and review.disposition == "FAIL":
        return _blocked_projection(base_report, "INDEPENDENT_SCIENCE_REVIEW_FAIL")
    if (
        not isinstance(admission, VerifiedTwoRunAdmission)
        or admission._issuer is not _GATE_ISSUER
    ):
        return _blocked_projection(base_report, "I11_R03_GATE_ADMISSION_REQUIRED")
    if (
        admission.admission_digest != source.admission_digest
        or admission.run_digests != source.run_manifest_digests
        or admission.event_ledger_digests != source.event_ledger_digests
        or admission.receipt_digests != source.terminal_receipt_digests
    ):
        raise I11R03ReportAdapterError("I11_R03_ADMISSION_BINDING_MISMATCH")
    if review is None:
        return _blocked_projection(base_report, "INDEPENDENT_SCIENCE_REVIEW_REQUIRED")

    complete = all(
        claim.status == "SOURCE_ADDRESSED_REVIEW_PENDING"
        and all(
            item.evidence_verification == "VERIFIED_EXACT"
            and item.page in admission.page_maps[index]
            and item.excerpt in admission.page_maps[index][item.page]
            for index, item in enumerate(claim.evidence)
        )
        for claim in source.comparison_claims
    )
    if not complete:
        return _blocked_projection(base_report, "SOURCE_EVIDENCE_INCOMPLETE")

    existing_ref_ids = {ref.ref for ref in base_report.evidence}
    added_refs: dict[str, EvidenceRef] = {}
    claims: list[Claim] = []
    for index, candidate in enumerate(source.comparison_claims, start=1):
        tokens = []
        for item in candidate.evidence:
            token = (
                f"i11-source:{item.source_pdf_sha256}:page:{item.page}:"
                f"excerpt:{item.excerpt_sha256}"
            )
            if token not in existing_ref_ids:
                added_refs[token] = EvidenceRef(
                    ref=token,
                    kind="SOURCE_PIN",
                    detail=(
                        "Owner-private source/page/excerpt pin; supports drillback only and "
                        "does not prove comparative claim correctness"
                    ),
                )
            tokens.append(token)
        review_label = review.disposition if review is not None else "UNREVIEWED"
        claims.append(Claim(
            label=f"candidate comparison {index} / {candidate.kind} / review={review_label}",
            value=candidate.statement,
            state="BLOCKED",
            evidence=tuple(sorted(tokens)),
        ))
        claims.append(Claim(
            label=f"candidate {index} limitations", value=candidate.limits,
            state="BLOCKED", evidence=tuple(sorted(tokens)),
        ))
    claims.extend((
        Claim(label="comparison sampling rule", value=source.sampling_rule,
              state="BLOCKED", evidence=()),
        Claim(label="comparison coverage", value=source.coverage_status,
              state="BLOCKED", evidence=()),
    ))
    section = ReportSection(title="I11 source comparison / CANDIDATE", claims=tuple(claims))
    projected = base_report.model_copy(update={
        "status": "PARTIAL_METADATA",
        "sections": (*base_report.sections, section),
        "evidence": (
            *base_report.evidence,
            *(added_refs[key] for key in sorted(added_refs)),
        ),
        "digest": "",
    })
    return projected.model_copy(update={
        "digest": _digest(projected.model_dump(mode="json", exclude={"digest"}))
    })


def write_and_verify_private_report(
    output: Path,
    report: ReportProjection,
    *,
    verify_only: bool = False,
) -> PrivateReportReadback:
    """Write once or compare JSON+HTML readback; never overwrite stale output."""
    _validate_base(report)
    raw = canonical_bytes(report)
    html = render_html(report)
    expected = {"report.json": raw, "report.html": html}
    missing = [name for name in expected if not (output / name).is_file()]
    if verify_only and missing:
        raise I11R03ReportAdapterError("MISSING_REPORT")
    if output.exists() and not output.is_dir():
        raise I11R03ReportAdapterError("STALE_REPORT")
    if output.is_symlink():
        raise I11R03ReportAdapterError("STALE_REPORT")
    if missing and output.exists() and any(output.iterdir()):
        raise I11R03ReportAdapterError("STALE_REPORT")
    if not output.exists():
        if verify_only:
            raise I11R03ReportAdapterError("MISSING_REPORT")
        output.mkdir(parents=True)
    for name, content in expected.items():
        path = output / name
        if path.is_symlink():
            raise I11R03ReportAdapterError("STALE_REPORT")
        if path.exists():
            if path.read_bytes() != content:
                raise I11R03ReportAdapterError("STALE_REPORT")
        elif verify_only:
            raise I11R03ReportAdapterError("MISSING_REPORT")
        else:
            with path.open("xb") as stream:
                stream.write(content)
    if any((output / name).read_bytes() != content for name, content in expected.items()):
        raise I11R03ReportAdapterError("STALE_REPORT")
    return PrivateReportReadback(
        projection_digest=report.digest,
        report_json_sha256=hashlib.sha256(raw).hexdigest(),
        report_html_sha256=hashlib.sha256(html).hexdigest(),
    )
