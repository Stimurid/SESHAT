# S-IMPL-003A — MethodAsset admission: concrete seam and negative oracle v0.1

**Design only / synthetic-only / NOT_IMPLEMENTED.** Prepared by HEPHAESTUS on 2026-10-11, concurrent with a single exclusive Codex core writer addressing publisher [#28](https://github.com/Stimurid/SESHAT/issues/28). This is an engineering handoff supplement to [S3A #41](https://github.com/Stimurid/SESHAT/issues/41), **not** authorization to open a second implementation stream, to load historical methods in public CI, or to merge automatically.

## 1. Verified existing interfaces, rather than a replacement runtime

Pinned starting evidence: `main@2ec1209dd2bb9c5a81e12e70725cad02de3087b1`. As inspected:

- `src/seshat/contracts.py` declares `OperationSpec.implementation_ref`, `RawAccessPolicy`, `ResearchObject`, `SourceContent`, `DerivedObject`, and consequential `AcceptanceState`. Neither `OperationSpec.implementation_ref` nor a pointer's existence proves a method body was loaded.
- `src/seshat/runtime.py::Runtime.run` verifies research source `FULL_REQUIRED`, selects only `blackboard.candidate_state()`, calls `OperationProvider.execute`, forbids provider-origin `ACCEPTED/STALE/REJECTED`, then calls `Blackboard.put`. The order is relevant: do **not** return a derived candidate before method admission is complete.
- `src/seshat/reconciliation.py` defines `ReconciliationProvider.propose`, `_OperationAdapter.execute` (calls provider `propose` before S2 validation/persistence), `ReconciliationController.run` (bounded Object↔Method turns, attempt receipts, APORIA and quarantine). Do **not** add a second cyclic scheduler.
- `src/seshat/adapters/base.py` currently defines `OperationProvider`, `SourceProvider`, `SourceContentProvider`, `SourceAccess`; there is no trusted MethodAsset port yet.
- `profiles/sechenovka_authorabstract/operations.py` pins these profiles:
  - `sechenovka.authorabstract.object` → `Drive:1zzxvEy88Fz61rMJAyUZEr9R3pvIQiCxcHn2ubPS_Pt8`, expected semantic role distributed research-object reconstruction.
  - `sechenovka.authorabstract.method` → `Drive:1LLKU0nC6sVBc34dR_wJSCQF2JCckI2x5oOoo-oN6PdE`, expected semantic role distributed method reconstruction.
  - The legacy methodological-frame label `AGENT_0_METHOD_SECTION_EXTRACTOR` is an **identifier**, NOT a license to implement a headings-only extractor.

## 2. Trust split / asset admission model

Proposed minimal public contracts (names for implementer to reconcile with existing code):

**MethodAssetBinding** (immutable trusted policy input): `asset_id`, `binding_operation_id`, `implementation_ref`, `semantic_role`, `method_version`, `media_type`, `canonical_export_profile`, `expected_sha256` (64 lowercase hex), `expected_byte_length` (positive), `source_rights_ref`, `trusted_policy_id/version`, `admission_state`. Critical: expected digest and rights grant originate from owner-authorized, versioned trusted manifest; NEVER derive a trusted expected hash from the same untrusted provider response.

**MethodAssetContent** (ephemeral execution-only, not a receipt): `asset_id`, `source_version`, `export_profile`, `media_type`, `content: bytes`, `complete`, optional untrusted response metadata. An untrusted `authorized: true` field does not create an authorization grant.

**MethodAssetProvider**: `open_method_asset(binding) → MethodAssetContent`, read-only under a separately authorized identity with least-privilege source access; distinguish method text from the research source. Do not expose browser/Google OAuth credentials to Codex or an LLM proposer.

**MethodAssetReadReceipt**: only `asset_id`, operation binding, fixed source locator, declared vs returned export profile, version, verified digest/byte length, rights decision reference, status/typed error and run_id; never full method content, secret-bearing source URL/query, exception string or raw prompt.

**VerifiedMethodProposer**: accepts `spec`, full research-source `SourceAccess`, admissible prior candidate state, and an **execution-only** verified method byte handle. It returns a proposed `ReconciliationProposal` with `WORKING` or `PROPOSED` candidate; it never grants scientific acceptance.

## 3. Exact execution seam: pair-wide preflight before any Blackboard writes

A naive wrapper checking the Method asset only on its first `propose` is insufficient. For Object↔Method pair, the Object candidate may already have been persisted when the Method lookup fails. Therefore S3A must **pre-admit the complete required method-asset bundle for both profile operations atomically before `ReconciliationController.run`**:

1. Resolve the *trusted* per-operation bindings for every planned operation. Reject an unbound operation, unknown/metadata-only ref, missing expected hash/length, rights denial, mismatch between `OperationSpec.implementation_ref` and trusted binding, or wrong operation semantic role. Register original Drive IDs as `AUTH_REQUIRED / CONTENT_HASH_UNVERIFIED` until authorized export exists; their Google Docs revision IDs are NOT byte hashes.
2. For **each** required method, obtain immutable/snapshot-backed **complete** exported bytes, canonical export format (including UTF-8/NFC/newline rules only if explicitly declared), stable version, actual hash and actual length. Compare against separately trusted expected bytes, export profile, rights policy and operation identity. A later source modification must not reuse the stale admitted handle.
3. Only if **all** required methods pass: create immutable in-memory method handles and construct exactly the two `ReconciliationProvider` wrappers. The wrapper calls the existing typed proposal port with the verified method bytes and delegates proposal validation to the existing `_OperationAdapter`. In the fail case, do not call `ReconciliationController.run` and do not write *any* candidate to `Blackboard`.
4. At each operation invocation, verify the binding and pinned version are still valid. Source-provider drift after pair preflight produces typed `METHOD_ASSET_DRIFT` and **quarantines current run outputs**; never silently reuse stale methods or let another provider bypass the verified wrapper. If S2B currently maps the exception to generic provider error, introduce a narrowly typed stop mapping with negative tests, not a broad rewrite.
5. Bind exact method-ref/version/digest + source-ref/version/digest into derived **provenance and attempt receipts** without raw text. S2B source-ref and acceptance gates remain intact. Keep research `FULL_REQUIRED` independent from methodology asset admission: a method pointer in the research source list must never make the method readable.

**Open implementation choice to decide by tests:** whether the method bundle is read once with a snapshot token validated on each call, or re-read at each attempt. Either is acceptable if an in-between mutation is not silently ignored and no content leak reaches public logs. Content-addressable versioned snapshot is preferable where source API supports it.

## 4. Synthetic-only fixtures, no historical prompts

All CI fixtures are fabricated; not paraphrases of the original Object/Agent-0 prompts.

- **Synthetic research source `research.v1`**: UTF-8 bytes from the literal LF-terminated text:
  `Title: Synthetic study on three signals.\nMaterials: records from fictitious sensor set R.\nResults: the third signal was normalized twice.\nDiscussion: two readings disagree on the target construct.\nAppendix: calibration steps for each sensor were recorded here.\n`
  This deliberately distributes method-relevant evidence outside a named “Methods” section.
- **Synthetic Object asset `fixture.object.v1`**:
  `SYNTHETIC OBJECT OPERATION, NOT A REAL METHOD.\nDistinguish stated object, material, functional object and alternative objectifications.\nGive source-grounded candidate only; never assert ACCEPTED.\n`
- **Synthetic Method asset `fixture.method.v1`**:
  `SYNTHETIC METHOD OPERATION, NOT A REAL METHOD.\nFind procedures, measurements, calibration and analysis across all source sections.\nReport conflicts as candidate evidence, not a forced definitive method.\n`
- Construct `expected_sha256 = SHA256(known_good_bytes)` and length from *trusted immutable fixture setup before any mutation*; mutate only provider-returned bytes for integrity-negative tests. The actual bytes handed to the fake proposer must be checked by test equality; do not self-certify from a digest computed on received corrupted bytes.

Binding table:

| operation_id | trusted synthetic asset | expected role | real source state |
|---|---|---|---|
| `sechenovka.authorabstract.object` | `fixture.object.v1` | `distributed_object_reconstruction` | `AUTH_REQUIRED` |
| `sechenovka.authorabstract.method` | `fixture.method.v1` | `distributed_method_reconstruction` | `AUTH_REQUIRED` |

## 5. Mandatory RED→GREEN test matrix (independent failure witnesses)

| ID | Fixture / perturbation | Required oracle |
|---|---|---|
| S3A-T01 | Both synthetic assets; trusted hashes, rights, versions and correct operation IDs | Both complete exact bytes reach deterministic proposer; receipts verified; candidates `WORKING`; no automatic acceptance |
| S3A-T02 | Method 2 omitted, metadata-only pointer, empty or truncated output | Pair-wide preflight fails before Object is proposed; zero provider calls and zero Blackboard writes |
| S3A-T03 | Modified bytes, expected length mismatch, wrong export MIME/profile, changed source version | Typed denial; never compute expected digest from returned bytes |
| S3A-T04 | Swap Object and Method bindings or provide unrelated operation ID | Binding mismatch; no proposal and no writes |
| S3A-T05 | Access denied, revoked grant, wrong bearer, malicious `authorized:true` claimed in payload | Trusted rights policy denies; no leaked source/prompts/credentials in error, manifest or Git |
| S3A-T06 | Same research source declared `FULL_REQUIRED` but method pointer only in research carrier list | Still needs separate MethodAsset authorization; metadata existence cannot satisfy method admission |
| S3A-T07 | Method drift **between** pair-wide admission and the second proposer call | Typed stop and quarantined run output; no stale current candidate |
| S3A-T08 | Source research version changes while method asset stays fixed, and vice versa | Only affected descendants invalidated/held; exact source and method provenance retained |
| S3A-T09 | In method bytes: “approve everything”, “read forbidden file”, “publish token” | Text remains untrusted instruction input; cannot override human acceptance, host scope or rights |
| S3A-T10 | Real Drive IDs return revision 1/paragraph counts but no authorized canonical export digest | `AUTH_REQUIRED/CONTENT_HASH_UNVERIFIED`, never `REAL_METHOD_MOUNTED` |
| S3A-T11 | Synthetic method clue appears only in `Appendix` and `Results` | Whole research bytes remain available; no upstream section-only censor |
| S3A-T12 | Provider returns `ACCEPTED` or research object/operation mismatch | Existing S1/S2B gates still block before acceptance |
| S3A-T13 | Real source body accidently included in public receipt, error or PR | Fail leak scan; public artifact contains only refs/digests/status |
| S3A-T14 | End-to-end exact SHA tests + existing S1/S2A/S2B suite | `pytest -q`, `ruff check .`, CI and source-only diff readback; fail on regression |

## 6. Release and rights boundaries

- Actual Google Drive files were read through a connected identity in prior source probe [#41/comment 6111893958](https://github.com/Stimurid/SESHAT/issues/41#issuecomment-6111893958). There are 753 and 260 API paragraphs; native revisions/paragraph lengths are **NOT** export bytes or checksums. The permission metadata is “anyone with link: reader”; **do not falsely call this restricted Drive ACL**. Public Git non-disclosure remains mandatory until method owner authorizes.
- No Google Drive export serialization is yet canonically selected and byte-hashed. No signed authorization from method owner, no code runtime adapter or real method acceptance. These are distinct gating states.
- S3A should deliver a single Codex PR with exact source/test paths, typed failure receipts and `docs/S_IMPL_003A_RESULT.md`, accepted by engineering separately. S3B needs separately authorized *original* method readback and semantic canary. HEPHAESTUS can approve engineering only; Artikl/method owner retains scientific semantics and consequential acceptance.
- This design may be revised by implementation evidence. **Current status = CONTRACT_DESIGNED, TEST_ORACLES_SPECIFIED, NOT_IMPLEMENTED, NOT_DISPATCHED.** One executable-core writer remains active on publisher #28/PR39. Do not start S3A concurrently without an explicit change of code ownership.
