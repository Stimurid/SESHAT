"""Invented-public unit tests of real-corpus reporting boundary.

Only the PRIVATE operator integration test may claim a real Opus receipt.
These tests monkeypatch canonical checks solely against invented PDF fixtures.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

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
    from seshat.public_pdf_method_bridge import make_public_pdf_method_views
    derivative = make_public_pdf_method_views(
        packet, requests, source_bytes=sources,
        owner_excluded_source_ids=frozenset(),
        owner_excluded_source_sha256=frozenset(),
    )[0]
    fresh = derivative.source_utf8.decode("utf-8")
    original_chunks = []
    for page_number in range(1, derivative.pdf_page_count + 1):
        marker = (
            f"=== ORIGINAL PDF PAGE {page_number} / {derivative.pdf_page_count} "
            f"SOURCE {derivative.original_source_id} ==="
        )
        next_marker = (
            f"=== ORIGINAL PDF PAGE {page_number + 1} / {derivative.pdf_page_count} "
            f"SOURCE {derivative.original_source_id} ==="
        )
        content = fresh.split(marker, 1)[1]
        if page_number < derivative.pdf_page_count:
            content = content.split(next_marker, 1)[0]
        original_chunks.append(
            f"=== PRINTED PDF PAGE {page_number} / "
            f"{derivative.pdf_page_count} ===\n{content.strip()}\n"
        )
    original_model_text = "\n".join(original_chunks).encode("utf-8")
    monkeypatch.setattr(
        portfolio, "CCBY_PAGES_SHA256", hashlib.sha256(original_model_text).hexdigest()
    )
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
        "source_pdf_sha256": first_pdf_sha,
        "pages_bytes": original_model_text,
    }
    if not observed:
        original_observe["status"] = "BLOCKED_REAL_MODEL_BINDING"
    monkeypatch.setattr(portfolio, "observe_existing_i11_package", lambda *a, **k: original_observe)
    params = dict(
        package_dir=Path("invented-never-read"),
        exclusion_policy={"excluded": {
            "source_drive_ids": [], "source_names": [],
            "aliases": [], "source_sha256": [],
        }},
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
    assert result["original_i11_model_input_provenance"]["pages_normalized_equivalent"] == 2
    assert result["original_i11_model_input_provenance"]["byte_identical_not_assumed"]
    assert result["selected_works"][0]["new_pdf_view_used_by_original_model"] is False
    assert result["selected_works"][1]["original_i11_model_input_pages_sha256"] == "NOT_RUN"
    assert result["r03"]["fictional_controls_counted_as_real"] is False
    assert result["customer_release"] == "BLOCKED"
    assert result["scientific_acceptance"] == "NOT_PERFORMED"
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

def test_real_owner_authorization_is_checked_before_any_public_pdf_join(monkeypatch):
    from seshat.fabric_waves.i11_vertical import observe_existing_i11_package
    params = _args(monkeypatch)
    # The production function, NOT the fixture mock, must reject this
    # non-authorizing policy without opening any private source or PDF.
    params["exclusion_policy"]["schema"] = "seshat.owner_source_exclusion.default_empty"
    params["exclusion_policy"]["authority"] = None
    params["exclusion_policy"]["status"] = "DEFAULT_EMPTY"
    monkeypatch.setattr(portfolio, "observe_existing_i11_package", observe_existing_i11_package)
    def forbidden_public_join(*args, **kwargs):
        pytest.fail("Derived public source must not be read before owner policy authorization")
    monkeypatch.setattr(portfolio, "make_public_pdf_method_views", forbidden_public_join)
    with pytest.raises(portfolio.RealI11PortfolioError, match="RUN_NOT_ADMITTED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)


def test_old_model_pages_must_match_rederived_pdf_page_contents(monkeypatch):
    params = _args(monkeypatch)
    original = params["source_bytes"]["pub-a"]
    assert original.startswith(b"%PDF")
    observed = portfolio.observe_existing_i11_package(
        params["package_dir"], exclusion_policy=params["exclusion_policy"],
        f07_permission=params["f07_permission"],
        source_id=params["source_id"], source_name=params["source_name"],
        f07_full_read_granted=params["f07_full_read_granted"],
    )
    old = observed["pages_bytes"]
    assert b"Researchers" in old
    altered = old.replace(b"Researchers", b"ResearchXrs", 1)
    observed["pages_bytes"] = altered
    monkeypatch.setattr(
        portfolio, "CCBY_PAGES_SHA256", hashlib.sha256(altered).hexdigest()
    )
    with pytest.raises(portfolio.RealI11PortfolioError, match="SOURCE_TEXT_DIVERGED"):
        portfolio.make_observed_i11_real_source_portfolio(**params)
