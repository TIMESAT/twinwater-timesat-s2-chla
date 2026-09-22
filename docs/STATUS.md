# Project status

**Status date:** 2026-09-18

**Evidence baseline reviewed:** repository starting commit
`b3aeb4e782d74f7b6ce7d08bad28e61ee9c66a4f` (the latest `main` when the
Vombsjön field-input audit began)

**Planning authority:**
[`Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`](Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md)

This is the current progress ledger for the broader two-lake project. It does
not change the active master or any frozen protocol. The repository's current
scientific manuscript is an **Erken-only completed draft**. The separate
versioned evidence now also completes the reliability synthesis and second
Erken-only freeze; neither artifact is evidence that the Vombsjön transfer has
been completed.

## Current boundary

- Completed evidence in this repository covers Lake Erken through the primary
  reconstruction benchmark, controlled-gap results, supplementary event and
  double-logistic sensitivity analyses, real Sentinel-2 index–CHLF analysis,
  processing-baseline audit, the versioned metric-specific reliability
  synthesis and interpretive correction, the second transfer freeze, and an
  Erken manuscript package.
- The four supplied Vombsjön field/reference files are now committed with
  byte-level checksums and a versioned field-input audit. The Vombsjön raw
  satellite/product and matchup audit is **implemented but not executed**: the
  external L1C, official L2A and ACOLITE roots exist on the server and remain
  repository-external runtime inputs, so no Vomb Sentinel-2 or
  atmospheric-correction product has yet been read, no audit output exists, and
  no Vomb reconstruction performance has been inspected.
- The original two-lake master remains active. Its remaining core path now
  begins with the Vombsjön raw satellite/product audit and governed matchup
  materialization, then continues to the locked transfer validation. The
  field-source audit alone does not authorize performance execution.

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
| Erken metric-specific reliability synthesis v1.0 | [`erken_reliability_report_v1.0.md`](../results/reliability_synthesis/v1.0/erken_reliability_report_v1.0.md), [`erken_reliability_synthesis_manifest_v1.0.json`](../results/reliability_synthesis/v1.0/erken_reliability_synthesis_manifest_v1.0.json), and associated CSV/figures | Completed from saved Erken results only. Uses year-first equal weighting, 10,000 whole-year paired cluster-bootstrap resamples, paired differences, leave-one-year-out re-summaries, and coverage-aware missingness strata. It does not execute the second freeze or inspect Vombsjön. |
| Reliability synthesis v1.0.1 interpretive correction | [`erken_reliability_report_v1.0.1.md`](../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md) and [`erken_reliability_corrigendum_manifest_v1.0.1.json`](../results/reliability_synthesis/v1.0.1/erken_reliability_corrigendum_manifest_v1.0.1.json) | Corrects leave-one-year-out tie/reversal language, replaces an unsupported denoising claim with a curve-smoothness description, and makes the retrospective/non-operational role of `A_gap` explicit. All v1.0 numerical files and checksums are unchanged. |
| Second Erken-only transfer freeze | [`Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md`](Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md), [`erken_vomb_transfer_freeze_v1.0.json`](../config/erken_vomb_transfer_freeze_v1.0.json), and [`erken_vomb_transfer_freeze_manifest_v1.0.json`](../results/transfer_freeze/v1.0/erken_vomb_transfer_freeze_manifest_v1.0.json) | Complete before Vomb input/performance inspection. Retains all three primary methods; fixes the final spline at `p_smooth=10`; keeps CV double logistic separate; freezes MCI/ACOLITE, QC, support, scaling, holdout, metric, uncertainty and failure rules. Synthetic holdout and TIMESAT affine-equivariance checks pass. |
| Vombsjön field-source intake and audit | [`vombsjon_field_input_audit_report.md`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_input_audit_report.md), [`vombsjon_field_source_manifest.csv`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_source_manifest.csv), and [`vombsjon_field_input_audit_manifest.json`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_input_audit_manifest.json) | Four supplied files are committed byte-preserved. The 54-row field table (2018/2019/2020 = 6/22/26) and 2019-2020 metadata cross-check pass. Two source longitude flags remain unresolved and retained. This completes field-material verification only; satellite products remain pending. |
| Double-logistic `p_seapar` sensitivity | [`Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md`](Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md) and [`results/phase5/`](../results/phase5/) | Secondary sensitivity reached its hard human-review gate; no Vombsjön inspection. |
| Erken real Sentinel-2 observation layer | [`results/phase6a/`](../results/phase6a/) and [`results/phase6b/`](../results/phase6b/) | L1C, official L2A, and ACOLITE extraction/QA plus frozen 6/9 observation selection. |
| Erken exact-date Sentinel-2 index–CHLF analysis | [`Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md`](Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md) and [`results/phase6c/`](../results/phase6c/) | MCI carried moderate but incomplete information; no uniquely superior processor was selected. |
| Processing-baseline audit | [`Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md`](Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md) and [`results/phase6d/processing_baseline/`](../results/phase6d/processing_baseline/) | Empirical L1C/L2A harmonization was not identifiable; Phase 6C outputs remained unchanged. |
| Erken manuscript package | [`manuscript/README.md`](../manuscript/README.md), [`manuscript/manuscript.md`](../manuscript/manuscript.md), and [`manuscript/manuscript_manifest.json`](../manuscript/manuscript_manifest.json) | Complete scientific draft for Erken only; 34 headline checks passed and the stored test record reports 407 passed/7 external-runtime skips. |

