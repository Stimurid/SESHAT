# S-P1-F07 — source-only implementation receipt

## Scope and pins

- Base: `Stimurid/SESHAT` `origin/main@2ec1209dd2bb9c5a81e12e70725cad02de3087b1`.
- Task: [#56](https://github.com/Stimurid/SESHAT/issues/56); coordination: [#6](https://github.com/Stimurid/SESHAT/issues/6).
- Owner source: [authorabstract machine v0.12](https://docs.google.com/document/d/1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k/edit), read-only. Its four source regimes distinguish one work, a local corpus, additional internal data, and an external corpus. F07 only supplies pinned corpus metadata selections; it does not infer scientific meaning.
- Changed paths: `src/seshat/corpus.py`, `src/seshat/corpus_adapters.py`, `src/seshat/__init__.py`, `tests/test_corpus_selection.py`, this receipt, and `README.md`.

## API and semantics

`CorpusSelectionSpec` pins a stable selector ID/version, source manifest ID/version/SHA-256, caller/view and `F07-1` semantics. Its `Predicate` is a closed typed DSL: exact study IDs, inclusive integer ranges on an explicitly named field, exact field values, AND, OR. `canonical_json` sorts set-like IDs/values and commutative children before hashing. No predicate text is evaluated as code. Source roles, specialty, year kinds, lab and supervisor are field names declared by an adapter and backed by `EvidenceField.evidence_ref`; missing values remain unknown. An undeclared field is not evaluable. Source roles are evidenced separately per carrier. The core has no medical or Sechenovka-specific branch.

`build_corpus_space` asks the trusted host `EntitlementAuthority` for a revision, study visibility, every carrier's visibility, permission to count denied studies, and a keyed seal of the canonical predicate. It evaluates no metadata before the visibility decision. Its immutable `CorpusSpaceSnapshot` contains exact, sorted, unique visible `object_id@version` and carrier ID/version/SHA pins; visible study and carrier denominators; true, false, unknown and not-evaluable counts. The snapshot retains the **host-sealed selection digest** and digest of the manifest pin, not the predicate body, unkeyed selector SHA, selector ID, caller ID or manifest address, because those can mention guessable hidden IDs. The source specification must be held under host rights and passed separately to `require_current`. Without denied-count permission, the receipt emits `denied_studies=null` and only `suppressed_remainder=true` rather than a hidden population total. A study with an unauthorized carrier is suppressed as a whole. Conflicting duplicate visible study IDs fail closed. Identical duplicates count once.

The snapshot always says `METADATA_ONLY`, `runtime_ingestion_state=NOT_ASSERTED`, `semantic_acceptance_state=NOT_ASSERTED`, and each carrier pin says `PIN_ASSERTED_NOT_VERIFIED`. A carrier SHA pin is an asserted source identity, not proof of readable bytes, runtime ingestion, identity review or semantic acceptance. F07 does not call `RuntimeSourceAccess` or claim `FULL_REQUIRED`; that remains the S1 runtime gate. `require_current` rebuilds from current host rights and manifest and rejects drift with `StaleCorpusSpaceError`. Persisted snapshots require that check before use. The core never creates or accepts a `DerivedObject`. `accepted_current_one` reads current blackboard state and raises on competing accepted objects; `accepted_state()` is historical and may include now-stale revisions.

`evidenced_study` is a second-host neutral adapter. `sechenovka_v4_metadata_row` maps only an **already authorized** runtime row's intake `year`, optional nonempty `specialty_raw`, and abstract/dissertation identity pins. It does not fetch Drive data or infer lab/supervisor/school from `source_performed`, defense council, title or affiliation. The adapter's output contains private identifiers at runtime; hosts must not serialize it into public logs. This repository contains no private row IDs or PDF URLs.

The host must verify that field provenance and study/carrier pins belong to the pinned manifest before passing records to F07. `evidence_ref` is an address, not a self-authenticating proof. The host also owns the monotonic authorization revision: a policy change must advance it even when currently visible membership happens to remain the same.

## Synthetic acceptance matrix

The test module has invented study and carrier IDs. Its 186-study synthetic distribution reproduces the public aggregate oracles from [#56](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6153309817): 2021–2023 = 54 studies/31 pairs/51 known specialties; 2024–2026 = 132/63/31; 2025 = 93/38/4; 2026 = 12/12/0; whole = 186 studies/280 carriers. It also covers two distinct selectors on one manifest, input permutation, boundary inclusion, AND/OR overlap, missing metadata, unauthorized and revoked studies/carriers, changed source/provenance/version, duplicate conflict, second-host arbitrary fields, and historical versus current acceptance. These are mechanical source tests, not a blind holdout. All 186 real v4 records were development-exposed; four PDF file records need identity review and are not asserted to represent four distinct studies.

## Gate and limits

**Status: ENGINEERED_UNREVIEWED, STATIC_CHECK_ONLY.** The delegated worker did not run project Python, pytest, Ruff, unreviewed demo code or a privileged Git publisher on credentialed Windows. Test assertions are source authored, not test results. The Hub snapshot publisher, independent reviewer and truly isolated exact-tree CI must supply commit/tree, test outcome and review verdict before `TESTED` or engineering acceptance. No Drive sync, PR, merge, F06/F08/F09 function, R01–R09 reports, scientific validity or product release is claimed. Rollback is removal of this isolated F07 file set and `__init__` exports; accepted S1/S2 runtime behavior was not edited.

The explicit delegated job passport is the authorization used for this isolated F07 authoring pass. The latest read-only #6/#56 comments describe a separate RUG author/review chain, but do not establish its terminal runtime state; the Hub must verify the sole-writer gate before publishing this snapshot. `git diff --check` passed; local Python/AST, pytest and Ruff were unavailable or intentionally not run in this credentialed sandbox.

## Open engineering questions and defaults

- Which private host metadata fields beyond intake year and specialty are authorized? Default: none; lab/supervisor and alternate year roles remain unknown/not evaluable until independently evidenced.
- May a specific caller learn denied population counts? Default: no; only the trusted host authority can grant it.
- Is the v4 manifest already runtime ingested and identity verified? Default: no; F07 emits `METADATA_ONLY` and makes no full-source or semantic claim.
