# S-F08-EVIDENCE-001 — atomic model quote gate over F07/PDF

2026-10-21 | Canonical issue: https://github.com/Stimurid/SESHAT/issues/69

## Status

ENGINEERING_REVIEW_FIX_2 / LOCAL_SCOPED_120_PASS / FULL_LOCAL_QA_831_PASS_1_SKIP / REMOTE_SUCCESSOR_CI_PENDING / INDEPENDENT_SUCCESSOR_REVIEW_PENDING / **REAL_AUTHORIAL_SCIENCE_NOT_READY / CUSTOMER_NOT_AUTHORIZED**.

This is stacked *after* source-pinned PDF primitive PR #68, not a replacement for F07 rights or for G1 MethodBody provenance. The historical owner-excluded source family remains archival only. No new privileged issuer/server, original authorial method, private PDF or provider secret is included.

## Executable contract

New `src/seshat/pdf_claims.py` accepts an **exact serialized JSON byte stream** plus an existing policy-scoped `RuntimeSourceAccess` and a declared PDF source identity. Strict, extra-forbid models cap response and claims/unknowns size; every model claim includes 1-based PDF page, exact verbatim excerpt and claim text, typed evidence kind. The gate never reads raw source bytes or self-asserted source hashes from candidate JSON: the complete exact source must already pass F07 FULL_REQUIRED on the configured provider, including declared/actual MIME `application/pdf`, source version, SHA and verified FULL access receipt.

The gate performs ONE admitted F07 source read, ONE PDF parse and ONE extraction per distinct cited page, using an INTERNAL helper that is not itself a source-admission API. Each model citation is then checked for an exact extracted-text window. Misaddressed, joined, nonadjacent, ambiguous, unsupported or invented excerpts fail. **Atomic status:** one failed quote makes the entire candidate `REJECTED / CLAIM_EVIDENCE_FAILED` even if other quotes verify. All quotes exact yields only `EXACT_PDF_PAGE_EXCERPTS_VERIFIED`. That means byte/page-extractor evidence only; it does not prove the claim logically follows the quote.

Result `ModelQuoteGateReceipt` is owner-private and intentionally fingerprint-bearing, with source/read/response hashes, per-claim error codes, no page/claim/quote prose. Its exact YES-equivalent fields never become scientific or legal grants: `semantic_entailment=NOT_ASSESSED`, `real_model_identity=NOT_INDEPENDENTLY_ATTESTED`, `rights_independently_attested=NO`, `scientific_acceptance=NOT_ASSERTED`, `customer_release=NOT_AUTHORIZED`. Additional model/PDF runtime attestation is a separate future gate. A serialized receipt remains forgeable by direct in-process Pydantic construction, including a structurally valid green result with invented exact-quote entries. Only the owner-controlled verifier performs the source check; never treat deserialized receipts as independently signed authority or human acceptance. It records SYNTHETIC_QA, a caller-supplied method tag, and SELF_OBSERVED_UNATTESTED provenance. The new `redacted_view()` omits source identifiers, hashes, page offsets and even the model-supplied method_id (which might itself contain a restricted title).

## Grounded red oracle from an actual synthetic model call

Actual owner-private Hub Qwen structured-model job `jx-0954d6ecffee` SUCCEEDED on only two *invented* pages. Verifier over the original preserved PDF rejects 2 of 4 cited quotes, accepts 2 individual offsets, so the model output is REJECTED overall. A separate epistemic review also observed the unsupported inference from missing calibration documentation to an instrument being uncalibrated. The original model JSON/stdout was preserved **unchanged**; a private protocol-label-only adapter converted it into this new validator's schema with no repairs to claim/excerpt/page data, proving the product module reaches the same 2/4 REJECTED result. Owner-private full evidence and hashes under `C:\AI\llm\aiye-executor\handoffs\SESHAT-20261012\S_F07_SYNTHETIC_MODEL_CANARY\actual-qwen-vs-F08-quote-gate-v1.json`; not replicated in public CI.

## Tests / security boundaries

