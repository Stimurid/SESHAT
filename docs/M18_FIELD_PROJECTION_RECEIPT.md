# M18 R03/R04 field-projection receipt

Status: `IMPLEMENTED_AWAITING_NATIVE_EXECUTION`

Scope: `SESHAT-M18 / ONE ENGINEERING WRITER / substantive R03/R04 field
projections / 2026-10-23`. Base commit: `8420e13318dea1c66025decf517ff74c03d127ef`
(`aiye/exec-fbb3d7ef8e1c`), M17 source repair. M17 (`src/seshat/m17_source_carpet.py`,
`src/seshat/authorial_oracle.py`) was **not** rebuilt; this change only reuses
its typed overlay import.

## What this bounded worker could and could not do

This session is a bounded, sandboxed CLI worker confined to the git worktree
`C:\AI\llm\aiye-executor\worktrees\jx-311c339ddaba`. Two environmental limits
applied for the whole session, both confirmed by direct tool denial rather
than assumed:

1. **The real source pilot was unreachable.** The task passport points at
   `C:\AI\llm\aiye-executor\handoffs\SESHAT-M18-FOUR-REAL-STUDIES-20261023`
   (manifest_dent.json / manifest_surg.json, eight real A/D PDFs). A direct
   `Read` against `manifest_dent.json` in that folder was denied twice with
   "you haven't granted it yet" (no interactive approver exists in this run),
   and a directory listing was denied as outside the allowed worktree. This
   worker therefore has **not seen** the real manifests, the real PDFs, or the
   real per-study metadata (titles, true defense years, true object/method
   tags). All schema and fixture decisions below are inferred from the
   existing M17/M13-M16 code and tests, not from the real pilot files.
2. **No command execution is authorized in this session.** Running `python`
   (even `python -c "print(1+1)"`) through the Bash tool returned "This
   command requires approval", and the PowerShell tool in this environment
   cannot parse any command at all (`pwsh` reports a garbled-encoding parse
   error independent of this task). Consequently **pytest, Ruff, and the
   owner-private CLI run were not executed by this worker.** Every claim
   below about test behaviour is a manual trace against the exact source
   written, not an observed pass. This mirrors the prior M17 receipt's
   documented execution gap; it has not improved in this session.

