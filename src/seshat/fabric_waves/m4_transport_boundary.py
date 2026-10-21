"""M4 transport vs semantic delivery boundaries (synthetic contracts only).

Scope statement, deliberately narrow: everything here decides **structural
completeness and correspondence** — did the bytes a consumer received cover
the bytes the host stored, for the artifact version it claims?  Nothing here
validates meaning.  A ``REPORT_COMPLETE`` says the transport contract held;
it is not a judgement that the content is correct, relevant or entailed, and
:func:`check_declared_fact` certifies only that a declared synthetic quote
occurs where it says it does, never that a natural-language claim follows
from it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

DeliveryStatus = Literal["REPORT_COMPLETE", "REPORT_INCOMPLETE", "DELIVERY_DENIED"]

#: Byte cap for a bounded preview. Previews are measured in bytes, never in
#: characters, because a character slice makes a byte claim unverifiable.
DEFAULT_PREVIEW_BYTES = 50 * 1024

#: A line longer than this is reported; truncating it would silently destroy
#: the locator correspondence a consumer needs.
LONG_LINE_BYTES = 2000


@dataclass(frozen=True)
class StoredInputView:
    """What the host stored for one source version."""

    source_id: str
    source_version: str
    byte_length: int
    content_sha256: str
    complete: bool

    def __post_init__(self) -> None:
        if self.byte_length < 0:
            raise ValueError("STORED_BYTE_LENGTH_NEGATIVE")


@dataclass(frozen=True)
class DeliveredSpan:
    """One contiguous byte range actually handed to a consumer.

    The span carries its own artifact identity: a range without the source,
    version and digest it came from cannot be checked against anything.
    """

    offset: int
    length: int
    source_id: str
    source_version: str
    content_sha256: str
    finish: str = "stop"
    routing_metadata_only: bool = False

    @property
    def end(self) -> int:
        return self.offset + self.length


@dataclass(frozen=True)
class CoverageReport:
    """Disjoint coverage of a stored artifact by a set of delivered spans."""

    stored_byte_length: int
    covered_bytes: int
    merged_spans: tuple[tuple[int, int], ...] = ()
    missing_ranges: tuple[tuple[int, int], ...] = ()
    overlapping_byte_count: int = 0
    denials: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_full(self) -> bool:
        return not self.denials and self.covered_bytes == self.stored_byte_length


def coverage_report(
    stored: StoredInputView, delivered: Sequence[DeliveredSpan]
) -> CoverageReport:
    """Merge spans into disjoint coverage. Overlap never fills a gap."""

    denials: list[str] = []
    accepted: list[tuple[int, int]] = []
    raw_total = 0
    for index, span in enumerate(delivered):
        tag = f"span[{index}]"
        if span.source_id != stored.source_id:
            denials.append(f"{tag}:SPAN_SOURCE_ID_MISMATCH")
            continue
        if span.source_version != stored.source_version:
            denials.append(f"{tag}:SPAN_SOURCE_VERSION_MISMATCH")
            continue
        if span.content_sha256 != stored.content_sha256:
            denials.append(f"{tag}:SPAN_CONTENT_DIGEST_MISMATCH")
            continue
        if span.offset < 0 or span.length < 0:
            denials.append(f"{tag}:SPAN_RANGE_NEGATIVE")
            continue
        if span.end > stored.byte_length:
            denials.append(f"{tag}:SPAN_EXCEEDS_STORED")
            continue
        if span.routing_metadata_only:
            # Routing metadata is not content; it covers nothing.
            continue
        if span.length == 0:
            continue
        accepted.append((span.offset, span.end))
        raw_total += span.length

    merged: list[tuple[int, int]] = []
    for start, end in sorted(accepted):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    covered = sum(end - start for start, end in merged)
    missing: list[tuple[int, int]] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            missing.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < stored.byte_length:
        missing.append((cursor, stored.byte_length))

    return CoverageReport(
        stored_byte_length=stored.byte_length,
        covered_bytes=covered,
        merged_spans=tuple(merged),
        missing_ranges=tuple(missing),
        overlapping_byte_count=raw_total - covered,
        denials=tuple(denials),
    )


def utf8_boundary_violations(
    content: bytes, delivered: Sequence[DeliveredSpan]
) -> tuple[str, ...]:
    """Spans whose edges cut a UTF-8 character in half."""

    def is_continuation(position: int) -> bool:
        return 0 < position < len(content) and (content[position] & 0xC0) == 0x80

    bad: list[str] = []
    for index, span in enumerate(delivered):
        if span.routing_metadata_only or span.length <= 0:
            continue
        if is_continuation(span.offset):
            bad.append(f"span[{index}]:SPLIT_UTF8_AT_OFFSET")
        if is_continuation(span.end):
            bad.append(f"span[{index}]:SPLIT_UTF8_AT_END")
    return tuple(bad)


def assess_delivery(
    stored: StoredInputView,
    delivered: Sequence[DeliveredSpan],
    *,
    admitted_byte_length: int,
    policy: str,
    content: bytes | None = None,
) -> tuple[DeliveryStatus, str, CoverageReport]:
    """Distinguish stored input from delivered ranges; transport != full answer."""

    if isinstance(delivered, DeliveredSpan):  # defensive: a single span is a sequence of one
        delivered = (delivered,)
    report = coverage_report(stored, delivered)
    if report.denials:
        return "DELIVERY_DENIED", ";".join(report.denials), report
    if content is not None:
        violations = utf8_boundary_violations(content, delivered)
        if violations:
            return "DELIVERY_DENIED", ";".join(violations), report
    if admitted_byte_length < 0:
        return "DELIVERY_DENIED", "ADMITTED_BYTES_NEGATIVE", report
    if admitted_byte_length > stored.byte_length:
        return "DELIVERY_DENIED", "ADMITTED_BYTES_EXCEED_STORED", report

    content_spans = [s for s in delivered if not s.routing_metadata_only and s.length > 0]
    if not content_spans and delivered:
        return "REPORT_INCOMPLETE", "ROUTING_METADATA_ONLY_NO_CONTENT", report
    if not stored.complete:
        return "REPORT_INCOMPLETE", "STORED_MARKED_INCOMPLETE", report

    if policy == "FULL_REQUIRED":
        if report.missing_ranges:
            gaps = ",".join(f"{a}-{b}" for a, b in report.missing_ranges)
            return "REPORT_INCOMPLETE", f"COVERAGE_GAPS[{gaps}]", report
        if admitted_byte_length < stored.byte_length:
            return "REPORT_INCOMPLETE", "FULL_REQUIRED_ADMITTED_BYTES_SHORT", report
        if any(span.finish != "stop" for span in content_spans):
            return "REPORT_INCOMPLETE", "FULL_COVERAGE_WITH_TRUNCATED_FINISH", report
    return "REPORT_COMPLETE", "DELIVERED_COVERS_STORED_CONTRACT", report


def preview_bounds(
    content: bytes | str, *, max_preview_bytes: int = DEFAULT_PREVIEW_BYTES
) -> dict[str, Any]:
    """Bounded preview measured in bytes, with long lines reported not cut."""

    raw = content.encode("utf-8") if isinstance(content, str) else content
    cut = raw[:max_preview_bytes]
    # Never end a preview mid-character.
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    if cut and (cut[-1] & 0xE0) == 0xC0:
        cut = cut[:-1]

    lines = raw.split(b"\n")
    preview_end = len(cut)
    long_lines: list[int] = []
    offset = 0
    for index, line in enumerate(lines, 1):
        if len(line) > LONG_LINE_BYTES:
            line_end = offset + len(line)
            if offset >= preview_end or line_end <= preview_end:
                long_lines.append(index)
        offset += len(line) + 1
    return {
        "stored_bytes": len(raw),
        "preview_bytes": len(cut),
        "truncated": len(cut) < len(raw),
        "truncated_byte_range": [len(cut), len(raw)] if len(cut) < len(raw) else None,
        "long_line_numbers": long_lines,
        "long_lines_preserved_not_truncated": True,
        # A trailing marker is a claim about completeness, not evidence of it.
        "end_marker_present": raw.rstrip().endswith(b"[END]"),
        "end_marker_is_not_proof_of_completeness": True,
    }


def line_number_binding(
    artifact_version: str, reported_line: int, *, actual_version: str
) -> str:
    if artifact_version != actual_version:
        return "LINE_NUMBER_STALE_ARTIFACT_VERSION"
    if reported_line < 1:
        return "LINE_NUMBER_INVALID"
    return "LINE_NUMBER_BOUND_TO_ARTIFACT_VERSION"


def permission_may_not_become_unknown(explicit_permission: bool, output_unknown: bool) -> str:
    if explicit_permission and output_unknown:
        return "PERMISSION_ERASED_TO_UNKNOWN"
    return "OK"


def scoped_success_not_inherited(old_purpose_ok: bool, new_purpose: str, inherited: bool) -> str:
    if inherited and not old_purpose_ok:
        return "INHERITED_VALIDATION_WITHOUT_OLD_SCOPE"
    if new_purpose and old_purpose_ok and inherited:
        return "NEW_PURPOSE_CANNOT_INHERIT_OLD_VALIDATION"
    return "OK"


# -- output gate --------------------------------------------------------------


def assess_output_sections(
    sections: Mapping[str, str],
    *,
    required: Sequence[str],
    partial_finish: bool = False,
    metadata_only: bool = False,
) -> tuple[DeliveryStatus, str]:
    """Structural completeness of a report: required sections with real content.

    A heading alone does not prove the section was produced: a required
    section present but empty (or whitespace) is reported missing.  A known
    partial-finish or metadata-only flag overrides any apparent completeness.
    """

    missing = [name for name in required if not str(sections.get(name) or "").strip()]
    if missing:
        return "REPORT_INCOMPLETE", "MISSING_OR_EMPTY_SECTIONS[" + ",".join(missing) + "]"
    if metadata_only:
        return "REPORT_INCOMPLETE", "METADATA_ONLY_FLAG_SET"
    if partial_finish:
        return "REPORT_INCOMPLETE", "PARTIAL_FINISH_FLAG_SET"
    return "REPORT_COMPLETE", "ALL_REQUIRED_SECTIONS_NONEMPTY"


# -- typed source / claim correspondence --------------------------------------


@dataclass(frozen=True)
class DeclaredFact:
    """A declared SYNTHETIC fact with an explicit source locator."""

    claim_id: str
    quote: str
    source_id: str
    source_version: str
    byte_offset: int
    scope: str = "SYNTHETIC_WORLD_ONLY"


@dataclass(frozen=True)
class FactCheck:
    claim_id: str
    status: str
    detail: str
    observed_offset: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "LOCATOR_MATCHES_DECLARED_SOURCE_VERSION"


def check_declared_fact(
    fact: DeclaredFact,
    *,
    source_id: str,
    source_version: str,
    content: bytes,
) -> FactCheck:
    """Verify a declared synthetic quote sits at its declared locator.

    Positive structural check only.  It establishes that the quote exists at
    that byte offset in that source version — not that any conclusion drawn
    from it is warranted.
    """

    if fact.source_id != source_id:
        return FactCheck(fact.claim_id, "LOCATOR_SOURCE_ID_MISMATCH", f"{fact.source_id}!={source_id}")
    if fact.source_version != source_version:
        return FactCheck(
            fact.claim_id,
            "LOCATOR_SOURCE_VERSION_MISMATCH",
            f"{fact.source_version}!={source_version}",
        )
    needle = fact.quote.encode("utf-8")
    if not needle:
        return FactCheck(fact.claim_id, "LOCATOR_EMPTY_QUOTE", "quote is empty")
    if fact.byte_offset < 0 or fact.byte_offset + len(needle) > len(content):
        return FactCheck(fact.claim_id, "LOCATOR_OUT_OF_RANGE", f"offset={fact.byte_offset}")
    actual = content[fact.byte_offset : fact.byte_offset + len(needle)]
    if actual != needle:
        found = content.find(needle)
        return FactCheck(
            fact.claim_id,
            "LOCATOR_QUOTE_NOT_AT_OFFSET",
            "quote does not occur at the declared offset",
            observed_offset=found if found >= 0 else None,
        )
    return FactCheck(
        fact.claim_id,
        "LOCATOR_MATCHES_DECLARED_SOURCE_VERSION",
        f"scope={fact.scope}; structural correspondence only, not entailment",
        observed_offset=fact.byte_offset,
    )


def consumed_source_check(
    *,
    stored: StoredInputView,
    delivered: Sequence[DeliveredSpan],
    admitted_byte_length: int,
    policy: str,
    content: bytes | None = None,
) -> dict[str, Any]:
    """Transport verdict in the shape the M5 runner records per consumed source."""

    status, reason, report = assess_delivery(
        stored,
        delivered,
        admitted_byte_length=admitted_byte_length,
        policy=policy,
        content=content,
    )
    return {
        "source_id": stored.source_id,
        "source_version": stored.source_version,
        "content_sha256": stored.content_sha256,
        "policy": policy,
        "status": status,
        "reason": reason,
        "stored_byte_length": report.stored_byte_length,
        "covered_bytes": report.covered_bytes,
        "missing_ranges": [list(item) for item in report.missing_ranges],
        "overlapping_byte_count": report.overlapping_byte_count,
        "structural_only": True,
    }


__all__ = [
    "DEFAULT_PREVIEW_BYTES",
    "LONG_LINE_BYTES",
    "CoverageReport",
    "DeclaredFact",
    "DeliveredSpan",
    "DeliveryStatus",
    "FactCheck",
    "StoredInputView",
    "assess_delivery",
    "assess_output_sections",
    "check_declared_fact",
    "consumed_source_check",
    "coverage_report",
    "line_number_binding",
    "permission_may_not_become_unknown",
    "preview_bounds",
    "scoped_success_not_inherited",
    "utf8_boundary_violations",
]
