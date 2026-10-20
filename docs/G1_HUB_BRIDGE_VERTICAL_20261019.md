# G1 Hub issuer bridge vertical — 2026-10-19

## Exact workspace and scope

- Worktree: `C:\AI\llm\aiye-executor\worktrees\jx-3cf03ace8f21`
- Origin (from `AGENTS.md`): `https://github.com/Stimurid/SESHAT.git`
- Branch: `aiye/exec-3cf03ace8f21`
- Pinned parent (verified): `9a0bf49b46c870fb232b49c4b984c8eba8b6eb99`, tree
  `4e1f5de8c543711d5342b8ed97e38dba474ea60d` — both matched the task passport exactly
  before any edit in this session.
- Predecessor receipt: [G1_PHASE_B_REPAIR_RECEIPT_20261018.md](G1_PHASE_B_REPAIR_RECEIPT_20261018.md)
  (author jx-d421712c0ec8, reviewed by jx-2d990027d60d). This session continues from
  its "Remaining P0 barriers" list, specifically barrier 1 (distinguish the
  deterministic host id from the Hub-issued `jx-...` id and build a real, reviewable
  caller) and the one Docker-reported test failure.

## What this session changed

### 1. Fixed the one Docker-reported test failure (root cause: test harness, not product code)

`test_rehashed_metadata_poison_and_deleted_key_marker_refused` (in
`tests/fabric_waves/test_phase_b_security_regressions.py`) calls
`make_harness(tmp_path, mac=True)` expecting the store's `meta.integrity_key_required`
row to exist so it can tamper with it. Tracing `HostJobStore.__init__` and
`make_adapter()` in `tests/fabric_waves/phase_b_harness.py` shows `make_adapter` passed
the MAC key into the `HubIssuerRegistry` (so `HubJobRecord.issuer_mac` verification was
exercised) but **never passed `integrity_key=` into the `HostJobStore` constructor**,
so the store was always created unkeyed and the `integrity_key_required` meta row was
never written. The first `SELECT ... WHERE k='integrity_key_required'` in the test
returned `None`, and the test failed on `.fetchone()[0]` before it ever reached the
assertion under test — exactly matching the Docker receipt's note ("fixture never
creates keyed marker"). Fix: `make_adapter` now also builds the `HostJobStore` with
`integrity_key=HostIntegrityKey(MAC_KEY_BYTES) if mac else None`. This only changes
behavior for the two existing `mac=True` call sites (this test and
`test_hmac_issuer_receipts_forged_mac_rejected_and_key_never_printed`, which does not
depend on the store being unkeyed); no other test passes `mac=True`.

**Not independently re-run**: this session's "no SESHAT project Python on credentialed
Windows from authoring job" constraint means `pytest` was not executed here (the Bash
tool also required an approval this unattended run could not grant). The fix was
verified by manual trace of `HostJobStore.__init__`'s meta-row branches against the
exact bytes the test forges, reproduced step by step in this receipt's companion
reasoning; it needs confirmation by the next isolated Docker QA pass.

### 2. New, NOT-WIRED-IN outbound Hub bridge: `src/seshat/fabric_waves/external_carrier/native_hub_bridge.py`

This is the "host-only trusted official Hub caller" vertical (G1 requirement 2) as a
standalone module, plus `tests/fabric_waves/test_native_hub_bridge.py` exercising it in
isolation. It is **not imported by `host_cli.py` or `host_dispatcher.HostDispatcher`**
and cannot be reached from any existing command or test. Two independent gates already
in the pinned parent commit continue to refuse all native dispatch exactly as before,
untouched by this session:

- `host_dispatcher.AiyeExecSubmitter.submit` unconditionally raises
  `HubTransportError("PROTOCOL_UNVERIFIED")`.
- `host_dispatcher.HostDispatcher.dispatch` refuses **any**
  `isinstance(submitter, AiyeExecSubmitter)` before calling `.submit` at all —
  independent of environment variables, config or constructor arguments
  (`test_live_dispatch_fails_closed_when_caller_protocol_unverified` pins this).

`native_hub_bridge.py` provides:

- `build_native_submit_argv(...)` — builds the exact `aiye-exec submit` argv the task
  passport specified: `--agent auto --kind reasoning --mode <audit|code> --role
  <analyze|classify> --ticket <t> [--decision-id <id>] --prompt-file <path>
  --max-seconds <n> --client <c> --project-target <p>`. `--agent`/`--kind` are fixed
  constants, never parameters, so no caller input can select a different agent or job
  kind. `--provider`, `--job-id`, `--budget-usd`, `--max-tokens`, `--timeout-seconds`
  and `--decision` are not parameters of the function and so cannot be emitted even by
  caller error. `--mode read-only` is refused (`NATIVE_ALLOWED_MODES = {"audit",
  "code"}`); the existing `HubJobSpec.mode` sentinel is never read or forwarded.
  Every value (role, ticket, client, project-target, decision-id) is run through
  `host_security.require_safe_token`; the prompt is written to its own file and never
  concatenated into argv, so prompt content cannot inject flags.
