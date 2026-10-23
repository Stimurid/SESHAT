# M13–M16 product build receipt

Status: `IMPLEMENTED_UNEXECUTED_IN_CURRENT_SANDBOX`

## Workspace

- `WORKSPACE_MODE`: executor isolated worktree
- `WORKDIR_ABSOLUTE`: `C:\AI\llm\aiye-executor\worktrees\jx-4cdcf2bc7ca1`
- `ORIGIN_URL`: `https://github.com/Stimurid/SESHAT.git`
- `BASE_SHA`: `501e508d28d56e346f1c4936b44f9ded83dc48df`
- `CURRENT_TASK`: M13–M16 functional product preview
- `CURRENT_PR`: none created by bounded worker; Hub owns snapshot publication
- `NEXT_GATE`: execute exact-tree tests and public preview on a Python-capable runner
- `BLOCKERS`: the only discovered project venv is a uv trampoline whose base
  interpreter is denied by the workspace sandbox (`permission denied (os error
  5)`). No Git metadata write, push, merge, production, secrets, or Drive write
  was attempted.

## Delivered

- `src/seshat/product_preview.py`: one CLI and API for generic PDF/TXT intake,
  five selection modes, immutable method-output pins, R01–R09 projections,
  M5/M6 activation/delta evidence, two-host F09A run/resume, source-revision
  invalidation, Markdown/JSON/HTML, and a concise status matrix.
- `tests/test_product_preview.py`: 12 focused tests covering absent D, distinct
  selector membership, malformed source, duplicate study-carrier, R03 purpose,
  missing external evidence, immutable/missing methods, resume, source change,
  owner exclusion, and real-manifest-only archive counting.
- `examples/product_preview/`: three public synthetic text sources (including a
  meteorology study), five selectors, and a clearly labelled synthetic I11
  fixture. It is not presented as authorial science.
- `docs/PRODUCT_PREVIEW_M13_M16.md`, README, and console-script entry point.

## Truthful verification record

Executed:

- workspace/origin/branch/HEAD/dirty preflight;
- current owner v0.12 and product-first frontier read through connected Drive;
- `git diff --check` (no whitespace errors; only Git LF→CRLF notices);
- example manifest parsed with PowerShell `ConvertFrom-Json` (3 sources,
  5 selectors);
- structural delimiter count on both new Python files (balanced parentheses
  and braces, no tabs);
- confirmed 12 named tests exist.

Attempted but not executed:

```text
C:\AI\llm\.venv\Scripts\python.exe -m pytest -q tests\test_product_preview.py
error: uv trampoline failed to spawn Python child process
Caused by: permission denied (os error 5)

C:\AI\llm\.venv\Scripts\python.exe -m ruff check ...
error: uv trampoline failed to spawn Python child process
Caused by: permission denied (os error 5)
```

Therefore there is no claim that the 12 new tests, full suite, Ruff, or the
example CLI passed in this worker. Historical `1240 PASS` applies only to the
base SHA. Tangible generated runtime outputs will exist only after the documented
CLI is actually run; no activation/event receipt was hand-fabricated to fill
that gap.

## WORKS / PARTIAL / MISSING

| Capability | Engineering state | Runtime evidence in this job |
| --- | --- | --- |
| Generic owner PDF/TXT intake | WORKS in code | PARTIAL — not executed |
| A/D/A+D/article/arbitrary selection | WORKS in code/tests | PARTIAL — not executed |
| M13 selected-source causal Carpet route | PARTIAL: real synthetic M5/M6 witnesses, selected-source binding still missing | MISSING — sandbox Python denied |
| R01–R04 distinct substantive projections | WORKS in code | PARTIAL — not rendered here |
| R05–R09 honest projections | WORKS/PARTIAL by evidence availability | PARTIAL — no real SRC-C/SRC-D |
| F09A Sechenovka-like + meteorology | WORKS by existing batch API path | MISSING — sandbox Python denied |
| Resume/selective invalidation | WORKS in code/tests | PARTIAL — tests authored, not run |
| 186 archive compatibility | WORKS only from actual JSON record manifest | MISSING — no real manifest supplied |
| Owner scientific/customer acceptance | MISSING by design | human-only |

## Activity/product effect receipt

```json
{
  "schema": "activity_product_effect_receipt_v0.1",
  "ticket": "M13-M16-FUNCTIONAL-PRODUCT",
  "request_summary": "Build a no-server SESHAT research-product preview",
  "depth": "deep",
  "actor": "bounded delegated CLI worker / exclusive core writer",
  "use_activity": "inspect selected research materials, compare subsets, and produce evidence-addressed reports",
  "telos_hypotheses": [
    {
      "text": "make the existing fabric usable end-to-end before concentrated hardening",
      "confidence": "high",
      "evidence": ["owner product-first override 2026-10-23"]
    }
  ],
  "intervention_chosen": "literal",
  "intervention_alternatives_considered": ["new runtime rejected", "template-only reports rejected"],
  "rights_checked": ["assigned worktree write", "no Git metadata", "no deploy/merge", "owner-selected local files"],
  "protected_human_functions": ["scientific acceptance", "publication acceptance", "institutional decision"],
  "uep_decision_id": null,
  "delivery_status": "partial",
  "installed": "not_applicable",
  "loaded": "not_observed",
  "product_in_use": "not_observed",
  "behavioral_change": "not_observed",
  "unknowns": ["exact-tree test outcome", "real owner-source run", "real 186-record manifest"],
  "observed_at_utc": "2026-10-23T13:38:53Z"
}
```

## OPEN QUESTIONS

1. Which real owner corpus manifest should be used first? Default used: public
   synthetic fixture only; no private bytes copied into Git.
2. Are real historical I11/I08/I09/I12/C09 output paths available to the CLI?
   Default used: accept immutable paths when supplied; otherwise report partial.
3. Is a real 186-record archive manifest available? Default used: no; reject a
   bare declared count.
