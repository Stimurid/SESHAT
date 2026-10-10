# SESHAT — FABRIC, PROJECTION & AUTHORITY ARCHAEOLOGY v0.2

2026-10-10 — read-only multi-generation audit / SESHAT donor line Socrates × Tinkuy × Zarathustra
Drive mirror: https://docs.google.com/document/d/1pUGdIiRMZtA32m8S2OZHs3nGBmZgB6qp19xLEzzl66c/edit?usp=drivesdk
Standing triage: https://github.com/Stimurid/SESHAT/issues/6
Specific follow-up: https://github.com/Stimurid/SESHAT/issues/9 and https://github.com/Stimurid/SESHAT/issues/10
Status: source-pinned code inspection + isolated synthetic runtime probes; NOT a live LLM evaluation or full domain method acceptance.

1. WHAT HAS BEEN TRACED

Do not collapse distinct mechanisms into a single "Cutter Core":
(A) Early Tinkuy FabricParser: document text → coarse, semantic units, blocks, relations, threads, scene → FabricSnapshot.
(B) Socrates cutter registry: operation + object family + recognition policy + ORIGINAL source → ProjectionResult. It is a typed re-projection executor, not the old FabricParser itself.
(C) Socrates reflective projection control: P1 → diagnostic/residue → reflective return → changed operation/ontology → P2 against the preserved ORIGINAL text, with versions and stop guards.
(D) Socrates APORIA apparatus diagnostics: unresolved/ordinary gap versus genuine mismatch; possible world-map update through governed state, not automatic semantic certainty.
(E) Original TyumenAILab/Socrates scene contract: separate Waku-based human/mode/dictionary gate. Distinct physical repository, not proven code ancestor of Zarathustra scene_contract.py.

2. PINNED CODE GENERATIONS / WITNESSES

Stimurid/zarathustra- code history (all paths rooted CALIFORNIAN_ID/):
- 91c9ee9 (2026-08-08) adds src/californian_id/fabric/parser.py, initial FabricParser, blob 59b2092e...
- 9c86a52 (2026-08-17) adds src/socrates_runtime/cutter_registry.py, marker-based original-source projection, blob fbe3573e... in later source.
- 7327705 (2026-08-17), then 77a1178 (2026-08-19) add/revise aporia apparatus and world-map logic.
- dba32e1 (2026-08-18), then b911e3b / 2f3474e / 4802c6d develop scene-contract drift and revision admission.
- 5358199 (2026-09-07) revises FabricParser (blob cb6596abeae2e39cb0366a5fafe7305336e421c9), with the same implementation at examined 7d94e62 (2026-09/30) and local clean C:\projects\zarathustra-g-next-03 @c1298e803804b2180b27cb252c00975265193736.

Actual four inspected local blobs at c1298e8 match inspected GitHub versions: FabricParser cb6596abe..., CutterRegistry fbe3573e..., SceneContract 62cc58d5..., APORIA c89c5d14.... Local checkout was clean after synthetic probes, and no donor files were edited.

Original independent TyumenAILab/socrates @41fcf2b: topdown/waku/contract.py (closed dictionary + confirm gate + mutable explicit edit), distinct topdown/bottomup/space/arena package boundaries. Its independent-copy law in ADR 0006 remains binding as a historical decision.

3. FABRIC METHOD BODY VERSUS IMPLEMENTATION — PROVEN GAP

Source-authorized method descriptions at src/californian_id/data/fabric:
00_fabric_parser_orchestrator.md requires stages 01 through 11, explicit uncovered-range reporting and no unsourced objects;
02_multiscale_segmentation.md requires overlapping 15–25% transport windows, not semantic objects;
07_cross_scale_reconciliation.md requires gap coarse blocks, duplicate/contradictory blocks and orphan units detection without automatic merge/split;
08_window_boundary_repair.md requires overlap-gap/duplicate review;
10_provenance_validation.md requires references and valid non-out-of-bounds spans;
11_no_loss_validation.md requires uncovered_ranges, default 85% warning and BLOCK below 60%.

