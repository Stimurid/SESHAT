# SESHAT Codex Watchdog — operational receipt (2026-10-10)

**Mission:** close the missing finish/notify loop between an autonomous local Codex execution, the user, and the SESHAT Implementation Lead. This is an operational watchdog, not a semantic-method organ. No second repo or alternative runtime.

## Two independently scheduled layers

1. **Aorustim / Windows Task Scheduler:** task `SESHAT-Codex-Watch`, every **5 minutes**, current user `AORUSTIM\Homee`, launch command `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\Users\Homee\AppData\Local\SESHAT\watch\monitor.ps1`. Created 2026-10-10; manual `schtasks /run` produced Scheduler `LastTaskResult=0`. Watch script is read-only toward the repository, writes local machine state and transition events.
2. **ChatGPT Automation / condition_watch:** `SESHAT — Codex Watch`, **hourly**, enabled 2026-10-10. Each wake checks the local `state.json` and `exit.json` via connected Remote Desktop Commander (Aorustim) plus GitHub current PR/CI/issue, and notifies the user on meaningful terminal state, lost executor, failed CI, PR ready, or stalled execution. It does **not** auto-merge or auto-restart Codex.

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

State is a monitoring projection, not SESHAT scientific state. GitHub PR/CI is a separate independent witness. Watchdog emits event records when state/HEAD/dirty-count/exit-code changes; no automatic job chaining.

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

- gate.ps1: pure authorization check. tests/test-gate.ps1 covers admission and denial cases.
- task_queue.json: one preapproved mapping, PR 16 (S2A) to issue 17 (S2B).
- dispatch.ps1: dry run by default; -Apply is for the Windows scheduled task.
- execute-task.ps1: starts a bounded Codex CLI run with workspace-write, local JSON logging, no Git credentials and no Git writes.
- publish.ps1: the trusted host validates canonical repository, task branch, clean base, allowed file paths and tests before committing/pushing and opening a draft PR. No automatic merge.
- monitor.ps1: detects the new execute-task.ps1 runner as well as the legacy resume runner.

Admission requires ALL of: previous PR manually reviewed and labeled seshat:engineering-accepted; previous PR MANUALLY merged to main; successful GitHub workflow ci on current main SHA; preapproved next issue still open and labeled seshat:codex-ready; one explicit mapping in task_queue.json; clean worktree; matching previous exit receipt; no duplicate branch or prior dispatch marker.

The two labels are different independent permissions. Engineering acceptance does NOT mean scientific-method approval. Codex must never invent another task, import a donor wholesale, or modify the research ontology on its own.

Task S-IMPL-002B (#17) is prepared; current predecessor PR #16 remains draft/unmerged. Automatic dispatch is therefore BLOCKED until explicit review and merge. Do not apply the PR acceptance label merely because tests pass.

Operational state is stored locally in %LOCALAPPDATA%\SESHAT\watch: dispatch_state.json, dispatch_events.jsonl, job.json, exit.json, publish_receipt.json and per-run archived logs. The dispatcher creates a one-time gate marker under dispatches BEFORE spawning the worker to guarantee fail-closed recovery. A stale marker requires investigation; never delete it automatically.

Windows Task Scheduler task SESHAT-Codex-Dispatch runs every five minutes while Aorustim is available. It is distinct from the existing SESHAT-Codex-Watch task and from hourly ChatGPT notifications. The machine must be awake/logged in for the local scheduled process to run.

Verification:
- powershell -NoProfile -File C:\projects\seshat\ops\codex_watch\tests\test-gate.ps1
- powershell -NoProfile -File C:\Users\Homee\AppData\Local\SESHAT\watch\dispatch.ps1 (safe dry-run)
- schtasks /query /tn SESHAT-Codex-Dispatch /fo LIST /v
- Inspect local dispatch_state.json and GitHub current HEAD/PR/CI.
- To stop automatic task dispatch: schtasks /change /tn SESHAT-Codex-Dispatch /disable

Implementation limitations: this first version handles ONE queued transition and ONE active job per Windows checkout; it is not a general self-programming scheduler. It preserves old job logs, never resets a dirty repository, never auto-merges, never self-certifies acceptance, and cannot work while the host is unavailable.

Security boundary: the trusted host publisher MUST NOT execute Codex-produced Python or tests while GitHub credentials are accessible. After an allowed-files/secret-pattern/diff check it opens a draft PR; isolated GitHub Actions CI runs both pytest and Ruff on the proposed branch. PR reviewers examine code and CI before manual engineering acceptance. The scanner detects common secret formats but cannot prove arbitrary content contains no sensitive data; review remains mandatory.
