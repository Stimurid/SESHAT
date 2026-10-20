# Phase B — trusted AORUS Hub host adapter (S-RUG-CORE-003)

Status: code + tests authored in an isolated worktree. **Not executed.** No Hub call, no model
call, no pytest run and no credential use happened while authoring. Test execution belongs to the
coordinator's immutable, non-root, network-none, read-only Docker run on the child SHA/tree.
Engineering acceptance, live dispatch and any scientific-method approval remain human decisions.

Task source: [issue #60](https://github.com/Stimurid/SESHAT/issues/60). Base:
`1a26d11189713f66bbcb850341130e31eab78de1` (tree `06974c16de4662c75ae40b82f5b4b60a74cffffe`).

## Trust boundary

```
 UNPRIVILEGED CORE (unchanged)          HOST-ONLY (new, this change)
 engine / contracts / port / ledger  -> ExecutorPort -> TrustedHubHostAdapter
 hosts / fake_host(TEST ONLY)                              |
                                          HostJobStore (SQLite WAL, immutable rows)
                                          HubIssuerRegistry (independent issuer pins [+HMAC])
                                          build_outbound / parse_model_output (strict envelope)
                                          HostDispatcher (dry run default) -> aiye-exec (official)
```

* The core never imports a host module, `subprocess`, `sqlite3`, network libraries or reads
  `os.environ` (enforced by an AST test). `FakeHostExecutor` is test-only and is not used by any
  Phase B code or artifact.
* `compute_host_binding_hash` is an **unkeyed SHA-256 correlation value, not authentication**.
  Authentication here means: host registry pins (issuer id, Hub instance id, provider/model
  allow-list) + the host's own persisted original job spec digest + stdout hash/bytes + the
  first-writer terminal row, and, only if the host configures a private key, an HMAC over the Hub
  record. Without a key the receipt says `issuer_auth: REGISTRY_PINS_ONLY`. It never claims more.

## Modules (`src/seshat/fabric_waves/external_carrier/`)

| module | role |
| --- | --- |
| `host_security.py` | limits (absolute token/time/cost ceilings, clamped), secret/path/protected-marker/control/env scanners, safe path reader (no `..`, no symlinks, regular file, size cap, fd re-check), atomic fsync write, redacted `HostIntegrityKey` |
| `hub_protocol.py` | normalized `HubJobSpec` / `HubJobRecord`, `HubIssuerRegistry.verify_record`, typed `HubTransportError` |
| `host_envelope.py` | outbound gate (E5-only, DRILLBACK-only, two allow-listed public synthetic carriers, versions + content current, bounded excerpts, budgets clamped) and the untrusted-answer parser (closed schema `external.hypothesis.v1`, authority-spoof keys/text rejected, lone surrogates rejected) |
| `host_store.py` | `HostJobStore`: ORIGINAL canonical request bytes, pins, owner origin, Hub spec, prompt, source digests, replay material; immutable rows (triggers); row digests (+ optional HMAC); first-writer terminal CAS; atomic `begin_submission` |
| `host_adapter.py` | `TrustedHubHostAdapter` implements `ExecutorPort`; `prepare`/`preview`, `ingest_hub_result`, `build_evidence_return`, `verify_return`, `recheck_outbound` |
| `host_dispatcher.py` | hard-denied native `aiye-exec` argv/submission pending an authenticated ID bridge; `SpoolHubFetcher`, single-use live authorization, `HostDispatcher` |
| `phase_b.py` | `resume_live`, `resume_by_replay`, causal assertions, machine artifact export |
| `host_cli.py` | `seshat-fabric-external` (`write-origin`, `prepare`, `dispatch`, `ingest`, `resume`, `status`) |

## Resume modes (stated verbatim, never blurred)

* `PHASE_B_LIVE_IN_PROCESS_ONLY` — one in-memory `WaveEngine` stays alive while the host job runs;
  the return comes through the untrusted mailbox and is re-verified by the adapter. Single process,
  nothing persisted.
* `PHASE_B_REPLAY_VERIFIED` — restart-safe. The host persisted the original machine StoneEvent,
  budget and request bytes. A fresh engine replays that event with the same `run_id` and must
  regenerate a ResearchNeed with an identical **pin digest** (`request_pin_digest`: all dispatch
  pins + question text + budgets, excluding `created_at`/`status`/`provenance`) and identical source
  content digests, before anything is admitted. Engine state is **re-derived and compared**, not
  restored. `resume_receipt.json` says `NOT_RESTORED_DETERMINISTIC_REPLAY_COMPARED_TO_HOST_ORIGINALS`.
* `PHASE_B_REQUIRED` — no replay material persisted: the adapter refuses
  (`PHASE_B_REQUIRED_NO_REPLAY_MATERIAL`).

`phase_b.causal_facts` fails closed unless exactly the two dependent threads
(`external-integrate-*`, `reconcile-*`) newly FIRED, the return event is parented on the real
WAITING activation, the proposal is E5, all observation branches are version-stable and a resonance
traces the waiting activation. Both `campus` and `meteorology` use the same engine architecture.

## Safety properties implemented

* Owner-approved origin: a host-held approval keyed by the request pin digest is required
  (`ORIGIN_NOT_APPROVED`). Approval cannot widen the outbound gate.
* Idempotent persistence: job id derives from the pin digest; a deterministic replay (different
  `created_at`) maps to the same job; conflicting pins raise `HOST_REQUEST_ID_CONFLICT`.
* Terminal CAS across processes: `BEGIN IMMEDIATE` + primary key; identical re-record is
  idempotent, a different one raises `TERMINAL_RESULT_ALREADY_ISSUED`. Failed/cancelled/timeout
  and host-rejected model output are typed terminals and never become evidence.
* Dispatch: dry run is the default. Native submission is hard denied with
  `PROTOCOL_UNVERIFIED`, regardless of environment variables or JSON switches. It records no
  attempted send and does not call the runner. Synthetic test submitters still exercise the
  single-use authorization and atomic submission claim. After any synthetic transport error
  whose delivery cannot be disproved, the attempt stays `SUBMIT_AMBIGUOUS` and cannot retry.
* Store integrity: once a host-private HMAC key is used, `meta.integrity_key_required=true` is set
  and unkeyed opens or reads of MAC'd rows raise `HOST_STORE_INTEGRITY_KEY_REQUIRED`.
* Artifact export: CLI `resume --execute` defaults `transport_kind` to `UNATTESTED_MANUAL_IMPORT`.
  `HUB_SPOOL_RECORD` is hard denied in both CLI and library exports. A locally minted ACK and
  normalized spool record cannot certify official Hub issuance.
* No native argv is generated. The dry-run manifest reports the protocol gap and `argv: null`.
  Absence of a Hub record is typed `WAITING` and produces no result.

## Machine artifacts (written by `export_phase_b_artifacts`, per-file SHA-256 in `receipt.json`)

`stones.json`, `events.jsonl`, `waves.jsonl`, `activations.jsonl`, `sediment.json`,
`resonances.json`, `carpet.html` (adds an external-provenance block: run, wave, request, host job,
Hub job, ticket, provider/model, issuer auth mode, stdout/result digests, producer, waiting
activation, return event, fired threads), `research_needs.jsonl`, `job_dispatch.jsonl`,
`independent_host_job_receipts.jsonl`, `terminal_output_sha.jsonl`, `evidence_returns.jsonl`,
`resume_receipt.json`, then `receipt.json` (digests, host-module digests, git meta, claims,
known limits, caller-supplied `transport_kind` such as `MOCK_HUB_TEST_ONLY`).

## Coordinator run (not executed here)

```
docker run --rm --network none --read-only --user 65532:65532 --tmpfs /tmp \
  -v <child-checkout>:/src:ro <pinned-image> sh -c \
  "cp -r /src /tmp/w && cd /tmp/w && pip install -e .[dev] && python -m pytest -q && ruff check ."
```

New tests: `tests/fabric_waves/test_phase_b_host_adapter.py`, `test_phase_b_host_cli.py` (shared
mock in `phase_b_harness.py`). Pre-existing tests and the nine external exact-tree groups are not
modified. Note: pre-existing `F401` in `hosts.py`/`ledger.py` is not touched by this change.

## Known limits (honest)

* **Hub protocol unverified.** AORUS `CALLER_PROTOCOL.md` was read for the G1 repair. It confirms
  that native Hub submission assigns a new `jx-...` ID; the current normalized SESHAT spec
  presumes that ID before submission. The
  `aiye-exec submit` flag spelling, the exit-code mapping (`exit_code_map`) and the normalized
  record schema (`aiye.hub.job_record.normalized.v1`, produced by a Hub-to-spool bridge that does not
  exist yet) are **placeholders pinned in one place** and flagged `UNVERIFIED_AGAINST_CALLER_PROTOCOL`
  in every dispatch manifest. Native submission stays blocked until a trusted bridge binds the
  exact original request and real Hub-issued ID to an independently authenticated terminal.
* **Legacy SQLite:** the original two-column `meta(k,v)` table was not sealed. Opening it now
  raises `HOST_STORE_LEGACY_MIGRATION_REQUIRED` before DDL or journal-mode changes, preserving
  original jobs, submission attempts and terminals. An authorized, independently audited
  forward migration is still required. Keyed metadata is MAC-checked on open; missing key
  metadata with existing rows refuses an implicit integrity upgrade.
* Config, approvals and live-authorization documents are plain JSON in the host directory; only
  store rows and Hub records can be MAC'd. Directory ACLs are the control.
* SQLite digests detect edits, not whole-row deletion by an attacker who can also drop triggers.
* A terminal is immutable: a FAILED/TIMEOUT/OUTPUT_REJECTED request cannot be retried; it needs a
  new, separately approved ResearchNeed.
* The engine's own ledger compares only 14 dispatch pins; `resume_live` additionally binds question
  text/budgets/priority (`LEDGER_NEED_PIN_DRIFT`). Do not set `engine.executor_port` to this adapter:
  approval is keyed on the pin that exists only after the run, so use `prepare` after the wait.
* Hypothesis text containing standalone `E1`-`E4` or `ACCEPTED` is rejected (conservative).
* The origin stone for the two machine ResearchNeeds (`rn:campus:bdda91e52f60`,
  `rn:met:94a4ace68a5b`) was not readable; supply it via `write-origin` or an origin manifest and the
  pin digest must reproduce, otherwise `REPLAY_REQUEST_DRIFT` is raised (no silent substitution).
