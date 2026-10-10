# S-IMPL-002B RESULT

## Status

**ENGINEERING REVIEW REPAIR IMPLEMENTED IN THE SANDBOXED WORKING TREE FOR
PR #27 AT INPUT HEAD `c34cad720c6c21ae58a6affe4076939f33bc9c18`;
LOCAL PYTHON TEST EXECUTION IS PROHIBITED; ISOLATED PR CI IS
PENDING. TESTED/ACCEPTED ARE NOT CLAIMED.**

This receipt covers the bounded, domain-neutral reconciliation controller in
[S-IMPL-002B / issue #17](https://github.com/Stimurid/SESHAT/issues/17). It does not
claim execution of the historical Object or Agent-0 method bodies, semantic review,
durable S6 persistence, or scientific acceptance.

## Admission and baseline

- **WORKSPACE_MODE:** `WINDOWS_LOCAL`
- **WORKDIR_ABSOLUTE:** `C:\projects\seshat`
- **ORIGIN_URL:** `https://github.com/Stimurid/SESHAT.git`
- **BRANCH:** `codex/s2b-bounded-reconciliation`
- **ORIGINAL TASK BASE_SHA:** `041ea2e8c69a4fb9d6a640dee04aa52833e47575`
- **REPAIR INPUT HEAD_SHA:** `c34cad720c6c21ae58a6affe4076939f33bc9c18`
- **INITIAL_DIRTY_STATUS:** clean
- **RESUME_DIRTY_STATUS:** exactly the three allowed paths below, containing the
  interrupted repair attempt; preserved and completed without reset or checkout
- **CURRENT_TASK:** S-IMPL-002B / issue #17
- **CURRENT_PR:** #27, engineering review status `CHANGES REQUIRED`
- **NEXT_GATE:** exact-path trusted handoff, isolated PR CI, and independent re-review
- **BLOCKERS:** Codex-written Python/pytest must not run on the credential-bearing host;
  isolated PR CI has not yet evaluated this repair

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
state, not authority to weaken or repeat the admission decision. The wrapper exited
with code 92 after treating a recoverable documentation patch-context diagnostic as
fatal. This was not a pytest, Ruff, or GitHub Actions result; publication remained
`NOT_STARTED`.

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

### Typed bounded controller and complete-round law

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

A complete round now contains exactly one call of each member of the reciprocal pair,
in either order. A strategy exception, non-string/unhashable/out-of-pair selection, or
same-side repeat within an incomplete round produces sanitized
`BLOCKED / STRATEGY_STOPPED`; it cannot call the selected provider or synthesize a
complete round. Round numbers and `rounds_completed` therefore describe reciprocal
pairs rather than every two arbitrary calls.

### Versioned proposals and evidence

Every successful attempt records:

- operation ID, attempt and round number;
- versioned input `SourceRef` and `CandidateRef` values;
- versioned output `ProposalRef` and candidate ref;
- provider-declared typed constraints and mismatches;
- provenance and causal links;
- the S1 `SourceAccessManifest` without raw source content;
- unchanged/duplicate detection.

Before `Runtime.run()` can persist a candidate, the operation adapter computes a
strict canonical JSON semantic fingerprint. Non-serializable values, non-canonical
mixed key types, and equivalent unknown-object type fallbacks are rejected as
`BLOCKED / INVALID_PROPOSAL`. The fingerprint includes payload, constraints,
mismatches, source observation IDs, applicability, and uncertainty. Candidate/proposal
identity, parent lineage, provenance/receipts, and acceptance state remain outside
semantic equivalence so fresh receipt IDs do not conceal or manufacture oscillation.

`FULL_REQUIRED` access is still enforced by the existing S1 runtime. The controller
pins the research-object version and verified source IDs/versions/digests on the first
attempt and blocks a later mismatch before the candidate is persisted. It compares the
runtime candidate snapshot before and after provider execution and between attempts.
Provider input comes only from `Blackboard.candidate_state()`, so `STALE`, `REJECTED`,
`CONTESTED`, and historical `ACCEPTED` objects are not active prior candidates.
If source/access/candidate drift blocks a later attempt, candidates already emitted by
that run are explicitly quarantined to `STALE` through a recorded guard dependency;
their history remains addressable and the ledger lists the quarantined refs.

Mismatch validation is deliberately two-stage. `against_operation_id` must name the
other member of the bounded pair and is rejected before candidate persistence if it is
self/ghost. Constraint references may name the peer's future constraint during the
first call (required by T02). Once both current-round proposals exist, the controller
requires pair-wide unique constraint IDs and resolves every mismatch and
`incompatible_with` reference before convergence or APORIA classification. A dangling
or ambiguous duplicate ID blocks as `INVALID_PROPOSAL`; already persisted outputs from
that unsafe round are quarantined while their attempt receipts remain inspectable.

### Outcome and authority separation

- `CONVERGED` requires a complete pair of non-empty, provider-declared compatible
  constraints with no declared mismatch. A provider's `claims_convergence` field is
  retained as a statement but is not the decision rule.
- `APORIA` requires contradiction in the configured number of consecutive complete
  reciprocal rounds. A prior non-contradictory/non-convergent round does not count.
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

### PR #27 engineering-review correction matrix

| Review finding | Repair witness | Added regression expectation |
|---|---|---|
| Incomplete custom `A,A,B,B` schedule could look converged | A round is a per-round map and rejects a repeated side before provider dispatch | `A,A,B,B` blocks as sanitized `STRATEGY_STOPPED`; `B,A` completes and may converge |
| Strategy exception or malformed/unhashable selection escaped typed handling | `choose_next` is inside a sanitizing boundary and selection is type-checked before membership | exception and `[]` both block with zero provider calls and no leaked detail |
| Fingerprinting happened after persistence and accepted ambiguous Python material | strict canonical fingerprint is computed in `_OperationAdapter.execute` before it returns to `Runtime.run`; JSON object keys must be strings | opaque payload, non-string/mixed keys, and opaque constraint value block as `INVALID_PROPOSAL` with empty Blackboard |
| Fingerprint omitted semantic candidate state | payload, observations, applicability, uncertainty, constraints, and mismatches are fingerprinted; IDs/lineage/receipts remain excluded | changed uncertainty is neither unchanged nor duplicate and reaches the round budget |
| Mismatch/constraint references could manufacture a false contradiction | peer target is checked before persistence; pair-wide ID uniqueness and references are checked only after both proposals exist | self/ghost target blocks pre-persistence; dangling and duplicate IDs block before outcome and quarantine prior outputs; T02 future peer refs remain valid |
| APORIA used absolute round position | a counter advances only for contradictory complete reciprocal rounds and resets on a non-contradictory round | clean round 1 plus contradictory rounds 2-3 reaches APORIA only after the second consecutive contradictory round |

These are static implementation and test witnesses. None is reported as executed until
the trusted publisher produces a new PR head and isolated CI reports the exact results.

## Verification

### RED order

The original S2B test file preceded its implementation. For this review repair, the
negative cases were written before the narrow controller corrections in the interrupted
attempt. An executable RED result is not claimed: task policy prohibits running
Codex-written Python/pytest on this credential-bearing Windows host, and delegates Ruff
and pytest to the trusted publisher and isolated GitHub CI.

### Commands

Required final commands:

```text
python -m pytest -q
python -m ruff check .
git diff --check
```

Results at sandbox handoff:

- `python -m pytest -q` — **NOT EXECUTED LOCALLY / CI_PENDING** by explicit host policy;
- `python -m ruff check .` — **NOT EXECUTED LOCALLY / CI_PENDING** by explicit host policy;
- `git diff --check` — **PASS** for tracked deltas;
- static path review — **PASS**: only the three approved tracked paths are dirty;
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
