# QUINTA MULTI-GENERATION DONOR ARCHAEOLOGY — v0.1

**Status:** CODE-GROUNDED / FIRST HISTORICAL PASS. Not a full audit of inaccessible local archives.  
**Purpose:** Correct SESHAT donor census selection bias. "Latest main" is not the historical implementation universe. Rejected/superseded versions are evidence and potential component donors, although rejection reasons remain binding until explicitly reconsidered.

## Fundamental correction

The previous SESHAT statement "**generic AgentRun is not implemented**" was too broad and misleading. A **Quinta-specific AgentRun implementation is present and already existed at the initial Quinta commit**, while a *cross-project, provider-neutral, enforceable generic execution service* is not demonstrated.

At `Stimurid/quinta@3963df4b8fb693be5cf46cc75aee0dd1372deade`:
- `src/types/core.ts`: `AgentRun`, `RunProfile`, `RunPolicy`, `RunBudget`, `HypothesisTrack`, `RunReport`, `RunTraceGraph`, `createAgentRun`.
- `src/logic/agentRuns.ts`: `createKosmosAgentRun`, `createSingleMethodRun`, `summarizeAgentRun`, `archiveAgentRun`.
- `src/components/RunLauncher.tsx`, `PipelineBuilder.tsx`, `RunsPanel.tsx`, `RunInspector.tsx` and `RunTraceStudio.tsx`.
- `src/App.tsx`: actual `handleRunPipeline` (~lines 1809–1969), branching/cycle execution, max-steps and max-branch-factor guards, stored run history; actual KOSMOS and single-method run creation (~lines 631, 820).
- `knowledge/03_AGENT_RUN_MODEL.md`: current in-repo explicit matrix of ENFORCED vs TYPE_ONLY policy/budget capabilities; `knowledge/07_ARCHIVE_DEMOTED_IDEAS.md`: reasons for consciously demoted models.

Thus `AgentRun` is not simply an unrealized diagram. Its generalized *scope and guarantees* are incomplete. This distinction changes the extraction decision.

## Historical genealogy: multiple non-equivalent generations

| Historical stratum | Verified carrier / pin | Recoverable mechanisms | Limit / status |
|---|---|---|---|
| PRE-QUINTA legacy roots | Historical dossier: `C:\projects\Claude\TRIZ\inventive-memory-bench-mvp/`, `architecture/`, `TRIZovec/`, scaffold `_READY_FOR_CLAUDE/` | Original ontology, 12 architecture files, agent tiers, agent foundry, KOSMOS tick-oriented field, corpus/prompts, pre-Quinta MVP UI | **HISTORICAL DOCUMENT WITNESS ONLY.** Legacy physical code/files not read here; not independently Git-hosted in known Stimurid inventory |
| Initial Quinta | `Stimurid/quinta@b19465288` (initial repository commit) | AgentRun types + factories; KOSMOS profile/strategies; pipeline builder; agent operations; preview/apply; first UI | **CODE WITNESS.** Some constructs static/deterministic; old scope is branch/system |
| Recovery / Guided Invention | `d15b3a899` → `e4cd83748` | 36 Case-1/2/3 contracts; EventLog; objects/constraints/contradictions; Work Orders; agents graph; surface registry; provenance; legacy UI restoration | **CODE + historical acceptance dossier**. Not all original TRIZ raw prompt bodies were imported |
| Spindle and Run Trace | `036bea7a1` (Run Trace Studio); `SPINDLE_REGRESSION_ROOT_CAUSE.md` | Execution graph/reporter, visual machine and system operator, multiple previous integrated UI surfaces | **MIXED:** replacement shells caused actual UX/product regression; many old components continued to exist but were not wired |
| Auto-to-N / Run Control | `c99b00851` (W4); `a8184aaa` (W5); `5b05eae4` (W7d) | Deterministic multiple-solution pipeline, RunControlConfig, budgets, feedback-to-constraint, lifecycle guard, bounded execution and verification | **CODE WITNESS**, some guard states warning/diagnostic; policy enforcement partial |
| W8 case/field/forest | ~`794c81487` → `679040f6` | Real field-backed Auto-to-N, CaseCompiler, problem field, solution forest, reviewed seed mutation, engineering packets | **CODE + smoke paths**, domain-specific |
| W9 corpus/evolutionary swarm | `7f9a6e31` (W9.0), then main `3963df4` | `trizCorpus.ts` operator selection; `agentSwarm.ts` bounded parallel mutation; `fitnessEvaluator.ts` scoring and diversity; `runAutoToNSwarm.ts` orchestrator; history/smoke tests | **CODE WITNESS**; user-facing UI later consolidated, not proof of universal run kernel |
| Superseded/rejected V2/V2.1, alternative UI routes | `knowledge/07_ARCHIVE_DEMOTED_IDEAS.md`, `CASE_1_MICRO_PRESENCE_CANONICAL_V2*`, `CASE_2_3_DELTA_ADDENDUM_TO_CASE_1_V1_1.md`, `REMOVED_TOP_LEVEL_TABS_MAP.md` | Alternative ontological and UI layouts, historical stage contracts, negative regression tests and design rationales | **DO NOT promote rejected versions to canonical semantics**; retain as donors and counterexamples |

