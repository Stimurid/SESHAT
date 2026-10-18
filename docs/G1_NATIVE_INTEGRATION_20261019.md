# G1 native integration — worker jx-282def3d2613

Status: IMPLEMENTED_UNTESTED; LIVE_BLOCKED_HOST_ATTESTATION_INTERFACE.
This is an engineering increment, not G1/G2 acceptance or proof of real E5.

## Source and execution receipt

- WORKSPACE_MODE: isolated Hub worktree, explicitly assigned by owner.
- WORKDIR_ABSOLUTE: C:\AI\llm\aiye-executor\worktrees\jx-282def3d2613
- ORIGIN_URL: https://github.com/Stimurid/SESHAT.git
- CURRENT_BRANCH: aiye/exec-282def3d2613
- BASE_SHA / initial HEAD: d944e3917c0df6fceb36499d99a1fd11e59a1dd2
- BASE_TREE: 3c711ac769c8fab9e91ad1a2efc9f46cda19fc6f
- Initial DIRTY_STATUS: clean. Canonical local main observed at cad04bde48434d76c2fdd1825621052c64c8db3c.
- CURRENT_TASK: SESHAT-G1-OFFICIAL-HUB-BRIDGE-20261018, issues #60/#6.
- CURRENT_PR: none created. NEXT_GATE: Hub snapshot, independent locked Linux QA, premium review.
- CHILD_SHA / CHILD_TREE: assigned by Hub after worker exits; not fabricated here.
- No git add/commit/push, merge, deploy, paid submit, model CLI, protected source,
  secret access, host configuration changes, or external publication performed.
- Executed: PowerShell source reads/edits, Git read-only inventory/diff/status,
  connector reads of the goal document and Inbox #6/comments, source hashing.
  `git diff --check` passed. No Python/pytest/Ruff/Docker executed.
  Python at the machine pointer path and python/py/aiye-exec on PATH were unavailable
  in this sandbox. Running unreviewed code on credentialed Windows is also prohibited
  by the project and owner plan. Existing 577/74/9-of-9 evidence is predecessor evidence,
  not a test result for these changes.
- DRIVE_SYNC: MIRROR_PENDING; no write/readback claimed.

The one-time pre-edit queue inventory found this job as the only SESHAT code writer.
Other RUNNING jobs: jx-36c5646a04d7 and jx-dcf276ee516b (aorus-ecosystem code),
jx-dae9a7b93387 (aorus-ecosystem audit). QUEUED: jx-4415eb5f8edd and
jx-70640cdd67ba (aorus-ecosystem audit), jx-5ff52f327413 (SESHAT audit).
These are observed status files, not an assertion about later process liveness.
No recurring polling was installed or performed.

Read: repo AGENTS/Charter/coordination/implementation plan; machine AGENTS;
ARCHIVARIUS portable entry and routing instructions; full reviewer stdout;
CALLER_PROTOCOL and relevant original executor parser/admission/receipt source;
Drive plan 1bT8EMjqxATvs9VpxtweotqJ8sKeLUJWw40WTd-SaQ4w
(modified 2026-10-18T20:31:10.165Z); GitHub #6 and current comments.
Proteus/routing Python invocation failed because the documented interpreter was
unavailable: no runtime/mount claim inferred from identity or the handoff locator.

Read source SHA-256:

- Reviewer jx-02fc63a9e0ee stdout.log:
  11efe77d92a11702e5788feacfb2fd9c0df293f953c969fb3522c6f80cf8338c
- CALLER_PROTOCOL.md:
  9dc899e161cb0d990639d6e0f15351d0b487e378a62d4923e3d9c3d28c0071c1
- Official executor.py:
  759992538728d3f54c04ed9dbae5dd8113bd2afecb2b5f2c0c8fbc2e45ea19ad

## Changes and review intake

Reviewer B1/B2/B3/B4: ACK_NEEDED_NOW / VERIFY_WITH_TEST, owned by #60.
The old standalone bridge receipt is historical and superseded by this receipt.

Production dispatch now accepts only the integrated NativeHubBridge, and rejects
raw NativeAiyeExecSubmitter, legacy AiyeExecSubmitter and arbitrary duck-typed callers.
Existing synthetic dispatcher tests explicitly opt into synthetic_only; the CLI
does not expose that switch. A trusted Python host bootstrap may inject a bridge
factory into host_cli.run; configuration/environment cannot load arbitrary code.

Native transport consumes a second durable launch claim under BEGIN IMMEDIATE,
requiring a keyed store and a prior dispatcher claim. New instances/restarts cannot
resubmit after nonzero, timeout, OSError, crash, or missing response. Prompt bytes
must match the original spec and pass environment-echo scanning before writing.
The host-pinned Python executable and official executor.py are hashed before launch,
then invoked as argv with shell=False, -E and -s; no .cmd or shell interpolation.
The old exe field is an argv-builder compatibility sentinel, not the executed binary.

