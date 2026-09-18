# Project status

**Status date:** 2026-09-18

**Evidence baseline reviewed:** repository `main` at `a507c27`

**Planning authority:**
[`Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`](Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md)

This is the current progress ledger for the broader two-lake project. It does
not change the active master or any frozen protocol. The repository's current
scientific manuscript is an **Erken-only completed draft**. That draft is not
evidence that the master plan's reliability synthesis, second freeze, or
Vombsjön transfer has been completed.

## Current boundary

- Completed evidence in this repository covers Lake Erken through the primary
  reconstruction benchmark, controlled-gap results, supplementary event and
  double-logistic sensitivity analyses, real Sentinel-2 index–CHLF analysis,
  processing-baseline audit, and an Erken manuscript package.
- No Vombsjön data or results are committed in this repository, and the Erken
  synthesis records explicitly state that Vombsjön was not inspected.
- The original two-lake master remains active. Its remaining core path is the
  final reliability synthesis, an Erken-only second freeze, the Vombsjön data
  audit, and locked transfer validation.

## Completed

| Work package | Completion evidence | Scope note |
|---|---|---|
| Scientific governance and first freeze | [`Reconstruction_Analysis_Contract_v1.0.1.md`](Reconstruction_Analysis_Contract_v1.0.1.md), versioned configs, and Phase 3 preflight | Primary Erken rules frozen before the first performance run. |
| Erken reference QC and seasonal characterization | [`data/processed/erken_daily_clean.csv`](../data/processed/erken_daily_clean.csv), [`results/tables/`](../results/tables/), and [`data_provenance.md`](data_provenance.md) | 2,420 daily records; raw source is external/ignored. |
| Erken Sentinel-2 SCL inventory, spatial rule, date mask, and temporal join | [`data/processed/`](../data/processed/) and the Phase 2 documentation | 926 inventory dates, 307 usable dates, 288 frozen reconstruction inputs. |
| Primary Erken actual-mask benchmark | [`results/phase3/actual_mask/`](../results/phase3/actual_mask/) | Linear, frozen-default double logistic, and LOYO-selected smoothing spline were run for seven years. |
| Supplementary seasonal-event analysis | [`Seasonal_Event_Detection_and_Matching_Protocol_v1.0.md`](Seasonal_Event_Detection_and_Matching_Protocol_v1.0.md) and [`results/phase3/event_actual_mask/`](../results/phase3/event_actual_mask/) | Secondary/exploratory because the protocol followed inspection of global-maximum results. |
| Controlled random-deletion and consecutive-gap experiments | [`results/phase4/`](../results/phase4/) | 2,800 random masks and 5,746 consecutive windows completed with passing audits. |
| Descriptive Erken Phase D synthesis | [`erken_phase_d_synthesis.md`](../results/phase4/synthesis/erken_phase_d_synthesis.md) | Descriptive only; it explicitly did not choose a final inferential model, universal threshold, or transfer setting. |
| Double-logistic `p_seapar` sensitivity | [`Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md`](Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md) and [`results/phase5/`](../results/phase5/) | Secondary sensitivity reached its hard human-review gate; no Vombsjön inspection. |
| Erken real Sentinel-2 observation layer | [`results/phase6a/`](../results/phase6a/) and [`results/phase6b/`](../results/phase6b/) | L1C, official L2A, and ACOLITE extraction/QA plus frozen 6/9 observation selection. |
| Erken exact-date Sentinel-2 index–CHLF analysis | [`Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md`](Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md) and [`results/phase6c/`](../results/phase6c/) | MCI carried moderate but incomplete information; no uniquely superior processor was selected. |
| Processing-baseline audit | [`Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md`](Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md) and [`results/phase6d/processing_baseline/`](../results/phase6d/processing_baseline/) | Empirical L1C/L2A harmonization was not identifiable; Phase 6C outputs remained unchanged. |
| Erken manuscript package | [`manuscript/README.md`](../manuscript/README.md), [`manuscript/manuscript.md`](../manuscript/manuscript.md), and [`manuscript/manuscript_manifest.json`](../manuscript/manuscript_manifest.json) | Complete scientific draft for Erken only; 34 headline checks passed and the stored test record reports 407 passed/7 external-runtime skips. |

## Original-plan pending

These items already belong to the active master. They are not new review
suggestions.

1. **Complete the metric-specific reliability synthesis.** The controlled-gap
   data and descriptive summaries exist, but the master calls for an empirical
   reliability envelope with year-aware uncertainty and explicit scope limits.
   The Phase D and Phase 5 syntheses explicitly stop before a final inferential
   model or transfer decision.
2. **Perform the second Erken-only freeze before Vombsjön.** Select and record
   the settings/workflow carried forward, retain the frozen defaults and
   sensitivities with their correct labels, and create the dated
   machine-readable transfer-freeze manifest required by the contract.
3. **Complete the Vombsjön raw satellite/matchup audit.** Establish a governed
   observation inventory, matchup provenance, spatial extraction, QC, and the
   disposition of unresolved coordinates before performance is inspected.
4. **Execute the locked Vombsjön transfer.** Evaluate withheld Sentinel-2
   observations first, then use sparse field Chl-a only as the complementary
   ecological-consistency check, with no Vomb-driven retuning.
5. **Integrate the two-lake project evidence.** After the locked transfer,
   update the overall scientific synthesis, reproducibility package, and
   manuscript claims. The present Erken manuscript remains a valid scoped
   artifact and must not be described as the completed two-lake study.

## Necessary corrections

The accepted necessary correction in this documentation change is governance
alignment: the former README and experiment-design status stopped at Phase 3
pre-performance even though committed Phase 3–6 results and an Erken
manuscript now exist. The repository entry points have been aligned to the
committed evidence without modifying frozen scientific files. No additional
scientific correction has been accepted. Any future proposed correction must
remain labelled as a proposal until it passes the change-control rule in
[`AGENTS.md`](../AGENTS.md).

## To verify before the pending work

- Whether each external Vombsjön source listed in
  [`DATA_INVENTORY.md`](DATA_INVENTORY.md) is currently available, is the
  intended version, and has adequate licence/provenance and checksums.
- The content and resolution of the reported Vombsjön coordinate flags for
  2020-06-10 and 2020-06-24. Do not silently correct them.
- Availability and identity of the external Vombsjön Sentinel-2 archive and
  any atmospheric-correction products required by the future locked audit.
- Whether the external Introduction draft supplied outside the repository is
  to remain a historical planning reference or be reconciled with the current
  repository manuscript. It is not currently the canonical manuscript source.
- Whether the current Erken-only manuscript is intended as a standalone paper
  or as an interim/scoped manuscript within the larger two-lake plan. No
  repository evidence resolves that publication decision.
- `config/project.yaml` retains a historical Phase 2A label. It is preserved
  as configuration/history and is not a current progress authority; changing
  it would require a separately authorized configuration decision.

## Optional enhancements

The master explicitly says these are not required for Paper 1. They are not
approved tasks unless a later decision adopts them:

- Landsat/HLS integration or additional lakes;
- a larger reconstruction model zoo, including image-scale DINEOF/DINCAE;
- a broad atmospheric-correction factorial comparison;
- additional machine-learning Chl-a retrieval models;
- mapped/pixel-scale reconstruction or catchment-causality analysis; and
- any review suggestion not yet classified and accepted under the triage rule
  in [`AGENTS.md`](../AGENTS.md).
