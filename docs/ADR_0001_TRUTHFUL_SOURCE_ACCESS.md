# ADR 0001 — Truthful source access

**Status:** Accepted for S-IMPL-001  
**Scope:** runtime source access only; no semantic method implementation

## Decision

SESHAT separates source identity metadata (`SourceCarrier`) from executable content access
(`SourceContentProvider` and a policy-scoped `SourceAccess` session). An operation provider receives
the session alongside observations and prior derived state. Observations remain evidence addresses;
they are never accepted as substitutes for source bytes.

`SourceCarrier` pins the expected source version, media type, SHA-256, and byte length.
`SourceContentProvider` returns authorized bytes plus its own version, media type, completeness,
SHA-256, and byte length declarations. Before exposing content, the runtime independently computes
the byte length and SHA-256 and compares all declarations. No normalization is performed, so the
hash lineage is over the exact returned bytes.

The runtime supports `text/plain`, `text/markdown`, `application/json`, and opaque
`application/octet-stream` bytes. `char_range` is UTF-8-only; `byte_range` is byte-addressed. Other
media and address types fail explicitly. PDF/OCR extraction is not claimed by this change.

## Policy semantics

- `FULL_REQUIRED` reads and validates every carrier declared by the `ResearchObject` before the
  operation provider runs. Missing metadata/content, unauthorized or partial content, source drift,
  unsupported media, and integrity mismatch fail closed. Validated content is cached for stable,
  repeatable reads during the operation.
- `DRILLBACK` permits only explicit, version-pinned, bounded addresses. It rejects undeclared
  carriers, absent/wrong versions, invalid bounds, and unsupported address/media combinations.
  It does not assert that every declared source was inspected.
- `NEVER` supplies a denial-only session. Observation-only operations can run, while any whole or
  bounded raw read raises `POLICY_DENIED`.

Every successful result receives a runtime-authored `SourceAccessManifest`. Receipts identify the
carrier, version, read kind, full-source digest/length, returned length, address, status, and typed
error when applicable; they never contain raw source bytes. Failed reads attach the manifest to the
raised `EvidenceAccessError`. A failure occurs before any `DerivedObject` is written to the
blackboard.

## Compatibility and limits

The existing `SourceProvider` metadata/observation protocol remains intact. Content access is an
additional protocol and `RecordSourceProvider` gains an optional in-memory content mapping for
tests and read-only host adapters. `OperationProvider.execute` gains the `source_access` argument;
providers must consciously adopt the new contract instead of silently retaining the metadata-only
false positive.

This slice does not provide durable receipt storage beyond the returned `DerivedObject` or raised
exception, streaming reads, remote acquisition, PDF/OCR parsing, prompt-size/coverage guarantees,
semantic method bodies, or scientific acceptance. A verified full read proves byte availability and
integrity, not methodological completeness.

## Rollback

Revert the S-IMPL-001 commit/PR. No data migration or external store mutation is required. Reverting
also restores the old metadata-only behavior, so it must not be treated as a safe long-term access
policy.
