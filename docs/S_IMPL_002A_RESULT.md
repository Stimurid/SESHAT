# S-IMPL-002A RESULT

## Status

**IMPLEMENTED IN WORKING TREE; EXECUTION AND GIT DELIVERY BLOCKED BY THE CURRENT
MANAGED SANDBOX. NOT ACCEPTED.**

This receipt covers the bounded coherent-blackboard slice in issue
[S-IMPL-002A / #14](https://github.com/Stimurid/SESHAT/issues/14). It does not claim S2B
reconciliation scheduling, durable traces, semantic review, or human acceptance.

## Preflight

- **WORKSPACE_MODE:** Windows local verified checkout
- **WORKDIR_ABSOLUTE:** `C:\projects\seshat`
- **ORIGIN_URL:** `https://github.com/Stimurid/SESHAT.git`
- **BRANCH:** `codex/s2a-coherent-blackboard-20261010`
- **BASE_SHA:** `4a58907cf55d5af408c61866103212e0320927fb`
- **HEAD_SHA:** `4a58907cf55d5af408c61866103212e0320927fb` (unchanged because `.git` is
  read-only in this session)
- **INITIAL_DIRTY_STATUS:** clean
- **CURRENT_TASK:** S-IMPL-002A / issue #14
- **CURRENT_PR:** none
- **NEXT_GATE:** S2B bounded Object/Method reconciliation, only after S2A review
- **BLOCKERS:** Python executables and GitHub network are inaccessible from the managed shell;
  `.git/index.lock` cannot be created, so commit/push/PR and CI triggering are blocked.

Only one Git worktree was present, at `C:\projects\seshat`, and no local competing core-writer
worktree was found before editing.

## Changed paths

- `src/seshat/blackboard.py`
- `src/seshat/runtime.py`
- `tests/test_runtime.py`
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
- `accepted_state(...)` exposes `ACCEPTED` objects explicitly. Accepted objects are not fed to a
  provider as current candidates and are not silently displaced by a proposal.
- `history(...)` exposes all retained objects, including `STALE`, `REJECTED`, and `CONTESTED`.
- `get(derived_id, version=...)` is the exact version-pinned lookup and fails on version drift.
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

`supersede(prior_id, replacement_id)` is explicit. It requires the same research object and object
type, a candidate replacement, and a declared parent-lineage link to the prior candidate. It marks
the prior candidate `STALE` and transitively invalidates only dependency descendants. It refuses to
supersede `ACCEPTED` (or any other non-candidate) state without a future authorized workflow.

`invalidate_descendants(upstream_id)` is distinct: it changes only transitively linked descendants,
preserves the upstream object, every stored object and dependency edge, and unrelated branches.
Cycle traversal excludes the root from self-invalidation. `mark_changed(...)` remains a compatibility
alias for this descendant-only behavior.

## Test evidence

Nine S2A tests were added, covering:

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

The focused RED command was attempted before changing source code:

```text
python -m pytest -q tests/test_state_views.py::test_runtime_prior_state_excludes_stale_downstream
```

The managed shell could not resolve `python`. A retry with the machine's known Python 3.14 path was
denied by the filesystem sandbox. Therefore no executed RED result is claimed. The base source
witness was direct: `Runtime.run` passed `tuple(blackboard.working_state(...))`, while
`working_state` yielded every object regardless of state; the new T01 assertion would therefore
receive all six seeded states instead of only `working` and `proposed`.

### GREEN and static evidence

- `git diff --check` — **PASS** (line-ending conversion warnings only).
- `python -m pytest -q` — **NOT EXECUTED**: installed Python is outside the shell's permitted
  filesystem surface (`Access is denied`). The prior main receipt records 36 passing tests; the
  working tree now defines 9 additional tests, but **45 passing is not claimed**.
- `python -m ruff check .` — **NOT EXECUTED** for the same sandbox reason.
- GitHub Actions — **NOT TRIGGERED** because shell network access to `github.com:443` failed and no
  commit/PR could be created.

## Delivery blocker

`git add` and `git commit` failed with:

```text
fatal: Unable to create 'C:/projects/seshat/.git/index.lock': Permission denied
```

The session permission profile exposes `.git` read-only. A read-only `git ls-remote` also failed to
connect to `github.com:443`. No commit SHA, push, PR, or CI URL is fabricated. The implementation is
left as an inspectable uncommitted working-tree delta on the requested branch.

The mandatory coordination inbox is
[S-COORD-001 / #6](https://github.com/Stimurid/SESHAT/issues/6). Live issue retrieval was attempted,
but `gh` was unavailable and browser fetch could not access this repository. The full task handoff
and Git-local coordination records were used. Donor issues #10 and #11 are classified `NEXT_SLICE`:
they are later-stage warnings with no permission or need to import donor code into S2A.

## Limitations

- State, transitions, dependencies, and access receipts remain in memory only.
- Status mutation preserves stored objects and lineage but is not a durable event log.
- No acceptance workflow is introduced; authorized host code remains responsible for inserting or
  transitioning accepted state.
- No S2B scheduler, reconciliation budget, convergence/conflict/exhaustion receipt, APORIA loop, or
  executable Object/Method method body is implemented.
- No claim is made that coherent infrastructure state establishes scientific validity.

## Rollback

Discard or revert only the five changed paths listed above. There is no schema migration, external
store mutation, donor import, or Drive write to undo. Because Git commit creation was blocked in
this session, rollback currently means restoring those working-tree files from the verified base,
and must not be performed while unrelated user changes overlap them.

## Recommended S2B scope

After review and verified S2A test execution, add a bounded host-directed reconciliation protocol
for Object/Method candidates: explicit round budget and stop reasons, version-pinned proposal refs,
mismatch/APORIA records, and distinct converged/conflicting/exhausted receipts. Do not infer a
universal cyclic scheduler, auto-accept any proposal, or import donor method bodies in that slice.
