"""M4 transport/delivery boundary groups (synthetic only)."""

from seshat.fabric_waves.m4_transport_boundary import (
    DeliveredRange,
    StoredInputView,
    assess_delivery,
    line_number_binding,
    permission_may_not_become_unknown,
    preview_bounds,
    scoped_success_not_inherited,
)


def test_full_required_partial_with_finish_stop_is_incomplete():
    stored = StoredInputView("s://a", "v1", 100_000, "abc", complete=True)
    delivered = DeliveredRange(offset=0, length=40_000, finish="stop")
    status, code = assess_delivery(stored, delivered, admitted_byte_length=40_000, policy="FULL_REQUIRED")
    assert status == "REPORT_INCOMPLETE"
    assert code == "PARTIAL_WITH_FINISH_STOP"


def test_preview_bounds_flags_large_preview_and_long_lines():
    content = "x" * 60_000
    long_line = "y" * 2500
    meta = preview_bounds(content + "\n" + long_line)
    assert meta["truncated"] is True
    assert meta["preview_bytes"] <= 50 * 1024
    assert meta["long_line_numbers"]


def test_line_number_bound_to_artifact_version():
    assert line_number_binding("v1", 3, actual_version="v2") == "LINE_NUMBER_STALE_ARTIFACT_VERSION"
    assert line_number_binding("v1", 3, actual_version="v1") == "LINE_NUMBER_BOUND_TO_ARTIFACT_VERSION"


def test_permission_not_erased_to_unknown():
    assert permission_may_not_become_unknown(True, True) == "PERMISSION_ERASED_TO_UNKNOWN"
    assert permission_may_not_become_unknown(True, False) == "OK"


def test_scoped_success_not_inherited():
    assert scoped_success_not_inherited(False, "new", True) == "INHERITED_VALIDATION_WITHOUT_OLD_SCOPE"
