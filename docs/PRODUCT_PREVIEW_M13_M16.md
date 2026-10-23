# M13–M16 product preview

This is a runnable, no-server research-product preview over owner-selected local
PDF/TXT files. It extends the existing Carpet, source, report, and F09A lines; it
does not create a separate SESHAT runtime.

Run the public synthetic two-host preview:

```powershell
python -m seshat.product_preview `
  --manifest examples/product_preview/manifest.json `
  --output artifacts/product-preview
```

Replay without duplicate method/model calls:

```powershell
python -m seshat.product_preview `
  --manifest examples/product_preview/manifest.json `
  --output artifacts/product-preview `
  --resume
```

Attach an owner-private, source-bound authorial analysis without copying it into
the public repository:

```powershell
python -m seshat.product_preview `
  --manifest C:\owner-private\manifest.json `
  --study-analysis C:\owner-private\authorial-oracle.json `
  --output C:\owner-private\run
```

The console script `seshat-product-preview` accepts the same arguments.

## Manifest contract

- `source_id` is a carrier identity and must differ from `study_id`.
- `source_kind` is `A`, `D`, `ARTICLE`, `EXTERNAL`, or `INTERNAL`.
- `path` may point to an owner-chosen `.pdf`, `.txt`, or `.md` file. The intake
  records byte SHA-256, version, size, PDF page count, and text extraction state.
  Missing, malformed, unsupported, or textless inputs remain `PARTIAL`.
- `excluded: true` preserves an owner exclusion and does not read the file.
- Generic intake does not invoke the legacy CC-BY witness/license publisher
  gate. Rights metadata may be bibliographic, but it is not a read blocker.
- `selectors` support `A_ONLY`, `D_ONLY`, `A_PLUS_D`, `ARTICLE_ONLY`, and
  `ARBITRARY`. At least three selectors must produce genuinely distinct
  memberships. A missing D source is reported; it is never assumed.
- `method_outputs` can point to existing immutable JSON outputs such as two
  historical I11 runs. Their bytes are hashed and never rewritten. A missing
  output yields an honest partial operation.
- `archive_manifest` may point to a real JSON list (or an object with a
  `records` list). The preview hashes it and counts actual records. A declared
  `archive_census_count` without a manifest is rejected, so 186 can never be
  promoted from an operator-entered number into “186 analysed studies”.
- `study_analyses` is optional and contains `{study_id, path, sha256}`
  references. The same private reference may instead be supplied by repeatable
  `--study-analysis` CLI options. The importer requires one ResearchObject
  separate from source carriers, exact SHA/version binding, fourteen ordered
  E2 candidates, page-addressed E1 claims and typed contradictions. It refuses
  a fake ModelRun or self-accepted science state.

## Outputs

- `product.json` and `index.html`: structured and browsable portfolio.
- `reports/R01..R09.{json,md,html}`: nine distinct report purposes.
- `carpet/`: actual M5/M6 `WaveEngine` artifacts, including events, waves,
  activations, sediment, two host contexts, and delta/selective-replay oracles.
- `carpet/m17_source_bound/`: selected-source `WaveEngine` events and actual
  thread activations plus sanitized claim/APORIA sediment. It persists source
  IDs/hashes and payload hashes, never extracted private source text.
- `f09a_preview_ledger.json`: per-item paths, fingerprints, source revisions,
  replayed/invalidated item lists, and zero duplicate model calls.
- `f09a_hosts/sechenovka-like` and `f09a_hosts/meteorology`: the existing real
  F09A serial batch implementation, with manifest, SQLite ledger, receipts,
  per-item paths, and idempotent resume. These are private operator volumes,
  not customer publication bundles.
- `WORKS_PARTIAL_MISSING.json`: concise engineering capability matrix.

R03 is the map of the selected research field/corpus. It is not re-labelled as
a two-paper I11 comparison. R05 contains seven separate external-entity dossier
slots. When external SRC-D or internal SRC-C is absent, R05/R06/R09 say so and
do not claim global novelty, deployed practice, institutional capacity, or an
authorized decision.

All outputs remain `SELF_OBSERVED_UNATTESTED`: scientific acceptance and
customer release stay human-only.

Current exact M13 limitation: the exported M5/M6 activation witnesses are real
engine records from the approved synthetic two-world fixture, but the selected
owner files are not yet causally bound into those activations. The receipt says
`PARTIAL_SYNTHETIC_ENGINE_DEMONSTRATION`; it does not splice the two traces into
a fake source-bound route. The product still provides the full typed operation
plan and immutable historical-method pins needed for that next adapter.

When a valid study analysis is supplied, M17 replaces that limitation for the
selected study with a source-bound route: a study-evidence thread and, where
contradictions exist, a distinct APORIA thread execute against loaded carrier
content. Identical source+oracle pins replay without a model call or report
version change. A contradiction change invalidates only report views whose
selector contains its source claims; A-only cannot inherit a D-only claim.