CLI job_id must be exactly jx- plus 12 lowercase hex digits; job_path is ignored.
The ID is only a locator. Independent admission verification precedes an immutable
NATIVE_BOUND row; original request/spec bytes are never rewritten. Native job IDs
cannot be bound to two originals. Ghost recovery reads an independently issued
admission certificate for the existing host claim, without sending any new job.

Native-bound ingest, evidence verification and export re-read signed admission and
terminal certificates plus exact spec/status/receipt/stdout originals. Normalized
spool material cannot replace that chain, including during an unbound ghost state.
Existing E5 parsing, source rights, same-WAITING replay and downstream causal checks
remain in the original adapter/engine. No methodology or donor import changes.

## Missing host interface — explicit blocker, not fabricated provenance

The observed official Hub writes ordinary JSON originals. No independently authorized
immutable issuer-ledger/attestation publisher was established in this workspace.
This change implements its CONSUMER contract only. It contains NO production signer,
key provisioning, ACL installation or automatic trust in a rehashed spool.

Before live use a separately reviewed, independently authorized host component must:

1. Provision protected jobs_root/ledger_root, separate host-held attestation and
   normalized-record keys, a keyed SESHAT store, host/provider/model policy and exact
   Python/executor/dependency installation provenance. Never provide keys to workers.
2. Issue `<host_job_id>.launch.json` only after real human authorization and independent
   exact-source review. Envelope is `{body, mac}`; MAC covers material_hash(body).
   Body schema `seshat.native_hub.launch.v1`, host_job_id, original_spec_sha256,
   hub_instance_id, authorization_sha256, python_sha256, executor_sha256, client,
   project_target and decision_id must match. File contents alone cannot grant the
   publisher authority; its protected identity and immutable history are prerequisites.
3. Independently observe actual Hub issuance, verify original prompt/spec and immutable
   enqueue provenance, and publish `admission` with the same common fields, native_job_id,
   consumed nonce, issued_at and native_spec_sha256. No caller/model self-certification.
4. Publish `terminal` binding admission_sha256 and all four original byte hashes,
   usage_verified and a separately issuer-authenticated normalized record for the
   effective spec (original spec with only hub_job_id replaced by verified native ID).
   Native missing cost/token telemetry must NOT be interpreted as zero. Publisher
   must independently enforce/verify budget and issuance lineage.

The current auto-router must select the independently pinned provider/model or admission
fails closed; this increment does not silently revise the approved policy after dispatch.
Original files changed after attestation fail closed and require host investigation.
No automatic NOT_SENT reset exists. Missing certificates mean blocked/pending, never
an authorized paid retry. The default CLI remains blocked without the trusted bootstrap.

## Validation required on the Hub snapshot

New `tests/fabric_waves/test_native_hub_integration.py` uses a public synthetic signing
fixture and an injected runner; no real host identity or execution is claimed. It covers
two-host WAITING→verified-original→E5→same wave→two dependent threads; ghost recovery
and reopened-store retry denial; raw/unknown submitter denial; original/ledger tamper;
wrong host/spec/nonce, backdating, invalid IDs, unbound-spool injection, environment echo
and installation pin drift. Existing native tests now use durable keyed claims and
assert rejection of repeated ambiguous sends. Existing dispatcher tests explicitly
identify their synthetic execution mode; no prior negative assertions were removed.

Run in the authorized isolated Linux environment, not credentialed Windows:

```text
python -m pytest -q tests/fabric_waves/test_native_hub_bridge.py tests/fabric_waves/test_native_hub_integration.py tests/fabric_waves/test_phase_b_host_adapter.py tests/fabric_waves/test_phase_b_security_regressions.py
python -m pytest -q
ruff check .
```

Retain all predecessor external adversarial scripts and Fabric P1/two-host oracles.
This worker did not run them. No scientific, product or release acceptance follows
from these authored tests. Existing G2 requests rn:campus:bdda91e52f60 and
rn:met:94a4ace68a5b remain undispatched by this worker.

Rollback: revert this scoped snapshot in review; retain all host submission/binding
history. Never delete launch claims to permit a retry. No donor worktree was modified.

## OPEN QUESTIONS

1. Is a reviewed independent host attestation publisher already deployed? Default:
   UNKNOWN; no deployment assumed. Exact required interface is above.
2. Can the changed snapshot pass independent locked Linux QA and premium review?
   Default: UNVERIFIED; no inherited green result promoted to this child.
3. Are live provider/model/budget and the two original G2 requests authorized now?
   Default: NO live authorization in this task; no paid attempt made.
4. May the worker commit or publish? Default: Hub snapshots files after exit;
   no worker Git metadata writes and no external publication.
