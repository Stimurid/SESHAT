# Report-first worktree receipt — 2026-10-19

- WORKSPACE_MODE: Hub isolated Windows worktree (caller assigned).
- WORKDIR_ABSOLUTE: `C:\AI\llm\aiye-executor\worktrees\jx-831e2f3304cf`
- ORIGIN_URL: `https://github.com/Stimurid/SESHAT.git`
- CURRENT_BRANCH: `aiye/exec-831e2f3304cf`
- BASE_SHA: `a44a1a66996c18d9adcc87b6abb5f71392989ba0`
- BASE_TREE: `23c00c6cbeb0611111fdc95fc2043bf291b0232c` (caller pin).
- CURRENT_TASK: #55 report-first vertical; #58/#59 context not independently fetched.
- CURRENT_PR: none; no push or merge authorized.
- NEXT_GATE: Hub snapshot commit, isolated exact-tree tests, independent premium
  source review, and human science-method acceptance.
- BLOCKERS: GitHub #55/#58/#59/#6 and the two Drive scope documents were not
  readable via the available web route; `gh` absent. Python was unavailable
  (`uv trampoline failed to spawn Python child process: permission denied`);
  Docker daemon denied access to `npipe:////./pipe/docker_engine`.
- DRIVE_SYNC: MIRROR_PENDING; no write or readback attempted.

The donor files came from `4ac44d60dfc35b2bed549cd4a88dd15606098bef`
selectively; the current `corpus_host.py` was adapted without replacing the
F07/G1 access code. `git diff --check` returned 0. No Python tests, Ruff,
Docker smoke, CI, commit, SHA of a resulting commit, or independent review
were executed in this sandbox. The Hub must capture the working-tree snapshot
and the coordinator must run the exact snapshot in isolated CI before calling
this implemented or accepted.

Changed paths: `src/seshat/corpus_host.py`, `src/seshat/reports.py`,
`src/seshat/scientific_report.py`, `src/seshat/report_demo.py`,
`src/seshat/batch.py`, `src/seshat/batch_demo.py`, `tests/test_reports.py`,
`tests/test_batch.py`, `tests/test_scientific_report.py`,
`docs/F08_A_EXECUTABLE_REPORTS.md`, `docs/F09_A_REAL_BATCH.md`,
`docs/REPORT_FIRST_VERTICAL.md`, `docs/REPORT_FIRST_WORKTREE_RECEIPT.md`,
`Dockerfile.report`, `.dockerignore`. Rollback: revert the Hub's isolated snapshot; no
main/production/Drive state was changed.