## Original-plan pending

These items already belong to the active master. They are not new review
suggestions.

1. **Complete the Vombsjön raw satellite/product and matchup audit.** Field
   source intake, checksums, row/date/depth/GPS verification and preservation of
   the two unresolved coordinate flags are complete. The audit workflow is now
   **implemented at v1.1 but not executed**: see
   [`Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md`](Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md),
   [`config/vombsjon_satellite_input_audit_v1.1.yaml`](../config/vombsjon_satellite_input_audit_v1.1.yaml),
   [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json)
   and [`scripts/41_vombsjon_satellite_input_audit.py`](../scripts/41_vombsjon_satellite_input_audit.py).
   No Vombsjön Sentinel-2 or ACOLITE product has been read and
   `results/vombsjon/satellite_input_audit/` holds no output. Running the entry
   point on the server with the real L1C, official L2A and ACOLITE roots
   establishes the Sentinel-2 observation inventory, product/scene provenance,
   the fixed pelagic field-validation polygon, fixed-target, polygon and
   GPS-sensitivity extraction, QC, ACOLITE identity/settings, coverage and
   same-day deduplication before performance is inspected. A failed gate stops
   rather than changes a setting or silently falls back to another product.
2. **Execute the locked Vombsjön transfer.** Evaluate withheld Sentinel-2
   observations first, then use sparse field Chl-a only as the complementary
   ecological-consistency check, with no Vomb-driven retuning.
3. **Integrate the two-lake project evidence.** After the locked transfer,
   update the overall scientific synthesis, reproducibility package, and
   manuscript claims. The present Erken manuscript remains a valid scoped
   artifact and must not be described as the completed two-lake study.

## Necessary corrections

**Vombsjön field-validation spatial support, amended before performance
inspection (Decision 026).** The v1.0 primary field-satellite comparison used
an actual-GPS 3×3 window with a nominal-point fallback, so the compared spatial
support moved between dates and differed in kind between dates with and without
a GPS record. v1.1 replaces it with one fixed pelagic convex-hull polygon used
identically on every field date, judged by a pre-specified two-thirds
fractional support rule; actual-GPS 3×3 becomes a secondary spatial
sensitivity, and the nominal-point fallback is removed from primary field
validation. The fixed nominal-station 3×3 temporal reconstruction target and
its 6-of-9 rule are unchanged. No Vombsjön result was inspected or used to
choose the polygon, its size or its validity threshold. The v1.0 freeze,
configuration and protocol are preserved unchanged; the v1.0 audit
configuration is deliberately no longer loadable.

The other accepted necessary correction in this work is interpretive, not
numerical.
Reliability report v1.0.1 states that the linear-interpolation peak-timing
advantage becomes a tie in some leave-one-year-out re-summaries but never
reverses; the spline-versus-default-double-logistic contrast genuinely takes
both signs. It also describes the spline as producing smoother reconstructed
curves, not as independently verified denoising, and identifies `A_gap` as an
Erken complete-reference-derived retrospective covariate rather than a known
operational Vomb input. The v1.0 report, results, figures and manifest remain
preserved and checksum-identical.

## To verify before the pending work

- The exact Dryad dataset version and package-wide licence for the committed
  CSV/XLSX/README. Their local identities and checksums are verified, but the
  supplied files do not establish those two repository-level facts. The paper
  PDF itself states CC BY 4.0.
- Whether the source longitude minute is `35` or `36` on 2020-06-10 and
  2020-06-24. The XLSX and CSV both contain `35`; the raw values, empty matchup
  coordinates and QC flags are preserved. Do not silently correct them. The
  satellite input audit therefore withholds field-location extraction on those
  two dates and records the flag as unresolved; the fixed temporal target is
  unaffected on those dates.
- The formal datum/CRS terminology for the handheld N/E GPS records. Their
  degree/minute/second conversions and stored decimal coordinates were
  verified, but the source files have no machine-readable CRS declaration.
- Identity of the external Vombsjön Sentinel-2 and ACOLITE archives. The
  operator reports that `S2L1C/T33UVB`, `S2L2A/T33UVB` and `ACOLITE_VOMBSJON`
  now exist under the server `TWIN_water` tree, but none of them is reachable
  from the repository working copy, so their contents, layout, product counts,
  date coverage and checksums are unverified. The audit discovers the ACOLITE
  layout at run time and records it rather than assuming it.
- Whether the frozen ACOLITE identity (workflow commit, ACOLITE source commit,
  version string, inland profile, 20 m, polygon clipping, ancillary data) is
  actually declared by the Vombsjön ACOLITE settings/`run.json` files. Anything
  the files do not state is reported as not verifiable rather than assumed.
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
