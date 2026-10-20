# fabric_waves: unaccepted synthetic prototype

This namespace is additive to the accepted S1/S2 code. It uses the existing
RuntimeSourceAccess port without changing accepted runtime, contracts,
blackboard, reconciliation, profiles or host operations. It does not demonstrate
private MethodBody admission, scientific acceptance, production F07, reports
R01–R09, operator utility or independent multi-host reuse.

The P1 repair is source-level work pending isolated tests and independent review.
See docs/RUG_P1_CLOSURE_RECEIPT_20261014.md for provenance and execution truth.

## Boundaries

- FULL_REQUIRED needs a trusted FabricCarrierStore and complete authorized,
  version-consistent readable UTF-8 content. DRILLBACK needs an explicit pinned
  address. NEVER gets no event payload or source bytes. Derived inputs are only
  explicitly declared current working states.
- Source revisions require an injected host revision provider. Old version,
  old rights, new version, source identity and actual new bytes are checked;
  event flags never grant rights. Missing providers fail closed.
- Registry admission explicitly lists supported operation IDs. Nodes explicitly
  name registered method refs and output IDs/types (output_contracts for multiple
  outputs). Body output version must equal its canonical payload_hash. The engine
  derives persisted identity from payload, dependency versions, method and source
  receipts. Invalid outputs commit no partial state.
- E1 requires an actual trusted source read. E5 remains PROPOSED, never canonical
  acceptance. Acceptance uses an external verifier over issuer, actor, right,
  exact subject/version, choice, decision ID and nonce. There is no embedded trust
  key or bare-string public accept path. Rejected/invalid decisions cannot accept.
  The host must persist/reload its decision ledger and retain replay state.
- Node guards run just before each invocation. Changed outputs each emit causal
  events. Stale intermediates do not stop invalidation. Fresh runs reset counters;
  each event is charged once and each node invocation consumes an activation.
- Error/APORIA public details are fixed codes, provider output is suppressed,
  and late output writes stage atomically. This is NOT an OS sandbox for arbitrary
  hostile Python, nor a per-body wall-clock timeout. Only admitted synthetic
  callables may run here; isolate execution at the host boundary.
- Export uses detached per-run snapshots. Ledger verification checks append order,
  lengths and final head; verify_serialized requires an independently retained
  head checkpoint. Hashes do not authenticate a checkpoint an attacker replaces.

## Three synthetic scenarios

1. s1: source -> Object hypothesis -> Method critique -> Object refusal/APORIA.
   This deliberately ends unresolved; it does not fabricate a scientific repair.
2. s2: explicit version-pinned SyntheticCorpusSelection, two individually read
   cached study states, then aggregation of exactly those refs. Registration order
   and unrelated similarly named states do not define membership.
3. s3: trusted source revision -> A/B/C invalidation and refreshed versions;
   unrelated U is retained. Initial export remains frozen. This is a source
   revision fixture, not an authenticated external EvidenceReturn integration.

## Reproduce only in an authorized credential-free runner

```sh
python -m pip install build pytest ruff
python -m build --wheel
python -m pip install dist/*.whl
python -m pytest -q
python -m ruff check .
seshat-fabric-demo --scenario all --output-dir artifacts/fabric_waves
python scripts/carpet_portfolio.py --output-dir artifacts/carpet_portfolio
```

The PR workflow `.github/workflows/fabric-waves.yml` also tests the installed
entry point outside the checkout and runs five portable negative oracles against
the rejected parent. Its source/tree pins, JUnit, wheel and trace artifacts must
be reviewed. This job did not run that workflow or those commands.

Expected artifact paths: s1-s1-repair.{json,html,svg},
s2-s2-corpus.{json,html,svg}, s3-s3-init.{json,html,svg},
s3-s3-after-delta.{json,html,svg}, summary.json.

The operator CLI uses the same synthetic profiles. Event payloads are untrusted;
HUMAN_DECISION events do not replace the authenticated decision API, and an
arbitrary FRONTIER_RETURN event does not establish trusted external evidence.
