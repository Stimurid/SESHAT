# SESHAT — ORIGINAL SOCRATES BOTTOM-UP DONOR RECOVERY v0.1

2026-10-10 / archaeological engineering report / original TyumenAILab/socrates, distinct from Stimurid/zarathustra-
Drive canonical mirror: https://docs.google.com/document/d/1Un0HNbBBOGQvzoEAfjkRS6mv61NockHgsVV0ACmWNtA/edit?usp=drivesdk
Git review: https://github.com/Stimurid/SESHAT/pull/7
Targeted engineering question: https://github.com/Stimurid/SESHAT/issues/11
Standing incoming evidence: https://github.com/Stimurid/SESHAT/issues/6

STATUS / LIMIT OF CLAIM
Read-only code inspection and five freshly rerun deterministic test modules against original Socrates clean snapshot. No Waku runtime migration, no production/live LLM verification, no transfer of private source bodies. The original owner of the bottom-up implementation and its independent topdown counterpart retains semantic/governance authority.

SOURCE IDENTITY
Verified original origin: https://github.com/TyumenAILab/socrates.git
Read-only local checkout: C:\projects\tyumen-socrates-main-readonly-41fcf2b
HEAD: 41fcf2b16b3eda291c97c948c585a9fc9bfa50b6
The separately existing C:\projects\tyumen-socrates checkout was dirty and deliberately untouched.
Historical ADR 0006: waku-fork reference read-only; topdown, bottomup are independent copies intentionally NOT using a shared importable dependency. space and arena are additional distinct bodies. This structural choice cannot be silently overridden by a generic SESHAT import.

ARCHITECTURE — CONCRETE EXECUTABLE CONTINUOUS LOOP
Event/channel topology:
SpaceWatcher -> EventBus -> Detectors/Noticer -> deterministic Arbiter -> Ledger/Proposals/LoopMemory -> Consolidator when warranted.

Source files at bottomup/waku/bottomup/:
watcher.py — scan MD materials, compare content hashes, skip temporary/partially written files. This is source change detection, not semantic judgement.
bus.py — settle window, deduplication per key, single-flight per space, revision cancellation; a new user message cancels stale background work that began from older state. Events wake processing but are not executable instructions.
writer.py — origin and same-content TTL journal suppress own-write echo; atomic temp+replace avoids own-run recursion.
runner.py — materializes visible inbox/digest/record channels with run IDs, separates low-cost attention from expensive consolidation.
arbiter.py — class-owned max intervention levels, budget and feedback, inhibition of repeat winners; raw evidence required for actionable finding. No model decides own right to interrupt.
proposals.py — first-class proposed -> accepted / rejected / stale state, typed contract-field deltas; accepted human proposal is distinct from detector observation.
ledger.py — source-linked run cards and decisions.
memory.py — SQLite Claim with provenance/evidence, valid_from/to separate from recorded_at/closed_at, closure reason, derived_from parents, recursive quarantine of dependent claims. Old record retained rather than erased.
consolidator.py — only quote-grounded source facts; exact quoted substring must appear in text. Hash-based per-file version idempotence; disappeared quote closes claim and quarantines downstream; semantic neighbor dedup ADD/UPDATE/NOOP. MAX_CHARS=6000, MAX_FACTS=10: source is a short space note, NOT full scientific document input.
This is an implemented domain-specific continuous observation loop, not merely a planned nonlinear architecture.

EXECUTABLE TEST WITNESS — RERUN ON 2026-10-10
Environment: Python 3, pytest 9.0.3, PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; no pytest cache, no live provider.
Command, from bottomup/:
python -m pytest -q -p no:cacheprovider evals/deterministic/test_bottomup_bus.py evals/deterministic/test_bottomup_writer.py evals/deterministic/test_bottomup_memory.py evals/deterministic/test_bottomup_arbiter.py evals/deterministic/test_bottomup_consolidator.py
Output: 46 passed in 1.23s; EXIT_CODE=0.
After run: git status --short was empty; same HEAD.
Evidence in test source:
- Bus: batch settling, repeat key collapses, in-flight single-flight, own-origin suppression, foreign space rejection, user cancellation, revision increments only for user events.
- Writer: no own write loop, foreign writes observed, journal consumptive and expiry, atomic write, temp ignore.
- Memory: no provenance -> reject; closure retains evidence; dependent quarantine cascades; unrelated branches unaffected; history preserved.
- Arbiter: no evidence -> refuse; bounded slot, class ceiling, feedback replenishment, unsuppressible contract breach.
- Consolidator: exact quote is required; hallucinated/vanished quote rejected or closes claim; hash idempotence; partial model failure leaves queue; dedup UPDATE/NOOP behavior.
These five suites passing is NOT proof of the old report's entire 796 bottomup / 911 topdown tests or live multi-provider behavior.

