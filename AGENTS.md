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
- The first handed-off implementation task (unless already closed/superseded when you start) is [S-IMPL-001 / Issue #3](https://github.com/Stimurid/SESHAT/issues/3). Read the exact [Codex handoff](docs/CODEX_IMPLEMENTATION_HANDOFF_v0.1.md), then re-check actual `origin/main` and task status.
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

## Autonomous Codex completion watch

**Installed:** [ops/codex_watch/README.md](ops/codex_watch/README.md) and recoverable [monitor.ps1](ops/codex_watch/monitor.ps1) / [run-codex.ps1](ops/codex_watch/run-codex.ps1). Aorustim Windows task `SESHAT-Codex-Watch` checks local job state every **five minutes**, with state/transition/exit receipts under `%LOCALAPPDATA%\SESHAT\watch`; a separate **hourly ChatGPT condition-watch automation** reads this state and GitHub PR/CI and notifies on completion or failure. On re-entry, inspect `state.json` and `exit.json` before deciding whether an agent is still running. Do not infer completion from missing PID or green tests alone; do not confuse another process (e.g. Hestia) with the SESHAT runner. Watchdog scripts cannot accept scientific results, merge code or restart agents. Local monitoring is host-dependent, and a sleeping/offline Aorustim prevents five-minute checks.

## Execution truth

Creating a Git issue, handoff or agent instruction file does **not** start a Codex session. If no executor is running or attached to this checkout, report `READY_FOR_CODEX`, not `RUNNING`. Mark implementation complete only with a commit, PR, tests and CI evidence.
