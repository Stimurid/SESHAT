# Donor / Adapter Map v0.1

SESHAT is assembled from existing ecosystem implementation where possible. Donor systems remain independently governed.

| Donor | Candidate reusable contribution | Default disposition to verify |
|---|---|---|
| LitOps | source ingestion, provenance, longitudinal source/corpus handling, observation candidates | REUSE / WRAP |
| Tinkuy Fabric | multiscale evidence observations, semantic units, competing views | EXTRACT / COMPLETE |
| Socrates | typed operation/projection state, dependency graph, epistemic status and reconciliation mechanics | REUSE / EXTRACT |
| Quinta / AgentRun | run/profile execution mechanics, run trace, profile-bound behavior | REUSE / WRAP |
| D20 | entity/field state substrate and shared typed state | REUSE / WRAP |
| Indago | research transaction, search need, evidence return, provenance of external discovery | WRAP / REUSE |
| PRAGMA / Paideia | typed packages, reconciliation, return/acceptance, state/version transitions | EXTRACT / WRAP |

## Rules

1. Never copy a donor wholesale into SESHAT.
2. Keep semantic origin and code lineage separately.
3. An adapter may be preferable to extraction when the donor remains the natural execution owner.
4. Shared code becomes SESHAT-owned only when its boundary and release lifecycle are genuinely shared.
5. Donor upgrades must not be silently forked into stale SESHAT copies.
6. Every imported slice requires:
   - source repository/path;
   - commit/revision witness;
   - owner;
   - tests or executable evidence where available;
   - chosen disposition;
   - compatibility obligations.
