# F09A1 — real durable offline batch (serial MVP)

Status: **F09A1 engineering slice** on F08 base `d7f80b3`. Not F09B concurrency, not production deployment, not scientific acceptance.

## Scope

- Typed `BatchManifest`, `BatchItemStatus`, `BatchReceipt` in `src/seshat/batch.py`
- SQLite ledger (`batch_ledger.sqlite`), serial worker (`concurrency=1`)
- F07 `HostRuntime` + F08 `report_session` / `artifacts()` only — no invented report dicts
- Synthetic hosts via `report_demo.install_fixture` (`sechenovka-like`, `meteorology`)
- CLI: `python -m seshat.batch_demo --fixture HOST --output NEW_DIR [--resume]`

## Owner-private batch state — NEVER copy this whole directory to a customer

The local batch root is an **internal, access-controlled operator volume**,
not a customer deliverable. Its `manifest.json` intentionally contains
private whole-source, rights and temporal SHA pins (`source_pins`) needed
for resume; `batch_ledger.sqlite` also contains internal operational state.
Comparing such pins across private runs may reveal hidden changes, so the
directory and its receipts MUST NOT be published wholesale.

Customers receive only a separately rights-reviewed **human-readable report**
(`report.md` and/or `report.html`) after the required science-owner decision.
For a fully synthetic public demonstration, copy only the selected report
file(s) into a **distinct** preview directory with UNREVIEWED banners.
Do not copy the batch root, manifest, ledger, JSON or raw carrier files.

### Private operator artifacts per batch directory

| File | Role |
|------|------|
| `manifest.json` | Frozen manifest fingerprint input |
| `batch_ledger.sqlite` | Durable item states and content hashes |
| `index.json` | Safe item index (no secrets) |
| `batch_receipt.json` | `code_pass` vs `scientific_accepted=NEVER_AUTO_SET` |
| `items/<item_id>/report.{json,html}` + `receipt.json` | Real F08 three-file bundles |

## State machine (item)

`QUEUED` → `RUNNING` → terminal: `DONE_METADATA`, `PARTIAL_METADATA`, `BLOCKED_METHOD`, `BLOCKED_EXTERNAL`, `FAILED_*`, `CANCELLED`, `STALE`.

Ledger marks **done only after** all three artifact hashes are verified and written. Crash between file write and ledger update leaves `FAILED_RETRYABLE` or incomplete checkpoint — resume recomposes or regenerates.

## Report families in demo manifest

| Item | Report | Ledger / F08 status |
|------|--------|---------------------|
| `r03-corpus` | R03 | `DONE_METADATA` / substantive metadata |
| `r02-method-graph` | R02 | `PARTIAL_METADATA` / `BLOCKED_METHOD` |
| `r05-external-blocked` | R05 | `BLOCKED_EXTERNAL` |
| `r01-individual` | R01 | `PARTIAL_METADATA` |

R06–R09 remain available through F08 but are not in the default demo queue.

## Security notes

- No customer source paths, env secrets, or MethodBody bytes in ledger or receipts
- `batch_receipt.json` / `index.json` expose only public selection snapshot digests and item projection metadata — never owner `rights_sha256`, temporal pins, or manifest `source_pins`
- `assert_safe_path` rejects lexical `..`, symlink/reparse ancestors before `resolve()` (Unix symlink test in CI)
- Ledger identity is checked before any `manifest.json` write; manifest conflict raises with no durable mutation
- Same `batch_id` with different manifest fingerprint → `BatchManifestConflict`
- Denied-only host mutations must not change public report bytes, batch receipt, index, or attempt counts (see `tests/test_batch.py`)
- No-op resume keeps `batch_receipt.json` byte-identical when visible inputs are unchanged

## Follow-up (not in F09A1)

- **F09B**: multi-worker leases, quotas
- **F09C**: authorized remote executor / customer UI
