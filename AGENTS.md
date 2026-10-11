# AGENTS.md — SESHAT agent operating rules

## Repository identity and workspace gate

This directory must be a verified checkout of [Stimurid/SESHAT](https://github.com/Stimurid/SESHAT), the **single canonical** Universal Analytic Fabric implementation. Do not create another implementation repository.

**Intended Windows local workspace:** `C:\projects\seshat`. If the local Windows folder exists, verify `git rev-parse --show-toplevel` and `git remote get-url origin` before writing. Reuse the correct checkout. If it is missing, clone `https://github.com/Stimurid/SESHAT.git` into `C:\projects\seshat`. If the folder belongs to another repo, has conflicting files, or has unsafe uncommitted work, stop and report `BLOCKED_WORKSPACE`; never delete/reset/overwrite or create an alternate SESHAT repo without permission.

**Cloud Codex or non-Windows environment:** use the actual platform-provided checkout for `Stimurid/SESHAT`, or clone into a real writable workspace when allowed. The Windows path is not available in a cloud container. Never pretend a cloud checkout changed the user's local Windows files.

For the complete preflight procedure, see [CODEX_IMPLEMENTATION_HANDOFF_v0.1.md](docs/CODEX_IMPLEMENTATION_HANDOFF_v0.1.md), section "MANDATORY WORKSPACE BOOTSTRAP".

**Before code changes, report:** `WORKSPACE_MODE`, `WORKDIR_ABSOLUTE`, `ORIGIN_URL`, `CURRENT_BRANCH`, `HEAD_SHA`, `DIRTY_STATUS`. If unverified, report `BLOCKED_WORKSPACE`, not a fictitious implementation success.

## Code ownership and active task

- Read [WORKSTREAM_COORDINATION_v0.1.md](docs/WORKSTREAM_COORDINATION_v0.1.md). One implementation executor owns `src/`, `tests/`, `profiles/` and CI code at a time. Archaeology and Indago are parallel evidence workstreams, not concurrent core writers.
- Read [SESHAT_IMPLEMENTATION_PLAN_v0.1.md](docs/SESHAT_IMPLEMENTATION_PLAN_v0.1.md) and [IMPLEMENTATION_CHARTER.md](docs/IMPLEMENTATION_CHARTER.md).
- Historical initial task: [S-IMPL-001 / issue #3](https://github.com/Stimurid/SESHAT/issues/3). **Do not treat this or the old PR16→issue17 queue as a current dispatch order.** As of 2026-10-11 S1/S2A/S2B are engineering-accepted, S2B [issue #17](https://github.com/Stimurid/SESHAT/issues/17) is closed, [PR #27](https://github.com/Stimurid/SESHAT/pull/27) is merged in `main@cad04bde48434d76c2fdd1825621052c64c8db3c` with [postmerge CI success](https://github.com/Stimurid/SESHAT/actions/runs/38093134714). Determine the *new* work item from current [Inbox #6](https://github.com/Stimurid/SESHAT/issues/6), not this dated snapshot.
- Work on a task-specific branch and open a PR with tests, CI links, changed paths, known limits and rollback. No unreviewed executable edits straight to main.

## Standing implementation inbox and cross-workstream intake

**Mandatory re-entry channel:** [S-COORD-001 — Implementation Inbox / issue #6](https://github.com/Stimurid/SESHAT/issues/6), together with [Drive Implementation Lead Sync v0.1](https://docs.google.com/document/d/1OyIuHINMj7Lgv_snDGs8cRDV50txgGyqyyguyesW7Zk/edit). These govern *coordination and recovery*, not a replacement for the accepted engineering plan.

- On every implementation session start / cold re-entry: check actual repository HEAD and dirty status, `docs/SESHAT_IMPLEMENTATION_PLAN_v0.1.md` (or proven successor), active implementation task/PR/CI, and new comments/issues in #6.
- Before entering another S1-S6 gate, donor import, method/public-contract edit, or PR acceptance: re-read relevant pinned donor archaeological returns and negative tests. During long uninterrupted **active** work check the inbox about every two hours; this is not a background watcher.
- Classify each source-pinned return as `ACK_NEEDED_NOW`, `NEXT_SLICE`, `VERIFY_WITH_TEST`, `ARCHIVE_ONLY`, `NOT_APPLICABLE` or `BLOCKED_ON_SEMANTIC_DECISION`. Record its effect on current task, exact evidence/pin, concrete negative/acceptance tests and owning issue/PR. Do not change methodology on archaeology/Indago authority alone.
- First known intake: [Quinta PR #4](https://github.com/Stimurid/SESHAT/pull/4) and [Socrates/Tinkuy PR #7](https://github.com/Stimurid/SESHAT/pull/7), with deferred regression backlog [S-REG-001 / issue #8](https://github.com/Stimurid/SESHAT/issues/8). These do not automatically block unrelated S1 [PR #5](https://github.com/Stimurid/SESHAT/pull/5); review affected S2/S3/S5/S6 work before merge.
- After re-entry record `BASE_SHA`, `CURRENT_TASK`, `CURRENT_PR`, `NEXT_GATE` and `BLOCKERS` in the durable task/PR receipt. Preserve one executable-core writer.

## Invariants

- Do **not** replace this repository with a new scaffold. Extend existing Pydantic contracts, minimal runtime, adapters, blackboard and tests.
- No universal mandatory `cut → derive → analyze` pipeline. Source-addressing observations are **not semantic truth**. Method-specific operations can need complete original source and prior states.
- `FULL_REQUIRED` must validate **actually readable, complete, version-consistent source content**, not just a SourceCarrier metadata record. `DRILLBACK` must be source-addressed; `NEVER` must deny raw access.
- Preserve semantic authority of host systems and human-only decisions. A green CI build cannot self-certify scientific methodology.
- No private research, medical or author-owned prompt bodies in this public Git repo without explicit authorization.
- Donor capabilities require source- and generation-pinned implementation evidence. See [Donor census](docs/DONOR_IMPLEMENTATION_CENSUS_v0.1.md) and [Quinta archaeology](docs/QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md). Do not repeat archaeology as a substitute for the assigned code.
- Git is the current verified code/durable handoff surface; do not assert Google Drive synchronization without successful write and readback.

## Agent evidence-return and RDC economy (2026-10-11)

**Mandatory global policy:** [AIYE — Global Agent Evidence Return & RDC Economy](https://docs.google.com/document/d/1M4GqFP8LdEvZnIlTGHPdWngf7z6BHLWClVWuLNhlK18/edit). Project delivery issue: [S-OPS-EVIDENCE-RETURN #37](https://github.com/Stimurid/SESHAT/issues/37). This applies to all SESHAT-Codex/Cursor/Claude/remote workers and to the operating norm of the AIYE ecosystem.

- **Default: no steady-state Remote Desktop Commander process/log polling.** Query the current GitHub task issue, PR commits, exact-SHA CI, owner/agent receipt and Drive current-state mirror. Local scheduled monitors may observe process termination *on the host*, and a trusted publisher returns **one** bounded Git/Drive status; do not poll `state.json`, Win32 process IDs or terminal output repeatedly from ChatGPT.
- On new session or context loss, consult [Inbox #6](https://github.com/Stimurid/SESHAT/issues/6), canonical Git main, active issue/PR/CI and owner/source facts first. An unchanged issue is not proof a worker is running, stalled or done. A result is complete only after an exact commit/PR, tested CI and explicit engineering gate.
- For initial installation, missing/unreachable journal, failure recovery or a real transport incident, one bounded RDC operation is permitted with `WHY_RDC_REQUIRED`, a finite safe pathset, resource-cost note and a follow-up journal-repair ticket. **Never use periodic RDC to emulate a message bus.**
- Executor writes scoped code/tests and a durable receipt. Privileged publisher (a distinct trusted host component) validates authorization, exact changed paths/digests and secrets, then commits/pushes/opens a **draft** PR. CI reports exact SHA and test outcome, separate from scientific review. Do not give untrusted Codex Google/GitHub/browser credentials or execute its code on a privileged Windows host.
- Drive mirror must use an independently authorized least-privilege identity with successful readback. Without it mark `DRIVE_SYNC=MIRROR_PENDING/BLOCKED_AUTH`. **A Google Doc link or a status claim is not proof of automatic propagation.** Existing open chats require their own reentry/refresh to ingest new policy.
- Local `SESHAT-Codex-Watch` and `SESHAT-Codex-Dispatch` are runtime surfaces, not durable cross-chat truth. Watch history and immutable failures are retained. Dispatcher is **Disabled** pending repairs [#25](https://github.com/Stimurid/SESHAT/issues/25), [#28](https://github.com/Stimurid/SESHAT/issues/28), [#37](https://github.com/Stimurid/SESHAT/issues/37) and successor authorization [#34](https://github.com/Stimurid/SESHAT/issues/34). Do not re-enable from task-level agent output.

## Execution truth

Creating a Git issue, handoff or agent instruction file does **not** start a Codex session. If no executor is running or attached to this checkout, report `READY_FOR_CODEX`, not `RUNNING`. Mark implementation complete only with a commit, PR, tests and CI evidence.

## Trusted host Git publishing and conditional task dispatch

The Codex Windows workspace-write sandbox denies .git writes even with --add-dir. Do not bypass the sandbox or copy GitHub secrets into prompts. The authorized Windows host account already has gh/GCM rights; the trusted SESHAT host runner (see ops/codex_watch/README.md) validates allowed paths, staged diff and credential patterns (without executing agent code), then performs Git commit, push and opens a DRAFT PR on Codex's behalf. The Codex worker itself remains sandboxed.

A successor issue may launch only after an explicit, independently reviewed, single-transition authorization: human/Implementation Lead engineering acceptance, manual predecessor merge, exact-head green current-main CI, task-issue body digest, finite allowed paths, reviewed ops bundle provenance and a separately approved `seshat:codex-ready` issue. No automatic merge, scientific-method approval or agent-invented tasks. **The historic PR16→issue17 transition is completed and must not be rearmed.** The generalized successor gate is backlog [#34](https://github.com/Stimurid/SESHAT/issues/34), not an activated queue. See [Inbox #6](https://github.com/Stimurid/SESHAT/issues/6).

Unreviewed Codex code must NOT be run under the privileged Windows account holding gh/GCM credentials. Tests and Ruff for autonomous handoffs belong to isolated GitHub PR CI. Passing CI still cannot authorize merge or scientific-method approval.
