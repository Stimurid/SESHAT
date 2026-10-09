# CODEX HANDOFF — SESHAT S-IMPL-001: Truthful Source Access

**Status:** READY FOR CODEX IMPLEMENTATION; **NOT EXECUTED** by the author of this handoff.  
**Date:** 2026-10-09  
**Home:** [Stimurid/SESHAT](https://github.com/Stimurid/SESHAT). No other repository.  
**Planning artifact:** [SESHAT_IMPLEMENTATION_PLAN_v0.1.md](SESHAT_IMPLEMENTATION_PLAN_v0.1.md).  
**Inspected executable baseline:** `main@d0b324ed78057dea5c39bbb4de8176ec01c34c91`; subsequently a documentation-only planning commit `4288c2398e9b889aa532b2070607327f1ac31ec9` was created. **Fetch current main and record its actual SHA before coding.**
**Known CI:** [run 37982798112](https://github.com/Stimurid/SESHAT/actions/runs/37982798112) = SUCCESS for prior docs-only HEAD, not proof of the new S1 code.

## 0. MANDATORY WORKSPACE BOOTSTRAP — BEFORE ANY CODING

**This is an executable preflight gate, not a suggestion.** The handoff is not complete until Codex identifies an actual writable checkout and reports its absolute path, origin and HEAD. A GitHub issue or document by itself does **not** launch Codex or attach a workspace.

- **Canonical origin:** `https://github.com/Stimurid/SESHAT.git`; **the only implementation repository**.
- **Intended Windows local checkout:** `C:\projects\seshat` (already named in README and workstream docs; its presence on the user's disk has **not** been independently verified here).
- **Cloud Codex / non-Windows runner:** use the runner-provided checkout for `Stimurid/SESHAT`. Do **not** try to access `C:\projects\seshat` from Linux or create a fictitious Windows path. If no checkout is provided but cloning is available, clone into a real runner workspace and report the resulting absolute path. The user's local Windows folder will not be modified by cloud cloning.
- **Windows local Codex:** use exactly `C:\projects\seshat`. If a correct Git checkout already exists, reuse it. If the folder is absent, clone the canonical origin to **that path**. If the path exists but is non-Git, another repository, or dirty/conflicted, **do not delete, reset, stash, overwrite, relocate, or silently clone somewhere else**; report `BLOCKED_WORKSPACE` or the existing uncommitted state for safe resolution.

**Windows PowerShell preflight (execute on the actual Windows host, not in cloud):**

```powershell
$root = 'C:\projects\seshat'
$canonical = 'https://github.com/Stimurid/SESHAT.git'
$allowed = @(
  'https://github.com/Stimurid/SESHAT.git',
  'https://github.com/Stimurid/SESHAT',
  'git@github.com:Stimurid/SESHAT.git'
)
if (-not (Test-Path -LiteralPath $root)) {
  New-Item -ItemType Directory -Path (Split-Path -Parent $root) -Force | Out-Null
  git clone $canonical $root
  if ($LASTEXITCODE -ne 0) { throw 'BLOCKED_WORKSPACE: clone failed' }
}
$top = git -C $root rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED_WORKSPACE: not a Git checkout' }
if ([IO.Path]::GetFullPath($top).TrimEnd('\') -ine [IO.Path]::GetFullPath($root).TrimEnd('\')) {
  throw "BLOCKED_WORKSPACE: Git root is $top, expected $root"
}
$origin = git -C $root remote get-url origin
if ($LASTEXITCODE -ne 0 -or $origin -notin $allowed) {
  throw "BLOCKED_WORKSPACE: unexpected origin $origin"
}
git -C $root status --porcelain=v1
git -C $root branch --show-current
git -C $root rev-parse HEAD
git -C $root remote -v
```

**After preflight in either environment:**

1. State `WORKSPACE_MODE = WINDOWS_LOCAL | CLOUD_CHECKOUT | OTHER_CHECKOUT` and exact `WORKDIR_ABSOLUTE`.
2. State `ORIGIN_URL`, `CURRENT_BRANCH`, `HEAD_SHA`, `DIRTY_STATUS`. Verify that the checkout is genuinely `Stimurid/SESHAT`, not a similarly named unrelated directory.
3. If dirty or another implementation executor is active in that directory/branch, do not overwrite their changes. Coordinate a distinct working tree/branch only with explicit safe isolation; otherwise `BLOCKED_WORKSPACE`.
4. When clean and correctly bound, `git fetch origin`, create `codex/s1-source-access` from the **actual latest** `origin/main` (or a collision-free task branch), and perform the numbered S-IMPL-001 steps below.
5. If the environment has no filesystem, Git checkout or write permission, return `BLOCKED_WORKSPACE` with the missing capability. **Do not report CODING_STARTED, CODE_WRITTEN or PR_CREATED.**

The first Codex message/receipt must include the four identifiers above. Do not start code changes before this gate passes.

## 1. Your identity, assignment and execution ownership

You are **Codex acting as the exclusive implementation executor** in the SESHAT workstream. Hephaestus provides engineering direction and reviews acceptance; the user owns methodological and consequential decisions. You may edit code/tests and raise a PR; do not create a second repo, rewrite all architecture, or ask the user for already known context.

Read **completely**, in this order:

1. [WORKSTREAM_COORDINATION_v0.1.md](WORKSTREAM_COORDINATION_v0.1.md) — separate implementation / archaeology / Indago; only implementation owner edits executable core.
2. [SESHAT_IMPLEMENTATION_PLAN_v0.1.md](SESHAT_IMPLEMENTATION_PLAN_v0.1.md) — roadmap and precedence, especially S1/S2/S3.
3. [IMPLEMENTATION_CHARTER.md](IMPLEMENTATION_CHARTER.md) — method-neutral, no mandatory linear cut pipeline.
4. [DONOR_IMPLEMENTATION_CENSUS_v0.1.md](DONOR_IMPLEMENTATION_CENSUS_v0.1.md) — provisional coverage status and code witnesses.
5. [QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md](QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md) — old Quinta-specific AgentRun exists; generic release capability unproven.
6. `src/seshat/contracts.py`, `adapters/base.py`, `adapters/records.py`, `adapters/testing.py`, `runtime.py`, `blackboard.py`; `profiles/sechenovka_authorabstract/operations.py`; tests and CI workflow.
7. Existing [QH-01](https://github.com/Stimurid/SESHAT/issues/1) and [Drive/Git drift #2](https://github.com/Stimurid/SESHAT/issues/2). Do **not** duplicate them.

**Do not redo the seven-line donor audit.** It is a separate evidence stream; S1 concerns currently owned SESHAT contracts and code.

## 2. Facts and exact defect to repair

At the inspected baseline:

- `SourceCarrier` contains source identity/version/media type/URI/metadata but has **no content-read capability** by itself.
- `SourceProvider.get_carriers()` returns metadata objects. `OperationProvider.execute(spec, research_object, observations, prior_state)` has no source handle.
- `Runtime._enforce_access()` checks only that all expected carrier IDs appear in `get_carriers()` if `raw_access_policy == FULL_REQUIRED`. It can PASS without reading a single source character.
- `tests/test_runtime.py::test_full_required_runs_with_carrier_and_keeps_working_status` currently passes using only carrier metadata. This test records the **old bug** and must be revised to require actual readable content.
- `Observation` is a non-sovereign addressing device; `DerivedObject` defaults to `WORKING`. Preserve both laws.
- `Object` / `Method` are *declarations*, not implemented historical prompts. `OperationSpec.dependency_ids` is not yet a reconciliation scheduler.

**Desired outcome:** source-access contract and runtime enforce the *real accessibility, integrity and policy of input content* rather than the existence of a carrier record. Semantic operations will then be able to read (or acquire source-addressed access to) complete authorized source packages. This is the smallest critical foundation for later Object↔Method reconstruction.

## 3. Task bounds

### In scope (S-IMPL-001)

1. Design a minimal typed **source content access** port/handle that is distinct from source identity metadata and distinct from observations. Choose a coherent API after reading the current code. It may use `SourceContentProvider`, `SourceReadHandle`, or equivalent. Document the choice in a concise engineering note/ADR.
2. Allow full access to a carrier's authorized bytes/text and bounded read-by-address, with exact `carrier_id`, source `version`, media/content status and integrity information (e.g. SHA-256 of bytes + byte length; use normalized text checks only with explicit lineage). Do not claim arbitrary PDF/OCR parsing exists; unsupported formats fail visibly.
3. Enforce the three `RawAccessPolicy` meanings:
   - `FULL_REQUIRED`: every *declared* source carrier is actually retrievable/fully addressable and validates version/integrity; fail closed if a source is missing, inaccessible, unauthorized, unreadable, partial or hash-mismatched. The operation provider must genuinely be able to inspect the complete source, not a title/snippet/observation proxy.
   - `DRILLBACK`: source spans can be requested explicitly, with locator bounds, version checks and a trace/receipt; allow observation-first work without silently implying whole-source verification.
   - `NEVER`: the operation receives no raw access; a raw-content request fails.
4. Make `OperationProvider` able to use the source-access interface when permitted, with a deterministic fake provider in tests that checks the actual content seen. Favor a minimal additive/compatibility-conscious change rather than replacing every API in one PR.
5. Record an **inspectable run/source access manifest or receipt** (at least in the returned/result-side structured evidence or a testable separate run object) identifying actual carrier versions, content hashes, read status, errors and access policy. It must not log raw sensitive content. If full durable persistence is out of S1 scope, say so and do not claim it.
6. Ensure failure occurs before persistence of a misleading `DerivedObject`. A missing raw source must not silently fall back to a guessed document.
7. Preserve metadata/observations as evidence addresses, never as acceptance or canonical scientific truth. Existing green tests may require updates but should not be weakened.

### Not in scope

- Do not build a new platform or a second SESHAT architecture.
- Do not implement `Object`/Agent-0 semantic prompts in this PR, nor `Infrastructure`/Novelty/Limitations.
- Do not invent a Cutter Core or impose `cut → derive → analyze` on all operations.
- Do not replace Pydantic, Python runtime, repository layout, or CI without evidence and necessity.
- Do not copy LitOps/Socrates/Quinta/D20/PRAGMA/Paideia code wholesale.
- Do not implement a second Indago; keep ResearchNeed/EvidenceReturn boundaries.
- Do not add real authorabstract, patient or protected methodology text to this **public** Git repo.
- Do not mistake a content-availability guard for full methodological coverage of a large source by an LLM; that later step needs traceable operation evidence.
- Do not let a model accept results, synthesize human approval, or change epistemic status on its own.

## 4. Execution protocol

1. `git fetch origin`; inspect `origin/main`, `git status`, tests and source. If main has advanced, rebase the plan on the actual head; do not silently reset anyone's work.
2. Start a feature branch, e.g. `codex/s1-source-access`. Do not directly push unreviewed executable changes to `main`.
3. Run the existing baseline: `python -m pip install -e ".[dev]"` then `python -m pytest -q`; record result and existing failures.
4. First add **negative tests that fail under old behavior**. Only then implement the smallest coherent source-access change. Prefer a read-only memory/record test adapter and an interface that future LitOps/Drive/FS adapters can satisfy.
5. Update source-access contracts, runtime, adapters and tests as one coherent change. Preserve current fixtures unless they encode the bug. Add a short ADR in `docs/` explaining hash/version, raw-policy semantics and compatibility.
6. Run complete tests and static checks (`python -m pytest -q`, `python -m ruff check .` if applicable). Run a source-read negative-path demonstration with exact test names.
7. Review diff for leakage, fake full-read, unbounded memory exposure and authority promotion. Commit/push the branch; open a PR with scope, tests, risk, rollback and links. Return commit/PR/CI URLs and exact limitations.

**Permitted primary paths:** `src/seshat/contracts.py`, `src/seshat/adapters/base.py`, `src/seshat/adapters/records.py`, `src/seshat/adapters/testing.py`, `src/seshat/runtime.py`, `tests/test_runtime.py`, new focused tests and a documentation ADR. Touch `blackboard.py` or Sechenovka profile only if a minimal S1 contract integration demands it; explain why. Avoid modifying `README`/coordination unless the relevant owner accepts the diff. No Drive write in this task.

## 5. Mandatory tests (names illustrative; behavior mandatory)

Construct **synthetic** corpus fixtures where title/metadata/observations are insufficient and evidence is distributed across two sections or two source carriers. Required cases:

| ID | Case | Expected |
|---|---|---|
| S1-T01 | FULL_REQUIRED with carrier metadata only | Block before provider invocation: CONTENT_UNAVAILABLE or equivalent. |
| S1-T02 | FULL_REQUIRED with valid readable content and exact versions/hash | Provider can read whole source; return remains `WORKING`, carries source receipt. |
| S1-T03 | Two declared carriers; only one has content | Block; no partial semantic result. |
| S1-T04 | Same carrier ID but wrong version/content digest | Block with explicit SOURCE_DRIFT / INTEGRITY_ERROR. |
| S1-T05 | Truncated/snippet-only resolver pretending to be complete | Block rather than silently certify complete access. |
| S1-T06 | DRILLBACK over a valid bounded source address | Return exact authorized span and versioned locator; record access. |
| S1-T07 | DRILLBACK out-of-range or wrong-carrier address | Reject, do not silently clamp. |
| S1-T08 | NEVER policy with an operation trying raw fetch | Deny; observation-only path may still work if allowed. |
| S1-T09 | Unsupported/missing medium or reader | Fail with typed status; do not fabricate text or OCR. |
| S1-T10 | Original observation/candidate objects | They remain non-sovereign; no implicit acceptance. |
| S1-T11 | Current happy-path and idempotent/repeated fake reads | No silent change to returned source bytes/hash; no unauthorized side effect. |
| S1-T12 | Provider raises/read error after metadata resolved | No misleading DerivedObject persisted; failure/attempt trace retained if designed. |

Tests must also prove that the provider can **access actual source contents**, not merely the carrier IDs. If an API design cannot satisfy both safe DRILLBACK and FULL_REQUIRED, document the failure and do not declare PASS.

Use clear structured exceptions; names may differ, but users and orchestrators must be able to distinguish `missing carrier record`, `missing contents`, `version mismatch`, `digest mismatch`, `unauthorized`, `unsupported`, `partial source` and `policy denied`. Avoid catching every exception and continuing.

## 6. Acceptance criteria and evidence return

`S-IMPL-001 = PASS` only if all are true:

- All currently supported source classes honor their `RawAccessPolicy`; FULL_REQUIRED cannot PASS from metadata alone.
- No runtime path lets a SourceAddress/Observation masquerade as the full underlying content.
- Source provenance and a real read/availability receipt are inspectable.
- Old tests remain meaningful, with the metadata-only false positive explicitly reversed.
- Regression + new negative tests pass in CI for the final PR HEAD.
- The PR contains a design note and a concise rollback plan.
- No original private/author-owned material was copied into public source or test fixtures.
- No S2/S3 semantic acceptance is claimed from S1 tests.

**Required Codex report (commit to Git as PR/receipt, not only a chat message):**

```
S-IMPL-001 RESULT
REPO / BASE_SHA / HEAD_SHA:
BRANCH / PR:
FILES MODIFIED:
API & POLICY CHOICES:
TESTS ADDED + COMMANDS + RESULTS:
CI RUN URL / CONCLUSION:
SOURCE ACCESS MATRIX (FULL_REQUIRED, DRILLBACK, NEVER):
PROVENANCE/READ RECEIPT WITNESS:
KNOWN LIMITATIONS:
ROLLBACK:
NEXT OWNED ACT OR NAMED BLOCKER:
```

If a necessary methodological source is unavailable, separate `S1 contract implementation` from `S3 source-method binding`. Do not block S1 to invent missing material.

## 7. Subsequent work — do not silently start it in the first PR

**S-IMPL-002:** provenance-aware coherent `Blackboard` views, selected working/current and STALE exclusion; explicit `OperationSpec.dependency_ids` admission into a bounded mutual Object↔Method reconciliation controller; `APORIA` and no-infinite-loop tests.

**S-IMPL-003:** source-authorized method-body resolution and version pinning, a typed non-sovereign `ModelProposer`, full-body Object and Agent-0 execution on synthetic then approved real cases, human-review gate.

**S-IMPL-004:** Infrastructure/Novelty/Limitations and the first comparable topology evaluation; external novelty requires explicit research evidence, not self-certification.

**Donor adapter tickets:** only after specific archaeological provenance returns. Follow the corrected all-generation census, especially Quinta's actual old AgentRun and negative regressions. No blanket import.

## 8. Source-method pointers for later S3

`profiles/sechenovka_authorabstract/operations.py` already contains `implementation_ref` pointers:
- `AGENT_OBJECT_CORE` → [SOURCE — AGENT_OBJECT_CORE](https://drive.google.com/file/d/1zzxvEy88Fz61rMJAyUZEr9R3pvIQiCxcHn2ubPS_Pt8/view).
- `AGENT_0_METHOD_SECTION_EXTRACTOR` → [SOURCE — Agent 0](https://drive.google.com/file/d/1LLKU0nC6sVBc34dR_wJSCQF2JCckI2x5oOoo-oN6PdE/view).

The original Object body distinguishes named/formal object, functional object and material; the Method body reconstructs dispersed procedures and instruments across the full text. These are read-only provenance pointers, **not** authorization to republish full text in this public Git repo. If access to them is absent, preserve exact refs and return `SOURCE_BODY_UNAVAILABLE`.

**No fake completion:** until code + tests + PR evidence exists, this handoff is only a task contract.