`tests/test_pdf_claims.py` uses only two dissimilar invented PDFs and bounded JSON fixtures; tests full green quote set, four-claim 2/4 red set, false source ID/version or hash, wrong pages/excerpts, overlapping ambiguity, malformed JSON and duplicate JSON keys, bad field types, coerced boolean page, denied and partial F07, forged rights/acceptance, giant response, and a *semantically false claim attached to an exact quote* which must still be marked `semantic_entailment=NOT_ASSESSED`.

Post-Opus rework scoped+PDF/SourceAccess **120 PASS**, Ruff PASS. Native Windows **full regression: 831 passed, 1 skipped, 2 existing warnings, EXIT_CODE=0 in 98.27s** (prior original-tree QA was 810 pass / 1 skip). Exact owner-private log: `C:\\AI\\llm\\aiye-executor\\handoffs\\SESHAT-20261012\\S_F08_MODEL_CLAIMS_FULL_REGRESSION.log` (and `.status`). The field-shadow warnings were eliminated using the external `schema` JSON alias. Duplicate citations, malformed/unpaired Unicode, JSON schema/size anomalies and unauthorized state fail closed. Remote successor CI and rootless `--network none --read-only --cap-drop ALL` hardened Docker CI are next release evidence gates; no assertions about their result before terminal receipt.

## Remaining gates

Source and method rights are STILL unproven for original works; this module accepts `run_scope=SYNTHETIC_QA` only. Parent #68 requires OS-bounded PDF execution before any real/untrusted source: tracked separately at https://github.com/Stimurid/SESHAT/issues/70 . The gate no longer reparses per quote: it parses once and extracts each distinct cited page once. Real/untrusted originals still require the separately reviewed OS resource sandbox #70, because Python extraction limits do not stop CPU/memory bombs before checking. The whole project still lacks genuine authorial MethodBody execution with certified F07 rights/G1 causal ledger and scientific/client acceptance. Keep #68 and this dependent change DRAFT, no merge, no release.


## Second independent Opus review remediation (current successor after 4be062b)

Read-only exact SHA audit of `4be062b` returned CONDITIONAL_PASS for synthetic quote-gate engineering, REAL_AUTHORIAL_SCIENCE=NOT_READY. The reviewer confirmed ONE F07 admission/read, ONE PDF parse, typed Unicode/duplicate rejection, no source text or real source, and no quote-to-semantic-entailment promotion. Additional medium findings were closed in the next code revision:

* Internal multi-excerpt helper now requires a complete typed `SourceAccessReceipt` and checks the actual PDF bytes hash, identity, version and length against it, then derives its own receipt SHA. Its previous arbitrary caller-supplied digest string is no longer accepted. This is still a PRIVATE helper, not an independent rights authority.
* The former redundant `SOURCE_DRIFT` per-proof branch is labelled `INTERNAL_PROOF_MISMATCH` and explicitly documented as an invariant within ONE read; it is not falsely represented as another live provider read or source freshness check.
* Public `code` is now a strict closed `QuoteGateOutcomeCode` Literal. Arbitrary caller text on a forged private receipt is rejected when projected via `redacted_view()`, rather than laundered into a public summary.
* Model-supplied `method_id` on candidate and private receipt is restricted to bounded ASCII safe identifier characters. Surrogate, prose and control/punctuation injection are rejected as malformed schema before source access. The public summary omits it entirely.
* Additional negatives verify a forged public code cannot be projected, invalid method labels fail safely, and a private helper cannot apply a genuine F07 receipt from PDF-B to PDF-A. Use only invented fixtures.

Owner-controlled AORUS targeted QA on this patch: **126 PASS / Ruff PASS**; full native project regression **837 passed, 1 skipped, 2 pre-existing warnings, EXIT_CODE=0 in 107.12s**. Private full-run receipt: `C:\AI\llm\aiye-executor\handoffs\SESHAT-20261012\PR71_OPUS_FINAL_REWORK_FULL_REGRESSION.log`. The remediated successor must still get its OWN remote CI and independent next-SHA review. In-process pypdf remains SYNTHETIC_QA ONLY; OS sandbox #70 is a separate hard prerequisite for untrusted originals.
