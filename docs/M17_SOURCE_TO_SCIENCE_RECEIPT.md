# M17 source-to-science vertical receipt

Status: `IMPLEMENTED_AWAITING_NATIVE_EXECUTION`

## Scope delivered

- Typed reusable import of owner-controlled `AuthorialStudyOracle` overlays.
- ResearchObject identity remains separate from A/D SourceCarrier identity.
- Fourteen ordered E2 answer candidates, typed source-page ClaimEvidence and
  unresolved Contradiction/APORIA state.
- Coherent R01/R02 prose with explicit SOURCE_REPORTED, E2 candidate,
  proposed/admitted, PARTIAL and UNKNOWN distinctions.
- Selector safety: A-only excludes D-only claims; D-only remains a real study
  view; A+D may expose cross-source claims and conflicts.
- Existing `WaveEngine` execution bound to loaded source IDs/hashes, with two
  distinct persisted activations for a contradiction-bearing multi-carrier
  overlay.
- Source/analysis-gated replay, stable report versions, targeted contradiction
  invalidation, zero model calls, and UTF-8 CLI output configuration.

## Public/private boundary

Public code and tests contain only source-neutral synthetic facts. No private
PDF, source text, source title, author name, real medical count, or private
oracle body is included here. Private extracted text exists only in the
operator process and is not serialized into the sanitized M17 Carpet ledger.

## Verification in this bounded worker

`git diff --check` passed (only the repository's normal LF→CRLF warning).
Python execution was attempted through
`C:\AI\llm\.venv\Scripts\python.exe`; the uv trampoline failed before Python
started with `permission denied (os error 5)` for both the focused pytest command
and the exact owner-private M17 CLI command (whose output target was `%TEMP%`).
Therefore this receipt does not
claim local pytest, Ruff, private PDF execution, Git commit, PR, or CI success.
The Hub owns the post-worker snapshot commit. A native runner must replace this
status with exact command output and artifacts.

## Required native commands

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='<worktree>\src'

python -m pytest -q tests\test_product_preview.py tests\test_m17_authorial_oracle.py
python -m ruff check src\seshat\authorial_oracle.py src\seshat\m17_source_carpet.py src\seshat\product_preview.py tests\test_m17_authorial_oracle.py

python -m seshat.product_preview `
  --manifest <owner-private-case-root>\manifest.json `
  --study-analysis <owner-private-case-root>\authorial-oracle.json `
  --output <owner-private-case-root>\run-m17

python -m seshat.product_preview `
  --manifest <owner-private-case-root>\manifest.json `
  --study-analysis <owner-private-case-root>\authorial-oracle.json `
  --output <owner-private-case-root>\run-m17 `
  --resume
```

## Human boundary

All generated state is `SELF_OBSERVED_UNATTESTED`. It is neither independent
medical/scientific acceptance nor customer/publication approval. The abolished
standalone issuer is not restored or emulated.

## Activity/product effect receipt

```json
{
  "schema": "activity_product_effect_receipt_v0.1",
  "ticket": "SESHAT-M17",
  "request_summary": "Ship a source-bound AuthorialStudyOracle to coherent R01/R02 and actual Carpet/F09A replay without publishing private source material.",
  "depth": "deep",
  "actor": "bounded delegated CLI worker / exclusive engineering writer",
  "use_activity": "turn owner-selected source material and an authorial analytical overlay into inspectable, source-addressed research reports",
  "telos_hypotheses": [
    {
      "text": "make the existing no-server research product functionally useful before further hardening",
      "confidence": "high",
      "evidence": ["explicit M17 mission and functional-completeness priority"]
    }
  ],
  "intervention_chosen": "literal",
  "intervention_alternatives_considered": [
    "plan-only response rejected",
    "new server/runtime rejected",
    "private fixture publication rejected"
  ],
  "rights_checked": [
    "assigned worktree write",
    "owner-selected private inputs read-only",
    "no Git metadata, merge, deploy, server, secrets, or publication mutation"
  ],
  "protected_human_functions": [
    "scientific acceptance",
    "clinical interpretation",
    "publication acceptance"
  ],
  "uep_decision_id": null,
  "delivery_status": "partial",
  "installed": "not_applicable",
  "loaded": "not_observed",
  "behavioral_change": "not_observed",
  "product_in_use": "not_observed",
  "unknowns": [
    "exact-tree pytest and Ruff result",
    "M17 private PDF CLI artifact result",
    "Hub snapshot commit and CI result"
  ],
  "observed_at_utc": "2026-10-23T14:22:26Z"
}
```
