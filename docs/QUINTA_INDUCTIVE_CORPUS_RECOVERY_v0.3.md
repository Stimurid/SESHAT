# Quinta original-source and inductive corpus recovery v0.3

**Status:** source-grounded historical archaeology, not implementation verification.
**Owner:** SESHAT archaeology stream, separate from Implementation Lead.
**Drive record (full):** [04 — Quinta Original Corpus & Inductive Recovery](https://docs.google.com/document/d/1Xc5YHVI125H5gzA64CMG3U4fSwy9DjlLO1anya3t4RI/edit)
**Standing intake:** [S-COORD-001 / #6](https://github.com/Stimurid/SESHAT/issues/6).
**Earlier physical recovery:** [QUINTA_LOCAL_LEGACY_BODY_RECOVERY_v0.2.md](QUINTA_LOCAL_LEGACY_BODY_RECOVERY_v0.2.md).

## Evidence carriers — read-only local inspection

Verified on authorized device `timlenovo`:
- `C:\projects\Claude\TRIZ\inventive-memory-bench-mvp\` — pre-repository working-source snapshot; `agentRuns.ts` is byte-identical to current `C:\projects\quinta`, and matches `Stimurid/quinta` initial/current Git blobs.
- `C:\projects\Claude\TRIZ\architecture\` — 12 early architecture docs; explicitly notes mock prompt import, deterministic agents and template-based KOSMOS in `FOUNDATION_RUN_REPORT.md`.
- `C:\projects\Claude\TRIZ\ТРИЗовец\` — raw TRIZ/MTM PDF/text source bodies.
- `C:\projects\Claude\TRIZ\triz-bot-claude-project_scaffold_v0_2026-05-09\triz-bot-claude-project\_READY_FOR_CLAUDE\` — converted corpus + metadata and prior analytical work.

**Original authored prompt contents are not reproduced in this public Git record.** They are method-source carriers and may have different ownership/access limits from source code.

## Physical corpus topology

`_READY_FOR_CLAUDE/INDEX.md` and `PACKAGE_REPORT.md` report **18 converted Markdown documents**, roughly **3.3 MiB**, and a 21-file isolated ZIP of conversions plus three indexes. Distribution:
- core TRIZ: 4;
- architecture/IT: 2;
- MTM agents/infra: 7;
- game layer: 1;
- review/possible duplicate: 4.

Missing from **that specific conversion bundle**, not necessarily globally absent: classical TRIZ glossary and education cases. Originals/raw exports reside outside the isolated ZIP. `WHAT_TO_READ_FIRST.md` specifies manifest IDs, source SHA-256 and PDF page markers. A conversion, digest, and raw original are distinct `SourceCarrier` stages and should not be flattened.

Four review candidates were explicitly NOT generally admitted as canonical: `triz_new_hcore`, `industy_mapper`, `module_guide_core_42`, `quality_of_mind_operator_2`.

## A crucial rejected generation — do not promote it

Prior `_analysis/02_FIELD_ORCHESTRATOR_EXTRACTION/` contains a rich-sounding three-part field/orchestrator/multiagent model. **The later `_analysis/02_INDUCTIVE_EXTRACTION/INDUCTIVE_EXTRACTION_COMPLETE.md` explicitly rejects this prior approach as filling a predetermined architecture.** It permits using prior notes only as recall/check material, not as architectural evidence.

This makes an earlier SESHAT enthusiasm for the model an overclaim. The early orchestrator remains a **SPEC/NEGATIVE DONOR** and candidate **topology hypothesis**, not an observed runtime or corpus-proved universal machine.

## Inductive generation: historical analytical results with provenance limitations

The distinct `02_INDUCTIVE_EXTRACTION/` has:
- `01_RAW_PHENOMENA_LEDGER.md`
- `02_EMERGENT_CLUSTERS.md`
- `03_FIELD_DYNAMICS_FROM_CORPUS.md`
- `04_AGENTIC_FORCES_FROM_CORPUS.md`
- `05_INTERFACE_FROM_DYNAMICS.md`
- `06_PROMPT_CONTAMINATION_AUDIT.md`
- `FOR_TIMUR_REVIEW.md`
- `INDUCTIVE_EXTRACTION_COMPLETE.md`

Its own completion report states: **18/18 digests, 78 phenomena, 16 emergent clusters A–P and 13 unassigned phenomena, nine field dynamics, eleven agentic forces + one coordination function, ten conflict pairs**. These are claims of a completed *historical analysis*, not independent runtime test results or a fresh re-evaluation of the original texts in this audit.

Reported strong clusters include:
- **A** wave/deepening with altered viewpoint;
- **B** quality gates against premature completion;
- **D** object redefinition affecting available operations;
- **G** composable units with combination rules;
- **M** TRIZ as operational prompt system (notably supported by *one* document).

Other notable patterns: **C** errors/negative outcomes as input, **J** reverse-flow problem formation and **O** managing temporal rhythm/pauses.

The report says C–M–T explains only **6/18** documents. It flags pseudo-calculators without formulas, embodied metaphors without machine-sensed referents, synthetic interface forms, and ten conflict pairs **without a demonstrative case of conflict producing a solution**. These cannot silently count as implemented or verified SESHAT operations.

## Prompt contamination: original model versus sourced distinction

The separate `06_PROMPT_CONTAMINATION_AUDIT.md` audits analytical vocabulary against the user's initial instruction and source phrasing. It downgrades labels such as **engineering grounding** and **anti-slop** to analyst synthesis/external terms, while keeping the source-supported underlying functions distinguishable.

**Guardrail:** `corpus passage` → `converted passage` → `digest` → `coded phenomenon` → `inductive cluster` → `architecture proposal` → `executed implementation` → `tested / accepted` are eight different evidence levels. Preserve transformation provenance and mark synthesis; do not infer universal ontologies from the analysis frame.

The original `architecture/05_AGENT_FOUNDRY.md` proposes shrinking full prompts to <500-token kernels by removing philosophy/poetic context. That is **not** an authorized global operation for SESHAT or distributed authorabstract Object/Method. It is at best an ablation candidate against complete original source methods; reduction could remove method-bearing commitments.

## Per-gate relevance, no scope hijack

- **S1** source access: reinforcing provenance/whole-source integrity, no new blocker to PR #5.
- **S2** state/reconciliation: explore typed conflicts, competing projections, source invalidation, but no unvalidated TRIZ field-state import.
- **S3** semantic methods: full original method bodies, audit trail for conversion/digest/derived prompt; no automatic prompt-kernel shrinkage.
- **S5** Quinta donor adapter: original AgentRun code duplicates retained current code; wrap/test rather than importing same file.
- **S6** topology evaluation: conditional non-linear activation/field scheduling is a candidate T5 to evaluate, not a pre-selected winner. Early rejected model is negative case; inductive generation is evidence for hypotheses, not executable proof.

## Requested follow-on archaeology

1. Verify a bounded sample of original converted sources against `source_sha256`, page markers and manifest; identify missing/de-duplicated sources without assuming package completeness.
2. Trace strongest phenomena A/B/D/G/M to source passage anchors; preserve analyst constructs as such.
3. Test reachability and execution against current/old Quinta code (do not equate file presence with active UI).
4. Apply same all-generation standard to Tinkuy, Socrates and other SESHAT donors before transfer.

**Builder:** consume through [issue #6](https://github.com/Stimurid/SESHAT/issues/6). This document does not authorize concurrent writes to SESHAT `src/` or `tests/`.

## Original-source integrity validation — 2026-10-10

A **read-only automated file check** enumerated all converted Markdown bodies with `source_path` and `source_sha256` in YAML frontmatter under `_READY_FOR_CLAUDE/`, resolved each original inside the local scaffold, and computed the actual SHA-256 of that physical original.

Result: **18 MATCH / 0 MISMATCH / 0 MISSING**.

Verified source categories included TXT, PDF and one Google-Docs-exported DOCX, including the human-review candidates. Example three exact digests confirmed:
- `triz_meta_apex_core_txt.md` → `90_raw_exports/txt_originals/triz_meta_apex_core_txt.txt` = `ec8b106ec4fef25b38be3099e3ed0b0abac5e598cfc64c0ca07b4932108a9555`.
- `mtm_orkestrator_telo_2_pdf.md` → `90_raw_exports/pdf_originals/mtm_orkestrator_telo_2_pdf.pdf` = `227a8427cdf423dd279ac857e0ab22de5b134cf9c93354c1a0d1d9afdbb70f40`.
- `triz_new_hcore_pdf.md` → `90_raw_exports/pdf_originals/triz_new_hcore_pdf.pdf` = `be711c45d834195d337699ac1b5c18aec66b81fa873e8b46e5b5948827350310`; this remains in the human-review cluster despite file identity passing.

**Do not overinterpret the PASS:** it establishes *raw original path presence and content identity relative to conversion metadata*, not full text extraction fidelity, semantic validity, copyright clearance or canonical admission of disputed versions. It does not cover source documents absent from this particular 18-file bundle.

**Action for SESHAT S1/S3:** preservation of source-hash lineage is practically supported by an existing corpus. Model the source version/digest verification independently of method-authority and quality review. Use synthetic/public fixtures for CI; no need to upload private originals to public Git.
