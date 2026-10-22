"""Invented-public unit tests of real-corpus reporting boundary.

Only the PRIVATE operator integration test may claim a real Opus receipt.
These tests monkeypatch canonical checks solely against invented PDF fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_public_source_admission import sample
from seshat.public_source_admission import admit_public_published_corpus
from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID, AUTHORIAL_I11_VERSION, interpret_labeled_world,
    fictional_method_bytes, world_bytes,
)
from seshat.fabric_waves import i11_real_portfolio as portfolio


def _args(monkeypatch, *, observed=True):
    requests, sources = sample()
    packet = admit_public_published_corpus(requests, source_bytes=sources)
    first_pdf_sha = packet.articles[0].pdf_sha256
    monkeypatch.setattr(portfolio, "CCBY_PDF_SHA256", first_pdf_sha)
    state = interpret_labeled_world(
        world="world_a",
        source_bytes=world_bytes("world_a"),
        method_bytes=fictional_method_bytes(),
    ).model_copy(update={
        "methodbody_id": AUTHORIAL_I11_ID,
        "version": AUTHORIAL_I11_VERSION,
        "model_job_receipt_or_null": portfolio.OBSERVED_I11_JOB_ID,
    })
    original_observe = {
        "status": "OBSERVED_TERMINAL_UNATTESTED",
        "typed_state": state,
        "job_id": portfolio.OBSERVED_I11_JOB_ID,
        "method_sha256": portfolio.AUTHORIAL_I11_SHA256,
        "stdout_sha256": "0" * 64,
        "source_pdf_sha256": first_pdf_sha,
    }
    if not observed:
        original_observe["status"] = "BLOCKED_REAL_MODEL_BINDING"
    monkeypatch.setattr(portfolio, "observe_existing_i11_package", lambda *a, **k: original_observe)
    params = dict(
        package_dir=Path("invented-never-read"),
        exclusion_policy={
            "schema": "seshat.owner_source_exclusion.v1",
            "authority": "OWNER_EXPLICIT",
            "status": "PERMANENT_ACTIVE_EXCLUSION",
            "operator_supplied": True,
            "excluded": {
                "source_drive_ids": ["invented-excluded-drive"],
                "source_names": ["invented-excluded-name"],
                "aliases": ["invented-excluded-alias"],
                "source_sha256": [],
            },
        },
        f07_permission={"not_a_real_permission": True},
        f07_full_read_granted=False,
        source_id="invented-pdf", source_name="invented-world",
        public_corpus=packet, public_requests=requests, source_bytes=sources,
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )
    return params


def test_two_real_named_source_slots_but_second_analysis_is_not_invented(monkeypatch):
    params = _args(monkeypatch)
    result = portfolio.make_observed_i11_real_source_portfolio(**params)
    assert result["status"] == "TWO_REAL_SOURCES_ONE_AUTHORIAL_I11_RUN"
    assert len(result["selected_works"]) == 2
    assert sum(row["actual_terminal_job"] == "NOT_RUN" for row in result["selected_works"]) == 1
    assert result["r03"]["status"] == "BLOCKED_PENDING_SECOND_REAL_AUTHORIAL_METHOD_RUN"
    assert result["r03"]["comparison_claims"] == []
    assert result["r03"]["fictional_controls_counted_as_real"] is False
    assert result["customer_release"] == "BLOCKED"
    assert result["scientific_acceptance"] == "NOT_PERFORMED"
    analysed = next(row for row in result["selected_works"] if row["actual_terminal_job"] != "NOT_RUN")
    pending = next(row for row in result["selected_works"] if row["actual_terminal_job"] == "NOT_RUN")
    assert analysed["derived_page_view_role"].startswith("POST_EXTRACTION")
    assert analysed["derived_view_is_model_input"] is False
    assert analysed["original_model_input_page_text_sha256"]
    assert pending["original_model_input_page_text_sha256"] == "NOT_FED_TO_MODEL"
    assert result["second_model_run"]["status"] == "BLOCKED_SECOND_MODELRUN"
    assert result == portfolio.make_observed_i11_real_source_portfolio(**params)


@pytest.mark.parametrize("field", ["owner_excluded_source_ids", "owner_excluded_source_sha256"])
def test_missing_policy_is_not_a_default_grant(monkeypatch, field):
    params = _args(monkeypatch)
    params[field] = None
    with pytest.raises(portfolio.RealI11PortfolioError, match="OWNER_POLICY_REQUIRED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)


@pytest.mark.parametrize("field", ["id", "sha", "alias", "derived"])
def test_private_owner_exclusions_survive_across_multi_source_join(monkeypatch, field):
    params = _args(monkeypatch)
    pin = params["public_corpus"].articles[1]
    if field == "id":
        params["exclusion_policy"]["excluded"]["source_drive_ids"] = [pin.carrier_id]
    elif field == "sha":
        params["exclusion_policy"]["excluded"]["source_sha256"] = [pin.pdf_sha256]
    elif field == "alias":
        params["exclusion_policy"]["excluded"]["aliases"] = [pin.doi]
    else:
        from seshat.public_pdf_method_bridge import make_public_pdf_method_views
        derived = make_public_pdf_method_views(
            params["public_corpus"], params["public_requests"],
            source_bytes=params["source_bytes"],
            owner_excluded_source_ids=frozenset(),
            owner_excluded_source_sha256=frozenset(),
        )
        params["owner_excluded_source_sha256"] = frozenset({derived[1].source_pin.sha256})
    with pytest.raises(Exception, match="SOURCE_EXCLUDED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)


def test_missing_model_terminal_cannot_be_replaced_by_public_pdf(monkeypatch):
    params = _args(monkeypatch, observed=False)
    with pytest.raises(portfolio.RealI11PortfolioError, match="RUN_NOT_ADMITTED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)


def test_forged_second_original_pdf_fails_before_fake_r03(monkeypatch):
    params = _args(monkeypatch)
    params["source_bytes"] = {**params["source_bytes"],
                               "pub-b": params["source_bytes"]["pub-b"][:-1]}
    with pytest.raises(Exception, match="SOURCE_ADMISSION_FAILED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)


def test_no_primary_observed_pdf_in_corpus_does_not_yield_fake_science(monkeypatch):
    params = _args(monkeypatch)
    monkeypatch.setattr(portfolio, "CCBY_PDF_SHA256", "a" * 64)
    with pytest.raises(portfolio.RealI11PortfolioError, match="TERMINAL_PIN_DRIFT"):
        portfolio.make_observed_i11_real_source_portfolio(**params)
