# SESHAT Codex Watchdog — operational receipt (2026-10-10)

**Mission:** close the missing finish/notify loop between an autonomous local Codex execution, the user, and the SESHAT Implementation Lead. This is an operational watchdog, not a semantic-method organ. No second repo or alternative runtime.

## Two independently scheduled layers

1. **Aorustim / Windows Task Scheduler:** task `SESHAT-Codex-Watch`, every **5 minutes**, current user `AORUSTIM\Homee`, launch command `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\Users\Homee\AppData\Local\SESHAT\watch\monitor.ps1`. Created 2026-10-10; manual `schtasks /run` produced Scheduler `LastTaskResult=0`. Watch script is read-only toward the repository, writes local machine state and transition events.
2. **ChatGPT Automation / condition_watch:** `SESHAT — Codex Watch`, **hourly**, enabled 2026-10-10. Each wake checks the local `state.json` and `exit.json` via connected Remote Desktop Commander (Aorustim) plus GitHub current PR/CI/issue, and notifies the user on meaningful terminal state, lost executor, failed CI, PR ready, or stalled execution. It does **not** auto-merge or auto-restart Codex.

**Security review hold:** the separate Windows task `SESHAT-Codex-Dispatch` is temporarily **DISABLED** while PR #18 is under review. Do not enable it from this worktree. It may be considered for manual re-enablement only after PR #18 is manually merged, the canonical `.github/workflows/ci.yml` push run succeeds on the then-current `main` SHA, and the installed bundle matches the reviewed PR #18 source hashes.

