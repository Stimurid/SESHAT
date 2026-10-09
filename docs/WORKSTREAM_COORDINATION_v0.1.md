# SESHAT WORKSTREAM OWNERSHIP v0.1

Status: coordination proposal for three parallel workstreams. Canonical repo: Stimurid/SESHAT. Local path: C:\projects\seshat.

## Roles

- Archaeology / architecture review (this chat): prior implementations, rejected versions, preservation of donor capability, source-grounded dispositions, review of method contracts, negative tests and recommendations. Publishes audit reports and issues. Does not edit implementation code concurrently.
- Implementation lead (neighboring chat): executable code, adapters, profiles, tests, CI, branches and merges. Reads historical donor evidence before claiming capability absent. Owns src/, tests/, profiles/ and workflows.
- Indago: external analog research, reproducible evidence and counterexamples, ledger/provenance, targeted ResearchNeed and EvidenceReturn records. Does not merge runtime code or override semantic methods.
- User/semantic acceptance: material methodology and ontology decisions; engineering passing tests alone does not establish scientific correctness.

## Coordination law

Only the implementation lead writes executable core during parallel work. Audit and research return source-pinned evidence and tasks. No second SESHAT repo, no duplicate agent implementation, no code changes based solely on the last donor commit. Implementation returns PR/commit, CI, trace and acceptance receipts. The review chat checks them against source-authorized methods and historical regressions.

Every donor handoff records: item ID, question, repo/path/commit or Drive ID, old generations and reasons for rejection, observed code/test/reachability status, REUSE/WRAP/EXTRACT/COMPLETE/DEPRECATE/UNKNOWN_HOLD recommendation, contract impact, tests and owner.

## Starting point

Baseline repository main was 4ab96573cd7bc47d51986ca06e5f4b249342b048 before this record. Recheck HEAD before implementation.
- Core: src/seshat; profiles/sechenovka_authorabstract; tests/ and CI.
- Architecture: docs/IMPLEMENTATION_CHARTER.md and docs/DONOR_MAP.md.
- Revised donor census: docs/DONOR_IMPLEMENTATION_CENSUS_v0.1.md.
- Quinta historical audit: docs/QUINTA_MULTI_GENERATION_DONOR_ARCHAEOLOGY_v0.1.md.
- Historical code recovery: GitHub issue 1, https://github.com/Stimurid/SESHAT/issues/1.

The implementation lead should continue the existing Object/Method vertical slice, with real method bodies and controlled revisions, rather than build another architecture skeleton. The audit chat continues donor archaeology and PR review. Indago continues its independent hunt, recording findings durably and returning only relevant evidence.

## Conflict resolution

Evidence/source disputes: archaeology supplies witnesses. Runtime disputes: implementation supplies reproducible tests. Meaning/method disputes: flag unresolved and seek the user's decision. External research disputes: Indago supplies source material, not unilateral authority.

Note: earlier attempt to update the Drive census received 403 permission error; Git has the corrected copy. Do not claim Drive sync without verified readback.
