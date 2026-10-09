# SESHAT Donor Implementation Census v0.1

Status: source/code-grounded first pass. This census separates semantic identity from physical code carrier. One donor line may share a repository with other systems.

## Summary

| Line | Physical implementation witness | Pin used | SESHAT disposition |
|---|---|---|---|
| LitOps | `Stimurid/whitecrow:litops/` | `main@9bd58f2` | REUSE + WRAP + EXTRACT + COMPLETE |
| Tinkuy Fabric | `Stimurid/zarathustra-:CALIFORNIAN_ID/src/californian_id/fabric/` | Socrates branch `7d94e62` | REUSE + WRAP + EXTRACT + COMPLETE |
| Socrates | `Stimurid/zarathustra-:CALIFORNIAN_ID/src/socrates_runtime/` + current contracts | `socrates/gcur32-claude-overnight-20260930@7d94e62` | REUSE + WRAP + EXTRACT + COMPLETE |
| Quinta / AgentRun | `Stimurid/quinta` | `main@3963df4` | REUSE / WRAP / EXTRACT / COMPLETE (generation-scoped) |
| D20 Field Core | `Stimurid/whitecrow:fieldcore/` | `main@9bd58f2` | REUSE + WRAP; EXTRACT only after ownership split |
| Indago | live OpenClaw body + Drive ledgers; no canonical Git repo evidenced in accessible Stimurid repo set | current Drive/OpenClaw witnesses | WRAP first; EXTRACT protocol; code import UNKNOWN_HOLD |
| PRAGMA | `Stimurid/moderbober` | `main@6d59256` | REUSE + WRAP + EXTRACT selectively |
| Paideia | `Stimurid/paideia:api/dialogue_runtime/` | `main@8a2708d` | REUSE + WRAP + EXTRACT selectively |

---

## 1. LitOps

### Implementation witness
Repository: `Stimurid/whitecrow`, `main@9bd58f2bb7ce371ba876934f0a53ed51d2ef0a38`.

Observed executable package: `litops/`.

Load-bearing paths:
- `litops/extraction.py` — multi-format extraction; large plaintext segmentation is explicitly paragraph/size transport segmentation.
- `litops/semantic_resolution.py` — profile → Segment → density → extraction → review → promotion; accepted EntityCandidate → Brick(candidate).
- `litops/schema.py`, `litops/registry.py`, stores/provenance/lineage modules.
- acquisition subpackage and source identity machinery.

Test witnesses:
- `tests/test_semantic_resolution_runtime.py`
- `tests/test_v33_4d_segment_extraction.py`
- `tests/test_v61_semantic_extraction_orchestrator.py`
- `tests/test_live_extraction_loop.py`
- `tests/test_runtime_extraction.py`

### What is actually reusable
REUSE:
- Source identity/acquisition.
- Source-addressed Segment/anchor mechanics.
- candidate/review/promotion lifecycle.
- provenance and lineage.

WRAP:
- current LitOps registry/store/run implementation behind SESHAT Source/Evidence interfaces.

EXTRACT:
- source/provenance/promotion contract if it can be separated without forking WhiteCrow ownership.

COMPLETE:
- explicit separation of transport segmentation from semantic observation.
- profile routing compatibility with SESHAT EvidenceAccessProfile.
- multiscale observation provider integration.

DEPRECATE AS SEMANTIC AUTHORITY:
- paragraph/size transport segmentation.

### SESHAT import rule
Do not copy `litops/` wholesale. Build an adapter first. Extract only contracts that survive a second host.

---

## 2. Tinkuy Fabric

### Implementation witness
Physical carrier: `Stimurid/zarathustra-`.
Current inspected pin: `socrates/gcur32-claude-overnight-20260930@7d94e62e4a6ef3fd4ca74ab6e9843df3e621127f`.

