# S-IMPL-001 RESULT

## Repository and delivery

- **REPO:** `https://github.com/Stimurid/SESHAT.git`
- **BASE_SHA:** `39cb6b6833c622442cde1e6720c501afd3752329`
- **HEAD_SHA (implementation commit):** `12803b6682e3121bc4e55ad49cc383cd4101aba0`
- **BRANCH:** `codex/s1-source-access`
- **PR:** [#5 — S-IMPL-001: enforce truthful source access](https://github.com/Stimurid/SESHAT/pull/5)

## Files modified

- `src/seshat/contracts.py`
- `src/seshat/runtime.py`
- `src/seshat/adapters/base.py`
- `src/seshat/adapters/records.py`
- `src/seshat/adapters/testing.py`
- `src/seshat/__init__.py`
- `profiles/sechenovka_authorabstract/operations.py`
- `tests/test_runtime.py`
- `tests/test_source_access.py`
- `docs/ADR_0001_TRUTHFUL_SOURCE_ACCESS.md`
- `docs/S_IMPL_001_RESULT.md`
- `src/seshat/blackboard.py` (lint-only removal of an unused import and modernized
  `Iterable` import; no behavior change)

## API and policy choices

- `SourceCarrier` remains source identity metadata and now pins expected byte length and SHA-256.
- `SourceContentProvider` is a separate adapter port returning authorized, versioned bytes.
- `SourceAccess` is the only operation-facing read interface. It exposes full reads or bounded,
  versioned addresses according to `RawAccessPolicy`.
- `FULL_REQUIRED` validates every declared carrier before provider invocation.
- `DRILLBACK` permits exact `byte_range` or UTF-8 `char_range` reads and does not claim whole-source
  inspection.
- `NEVER` denies every raw request while allowing observation-only execution.
- Runtime-authored `SourceAccessManifest` receipts contain identity/integrity/status information but
  no source bytes. Failures expose the attempt manifest through `EvidenceAccessError`.

See [ADR 0001](ADR_0001_TRUTHFUL_SOURCE_ACCESS.md) for the detailed contract.

## Tests and commands

- Baseline before code: `python -m pytest -q` → `13 passed`.
- Red test against old behavior:
  `python -m pytest -q tests/test_runtime.py::test_full_required_rejects_metadata_only_carrier`
  → failed because no exception was raised.
- Final local suite: `python -m pytest -q` → `27 passed`.
- Static checks: `python -m ruff check .` → all checks passed.
- Whitespace/error check: `git diff --check` → passed.
- CI: [run 37998841484](https://github.com/Stimurid/SESHAT/actions/runs/37998841484) →
  `success` (`test`, Python 3.12, 27 tests).

The tests cover metadata-only access, valid complete reads, multi-carrier partial availability,
version/digest drift, snippet-only content, bounded DRILLBACK, invalid ranges/carriers, NEVER,
unsupported media, non-sovereign observations, repeated stable reads, unauthorized content, and
read failures before blackboard persistence.

## Source access matrix

| Policy | Whole source | Bounded versioned span | Result evidence |
|---|---|---|---|
| `FULL_REQUIRED` | Required and preflight-verified for all carriers | Allowed after the same validation | Full-read receipts; `all_declared_sources_verified=true` |
| `DRILLBACK` | Denied | Allowed for exact in-range address | Range receipt; no whole-source claim |
| `NEVER` | Denied | Denied | Empty manifest if unused; typed denial receipt on attempt |

## Provenance/read receipt witness

`tests/test_source_access.py::test_full_required_validates_and_exposes_complete_content` proves that
the deterministic provider reads actual source bytes and that the returned `DerivedObject` contains
the source version, independently validated SHA-256/length, read status, and full-verification flag.
`test_drillback_returns_exact_versioned_bounded_span_and_receipt` proves the addressed range path.
Receipts never include source content.

## Known limitations

- Receipts are structured on returned objects and failures but are not durably persisted outside the
  in-memory blackboard/runtime.
- The record adapter is a deterministic in-memory implementation, not a live filesystem/Drive/LitOps
  acquisition adapter.
- Supported media are UTF-8 text/Markdown/JSON and opaque bytes. PDF/OCR readers are intentionally
  unsupported.
- Reads currently materialize complete bytes in memory; streaming and very-large-source handling are
  future adapter/runtime work.
- Byte availability/integrity does not prove prompt coverage, methodological correctness, semantic
  review, or acceptance. S2/S3 are not claimed.

## Rollback

Revert the delivery commit(s). No schema migration, external store mutation, or Drive write occurred.
Rollback restores metadata-only behavior and therefore must be treated as removal of the S1 safety
gate, not as an equivalent implementation.

## Next owned act or blocker

PR #5 is ready for Hephaestus/user review. S2/S3 remain separate work and were not started. The only
remaining external action is review/merge; there is no implementation blocker in S1.
