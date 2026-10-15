# F07 P1 confidentiality and evidence-trust repair — 2026-10-15

Status: SOURCE_UNREVIEWED; TESTED=NO; REAL_V4_RUN=BLOCKED;
HOST_ATTESTATION=BLOCKED; AUTHORITATIVE_CURRENTNESS=BLOCKED;
SCIENCE_ACCEPTANCE=NO; RELEASE=NO. This replaces the prior receipt's incorrect
claim that a caller-supplied coherent reader can establish EVIDENCE_VERIFIED.
The previous receipt remains in Git history at the base below.

## Workspace and evidence

- WORKSPACE_MODE=HUB_ISOLATED_WORKTREE
- WORKDIR_ABSOLUTE=C:\AI\llm\aiye-executor\worktrees\jx-68147a3c6447
- ORIGIN_URL=https://github.com/Stimurid/SESHAT.git
- CURRENT_BRANCH=aiye/exec-68147a3c6447
- BASE_SHA=HEAD_SHA=d0b6e9585c3f0fa6a3afb87473452da3225dd90a
- BASE_TREE=e293c0826c8819865de7851858b869d4ed368691
- DIRTY_STATUS at entry=clean; final changes are working-tree files for Hub snapshot.
- CURRENT_TASK=[#56](https://github.com/Stimurid/SESHAT/issues/56), delegated F07 P1 architecture repair.
- CURRENT_PR=NONE; NEXT_GATE=Hub exact SHA/TREE, independent source review and isolated CI.
- BLOCKERS=authenticated host source/epoch integration absent; private real oracle artifact and source files absent; no local execution authorization.

The explicit job passport authorizes this assigned worktree instead of writing
C:\projects\seshat. The latter's root and canonical origin were verified read-only.
Canonical main, RUG/fabric_waves, services and protected MethodBodies were not edited.
No Git metadata mutation was attempted. Hub owns the later source snapshot;
there is no new commit/test/CI/PR evidence from this worker.

Read source: complete corpus.py, corpus_adapters.py, test_corpus_selection.py,
prior F07 receipt, project AGENTS/Charter/Plan/Coordination, machine AGENTS and
portable routing instructions; reviewer jx-ba8641d90e51 stdout and diagnostic log.
Reviewer stdout explicitly FAILs the base for self-certification, hidden-only
pin/version leakage and loss of private rights currentness. Some diagnostic-log
outputs were truncated by the tool; no claim of complete untruncated log review.
The routing Python/Proteus commands could not run: the documented Python314
executable is unavailable in this sandbox. No actor or live mount was inferred.

Read current issue #56 and #6 plus latest comments through connected GitHub:
[#56 return](https://github.com/Stimurid/SESHAT/issues/56#issuecomment-6191534466),
[#6 return](https://github.com/Stimurid/SESHAT/issues/6#issuecomment-6191538368).
The initial web fetch failed and gh is unavailable; the connector succeeded.
Read owner [v0.12](https://docs.google.com/document/d/1ECGHtbYj1Az5WqNbMttX78RMxTq43iS5ZAGA3MSww4k/edit)
and the [real oracle return](https://docs.google.com/document/d/16MupFPKofY9MNxjdNtWqzzm0N8XuQ9TR5ixmx1O0ToM/edit)
(modified 2026-10-15T12:02:45.005Z). The lead-sync mirror is older
(2026-10-14T22:30:12.963Z); current assignment and latest issue return govern this repair.
No external write or Drive synchronization was performed.

Intake disposition: reviewer P1s and real oracle return = VERIFY_WITH_TEST on
#56; donor imports and RUG/Witness findings = NOT_APPLICABLE to this bounded
change; scientific methods/QA acceptance = BLOCKED_ON_SEMANTIC_DECISION, never
inferred from metadata. No donor code or method body was imported.

## Two planes and deliberate trust fallback

The public function is a library projection over supplied metadata and policy.
It is NOT an authenticated server. Neither a Python protocol, a private
attribute, a constructor, a field reference nor a SHA proves source authority.
A service exposing private data must own its policy and source access outside
the request boundary; allowing remote users to replace `authority` is unsafe.

There is no evidenced independent host verifier in this checkout. The repair
therefore takes task P1-1 option (b): every selector result is METADATA_ONLY,
PROVISIONAL, PENDING_HOST_ATTESTATION and UNVERIFIED_CURRENTNESS. Carrier pins
remain PIN_ASSERTED_NOT_VERIFIED. EVIDENCE_VERIFIED and the verified carrier
state are removed from the result schema and all construction paths. Legacy
`trusted_manifest` and `require_verified` arguments are inert for migration:
no reader method is called, even for an honest coherent source. Callers MUST
inspect evidence_state; passing require_verified=True does not satisfy it.
There is no substitute error about a supposedly nonexistent hash.

The private plane retains the full request manifest pin, canonical request
and content checksum helpers for host-controlled diagnostics. Those data must
not be exported as a public receipt or used as a public cache key. The core
makes no authenticity/currentness claim for those assertions.

## Public noninterference contract (F07-2)

Fix the selector, visible records, public declared-field schema, caller/view,
entitlements and seal key. Insertion/deletion of denied rows, conflicting denied
duplicates, hidden source SHA/version mutation and full-manifest epoch/version
rotation must leave the serialized receipt, digest, status and error unchanged.
The tests compare whole JSON strings and exception type/text, with the SAME
request pin in both worlds. They also cover a denied carrier candidate whose
study ID collides with an admitted study.

`build_corpus_space` performs study/carrier visibility before copying,
validating, fingerprinting or deduplicating content. Denied rows contribute to
no visible input digest or denominator. Only admitted records can produce
content-integrity errors. Hidden candidate collisions are not visible conflicts.
Visible duplicate and shared-carrier pin conflicts still fail explicitly.
Studies count by distinct study ID; carriers count by distinct carrier ID.

The seal excludes the ENTIRE population pin, not just its SHA. Public
`manifest_digest` now identifies the declared public schema, NOT full-population
integrity. `input_digest` binds the visible record content. `snapshot_digest`
binds every public result field other than itself, including all statuses.
No policy epoch is queried, hashed or exposed in the public path. Count rights
grant only the exact unique denied-study count (excluding IDs already admitted),
never hidden IDs, global epoch or full-manifest digest. No-count output always
has denied_studies=null and suppressed_remainder=false.

The host's seal service must be deterministic over its supplied arguments and a
stable per-view secret, independent of source/policy epochs. Policy decisions
must come from one consistent immutable host policy view. Public schema must
be predeclared, not inferred from hidden rows. Host callback failure is a generic
entitlement error; this library cannot guarantee noninterference for a malicious
or inconsistent policy/seal callback, arbitrary executable Python objects,
concurrent mutation, timing, memory usage or a transport exposing tracebacks and
locals. The contract covers typed metadata, deterministic policy and serialized
projection/error. Server transport must export only the safe exception type/code,
not exception contexts or private validation diagnostics. No formal security
proof or executed negative-test evidence is claimed by this source-only pass.

## Currentness and cache migration

Task P1-3 explicitly permits disabling authoritative currentness when trusted
host support is missing. This repair takes that fallback. It does NOT implement
or claim a trusted private-epoch cache. A constant public digest can never
establish cache currentness. `require_current` now always raises the exported
UnverifiedCurrentnessError("UNVERIFIED_CURRENTNESS"), a StaleCorpusSpaceError
subclass, before reading any records, reader, rights or prior snapshot. This
refusal is identical for unchanged data, hidden-only rotation and visible drift.
There is no stale-cache success path.

For useful provisional results, explicitly call build_corpus_space again.
It always rebuilds, rechecks policy and creates a new result. Instrumented tests
assert fresh per-record policy checks across unchanged-membership epoch
rotations and byte-identical public projections. Those are rebuild tests, NOT
proof of an authenticated epoch mechanism. Historical snapshots remain history.
Existing blackboard accepted-current/stale ambiguity behavior is unchanged.

Future host integration must own source trust roots and an independent private
cache key (source epoch, monotonic policy epoch, principal/entitlement scope,
selector/schema semantics). It must invalidate before reuse even if membership
is unchanged; acquire an atomic source+policy snapshot or retry privately;
keep source-admission failures and epoch transitions out of public responses;
and never accept these authority values from the requesting caller. It requires
separate review and cannot be enabled through this patch's public arguments.

## Private real v4 evaluation contract

`corpus_evaluation.py` provides executable comparison functions for an owner-
authorized isolated runner with an OUT-OF-TREE private fixture directory.
It is intentionally not a CLI that fetches data or runs on credentialed AORUS.
The operator supplies these independently obtained artifacts:

1. Exact SECH_MASTER_v4.json and SECH_INTAKE_v4.jsonl bytes.
2. A private PrivateV4Contract: exact master JSON pointers for each carrier's
   Drive ID, SHA, year, specialty and source card; the intake card pointer;
   expected study/carrier/pair/unknown counts; fourteen selector cases.
3. Each case contains the exact original oracle predicate JSON, a typed F07
   Predicate translation, private expected study_key/source_shas members,
   membership SHA and counts. Do not substitute a list reconstructed from F07
   results. The original oracle artifact is the independent comparison source.
4. Host policy for a private evaluator entitled to the complete comparison set.

`compare_real_v4_metadata` requires the owner-published MASTER/INTAKE SHA,
population pin and all 14 exact count/digest targets before reading files.
`compare_private_v4_metadata` is the generic synthetic/declared-contract route:
matching caller-selected hashes there is NEVER real-v4 or source authority.
The actual comparison checks file bytes, unique study IDs, unique carrier joins,
carrier ID AND SHA, year/specialty/card equality against master primary-record
pointers, full binding coverage, aggregates, each oracle's internal digest,
actual F07 exact member sets, digest and per-selector counts. It does not just
compare aggregate totals. The canonical membership algorithm matches the
published sorted-key, compact UTF-8 JSON algorithm; the owner population pin is
a separate opaque oracle identifier, not the F07 population checksum algorithm.

MASTER pointer mapping and exact oracle predicate objects were not available in
this run, so they are REQUIRED private contract inputs rather than guessed
schema or selector syntax. Readiness is CONTRACT_AUTHORED, REAL_SCHEMA_BINDING
and REAL_V4_RUN remain BLOCKED until the safe runner supplies/reviews them.
The synthetic tests exercise this mapping and the actual selector call path.

The adapter maps intake year as cohort_year (defense year OR fallback, never
proof of defense), optional specialty, explicit source roles, and structural
pair_status/specialty_status. Missing specialty remains UNKNOWN, not a fabricated
specialty. No lab, supervisor, institution or scientific quality is inferred.

All runtime rows/IDs/pointers and oracle membership digests stay private by
default. The comparison returns only MATCHED_DECLARED_ORACLES and number of
cases, plus pending evidence/currentness and NOT_CLEARED_BY_METADATA QA status.
It never exports member sets or file paths. Missing files or mismatches share
a constant error. The four real first-page QA flags remain unresolved; all 186
records are development-exposed, not blind. QA and private MethodBody access
are outside this function. No source PDFs, raw access, FULL_REQUIRED,
E1/scientific acceptance, method ownership or release rights follow from a match.

## Verification and handoff

Authored adversarial tests include coherent forged reader+pin+year/specialty/
references, honest-but-unattested source, unused exploding readers, fixed-query
hidden worlds and corrupted payloads, carrier-denied collisions, same typed
error in equivalent worlds, no authoritative reuse, fresh rebuilds, permitted
count-only disclosure, visible source drift and shared-carrier deduplication.
Private comparison tests cover exact sets, permutation, known/UNKNOWN/pairs,
recomputed-file-hash mutations, forged IDs, master joins, changed selectors,
wrong expected digest, duplicate/missing rows, policy denial and missing files.
Original typed query, second-host and accepted-history tests remain present.

Executed: read-only Git identity/status/diffs, file/connector reads, source edits,
and git diff --check. No project Python import, AST parser, pytest, Ruff, wheel,
PDF or private v4 metadata execution. Python/py/python3 commands were not found
in this sandbox; the preflight's documented external Python path also failed.
No tests or CI were run and no science acceptance was made.

Changed paths: src/seshat/corpus.py, corpus_adapters.py, corpus_evaluation.py,
__init__.py; tests/test_corpus_selection.py, test_corpus_confidentiality.py,
test_corpus_evaluation.py; README.md and this receipt.

Next isolated exact-tree checks (NOT EXECUTED HERE):
`python -m pytest -q -o pythonpath=src` and `ruff check .`; independent source
review must evaluate both fallback semantics and API compatibility. Safe real
v4 comparison is a separate authorized run, not part of public synthetic CI.
Rollback: discard this job's named file delta or restore it from BASE_SHA in a
new review branch; do not reset canonical main or recover the old verified path
as an accepted trust implementation. No publication or deployment is authorized.

## OPEN QUESTIONS

- Is there an independently authenticated host source verifier? Default: none;
  all selectors remain PENDING_HOST_ATTESTATION.
- Is an independently owned atomic private policy-epoch cache available?
  Default: none; authoritative reuse disabled and currentness UNVERIFIED.
- Are private MASTER mapping and exact oracle artifact available to a safe
  runner? Default: unavailable here; REAL_V4_RUN=BLOCKED, synthetic tests only.
- Are method, PDF identity QA or scientific acceptance rights granted?
  Default: no; four identity flags remain unresolved and no methods execute.
# Superseding host-boundary author delta

The subsequent bounded job jx-a08fbc3306cf is documented in
[S_P1_F07_HOST_BOUNDARY_RECEIPT.md](S_P1_F07_HOST_BOUNDARY_RECEIPT.md).
The older receipt above describes the provisional-only predecessor. Its claims
that no host cache or owner evaluation CLI is authored are superseded by that
delta; neither receipt certifies a deployment or current-tree test PASS.