### Git-history coverage

Inspected default-branch commit history in four pages from initial May commit to June main; compared recursive trees at ten cuts:
`b19465288`, `d15b3a899`, `036bea7a1`, `c99b00851`, `a8184aaa`, `5b05eae4`, `686208f69`, `7f9a6e31`, `90009b57`, `3963df4b`.
Five named heads appear in GitHub: main, quinta-workspace-reconcile, codex/remove-302-provider, slice/302ai-pivot, slice/llm-diagnostics. No release tags were present in the accessible refs inventory. A ten-snapshot *path-set* diff found only one relevant code path present earlier and absent at HEAD: `src/logic/intakeReconstruction.ts` (historical W7 deterministic/mock reconstruction, later superseded by W9 Case Compiler). This **does not mean functionality was preserved**: code can remain physically present while no longer reached by active UI/runtime.

### Explicit regression: hidden earlier working features

`knowledge/SPINDLE_REGRESSION_ROOT_CAUSE.md` identifies an earlier refactor that replaced:
- SystemOperatorNavigator 3×3 graphical grid → text-only shell;
- MachineView cross diagram → flat list;
- GlobalQuintConsole (7 LLM modes) → empty KaionDock shell;
- natural LLM routing → command-only parser;
- AgentFoundry, Effects, ScenarioTests, Metrics → empty placeholders/simplified output.

Some were later repaired and others remained reachable only through Legacy UI. Therefore **CURRENT FILE EXISTS** and **CURRENT FEATURE WORKS IN PRODUCT** must be separately evidenced. `knowledge/REMOVED_TOP_LEVEL_TABS_MAP.md` maps 17 earlier top-level surfaces to Spindle/Trajectory/Base and documents hidden Legacy UI access.

### Historical code that SESHAT should not lose

1. **AgentRun envelope and lifecycle**
   - `src/types/core.ts`, `src/logic/agentRuns.ts`, `src/App.tsx:handleRunPipeline`
   - `RunProfile`, `RunPolicy`, `RunBudget`, `AgentRunStep`, `HypothesisTrack`, `RunReport`, target object, artifact and history.
   - *Disposition:* **REUSE concepts + EXTRACT typed interface + WRAP runtime; COMPLETE missing enforcement/portability.** The code already exists, but its target-object semantics are rooted in Quinta.

2. **Operator repertoire and agent ecology**
   - `src/logic/agentOperations.ts`, `src/data/operators.ts`, `src/data/agentGraph.ts`, `src/agents/defaultAgentSpecs.ts`, `src/agents/metaAgentSpecs.ts`
   - Historic L0/L1/L2/L3 taxonomy; specialized roles; compatibility/activation rules; deterministic methods.
   - *Disposition:* **REUSE selectively as typed Operation providers and registration patterns**; do not import TRIZ agents as generic science methods.

3. **Full execution and trace/reporter**
   - `src/logic/executionRunner.ts`, `src/logic/runTraceAdapters.ts`, `src/components/RunTraceStudio.tsx`, `src/tests/runTraceStudioSmoke.test.ts`
   - W7d bounded execution, result/verdict, reporter, graph and event refs.
   - *Disposition:* **WRAP/EXTRACT trace and run-guard semantics** after validating actual active paths and authority limits.

4. **Budget/policy, feedback and lifecycle**
   - `src/logic/autoToN.ts`, `src/types/runControl.ts`, `src/logic/agentBudget.ts`, `src/logic/lifecycleGuard.ts`, `src/logic/feedbackRealityCheck.ts`
   - Step/branch constraints, feedback candidates with no false `verified` status, warning vs hard-block distinctions.
   - *Disposition:* **EXTRACT enforcement-pattern subset**, carrying negative guard tests. Current `knowledge/03_AGENT_RUN_MODEL.md` explicitly distinguishes policy ENFORCED vs TYPE_ONLY; do not promise token/tool/budget enforcement that code does not implement.

5. **Exploration, evolutionary selection, anti-clone diversity**
   - `src/logic/trizCorpus.ts`, `src/logic/agentSwarm.ts`, `src/logic/fitnessEvaluator.ts`, `src/logic/runAutoToNSwarm.ts`, `src/tests/w9CorpusSwarmSmoke.mjs`, `src/tests/w916AntiClusterSmoke.mjs`.
   - Actual bounded parallel mutation, operator selection, 4-axis fitness, top-K diversity and anti-clone tests; a plausible generic run-provider donor.
   - *Disposition:* **EXTRACT the population/exploration pattern as optional RunProfile**, not as the universal epistemology. Re-evaluate fitness as disciplinary criteria, not universal novelty metric.

