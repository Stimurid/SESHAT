# F08-A executable metadata report delivery

Source authored 2026-10-15 for issue #58. Execution/review acceptance PENDING.
This is product source and tests, not a dispatch authorization receipt.

## Source and authority

- WORKSPACE_MODE: isolated Hub worktree, explicitly assigned by caller.
- WORKDIR_ABSOLUTE: `C:\AI\llm\aiye-executor\worktrees\jx-5f45169df4a7`
- ORIGIN_URL: `https://github.com/Stimurid/SESHAT.git`
- CURRENT_BRANCH: `aiye/exec-5f45169df4a7`
- BASE_SHA / initial HEAD: `d0978b41305f238eaa3f4df920fcc4016b7b0a62`
- Initial DIRTY_STATUS: clean. CURRENT_TASK: F08-A / #58. CURRENT_PR: none.
- NEXT_GATE: Hub snapshot, independent source review, exact-tree isolated full pytest.
- BLOCKERS: no Windows execution authorization; original method science and real corpus rights absent.

Read machine entry point, portable entry and routing instructions, project coordination,
implementation plan/charter, F07 source and tests. Python314 path from machine pointer
was unavailable; neither routing CLI nor Proteus resolve executed successfully. The
injected typed SESHAT route is a locator, not evidence of runtime mount. No actor invoked.
Ordinary web fetch failed; the authenticated read-only connectors subsequently retrieved
[issue #58](https://github.com/Stimurid/SESHAT/issues/58),
[product gap #55](https://github.com/Stimurid/SESHAT/issues/55),
[Inbox #6 current return](https://github.com/Stimurid/SESHAT/issues/6#issuecomment-6199344628),
and [owner v0.12](https://docs.google.com/document/d/1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k/edit)
(modified 2026-10-07T14:36:53.868Z; report requirements §§9.1–9.9 inspected).
The current Inbox names this exact job and supersedes the stale F07 dispatch blocker.
Classification: ACK_NEEDED_NOW for current F08 scope; VERIFY_WITH_TEST for F07 security
negatives; NEXT_SLICE for external/education/institution reports. No donor import or
methodology change. The supplied 240-pass F07 result is coordinator evidence, not a run here.

## Implemented files and behavior

- `src/seshat/reports.py`: frozen request/projection/receipt and evidence/MethodAsset
  types; owner-bound composition; deterministic JSON and escaped, offline static HTML.
- `src/seshat/corpus_host.py`: small owner-internal evidence port and private admitted
  record cache. Reuses existing F07 admission under its lock; rechecks installed pins
  on every report request. No S1/S2 or witness code changes.
- `src/seshat/report_demo.py`: two predeclared synthetic hosts, source/rights/temporal
  package bootstrap and actual three-file export CLI. No arbitrary corpus input path.
- `tests/test_reports.py`: differential security, selection, currentness and CLI tests.

R03 renders named versioned A and D subsets, selected union and pairwise overlap;
three unique studies versus four carriers; per-subset eligible/selected denominators,
false/unknown/not-evaluable counts; source/version pins; specialty/lab/cohort/defense
distributions; per-study evidence rows and drillback. Study 1 has cohort 2025 and
explicitly sourced defense 2026; study 2 has cohort 2026 and UNKNOWN defense. No
degree award is inferred. Multiple source carriers do not create extra studies.

R01 requires exactly one selected research object and renders source metadata assembly.
R02 exposes object, candidate method and evidence/state bindings. R04 adds an actual
Object × Method × Infrastructure table with unknown cells. These three are explicitly
PARTIAL_METADATA, not reconstructed science. A rights-cleared MethodAsset references
Blackboard's present status via `get`, never its historical `accepted_state`. Stale,
candidate, incompatible or changed-source bindings are blocked. Even an accepted-current
result plus an owner-supplied body hash leaves method execution BLOCKED: F08 does not
read or verify MethodBody bytes and cannot turn a hash assertion into scientific evidence.
No derived payload or private MethodBody text is exported.

R05/R06/R07 have BLOCKED_EXTERNAL_EVIDENCE with different required inputs; R08 has
BLOCKED_ADAPTER; R09 has BLOCKED_DECISION_RIGHTS. Their metadata context is renderable
but receipt `substantive_completed` is false. Only R03 sets that flag, scoped to metadata.

## Replay in the independently authorized isolated environment

With the existing package/dependencies available (no install or network required):

```sh
PYTHONPATH=src python -m seshat.report_demo --fixture sechenovka-like --report R03 --output /tmp/f08-demo
PYTHONPATH=src python -m seshat.report_demo --fixture meteorology --report R04 --output /tmp/f08-atlas
PYTHONPATH=src pytest -q
ruff check src/seshat/reports.py src/seshat/report_demo.py tests/test_reports.py
```

Output must be a NEW directory beneath an existing trusted writable parent. Existing
directories, symlinks/junction ancestors and overwrites are refused. Do not use an
attacker-writable shared parent; race-proof hostile-filesystem export is outside scope.
CLI temporary inputs contain only invented fixtures and are removed after composition.
Artifacts: `report.html`, `report.json`, `receipt.json`. The receipt hashes the exact JSON
and HTML bytes; projection digest hashes canonical JSON excluding only `digest`.
The CLI integration test executes a real subprocess, opens all three files, validates
Pydantic models, recomputes hashes and compares a second run byte for byte.

## Security and provenance limits

HostRuntime and `report_session` factory are owner-side trusted components, not client
dependency injection endpoints. Expose only the bound callable through authenticated
transport. This source does not deploy a service. Public model constructors are not
authentication. Python arbitrary code execution in the owner process is outside the model.

F07 filters denied objects/carriers before parsing. Reports consume only admitted selected
rows, and only explicit field allowlist values. Raw carrier URI, source_identity, metadata,
filesystem paths, full-population hashes and private rights/source epochs are not exported.
Allowed object/carrier IDs are visible evidence pins. Host grants must authorize publication
of allowlisted fields; this slice does not add a field-level policy system. HTML escapes
all text, uses only generated fragment links, no scripts/CDN/network resources. Rights
revocation requires a fresh composition; already exported files cannot be remotely revoked.

The request's as-of is a requested label, NOT historical reconstruction: output says so.
Public selected member pins and snapshot digests support explicit stale-request rejection;
private manifest/rights rotations never change equivalent public output. Denied counts
are omitted. Empty selections have zero selected counts and no invented research claims.
The host must serialize Blackboard changes with report calls if used concurrently; this
in-memory composer does not add a cross-store transactional Blackboard lock.

## Verification actually performed

Read-only Git identity/status/diff inspection and `git diff --check` were executed.
No project import, pytest, Ruff, demo CLI, Docker or other project-code execution occurred
on credentialed Windows. New tests are authored, NOT claimed passing. Original baseline
test files remain untouched. Required external gate is the FULL suite including F07's 240
baseline tests and these added cases, on the exact Hub snapshot, root/source read-only,
nonroot, no network/secrets. No commit/push/PR/merge or Drive publication performed;
Hub owns snapshot creation. Rollback is removal of the new modules/test/doc and the
17-line host evidence-port addition; no data migration.

## OPEN QUESTIONS

1. Are all allowlisted metadata fields publishable for a host grant? Default used:
   yes only for the predeclared synthetic fixture; production requires host-owner review.
2. Does as-of mean historical state reconstruction? Default used: requested date label
   only, with explicit current-composition caveat; no invented history.
3. Can MethodBody availability or scientific acceptance be asserted? Default used: no;
   report shows source/state binding and remains method-blocked.
4. Has this new exact tree passed tests/security review? Default used: not yet;
   coordinator must execute the isolated checks after Hub snapshot.