Per the standing instruction for this run ("nobody can answer questions...
state your assumptions explicitly... say what you could not verify and
why"), the two points above are treated as the load-bearing facts the rest
of this receipt is built on, not as blockers that stopped the work.

## DEFECT1 — year/object/method/infrastructure double counting (fixed)

`build_reports`'s old R03 `field_map` iterated `Counter(... for x in chosen
...)` over every selected **source carrier**. A study with one A carrier and
one D carrier was counted twice for its year and for every shared
object/method/infrastructure tag (the passport's concrete example: two
surgery ResearchObjects reading as `2022:2, 2024:2`).

Fix, in `src/seshat/product_preview.py`:

- `_per_study_field_metadata` groups selected sources by `study_id` first,
  unions each study's `objects`/`methods`/`infrastructure` tags *before*
  counting, and counts each tag/year once per distinct study. `source_count`
  (carrier count) is unchanged and still reported separately from
  `study_count`.
- `_study_year` resolves one authoritative year per study. It prefers a new
  optional per-source manifest field `defense_year` (the study's own
  event/authorial year, expected identical across all of a study's carriers)
  and falls back to the existing `year` field (the *carrier's own*
  upload/publication year) only when `defense_year` is absent everywhere for
  that study. **It never silently picks one disagreeing value**: if a
  study's carriers disagree (on `defense_year`, or on `year` as a fallback),
  the study's year bucket becomes `"CONFLICT"` and the disagreement is
  recorded verbatim in a new `field_map["year_discrepancies"]` list
  (`{study_id, field, conflicting_values, status}`), and
  `"YEAR_METADATA_DISCREPANCY_UNRESOLVED"` is added to that report's
  `limitations`.
- `field_map["years"]` is now the per-study-deduped authoritative count;
  `field_map["source_upload_years"]` is a new, separate, intentionally
  per-carrier counter (upload/document year, not deduped) so the
  source-upload-year-vs-defense-year distinction the passport asked for is
  visible as two different fields rather than collapsed into one.

### Assumption (open — see below)

The real manifest schema was not readable in this session. `defense_year` is
a **new, optional** field this worker is introducing on the source-spec
object (sibling to the existing `year`); it is additive and backward
compatible (`ingest_sources` defaults it to `None`, existing manifests
without it fall back to the old `year`-based behaviour, just deduped per
study instead of per carrier). If the real manifests already encode a
defense/event year under a different key, that key must be mapped to
`defense_year` (or the field name changed) before the real run — this was
not knowable without reading `manifest_dent.json`/`manifest_surg.json`.

## DEFECT2 — fake field/atlas science (fixed)

Two sub-problems, both in `build_reports`:

1. **PDF-extraction noise counted as "the field".** `_extract_source` injects
   `"=== PAGE n ==="` banners into PDF text for page addressing; `_words`
   then tokenized that banner (and generic bibliographic boilerplate like
   `PMID`) straight into `field_map["recurring_terms"]`, which read as if the
   corpus's lexical content included literal page/citation artifacts as
   "science". Fixed: `_words` now strips the page-banner pattern before
   tokenizing and excludes `page`, `pages`, `pmid`, `issn`, `isbn`, `doi` as
   stopwords. The field is renamed `source_text_recurring_terms` with an
   explicit sibling key `source_text_recurring_terms_meaning =
   "RAW_SOURCE_TEXT_LEXICAL_FREQUENCY_NOT_SCIENTIFIC_CONCEPT"` so no reader
   can mistake raw lexical frequency for a scientific-concept extraction.
2. **No distinction between "we could read the PDF" and "a human/overlay
   actually analysed the study".** R03/R04 now each carry two explicit,
   literal status tokens:
   - `source_corpus_status`: `SOURCE_CORPUS_READABLE` (all selected sources
     extracted text) or `SOURCE_CORPUS_NOT_FULLY_READABLE`.
   - `scientific_study_analysis_status`: `SCIENTIFIC_STUDY_ANALYSIS_MISSING`
     (no manifest object/method/infrastructure tags **and** no M17 overlay
     contributes), `SCIENTIFIC_STUDY_ANALYSIS_METADATA_TAGS_ONLY` (tags
     exist but no overlay), or `SCIENTIFIC_STUDY_ANALYSIS_OVERLAY_PRESENT`
     (at least one selected ResearchObject contributes a real overlay).
     `SCIENTIFIC_STUDY_ANALYSIS_MISSING` is also added to that report's
     `limitations`, so a metadata-only run cannot read as `WORKS_UNREVIEWED`
     — it is forced to `PARTIAL`.

## M18 real semantic pipeline (R03/R04 science overlay)

New shared helper `_science_field_sections` (in `product_preview.py`) reuses
the existing M17 `analysis_view` selector-scoped overlay projection — it does
**not** reimplement study-analysis import, and does not call any model. For
every selected ResearchObject (`study_id` present in the report's resolved
`studies`) that carries a loaded `AuthorialStudyOracle`, it asks
`analysis_view` for that study's carrier-selection-scoped view (the same
function R01/R02 already use), then extracts only the question IDs relevant
to this report:

- R03 field map (`SCIENCE_FIELD_SECTION_QUESTION_IDS`): `5.2` problem, `5.3`
  objects, `5.5` performed research methods, `5.7` recording, `5.8`
  evidence, `5.9` infrastructure, `5.11` labor, `5.12` result form, `5.13`
  unfinished.
- R04 atlas (`SCIENCE_ATLAS_QUESTION_IDS`): `5.3` objects, `5.5` performed
  research methods, `5.9` infrastructure (the method/object/instrument
  subset), merged per study into each `atlas_rows[*]["science_overlay_sections"]`.

Each section entry carries exactly what the passport asked for: the
candidate answer text and modality from the owner's overlay (`E1`/`E2` as
authored), its `source_addresses` (page-level citation back to the specific
carrier), and an explicit `carrier_selection_status`
(`INCLUDED_IN_SELECTED_CARRIERS` / `OMITTED_REQUIRED_CARRIER_NOT_SELECTED` /
`NOT_AUTHORED_FOR_THIS_QUESTION`) — the same required-carrier-subset rule
M17 already enforces conservatively (an answer with no declared
`required_carrier_ids` is never surfaced, by existing M17 design).

Aggregation status is honest about what multiple-overlay means:

- `0` contributing overlays → `NO_STUDY_OVERLAY_AVAILABLE`,
  `cross_study_comparability: NOT_APPLICABLE_NO_OVERLAY`.
- `1` contributing overlay → `SINGLE_STUDY_OVERLAY_ONLY`,
  `cross_study_comparability: NOT_APPLICABLE_SINGLE_STUDY`.
- `≥2` contributing overlays → `AGGREGATED_TWO_OR_MORE_STUDY_OVERLAYS`,
  `cross_study_comparability: NEEDS_REVIEW` with an explicit rationale that
  shared or similar wording across studies is not evidence of shared
  method/object/population. This worker never computes or asserts a
  "same methods" conclusion from title or text similarity — comparability
  is always left at `NEEDS_REVIEW` (never auto-resolved) per the passport's
  explicit instruction.

R04's `actual_resource_availability` is renamed from the previous
`UNKNOWN_WITHOUT_INTERNAL_SRC_C` to the passport's literal
`RESOURCE_AVAILABLE_UNKNOWN` (or `RESOURCE_AVAILABLE_FROM_SRC_C` only when
the manifest declares `internal_evidence`); no test or other module
referenced the old string (confirmed by repo-wide grep before renaming).

### Assumption (open — "RP vs SS")

The passport's phrase for `5.5` is "performed research methods RP vs SS".
This worker could not resolve what `RP`/`SS` stand for: the two reference
documents (`1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k`,
`18xEsD_qFKnaj3TfHkQrcCmoUQq4TKAvRtWEqgNj0tMs`) are Google Docs this worker
has no fetch credential for (the passport itself reports the drive-fetch
client secret as missing), and no `RP`/`SS` acronym appears anywhere in this
repository's source, docs, or tests. Rather than invent a meaning, the
`5.5` section is labelled generically `performed_research_methods` and
simply carries through whatever modality/text the owner's own oracle
authored (`E1_SOURCE_FIXATION` vs `E2_RECONSTRUCTION_CANDIDATE`, already a
real, existing M17 distinction) — no RP/SS-specific logic was fabricated.

## Selective replay (unchanged mechanism, now covers R03/R04)

No new ledger logic was added. The existing `write_product` per-report
fingerprint (`sha256({"report": <built dict>, "sources": {...byte_sha256}})`)
already invalidates exactly the reports whose *built content* changed. Since
the new science-overlay sections are embedded directly inside R03/R04's
(and, as before, R01/R02's) returned dict, any oracle change that alters a
contributing study's view automatically changes only the reports that
actually embedded that view — reports with no study-analysis dependency
(R05–R09) are untouched and keep replaying. This is exercised by
`test_selective_replay_invalidates_only_overlay_dependent_reports` in the new
test file. `m17_source_carpet.py`'s own resume/invalidation path (keyed off
`R01`/`R02` narrative pins only) was not touched.

## Files changed

- `src/seshat/product_preview.py` — `_words` noise fix, `_study_year`,
  `_per_study_field_metadata`, `_science_field_sections`,
  `SCIENCE_FIELD_SECTION_QUESTION_IDS`, `SCIENCE_ATLAS_QUESTION_IDS`, R03/R04
  bodies in `build_reports`, `defense_year` passthrough in `ingest_sources`.
- `tests/test_m18_field_projection.py` — new. Seven tests: per-study year/tag
  dedup (the literal "4 carriers, two years → 1+1 not 2+2" case), a genuine
  A/D year-conflict case, the page-banner/PMID noise exclusion, the
  metadata-missing honest-PARTIAL case, two-overlay aggregation with
  `NEEDS_REVIEW` comparability plus a different (single-study) selector
  producing a genuinely different field, and the selective-replay case.
- `docs/M18_FIELD_PROJECTION_RECEIPT.md` — this file.

## Required native commands (not run by this worker — see above)

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='<worktree>\src'

python -m pytest -q tests\test_product_preview.py tests\test_m17_authorial_oracle.py tests\test_m18_field_projection.py
python -m ruff check src\seshat\product_preview.py tests\test_m18_field_projection.py

python -m seshat.product_preview `
  --manifest <SESHAT-M18-FOUR-REAL-STUDIES-20261023 root>\manifest_dent.json `
  --output <owner-private-case-root>\run-m18-dent

python -m seshat.product_preview `
  --manifest <SESHAT-M18-FOUR-REAL-STUDIES-20261023 root>\manifest_surg.json `
  --output <owner-private-case-root>\run-m18-surg
```