Paths:
- `CALIFORNIAN_ID/src/californian_id/fabric/parser.py`
- `CALIFORNIAN_ID/src/californian_id/fabric/schemas.py`
- `CALIFORNIAN_ID/src/californian_id/data/fabric/*`

`FabricParser` is executable and returns `FabricSnapshot`. Its declared pipeline includes coarse composition, optional multiscale segmentation, semantic move extraction, block/relation/thread assembly, optional cross-scale reconciliation, scene reconstruction, provenance validation and no-loss validation.

Important runtime defect confirmed in code:
- passes 02, 07 and 08 are allowed to be skipped/non-blocking;
- therefore canonical multiscale/no-loss doctrine is stronger than the active parser.

### Disposition
REUSE:
- SourceSpan/evidence schemas.
- FabricSnapshot and provenance-bearing units.
- relation/thread/scene representations where generic.

WRAP:
- `FabricParser` as one observation provider.

EXTRACT:
- overlap / multiscale / reconciliation / boundary-repair / no-loss contracts.

COMPLETE:
- strict union-of-spans coverage.
- first-class uncovered ranges.
- preservation of competing projections.
- canonical passes currently optional/missing in runtime.

DEPRECATE:
- cheap text chunker as critical semantic path.

### SESHAT boundary
Fabric observations are non-sovereign. They may address evidence for a domain method but do not define the target analytic object.

---

## 3. Socrates

### Implementation witness
Physical carrier: `Stimurid/zarathustra-`.
Current inspected branch:
`socrates/gcur32-claude-overnight-20260930@7d94e62e4a6ef3fd4ca74ab6e9843df3e621127f`.

Concrete runtime:
- `CALIFORNIAN_ID/src/socrates_runtime/epistemic_model.py`
- `.../epistemic_ops.py`
- `.../projection.py`
- `.../projection_primitives.py`
- `.../projection_step.py`
- `.../aporia_and_world_map.py`
- `.../cutter_registry.py`
- `.../governor.py`
- `.../operation_set.py`
- `.../private_work_plane.py`
- `.../provenance.py`

Current contract schemas:
- `data/socrates/current/contracts/epistemic_claim.schema.json`
- `epistemic_space.schema.json`
- `generated_cutter_spec.schema.json`
- `projection_spec.schema.json`
- `projection_result.schema.json`
- `world_model_mount.schema.json`
- scene state/branch schemas.

Runtime evidence:
- live smoke receipts/reports and G-NEXT receipts exist on the current branch.
- the branch is not repo `main`; SESHAT must pin the branch/commit explicitly.

### Strong transferable mechanics
REUSE:
- typed epistemic state and claim origin/status.
- applicability / aporia.
- explicit state-write authority.
- projection lineage.
- governed revision/admission.

WRAP:
- existing Socrates runtime behind a lightweight SESHAT analytic-operation adapter.

EXTRACT:
- `OperationSpec`-like contracts.
- projection lineage/DAG mechanics.
- applicability/aporia and governance primitives.

COMPLETE:
- batch/document mode that does not require a full constitutional Scene.
- corpus invalidation dependency semantics.
- integration with shared Source/Evidence interfaces.

Do not import:
- the whole Socrates constitutional/dialogue machinery as a mandatory dependency.

---

## 4. Quinta / AgentRun — HISTORICAL CORRECTION

**This section supersedes the initial latest-HEAD-only assessment.** Detailed source-/commit-pinned audit: [QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md](QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md).

### Implementation witness — current *and historical*

Repository: `Stimurid/quinta`, `main@3963df4b8fb693be5cf46cc75aee0dd1372deade`. Initial Quinta commit `b19465288` already implemented a specific `AgentRun` envelope and KOSMOS / single-method factories. Historical source dossier `knowledge/LEGACY_RECOVERY_FULL_DOSSIER.md` also identifies **pre-Quinta** `C:\projects\Claude\TRIZ\inventive-memory-bench-mvp` and related architecture/corpus assets; that local code has **not** been inspected here.

