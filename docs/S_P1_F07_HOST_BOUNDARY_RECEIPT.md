# F07 host boundary author receipt — 2026-10-15

Status: CODE_AUTHORED / ENGINEERING_REVIEW_PENDING. Not deployed or accepted.
Task: #56, bounded Hub job jx-a08fbc3306cf. CURRENT_PR=NONE.
BASE_SHA=7b96ca1fc51f8e9786792f7b6356740061465b0b
BASE_TREE=28936893d06daf2827b505080a3761373e05341d
WORKSPACE_MODE=HUB_WORKTREE
WORKDIR_ABSOLUTE=C:\AI\llm\aiye-executor\worktrees\jx-a08fbc3306cf
ORIGIN_URL=https://github.com/Stimurid/SESHAT.git
CURRENT_BRANCH=aiye/exec-a08fbc3306cf; initial DIRTY_STATUS=CLEAN.
The explicit Hub assignment supersedes the generic C:\projects\seshat location rule.
No Git metadata writes attempted. Hub owns the final author snapshot.

## Implemented boundary

`corpus.py` computes public selection identity itself. No call to an untrusted
`seal_selection` or legacy manifest reader can confer authority, affect the
digest, or inject a hidden-population exception. Existing public API remains
PROVISIONAL / UNVERIFIED_CURRENTNESS. The digest domain changes to v3; old
selection digest references must be rebuilt, not silently treated as current.

`corpus_host.py` is a separate owner control plane. HostConfiguration contains
exact primary metadata and rights file SHA-256 pins plus expected host_id.
The runtime hashes the actual bytes it parses; it does not compare two request
assertions. Native SourcePackage contains host_id, manifest_id, version,
declared_fields and records in StudyRecord JSON shape. Every visible field is
derived from the pinned record value and rebound to a stable host/object/field
token. The token proves neither a fact in the original PDF nor publication rights.
The full-file pin binds all record fields, identity and carriers privately.

RightsPackage contains host_id, a nonempty private epoch and unique
caller_id/view_id grants with explicit object_ids AND carrier_ids. Default deny;
no metadata flags grant access. No-count projection is mandatory for this route.
An owner calls install() to change independently approved pins atomically.
Each select rechecks both files; full source SHA, rights SHA and policy epoch
invalidate the private cache, including hidden-only updates. Public projections
contain no full-population epoch/hash or rebuild counter. Hidden invalid field
payloads are not semantically validated before admission. Invalid visible
records return a constant error. Invalid package envelope, unreadable file or
unapproved byte changes fail closed as HOST_INPUT_UNAVAILABLE; the runtime
does not mask loss of its trusted source/policy as a successful empty result.

Trust is the external owner process/OS boundary, NOT the Python class name.
The owner must provision immutable read-only files and approved hashes outside
request scope, authenticate sessions, and expose ONLY the returned select
callable through its transport. session() and install() are privileged APIs;
never expose them as caller RPCs. No arbitrary untrusted Python may run inside
this process. This patch does not install an authenticated server, ACLs or a
production service, and does not claim such a deployment exists. File pins
alone cannot establish who approved them. Owner pin provenance is a deployment
precondition, not a property callers can self-assert.

The module also implements an actual JSON-line worker entry point:
`python -m seshat.corpus_host --config /private/host.json --config-sha256 APPROVED_SHA --host-id HOST --caller-id AUTHENTICATED_CALLER --view-id AUTHORIZED_VIEW`.
The owner controls process argv and mounts; the untrusted channel is stdin,
accepting CorpusSelectionSpec JSON only. Additional configuration/policy/seal
fields are rejected. stdout returns only a public snapshot or constant
SELECTION_UNAVAILABLE error. The launcher authenticates the pipe/session; it
must never forward request-controlled argv. Bootstrap errors are constant and
terminate with exit 2. This entry point is authored, NOT launched in this job.
Owner rotations use the separate install control plane or restart the worker
with new independently approved pins; requests cannot rotate policy.

PackageAttestation is an OWNER-ONLY diagnostic:
SOURCE_PACKAGE_INTEGRITY_VERIFIED, original_source_fact_state=NOT_VERIFIED,
raw_access_state=NOT_READ, semantic_acceptance_state=NOT_ASSERTED. It is never
merged into the public projection. Public require_current remains blocked;
the host runtime checks current private inputs before serving/rebuilding its
cache. No EVIDENCE_VERIFIED or FULL_REQUIRED admission is added.

`corpus_report_input.py` binds all R01–R09 input IDs to the exact named/versioned
selection and internally consistent snapshot. It labels them SRC-B metadata
inputs, not sufficient report evidence. It implements neither report prose nor
external/internal source layers, scientific analysis or acceptance.

## Owner-only real v4 evaluation

