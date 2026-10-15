# F07 carrier-order and temporal metadata repair — 2026-10-15

Status: SOURCE_EDITED / ENGINEERED_UNREVIEWED. Tests NOT RUN by this worker.
SECURITY_ACCEPTED=NO; METHOD_SCIENCE_ACCEPTED=NO; RELEASE=NO.

## Exact entry and authority

- WORKSPACE_MODE: OTHER_CHECKOUT, explicitly assigned isolated Windows Hub worktree.
- WORKDIR_ABSOLUTE: `C:\AI\llm\aiye-executor\worktrees\jx-b5531e6afa95`.
- ORIGIN_URL: `https://github.com/Stimurid/SESHAT.git`.
- CURRENT_BRANCH: `aiye/exec-b5531e6afa95`; initial DIRTY_STATUS: clean.
- BASE_SHA / HEAD_SHA: `19268cecdf473ee8a32e6cd9d1fb36444ed3e667`.
- Parent tree: `d31ada792b7418ba01763af8be0b85a708e4496a`.
- CURRENT_TASK: [#56](https://github.com/Stimurid/SESHAT/issues/56),
  `SESHAT-F07-P1-CARRIER-ORDER-TEMPORAL-20261015`.
- CURRENT_PR: none created; publication is outside this assignment.
- NEXT_GATE: Hub snapshot, independent source review by assigned reviewer
  `jx-edce2aaf6daa`, fresh isolated exact-SHA/tree suite and both external attacks.
- BLOCKERS: those review/test gates are pending; private v4 join/14-oracle evaluation
  is not authorized or mounted for this worker.

The explicit job passport supersedes the old default `C:\projects\seshat`
checkout instruction. No writes outside this worktree, Git metadata writes,
candidate Python execution, tests, Ruff, Docker, host changes or publication
were performed. The Hub is responsible for snapshot commit after delivery.

Read sources: machine entry map, portable routing entry and routing guide;
repo rules, coordination, implementation plan and charter; both previous
reviewer stdout files (`jx-10e69f490455`, `jx-e85abd92bf80`); external carrier-order
harness and its receipt. The receipt independently records exit 7 against the
parent tree, not against these changes. The task's 145-pass parent suite is
historical evidence only. The v0.12 document was fetched through the Drive
connector; GitHub #56/#6 and latest comments were fetched read-only through the
GitHub connector after web access failed. No actor/runtime mount was invoked or
inferred; the supplied SESHAT routing result does not establish a live runtime.

Intake dispositions:

- VERIFY_WITH_TEST: [executed carrier oracle and this dispatch](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6193503486).
  Regression: `test_denied_carrier_permutations_and_conflicting_duplicates_are_invisible`.
- VERIFY_WITH_TEST: [temporal audit amendment](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6192543183).
  Regression: `tests/test_corpus_temporal.py`. Reported private counts were not
  recomputed here and no private rows were imported.
- NOT_APPLICABLE to this bounded core repair: the latest Inbox #6 Wave Witness
  repair stream; no edits to that repository or runtime.

## Security change and boundary

`corpus_host.py` first checks object entitlement, then scans recognizable carrier
IDs in both the carrier list and research-object references. It does not validate,
serialize or fingerprint malformed neighbours during this routing phase. Any
known denied carrier excludes the whole row before StudyRecord validation or
duplicate conflict detection. Only admitted rows participate in public digests.
Malformed visible rows without a known denial still raise `invalid study pin`.

SourcePackage defers row shape validation until selection. A non-list records
container cannot be classified safely and fails with `HOST_INPUT_UNAVAILABLE`.
An unrouteable individual row raises `invalid study pin`; it is not silently
discarded. The JSON-line transport still returns `SELECTION_UNAVAILABLE` for
selection errors. Errors contain no IDs, paths, file hashes or private versions.
Changing bytes without an independently installed pin still fails closed.

This is conditional noninterference for routable denied rows, fixed visible
data/schema/request and visible grants. The pinned source and grants are
owner-controlled, NOT untrusted reader input. A compromised owner, invalid JSON,
unrouteable source container, timing/resource side channels or a changed public
schema are outside this guarantee. There is no cryptographic multi-tenant
isolation claim. Public receipts remain PROVISIONAL / PENDING_HOST_ATTESTATION /
UNVERIFIED_CURRENTNESS. Package integrity is not original-source science.

Tests compare the entire receipt or full sanitized error, with carrier
permutations, null/list/string/object/number malformed entries, a duplicate of
an admitted object, conflicting hidden duplicates, reversed row order, hidden
carrier hashes/versions, source versions and private rights epochs. Existing
seal_selection callback rejection tests are retained unchanged.

## Temporal contract

`TemporalProvenance` retains the literal source field, exact source value,
DATE versus YEAR precision, per-study SHA-256 and per-study source version.
Reserved temporal EvidenceFields require that provenance and validate both
their name and value against it. A record rejects contradictory provenance for
the same temporal source. Generic evidenced metadata remains available to other
hosts; scalar values now reject bool/float coercion. Absent optional provenance
is omitted from canonical payloads, preserving old non-temporal digest shape.

The v4 adapter's `cohort_year` is the existing intake cohort/index label
(the audit calls this `cohort_year_defense_or_fallback`). It is not renamed or
reinterpreted as a defense year. No date is inferred from it.

Optional `pinned_temporal_metadata(raw, expected_sha256=..., expected_object_id=...,
source_version=...)` verifies a single-study JSON envelope and produces
HostTemporalMetadata for the adapter's `temporal_metadata` argument. Envelope:

```json
{"study_id":"invented-only","defended_on":"2026-01-17","defense_date":"2026-02-18","abstract_published":2024}
```

The host must independently authorize the master/intake join and field access,
verify that identity against the master, and pin the per-study envelope outside
reader control. This optional channel does not fetch a master or accept a reader
grant. A constructed model or matching hash is not independent authorization.
Keep whole-master hashes and epochs private: the supplied source_version and
envelope SHA must concern only this admitted study. No actual master binding is
asserted by this patch.

Supported fields are `defended_on`, `defense_date`, `abstract_published` and
their separate `_year` projections. Integer years stay integers; strict
YYYY-MM-DD dates retain the exact date and calendar validity. Null/absent values
are missing metadata: a declared selector yields UNKNOWN_METADATA; an undeclared
field yields NOT_EVALUABLE. Empty/invalid dates fail validation. Similar keys on
arbitrary intake rows are ignored without the separate authorized channel.
There is no degree-awarded assertion or defense-event verification.

R01–R09 input contracts retain the actual predicate and explicitly declare
EXPLICIT_FIELDS_ONLY_NO_COHORT_DEFENSE_FALLBACK. This is input wiring, not nine
implemented report bodies. Tests preserve mismatching dates even within one
year, different publication years, cohort=2025/defended_on=2026 and
cohort=2026/unknown defended_on.

## Changed paths and validation handoff

- `src/seshat/corpus_host.py`: two-phase admission and sanitized unknown shape.
- `src/seshat/corpus.py`: typed temporal provenance and consistency validation.
- `src/seshat/corpus_adapters.py`: optional pinned host temporal channel.
- `src/seshat/corpus_report_input.py`: explicit temporal semantics.
- `tests/test_corpus_host.py`: adversarial security regressions.
- `tests/test_corpus_temporal.py`: invented temporal and R01–R09 regressions.
- This receipt.

Executed here: read-only Git identity/status/diff commands, file reads, connector
reads, source/test edits and `git diff --check` (exit 0; CRLF notices only).
No pytest/Ruff or candidate imports were executed. No new exact-tree test result
or independent source verdict is claimed. The coordinator must record the new
snapshot SHA/tree and run, in the existing isolated no-network/no-credentials
runner, the full `python -m pytest -q -o pythonpath=src`, Ruff, and unchanged
external `F07_ADVERSARIAL_DENIED_CARRIER_ORDER_20261015.py` and
`F07_ADVERSARIAL_SEAL_NONINTERFERENCE_20261015.py`. The parent receipt/image
does not certify this new tree.

Rollback: discard this snapshot's seven-file patch through the authorized Hub
workflow; retain the parent FAIL receipts. Do not deploy the vulnerable parent
as an accepted fallback. No release, merge, PR or Drive mirror write occurred.
REAL_V4_14_ORACLE_RUN=NOT_RUN; four owner identity-QA flags remain unresolved.

## OPEN QUESTIONS

- Has the new exact tree passed independent review and isolated tests? Default:
  NO/UNVERIFIED until coordinator receipts arrive; this worker cannot self-certify.
- Which original master mapping and date format will the host authorize? Default:
  none mounted; accept only pinned per-study explicit ISO dates/integer years.
- Is the per-study temporal join independently authorized and source-verified?
  Default: not established here; adapter availability does not establish it.
- Does missing defended_on mean no defense occurred? Default: no; UNKNOWN_METADATA.
- Are private 14-oracle results or the four identity flags resolved? Default: no.
