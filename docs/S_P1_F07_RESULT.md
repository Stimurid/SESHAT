# S-P1-F07 — P1 source repair receipt (2026-10-15)

## Repair boundary and execution truth

This repair is authored against `022140bee725aec0e2987440ebfb7b382e36d655`
on the delegated worktree. `SOURCE_UNREVIEWED`, `TESTED_NO`,
`SCIENCE_ACCEPTANCE_NO`, `REAL_V4_CHECK=BLOCKED_SOURCE_ACCESS`. No project
Python, pytest, Ruff, PDF, private v4 row, production runtime, PR or release was
run or read on credentialed AORUS. The previous v4 aggregate test is SYNTHETIC.
Issue #56, its latest comments, and the v0.12 owner document were read through
connected read-only tools. The latest issue comment records the original F07
author/reviewer chain, not an approval of this repair or a release gate.

## Scope and pins

- Base: `Stimurid/SESHAT` `origin/main@2ec1209dd2bb9c5a81e12e70725cad02de3087b1`.
- Task: [#56](https://github.com/Stimurid/SESHAT/issues/56); coordination: [#6](https://github.com/Stimurid/SESHAT/issues/6).
- Owner source: [authorabstract machine v0.12](https://docs.google.com/document/d/1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k/edit), read-only. Its four source regimes distinguish one work, a local corpus, additional internal data, and an external corpus. F07 only supplies pinned corpus metadata selections; it does not infer scientific meaning.
- Changed paths: `src/seshat/corpus.py`, `src/seshat/corpus_adapters.py`, `src/seshat/__init__.py`, `tests/test_corpus_selection.py`, this receipt, and `README.md`.

## API and semantics

`CorpusSelectionSpec` pins a stable selector ID/version, source manifest ID/version/SHA-256, caller/view and `F07-1` semantics. Its `Predicate` is a closed typed DSL: exact study IDs, inclusive integer ranges on an explicitly named field, exact field values, AND, OR. `canonical_json` sorts set-like IDs/values and commutative children before hashing. No predicate text is evaluated as code. Source roles, specialty, year kinds, lab and supervisor are field names declared by an adapter and backed by `EvidenceField.evidence_ref`; missing values remain unknown. An undeclared field is not evaluable. Source roles are evidenced separately per carrier. The core has no medical or Sechenovka-specific branch.

`build_corpus_space` asks the trusted host `EntitlementAuthority` for study and carrier visibility, count rights, and a keyed selector seal. For a view without denied-count rights it emits neither denied counts nor a hidden-presence flag. The public seal and digests omit the full-population content SHA and global rights revision: hidden-only mutations do not alter the public receipt. Conflicting *visible* duplicates fail; conflicting denied duplicates are ignored. A visible study with a denied carrier is suppressed as a whole. The public receipt still includes exact sorted visible members and visible denominators. The host must keep the selection specification and callback failures in a rights-controlled scope, not a public log.

The default remains `METADATA_ONLY` and `PIN_ASSERTED_NOT_VERIFIED`. `EVIDENCE_VERIFIED` is available only with `require_verified=True` and an injected, host-owned `TrustedManifestAuthority`. The host reader first returns its independently predeclared `current_pin(manifest_id)`, then its authoritative manifest and canonical records. F07 verifies a domain-separated SHA-256 over the complete population, including field values, evidence references, carrier versions and SHA pins. Caller-supplied records and declared fields are ignored in this mode. A self-consistent forged request pin fails against `current_pin`. The host integration must protect this callback from caller substitution and must independently establish issuer rights, primary-source provenance, and file provenance; a Python protocol or SHA alone is not authentication. Neither mode claims readable source bytes, `FULL_REQUIRED`, runtime ingestion, accepted identity or scientific validity. `require_current` rebuilds the view and rejects visible drift. Hidden-only content drift is intentionally invisible to a no-count view; a new public manifest version or changed visible pin invalidates it.

## Private v4 metadata runner contract

An owner-authorized runner **outside the public repository**, in an isolated
environment, obtains SECH_MASTER_v4.json, SECH_INTAKE_v4.jsonl and SECH_QA_v4.json
through its own private rights. It validates the source file SHA-256 against an
independently approved pin and supplies per-row SHA-256 keyed by SHA-256 of
study ID to `load_private_v4_metadata_fixture`. This adapter reads only intake
JSONL metadata and never opens original PDFs or carrier URLs. Its records stay
inside the rights-controlled runtime. The runner must bind them to the master
manifest and QA records through its host-owned `TrustedManifestAuthority`,
check 186/280/94 aggregate expectations only as diagnostics, and reject any
unapproved row or manifest change. It must call F07 using the view's actual
entitlements and export only that view's serialized receipt. No raw row, ID,
path, PDF URL, callback exception or private provenance is a public CI artifact.
The four pending first-page identity cases block identity certification;
metadata-only year selection may proceed where independently pinned. If those
private files are unavailable, report `REAL_V4_CHECK=BLOCKED_SOURCE_ACCESS`.

Public CI should check out the exact Hub snapshot tree in an ephemeral runner
with no secrets or private fixtures, then run `pytest -q tests/test_corpus_selection.py`
and `git diff --check`. Synthetic tests may establish code behavior only. An
independent source reviewer must inspect the exact tree, with special attention
to callback ownership, cross-row visibility consistency, and no-count receipt
noninterference. The human owner retains semantic and publication acceptance.

`evidenced_study` is a second-host neutral adapter. `sechenovka_v4_metadata_row` maps only an **already authorized** runtime row's intake `year`, optional nonempty `specialty_raw`, and abstract/dissertation identity pins. It does not fetch Drive data or infer lab/supervisor/school from `source_performed`, defense council, title or affiliation. The adapter's output contains private identifiers at runtime; hosts must not serialize it into public logs. This repository contains no private row IDs or PDF URLs.

The host must verify that field provenance and study/carrier pins belong to the pinned manifest before passing records to F07. `evidence_ref` is an address, not a self-authenticating proof. The host also owns the monotonic authorization revision: a policy change must advance it even when currently visible membership happens to remain the same.

## Synthetic acceptance matrix

The test module has invented study and carrier IDs. Its 186-study synthetic distribution reproduces the public aggregate oracles from [#56](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6153309817): 2021–2023 = 54 studies/31 pairs/51 known specialties; 2024–2026 = 132/63/31; 2025 = 93/38/4; 2026 = 12/12/0; whole = 186 studies/280 carriers. It also covers two distinct selectors on one manifest, input permutation, boundary inclusion, AND/OR overlap, missing metadata, unauthorized and revoked studies/carriers, changed source/provenance/version, duplicate conflict, second-host arbitrary fields, and historical versus current acceptance. These are mechanical source tests, not a blind holdout. All 186 real v4 records were development-exposed; four PDF file records need identity review and are not asserted to represent four distinct studies.

## Gate and limits

**Status: SOURCE_UNREVIEWED, TESTED_NO, SCIENCE_ACCEPTANCE_NO.** The delegated worker did not run project Python, pytest, Ruff, unreviewed demo code or a privileged Git publisher on credentialed Windows. Test assertions are source authored, not test results. The Hub snapshot publisher, independent reviewer and truly isolated exact-tree CI must supply commit/tree, test outcome and review verdict before engineering acceptance. No Drive sync, PR, merge, F06/F08/F09 function, R01–R09 reports, scientific validity or product release is claimed. Rollback is restoration of the four changed F07 files to the pinned parent snapshot; accepted S1/S2 runtime behavior was not edited.

The explicit delegated job passport is the authorization used for this isolated F07 authoring pass. The latest read-only #6/#56 comments describe a separate RUG author/review chain, but do not establish its terminal runtime state; the Hub must verify the sole-writer gate before publishing this snapshot. `git diff --check` passed; local Python/AST, pytest and Ruff were unavailable or intentionally not run in this credentialed sandbox.

## Open engineering questions and defaults

- Which private host metadata fields beyond intake year and specialty are authorized? Default: none; lab/supervisor and alternate year roles remain unknown/not evaluable until independently evidenced.
- May a specific caller learn denied population counts? Default: no; only the trusted host authority can grant it.
- Is the v4 manifest already runtime ingested and identity verified? Default: no; F07's default emits `METADATA_ONLY`, while its trusted mode verifies metadata binding only and makes no full-source or semantic claim.
