# M5 — Room / Carpet source matrix (M5-A … M5-G)

Status: **SYNTHETIC_ENGINEERING_ONLY / NOT_SCIENCE_ACCEPTED / NOT_AUTONOMOUSLY_ACCEPTED.**
M4 v0.3 remains `NOT_AUTONOMOUSLY_ACCEPTED`. Nothing in this milestone grants
scientific acceptance, rights attestation or release authorisation.

**Execution honesty.** The code in this corrective pass was authored without
being executed on the authoring Windows host: no project module, no pytest, no
Ruff and no synthetic runner was run there. Every claim below is a claim about
*source*, not about observed test results. Isolated Linux CI
(`.github/workflows/report-first-no-network.yml`) is the only execution route,
and until it has run, all runtime results in this document are
**NOT_OBSERVED**.

## Where each part lives

| Part | Scope | Source | Tests | Source state |
|---|---|---|---|---|
| M5-A | Single engineering line restored; prior commits preserved | worktree on `33f6e07` | — | IMPLEMENTED |
| M5-B | Source-neutral F07/F08 seam (#73) | `src/seshat/pdf_claims_sandbox_bridge.py`, shared admission in `src/seshat/pdf_claims.py` | `tests/test_pdf_claims_sandbox_bridge.py` | IMPLEMENTED |
| M5-C | RoomBuilder over the real registry, runtime state and budget | `src/seshat/fabric_waves/room_builder.py` | `tests/fabric_waves/test_m5_room_builder.py` | IMPLEMENTED |
| M5-D | Six+ functionally distinct threads across two worlds | `src/seshat/fabric_waves/m5_synthetic_hosts.py` | `tests/fabric_waves/test_m5_room_carpet.py` | IMPLEMENTED |
| M5-E | Delta scoping, durable checkpoint, new-process continuation | `src/seshat/fabric_waves/m5_checkpoint.py`, `m5_room_carpet.py` | `tests/fabric_waves/test_m5_checkpoint.py` | IMPLEMENTED (bounded, see limits) |
| M5-F | Operator answer vs observer telemetry | `m5_room_carpet.py` (`_operator_sections`, `build_telemetry`, `render_carpet_index`) | `tests/fabric_waves/test_m5_room_carpet.py` | IMPLEMENTED |
| M5-G | Oracle portfolio, independent reading, isolated execution | `src/seshat/fabric_waves/m5_oracles.py`, CI workflow | `tests/fabric_waves/test_m5_oracles.py` | IMPLEMENTED in source; **execution NOT_OBSERVED** |

## What the repaired Room actually does

`compile_room` is a pure recursive backwards dependency closure over the
fixture's declared `thread_registry` (`read_set` / `write_set` state types),
the desired output state, the states the host actually has, the rights granted
to the room, and a capability budget.

It **never reads `must_wave`**. `must_wave` is the acceptance oracle for the
plan; compiling from it would make the oracle assert itself. The discriminating
test is `test_plan_is_identical_when_must_wave_is_erased`: erasing the field,
replacing it with a wrong plan, or reordering it leaves the compiled plan
byte-identical.

Admission is **binding on execution**, not metadata: `admitted_threads()`
narrows `engine.thread_specs` for the duration of the run, so a capability the
room refused has no spec and cannot fire. `RoomManifest.status` stays `PLANNED`
until the room is admitted to a real run and `close()` has observed genuine
activations.

Verdicts a capability can receive: `ADMITTED`, `BLOCKED_MISSING_INPUT` (with
the specific missing state named), `DENIED_RIGHTS`, `DROPPED_BUDGET`.

## Oracles

Every RM row is decided by a named observation. There are **no constant `True`
verdicts**. A scenario that was not exercised reports `NOT_TESTED`, which is a
distinct, non-passing state and is counted separately in
`oracles.json → summary.not_tested_ids`.

| Oracle | Decided by |
|---|---|
| RM01 | no capability the room refused produced an activation in that room's run |
| RM02 | each producing activation is backed by a retained sediment record |
| RM03 | a join whose consumed records came from two **named distinct** parent activations |
| RM04 | branch A's derived record ids/versions/payload hashes unchanged **and** no A re-execution during the delta run; B's changed |
| RM05 | frontier capability not admissible before the need existed, admissible after, actually fired, with the triggering predecessor named |
| RM06 | a child **process** continued from the checkpoint and matched the uninterrupted control, **and** a duplicate stone did zero fresh activations |
| RM07 | the other host's checkpoint was **refused by ownership**, not merely hash-different |
| RM08 | an excluded carrier was refused on admission |
| RM09 | withholding the declared right yields `DENIED_RIGHTS` and zero activations |
| RM10 | the ACCEPTED view is empty |
| RM11 | no decision event **and** an unauthorised acceptance was actively refused (two refusal paths probed) |
| RM12 | an aporia recorded on an activation, ending its run as `APORIA` |
| RM13 | no record on the untouched branch was invalidated (scoped, not `len(stale) >= 0`) |
| RM14 | every E1 record carries a version-pinned access receipt |
| RM15 | a budget-capped run and a settled run recorded different outcome/stop reasons |
| RM16 | no executor port bound, no external carrier admission |
| RM17 | room close dropped no record and rewrote no version |
| RM18 | a self-owned checkpoint verified as integrity only, never as external authority |
| RM19 | every reference in the operator answer resolves to a real record or activation |
| RM20 | every thread that fired is bound to a declared registry capability |

## Checkpoint and continuation — stated limits

`M5Checkpoint` retains: current source versions plus the applied deltas
(replayed through the host's own pinned revision authority, never from the
checkpoint's own content), all sediment records with their view membership and
producer activation links, the full serialised `RunLedger` with its append
order, processed-stone fingerprints and cursor, dispatcher pending stones,
budget, and stored per-stone results. It is checksummed, written atomically and
verified on read-back, mirroring `ExternalWaitCheckpoint`.

**Bounded scope, stated explicitly:**

* Checkpoints are taken only at **quiescent** points, between stones. There is
  no mid-wave checkpoint.
* A process that died inside a stone writes `completed=False` with
  `pending_stone_id` set. Continuation **refuses** such a checkpoint
  (`M5_CHECKPOINT_PENDING_STONE_REQUIRES_RECONCILIATION`) until
  `reconcile_pending()` is called with an explicit
  `DISCARD_PENDING_STONE` / `ACCEPT_PENDING_AS_DONE` decision. There is no
  automatic option, because blind replay can duplicate paid work and blind
  skipping can lose it.
* Verifying one's own checkpoint is an **integrity** check. It is not external
  attestation and promotes nothing.
* A checkpoint from another host or another fixture is rejected by ownership
  token, before any state is restored.

## M4 transport boundary

`assess_delivery` now takes **multiple spans with byte offsets**, each carrying
its own `source_id` / `source_version` / `content_sha256`. Spans are merged into
disjoint coverage, so overlapping ranges cannot fill a gap; missing ranges are
reported by byte offset. Negative ranges, ranges exceeding the stored length and
identity mismatches are `DELIVERY_DENIED`. UTF-8 characters are never split.
Previews are measured in bytes and roll back to a character edge; long lines are
reported, not truncated; a trailing end marker is explicitly not evidence of
completeness.

`consumed_source_check` is wired into the real M5 invocation path (every carrier
actually consumed by an activation) and lands in `receipt.consumed_source_checks`.

`assess_output_sections` gates the operator report on required **non-empty**
sections plus known partial/metadata flags — a heading alone does not complete a
report.

All of this is **structural completeness and correspondence only**.
`check_declared_fact` certifies that a declared synthetic quote occurs at its
declared byte offset in its declared source version, and says so in its own
detail string: it is not natural-language entailment.

## Fixtures and packaging

The frozen original fixture
(`m5_room_synthetic_acceptance_20261021_v01.json`, SHA-256
`9feab9b1…a0e328`) is accepted by its pin. **Any other fixture requires a
caller-approved digest** (`--fixture-sha256`), so an invented world can be run
without hardcoding one world identity as the engine.

The fixture is shipped as package data at
`src/seshat/fabric_waves/m5_fixtures/` so the installed `seshat-m5-carpet`
console script resolves it via `importlib.resources`; if the resource is
unavailable the CLI exits 2 and asks for `--fixture` rather than walking
parent directories. `test_fixture_copies_do_not_drift` pins the packaged copy
byte-identical to the test copy, and CI installs the built wheel into a clean
venv outside any checkout and runs the CLI with no `--fixture`.

## Not implemented / not tested

* **Nothing here was executed on the authoring host.** All runtime outcomes are
  `NOT_OBSERVED` until the isolated Linux CI run completes.
* RM oracles whose probe cannot run in a given environment report `NOT_TESTED`;
  the summary lists their ids. A `NOT_TESTED` row is **not** a pass.
* The #73 bridge establishes that a bounded child, given one admitted source,
  reported a match. It is `CHILD_REPORTED_MATCH_UNATTESTED`. Full-source
  rights, method identity, semantic entailment and scientific acceptance are
  unpromoted, and the bridge's status vocabulary contains no `VERIFIED` value.
* No real (non-synthetic) source, no model call, no issuer service and no
  privileged server participates anywhere in M5.
* Scientific acceptance of the method remains outside this milestone entirely.