But actual FabricParser.parse() at blob cb6596a:
- does NOT call passes 02, 07, 08 at all (separate prompt files exist, but no runtime invocation); the narrative that it conditionally "skips when JSON invalid" is even too generous for this exact parse() implementation.
- 01 coarse sends only first 20,000 source characters to the LLM, while setting text_length_full metadata; the fallback extraction may send the full source as one block, but method-specific long-text coverage remains unproven.
- 03 semantic extraction catches errors per block and continues without blocking snapshot. Its span-offset handling guesses relative versus absolute offsets.
- 10 provenance removes units with no valid referenced span. It does not independently validate all relation/thread references, bounds or source-text equality.
- 11 no-loss uses sum(end-start) across returned spans divided by total source length: no interval union, no uncovered-range detection, no threshold check, no blocked commit.
- snapshot source_version is hard-coded "v1" irrespective of original source checksum/version. Source ID defaults to hash of first 200 characters if not provided.

The docstring's "critical pass fails fatal" is contradicted by the local per-block except/continue behavior. This is not a conjectured defect: synthetic execution demonstrates invalid outputs can still return FabricSnapshot.

4. ISOLATED RUNTIME PROBES — EXECUTION WITNESSES

Ran Python against a clean, pinned local historical checkout with PYTHONDONTWRITEBYTECODE=1 and a synthetic in-memory fixture provider; no external LLM, no private raw corpus and no donor file writes:
FAB-PROBE-A: semantic extraction returns zero spans/units => parse() RETURNS FabricSnapshot: coverage_pct=0.0, n_units=0, n_spans=0, source_version=v1. Contradicts source 11 (<60% block).
FAB-PROBE-B: extraction returns two identical full-source spans => parse() RETURNS FabricSnapshot: coverage_pct=2.0, n_units=0, n_spans=2. Double counting is mistaken for 200% coverage.
FAB-PROBE-C: source_map("alpha\n \nbeta") gives beta char_start=7, but beta begins at index 8 in the actual original, because split assumes separator length always 2.

These prove behavior of *this code path under synthetic fixture outputs*, not frequency under live models or end-to-end field error rates.

Historical CALIFORNIAN_ID/tests/unit/test_fabric.py exercises FabricSnapshot storage, converter, JSON parser and mock rejection; it does not contain an end-to-end parse coverage oracle. Existence of a "no-loss" Markdown method body is not a passing implementation test.

5. SOCrates CUTTER AND REFLECTION: REAL POSITIVE DONOR, WITH A DIFFERENT LIMIT

At cutter_registry.py blob fbe3573e...: CutterCapability declares operation_id, target family, segmentation_policy, recognition rules and execute(original_source, spec). Peskov projection tests verify immutable original-source reread, typed P1→diagnostic→ReflectiveReturn→P2 provenance, preservation of P1, residue and bounded feedback.

However default cutters _scan_marked_lines() recognize only source lines beginning with bracketed category markers. Their coverage denominator is the number of matched marker lines, not original source length. Unmarked research prose is invisible even to the mismatch diagnostics.

Isolated synthetic execution:
CUT-PROBE-A: entirely unmarked source => status=ACCEPTED_LOCAL, coverage=0.0, objects=0, residue=0, diagnostic signals=[].
CUT-PROBE-B: one [concept] marked line + unmarked methodological content => status=ACCEPTED_LOCAL, coverage=1.0, objects=1, residue=0, diagnostic signals=[].
This is expected from a *symbolic demo cutter* but disqualifies it as a standalone semantic Object/Method extractor.

PROVEN useful pattern: method-selected projection from ORIGINAL raw carrier; prior versions/residue retained; diagnostics permit alternative operations; stop on repeated fingerprints/iteration cap.
NOT proven: reconstruction of a scientific Object, Method, or material distributed over many unmarked pages; full natural-language model provider in this path.
The status ACCEPTED_LOCAL is defined as *local* look acceptance and should never be laundered into human or global scientific acceptance.

6. APORIA AND VERSIONED WORLD-MAP: GOOD STRUCTURE, WEAK MODULE-LOCAL ADMISSION

aporia_and_world_map.py blob c89c5d14... and test_aporia_and_world_map.py / test_aporia_apparatus_3c.py show:
- AporiaGrade distinguishes ordinary uncertainty, open question and APORIA; only APORIA grade can open typed ApparatusMismatchHypothesis, and review may reject or defer.
- ApparatusReplayResult compares gains, destroyed distinctions, false distinctions, authority and productive aporia retention; can keep an alternative rather than forcing consensus.
- WorldMapVersion and Registry retain older versions; proposal is marked NO_DURABLE_WRITE.
- Existing tests cover missing evidence, user instruction/novelty demands, repeated failures, genuine unresolved APORIA and denial of some unprivileged writes.

