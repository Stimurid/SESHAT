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


## First actual G1 -> F07 -> F08 -> F09A synthetic execution bridge (2026-10-19)

The previously documented `--scientific` flag can still compose an **owner-supplied**
claim state. This does NOT establish that a MethodBody ran. A distinct runnable
production-seam demonstration now exists:

```sh
# Run only on a trusted owner-controlled machine, below an existing parent.
python -m seshat.fabric_waves.report_bridge_demo --output /tmp/seshat-g1-first-private
```

This CLI actually invokes one registered `fabric_waves` MethodBody via
`WaveEngine.run` against one rights-admitted, FULL_REQUIRED synthetic source.
It produces a hashed `SedimentRecord`, FIRED `ActivationRecord`, and verified
source read manifest in the G1 ledger. `report_bridge.project_fabric_r01_r02`
checks the in-process engine snapshot and ledger, source membership/version,
method registration, raw access policy, source bytes and page excerpts against
F07 before constructing a **FABRIC_GENERATED_UNREVIEWED** R01 analytic asset.
The F08 Markdown/HTML report is written as `report/report.md` and
`report/report.html`. The exact asset then flows through serial F09A into an
**owner-private** `owner-private-batch`, with a SQLite checkpoint and report
receipts. R03 is metadata-only, and R05 stays externally blocked.

This bridge is **not** a direct medical/publication MethodBody, external model
invocation, verified clinical inference, or an open-ended autonomous research
system. The synthetic MethodBody separates two explicit PAGE-tagged source
statements, not a human dissertation; it cannot infer scientific merit. Its
versioned callable is registered in the G1 registry; the separate readable
`method_definition` bytes are pinned in F08, but their SHA-256 is NOT a code
signature of the callable. The G1 registry tag hashes id/version/class,
NOT the executable callable; it is recorded only as a registry identity tag
in a private FabricReportBridgeReceipt marked `executable_method_attested=NO`.
Real documents are blocked until independent deployment/executable attestation is
available. Synthetic page verification additionally requires an explicit
trusted `locator_verifier=SYNTHETIC_PAGE_TAG_V1`. **Human scientific acceptance remains
NOT_ASSERTED**. Source locators for this fixture are flagged
`VERIFIED_IN_SYNTHETIC_SOURCE`; real PDF page locators are at most
`OWNER_ASSERTED` until a document-specific verifier checks them.

The current bridge is intentionally restricted to ONE F07-selected research
object, ONE content-verifiable UTF-8 carrier, FULL_REQUIRED source access,
R01/R02 and actual in-process trusted provenance. Unknown/missing/stale/denied
source, missing method activation, wrong user rights, invalid excerpts or
revoked bytes block generation; no E5 proposal may become E1 or ACCEPTED.
Broader corpora, binary PDF page mapping, historical MethodBody science
and valid external SRC-D belong to separate evidence-gated work.

`tests/fabric_waves/test_report_bridge.py` proves this causal route, F09A
serial resume and negative source/method/authorization cases. The separate
`tests/fabric_waves/test_report_bridge_demo.py` executes the actual demo.
The CLI now performs `resume_batch` itself and verifies a no-op restart.
The CI workflow
`.github/workflows/report-first-no-network.yml` exercises it with
`--network none`, an unprivileged user and a read-only image; the batch
manifest/database are private and MUST NOT be copied to the customer.
