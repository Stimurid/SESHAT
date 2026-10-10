# HEPHAESTUS operations security fix receipt

Date: 2026-10-10
Scope: PR #18 branch `ops/codex-automatic-handoff-20261010` only
Base: `b55a7ec87306e537df52b64d9f08dfd5987ebb03`

## Result

- O1: `task_queue.json` schema v2 requires the trusted-host-verified UTF-8 SHA-256 `541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8` for the exact live issue #17 body. `dispatch.ps1` downloads the live body, the pure gate compares its digest, and the prompt writer emits only that body as BOM-less UTF-8 with no added newline.
- O2: PR #16 admission requires the existing label plus an exact `SESHAT_ENGINEERING_ACCEPTED_SHA=<current PR head SHA>` line in a PR comment whose GitHub actor is exactly `Stimurid`. Missing comment, wrong actor, stale SHA, invalid head SHA, non-main base, or absence of manual merge fails closed.
- O3: admission also requires PR #18 itself to be closed and merged and requires successful `ci` for the current remote main SHA. Documentation records `SESHAT-Codex-Dispatch` as temporarily disabled for review; this worktree did not enable, install, or run it.
- O4: `ops/codex_watch/tests/test-gate.ps1` is offline and synthetic. It covers issue-body drift, stale acceptance SHA, wrong actor, missing comment, unmerged ops PR, and main-CI mismatch, then verifies no current-branch, branch-ref, or worktree-status change.
- O5: a green run is accepted only for canonical path `.github/workflows/ci.yml`, repository `Stimurid/SESHAT`, event `push`, branch `main`, and the exact current-main SHA. A same-SHA success from another workflow is denied.
- O6: both execution entrypoints require the canonical local `job.json`, a matching preapproved dispatch marker, exact issue/base/branch/job bindings and authorization digest. The installed five-file operations bundle must match the repository bytes and remain unchanged from the merged PR #18 SHA through the dispatched base SHA.
- O7: the queue records the finite approved S2B paths. The executor records the exact post-run dirty set; the publisher requires exact equality with that owned manifest and rejects all extras, including another syntactically allowlisted Python test. No proposed Python/tests are executed by the credential-holding publisher.
- O8: after push, GitHub must report an OPEN draft PR with base `main`, the registered head branch and the just-pushed SHA. The publication receipt records and the executor verifies `job_id`, issue, PR number, branch, SHA and verified PR state.
- O9: duplicate execution checks `exit.json` before the receipt-writing `try/finally`, and final receipt creation uses atomic create-new semantics. The offline sentinel test proves a pre-existing binary receipt remains byte-for-byte unchanged.
- Boundaries: no secrets or credentials are placed in dispatcher-authored prompts or receipts; `publish.ps1` remains draft-PR-only. No scheduler generalization, ontology, profile, scientific-method, deployment or runtime-domain changes were made.

## Verification

Command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/codex_watch/tests/test-gate.ps1
```

Observed result:

```text
PASS: offline O1-O9 authorization/denial cases; no branch, worktree, or exit-sentinel side effects
```

Windows PowerShell completed the suite locally. PowerShell 7 (`pwsh`) is not installed in this sandbox, so the added Ubuntu GitHub Actions `pwsh` job remains the independent cross-platform witness after trusted-host publication.

## Review hold

The live issue digest is now pinned. PR #18 still requires human review, merge and canonical current-main CI. The installed operations bundle must then be copied from and verified against that merged source before any manual scheduler re-enablement decision. Do not enable the dispatcher as part of this change.

No Git commit, push, `gh` invocation, scheduler mutation, primary-workspace edit, or installed-script edit was performed by this Codex worktree.
