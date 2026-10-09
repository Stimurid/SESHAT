# SESHAT — Implementation Plan v0.1

**Date:** 2026-10-09  
**Owner:** HEPHAESTUS / Implementation Lead (planning, engineering contract, acceptance review); Codex = implementation executor.  
**Canonical code carrier:** [Stimurid/SESHAT](https://github.com/Stimurid/SESHAT). **No second Analytic Fabric repository.**  
**Baseline inspected:** `main@d0b324ed78057dea5c39bbb4de8176ec01c34c91`; GitHub Actions [CI run 37982798112](https://github.com/Stimurid/SESHAT/actions/runs/37982798112) = completed/success at this checkpoint. Always re-check HEAD before a code change.  
**Status:** PLANNED; individual delivery slices must have their own code, tests and acceptance receipts. This document does **not** claim a running semantic Object/Method analyzer or production release.

## 0. Authority and scope

This plan extends, and must not silently replace:

- [Implementation Charter](IMPLEMENTATION_CHARTER.md) — host-neutral substrate, no universal cutter pipeline, Sechenovka first profile, second-host acceptance.
- [Workstream Coordination](WORKSTREAM_COORDINATION_v0.1.md) — exclusive executable-core writer, separate archaeology and Indago streams, source-pinned returns.
- [Donor Implementation Census](DONOR_IMPLEMENTATION_CENSUS_v0.1.md) — seven donor **lines** (PRAGMA/Paideia is one grouped line with two actual repositories). It is a code-grounded *first pass*, NOT generation-aware closure for all donors.
- [Quinta Multi-Generation Archaeology](QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md) and [QH-01](https://github.com/Stimurid/SESHAT/issues/1) — actual Quinta-specific AgentRun exists across generations; generic provider-neutral enforcement and durability are not yet proven.
- [Donor Map](DONOR_MAP.md) — REUSE / WRAP / EXTRACT / COMPLETE / DEPRECATE, with UNKNOWN_HOLD where evidence is lacking.
- Drive (read-only authoritative methodological sources, not a writable checkpoint in this pass): [SOURCE — AGENT_OBJECT_CORE](https://drive.google.com/file/d/1zzxvEy88Fz61rMJAyUZEr9R3pvIQiCxcHn2ubPS_Pt8/view), [SOURCE — Agent 0](https://drive.google.com/file/d/1LLKU0nC6sVBc34dR_wJSCQF2JCckI2x5oOoo-oN6PdE/view).
- [SESHAT Drive implementation state](https://docs.google.com/document/d/1GN9yMrkTWyQfzYKntyRBbXjxUnvAntoaEDIAsfE2bsI/edit) has drift; [Issue #2](https://github.com/Stimurid/SESHAT/issues/2) tracks reconciliation. Git is the current verified code carrier; do not claim Drive write/readback.

**Product invariant:** SESHAT is reusable *analytic execution fabric*. Sechenovka authorabstracts are the first fully specified domain profile, **not** the ontology of SESHAT. Donor tools, human methodological decisions and runtime orchestration retain different authorities.

**Epistemic invariant:** `cut` / `Observation` is an address or candidate, never the compulsory first meaning-making stage. An `OperationSpec` determines topology and permitted evidence. Raw package + observations + previous versioned objects + external evidence can coexist. Distributed `Object` and `Method` may require reconstruction across the whole text; an upstream extract cannot silently censor them.

## 1. What the actual repository already implements

**Code inspected at baseline:**

- `src/seshat/contracts.py`: `ResearchObject`, `SourceCarrier`, `SourceAddress`, `Observation`, `AnalyticObjectSpec`, `EvidenceAccessProfile`, `RawAccessPolicy`, `OperationSpec`, `DerivedObject`, `DependencyEdge`, `Aporia`, `ResearchNeed`, `EvidenceReturn`, `ProjectionSpec`.
- `src/seshat/runtime.py`: minimal bounded run, metadata-presence guard and provider dispatch.
- `src/seshat/blackboard.py`: in-memory version list, explicit dependency links and transitive STALE propagation.
- `src/seshat/adapters/base.py` and `records.py`: abstract provider contracts and donor-shaped record translators; no claim of live donor integration.
- `profiles/sechenovka_authorabstract/operations.py`: **declared** `Object` and `Method`, reciprocal dependencies, FULL_REQUIRED; no original full method execution.
- `tests/`, `.github/workflows/ci.yml`: contract and runtime tests; passing CI proves only these tests.

**Observed engineering gaps, not speculative:**

1. `FULL_REQUIRED` currently checks that expected `SourceCarrier` metadata exists; neither content-addressable raw data nor a full-read receipt is required. `OperationProvider.execute` receives observations and prior objects but **no raw-source read capability**. Thus the current green test can pass without the source text being read.
2. `OperationSpec.dependency_ids` is not an executable reconciliation scheduler. Object↔Method currently exists in profile declarations, not as a bounded source-linked mutual correction cycle.
3. `Blackboard.working_state()` yields every stored object for the research object, including STALE and historical variants. Callers must not mistake this for a coherent accepted/current case view.
4. Acceptance rights, persisted run traces, provider-neutral model proposals, method-body loading, real donor adapters, corpus projections and topology evaluation remain incomplete/unverified.

A new skeleton or blanket refactor would hide these gaps rather than repair them.

## 2. Execution sequence (deliver slices with independent evidence)

| Gate | Deliverable | Depends on | Exit condition |
|---|---|---|---|
| **S0 CURRENT** | Canonical scope, owners, baseline, donor/authority constraints | Existing Git + docs | Git head and CI verified; no competing repo or redundant runtime. |
| **S1 SOURCE ACCESS** | Read-only, version-pinned `SourceContent/SourceRead` port; content availability, hash/length/locator checks; meaningful FULL_REQUIRED/DRILLBACK/NEVER guards; no silent truncation | S0 | A full-required operation can actually access every authorized source carrier; absent, mismatched or unreadable content fails closed. Positive and negative tests pass. |
| **S2 STATE & RECONCILIATION** | Coherent versioned views, explicit proposal/current/STALE selection, typed source/derived dependencies, bounded Object↔Method revision with `APORIA` | S1 | A source/method change recomputes only affected descendants; no stale object is served as current; converged, conflicting and exhausted loops have distinct receipts. |
| **S3 SEMANTIC VERTICAL** | Authorized original `Object` and `Agent-0 Method` bodies loaded as versioned profile assets (with access rights), typed `ModelProposer`, provenance-bearing structured outputs | S1-S2 + method source availability | Whole-source synthetic and approved real canaries produce inspectable distributed Object/Method hypotheses and evidence; no claims of human acceptance without owner decision. |
| **S4 PROFILE + RESEARCH** | `Infrastructure`, `Novelty`, `Limitations`; external frontier claims through Indago ResearchNeed/EvidenceReturn; corpus Object projection | S3 + source-method contracts + donor binding | Each operation has scope, evidence policy and negative tests; source-only novelty is not falsely world novelty; cross-item invalidation is measured. |
| **S5 GENERALITY & INTEGRATION** | Generation-aware donor adapters (LitOps/Tinkuy/Socrates/D20/Quinta/PRAGMA-Paideia) and at least one independent second host | S1-S4 + donor-specific archaeology | Two genuinely independent hosts run SESHAT-owned contracts without method/authority leakage or donor-copy forks. |
| **S6 RELEASE CANDIDATE** | Durable runs/trace/budgets, recovery, schema/contract CI, negative cases, comparison of execution topologies, acceptance evidence | S3-S5 | Reproducible scenario, regression, recovery and cross-host receipts; explicit human release decision. |

The gates denote **dependency order**, not a claim that each is a single PR or that all donors must be imported. Split implementation into small, independently testable PRs; no speculative schedule estimates.

## 3. FIRST CODEX TASK — S-IMPL-001 / SourceAccess closure

**Do first:** implement S1 in the existing repo, not S2-S6. A full engineering assignment is in [CODEX_IMPLEMENTATION_HANDOFF_v0.1.md](CODEX_IMPLEMENTATION_HANDOFF_v0.1.md).

Required behavior:

- Carrier metadata presence does **not** satisfy `FULL_REQUIRED`. Supply an authorized source reader/handle/port with read capability and stable carrier identity/version/content hash. Make source completeness verifiable and provide a read/attempt receipt. Separate *ability to read the entire source* from *placing the entire source in one model prompt*.
- **FULL_REQUIRED**: if any declared carrier cannot be resolved to actually readable, version-consistent complete content, fail with typed reason; do not execute the semantic operation.
- **DRILLBACK**: explicit addressable source span retrieval, source-version checks and recorded accesses; bounded observations alone cannot be elevated to full-corpus claims.
- **NEVER**: raw content must not be exposed to the operation; observation-only input where permitted.
- Do not hide missing source, OCR, permission, format or checksum errors by synthesizing a source or truncating it.
- Keep donor observations non-sovereign and `DerivedObject` default `WORKING`. No automatic semantic acceptance.
- Make existing record adapters backward-compatible when meaningful, but intentionally update old positive tests that relied on metadata-only FULL_REQUIRED.

**S1 test oracle:** verify real content reaches a deterministic test provider, every declared carrier is opened or accessibly addressable, mismatched/missing source fails, metadata-only FULL_REQUIRED fails, NEVER blocks raw and DRILLBACK is source-addressed, deterministic provider output remains WORKING. Do not claim this is yet a scientific Object reconstruction.

## 4. Reconciliation, then methods (design constraints for later PRs)

**S2:** reciprocal `Object ↔ Method` is a *bounded reconciliation relation*, not a globally cyclic execution DAG. An execution round records versioned proposal refs, what object/method mismatch means, evidence addresses, explicit `APORIA`, budget and stop reason. Prevent infinite bounce and acceptance laundering. Invalidation must distinguish superseded/current, STALE, WORKING, rejected, accepted states and cross-object dependencies. The scheduler must never silently use `working_state()` as authoritative input.

**S3:** two original source bodies exist and have been read by the planner: Object (~34.7k characters) and Agent-0 (~16.3k characters). Both demand whole-text reconstruction; Object distinguishes declared/formal object, functional object and material; Method reconstructs distributed methods, instruments, measurements, statistics and procedures. The source IDs already exist in `operations.py`. Record exact source version/checksum and authorized storage location; **do not paste these source documents into a public repository without explicit disclosure authorization**. In the absence of Codex access, implement the loader contract with licensed/private local fixtures and mark production-body binding BLOCKED rather than inventing a replacement.

Later profile operation admissions require actual source-authorized methods and provenance. Do **not** construct 39 prompts to fill the matrix. A full `39-output` semantic inventory is contract coverage, not evidence that 39 executable heads exist.

## 5. Donor archaeology as parallel acceptance dependency

The census covers seven **logical lines** (LitOps, Tinkuy, Socrates, Quinta, D20, Indago, PRAGMA/Paideia). The current physical witnesses are stronger than abstract analogies, but except Quinta they remain **PROVISIONAL_HISTORICAL_COVERAGE**. For any donor reuse/adapter PR, the archaeology stream must supply source-ref and history from earlier/retired generations, original rejection reasons, present path, reachability, execution/test status and `REUSE/WRAP/EXTRACT/COMPLETE/DEPRECATE/UNKNOWN_HOLD` per capability.

Do not make *completion of every historical audit* a prerequisite for S1. Do require the targeted donor evidence before claiming a real integration. The Indago line is an external research organ: `ResearchNeed / EvidenceReturn / ReturnAddress`, not a second researcher built inside SESHAT. Quinta's AgentRun is a verified domain-specific implementation, **not** proof of a cross-host release-ready generic runner.

## 6. Evaluation and release truth

A milestone is not complete on document fluency, a green existing smoke suite or model praise. Maintain the independent statuses:

- `SPECIFIED` — contract and design exist.
- `IMPLEMENTED` — named code path and returned artifact exist.
- `TESTED` — exact command + run URL + cases and negative tests passed.
- `SEMANTICALLY_REVIEWED` — source-owner/methodology review, not model self-certification.
- `ACCEPTED` — authorized acceptance tied to evidence and declared scope.

Minimum evaluation matrix: same source / different topology; full reconstruction versus local+drillback; distributed evidence across sections; absent or contradictory data; source update and invalidation; authority/consent failures; mixed-language/OCR cases where available; external evidence insufficiency; second-host independence. Track semantic fidelity and evidence coverage separately from execution/CI pass.

For every implementation PR require: prior HEAD pin; exact changed paths; contracts/tests; `pytest -q`; preferably `ruff check .`; CI URL; known limits; replay or negative evidence; rollback note; and a Git durable receipt. No Drive-sync claim while write/readback is blocked.

## 7. Workstream and writing-right rule

- **Codex / Implementation Lead execution stream**: exclusive owner for changes to `src/`, `tests/`, `profiles/`, `.github/`; work on a branch/PR; provide evidence.
- **Hephaestus / engineering lead**: plan, contract, critique, acceptance review and Codex tasking; may create docs/issues, but does not concurrently edit implementation files.
- **Archaeology stream**: historical donor/code evidence and negative regressions, no competing core commits.
- **Indago**: analog search/source/evidence transactions, no architectural or semantic authority takeover.
- **User / method owner**: method meaning, human approval, consequential acceptance.

Keep Git as the current durable control surface. The plan itself is a planning artifact, **not** proof that Codex has been remotely started or that a release was accepted.
