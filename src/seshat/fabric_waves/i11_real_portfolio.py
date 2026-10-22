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
    CCBY_PAGES_SHA256, CCBY_PDF_SHA256, OBSERVED_I11_JOB_ID,
    ActivityNetworkState,
)
from seshat.fabric_waves.i11_readable_reports import compose_readable_r01r02
from seshat.fabric_waves.i11_second_run import (
    BLOCKED_SECOND_MODELRUN,
    admit_second_authorial_i11_run,
)
from seshat.fabric_waves.i11_source_lineage import (
    inner_page_texts,
    qualify_source_text_lineage,
)
from seshat.fabric_waves.i11_vertical import (
    is_real_authorizing_policy,
    observe_existing_i11_package,
    run_observed_vertical,
)
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
    if not is_real_authorizing_policy(exclusion_policy) or f07_permission is None:
        raise RealI11PortfolioError("I11_REAL_PORTFOLIO_POLICY_BEFORE_JOIN")
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
    model_pages = None
    pages_bytes = observed.get("pages_bytes")
    if isinstance(pages_bytes, (bytes, bytearray)):
        model_pages = inner_page_texts(bytes(pages_bytes))
    selected = []
    for paper in public_corpus.articles:
        method_view = members_by_sha[paper.pdf_sha256]
        analysed = paper.pdf_sha256 == CCBY_PDF_SHA256
        derived_pages = inner_page_texts(method_view.source_utf8)
        lineage = qualify_source_text_lineage(
            original_pdf_sha256=paper.pdf_sha256,
            derived_page_view_sha256=method_view.source_pin.sha256,
            extractor_version=method_view.extractor_version,
            original_model_input_page_text_sha256=(
                CCBY_PAGES_SHA256 if analysed else None
            ),
            model_input_pages=model_pages if analysed else None,
            derived_pages=derived_pages if analysed else None,
        )
        selected.append({
            "source_id": paper.carrier_id,
            "original_pdf_sha256": paper.pdf_sha256,
            "original_pdf_page_count": paper.page_count,
            "f07_full_receipt_sha256": paper.f07_full_receipt_sha256,
            "f08_page_evidence_count": len(paper.f08_page_evidence),
            "original_model_input_page_text_sha256": lineage[
                "original_model_input_page_text_sha256"
            ],
            "derived_page_view_sha256": method_view.source_pin.sha256,
            "derived_page_view_role": "POST_EXTRACTION_F07_F08_VIEW_NOT_AUTOMATICALLY_MODEL_INPUT",
            "extractor_version": method_view.extractor_version,
            "extraction_relation": lineage["extraction_relation"],
            "derived_view_is_model_input": lineage["derived_view_is_model_input"],
            "page_comparison": lineage["page_comparison"],
            "authorial_method": AUTHORIAL_I11_ID if analysed else "NOT_RUN",
            "actual_terminal_job": OBSERVED_I11_JOB_ID if analysed else "NOT_RUN",
            "analysis_state": "AUTHORIAL_I11_OBSERVED_UNATTESTED" if analysed
                              else "REAL_SOURCE_ADMITTED_PENDING_I11",
            "scientific_acceptance": "NOT_PERFORMED",
        })
    assert sum(x["analysis_state"] == "AUTHORIAL_I11_OBSERVED_UNATTESTED" for x in selected) == 1
    readable = compose_readable_r01r02(
        state,
        job_id=str(observed.get("job_id") or OBSERVED_I11_JOB_ID),
        stdout_sha256=str(observed.get("stdout_sha256") or ""),
        source_sha256=CCBY_PAGES_SHA256,
        hub_receipt_sha256=observed.get("hub_receipt_sha256"),
    )
    second = admit_second_authorial_i11_run(
        exclusion_policy=exclusion_policy,
        f07_permission_b=None,
        source_id="second-admitted-pending-grant",
    )
    r03 = compose_real_two_source_r03(
        state,
        None,
        membership_kinds={
            state.work_id: "ADMITTED_REAL_OBSERVED",
            "second-admitted-pending-grant": "REAL_SOURCE_ADMITTED_PENDING_I11",
        },
        second_run=second,
    )

    content = {
        "schema": "seshat.i11.real_two_source_portfolio.v1",
        "status": "TWO_REAL_SOURCES_ONE_AUTHORIAL_I11_RUN",
        "visibility": "OWNER_PRIVATE_ONLY",
        "source_rights": "OPERATOR_DECLARED_CC_BY_PUBLISHED_ARTICLES_ONLY",
        "independent_source_rights_attestation": "NO",
        "selected_works": tuple(selected),
        "r03": r03,
        "first_model_run": {
            "job_id": OBSERVED_I11_JOB_ID,
            "method_body_id": AUTHORIAL_I11_ID,
            "method_sha256": AUTHORIAL_I11_SHA256,
            "observed_actor_count": len(state.actors),
            "observed_action_count": len(state.action_events),
            "observed_relation_count": len(state.relations),
            "stdout_sha256": observed.get("stdout_sha256"),
            "r01r02_readable_sha256": readable["projection_sha256"],
        },
        "second_model_run": second,
        "first_source_readable_r01r02": {
            "projection_sha256": readable["projection_sha256"],
            "scientific_acceptance": readable["scientific_acceptance"],
            "customer_release": readable["customer_release"],
            "im_status": readable["im_status"],
        },
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
    }
    return {**content, "projection_sha256": _hash_json(content)}


