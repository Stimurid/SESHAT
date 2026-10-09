# SOCRATES × TINKUY — multi-body genealogy audit v0.1

**Status:** read-only physical and source inspection; historical code/test witnesses, **not** tests freshly executed.
**Drive mirror:** [05 SESHAT — Socrates × Tinkuy Donor Genealogy](https://docs.google.com/document/d/13Q-ikcyYuYZ_5zs8iHM5BJRV2os6VYHK5m0BAAvA2Z8/edit).
**Standing intake:** [#6](https://github.com/Stimurid/SESHAT/issues/6).

## Correction to source-carrier inventory

The initial SESHAT census describes Socrates mainly as `Stimurid/zarathustra-:CALIFORNIAN_ID/src/socrates_runtime/`. This is **not a complete physical Socrates genealogy**.

There is an **independent original** `https://github.com/TyumenAILab/socrates.git` line:
- local live checkout `C:\projects\tyumen-socrates`, branch `arena/tinkuy-harness-incubator@0135959`, dirty (3 changes; never touched);
- clean read-only historical main checkout `C:\projects\tyumen-socrates-main-readonly-41fcf2b`, commit `41fcf2b`.
- actual code areas: `topdown/`, `bottomup/`, `space/`, `arena/`; common `waku-fork/` is read-only and `forum/` is a message surface.
- the old `topdown/README.md` documents explicit scene intent/position/truth_mode and space management, local state/memory and gate-before-main-loop.
- code witness `topdown/waku/loop/agent.py`: bounded tool loop with observer/trace and max iterations.
- deterministic tests **present, not rerun**: `topdown/evals/deterministic/test_contract.py` (scripted confirm gate, typed statuses, provenance, tentative fallback); `test_dashboard_space_contract.py` (shared contract/space UI state path).

### Rejected shared runtime is a deliberate governance fact

`docs/adr/0006-shared-repo-fork-topdown-bottomup-forum.md` explicitly **rejects a shared importable `waku-fork` dependency**, choosing independent topdown/bottomup copies because two owners and two distinct loops need decoupled evolution. SESHAT cannot treat this intentional divergence as forgotten plumbing that should automatically be deprecated. Shared typed interfaces/adapters may be useful; forcing a shared runtime requires reviewing that decision with owners.

## Tinkuy and the zarathustra- Socrates contour are another physical body

Verified clean worktrees in the second repository:
- `Stimurid/zarathustra-` `C:\projects\tinkuy-socrates-gcur28-pin-7ca2934 @7ca2934`;
- `C:\projects\tinkuy-socrates-gcur30a-20260917 @f87ccb8`;
- `C:\projects\zarathustra-g-next-03 @c1298e8`;
- earlier inspected later branch `socrates/gcur32-claude-overnight-20260930@7d94e62`.

Original local `C:\projects\tinkuy\CALIFORNIAN_ID` describes candidate v0.3.0. Older zarathustra worktree `CALIFORNIAN_ID/README.md` describes candidate v0.4.0 and **reports 66/66 historical tests passed**; the tests were not rerun by this audit. Its main council is deliberately sequential, shares a `BodyProjection` and gives heads slices, rather than the full original input.

`CALIFORNIAN_ID/src/californian_id/fabric/parser.py` (source read, ~403 lines) is a separate **FabricParser**, which refuses a mock provider and performs source mapping, semantic move extraction, assembly, relation/thread extraction, scene reconstruction and provenance/no-loss validation. Its source also says passes **02 multiscale**, **07 cross-scale**, and **08 boundary repair** may be non-blockingly skipped on invalid LLM JSON. Thus the council's mock-first / historical test status is NOT proof of full FabricParser live coverage.

Later `CALIFORNIAN_ID/src/socrates_runtime/` has concrete modules `epistemic_model.py`, `projection.py`, `aporia_and_world_map.py`, `cutter_registry.py`, `scene_contract.py`, `governor.py`, etc. The read `scene_contract.py` explicitly restricts ContractRevisionCandidate to **unprivileged evidence** and admits scene revisions only through governed admission. This is a valid code witness, but it does not prove runtime equivalence to TyumenAILab topdown.

## Corrections and dispositions

| Carrier/capability | Decision until tests |
|---|---|
| `TyumenAILab/socrates:topdown` contract/memory/truth-mode gate | WRAP; possible contract EXTRACT; keep owner/authority |
| `TyumenAILab/socrates:bottomup`, arena | UNKNOWN_HOLD pending specific audit |
| `Stimurid/zarathustra-:socrates_runtime` | REUSE/EXTRACT typed status, aporia, projection and revision *selectively* |
| `Stimurid/zarathustra-:fabric/FabricParser` | WRAP as non-sovereign observation provider; COMPLETE skip/coverage tests |
| `CALIFORNIAN_ID` sequential ideological council | specialized profile/topology comparison, NOT mandatory SESHAT pipeline |

**No automatic shared implementation promotion.** Code identity, ancestry, currentness, acceptance and semantic authority must be established separately for each carrier.

## Relevance to SESHAT

- S1 source access remains unaffected and should proceed.
- S2 acceptance/revision contracts may compare both Socrates bodies.
- S5 two-host admission must not claim independence from two adapters into one merged runtime.
- S6 topology comparison may include a sequential dialogue council as a contrast, but not as universal architecture.
- Fabric skip behavior is negative-test evidence; source_map/cuts are not the distributed semantic research Object.

**Next checks:** repo ancestry and version history, the bottomup/space/arena packets, Fabric pass coverage in earlier generations, exact tests/receipts. No donor code was modified.

Source proofs: physical local roots noted above, ADR 0006, inspected source files and deterministic test modules.