**Release provenance hold (S-OPS-PUBLISH-RECOVERY / #28):** branch
`fix/ops-publisher-recovery-20261011` is review source only and is **not deployed** to
the trusted-host runtime. The installed, reviewed PR #18 five-file bundle remains
untouched, and `SESHAT-Codex-Dispatch` stays Disabled. PR #26 is the separate
strict-mode bootstrap fix for issue #25; the generic next-release decision remains
separately held in issue #34. None of #28, #25/PR #26, or #34 authorizes a job
launch, installation, merge, semantic acceptance, or scheduler enablement.

**Do not confuse these:** the five-minute task detects local changes and saves durable local evidence; outbound ChatGPT notifications are at most hourly, not five-minute push notifications. A powered-off/sleeping Aorustim cannot run its local task; remote connectivity is a separate prerequisite. This is bounded supervision, not an always-on service guarantee.

## Installed local paths

- Source scripts (canonical recoverable copies in Git): [monitor.ps1](monitor.ps1), [run-codex.ps1](run-codex.ps1).
- Installed copies: `C:\Users\Homee\AppData\Local\SESHAT\watch\monitor.ps1` and `run-codex.ps1`.
- Current active job descriptor: `...\watch\job.json` (job ID, branch, issue, exec session ID, runner PID, start time).
- Current synthesized state: `...\watch\state.json` (state, checked_at_utc, branch, HEAD, dirty_file_count, runner, exit, local log paths).
- State transitions: `...\watch\events.jsonl` (append only, on transitions rather than every heartbeat).
- Runner full JSON stream: `...\watch\stdout.jsonl`; errors `stderr.log`; last Codex answer `last_message.txt`. **Keep these logs local**, not in public Git: logs may contain source snippets.
- Terminal exit receipt: `...\watch\exit.json`. A process disappearing without this is **not success**.

## Current S2A job

- Task: [S-IMPL-002A / issue #14](https://github.com/Stimurid/SESHAT/issues/14).
- Git worktree: `C:\projects\seshat`, branch `codex/s2a-coherent-blackboard-20261010`, starting SHA `4a58907cf55d5af408c61866103212e0320927fb`.
- Original interactive Codex CLI session was lost while five uncommitted files remained. Recovery used `codex exec resume` with the original thread ID and a separate, detached PowerShell supervisor; no files were reset. The parent wrapper writes `exit.json` in `finally`.
- Actual starting runner PID and session are stored in `job.json`. Do not hardcode the PID in future watchdogs.
- The runner has no permission to merge its own PR and no authority to change scientific method or start S2B.

## State vocabulary and alert semantics

| State | Interpretation |
|---|---|
| `RUNNING` | Registered PowerShell supervisor PID exists and command line matches `run-codex.ps1`; no terminal receipt yet. |
| `POSSIBLE_STALL` | Runner alive, but JSON output file unchanged for more than 120 minutes. Investigate; do not kill based on this alone. |
| `CODEX_EXITED_OK_VERIFY_OUTPUT` | Supervisor wrote exit code 0. Still verify Git commit, PR, tests, CI; a CLI success is not method or merge acceptance. |
| `CODEX_EXITED_ERROR` | Supervisor wrote nonzero exit code. Inspect safe receipt and selective logs. |
| `LOST_SESSION_DIRTY_WORKTREE` | No registered runner and no exit receipt, with changed repo files. Keep WIP; never assume completion or reset. |
| `LOST_SESSION_NO_EXIT_RECEIPT` | No runner and no exit receipt, clean repo. State unresolved; Git may show a commit/PR separately. |
| `BRANCH_MISMATCH` | Worktree branch changed relative to the registered job; do not certify run status until reconcile. |
| `WATCHDOG_ERROR` | Local script exception; writes safe exception type only, not raw errors or source text. |

State is a monitoring projection, not SESHAT scientific state. GitHub PR/CI is a separate independent witness. The watchdog itself only emits event records; the separate acceptance-gated dispatcher handles the one explicitly authorized next-task transition.

## Verify and recover

Run from an authorized PowerShell session on Aorustim (read only):

```powershell
schtasks /query /tn "SESHAT-Codex-Watch" /fo LIST /v
Get-ScheduledTaskInfo -TaskName 'SESHAT-Codex-Watch' | Select-Object LastRunTime,LastTaskResult,NextRunTime
Get-Content 'C:\Users\Homee\AppData\Local\SESHAT\watch\state.json' -Raw
Get-Content 'C:\Users\Homee\AppData\Local\SESHAT\watch\events.jsonl' -Tail 5
git -C C:\projects\seshat status --short --branch
```

The direct diagnostic `schtasks /run /tn "SESHAT-Codex-Watch"` is safe: monitor has read-only Git calls and writes only local monitoring files.

Before registering a new job, clear/reconcile the *previous job's terminal status*, archive its logs/receipt under a run-specific directory, and write a new `job.json`. Never silently erase dirty work or simply reuse a PID. The currently installed runner and monitor are **single-active-job**, not a multi-tenant concurrency scheduler.

## Authority / truth

- Local watchdog reads and records; it does not commit, push, merge, kill, or spawn Codex.
- Runner executes only a previously authorized bounded issue, writes complete local terminal receipts; code results go to an isolated Git task branch and PR.
- ChatGPT hourly automation sends condition-based notifications, avoiding duplicate alerts when possible; cloud automation scheduling and tool access can vary. It cannot provide hard real-time delivery.
- Implementation Lead reviews exact code and CI before merge, follows [S-COORD-001](https://github.com/Stimurid/SESHAT/issues/6). User retains semantic-method acceptance.
- All task/PR decisions return to Git; local logs and machine-specific task registration are operational witnesses. Do not call a source read, CLI exit, test pass or GitHub CI pass scientific acceptance.

## Automatic Codex publication and acceptance-gated dispatch

On Aorustim, GitHub CLI is already authorized as Stimurid via the Windows keyring and Git Credential Manager; repository push rights are verified. There is no need to install, disclose, or copy a token.

The normal Codex workspace-write sandbox refuses writes to .git even when the .git directory is explicitly added, and does not expose gh. Do NOT bypass the whole operating-system sandbox. Instead, the following trusted host scripts use the existing Windows account and its credentials:

- gate.ps1: pure authorization and security helpers. tests/test-gate.ps1 covers admission, entrypoint binding, exact manifests, publication verification and immutable-exit denial cases.
- task_queue.json: one preapproved mapping, PR 16 (S2A) to issue 17 (S2B).
- dispatch.ps1: dry run by default; -Apply is for the Windows scheduled task.
- execute-task.ps1: starts a bounded Codex CLI run with workspace-write, local JSON logging, no Git credentials and no Git writes. It rejects a noncanonical `JobPath`, missing/mismatched dispatch marker, altered job binding or installed-bundle drift before code execution.
- publish.ps1: the trusted host revalidates the same job/marker/bundle, requires the exact executor-owned dirty path set, scans the staged diff, commits/pushes, and creates or verifies a draft PR. It does not execute agent-produced tests; isolated GitHub PR CI runs pytest and Ruff. No automatic merge.
- reconcile-publish.ps1: read-only partial-publication readback. It reports the
  recorded stage, local branch/HEAD/dirty count, optional GitHub PR readback and a
  manual recovery instruction. It never resumes or retries publication.
- monitor.ps1: detects the new execute-task.ps1 runner as well as the legacy resume runner.

Admission requires ALL of: previous PR manually reviewed and labeled seshat:engineering-accepted; an exact-line comment `SESHAT_ENGINEERING_ACCEPTED_SHA=<40-hex reviewed PR head SHA>` authored by GitHub actor `Stimurid`; previous PR MANUALLY merged to main; PR #18 MANUALLY merged to main; successful GitHub workflow at exact path `.github/workflows/ci.yml`, repository `Stimurid/SESHAT`, event `push`, branch `main`, and exact current main SHA; preapproved next issue still open, labeled seshat:codex-ready, and byte-for-byte equal to its approved UTF-8 SHA-256 pin; one explicit mapping in task_queue.json; clean worktree; matching previous exit receipt; no duplicate branch or prior dispatch marker.

The label is intentionally insufficient by itself: if PR #16's head changes after review, the old SHA comment no longer admits it. A Codex worker cannot self-accept because only a comment returned by GitHub for the exact actor `Stimurid` and exact current PR head token is recognized. The operations code in PR #18 cannot authorize its own use: the gate rejects dispatch until GitHub reports PR #18 closed and merged.

`task_queue.json` contains the trusted-host-verified issue #17 body digest `541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8`. It was computed from the GitHub response value itself, without newline normalization or copy/paste:

```powershell
$next = gh api repos/Stimurid/SESHAT/issues/17 | ConvertFrom-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$next.body)
$sha = [System.Security.Cryptography.SHA256]::Create()
try { ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
finally { $sha.Dispose() }
```

The offline test pins this exact digest against accidental replacement. After admission, `task_prompt.txt` is written as exactly that approved issue body in BOM-less UTF-8: no dispatcher-authored prefix, suffix, or appended newline.

The queue also carries a finite S2B `approved_paths` set. After Codex exits, the trusted executor records the exact dirty set as `owned_paths`; publication requires `dirty paths == owned_paths` and every owned path to be in the reviewed queue set. A broadly allowlisted file such as `tests/unrelated.py` is rejected. The publisher never runs the proposed Python or tests under the credential-holding process.

The installed runtime bundle (`dispatch.ps1`, `gate.ps1`, `execute-task.ps1`, `publish.ps1`, and `task_queue.json`) must byte-match the repository files, remain unchanged between the merged PR #18 SHA and the dispatched main SHA, and carry its SHA-256 manifest inside the marker-bound job. Both execution entrypoints recheck this provenance. After push, publication succeeds only when GitHub reports the PR `OPEN`, draft, based on `main`, headed by the registered branch, and pointing to the just-pushed commit SHA. Existing `exit.json` is never overwritten; duplicate execution is rejected before the operational `try/finally`, and final creation uses create-new semantics.

Codex launch additionally requires a separately reviewed, host-owned
`C:\ProgramData\SESHAT\codex-launch-policy.json`. The repository deliberately
contains no release pin and cannot nominate a trusted binary. The v1 policy names
canonical absolute `node.exe`, Codex `bin\codex.js`, and `package.json` paths;
their allowed parent roots; SHA-256 values; exact `@openai/codex` version; and the
Authenticode signer thumbprint for Node. Dispatch fails closed if it is missing,
malformed, unsigned, outside its roots, or traverses a reparse point. Its complete
binding and policy hash are included in the job authorization digest. Execution
revalidates it, opens all three identity files without write/delete sharing,
rehashes them after locking, and retains the locks through process execution. PATH
shims, adjacent packages, direct executable fallbacks, and drifted pins are never
considered. A trusted operator must create/review this policy from independently
verified installation evidence; the sandbox and CI fixture must not be used as a
source of production pins.

The two labels are different independent permissions. Engineering acceptance does NOT mean scientific-method approval. Codex must never invent another task, import a donor wholesale, or modify the research ontology on its own.

Task S-IMPL-002B (#17) is prepared; current predecessor PR #16 remains draft/unmerged. Automatic dispatch is therefore BLOCKED until explicit review and merge. Do not apply the PR acceptance label merely because tests pass.

Operational state is stored locally in %LOCALAPPDATA%\SESHAT\watch: dispatch_state.json, dispatch_events.jsonl, job.json, exit.json, publish_receipt.json and per-run archived logs. The dispatcher creates a one-time gate marker under dispatches BEFORE spawning the worker to guarantee fail-closed recovery. A stale marker requires investigation; never delete it automatically.

### Publisher native-process and partial-stage recovery

The publisher and its parent invoke native Git/GitHub processes with stdout and
stderr captured separately and classify the explicit native exit code. Stderr on
an exit-zero command (for example a Git CRLF warning) is recorded as
`EXIT_ZERO_STDERR` in the per-job native audit and does not become a terminating
PowerShell error. Any nonzero native exit remains fail-closed. Audit records contain
only command labels, exit status, stderr presence/count/hash and classification;
they do not contain command arguments, diff bodies, tokens, or raw native output.

Long-running Codex output uses a separate bounded streaming path. While the child
is running, stdout is flushed directly to the private local `stdout.jsonl` and
stderr to `stderr.log`; neither stream is accumulated in PowerShell memory. The
files therefore retain a readable partial prefix after a child failure or host
interruption and their modification times remain useful to the watchdog. The
current hard limits are 64 MiB for stdout and 8 MiB for stderr. Reaching either
limit terminates the child fail-closed, retains the bounded prefix, records
`OUTPUT_LIMIT_EXCEEDED`, and cannot proceed to publication. Short Git/GH and
publisher-child commands continue to use the small buffered helper.

The private streaming audit records `STARTING` and exactly one terminal status
(`COMPLETED`, `NONZERO_EXIT`, `OUTPUT_LIMIT_EXCEEDED`, or `FAILED`) with exit code
when available, byte counts and paths, but never raw agent output. These local
agent logs must not be uploaded as GitHub artifacts or copied into issues/PRs.

The first failed publisher run for issue #28 returned an opaque `RemoteException`
and an empty publisher log. Its original exception stack was **not captured**.
An isolated synthetic probe reproduced the relevant Windows PowerShell 5 behavior;
that probe is evidence for the fix, not a reconstruction of the missing stack.

Each publication attempt has an append-only per-job stream under
`publication-events`. Journal and attempt writes call `FileStream.Flush(true)`
before returning, so an I/O or durable-flush failure stops the publisher before
the associated mutation. Before every `git add`, `git commit`, create-only push, and
`gh pr create`, it durably appends a v2 `INTENT` with job, attempt nonce, phase and
before-witness; native return is recorded as `RETURNED`; verified after-witness is
then recorded as `COMPLETE`. Any exception after the first intent records
`RECONCILIATION_REQUIRED`. A prior stream or receipt blocks automatic retry.
`exit.json` and `publish_receipt.json` use create-new semantics and are never
overwritten. Reconciliation reads the index, HEAD, remote ref and PR state and
reports an incomplete intent/return without mutating any of them.

Worker-amplifiable `git status --porcelain -uall` reads use separate byte-streamed
stdout and stderr caps (256 KiB and 32 KiB) and a 64-line ceiling. Output above
either ceiling or invalid UTF-8 fails closed; status is never accepted from a
truncated prefix. The reader retains at most 64 decoded records and preserves the
leading status-column whitespace. This applies in executor, publisher and
reconciliation paths.

Before staging, every owned regular file is constrained to 2 MiB and the total to
5 MiB, with repository containment and reparse-point denial. After staging, Git
blob sizes and regular-file modes are checked independently. Binary numstat is
denied. The staged patch is streamed to a private file with an 8 MiB ceiling and
scanned incrementally as strict UTF-8; added-line secret matching survives chunk
boundaries and neither shapes nor patch bodies enter public logs. Remote branch
and PR absence are checked before staging and again before publication. Push is
atomic and create-only using an empty-expected-OID force-with-lease; it cannot
overwrite a ref created before or during the attempt.

After this change is reviewed and deliberately installed, an authorized operator
handles an interrupted attempt by performing readback first:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File C:\Users\Homee\AppData\Local\SESHAT\watch\reconcile-publish.ps1 `
  -JobPath C:\Users\Homee\AppData\Local\SESHAT\watch\job.json
```

Recovery is deliberately manual and stage-specific:

- `PRECHECK`: no mutation was recorded; inspect the failed admission check before any new authorized attempt.
- `BEFORE_COMMIT`: inspect worktree and authorization evidence; do not rerun.
- `STAGED_ONLY`: inspect the index and exact allowed paths; do not commit blindly.
- `COMMITTED_ONLY`: verify the remote branch before any push decision.
- `PUSHED_WITHOUT_PR`: verify GitHub for an existing PR before any create decision.
- `DRAFT_PUBLISHED`: verify the existing draft and receipt; never create a duplicate.
- `RECONCILIATION_REQUIRED`: compare the last `INTENT`/`RETURNED` record with index, HEAD, remote ref and PR readback; never infer that the interrupted mutation did or did not happen.

Missing, malformed, mismatched, or stale publication receipts always fail the
executor. Reconciliation does not repair receipts, modify Git, call `gh pr create`,
or bypass the pinned SHA, bundle provenance, exact path manifest, credential diff
scanner, human acceptance, or disabled scheduler.

Windows Task Scheduler task SESHAT-Codex-Dispatch is a five-minute task distinct from the existing SESHAT-Codex-Watch task and from hourly ChatGPT notifications. It is temporarily **DISABLED for PR #18 review**. If it is later re-enabled after all security gates are satisfied, the machine must be awake/logged in for the local scheduled process to run.

Verification:
- powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ops\codex_watch\tests\test-gate.ps1
- powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ops\codex_watch\tests\test-publisher-recovery.ps1 (Windows PowerShell 5.1 quoting, UTF-8 and bounded streaming; isolated CI only)
- pwsh -File ops/codex_watch/tests/test-gate.ps1 (isolated GitHub Actions job; checkout uses `persist-credentials: false` and `contents: read`)
- pwsh -File ops/codex_watch/tests/test-publisher-recovery.ps1 (same synthetic publisher/streaming coverage under PowerShell 7; isolated Windows GitHub Actions only; no live GitHub calls)
- powershell -NoProfile -File C:\Users\Homee\AppData\Local\SESHAT\watch\dispatch.ps1 (safe dry-run)
- schtasks /query /tn SESHAT-Codex-Dispatch /fo LIST /v (must report disabled during PR #18 review)
- Inspect local dispatch_state.json and GitHub current HEAD/PR/CI.
- To stop automatic task dispatch: schtasks /change /tn SESHAT-Codex-Dispatch /disable

Implementation limitations: this first version handles ONE queued transition and ONE active job per Windows checkout; it is not a general self-programming scheduler. It preserves old job logs, never resets a dirty repository, never auto-merges, never self-certifies acceptance, and cannot work while the host is unavailable.

Security boundary: the trusted host publisher MUST NOT execute Codex-produced Python or tests while GitHub credentials are accessible. After an allowed-files/secret-pattern/diff check it opens a draft PR; isolated GitHub Actions CI runs both pytest and Ruff on the proposed branch. PR reviewers examine code and CI before manual engineering acceptance. The scanner detects common secret formats but cannot prove arbitrary content contains no sensitive data; review remains mandatory.

Review state for S-OPS-PUBLISH-RECOVERY #28 / PR #39 after this source change:
`CI_PENDING`. No local PowerShell or agent-authored test was executed on the
credential-bearing host; only isolated GitHub PR CI may supply test evidence.

The offline PowerShell gate test is pure simulation: it uses synthetic GitHub-shaped objects, performs no network calls, and asserts that the current branch, local branch refs, and worktree status are unchanged. Its negative cases include issue-body drift, a stale/wrong reviewed SHA, a wrong acceptance actor, a missing acceptance comment, unmerged PR #18, wrong-workflow success at the matching SHA, arbitrary job/marker binding, `tests/unrelated.py`, wrong PR head SHA, and byte-for-byte preservation of a pre-existing exit sentinel.
