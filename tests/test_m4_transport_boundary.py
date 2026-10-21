"""M4 transport/delivery boundary groups (synthetic only).

These assert *structural* coverage and correspondence. None of them claims a
semantic judgement about the delivered content.
"""

import pytest

from seshat.fabric_waves.m4_transport_boundary import (
    DeclaredFact,
    DeliveredSpan,
    StoredInputView,
    assess_delivery,
    assess_output_sections,
    check_declared_fact,
    coverage_report,
    line_number_binding,
    permission_may_not_become_unknown,
    preview_bounds,
    scoped_success_not_inherited,
    utf8_boundary_violations,
)

STORED = StoredInputView(
    source_id="s://a", source_version="v1", byte_length=100, content_sha256="abc", complete=True
)


def span(offset: int, length: int, **kw) -> DeliveredSpan:
    base = {
        "source_id": STORED.source_id,
        "source_version": STORED.source_version,
        "content_sha256": STORED.content_sha256,
    }
    base.update(kw)
    return DeliveredSpan(offset=offset, length=length, **base)


# -- G1 partial delivery ------------------------------------------------------


def test_single_partial_span_leaves_a_named_gap():
    status, code, report = assess_delivery(
        STORED, [span(0, 40)], admitted_byte_length=40, policy="FULL_REQUIRED"
    )
    assert status == "REPORT_INCOMPLETE"
    assert code == "COVERAGE_GAPS[40-100]"
    assert report.missing_ranges == ((40, 100),)


def test_multiple_spans_can_cover_the_whole_artifact():
    status, code, report = assess_delivery(
        STORED, [span(0, 40), span(40, 60)], admitted_byte_length=100, policy="FULL_REQUIRED"
    )
    assert status == "REPORT_COMPLETE", code
    assert report.covered_bytes == 100
    assert report.missing_ranges == ()


def test_overlapping_spans_cannot_fill_a_gap():
    # 0-40 and 20-60 sum to 80 bytes delivered but only cover 0-60.
    status, code, report = assess_delivery(
        STORED, [span(0, 40), span(20, 40)], admitted_byte_length=80, policy="FULL_REQUIRED"
    )
    assert report.covered_bytes == 60
    assert report.overlapping_byte_count == 20
    assert status == "REPORT_INCOMPLETE"
    assert code == "COVERAGE_GAPS[60-100]"


def test_negative_offsets_and_lengths_are_denied():
    status, code, _ = assess_delivery(
        STORED, [span(-1, 10)], admitted_byte_length=10, policy="FULL_REQUIRED"
    )
    assert status == "DELIVERY_DENIED"
    assert "SPAN_RANGE_NEGATIVE" in code
    status, code, _ = assess_delivery(
        STORED, [span(0, -5)], admitted_byte_length=0, policy="FULL_REQUIRED"
    )
    assert status == "DELIVERY_DENIED"
    assert "SPAN_RANGE_NEGATIVE" in code


def test_span_exceeding_stored_is_denied():
    status, code, _ = assess_delivery(
        STORED, [span(90, 20)], admitted_byte_length=20, policy="FULL_REQUIRED"
    )
    assert status == "DELIVERY_DENIED"
    assert "SPAN_EXCEEDS_STORED" in code


def test_routing_metadata_only_covers_nothing():
    status, code, report = assess_delivery(
        STORED,
        [span(0, 100, routing_metadata_only=True)],
        admitted_byte_length=0,
        policy="FULL_REQUIRED",
    )
    assert report.covered_bytes == 0
    assert status == "REPORT_INCOMPLETE"
    assert code == "ROUTING_METADATA_ONLY_NO_CONTENT"


# -- G3 version / identity drift ----------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("source_id", "s://other", "SPAN_SOURCE_ID_MISMATCH"),
        ("source_version", "v2", "SPAN_SOURCE_VERSION_MISMATCH"),
        ("content_sha256", "deadbeef", "SPAN_CONTENT_DIGEST_MISMATCH"),
    ],
)
def test_a_range_without_matching_artifact_identity_is_denied(field, value, expected):
    status, code, _ = assess_delivery(
        STORED, [span(0, 100, **{field: value})], admitted_byte_length=100, policy="FULL_REQUIRED"
    )
    assert status == "DELIVERY_DENIED"
    assert expected in code


def test_identity_mismatch_is_denied_even_when_byte_coverage_is_complete():
    report = coverage_report(STORED, [span(0, 100, source_version="v2")])
    assert report.covered_bytes == 0
    assert report.denials


# -- G2 long lines and UTF-8 --------------------------------------------------


