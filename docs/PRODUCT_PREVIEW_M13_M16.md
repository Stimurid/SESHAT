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

## Outputs

- `product.json` and `index.html`: structured and browsable portfolio.
- `reports/R01..R09.{json,md,html}`: nine distinct report purposes.
- `carpet/`: actual M5/M6 `WaveEngine` artifacts, including events, waves,
  activations, sediment, two host contexts, and delta/selective-replay oracles.
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

Current M13 owner-source Carpet route: selected readable local PDF/TXT sources
are now loaded as versioned, content-hashed text-derived SourceCarriers through
FabricCarrierStore and ACTUALLY fire the shared WaveEngine. Per-source reading
threads feed separate historical I11 candidate-index threads and a corpus-field
summary. The native activations/events/sediment and source Carpet HTML live in
owner_source_carpet/owner-source-baseline/; source identity and raw PDF SHA are
preserved separately from freshly extracted text SHA. No old Opus job was rerun.

An owner-local counterfactual B revision is run through SOURCE_DELTA on a
separate engine run; it leaves both original PDF files unchanged, selectively
refires the B reader/index and dependent corpus summary, and leaves A idle.
This is a REVISION TEST, not evidence that a published article was revised.

Historical I11 outputs are indexed, not re-executed as a new model call;
full I08/I09/I12/C09 native MethodBody execution remains PARTIAL. Existing
M5/M6 two-world demos are retained as separate synthetic engineering evidence;
they are no longer the sole source of activation witnesses. The functional
real-source path is a preview rather than customer/scientific acceptance.
