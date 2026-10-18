# G1 Phase B repair receipt — 2026-10-18

## Exact workspace and scope

- Hub-assigned worktree: `C:\AI\llm\aiye-executor\worktrees\jx-d421712c0ec8`
- Origin: `https://github.com/Stimurid/SESHAT.git`
- Branch: `aiye/exec-d421712c0ec8`
- Parent: `17bd19f475f60e8cbd7d73ec2243ae9a1d8a66a2`
- Parent tree: `1c2c1def62330ba52ca8140da26208ead00d522b`
- Delivery: changed working-tree files for the Hub snapshot; no Git metadata mutation by this worker.

## Engineering outcome

**Status: G1 security hard block, not accepted live Phase B.** Native `aiye-exec submit`
and `HUB_SPOOL_RECORD` export refuse independently of environment/config. No official
`jx-...` job is created and no live chargeable call was made. Synthetic campus and
meteorology replay/causal tests remain the appropriate non-live evidence surface.

The official AORUS `CALLER_PROTOCOL.md` and `executor.py` source show that the Hub
assigns the job ID. The old SESHAT spec preassigns `hub_job_id`, and its old argv had
invalid flags (`--decision`, `--provider`, `--job-id`, `--max-tokens`,
`--timeout-seconds`, `--budget-usd`) and invalid `--mode read-only`. An environment
variable cannot repair this trust mismatch. Native dispatch now returns
`BLOCKED_EXTERNAL / PROTOCOL_UNVERIFIED` before consuming authorization or writing
`SUBMIT_ATTEMPTED`; direct submit and argv construction also refuse.

Legacy two-column `meta(k,v)` stores return `HOST_STORE_LEGACY_MIGRATION_REQUIRED`
before schema or journal changes. Both keyed and unkeyed original rows remain on disk.
The old metadata was unsealed, so an automatic migration cannot authenticate its
key-required marker. Current sealed metadata is MAC-checked on open; deleted or
rehashed marker rows fail closed. Any transport exception after an attempt is
`SUBMIT_AMBIGUOUS`, blocking a second chargeable call.

## Verification truth table

| Case | Earlier evidence supplied with task | This worker |
|---|---|---|
| Parent 17bd full matrix | 558 passed / 1 failed (CLI captured two JSON objects) | Not rerun |
| Original keyed/unkeyed store opened by 17bd | `sqlite3.OperationalError: no such column: at` | Typed legacy refusal implemented; regression test added, not run |
| Env flag unlocks invalid native argv | Six invalid flags passed to stub runner | Native runner cannot be called; regression test added, not run |
| CLI unattested transport negative | Failed before intended gate | Output capture corrected; transport gate moved before replay; not run |
| Locally minted ACK/spool label | Could claim `HUB_SPOOL_RECORD` | Library and CLI hard deny; regression test added, not run |
| OSError after child start | May be misclassified as preflight | Ambiguous, same-job retry refused; regression test added, not run |
| Campus + meteorology E5 and two-thread replay | Synthetic tests reported in parent QA | Tests retained; not rerun |

`git diff --check` completed without whitespace errors. Tests and Ruff were **not
executed** in this Windows authoring session: the task prohibits running unreviewed
SESHAT code under the privileged host account, and this worktree had no accessible
isolated no-network Linux runner. The Hub should snapshot these files and hand the
exact child SHA/tree to isolated CI and a separate source reviewer. This receipt
does not claim CI, engineering acceptance, release, scientific acceptance or Drive sync.

## Remaining P0 barriers

1. Build a trusted Hub adapter that stores the deterministic host request separately
   from the Hub-issued `jx-...` ID and binds the official original spec, immutable
   issuer receipt and stdout bytes. Ambiguous submit recovery must read that original
   Hub record before any retry.
2. Design and audit a transactional migration for old keyed and unkeyed stores with
   a host-held migration authority; current code preserves them but refuses opening.
3. Run the exact full matrix plus keyed/unkeyed migration, adversarial metadata,
   CLI, two-host replay and non-interference tests in isolated CI on the child SHA.
4. Have a separate reviewer verify source and the native Hub trust boundary. Human
   owner retains semantic and publication acceptance.

## Unverified inputs

The full Google goal document and current GitHub issues #6/#60 were not fetchable
through this worker's web channel. `aiye-exec` was not on this shell's PATH, so its
live `submit --help` was not invoked. Active Hub job inventory was not verified.
The task passport and local checked-in code/docs were used for scope; no assumption
of an active writer or completed live job was made.