Code-path witnesses at current main:
- `src/types/core.ts` — `AgentRun`, `RunProfile`, `RunPolicy`, `RunBudget`, `AgentRunStep`, `HypothesisTrack`, `RunTraceGraph`, factories.
- `src/logic/agentRuns.ts` — actual KOSMOS and single-method run objects, steps, artifacts, hypothesis tracks, reports, archive.
- `src/components/PipelineBuilder.tsx`, `RunLauncher.tsx`, `RunsPanel.tsx`, `RunInspector.tsx`, `RunTraceStudio.tsx`.
- `src/App.tsx:handleRunPipeline` (~1809–1969) — **actual** multi-cycle deterministic pipeline execution, max-step/branch guards and run-history mutation. Other App handlers create KOSMOS and single-method AgentRuns.
- `src/logic/executionRunner.ts`, `runTraceAdapters.ts`, `agentBudget.ts`, `lifecycleGuard.ts` — bounded execution and trace/report components.
- `src/logic/trizCorpus.ts`, `agentSwarm.ts`, `fitnessEvaluator.ts`, `runAutoToNSwarm.ts` — W9 operator selection, bounded parallel mutation, fitness and diversity selection.
- `src/tests/runTraceStudioSmoke.test.ts` + W8/W9 smoke family; existence of test files does not prove live production behavior.

Important limitation: `knowledge/03_AGENT_RUN_MODEL.md` distinguishes actual enforced guards from TYPE_ONLY budget/policy fields. Pipeline runs can be Quinta-centric and may contain empty artifact/hypothesis collections despite nonempty steps. Cross-project, provider-neutral runtime and full durability remain unproven. `src/RUN_PROFILE_AUDIT.md` refers to a distinct Spindle control-surface audit, **not** to the absence of every AgentRun implementation.

### Historical loss is not just file deletion

Inspection of 10 recursive Git snapshots across initial Quinta, recovery, Spindle, W4/W5, W7d, W8/W9, and main found only one relevant earlier code path missing at HEAD (`src/logic/intakeReconstruction.ts`); however `knowledge/SPINDLE_REGRESSION_ROOT_CAUSE.md` documents replaced/empty UI shells and still-existing functionality marooned behind Legacy UI. Therefore path presence, route reachability, actual runtime, and acceptance are separate evidence levels.

Consciously demoted architectures, reasons and acceptable secondary modes are preserved in `knowledge/07_ARCHIVE_DEMOTED_IDEAS.md`; do **not** infer from `SUPERSEDED` that the code has no donor value, nor from historical donor value that its obsolete semantics may become canonical.

### Corrected disposition — per capability

**REUSE:** actual Quinta-specific run envelope/factories, pipeline construction and execution primitives, run controls and history, W7 bounded execution, W9 population/fitness methods, trace/reporter and existing tests.

**WRAP:** domain-specific TypeScript actions and run implementations behind SESHAT operation/provider interfaces; preserve source kind, policy enforcement level, evidence rights and authority.

**EXTRACT:** generic `RunEnvelope / RunProfile / RunPolicy / RunBudget / RunStep / RunArtifact / HypothesisTrack / TraceGraph / PopulationRound` contracts after historical behavior/test verification. This is **not** HOLD merely because source code lacks an already-shared package boundary.

**COMPLETE:** provider-neutral target and execution abstraction, durable external trace, real token/tool budget enforcement, policy rights, event-driven invalidation, evidence access and acceptance semantics.

**DEPRECATE as governing ontology:** KOSMOS-as-god-object, cards-as-primary-objects, drag-as-mutation, hidden direct LLM mutations, irreversible pipeline. Keep the historical versions as negative donors and partial operation sources.

**UNKNOWN_HOLD:** physically unexamined pre-Quinta local MVP, original architecture and TRIZ/MTM corpus. The legacy dossier is evidence of their described existence, not a current executable witness.

---

## 5. D20 Field Core

