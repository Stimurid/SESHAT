# FABRIC WAVES CARPET — vertical integration receipt

## Status

**INTEGRATE (bounded prototype)** — executable agent-thread wave engine with operator
trace CLI, three owner scenarios (D1–D3), and regression coverage for independent
review blockers encoded as `tests/fabric_waves/test_review_blockers.py`. Does **not**
claim R01–R09, protected MethodBodies, F07 donor wiring, or scientific acceptance.

## Workspace preflight

- **WORKSPACE_MODE:** `WINDOWS_LOCAL` (aiye-executor worktree)
- **WORKDIR_ABSOLUTE:** `C:\AI\llm\aiye-executor\worktrees\jx-2a5815b9519b`
- **ORIGIN_URL:** `https://github.com/Stimurid/SESHAT.git`
- **CURRENT_BRANCH:** `aiye/exec-2a5815b9519b`
- **BASE_SHA (parent at session start):** `7f2aea32a968e5241ba7dba71fcb49857f125786`
- **DIRTY_STATUS (before commit):** modified `src/`, `tests/`, `scripts/`, `pyproject.toml`, `docs/`; untracked `AIYE_EXECUTOR_TASK.md`

## Independent reviewer jx-d6c301f31bca

**NOT READ** — reviewer stdout was not present in the workspace or local aiye index at
execution time. **Assumption used:** P1 blockers are encoded in
`tests/fabric_waves/test_review_blockers.py` and must pass before UI work; all such
tests passed locally in this session.

## CURRENT_TASK

Owner carpet vertical integration (goal doc Drive `1W-9wxVUq_yQZECDLtrK6IIiFsq0KTj4347fVzQJ7Yf4`).

## Evidence executed (this session)

| Command | Result |
|--------|--------|
| `python -m pytest` | **164 passed** (0.30s) |
| `python scripts/fabric_waves_demo.py --output-dir _demo_out_exec` | **3 scenarios**, artifacts written |
| `seshat-fabric-demo --scenario s1 --output-dir _wheel_test_out` | **wheel entry point OK** |
| `python -m scripts.fabric_waves_demo --help` | **OK** after ASCII docstring fix (cp1251) |

## Deliverables

- **D1** — `test_single_study_object_method_mutual_repair` + scenario `s1`
- **D2** — `test_corpus_aggregation_succeeds_when_corpus_registered_before_sum` + scenario `s2`
- **D3** — transitive invalidation + selective SOURCE_DELTA wake + unrelated sediment preserved
- **Operator surface** — `seshat-fabric-operator` JSON Stone events; HTML trace shows budget,
  stone events, workflow threads, sediment read-deps, waves/activations/resonance (per run)
- **Demos** — `seshat-fabric-demo` and `scripts/fabric_waves_demo.py` (reproducible JSON/HTML/SVG)

## Changed paths (this commit slice)

- `src/seshat/fabric_waves/operator.py` (new)
- `src/seshat/fabric_waves/trace.py`, `demo.py`
- `scripts/fabric_waves_demo.py`
- `tests/fabric_waves/test_operator.py`, `test_trace.py`
- `pyproject.toml` (`seshat-fabric-operator` console script)
- `src/seshat/fabric_waves/README.md`
- `docs/FABRIC_WAVES_CARPET_INTEGRATION_RESULT.md`

## NEXT_GATE

- Isolated GitHub PR CI on trusted runner (not credential-bearing local account policy)
- Human / implementation-lead review; inbox [#6](https://github.com/Stimurid/SESHAT/issues/6)
- No merge to `main` from this executor job

## BLOCKERS / limits

- Reviewer jx-d6c301f31bca stdout unavailable — P1 status inferred from tests only
- Safe fixture MethodBodies only; no production source carriers
- `_demo_out*` trees in branch are demo artifacts, not CI gates
