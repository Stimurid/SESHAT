# QUINTA PRE-REPOSITORY BODY — PHYSICAL RECOVERY v0.2

Status: READ-ONLY LOCAL INSPECTION COMPLETED FOR BOUNDED HISTORICAL SLICE. This corrects the earlier UNKNOWN_HOLD for the existence of the local archive; complete semantic/prompt and runtime requalification remains open.

## Physical access and scope

Authorized remote device: timlenovo, read-only archive inspection.
Observed root: `C:\projects\Claude\TRIZ\`.
Observed directories:
- `inventive-memory-bench-mvp\` — physically readable Vite/TypeScript application, code, UI, knowledge and reports.
- `architecture\` — 12 early architecture documents + supporting texts.
- `triz-bot-claude-project_scaffold_v0_2026-05-09\triz-bot-claude-project\` — old corpus scaffold, manifest, prompt groupings and _READY_FOR_CLAUDE digests.
- `ТРИЗовец\` — original TRIZ/MTM PDF/text prompt sources.
- `prompt_sources\` — empty staging subfolders in an earlier audit; physical directories exist.
- Actual local Quinta: `C:\projects\quinta\`, branch main, HEAD `3963df4`; no local modifications made.

The archive dossier previously cited these roots but they had not been physically read. We now have direct directory/file witnesses, not a claim inferred solely from GitHub reports.

## Critical identity result: early MVP is a snapshot of the existing Quinta lineage

Local file content hash comparison of archive versus `C:\projects\quinta`:
- `src/logic/agentRuns.ts`: same SHA256 prefix `A917AE799460F544`; Git blob `e03b318abc9a7f08ce12137c1b3c58f5e38f060c`; unchanged in Quinta initial `b19465288` and main `3963df4`.
- `src/logic/kosmos.ts`: same SHA256 prefix `8A0CA23778206C1D`, unchanged initial and main.
- `src/promptImport/candidateExtractor.ts`: same SHA256 prefix `0F4FD77CA3E279BF`.
- `src/agents/agentRegistry.ts`: same SHA256 prefix `83BBBD52E2E701D5`.
- `src/components/PipelineBuilder.tsx`: Git blob unchanged from initial to current `3800213d1e478b80a047378680b034d4678d30d4`; local archive-vs-current diff only 2 additions/2 deletions (do not infer significant functional difference).
- `src/types/core.ts`: local archive blob `37a132a719b693e7e2f4af2e951fbfce64a5fc3e` = Quinta initial commit blob; current has grown (local 541 vs current 1119 text lines).
- `src/App.tsx`: local archive 3492 lines; its early code has `handleRunPipeline` around line 1425, run creation, state.history and PipelineBuilder. Current is ~4069 lines with analogous execution around line 1809. Older archive is a runnable-source snapshot, but no distinct stronger generic AgentRun has yet been evidenced.

Implication: blindly importing archived MVP code would primarily duplicate preexisting Quinta source. Its special value is the **historical interaction model, architecture, old feature wiring, and regression evidence**, not a missing `agentRuns.ts`.

## Early architecture independently read from the actual archive

`architecture/04_ORCHESTRATOR_MODEL.md`:
- Defines orchestrator as regulator of **field metastability**, not pipeline manager or single agent router.
- Tracks branch population, maturity distribution, constraints, contradictions, repeated operations, clusters and user events.
- Candidate actions: activate/deactivate agents, amplify productive conflict, suppress noise, switch L2 Space, launch/stop KOSMOS, request human judgment, propose self-reconfiguration.
- Warns against overgeneration, stagnation, premature convergence, echo chamber and user abandonment.
- This is a valuable **TARGET METHODOLOGICAL/CONTROL MODEL**, not proof that a tick-based orchestrator was implemented.

`architecture/05_AGENT_FOUNDRY.md`:
- Import chain Raw Prompt → Candidates → Review → AgentSpec → kernel + preserved full body → tests → compatibility → activation.
- Governed prompt changes and adversarial testing; full source-preservation requirement.
- Also makes a risky methodological assumption: deleting philosophical framing and targeting <500-token kernels. This must NOT be canonized for SESHAT's distributed semantic objects without ablation and source-authorized comparison.
- In `FOUNDATION_RUN_REPORT.md`, prompt import and scenario tests were explicitly **mock**, not a working extraction/validation pipeline.

`architecture/06_RUNTIME_FIELD.md`:
- States agent network is **NOT linear workflow**; runtime has field state, L2 Space, agent activation and append-only events.
- Tick loop: observe state → select agents → act → append versions/trace → gates → repeat/pause.
- Agent output is delta validated against allowed actions; source version/trace must survive.
- This is a potential SESHAT alternative-topology donor with applicability caveat: TRIZ creative-field concepts are not automatically the ontology of research corpora.

`architecture/08_SELF_RECONFIGURATION.md`:
- Agents may PROPOSE prompt/scope/activation/deprecation changes but cannot silently rewrite own prompts, delete tests, remove gates, widen permissions or erase provenance.
- Proposals require automated checks, meta-agent review and human approval for structural changes.
- Candidate donor for SESHAT MethodBody/OperationSpec governance, still at historical spec level.

`architecture/09_TESTING_AND_VERIFICATION.md`:
- Scenario designs for Human Flight, 20km Drone, 100-player Game and negative tests against trivial solutions, quality gates, agent activation and overgeneration.
- The older `ACCEPTANCE_FILE_AUDIT.md` checks file existence; `FOUNDATION_RUN_REPORT.md` says TypeScript/build succeeded but agent ops/KOSMOS/import/scenario tests remain mock.
- DO NOT upgrade this evidence to real agent orchestration PASS.

## Critical cross-profile comparison

SESHAT must NOT use early Foundry's simple 'strip philosophy → kernel <500 tokens' as a universal method for Sechenovka authorabstract Object, Method or other distributed objects. Source-authorized historical method bodies may rely on full document/reread/cross-section reconstruction. Foundry is instead a valuable:
1. versioning/governance design donor;
2. negative/ablation candidate for prompt compression;
3. test-spec and provenance pattern.

Early non-linear tick orchestration can be included as an **additional topology hypothesis** alongside current SESHAT T1–T4, conditional on actual applicability, but not as evidence that an executable shared runtime exists.

## Updated disposition

- `AgentRun` old MVP: **ALREADY_PRESENT_IN_QUINTA / NO_DUPLICATE_IMPORT**.
- `PipelineBuilder`: **ALREADY_PRESENT_IN_QUINTA / UI-REACHABILITY-AUDIT**, not code extraction from duplicate snapshot.
- `FieldMetastabilityOrchestrator`: **SPEC_DONOR / TEST_HYPOTHESIS / NOT_IMPL_PROVEN**.
- `AgentFoundry`: **WRAP/EXTRACT GOVERNANCE DESIGN**, mock extraction noted; compression to 500-token kernel is **NOT AUTHORIZED** as SESHAT default.
- `RuntimeEvent / Patch / AgentSpec governance`: **DESIGN DONOR**, current code can be checked separately against type/schema/dispatch, including forbidden mutations and actual enforcement.
- `Original TRIZ/MTM prompt sources`: **PHYSICALLY_PRESENT / CONTENT_RECOVERY_PENDING**.
- `Pre-Quinta user-interaction modalities and hidden UI`: **REGRESSION TEST DONOR / ROUTE REQUALIFICATION PENDING**.

## Builder handoff

Do not create a second AgentRun skeleton based solely on Quinta's most recent top-level UI or on the legacy dossier. There is a real old/current implementation to wrap or compare. Inspect actual `handleRunPipeline`, `agentRuns.ts`, RunPolicy enforcement, W7 and W9 before building portability.

Preserve possibility of nonlinear event/field scheduling and reciprocal reconstruction in SESHAT. Never make a universal irreversible cutter/prompt-compression pipeline.

## Further work

- Recover read-only corpus originals and import-genealogy from scaffold; distinguish raw original, conversion, duplicate and accepted candidate.
- Historical UI reachability graph: archive App vs current App routes, formerly active versus legacy-hidden.
- Historical test requalification at pinned refs, including W7/W9 and policy guards; no code imports before result.
- Other donors: same multi-generation standard, not only present HEAD.
