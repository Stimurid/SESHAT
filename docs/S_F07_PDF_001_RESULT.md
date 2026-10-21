# S-F07-PDF-001 — PDF page-evidence engineering receipt (2026-10-21)

**Scope:** additive, offline, source-agnostic PDF-byte/page-text validation.
**Current disposition:** SOURCE_IMPLEMENTED / PREVIOUS_SHA_REMOTE_CI_PASS / INDEPENDENT_OPUS_CONDITIONAL_PASS_WITH_REPAIRS / SECURITY_H1_M2_M3_M4_M6_M7_LOCAL_REPAIR_TESTED / NEW_FULL_WINDOWS_QA_782_PASS_1_SKIP / NEW_REMOTE_CI_PENDING / SCIENCE_AND_CUSTOMER_NOT_READY.
**Authority:** https://github.com/Stimurid/SESHAT/issues/67
**Base:** PR #66 branch `fix/seshat-windows-f09a-fsync-20261021` at `697fce2bde9a12a2193efb6d7923ab0af9353c2f`.
**Work branch:** `aiye/exec-a3d0954d1651` in an isolated AORUS Hub worktree. Single agent run `jx-a3d0954d1651` stopped at `FAILED/max_turns` after authoring code and tests; this is not a PASS receipt. Source was preserved in WIP commit `c66a602c78892e8ebc21fb2ffcb8fbaaaf5e9686`. Post-WIP fixes to type validation, excerpt ambiguity and receipt schema were performed by the supervising engineer on the same isolated worktree, after the author stopped. Do not silently elevate failed agent status into product acceptance.

## Implemented components

- `src/seshat/runtime.py`: `RuntimeSourceAccess` validates opaque `application/pdf` exact bytes, identity/version, `authorized` and `complete` flags, media type, size and SHA. Only `FULL_REQUIRED` opens complete content; non-text `char_range` remains forbidden. This is a **local policy-and-integrity check** on the configured provider, not independent proof of actual legal/owner rights.
- `src/seshat/fabric_waves/source_access.py`: BOTH `FULL_REQUIRED` and `DRILLBACK` text-payload branches now reject declared or supplied nontext media before any UTF-8 decode with `SOURCE_MEDIA_TEXT_PROJECTION_UNSUPPORTED`. This closes the independent review's H1 ASCII-decodable PDF byte-window bypass.
- `src/seshat/pdf_page_evidence.py`: accepts a policy-scoped `RuntimeSourceAccess`, obtains bytes PLUS independently checked declared/actual media type, source_version and exact FULL-read receipt in one read via `read_full_with_metadata`, requires declared `application/pdf`, parses PDF offline with pinned `pypdf`, and checks a **1-based page** and **Unicode-character-indexed excerpt** against text extracted from that page. Requires unambiguous location; overlapping excerpt matches are correctly counted. Typed rejection for invalid numeric types (including Python bool), nonexistent page, source/read failure, damaged/encrypted/empty/image-only content, out-of-range spans, inconsistent source bytes and extractor limits.
- `PdfPageEvidenceReceipt` is now explicitly OWNER_PRIVATE: it binds `source_version`, the `FULL_REQUIRED` policy and a deterministic digest of the validated FULL-read receipt, along with PDF digest+byte length, page number/count, extractor name/version, extracted page-text digest, excerpt SHA and character offset/length. It contains no raw PDF/prose, but the SHA and short-quote hashes can fingerprint protected material and must NOT be exported to unauthorized viewers. Frozen, extra-forbid/Literal model maintains `rights_independently_attested=NO`, `human_acceptance=NOT_ASSERTED`, `acceptance=PROPOSED`. It is not a signed rights grant.
- `pyproject.toml`: pinned PDF extractor `pypdf==6.21.1` for consistent source-page extraction between local, wheel, CI and Docker. No OCR/network.
- `tests/test_pdf_page_evidence.py` and `tests/test_source_access.py`: two different entirely invented in-memory source PDFs, positive exact excerpts and all listed denial cases. No protected original source, author-owned method or excluded archival sample in tests.

The original `src/seshat/fabric_waves/report_bridge.py` non-synthetic `FABRIC_METHOD_ATTESTATION_REQUIRED` gate remains untouched. This patch does not wire real authorial MethodBody execution, G1 Wave/Activation, semantic R01/R02 or F09A customer release.

## Actual local QA, not inferred from author agent

