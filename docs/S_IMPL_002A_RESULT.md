# S-IMPL-002A RESULT

## Status

**PR #16 FOLLOW-UP IMPLEMENTED IN WORKING TREE; TEST EXECUTION AND GIT DELIVERY
ARE OUTSIDE THIS MANAGED SANDBOX. NOT ACCEPTED.**

This receipt covers the bounded coherent-blackboard slice in issue
[S-IMPL-002A / #14](https://github.com/Stimurid/SESHAT/issues/14). It does not claim S2B
reconciliation scheduling, durable traces, semantic review, or human acceptance.

## Preflight

- **WORKSPACE_MODE:** Windows separate Git worktree
- **WORKDIR_ABSOLUTE:** `C:\projects\seshat-impl-p16`
- **ORIGIN_URL:** `https://github.com/Stimurid/SESHAT.git`
- **BRANCH:** `codex/s2a-coherent-blackboard-20261010`
- **BASE_SHA:** `0110935d0f8df37543a45aa5e811bb55938fdcaf`
- **HEAD_SHA:** `0110935d0f8df37543a45aa5e811bb55938fdcaf` (no Git writes requested)
- **INITIAL_DIRTY_STATUS:** clean
- **CURRENT_TASK:** PR #16 follow-up review blockers B1-B5 for S-IMPL-002A
- **CURRENT_PR:** #16
- **NEXT_GATE:** publisher/reviewer test and review of this bounded S2A repair; S2B is excluded
- **BLOCKERS:** no Python executable is visible from the managed shell, so tests and Ruff are
  not run here; commit, push, `gh`, merge and self-approval were explicitly excluded.

The user designated this separate worktree as the sole write target. The primary worktree at
`C:\projects\seshat` was not inspected or modified.

## Changed paths

- `src/seshat/blackboard.py`
- `tests/test_state_views.py`
- `docs/S_IMPL_002A_RESULT.md`

No donor code, private corpus, profile method body, scheduler, Drive data, or external store was
added or changed.

## State and view contract

The blackboard retains every distinct `DerivedObject` under a stable `derived_id`. Reusing an
existing ID is idempotent only for identical content; different content under the same ID is
rejected and must receive a new ID/version. Public reads return deep snapshots so a provider or
caller cannot mutate stored state through a returned Pydantic model.

The views have intentionally different meanings:

- `candidate_state(...)` contains only `WORKING` and `PROPOSED`. It is the sole prior-state view
  supplied by `Runtime.run`.
- `accepted_state(...)` exposes historical `ACCEPTED` admissions explicitly, including an
  admission whose current evidence validity later became `STALE`. Accepted or stale snapshots are
  not fed to a provider as current candidates.
- `history(...)` exposes every retained content object at its current status, including `STALE`,
  `REJECTED`, and `CONTESTED`; status-transition snapshots are exposed separately by
  `state_history(derived_id)`.
- `get(derived_id, version=...)` pins the immutable content version but returns its current status.
  `get(..., state_revision=N)` retrieves an exact numbered status snapshot. Each in-memory
  `StateRevision` preserves the object/provenance, status and transition reason. This is a minimal
  S2A receipt, not a durable or immutable S6 event store.
- `get_candidate(...)` additionally fails if the addressed object is not an admissible candidate.
- `latest(...)` returns a value only when exactly one candidate exists. Multiple rivals raise an
  ambiguity error instead of granting last-writer authority.
- `working_state(...)` remains as a compatibility alias to the filtered candidate view; it no
  longer exposes raw history.

`ACCEPTED` is deliberately excluded from candidate state. Acceptance belongs to an external,
authorized host workflow not implemented in this slice. The existing runtime guard still rejects
provider-origin `ACCEPTED`, `CONTESTED`, `REJECTED`, and `STALE` results.

## Supersession and invalidation

Appending another result does not automatically supersede or invalidate an existing candidate.
Rival `WORKING`/`PROPOSED` projections remain separately visible.

`supersede(prior_id, replacement_id)` is explicit. It requires distinct IDs, the same research
object and object type, a candidate replacement, and a declared parent-lineage link to the prior
candidate. Before mutation it rejects any active invalidation path from the prior to the
replacement, preventing the replacement from being made stale by its own supersession. It marks
the prior candidate `STALE` and transitively invalidates only dependency descendants. It refuses
to supersede `ACCEPTED` (or any other non-candidate) state without a future authorized workflow.

`invalidate_descendants(upstream_id)` is distinct: it changes only descendants connected through
explicit `DependencyEdge` records with `invalidates_on_change=True`, preserves the upstream object,
every stored content object, transition history, dependency edge and unrelated branch. A
`parent_derived_ids` lineage declaration alone never creates an invalidation dependency. Cycle
traversal excludes the root from self-invalidation. `mark_changed(...)` remains a compatibility
alias for this descendant-only behavior.

## Test evidence

The original nine S2A tests remain. Five PR #16 follow-up tests were added:

1. `test_supersede_rejects_replacement_in_invalidation_path_transactionally`;
2. `test_self_supersession_fails_without_state_change_even_with_self_parent`;
3. `test_invalidated_acceptance_remains_inspectable_but_not_candidate_input`;
4. `test_lineage_does_not_imply_invalidation_but_explicit_edge_does`;
5. `test_content_version_pin_is_distinct_from_state_revision_pin`.

The prior nine tests cover:

1. runtime prior-state includes `WORKING`/`PROPOSED` and excludes accepted, contested, rejected, and
   stale objects;
2. stale, rejected, and explicitly superseded objects remain retrievable by ID/version and history;
3. rival candidates remain visible and `latest` refuses to choose a winner;
4. accepted history remains explicit while a newer proposal exists;
5. non-authoritative supersession cannot replace accepted state;
6. transitive invalidation preserves unrelated branches and lineage;
7. version drift and stale candidate lookup fail closed;
8. ambiguous exact-ID overwrite is rejected while identical replay is idempotent;
9. returned candidate snapshots cannot be mutated to forge stored acceptance or payload.

The existing parameterized provider-authority test continues to cover rejection of forged
`ACCEPTED`, `CONTESTED`, `REJECTED`, and `STALE` outputs. The original runtime invalidation test was
updated to use explicit lineage and explicit supersession rather than append-order inference.

### RED evidence

The focused RED command was attempted after adding the follow-up tests and before changing source:

```text
C:\Users\Homee\AppData\Local\Programs\Python\Python314\python.exe -m pytest -q tests/test_state_views.py
```

The managed shell could not resolve that executable (`CommandNotFoundException`). Therefore no
executed RED result is claimed. Direct source inspection established that the new tests referenced
missing `state_history` / `state_revision` behavior and that existing supersession mutated the
prior before invalidating its replacement.

### GREEN and static evidence

- `git diff --check` — **PASS** (line-ending conversion warnings only).
- `python -m pytest -q` — **NOT EXECUTED**: no Python executable is visible in this shell. The
  branch arrived with 45 tests and this follow-up adds 5, but **50 passing is not claimed**.
- `python -m ruff check .` — **NOT EXECUTED**: no Ruff executable is visible in this shell.
- GitHub Actions — **NOT TRIGGERED**; publishing and CI are assigned to the host reviewer.

## Delivery constraint

The assignment explicitly prohibits Git writes, `gh`, push, merge and self-approval. None was
attempted. No commit SHA, CI result or review approval is fabricated. The implementation is left
as an inspectable working-tree delta on the requested PR branch for the host publisher/reviewer.

The mandatory coordination inbox is
[S-COORD-001 / #6](https://github.com/Stimurid/SESHAT/issues/6). Live issue retrieval was attempted,
but `gh` was unavailable and browser fetch could not access this repository. The full task handoff
and Git-local coordination records were used. Donor issues #10 and #11 are classified `NEXT_SLICE`:
they are later-stage warnings with no permission or need to import donor code into S2A.

## Limitations

- State, numbered status transitions, dependencies, and access receipts remain in memory only.
- Status transition snapshots preserve stored content, provenance and lineage but are not a
  durable or tamper-evident event log.
- No acceptance workflow is introduced; authorized host code remains responsible for inserting or
  transitioning accepted state.
- No S2B scheduler, reconciliation budget, convergence/conflict/exhaustion receipt, APORIA loop, or
  executable Object/Method method body is implemented.
- No claim is made that coherent infrastructure state establishes scientific validity.

## Rollback

Discard or revert only the three changed paths listed above. There is no schema migration, external
store mutation, donor import, or Drive write to undo. Rollback means restoring those working-tree
files from the verified base and must not be performed while unrelated user changes overlap them.

## Recommended S2B scope

After review and verified S2A test execution, add a bounded host-directed reconciliation protocol
for Object/Method candidates: explicit round budget and stop reasons, version-pinned proposal refs,
mismatch/APORIA records, and distinct converged/conflicting/exhausted receipts. Do not infer a
universal cyclic scheduler, auto-accept any proposal, or import donor method bodies in that slice.