The real-corpus commands above also require whatever `study_analysis`
overlay paths the real manifests declare (or `--study-analysis` CLI
arguments) to exercise the M18 science-overlay aggregation path on real
data; this worker has not seen those paths.

## Human boundary

All generated state is `SELF_OBSERVED_UNATTESTED`. This receipt is an
engineering delivery, not independent medical/scientific acceptance and not
customer/publication approval. No standalone issuer, signing daemon, or
scientific attestor was installed, restarted, or emulated.

## OPEN QUESTIONS (default assumption used, pending owner/native confirmation)

1. **Can this worker read the real pilot manifests/PDFs?** Default used:
   no — both `Read` and directory listing outside the worktree were denied.
   All fixtures are synthetic, source-neutral, and invented by this worker.
2. **Does the real manifest already have a defense/event-year field, under
   what key?** Default used: introduce new optional `defense_year`,
   additive and backward compatible; real manifests may need a key rename
   or a one-line mapping before the native run.
3. **What do `RP`/`SS` mean in "performed research methods RP vs SS"?**
   Default used: no acronym-specific logic invented; `5.5` is carried
   through generically via the existing E1/E2 modality distinction.
4. **Can this worker execute Python/pytest/Ruff/the CLI in this session?**
   Default used: no — confirmed by direct denial of `python -c
   "print(1+1)"`; all correctness claims above are a manual source trace,
   not an observed test run. A native runner must execute the commands
   above and replace this section's claims with actual output.
5. **Should this worker commit?** Default used: no — per the prior M17
   receipt's convention ("the Hub owns the post-worker snapshot commit"),
   changes are left uncommitted in this worktree for the Hub/native runner
   to snapshot, test, and commit.