Yet WorldMapRegistry.admit_update itself accepts any nonempty authorized_transition_ref and does not verify proposal.base_version_id matches the latest map. In the isolated synthetic probe a proposal claiming base_version_id="wrong_stale_version" with authorized_transition_ref="arbitrary-non-empty-string" was admitted and created a successor to current version.

This proves a module-local precondition gap, NOT a confirmed externally exploitable security defect: upstream caller authentication/reference validation might exist elsewhere. SESHAT must nonetheless not reuse this function as its independent authority gate.

7. SCENE CONTRACTS: TWO DISTINCT CARRIERS; BOOLEAN IS NOT HUMAN IDENTITY

At Zarathustra scene_contract.py blob 62cc58d5...:
- ContractRevisionCandidate and SceneContractDriftAssessment are NO_TRANSITION_AUTHORITY evidence, not autonomous revisions.
- assess_scene_contract_drift compares scene/space identity, object_scope, telos, ownership and epistemic policy; changes of operation alone may be suboperations.
- admit_contract_revision checks context_action.kind and bool(context_action["human_explicit_choice"]). False holds proposal, True admits.
Isolated synthetic test: identical proposed candidate plus false flag => HOLD_PROPOSAL / NO_TRANSITION_AUTHORITY; true flag => ADMIT_REVISION / USER_EXPLICIT. A caller-provided boolean alone is not an authenticated human action. No assertion is made here about what outer runtime allows untrusted callers to send.

Original TyumenAILab topdown/waku/contract.py @41fcf2b has dictionary-bound intent/position/truth_mode confirmation. Its update_contract_field directly sets one field and verifies truth_mode membership in a space, but does not independently re-check full dictionary-triplet compatibility. Before reuse, test the user edit path for preservation of all tuple invariants. This code is in another repo and is NOT the same class as Zarathustra SceneContract.

8. ARCHITECTURAL DISPOSITION FOR SESHAT

REUSE/EXTRACT (after tests): typed projection schema, original-source reread, diagnostic/residue/lineage, bounded reflective returns, proposal-versus-admission separation, APORIA grades, alternative retention, versioned maps.
WRAP: Tinkuy FabricParser as best-effort observation/provider (not a no-loss sovereign Cutter); Socrates specialized marker cutter as a synthetic control fixture; scene-contract/WorldMap wrappers with verified outside authority.
COMPLETE: source interval validator and union coverage, source-version pinning, visible degraded/skipped passes, full-data check, trusted user event/capability, base-version optimistic locking, distributed Object/Method validation, independent second-host contract.
DEPRECATE AS UNIVERSAL: fixed 01→11 cutter chain as the mandatory ontology, unmarked content invisibility, fake no-loss certainty, caller-fabricated permission flags.
UNKNOWN_HOLD: live model behavior, full external authorization path, actual physical independence between other host variants, current-test coverage of branches not rerun.

Gate application:
S1 source access PR #5: NOT blocked. Its source-integrity work is a prerequisite but not semantic-coverage proof.
S2 reconciliation: use typed lineage, APORIA, stale version and admission negative tests.
S3 profile: full original Object/Method body stays source authorized; no reduction to marked lines or first-20k coarse pass.
S5 donor integration: block importing Fabric as *strict no-loss* or marker cutter as genuine semantic Object/Method provider until issues #9/#10 clear.
S6 topology evaluation: benchmark source-first reciprocal reads against 01→11 as an explicitly degraded baseline; measure actual gaps and preserved semantic distinctions.

9. DURABLE HANDOFF / NEXT WORK

https://github.com/Stimurid/SESHAT/issues/9 — Fabric coverage / source spans / omitted stages, negative tests.
https://github.com/Stimurid/SESHAT/issues/10 — trusted rights and stale WorldMap admission, negative tests.
https://github.com/Stimurid/SESHAT/issues/6 — standing re-entry and intake; send links there, no need to interrupt current S1.
https://github.com/Stimurid/SESHAT/pull/7 — audit branch, no executable SESHAT files changed.
https://github.com/Stimurid/SESHAT/pull/4 — earlier Quinta source archaeology and rejected induction.
Follow-up archaeology: source-code behavior for current TyumenAILab bottomup/space, exact caller authentication of scene and map writes, and other donor generations where adoption depends on historical behavior.

EVIDENCE HONESTY: all code paths pinned and at least five synthetic module-level probes run. Historical test files read but not reexecuted as full suites; no real Sechenovka corpus run, no semantic acceptance, no independent host migration.