REAL_V4_RUN=BLOCKED_SOURCE_ACCESS. No real rows were ingested by this job.
`corpus_private_cli.py` is an executable metadata-only CLI for an independently
authorized offline runner AFTER review. All data/config files stay outside the
checkout, mounted read-only; no credentials, network, PDFs or MethodBodies.

Example invocation (not executed):

```text
python -m seshat.corpus_private_cli --config /private/run.json --config-sha256 OWNER_APPROVED_SHA256 --host-id OWNER_HOST
```

OwnerEvaluationConfiguration JSON has host_id, caller_id, view_id and four
FilePin objects master/intake/contract/rights, each {path:absolute,sha256:exact}.
The independently approved configuration SHA is the launch trust root. The
contract is PrivateV4Contract: primary MASTER JSON pointer bindings for every
carrier (ID, SHA, year, specialty, source card), intake source-card pointer,
four aggregate expectations and fourteen PrivateSelectorOracle entries with
exact original predicate objects, member lists, query, counts and digest.
This private mapping must be reviewed by the source owner; it is not fabricated
from published counts. Existing compare_real_v4_metadata requires the exact
published MASTER/INTAKE pins, population pin and all 14 membership oracles.
The CLI binds the comparison to host-matching pinned rights and rechecks policy
and configuration bytes before issuing a terminal result. There is no public
callback/policy parameter. Missing mount returns BLOCKED_SOURCE_ACCESS;
invalid pins/host/rights/oracles return BLOCKED_OR_MISMATCH, exit 2.
Only an actual successful 14-oracle execution can emit REAL_V4_PASS, exit 0.
Even then four identity QA flags remain pending and source facts/science are
unverified. Synthetic fixtures cannot satisfy the hardcoded real source pins.

## Evidence and validation

Read Git #56, #6 and their comments via connector, full goal/handoff documents
retrieved via Drive connector (relevant corpus/source-regime and final oracle
sections inspected), local project rules/charter/coordination/plan, machine and
portable routing instructions, and the independent baseline test receipt.
The source task's stale cad04b handoff observation was superseded by actual Git.
The independent previous receipt names exact BASE_SHA/TREE above and image
sha256:042c3cdd5580db77f9d670f631ab14238cd53c4ce069cc87f2a07258a4b4789a:
119 passed, one Pydantic serialization warning. This is baseline evidence only,
not a test result for these changes. Existing tests were not removed or weakened.

Executed here: read-only Git inspection; PowerShell file reads; connector reads;
patch writes; git diff --check. NO project Python, pytest, Ruff, Docker, direct
agent CLI, privileged publisher, push, PR, merge, deployment or service changes.
No private data added. No claim of Drive synchronization. DRIVE_SYNC=MIRROR_PENDING.

Authored tests: malicious seal (exception/hidden digest/invalid return), exact
owner file tampering with self-consistent request hash, host/session spoofing,
hidden additions/deletions/reorder/mutation and invalid metadata, whole public
output/error equality, source-only and rights-only epoch rebuild counts,
grant/revoke, per-field binding, independent meteorology schema, nine matching
report inputs, four pending QA flags, missing private mount and rejection of
coherently pinned synthetic data by the real-v4 CLI. Existing coherent forged
reader and private master-join negative tests remain in place.

NEXT_GATE: independent reviewer, then isolated exact Hub-snapshot execution of
`python -m pytest -q -o pythonpath=src` and `ruff check .`, using the established
noncredentialed/read-only/no-network constraints. Preserve all prior 119 tests;
new tests increase the suite. No new PASS count asserted before that execution.
BLOCKERS: private safe mount and original oracle/mapping artifact unavailable;
host deployment/bootstrap authority not installed; current-tree tests pending.
Prior reviewer findings are VERIFY_WITH_TEST for #56; unrelated donor
methodology imports are NOT_APPLICABLE to this patch. Human acceptance remains
independent of all engineering results.

Changed files: corpus.py, corpus_evaluation.py, new corpus_host.py,
corpus_private_cli.py, corpus_report_input.py, tests/test_corpus_host.py, this
receipt and the supersession pointer in S_P1_F07_RESULT.md. Rollback: revert
this job's scoped snapshot in a reviewed branch; never reset canonical main.

## OPEN QUESTIONS

- Which deployment authenticates sessions and independently approves host pins?
  Default: none installed here; owner-only bootstrap contract authored, not live.
- Where are private v4 metadata and the exact original oracle/pointer contract?
  Default: not mounted in an authorized safe runner; BLOCKED_SOURCE_ACCESS.
- Did all prior 119 and the added tests pass on this snapshot?
  Default: unknown until independent isolated execution; baseline PASS preserved
  as evidence only, no inferred current PASS.
- Who clears four identity flags and accepts scientific/report claims?
  Default: source owner/human only; all four pending, no scientific acceptance.