Initial author's first version before fixes: 52 scoped tests PASSED, Ruff PASS on AORUS. Independent owner-private red-QA script `C:\AI\llm\aiye-executor\handoffs\SESHAT-20261012\S_F07_PDF_INDEPENDENT_RED_QA_20261021.py` generated PDFs in memory and exposed 12 additional failing cases: strict page/offset/length types, overlapping excerpts and forged receipt status. The damaged EOF control already rejected correctly. Tests and code were repaired after author exited.

**Post-repair provisional current QA:** 65 tests PASSED combining the original scope with the independent red-QA script; after porting these negative cases into the repository's own tests, **66 scoped tests PASSED**, Ruff all checks passed, `git diff --check` passed. **Full project native Windows regression on this source tree:** `777 passed, 1 skipped, 2 known Pydantic synthetic-test warnings in 105.57s`, terminal `EXIT_CODE=0`, logs at `C:\\AI\\llm\\aiye-executor\\handoffs\\SESHAT-20261012\\S_F07_PDF_001_FULL_REGRESSION.log` and `.status`. At earlier exact SHA `d79ea86`, GitHub CI completed 3/3 SUCCESS (ci 778 PASS, wheel/oracles 778 PASS, offline smoke 89 PASS). Independent read-only Opus `jx-c0e381c0e8b1` returned CONDITIONAL PASS with blocking H1 and source-proof/export weaknesses. These were repaired in a subsequent local worktree; NEW exact-SHA CI and follow-up review still must pass. Scoped new tests and Ruff were separately observed passing after the repair. Committing/publishing the code does not itself count as scientific acceptance.

**Opus-driven follow-up QA, current repaired tree (superseding old 777-PASS parent):** 140 targeted+adjacent PASS with 1 existing synthetic warning; Ruff PASS, git diff --check PASS; full native Windows suite **782 passed, 1 skipped, 2 existing synthetic Pydantic warnings, EXIT_CODE=0** (94.28 sec), exact owner-private log `C:\AI\llm\aiye-executor\handoffs\SESHAT-20261012\S_F07_PDF_REVIEWFIX_FULL_REGRESSION.log` and .status. Successor remote CI/re-review are separate evidence gates; prior green CI was original d79ea86.

## Security boundaries, unanswered gates

1. A read of an in-process `RuntimeSourceAccess` proves only what its configured content provider supplied. A caller can construct a different in-process provider; the resulting receipt **cannot independently attest source owner, legal rights or caller authentication**. F07 actual per-operation source rights must be established separately by a controlled owner integration. Never use fake `authorized=True` as that proof.
2. Extracted-page text offsets reflect the versioned `pypdf` extraction view. They do not prove faithful raster visual layout, OCR, scanned text or original page number printed on paper. No OCR performed.
3. The 50 MiB file size, 10,000 page count and one-million-character extracted-page limits reject known outliers but **do not constitute a hard CPU/decompression-bomb sandbox**. Run only controlled, inspected sources or isolate the parser at OS process/resource boundary for untrusted files.
4. Any model-produced scientific claim remains unreviewed and must cite approved carrier/versions; `E5`/local `PROPOSED` cannot self-promote to `E1` or human `ACCEPTED`.
5. Entirely private source and MethodBody bytes must stay out of public repository, CI logs and customer exports. The user-declared archival source freeze remains binding; tests and active cases do not reuse it.
6. This engineering patch does not claim an actual independent MethodBody/model invocation, an original PDF scientific evaluation, or readiness of client R01–R09.

## Reproduction

From the checked-out exact worktree with a Python environment supporting the declared dependencies:

```bash
python -m pytest -q -p no:cacheprovider tests/test_pdf_page_evidence.py tests/test_source_access.py
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache .
git diff --check
```

The separate owner-private red-QA script should also be re-run on the final exact SHA; its cases have been promoted into the committed tests. Do not call a test runner successful until its process has reached exit 0.

## Next evidence gate

Keep stacked Draft PR #68 against PR #66; after the Opus-driven repair, run full regression and independent hardening checks on the exact new commit, publish the new SHA, re-run all three remote CI workflows including unprivileged hardened Docker PDF tests, then obtain read-only review of all changed gates. Do not treat the earlier d79ea86 CI as approval of the successor.

For a subsequent scientific run, the private pre-admission candidate is `I11_ACTIVITY_NETWORK@v1.0`, tracked in the owner-private REPORT-FIRST FRONTIER and an owner-private JSON manifest. Two alternative original source files were found by exact Drive metadata, but **neither has a current F07 full-read rights grant or exact source SHA pin from a permitted run**. Do not automatically execute or transfer them: the next gate is source rights and original-byte admission first, followed by exact method-body version, actual model execution, provenance-bearing report and separate human scientific assessment. No privileged server resurrection.
