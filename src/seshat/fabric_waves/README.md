# SESHAT fabric_waves — executable agent-thread wave engine (prototype)

This is an **additive, namespaced prototype layer** in `src/seshat/fabric_waves/`.
It composes with the existing S2A Blackboard, S2B Runtime and S2B
ReconciliationController without modifying them.  It does **not** invent
MethodBodies for protected profiles.

## What's here

* **`WorkflowThreadSpec`** with the 14 owner-charter properties
  (purpose, input state, admissible sources, distinctions, carriers/nodes,
  completion criterion, output state, rationale, state-transfer rule, decision
  right, next-decision right, constraints, canon status, cost).
* **Typed StoneEvent** dispatcher with kinds `QUERY`, `SOURCE_DELTA`,
  `APORIA`, `HUMAN_DECISION`, `FRONTIER_RETURN`.
* **Deterministic `WaveEngine`** that selects the eligible frontier, fires
  threads under a bounded budget, deposits versioned sediment records and
  stops at saturation (`NO_DELTA`) or APORIA.
* **Two-layer storage**: append-only `RunLedger` (Run/Wave/Activation/Event/
  Decision/Resonance) and versioned `SedimentState` (working/candidate/
  accepted/stale views) keyed by `sediment_id`.
* **`MethodBodyRegistry`** + five safe built-in bodies that operate on
  deterministic synthetic fixtures only — no donor data, no production
  adapters, no secrets.
* **Six resonance kinds**: `ANSWER`, `QUESTION`, `MAP`, `ACTIONABLE_PLAN`,
  `FRONTIER_GAP`, `DECISION_REQUEST` (plus `REPORT` for bundles).
* **HTML + SVG trace renderers** with inline SVG (no external CSS, no JS).

## Invariants enforced

* No universal mandatory `cut → derive → analyze` pipeline.
* Acceptance to ACCEPTED requires an explicit `DecisionRecord` from
  `ACCEPTANCE_DECISION_RIGHT` (`seshat:fabric:human-acceptance`); the engine
  never self-certifies.
* A thread fires only if every `EdgeCondition` and every `PropagationLaw`
  guard is satisfied; "transitive name equality" is rejected.
* `SOURCE_DELTA` wakes **only** threads whose `wakes_on_carrier_ids` matches
  the changed carrier; downstream records go STALE, ancestors are not.
* Replay is byte-for-byte deterministic — same input → same ledger head hash.
* Budget is finite; APORIA halts the run after `aporia_after_waves` waves.

## Demo CLI

```bash
pip install -e ".[dev]"
seshat-fabric-demo --output-dir artifacts/fabric_waves
# or (from repo root, ASCII-only help on Windows cp1251 consoles):
PYTHONPATH=src python scripts/fabric_waves_demo.py --output-dir artifacts/fabric_waves
```

## Operator CLI (typed Stone events)

```bash
seshat-fabric-operator --events path/to/events.json --profile repair --output-dir artifacts/fabric_waves/operator
```

`events.json` is a JSON array of objects with at least `kind` (one of
`QUERY`, `SOURCE_DELTA`, `APORIA`, `HUMAN_DECISION`, `FRONTIER_RETURN`) and
optional `payload`, `target_carrier_id`, `issued_at_tick`, `event_id`.
Profiles: `repair` (D1), `corpus` (D2), `invalidation` (D3 carrier wake).

Produces:

* `summary.json` — one summary per scenario with run, outcome, ledger hash.
* `<scenario>-<run>.json` — full run + ledger + sediment + resonance dump.
* `<scenario>-<run>.html` — self-contained HTML trace.
* `<scenario>-<run>.svg` — inline SVG wave timeline.

## Scenarios

1. `s1` — single-study Object↔Method mutual repair (uppercase + sum).
2. `s2` — corpus question reusing individual sum states (C12/C04
   aggregation).
3. `s3` — changed external EvidenceReturn invalidating dependent
   conclusions and selectively waking only the necessary threads.

## Tests

```bash
PYTHONPATH=src python -m pytest tests/fabric_waves/
```

Run the full suite with ``python -m pytest tests/`` (fabric_waves tests live under
``tests/fabric_waves/``).

## Frontier gaps (NOT_READY)

* `F07` — real scientific MethodBodies (LitOps/Tinkuy/Quinta/D20/Indago)
  not wired in; safe fixtures only.
* Source content providers stay on synthetic SAFE fixtures; full
  `FULL_REQUIRED` end-to-end smoke requires a trusted carrier.
* The HTML trace does not yet cover CARRIER_REVISION hover details.