### Implementation witness
Repository: `Stimurid/whitecrow`, `main@9bd58f2`.
Package: `fieldcore/`.

Concrete paths:
- `fieldcore/schema.py`
- `fieldcore/runtime.py`
- `fieldcore/store.py`
- `fieldcore/persistence.py`
- `fieldcore/operations.py`
- `fieldcore/governance.py`
- `fieldcore/litops_bridge.py`
- `fieldcore/semantic_adapter.py`
- `fieldcore/validation.py`

`schema.py` already carries typed entities, anchors, acceptance states, origin modes, mutation types, field state collections and version-oriented structures.

Tests:
- `tests/test_fieldcore_runtime.py`
- `tests/test_fieldcore_operations.py`
- `tests/test_fieldcore_persistence.py`
- `tests/test_fieldcore_governance*.py`
- `tests/test_fieldcore_litops_bridge.py`
- `tests/test_fieldcore_workbody_roundtrip.py`

### Disposition
REUSE:
- stable entity identity.
- occurrence/anchor/evidence attachment.
- relation/revision/event/patch substrate.
- acceptance/origin distinctions.

WRAP:
- namespace/scope adaptation to SESHAT entity/projection state.

EXTRACT:
- not yet. D20 is physically and governance-wise inside WhiteCrow; shared ownership must be explicitly split before copying it into SESHAT.

COMPLETE:
- contested typing and sense split/merge.
- dependency/invalidation relations to corpus projections.
- generalized projections beyond D20 Field rings.

DEPRECATE:
- treating D20 Field topology as the whole EntityWorld.

---

## 6. Indago

### Implementation witness
No canonical Git repository was evidenced among the currently accessible `Stimurid/*` repositories in this pass.

Current durable/live body is nevertheless concrete.

Drive current surface:
- `00_CURRENT — INDAGO TASKS AND TRAILS`.
- HUNT_LEDGER / SOURCE_LEDGER and hunt histories.

Current implementation handoff identifies live local runtime:
- `/Users/timurshchukin/.openclaw/house-portal/bin/indago-run`
- `/Users/timurshchukin/.openclaw/house-portal/bin/indago-run.js`
- `/Users/timurshchukin/.openclaw/house-portal/config/indago-drive.json`
- scheduled body `com.openclaw.indago-heartbeat`.

Durable runtime evidence in Tasks & Trails records working citation chase, browser/provider paths, saturation and source/trail discipline.

Important current gap from the implementation handoff:
- bounded one-shot ResearchRequest transport can be written while the consumer remains unproven.
- canonical audit observed scheduled runs but did not prove direct task consumption.

### Disposition
REUSE:
- external acquisition/search behavior.
- source/trail identity.
- saturation and negative-result discipline.
- durable write/readback transaction.

WRAP:
- existing Indago runtime through typed `ResearchRequest / EvidenceReturn / ReturnAddress`.

EXTRACT:
- protocol/transaction contract only.

COMPLETE:
- one-shot request consumer.
- local-first resolution.
- durable return adapter back to blocked operation/state.
- direct invalidation/recompute notification.

CODE EXTRACTION:
- UNKNOWN_HOLD until the local OpenClaw code is put under a canonical repository or an existing repo carrier is proved.

Do not build a second Indago inside SESHAT.

---

## 7A. PRAGMA

### Implementation witness
Repository: `Stimurid/moderbober`, `main@6d59256cfa2e1b442b05486b003d9947c747f8dd`.

Concrete runtime paths observed:
- `backend/app/program_runtime/event_writes.py`
- `backend/app/program_runtime/governed_review.py`
- `backend/app/program_runtime/state_diff.py`
- `backend/app/program_runtime/reports.py`
- associated API routers.
- typed agent specifications and operation tables under product/ontology runtime.

Tests include:
- `backend/tests/test_mps9_governed_review_postgres.py`
- `backend/tests/test_r1_governed_review_reconcile.py`
- live event runtime/API tests.

