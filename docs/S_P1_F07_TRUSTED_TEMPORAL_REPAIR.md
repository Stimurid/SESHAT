# F07 owner temporal source repair — implementation receipt

Status: ENGINEERED_UNREVIEWED / EXECUTION_PENDING. No release or scientific acceptance.

## Workspace and authority

- WORKSPACE_MODE: isolated Hub worktree (explicit job scope overrides old canonical-folder rule).
- WORKDIR_ABSOLUTE: `C:\AI\llm\aiye-executor\worktrees\jx-3585a6ff0736`.
- ORIGIN_URL: `https://github.com/Stimurid/SESHAT.git`.
- CURRENT_BRANCH: `aiye/exec-3585a6ff0736`.
- BASE_SHA / initial HEAD_SHA: `b1183b5f6ff5fde6d0f75ebe52340857072fd0cf`.
- Parent tree: `e4a8af0b4f52d30909cdd13845a746d73a19e9f6`; initial DIRTY_STATUS: clean.
- CURRENT_TASK: issue #56, SESHAT-F07-OWNER-PINNED-TEMPORAL-20261015.
- CURRENT_PR: none created; publication excluded from this job.
- NEXT_GATE: Hub snapshot, independent restricted-container tests and independent source review.
- BLOCKERS: no authorized test runner attached to this worker; external temporal harness has
  an acceptance-assertion defect described below. Production binding not installed.
- DRIVE_SYNC: MIRROR_PENDING; no writes attempted.

