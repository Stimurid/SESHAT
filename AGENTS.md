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

## Invariants

- Do **not** replace this repository with a new scaffold. Extend existing Pydantic contracts, minimal runtime, adapters, blackboard and tests.
- No universal mandatory `cut → derive → analyze` pipeline. Source-addressing observations are **not semantic truth**. Method-specific operations can need complete original source and prior states.
- `FULL_REQUIRED` must validate **actually readable, complete, version-consistent source content**, not just a SourceCarrier metadata record. `DRILLBACK` must be source-addressed; `NEVER` must deny raw access.
- Preserve semantic authority of host systems and human-only decisions. A green CI build cannot self-certify scientific methodology.
- No private research, medical or author-owned prompt bodies in this public Git repo without explicit authorization.
- Donor capabilities require source- and generation-pinned implementation evidence. See [Donor census](docs/DONOR_IMPLEMENTATION_CENSUS_v0.1.md) and [Quinta archaeology](docs/QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md). Do not repeat archaeology as a substitute for the assigned code.
- Git is the current verified code/durable handoff surface; do not assert Google Drive synchronization without successful write and readback.

## Execution truth

Creating a Git issue, handoff or agent instruction file does **not** start a Codex session. If no executor is running or attached to this checkout, report `READY_FOR_CODEX`, not `RUNNING`. Mark implementation complete only with a commit, PR, tests and CI evidence.