### Disposition
REUSE:
- proposal/review/apply.
- state diff/patch mechanics.
- report/projection ≠ state semantics.
- governed review.

WRAP:
- project/group ontology into SESHAT acceptance and projection interfaces.

EXTRACT:
- generic review/apply, patch/diff and DecisionRight-like primitives where separable.

COMPLETE:
- generic source/evidence and operation-address adapters outside PRAGMA group/session ontology.

---

## 7B. Paideia

### Implementation witness
Repository: `Stimurid/paideia`, `main@8a2708d90331090822bd1faba3bde3621e1abdc5`.

Large concrete runtime package:
`api/dialogue_runtime/`.

Key modules:
- `bricks.py`
- `claims.py`
- `positions.py`
- `context_packs.py`
- `context_snapshots.py`
- `lineage.py`
- `semantic_packages.py`
- `decisions.py`
- `derived_moves.py`
- `orchestrator.py`
- `retrieval.py`
- `report_compiler.py`
- `report_ingestion.py`
- `state.py`
- `diff.py`
- `cross_project.py`
- `coverage_matrix.py`.

### Disposition
REUSE:
- typed semantic packages/bricks.
- context packages/snapshots.
- lineage/provenance structures.
- reconciliation/report compiler patterns.

WRAP:
- Paideia ontology through generic AnalyticPackage / Projection / Acceptance adapters.

EXTRACT:
- generic package, lineage, return/reconciliation primitives only where code dependencies permit.

COMPLETE:
- generic ReturnAddress and blocked-operation return contract shared with PRAGMA/Indago.

### Currentness caution
The code witness is strong, but repository `main` is older than several later Drive operational surfaces. Before copying code into SESHAT, re-check whether a newer Paideia/Dedalum branch or successor owns the relevant implementation.

---

# Cross-donor decision

## What can be coded in SESHAT now without pretending

Safe to implement as **SESHAT-owned interfaces and adapters**:
1. SourceCarrier / SourceAddress interfaces.
2. Observation / evidence-address contracts.
3. EvidenceAccessProfile / RawAccessPolicy.
4. OperationSpec and DerivedObject.
5. provenance/lineage interface.
6. dependency/invalidation interface.
7. acceptance/decision-right interface.
8. ResearchRequest / EvidenceReturn / ReturnAddress interface.

Not safe to copy wholesale yet:
- LitOps package.
- Socrates runtime.
- FieldCore.
- Paideia dialogue_runtime.
- PRAGMA program runtime.
- Indago local runtime.

## First executable composition
Use adapters/providers:
- LitOps provider for source acquisition/addressed evidence.
- Tinkuy provider for multiscale observations.
- Socrates-derived primitives for operation/applicability/aporia/projection governance.
- D20 adapter for entity state.
- PRAGMA/Paideia adapter for governed acceptance/projection.
- Indago adapter for external research.
- Quinta provides real AgentRun/pipeline/runtime, W7 execution, W9 swarm/fitness and trace donors; wrap/extract selectively with generation-pinned tests and authority safeguards.

## Language/runtime decision
The donor set is predominantly Python for LitOps, Tinkuy/Socrates runtime, D20, PRAGMA backend, Paideia and Indago's interface boundary, while Quinta is TypeScript.

Therefore the first SESHAT core should be **Python-first**, with typed JSON/Pydantic-compatible contracts and a TypeScript adapter/client boundary for Quinta/UI consumers.

This is an evidence-based implementation choice, not a permanent prohibition on multi-language adapters.

## Immediate next build
1. Define Python contract package with no donor imports.
2. Add adapter protocols.
3. Implement LitOps + Socrates + D20 read-only adapters first.
4. Add one Sechenovka operation (Object) using full-package evidence access.
5. Add Method as a second mutually constraining operation.
6. Add versioned blackboard + invalidation.
7. Only then introduce the topology evaluation harness.