Read local machine AGENTS, portable entry and routing guide, targeted SESHAT routing rows,
repository AGENTS, coordination, implementation plan, charter and bootstrap instructions.
Routing identifies SESHAT separately from its consumers; runtime remains UNKNOWN.
No actor invocation or Proteus mutations. The Proteus alias index inspection did not find
a SESHAT entry; no Python resolver was executed in this bounded worker.
Read current issue #56 and Inbox #6 comments, including
[the explicit dispatch](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6193977164).
Fetched the full [v0.12 goal](https://docs.google.com/document/d/1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k/edit)
(modified 2026-10-07T14:36:53.868Z). No methodological changes or donor import.

## Change and trust boundary

The generic v4 adapter now rejects every non-None `temporal_metadata` with
`UNTRUSTED_TEMPORAL_METADATA`. Manually constructed models, deserialized models
and data returned by `pinned_temporal_metadata` are equally untrusted. That
function remains a data decoder for compatibility, not an admission credential.
Intake date-like keys remain ignored. With no owner integration, declared dates
remain UNKNOWN_METADATA; undeclared fields remain NOT_EVALUABLE.

The existing owner process accepts an optional **out-of-band** `HostConfiguration.temporal`
FilePin (absolute path plus independently approved SHA). Its exact bytes are read and hashed
on bootstrap and on every selection, including cache hits, together with primary and rights
bytes. The file is opened for reading only. The deployment owner must mount the files and
configuration read-only to the noncredentialed worker and prevent clients from supplying
argv, environment, configuration, Python code or writable mounts. This patch does not alter
OS permissions, create a production launcher, authenticate a network connection or claim
that a public Python constructor authenticates anyone. `HostRuntime`, `install`, `_load`
and `_attach_owner_temporal` are private control-plane operations, not request APIs.
The public JSON-line schema accepts only a selector; extra control-plane fields fail closed.
Arbitrary Python execution inside the owner process remains outside the security model.

Owner temporal JSON format (synthetic illustration; no private source rows):

```json
{
  "host_id": "synthetic-host",
  "records": [{
    "study_id": "synthetic-study",
    "record_version": "v4",
    "carriers": [{
      "carrier_id": "synthetic-abstract",
      "source_identity": "v4:abstract",
      "version": "v4",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }],
    "defended_on": "2026-02-18",
    "defense_date": "2026-02-19",
    "abstract_published": 2025
  }]
}
```

The separately pinned grant adds `temporal_fields`, e.g.
`{"synthetic-study": ["defended_on", "defense_date"]}`. Absent grants deny all date fields.
Object and **all** carrier rights are checked before date validation. The source study ID,
record version and complete sorted carrier bindings (ID, source identity, version, SHA)
must equal the admitted primary record. Duplicate matching temporal rows are blocked.
Missing matching source rows or missing/null values stay unknown. Denied rows and denied
sibling date fields are not semantically validated and cannot change public evidence.
Temporal fields from the primary package are discarded before validation, so a forged
provenance label cannot bypass the independent temporal file and field rights.

The owner must approve this metadata source and its extraction from the original master;
the implemented join verifies identity/carrier binding between pinned packages, not the
truth of a council event or correctness of an independently prepared master export.
The real master was not read by this worker. No PDF content is read by the new code.

Private cache epochs include the complete temporal file SHA, primary SHA and rights SHA/epoch.
Public provenance instead hashes a canonical **single study/field** envelope containing host,
study/version/carrier binding, source field and its value. `source_version=content:<digest>`.
The public SHA is a derived canonical envelope digest, not the whole file's byte digest;
the owner configuration retains the actual approved file pin. No global private epoch,
file path or denied sibling value enters it. Hidden-only authorized rotations rebuild the
private cache while preserving byte-identical public results. Changed files without owner
pin installation produce HOST_INPUT_UNAVAILABLE, even when the request supplies a new SHA.

## Evidence and validation

ACK_NEEDED_NOW / VERIFY_WITH_TEST, owner issue #56:

- Parent independent receipt `F07_AORUS_FIX_NEW_SHA_EXACT_CONTAINER_RESULTS_20261015.json`:
  206 tests passed, one warning, both external hidden-world P1 attacks EXIT0 on **parent only**.
- Parent negative receipt `F07_AORUS_ADVERSARIAL_P1_NEW_SOURCE_20261015.json`:
  forged typed temporal provenance accepted, EXIT7 / FAIL_AUTHORITY on parent.
- Both receipts were read from `C:\AI\llm\aiye-executor\handoffs\SESHAT-20261012\G0_20261013`.
- Existing temporal test cases retained, with fixtures migrated off the now-forbidden direct
  adapter input. Their pure semantic helper is explicitly not an authorization test.
- Added owner-file tests: manual `ffff` model, serialized model, self-hashed raw envelope,
  missing/wrong file pin, swapped study, carrier ID/SHA/source identity/version mismatch,
  record version mismatch, duplicate source rows, explicit grants, revocation, stale cache,
  invalid dates, denied fields/rows/carriers, hidden-only mutations, primary-label laundering,
  16 synthetic unknown dates, no degree assertion, JSON-line and separate-process rejection.

Executed here: read-only Git inspection, file/source/receipt inspection, source/test edits,
SHA-256 file hashing and `git diff --check` (passed). No Python, pytest, Ruff, Docker,
production access, installation, Git metadata writes, PR, push or merge executed.
No private 186-row v4 run, 14 real oracles, or next-SHA pass is claimed.

Coordinator must run on the Hub's next exact SHA/tree in the independently restricted runner:

1. Full `python -m pytest -q -o pythonpath=src` (all prior semantic cases plus new cases).
2. `ruff check .` and `git diff --check`.
3. Both unchanged external carrier-denial/order and malicious-seal harnesses.
4. External temporal attack, with the harness issue below handled explicitly by its owner.

### External harness cannot currently produce a successful EXIT0

Original `F07_EXTERNAL_UNPINNED_TEMPORAL_PROVENANCE_20261015.py` SHA-256:
`4c7d6ab06282b4bcc92e1c6ed0d9c415b6c70f2907e9768d053060f71b75c378`.
The original bytes were read and remain untouched. The script calls the adapter without
catching rejection, then unconditionally asserts `defended == 2026`, then exits 7 when
that assertion is true. A safe rejection exits nonzero before its verdict; omission of
the invented date fails its assertion. Consequently, ordinary execution of the same
bytes cannot both reject this attack and EXIT0. Do not weaken the product to satisfy it.
The independent harness owner must retain the original exploit receipt and add an
acceptance wrapper/test that treats the explicit rejection (or no date) as PASS and
any admitted forged date as FAIL. The new regression test asserts this rejection.
This worker does not certify the external attack as passed.

## Rollback and remaining limits

Owner deployment can omit `temporal` and all temporal grants to keep all dates unknown.
Do not restore the old adapter input as a rollback: it restores the demonstrated defect.
A code rollback, if required, belongs to the coordinator on the Hub snapshot, with the
temporal feature disabled. The original suite's green receipt is not security acceptance.

## OPEN QUESTIONS

- Who supplies and approves the real master export, join and field rights? Default used:
  only the owner control plane; no real integration, private source or rights changed.
- Can the external harness owner correct the unconditional acceptance assertion?
  Default used: preserve original bytes, report the contradiction, require independent
  corrected negative acceptance; no fabricated EXIT0.
- Are the next snapshot's tests and source review green? Default used: NOT_EXECUTED /
  ENGINEERED_UNREVIEWED until coordinator evidence arrives; no release or science claim.