def test_utf8_characters_are_never_split():
    content = ("é" * 10).encode("utf-8")  # 20 bytes, 2 per char
    stored = StoredInputView("s://u", "v1", len(content), "d", complete=True)
    bad = DeliveredSpan(
        offset=0, length=5, source_id="s://u", source_version="v1", content_sha256="d"
    )
    assert utf8_boundary_violations(content, [bad])
    status, code, _ = assess_delivery(
        stored, [bad], admitted_byte_length=5, policy="FULL_REQUIRED", content=content
    )
    assert status == "DELIVERY_DENIED"
    assert "SPLIT_UTF8" in code


def test_preview_is_measured_in_bytes_and_preserves_long_lines():
    content = "x" * 60_000 + "\n" + "y" * 2500
    meta = preview_bounds(content)
    assert meta["truncated"] is True
    assert meta["preview_bytes"] <= 50 * 1024
    assert meta["long_line_numbers"] == [2]
    assert meta["long_lines_preserved_not_truncated"] is True
    assert meta["truncated_byte_range"][0] == meta["preview_bytes"]


def test_preview_never_ends_mid_character():
    content = "é" * 40_000  # 80 000 bytes
    meta = preview_bounds(content, max_preview_bytes=1001)
    assert meta["preview_bytes"] == 1000  # odd cut rolled back to a char edge


def test_end_marker_is_not_evidence_of_completeness():
    meta = preview_bounds("partial body …\n[END]")
    assert meta["end_marker_present"] is True
    assert meta["end_marker_is_not_proof_of_completeness"] is True


# -- G6 line binding, G4 permission, G5 scope ---------------------------------


def test_line_number_bound_to_artifact_version():
    assert line_number_binding("v1", 3, actual_version="v2") == "LINE_NUMBER_STALE_ARTIFACT_VERSION"
    assert line_number_binding("v1", 3, actual_version="v1") == "LINE_NUMBER_BOUND_TO_ARTIFACT_VERSION"
    assert line_number_binding("v1", 0, actual_version="v1") == "LINE_NUMBER_INVALID"


def test_permission_not_erased_to_unknown():
    assert permission_may_not_become_unknown(True, True) == "PERMISSION_ERASED_TO_UNKNOWN"
    assert permission_may_not_become_unknown(True, False) == "OK"


def test_scoped_success_not_inherited():
    assert scoped_success_not_inherited(False, "new", True) == "INHERITED_VALIDATION_WITHOUT_OLD_SCOPE"
    assert scoped_success_not_inherited(True, "new", True) == "NEW_PURPOSE_CANNOT_INHERIT_OLD_VALIDATION"


# -- output gate --------------------------------------------------------------


def test_a_heading_without_content_does_not_complete_a_report():
    sections = {"question": "Q?", "observed_facts": "   ", "unresolved": "x", "next_action": "y"}
    status, code = assess_output_sections(
        sections, required=("question", "observed_facts", "unresolved", "next_action")
    )
    assert status == "REPORT_INCOMPLETE"
    assert "observed_facts" in code


def test_known_partial_flag_overrides_apparent_completeness():
    sections = {"a": "x", "b": "y"}
    assert assess_output_sections(sections, required=("a", "b"))[0] == "REPORT_COMPLETE"
    assert assess_output_sections(sections, required=("a", "b"), partial_finish=True) == (
        "REPORT_INCOMPLETE",
        "PARTIAL_FINISH_FLAG_SET",
    )
    assert assess_output_sections(sections, required=("a", "b"), metadata_only=True) == (
        "REPORT_INCOMPLETE",
        "METADATA_ONLY_FLAG_SET",
    )


# -- declared synthetic fact locators -----------------------------------------


CONTENT = b"Method Alpha records a stable observation in material class T"


def test_declared_fact_locator_must_match_offset_and_version():
    good = DeclaredFact("c1", "stable observation", "s://a", "A1", CONTENT.index(b"stable"))
    assert check_declared_fact(good, source_id="s://a", source_version="A1", content=CONTENT).ok

    wrong_offset = DeclaredFact("c2", "stable observation", "s://a", "A1", 0)
    result = check_declared_fact(wrong_offset, source_id="s://a", source_version="A1", content=CONTENT)
    assert not result.ok
    assert result.status == "LOCATOR_QUOTE_NOT_AT_OFFSET"
    assert result.observed_offset == CONTENT.index(b"stable")

    stale = DeclaredFact("c3", "stable observation", "s://a", "A0", CONTENT.index(b"stable"))
    assert (
        check_declared_fact(stale, source_id="s://a", source_version="A1", content=CONTENT).status
        == "LOCATOR_SOURCE_VERSION_MISMATCH"
    )


def test_locator_match_is_explicitly_not_entailment():
    fact = DeclaredFact("c4", "stable observation", "s://a", "A1", CONTENT.index(b"stable"))
    result = check_declared_fact(fact, source_id="s://a", source_version="A1", content=CONTENT)
    assert "not entailment" in result.detail
