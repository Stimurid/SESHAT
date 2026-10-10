# S-IMPL-002B RESULT

## Status

**IMPLEMENTED IN THE SANDBOXED WORKING TREE; LOCAL PYTHON TEST EXECUTION IS
UNAVAILABLE; TRUSTED-HOST DRAFT PUBLICATION AND ISOLATED PR CI ARE PENDING.
TESTED/ACCEPTED ARE NOT CLAIMED.**

This receipt covers the bounded, domain-neutral reconciliation controller in
[S-IMPL-002B / issue #17](https://github.com/Stimurid/SESHAT/issues/17). It does not
claim execution of the historical Object or Agent-0 method bodies, semantic review,
durable S6 persistence, or scientific acceptance.

## Admission and baseline

- **WORKSPACE_MODE:** `WINDOWS_LOCAL`
- **WORKDIR_ABSOLUTE:** `C:\projects\seshat`
- **ORIGIN_URL:** `https://github.com/Stimurid/SESHAT.git`
- **BRANCH:** `codex/s2b-bounded-reconciliation`
- **BASE_SHA / INITIAL_HEAD_SHA:** `041ea2e8c69a4fb9d6a640dee04aa52833e47575`
- **INITIAL_DIRTY_STATUS:** clean
- **CURRENT_TASK:** S-IMPL-002B / issue #17
- **CURRENT_PR:** none at implementation time; trusted publisher owns draft creation
- **NEXT_GATE:** exact-path publication, isolated PR CI, and independent code review
- **BLOCKERS:** no Python/Ruff executable is visible in the managed worker shell

The SHA-bound dispatcher receipt records:

- predecessor PR #16 manually merged as
  `ed3400ca184cc3cf2100035936dcca2774d7893a`;
- independently reviewed PR #16 head
  `c72e41fc4e51658340b55c646cbdbd4ebb44e658`;
- accepted operations PR #18 included in current main;
- current main and task base
  `041ea2e8c69a4fb9d6a640dee04aa52833e47575`;
- issue #17 body SHA-256
  `541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8`;
- exact allowed paths equal to the three changed paths below.

The local dispatcher had already verified the predecessor acceptance token, merge,
main CI, issue label/body pin, clean worktree, and reviewed runtime bundle before it
created this branch and job. A later watchdog wrapper error is an operational monitor
state, not authority to weaken or repeat the admission decision.

## Changed paths

- `src/seshat/reconciliation.py`
- `tests/test_reconciliation.py`
- `docs/S_IMPL_002B_RESULT.md`

No existing S1/S2A source, donor runtime, profile method body, workflow, private source,
or external store was changed.

## Standing inbox / archaeological intake

The source-pinned Quinta and Socrates/Tinkuy returns were re-read as targeted negative
evidence, not as permission for donor import:

- **Quinta PR #4 — `ARCHIVE_ONLY` for this slice:** bounded run/fingerprint lessons are
  represented by duplicate/oscillation tests, but no Quinta runtime, fitness metric, or
  ontology was copied.
- **Socrates/Tinkuy PR #7 — `VERIFY_WITH_TEST`:** original-source version pinning,
  preserved alternatives, APORIA, bounded reflection, and proposal/admission separation
  map to S2B-T02, T04, T06, T07, and T08. The fixed Fabric chain and marker cutter are
  not promoted to a universal method.
- **Issue #8 — `NEXT_SLICE` plus regression guards now:** the deferred donor regression
  backlog does not block this isolated controller; preservation of rivals and invalidated
  history is covered now.
- **Issue #9 — `NOT_APPLICABLE` to donor import:** no Fabric coverage/no-loss claim is
  made. Existing S1 manifests remain the source-access boundary.
- **Issue #10 — `ACK_NEEDED_NOW` / `VERIFY_WITH_TEST`:** arbitrary strings and caller
  booleans are not authority. Extra proposal fields and executor-origin acceptance are
  rejected; source/candidate versions are checked before persistence.
- **Issue #11 — `VERIFY_WITH_TEST`:** source-change, cancellation/stale-state, proposal,
  and dependent-history laws inform the drift and history cases; the original Bottom-Up
  runtime and its bounded-note consolidator are not imported.

These classifications affect issue #17 / the eventual S2B PR only. No archaeological
return is treated as scientific-method acceptance.

## Engineering contract

### Typed bounded controller

`ReconciliationBudget` bounds rounds and operation calls. The controller stops with a
typed `RunOutcome` and `StopReason`; it has explicit gates for maximum budgets,
unchanged/duplicate proposals, unavailable or unsupported providers, provider errors,
source access failure, source drift, candidate drift, invalid proposals, strategy
failure, and acceptance laundering.

The controller admits exactly two distinct operations whose `dependency_ids` declare
the reciprocal relation. `AlternatingPairStrategy` is a separate strategy object; a
host may supply another bounded `NextOperationStrategy` without adding domain method
semantics to the controller. This is not a universal cyclic DAG or a compulsory
`cut -> derive -> analyze` pipeline.

### Versioned proposals and evidence

Every successful attempt records:

- operation ID, attempt and round number;
- versioned input `SourceRef` and `CandidateRef` values;
- versioned output `ProposalRef` and candidate ref;
- provider-declared typed constraints and mismatches;
- provenance and causal links;
- the S1 `SourceAccessManifest` without raw source content;
- unchanged/duplicate detection.

`FULL_REQUIRED` access is still enforced by the existing S1 runtime. The controller
pins the research-object version and verified source IDs/versions/digests on the first
attempt and blocks a later mismatch before the candidate is persisted. It compares the
runtime candidate snapshot before and after provider execution and between attempts.
Provider input comes only from `Blackboard.candidate_state()`, so `STALE`, `REJECTED`,
`CONTESTED`, and historical `ACCEPTED` objects are not active prior candidates.
If source/access/candidate drift blocks a later attempt, candidates already emitted by
that run are explicitly quarantined to `STALE` through a recorded guard dependency;
their history remains addressable and the ledger lists the quarantined refs.

### Outcome and authority separation

- `CONVERGED` requires a complete pair of non-empty, provider-declared compatible
  constraints with no declared mismatch. A provider's `claims_convergence` field is
  retained as a statement but is not the decision rule.
- `APORIA` requires contradiction to persist through the configured minimum rounds.
  The first-class `Aporia` references every attempted proposal plus the latest
  constraint and mismatch IDs.
- `EXHAUSTED` preserves the trace for duplicate, unchanged, round-budget, or call-budget
  stops.
- `BLOCKED` distinguishes missing capability, access/drift, invalid proposal, provider
  error, strategy failure, and attempted acceptance laundering.

Executor output may only be `WORKING` or `PROPOSED`. A provider-origin `ACCEPTED`,
`CONTESTED`, `REJECTED`, or `STALE` value is rejected before blackboard persistence.
`ReconciliationProposal` forbids extra fields, so caller-supplied consent-like values
such as `human_explicit=true` are not an acceptance channel. No acceptance workflow was
added.

The controller never calls `Blackboard.latest()` and never forces a last-write winner.
Competing candidates, isolated alternatives, stale dependents, proposal history, and
explicit causal references remain addressable.

## Test coverage added

`tests/test_reconciliation.py` contains deterministic synthetic coverage for:

1. **S2B-T01:** compatible typed constraints converge with a two-attempt trace and no
   automatic `ACCEPTED` state;
2. **S2B-T02:** persistent reciprocal contradiction yields `APORIA` with distinct,
   versioned proposals;
3. **S2B-T03:** A/B/A oscillation stops as duplicate-candidate `EXHAUSTED` within the
   call budget;
4. **S2B-T04:** source version/hash drift and candidate-state drift both stop as typed
   `BLOCKED` without stale reuse;
5. **S2B-T05:** a missing provider and unavailable full source stop without a fake
   result;
6. **S2B-T06:** forged `ACCEPTED` and an extra `human_explicit` field are rejected before
   persistence;
7. **S2B-T07:** competing candidates remain visible; no last-write selection occurs;
8. **S2B-T08:** isolated alternatives and invalidated dependents remain in explicit
   history;
9. provider exceptions produce a typed, sanitized receipt without leaking the original
   exception detail;
10. immediately unchanged candidates stop after the complete reciprocal round.

The full existing S1 and S2A suite remains selected by the repository-wide pytest
configuration. No tests were weakened or removed.

## Verification

### RED order

`tests/test_reconciliation.py` was created before
`src/seshat/reconciliation.py`. The required import and controller API did not exist at
that point. An executable RED result is not claimed because neither `python`, `py`,
`uv`, nor Ruff is available in this managed shell.

### Commands

Required final commands:

```text
python -m pytest -q
python -m ruff check .
git diff --check
```

Results at sandbox handoff:

- `python -m pytest -q` — **NOT EXECUTED LOCALLY**: no accessible interpreter;
- `python -m ruff check .` — **NOT EXECUTED LOCALLY**: no accessible interpreter/Ruff;
- `git diff --check` — **PASS** for tracked deltas;
- `git diff --no-index --check NUL <new-file>` for each of the three new files —
  **PASS** (exit status denotes a new-file diff; no whitespace diagnostics; LF/CRLF
  conversion warnings only);
- GitHub Actions — **PENDING** trusted draft publication.

The trusted host policy explicitly prevents credential-bearing publication code from
executing unreviewed Codex-produced Python. `publish.ps1` must validate the exact dirty
path set, scan and publish the draft; `.github/workflows/ci.yml` must then run pytest and
Ruff in isolated GitHub Actions. Until the final PR head is green, this result is not
`TESTED`.

## Replay and persistence boundary

`ReconciliationLedger` is an inspectable, serializable synthetic run receipt containing
the budget, inputs, outputs, constraints, mismatches, manifests, causal links, stop
reason, and optional `Aporia`. It is explicitly marked `durable=false` and
`persistence="in-memory"`. S2B does not add a database, daemon, tamper-evident event
store, or restart recovery. Durable execution receipts remain S6 work.

## Known limits

- Constraint meaning and incompatibility are provider-declared; the controller does not
  invent domain metrics or interpret Sechenovka methodology.
- Compatibility is structural and explicit. Undeclared semantic contradiction cannot be
  inferred by this domain-neutral slice.
- The included strategy alternates a pair. It is not a general cyclic-DAG scheduler.
- Blackboard and ledger storage remain in memory.
- No authorized acceptance actor/action is implemented.
- No original Object/Agent-0 method body, real patient/authorabstract data, donor runtime,
  production daemon, or paid model call is included.
- Passing engineering CI cannot establish scientific or methodological validity.

## Rollback

Revert only the three changed paths listed above. There is no schema migration, external
store mutation, protected-data publication, donor import, or Drive write to undo. Do not
reset or delete unrelated work. The trusted publisher can close the draft and revert its
single task commit if independent review rejects the slice.

## Return state

At sandbox handoff this work is **IMPLEMENTED, NOT YET TESTED, NOT ACCEPTED**. The next
owned action belongs to the trusted host publisher and isolated PR CI; Hephaestus then
reviews the exact published code and CI. Merge and scientific acceptance remain manual.