- `NativeAiyeExecSubmitter` — a real `subprocess`-based caller: `shell=False`,
  `stdin=subprocess.DEVNULL`, the exe path validated by the existing
  `host_dispatcher.validate_exe_path` (absolute, basename exactly
  `aiye-exec`/`aiye-exec.exe`), the prompt scanned with `host_security.scan_text`
  (secrets/paths/protected markers/control chars) **before** anything is written to
  disk or any subprocess is started. Outcome classification is deliberately
  conservative: a clean `exit 0` with a stdout JSON object containing a well-formed
  `job_id`/`jx_id` matching `^jx-[0-9a-f]{6,40}$` is the **only** success path
  (`last_result` gets set); a nonzero exit, a timeout, an `OSError`, or unparseable/
  malformed stdout all raise `HubTransportError` with an `*_AMBIGUOUS` code and leave
  `last_result` unset. None of these is ever read as proof the Hub did not admit the
  job ("ghost success" cannot be laundered into a safe retry here).
- The native `jx-...` id is captured as `NativeSubmitResult.native_job_id`, a value
  completely separate from `HubJobSpec.host_job_id` (deterministic, host-chosen) and
  from `HubJobSpec.hub_job_id` (the pre-invented synthetic/test-mode label the existing
  `SpoolHubFetcher`/`MockHub` path uses and that remains untouched). This is the
  "distinguish" half of barrier 1: the module simply never writes a Hub-issued id into
  the host's own frozen pre-submission spec.

### What was intentionally NOT done, and why

- **The flag contract was not independently re-confirmed.** The exact argv above comes
  directly from the task passport text (owner-supplied). This session could not read
  `C:\projects\aorus-ecosystem\services\aiye-local-executor\CALLER_PROTOCOL.md` — it is
  outside this worktree's permitted read scope, and the one attempt to read it in this
  session returned a permission-denied result with no human available to grant it
  (unattended run). A coordinator with independent access must diff the live
  `aiye-exec submit --help` output (or the doc) against `build_native_submit_argv`
  before anyone wires this module in. This mirrors exactly the predecessor receipt's
  own "Unverified inputs" section (`aiye-exec` was not on that session's PATH either).
- **The inbound/ingest half (`NativeHubFetcher`) was not built.** Reading a real
  `spec.json`/`status.json`/`receipt.json`/`stdout.log` under the host-owned authorized
  jobs root and mapping its fields onto `HubJobRecord` (so `HubIssuerRegistry.verify_
  record` can check it) requires knowing that file format. Guessing field names here
  would produce code that *looks* like a verified bridge while silently verifying the
  wrong things — strictly worse than leaving it undone. The recommended shape for
  whoever has verified access: add an optional `expected_job_id: str | None = None`
  parameter to `HubIssuerRegistry.verify_record` (defaulting to `spec.hub_job_id`,
  i.e. zero behavior change for every existing caller) and thread it from
  `HostDispatcher.ingest` by reading the native id out of the `SUBMIT_ACKED` submission
  detail row, rather than changing the frozen `HubJobSpec` schema.
- **Neither of the two existing live-dispatch gates was relaxed.** Doing so is the
  actual "arming" decision for a chargeable call, which this run's mandate reserves for
  a human after independent review (no live paid Hub during unreviewed coding; no
  bypassing permission checks). This session delivers reviewable, independently
  unit-tested code for the next reviewed step, not a flipped switch.
- **No code touches `HubJobSpec`, `hub_protocol.py`, `host_adapter.py`,
  `host_dispatcher.py`, or `host_cli.py`.** Zero risk to the 564-test baseline the
  predecessor Docker run reported (560/561 plus the 5 negative-suite tests this session
  addresses the 1 known failure in); `native_hub_bridge.py` and its test file are
  purely additive and unreachable from any existing path.

## Verification truth table

| Case | Status this session |
|---|---|
| Parent 9a0 full Docker matrix (564/565) | Not rerun (no Python execution on this credentialed host) |
| `test_rehashed_metadata_poison_and_deleted_key_marker_refused` | Root-caused to a test-harness gap, fixed, verified by manual trace only |
| `build_native_submit_argv` / `NativeAiyeExecSubmitter` | New, isolated unit tests added; not run; not reachable from `HostDispatcher`/`host_cli` |
| Native CALLER_PROTOCOL.md flag contract | Taken verbatim from the task passport; not independently re-read against the live CLI (permission denied in this sandboxed worktree) |
| Live dispatch gates (`AiyeExecSubmitter`, `HostDispatcher.dispatch` isinstance check) | Unchanged |
| Ingest/verification of a real native terminal (`spec.json`/`status.json`/`receipt.json`/`stdout.log`) | Not implemented; schema unknown without verified access |

## Remaining P0 barriers (updated from the 2026-10-18 receipt)

1. Independently confirm the `aiye-exec submit` flag contract against
   `CALLER_PROTOCOL.md`/live `--help`, then either wire `native_hub_bridge.py` in or
   correct it.
2. Build `NativeHubFetcher` (the inbound half) once the real `status.json`/
   `receipt.json`/`stdout.log` schema is verified, and thread an `expected_job_id`
   override through `HubIssuerRegistry.verify_record` / `HostDispatcher.ingest` as
   described above (additive, backward-compatible parameter).
3. Decide, with the human owner, when (if ever) to relax the two existing hard
   live-dispatch gates, and only after an independent source reviewer has read this
   session's diff.
4. Run the exact full matrix plus the new `test_native_hub_bridge.py` file in isolated
   Docker CI on this session's child SHA; confirm the harness fix actually turns the
   known failure green.

## Unverified inputs

Same web/PATH/CALLER_PROTOCOL.md access limitations as the predecessor receipt, plus:
this session could not execute `pytest`/`ruff` on this host at all (explicit task
constraint), so every claim above about test behavior is a manual trace against the
exact source read in this session, not an executed result. No live Hub job inventory,
no GitHub issue state, and no Drive goal-document content beyond the excerpt supplied
in the task passport were fetched.
