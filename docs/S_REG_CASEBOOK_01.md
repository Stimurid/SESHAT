# S-REG-CASEBOOK-01 — Sechenovka v4 methodology development panel (not blind)

**State:** PRE-REGISTERED CANDIDATE PANEL / NO MODEL RUN / NO PAGE-APPROVED GOLD.
**Machine fixture:** evaluation/sechenov_v4_method_contrast_development.v0.json
**Detailed source-reading notes:** https://docs.google.com/document/d/1hB43PDHAfsAqAY3_XgGfYo2CJQWLEG8_RRE7Wn7jj94/edit
**Governance:** [#50](https://github.com/Stimurid/SESHAT/issues/50), corpus [#24](https://github.com/Stimurid/SESHAT/issues/24), scan-regression [#47](https://github.com/Stimurid/SESHAT/issues/47), synthetic method admission [#41](https://github.com/Stimurid/SESHAT/issues/41).

## Why this panel exists

The canonical v4 intake contains 186 research objects and 94 paired dissertations. Having 280 unique original PDFs with Drive IDs does not establish that SESHAT read any full text or reconstructed a method. The linked 9-case panel supplies **development-exposed** variations and already observed negative situations. The positive observations came from extracted *actual* authorabstract and full-dissertation text; they remain hypotheses for adjudication, not final source-page gold. PDFs/rights/private Object/Agent-0 MethodAsset bodies are **not** embedded in this repository or in CI.

The selected cases force the scientific representation to discriminate:

1. P01 Guseva: 80/20 training/test, six **specific** regression algorithms (linear, SVM, kNN, random forest, tree, neural net), multiple feature-selection families, and failed cross/external validation despite apparently good training fit. A statement "ML confirmed prediction" is wrong.
2. P02 Muravyev: organizational experiment and claims-register/payment indicators; non-significant comparison (reported p=0.4789) but normative selection of an indicator for social/clinical/economic importance. Neither "empirically significant" nor "must be deleted" follows.
3. P03 Gurin: biomaterial synthesis/characterization, animal models, clinical deployment and differing posted/printed year. No generic "one experiment".
4. P04 Dudnik: 358 examined vs 288 treated, age/diagnosis strata and prenatal→later multidisciplinary processes. Do not confuse a treating team with a measurement method.
5. P05 Baldin: assay/material/marker/tissue controls and possible use claim are different typed assertions.

N01–N04 are real authorabstract PDFs with no usable text returned by direct Drive PDF extraction; N01 Lvova has also been independently visually rendered. Other three still require independent image readback. They are **admission/transport stop oracles**, not pseudo-content oracles. OCR requires a separately authorized derived carrier with its own provenance; source PDF is immutable.

## Evaluation design (after assets and gold are authorized)

Existing evaluation/README.md lists T1 frozen historical, T2 parallel raw-aware, T3 shared observations/drillback, T4 bounded Object↔Method reconciliation. Do not compare topologies until the same exact source SHA, full/abstract roles, method version, model/config, context budgets and stop conditions are recorded for each run. **Topology** is the independent variable; source and version are controls. If configurations or source completeness differ, explicitly invalidate that comparison.

Prerequisites: page- and passage-anchored manually adjudicated labels by Artikl/method-owner for each positive case, including counterfactual wrong claims and permitted Unknown; untouched independent blind source pre-registered separately. No S3A provider has authority to create methodological gold. Existing corpus is **never** counted as unseen.

Suggested first bounded pilot:
- T0 source/admission-only: four image-only negatives must stop as OCR_REQUIRED, even when study title and pairing metadata are available.
- T1 content differentiation: P01 must output method-specific feature selection, concrete algorithms, internal/external validation, and model-rejection basis without turning training accuracy into scientific success.
- T2 mixed epistemic justification: P02 must separate statistical conclusion from normative managerial inclusion of an indicator. A single decision may use both, but the evidence types are not interchangeable.
- T3 relational typing: P03–P05 force OBJECT/MATERIAL/PROCEDURE/INSTRUMENT/MEASUREMENT/POPULATION/CONTROL/RESULT/RECOMMENDATION separation.
- T4 version/contradiction: abstract vs dissertation must have independent read receipts, provenance, gap flags, disagreement/Unknown/APORIA when source conflicts, and no invisible fallback if mandatory authorabstract unreadable.

Measure per exact run: grounded claims, type-confusion counts, source evidence anchors retained, unsupported assertions, missing critical distinctions, APORIA validity, provenance/version integrity, source completeness, runtime/tokens/cost and owner correction burden. Collect both false-positive and false-negative errors. Human semantic reviewer must explicitly sign off; no auto-PASS from CI.

## Mechanical acceptance boundaries

CI can validate fixture uniqueness, SHA format, no duplicate case/study identifiers, all cases DEVELOPMENT_EXPOSED and declared admission modes. CI **cannot** validate PDF contents from this public metadata file nor certify a semantic oracle. Later authorized adapter must compare exact actual original bytes/sha/rights against private v4 manifest before opening source content.

Status vocabulary: FIXTURE_COMMITTED, CI_GREEN, SOURCE_READ, PAGE_ANCHORED, GOLD_ADJUDICATED, METHOD_ASSET_ADMITTED, S3_RUNTIME_EXECUTED, SCIENTIFICALLY_ACCEPTED are all distinct states. Today this change establishes only FIXTURE_COMMITTED (after exact GitHub receipt) and supporting private SOURCE_READ notes. No new original-method access or privileged publisher allowed. Security issues #44/#45 and AORUS #16 remain separate release barriers.
