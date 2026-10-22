"""I11 real-corpus portfolio boundary: do not promote a fake R03 comparison.

Links the existing completed observed authorial I11 model job to the actual
two-source F07/F08 public intake and source-to-UTF8 derivations. Source B
has its own independently witnessed paper, but has NOT been analysed by
authorial I11. The product cannot issue scientific comparative R03 until
both works have independently grounded real activity states.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID, AUTHORIAL_I11_SHA256, AUTHORIAL_I11_VERSION,
    CCBY_PDF_SHA256, OBSERVED_I11_JOB_ID, ActivityNetworkState,
)
from seshat.fabric_waves.i11_vertical import observe_existing_i11_package
from seshat.public_pdf_method_bridge import make_public_pdf_method_views
from seshat.public_source_admission import PublicArticleRequest, PublicCorpusIntake


class RealI11PortfolioError(ValueError):
    pass


def _hash_json(content: Any) -> str:
    return hashlib.sha256(json.dumps(
        content, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def make_observed_i11_real_source_portfolio(
    *,
    package_dir: Path,
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    f07_full_read_granted: bool,
    source_id: str,
    source_name: str,
    public_corpus: PublicCorpusIntake,
    public_requests: tuple[PublicArticleRequest, ...],
    source_bytes: Mapping[str, bytes],
    owner_excluded_source_ids: frozenset[str] | None,
    owner_excluded_source_sha256: frozenset[str] | None,
) -> dict[str, Any]:
    """Run both independent operator gates from their *original* bytes.

    Returning a blocked comparative R03 is intentional. Neither a fictional
    I11 world nor an unprocessed real PDF counts as a second analysed work.
    """
    observed = observe_existing_i11_package(
        package_dir, exclusion_policy=exclusion_policy,
        f07_permission=f07_permission,
        source_id=source_id, source_name=source_name,
        f07_full_read_granted=f07_full_read_granted,
    )
    if observed.get("status") != "OBSERVED_TERMINAL_UNATTESTED":
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_OBSERVED_RUN_NOT_ADMITTED")
    state = observed.get("typed_state")
    if not isinstance(state, ActivityNetworkState):
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_MODEL_STATE_REQUIRED")
    if state.methodbody_id != AUTHORIAL_I11_ID or state.version != AUTHORIAL_I11_VERSION:
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_METHOD_DRIFT")
    if (observed.get("job_id") != OBSERVED_I11_JOB_ID
        or observed.get("method_sha256") != AUTHORIAL_I11_SHA256
        or observed.get("source_pdf_sha256") != CCBY_PDF_SHA256):
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_TERMINAL_PIN_DRIFT")
    if state.customer_release != "BLOCKED" or state.scientific_acceptance != "NOT_ASSERTED":
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_FALSE_AUTHORITY")

    if owner_excluded_source_ids is None or owner_excluded_source_sha256 is None:
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_OWNER_POLICY_REQUIRED")
    # The private canonical owner policy is mandatory and travels forward.
    # Additional exclusions may be added, never removed by a caller.
    excluded = exclusion_policy.get("excluded", {})
    private_names = frozenset(str(value) for field in (
        "source_drive_ids", "source_names", "aliases"
    ) for value in excluded.get(field, ()))
    private_shas = frozenset(str(value).lower() for value in (
        excluded.get("source_sha256", ())
    ))
    owner_excluded_source_ids = owner_excluded_source_ids | private_names
    owner_excluded_source_sha256 = owner_excluded_source_sha256 | private_shas
    derived = make_public_pdf_method_views(
        public_corpus, public_requests, source_bytes=source_bytes,
        owner_excluded_source_ids=owner_excluded_source_ids,
        owner_excluded_source_sha256=owner_excluded_source_sha256,
    )
    members = [x for x in derived if x.original_pdf_sha256 == CCBY_PDF_SHA256]
    if len(members) != 1 or len(derived) != 2:
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_PRIMARY_SOURCE_NOT_IN_CORPUS")
    if state.model_job_receipt_or_null not in (None, OBSERVED_I11_JOB_ID):
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_MODEL_JOB_MISMATCH")

    members_by_sha = {m.original_pdf_sha256: m for m in derived}
    selected = []
    for paper in public_corpus.articles:
        method_view = members_by_sha[paper.pdf_sha256]
        analysed = paper.pdf_sha256 == CCBY_PDF_SHA256
        selected.append({
            "source_id": paper.carrier_id,
            "original_pdf_sha256": paper.pdf_sha256,
            "original_pdf_page_count": paper.page_count,
            "f07_full_receipt_sha256": paper.f07_full_receipt_sha256,
            "f08_page_evidence_count": len(paper.f08_page_evidence),
            "derived_page_view_sha256": method_view.source_pin.sha256,
            "authorial_method": AUTHORIAL_I11_ID if analysed else "NOT_RUN",
            "actual_terminal_job": OBSERVED_I11_JOB_ID if analysed else "NOT_RUN",
            "analysis_state": "AUTHORIAL_I11_OBSERVED_UNATTESTED" if analysed
                              else "REAL_SOURCE_ADMITTED_PENDING_I11",
            "scientific_acceptance": "NOT_PERFORMED",
        })
    assert sum(x["analysis_state"] == "AUTHORIAL_I11_OBSERVED_UNATTESTED" for x in selected) == 1

    content = {
        "schema": "seshat.i11.real_two_source_portfolio.v1",
        "status": "TWO_REAL_SOURCES_ONE_AUTHORIAL_I11_RUN",
        "visibility": "OWNER_PRIVATE_ONLY",
        "source_rights": "OPERATOR_DECLARED_CC_BY_PUBLISHED_ARTICLES_ONLY",
        "independent_source_rights_attestation": "NO",
        "selected_works": tuple(selected),
        "r03": {
            "report_id": "R03",
            "status": "BLOCKED_PENDING_SECOND_REAL_AUTHORIAL_METHOD_RUN",
            "real_sources_admitted": 2,
            "real_works_with_i11_analysis": 1,
            "comparison_claims": [],
            "fictional_controls_counted_as_real": False,
            "source_grounded_interstudy_comparison": "NOT_PERFORMED",
        },
        "first_model_run": {
            "job_id": OBSERVED_I11_JOB_ID,
            "method_body_id": AUTHORIAL_I11_ID,
            "method_sha256": AUTHORIAL_I11_SHA256,
            "observed_actor_count": len(state.actors),
            "observed_action_count": len(state.action_events),
            "observed_relation_count": len(state.relations),
        },
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
    }
    return {**content, "projection_sha256": _hash_json(content)}
