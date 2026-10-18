# Report-first synthetic vertical (working-tree delivery)

The owner supplies a versioned `ScientificReportAsset`, source bytes, and
method-body bytes
separately from the client's `ReportRequest`. Its claims include source carrier,
version, SHA-256, page, stage (E1–E5), and distinct functional subassembly. The
composer compares each pin with the authorized selected member, verifies the
source and method bytes against their SHA-256, and renders the supplied words in Russian.
It does not run a scientific method, inspect external literature, or sign a
science-owner decision. The synthetic fixture ships invented pages 1 and 2 and
an independently authored analytic state.

`--scientific` produces `report.md`, static `report.html`, `report.json`, and
`receipt.json` for R01; absent or mismatched method version leaves R01
`BLOCKED_METHOD` and no Markdown report. R03 counts studies and carriers in the
authorized selected union. R05–R09 remain blocked at their typed boundaries.

## No-network, unprivileged smoke (Docker daemon required)

Build in an isolated, noncredentialed CI runner before the no-network execution:

```sh
docker build -f Dockerfile.report -t seshat-report:local .
docker create --name seshat-report-smoke --network none --user 65532:65532 seshat-report:local
docker start -a seshat-report-smoke
docker cp seshat-report-smoke:/tmp/report ./synthetic-report
docker rm seshat-report-smoke
```

Run the exact snapshot's tests without network or root privileges:

```sh
docker run --rm --network none --user 65532:65532 --read-only --tmpfs /tmp:rw,nosuid,nodev seshat-report:local python -m pytest -q
```

Inspect `synthetic-report/report.md` first. Its two meteorology subassemblies
have distinct methods and source anchors. This is an invented example, not a
claim about a real researcher's activity.

For a serial batch:

```sh
docker create --name seshat-batch-smoke --network none --user 65532:65532 seshat-report:local python -m seshat.batch_demo --fixture meteorology --scientific --output /tmp/batch
docker start -a seshat-batch-smoke
# Preview only. The complete batch directory is PRIVATE operator state.
docker cp seshat-batch-smoke:/tmp/batch/items/r01-readable/report.md ./synthetic-preview-r01.md
docker cp seshat-batch-smoke:/tmp/batch/items/r01-readable/report.html ./synthetic-preview-r01.html
docker rm seshat-batch-smoke
```

Inspect `synthetic-preview-r01.md` and `synthetic-preview-r01.html` only.
The full batch directory, including `manifest.json`, `batch_ledger.sqlite`,
and private whole-source/rights/temporal digests, remains within an owner-
controlled volume and is NEVER copied as a public artifact. On resume the
manifest identity and scientific asset digests are pinned; live source rights
and source contents are rechecked, and changed visible state is recomposed.
The source-pins are not required to remain byte-identical on resume.
The `batch.py` API exposes `resume_batch` for this private volume.
Never put private source or method bodies in a public container image.

The content hash is checked against owner-provided bytes. For non-synthetic
sources, page coordinates remain an owner assertion at this interface. Before
any real case, an authorized operator must verify original page coordinates,
method body, content rights and currentness, then admit the separately reviewed
analytic state. Scientific acceptance and public release are separate human
decisions.