def _event_locator(events) -> dict[str, Any]:
    for event in events:
        for address in event.source_addresses:
            if address.page is not None:
                return {
                    "event_id": event.event_id,
                    "page": address.page,
                    "layer": event.layer,
                    "verb": event.verb,
                }
    if events:
        return {
            "event_id": events[0].event_id,
            "page": None,
            "layer": events[0].layer,
            "verb": events[0].verb,
            "unknown": "PAGE_UNKNOWN",
        }
    return {"event_id": None, "page": None, "unknown": "NO_TYPED_EVENT"}


def compose_real_two_source_r03(
    state_a: ActivityNetworkState | None,
    state_b: ActivityNetworkState | None,
    *,
    membership_kinds: Mapping[str, str],
    second_run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Comparative R03 only when two independently grounded real I11 states exist."""
    real_ids = [
        work_id
        for work_id, kind in membership_kinds.items()
        if kind == "ADMITTED_REAL_OBSERVED"
    ]
    blocked = {
        "report_id": "R03",
        "status": "BLOCKED_PENDING_SECOND_REAL_AUTHORIAL_METHOD_RUN",
        "real_sources_admitted": len(membership_kinds),
        "real_works_with_i11_analysis": len(real_ids),
        "comparison_claims": [],
        "fictional_controls_counted_as_real": False,
        "test_only_control_present": "TEST_ONLY_FICTIONAL" in membership_kinds.values(),
        "source_grounded_interstudy_comparison": "NOT_PERFORMED",
        "second_model_run_status": (second_run or {}).get("status", BLOCKED_SECOND_MODELRUN),
    }
    if state_a is None or state_b is None or len(real_ids) < 2:
        return blocked
    if state_a.work_id == state_b.work_id:
        raise RealI11PortfolioError("I11_R03_SAME_WORK")
    if (
        state_a.model_job_receipt_or_null
        and state_a.model_job_receipt_or_null == state_b.model_job_receipt_or_null
    ):
        raise RealI11PortfolioError("I11_R03_SAME_JOB")
    if (
        state_a.scientific_acceptance != "NOT_ASSERTED"
        or state_b.scientific_acceptance != "NOT_ASSERTED"
    ):
        raise RealI11PortfolioError("I11_HUMAN_APPROVAL_FORBIDDEN")
    identities_a = {actor.work_scoped_identity.casefold() for actor in state_a.actors}
    identities_b = {actor.work_scoped_identity.casefold() for actor in state_b.actors}
    overlap = sorted(identities_a & identities_b)
    claims = []
    for layer in ("RP", "SS", "FT", "PO", "BR", "IM", "PR"):
        ev_a = [event for event in state_a.action_events if event.layer == layer]
        ev_b = [event for event in state_b.action_events if event.layer == layer]
        claims.append({
            "axis": layer,
            "work_a": {"work_id": state_a.work_id, **_event_locator(ev_a), "event_count": len(ev_a)},
            "work_b": {"work_id": state_b.work_id, **_event_locator(ev_b), "event_count": len(ev_b)},
            "inference_forbidden": (
                "shared_listed_identity_or_institution_is_not_shared_RP_operation"
            ),
        })
    return {
        "report_id": "R03",
        "status": "SOURCE_GROUNDED_UNREVIEWED",
        "real_sources_admitted": len(membership_kinds),
        "real_works_with_i11_analysis": 2,
        "comparison_claims": claims,
        "identity_overlap_listed": overlap,
        "identity_overlap_is_not_shared_operation": True,
        "fictional_controls_counted_as_real": False,
        "source_grounded_interstudy_comparison": "LAYERED_WITH_PER_WORK_LOCATORS",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
    }


def run_stacked_product(
    out: Path,
    *,
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    package_dir: Path | None = None,
    f07_permission_b: dict[str, Any] | None = None,
    public_corpus: PublicCorpusIntake | None = None,
    public_requests: tuple[PublicArticleRequest, ...] | None = None,
    source_bytes: Mapping[str, bytes] | None = None,
    owner_excluded_source_ids: frozenset[str] | None = None,
    owner_excluded_source_sha256: frozenset[str] | None = None,
    second_source_id: str = "",
    second_source_name: str = "",
    second_source_bytes: bytes | None = None,
    second_pages_bytes: bytes | None = None,
    job_registry: Mapping[str, Any] | None = None,
    verify_only: bool = False,
    source_id: str = "",
    source_name: str = "",
    f07_full_read_granted: bool = False,
    submit_new_paid_job: bool = False,
) -> dict[str, Any]:
    """One resumable command: first observed source, second-run gate, honest R03."""
    if submit_new_paid_job:
        raise ValueError("I11_DUPLICATE_LAUNCH")
    out.mkdir(parents=True, exist_ok=True)
    first: dict[str, Any] = {
        "status": "BLOCKED_REAL_MODEL_BINDING",
        "reason": "PACKAGE_MISSING",
    }
    if package_dir is not None:
        first = run_observed_vertical(
            out / "source_a",
            package_dir,
            exclusion_policy=exclusion_policy,
            f07_permission=f07_permission,
            verify_only=verify_only,
            source_id=source_id,
            source_name=source_name,
            f07_full_read_granted=f07_full_read_granted,
        )
    second = admit_second_authorial_i11_run(
        exclusion_policy=exclusion_policy,
        f07_permission_b=f07_permission_b,
        source_id=second_source_id or "second-admitted-pending-grant",
        source_name=second_source_name,
        source_bytes=second_source_bytes,
        pages_bytes=second_pages_bytes,
        job_registry=job_registry,
        submit_new_paid_job=False,
    )
    portfolio = None
    if (
        public_corpus is not None
        and public_requests is not None
        and source_bytes is not None
    ):
        portfolio = make_observed_i11_real_source_portfolio(
            package_dir=package_dir or Path("missing-package"),
            exclusion_policy=exclusion_policy,
            f07_permission=f07_permission,
            f07_full_read_granted=f07_full_read_granted,
            source_id=source_id,
            source_name=source_name,
            public_corpus=public_corpus,
            public_requests=public_requests,
            source_bytes=source_bytes,
            owner_excluded_source_ids=owner_excluded_source_ids,
            owner_excluded_source_sha256=owner_excluded_source_sha256,
        )
    typed = first.get("typed_state")
    r03 = (portfolio or {}).get("r03") or compose_real_two_source_r03(
        typed if isinstance(typed, ActivityNetworkState) else None,
        None,
        membership_kinds={
            "first": (
                "ADMITTED_REAL_OBSERVED"
                if first.get("status") == "OBSERVED_BOUND_SELF_OBSERVED"
                else "UNBOUND"
            ),
            "second": "REAL_SOURCE_ADMITTED_PENDING_I11",
        },
        second_run=second,
    )
    manifest = {
        "schema": "seshat.i11.stacked_product.v1",
        "mode": "STACKED_PR87_ON_PR89",
        "first_source": {
            key: first.get(key)
            for key in (
                "status", "job_id", "stdout_sha256", "method_sha256",
                "source_pdf_sha256", "source_pages_sha256",
                "r01r02_sha256", "r01r02_readable_sha256",
                "typed_actor_count", "typed_event_count", "typed_relation_count",
            )
        },
        "second_model_run": second,
        "r03": r03,
        "portfolio_sha256": (portfolio or {}).get("projection_sha256"),
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
    }
    manifest["manifest_sha256"] = _hash_json({k: v for k, v in manifest.items() if k != "manifest_sha256"})
    target = out / "stacked_manifest.json"
    if target.exists():
        stored = json.loads(target.read_text(encoding="utf-8"))
        if _hash_json({k: v for k, v in stored.items() if k != "manifest_sha256"}) != manifest["manifest_sha256"]:
            raise RealI11PortfolioError("I11_STALE_REPORT")
    elif verify_only:
        raise RealI11PortfolioError("I11_STACKED_MANIFEST_MISSING")
    else:
        with target.open("x", encoding="utf-8") as sink:
            sink.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            sink.flush()
    return manifest