HISTORICAL PRODUCTION-SEAM WARNING — 2026-09-04
Original bottomup/ОБЪЕДИНЕНИЕ.md documents joint demonstration integration, with reported 121 smoke ×3 and 796/911 tests, but expressly identifies open holes:
1. Direct SQL writes by topdown tools (save_note, manage_memory, add_file_facts; also financial variants) circumvent bottomup Consolidator and its evidence/dependency invariants. Some were disabled in demo rather than truly integrated.
2. Accepted intent change may produce a contract value absent from closed dictionary of (intent, position, truth_mode); update_contract_field does not validate cross-field tuple consistency.
3. UI writes directly to fact projection are overwritten by next consolidator projection. Canonical edits must address source claim, not derived view.
4. Native integration exists for dashboard demo; CLI/Telegram build other Waku instances without same seam.
5. Demonstration home is temporary per-process; no durable release-grade state guarantees.
6. One graph-workflow fast path bypasses bottomup system-prompt integration when enabled.
These are historical statements tied to 2026-09-04; later fixes in other branches have not been evaluated and should not be assumed present or absent.

IMPORTANT PHILOSOPHICAL/ARCHITECTURAL DISTINCTION
Here bottom-up is a change/recognition/attention system over a space, with *conditional* activations, not a universal semantic research Object/Method cutter. The exact-quote Consolidator extracts maintainable claims from bounded notes. Its 6000-char source cap explicitly makes it inapplicable as a complete full-text authorabstract evidence provider without redesign.
What transfers is the operational law: real source event -> versioned evidence -> proposal -> authorized decision -> dependent invalidation; and no changes from own writes mistakenly treated as external new evidence.

SESHAT DISPOSITIONS
REUSE selectively: deterministic EventBus/LoopWriter/LoopMemory invariants, evidence/source hash, bitemporal lifetimes, revision cancel, proposal/invalidation vocabulary, tested negative examples.
WRAP: original-specific APIs as read-only/observation and event providers; adapters preserve source status, host ownership and preexisting SQL/projection boundaries.
EXTRACT: typed EventReceipt, SourceChange, Provenance, CandidateProposal, Approval/Decline, Cancellation, DependencyQuarantine, TraceRecord after contract verification.
COMPLETE: cross-host source version/hashes, trusted action actor, optimistic concurrency on proposal admission, correct projection writes, durable persistence and prompt/source access policy.
DEPRECATE as universal: source-note 6000-char consolidation for SESHAT FULL_REQUIRED, original exact-quote rule as sufficient to reconstruct distributed scientific Object/Method, original attention budget as semantic acceptance right.
UNKNOWN: production post-2026-09-04 integration closure, live Qwen behavior, original bottomup/space/arena version divergence after pinned checkout.

IMPLEMENTATION LEAD INTAKE
S1 current source-access PR: proceed; no direct blocker.
S2: test true parent/descendant STALE/quarantine separation, source update, identity/cancellation on concurrent revisions, accepted proposals under authority.
S3: note consolidation may produce candidate observations but cannot replace whole-source method provider.
S5: cross-host adapters only after preserving original topdown/bottomup independence under ADR 0006 and resolving direct SQL side-door issue.
S6: use this event-driven loop as alternate topology comparison to fixed cut/pipeline and reciprocal reconstruction, not as universal scheduling mandate.

SPECIFIC TESTS / ENGINEERING WORK
See GitHub issue #11, BUP-T01..T07. Before adopting, verify exact last-good branch, tests in implementation target, no silent public/private prompt leakage, and meaning of read receipts. Never take old PASS counts as current CI PASS.

FOLLOW-ON AUDIT
Read original topdown and bottomup source-claim write paths for historical merge outcome; examine later branch revisions where actual bypass bugs were fixed, if any. Inventory space and arena separately. Preserve negative cases and decision reasons alongside any extracted component.