6. **Object/field and alternative representation machinery**
   - `src/logic/systemObjectDerivation.ts`, `src/logic/solutionForestSeeder.ts`, `src/logic/solutionForestMutator.ts`, `src/logic/engineeringReviewPacket.ts`, `src/logic/operationalStream.ts`, `src/components/MachineView.tsx`, `SystemOperatorNavigator.tsx`.
   - Multiple connected views over structured system/work state; candidate/review/packet lifecycle.
   - *Disposition:* **WRAP/COMPARE as projection providers.** Never declare Quinta's TechnicalSystemModel the ontology of Sechenovka scientific objects.

7. **Rejected and unmounted UI generations**
   - `knowledge/07_ARCHIVE_DEMOTED_IDEAS.md`, `SPINDLE_REGRESSION_ROOT_CAUSE.md`, `REMOVED_TOP_LEVEL_TABS_MAP.md`, legacy UI.
   - *Disposition:* **NEGATIVE DONOR + rescue isolated functionalities**. Anti-patterns include card-as-ontology, drag-to-agent-as-semantic-action, KOSMOS-as-god-object, direct hidden LLM mutation, invisible actions, chatbot-as-workbench.

8. **Pre-Quinta TRIZ, MTM and KOSMOS source bodies**
   - Historical dossier lists legacy local `architecture/` (12 docs), `TRIZovec/` (21 original files), `_READY_FOR_CLAUDE/` (18 conversions), old MVP and 138KB master spec.
   - *Disposition:* **UNKNOWN_HOLD pending physical retrieval**. Corpus index is not proof that each old body is readable at the reported path in this environment. Rejected forms may still contain transferable operators, but their own rejection context must travel with them.

## SESHAT design impact — corrected

Previous: "REUSE primitives; COMPLETE generic AgentRun; do not claim executable generic code."

Corrected:
- **REUSE:** the actual Quinta-specific AgentRun data/model, pipeline UI/execution, run registry, summary/history, bounded policies, trace, W7 execution runner, W9 population/fitness patterns.
- **WRAP:** existing TypeScript functions/run providers behind a source-preserving boundary. Keep source kind, data lineage, run status and enforcement level explicit.
- **EXTRACT:** generic `RunEnvelope` / `RunPolicy` / `RunBudget` / `Step` / `Artifact` / `HypothesisTrack` / `TraceGraph` / `PopulationRound` interfaces after checking current and historical tests.
- **COMPLETE:** provider-neutral execution, persistent external trace, research-object scope, granular stop/invalidation/recompute, actual resource-budget enforcement, evidence access, applicability/aporia, acceptance rights.
- **DEPRECATE as normative:** KOSMOS as special omnipotent engine; direct uncontrolled mutation; irreversible one-way pipeline; card-as-object ontology. Preserve historical implementations only as test cases/evidence.
- **UNKNOWN_HOLD:** direct code extraction from local `inventive-memory-bench-mvp` / older TRIZ archives until files actually retrieved and read.

**Do not silently rewrite the existing SESHAT Python core to Quinta's ontology.** Quinta contributes operational components, not domain authority.

## Mandatory archaeology protocol for all SESHAT donors

A new donor census is not closed until it captures:
1. current canonical runtime and its branch/commit;
2. historical generations / prior repo names / legacy local or Drive roots;
3. branches, tags and release snapshots where available;
4. superseded, rejected, frozen and demoted variants *including why rejected*;
5. code path + exact ref + API/contract + test witness for each candidate capability;
6. physical presence **separately** from live reachability and real execution;
7. what disappeared, what became orphaned, and what survived behind new routing;
8. applicable target objects, evidence access and source preservation obligations;
9. per-capability `REUSE / WRAP / EXTRACT / COMPLETE / DEPRECATE / UNKNOWN_HOLD`;
10. negative lessons/guards that must accompany any isolated reuse.

Historical status is **not** proof of uselessness; a reject decision is **not** automatically revoked. Every import proposal must carry the causal reason for the earlier rejection and evidence that the new target does not repeat it.

## Next verification gates

- **QH-01** Fetch the actual pre-Quinta local root or authorized archive; inventory code/build/fixtures, not merely its dossier.
- **QH-02** Generate a call/reachability graph between HEAD App/Spindle and legacy component registry; classify dormant and hidden capabilities.
- **QH-03** Run historical and current tests for the AgentRun/Pipeline/W7/W9 candidates at pinned refs; separate smoke existence from passing output.
- **QH-04** Produce isolated `QuintaRunAdapter` conformance tests in SESHAT with zero normative takeover and explicit policy levels.
- **QH-05** Compare one SESHAT operation against historical non-pipeline and pipeline run patterns, preserving raw/source and alternate object reconstructions.

Source of authority: inspected GitHub code/commit trees and named historical docs; Drive originals of `модель ТРИЗ для клода` / metaontology are semantic references, not executable witnesses.
