# Project status

**Status date:** 2026-09-28

**Evidence baseline reviewed:** repository commit
`92f01b476f7c816cbf62f78ba8eb89cc4faa74ee` (the canonical Vombsjön satellite
input audit v1.2 outputs), which builds on `d8b4a8d` (the preserved v1.1
outputs) and `b3aeb4e782d74f7b6ce7d08bad28e61ee9c66a4f` (the latest `main` when
the Vombsjön field-input audit began)

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
- The four supplied Vombsjön field/reference files are committed with
  byte-level checksums and a versioned field-input audit. **The Vombsjön raw
  satellite/product and matchup audit is complete at v1.2**, which is the
  current canonical satellite input audit. The corrected ACOLITE processing
  completed on the server, the audit ran against it, and all 15 canonical
  outputs are committed under
  [`results/vombsjon/satellite_input_audit/v1.2/`](../results/vombsjon/satellite_input_audit/v1.2/)
  at result commit `92f01b476f7c816cbf62f78ba8eb89cc4faa74ee`. The audit itself
  executed repository code at `96325a5951e9775c04c6dbf4544f28405d23dd87`. The
  L1C, official L2A and ACOLITE archives remain repository-external runtime
  inputs, but they have been read and inventoried and the derived audit
  products are committed and citable.
- **v1.1 remains immutable historical provenance.** Its 15 outputs under
  [`results/vombsjon/satellite_input_audit/v1.1/`](../results/vombsjon/satellite_input_audit/v1.1/)
  are preserved unchanged. They were produced from the earlier ACOLITE archive
  processed with `ancillary_data=False`, while
  [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json)
  already required `ancillary_data=True`. v1.2 audits a reprocessed archive
  that conforms.
- **v1.2 was an execution and provenance correction, not a scientific
  amendment.** Every scientific rule is byte-identical between v1.1 and v1.2,
  no frozen value was rewritten, and no scientific parameter was retuned. No
  Vombsjön performance was used to make the ancillary-data correction: the
  correction was forced by a pre-existing frozen requirement, not chosen from
  any result. The ancillary-data correction changed ACOLITE radiometric/MCI
  values while leaving the frozen QC/eligibility structure, spatial support and
  observation counts unchanged; all 34 manifest count fields are identical
  between v1.1 and v1.2.
- No Vomb reconstruction has been run. No withheld-observation performance
  analysis, reconstruction metric, regression, correlation or processor
  selection has been performed, and no Vomb performance has been inspected.
  The committed v1.2 manifest records all of these as `false`.
- The original two-lake master remains active. With the input audit closed at
  v1.2, the next stage is the **locked-transfer preflight and execution-gate
  closure**. The execution gates are **not** yet closed. Only after all gates
  pass does the **locked Vombsjön transfer / withheld-observation performance**
  stage begin. Completing the input audit does not by itself authorize
  performance execution, and Vomb performance execution is not yet authorized.

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
| Vombsjön field-source intake and audit | [`vombsjon_field_input_audit_report.md`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_input_audit_report.md), [`vombsjon_field_source_manifest.csv`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_source_manifest.csv), and [`vombsjon_field_input_audit_manifest.json`](../results/vombsjon/field_input_audit/v1.0/vombsjon_field_input_audit_manifest.json) | Four supplied files are committed byte-preserved. The 54-row field table (2018/2019/2020 = 6/22/26) and 2019-2020 metadata cross-check pass. Two source longitude flags remain unresolved and retained. This work package completed field-material verification only; the satellite products were audited separately in the v1.1 satellite input audit below. |
| Double-logistic `p_seapar` sensitivity | [`Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md`](Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md) and [`results/phase5/`](../results/phase5/) | Secondary sensitivity reached its hard human-review gate; no Vombsjön inspection. |
| Erken real Sentinel-2 observation layer | [`results/phase6a/`](../results/phase6a/) and [`results/phase6b/`](../results/phase6b/) | L1C, official L2A, and ACOLITE extraction/QA plus frozen 6/9 observation selection. |
| Erken exact-date Sentinel-2 index–CHLF analysis | [`Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md`](Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md) and [`results/phase6c/`](../results/phase6c/) | MCI carried moderate but incomplete information; no uniquely superior processor was selected. |
| Processing-baseline audit | [`Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md`](Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md) and [`results/phase6d/processing_baseline/`](../results/phase6d/processing_baseline/) | Empirical L1C/L2A harmonization was not identifiable; Phase 6C outputs remained unchanged. |
| Erken manuscript package | [`manuscript/README.md`](../manuscript/README.md), [`manuscript/manuscript.md`](../manuscript/manuscript.md), and [`manuscript/manuscript_manifest.json`](../manuscript/manuscript_manifest.json) | Complete scientific draft for Erken only; 34 headline checks passed and the stored test record reports 407 passed/7 external-runtime skips. |
| Vombsjön raw satellite/product and matchup audit v1.1 (superseded, preserved) | [`Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md`](Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md), [`config/vombsjon_satellite_input_audit_v1.1.yaml`](../config/vombsjon_satellite_input_audit_v1.1.yaml), and the 15 committed outputs under [`results/vombsjon/satellite_input_audit/v1.1/`](../results/vombsjon/satellite_input_audit/v1.1/) | Completed 2026-09-23 against the earlier ACOLITE archive processed with `ancillary_data=False`. Retained unchanged as immutable historical provenance; superseded as the canonical audit by v1.2. Its scientific rules and the protocol remain those v1.2 inherits. |
| Vombsjön raw satellite/product and matchup audit v1.2 (**current canonical**) | [`Vombsjon_Satellite_Input_Audit_Protocol_v1.2.md`](Vombsjon_Satellite_Input_Audit_Protocol_v1.2.md), [`config/vombsjon_satellite_input_audit_v1.2.yaml`](../config/vombsjon_satellite_input_audit_v1.2.yaml), [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json), and the 15 committed outputs under [`results/vombsjon/satellite_input_audit/v1.2/`](../results/vombsjon/satellite_input_audit/v1.2/) | Run against the corrected ACOLITE archive (`ancillary_data=True`); result commit `92f01b476f7c816cbf62f78ba8eb89cc4faa74ee`, executed with repository code `96325a5951e9775c04c6dbf4544f28405d23dd87`. 1,509 L1C, 1,510 official L2A and 1,505 ACOLITE products inventoried; 1,466 exact-unique L1C/L2A pairs; 4,629 extraction rows; 4,524 fixed-target, 75 field-polygon and 30 GPS-3×3 observation rows; 4,296 same-day rows; 162 date-level matchup rows; 48 recorded extraction failures. All 43 freeze cross-checks agree. Fixed 3×3 temporal target MCI-eligible on 422 (L1C), 435 (L2A), 349 (ACOLITE); same-day MCI available on 408/419/335; field-polygon and exact-date matchup eligible on 9/9/7; GPS-3×3 sensitivity eligible on 4/4/3. Polygon support a constant 615 target-grid pixels. Input audit only: no reconstruction, performance, regression, correlation or processor selection. |

## Original-plan pending

These items already belong to the active master. They are not new review
suggestions.

1. **Close the locked-transfer preflight and execution gates.** This is the
   next stage. The satellite input audit is complete at v1.2, so the
   `execution_gates.before_vomb_performance` items in
   [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json)
   must now be evidenced and closed against the committed v1.2 outputs,
   including verification that the TIMESAT runtime matches the frozen snapshot
   and that the ACOLITE identity the freeze declares is reconciled with what
   the run files actually state. **The gates are not yet closed.** A failed
   gate stops the work rather than changing a setting or silently falling back
   to another product.
2. **Execute the locked Vombsjön transfer / withheld-observation
   performance.** Only after all gates pass; it is not yet authorized.
   Evaluate withheld Sentinel-2 observations first, then use sparse field
   Chl-a only as the complementary ecological-consistency and proxy-validation
   check — never as daily truth — with no Vomb-driven retuning.
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

**Vombsjön external ACOLITE execution corrected at v1.2 (execution and
provenance correction; resolved).** The ACOLITE archive audited by v1.1 had
been produced with `ancillary_data=False`, while
[`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json)
already required `ancillary_data=True`; the external processing did not
conform to a freeze that predated it. The archive was reprocessed from the same
stable ACOLITE source commit `64a02ff386e2985eef68ae00198b38e04f3c4a1f` with
`ancillary_data=True`, and the v1.2 audit ran against it. The v1.2 manifest
verifies `ancillary_data=True`, `s2_target_res=20`, `dsf_aot_estimate=tiled`,
`l2r_export_geotiff=True` and `l2w_export_geotiff=True` from all 1,505
discovered ACOLITE scene files.

**No scientific parameter was retuned and no Vombsjön performance was used to
make the correction** — it was forced by the pre-existing frozen requirement.
The ancillary-data correction changed ACOLITE radiometric/MCI values while
leaving the frozen QC/eligibility structure, spatial support and observation
counts unchanged: all 34 manifest count fields are identical between v1.1 and
v1.2, while all 335 available ACOLITE same-day MCI values and all 7 available
exact-date ACOLITE field-matchup MCI values changed (mean |ΔMCI| ≈ 0.000424,
median ≈ 0.000266, maximum ≈ 0.004063). Whether the changed values are in any
sense better cannot be stated, because no Vomb performance has been inspected.

The v1.2 manifest records `repository_worktree_dirty = true`. This is a
recording artifact, not a scientific failure: the audit writes its output files
before the manifest queries `git status`, so the newly created untracked
outputs make the worktree appear dirty at manifest-construction time. The run
code identity is unambiguous (`96325a5951e9775c04c6dbf4544f28405d23dd87`) and
the canonical output commit is `92f01b476f7c816cbf62f78ba8eb89cc4faa74ee`. The
audit is not rerun merely to change this field.

**Vombsjön SAFE QA diagnostic counts, corrected after the first real v1.1 run
(diagnostic only; resolved).** A polygon target is read through an enclosing
square window (33×33 = 1089 pixels) while the observation uses only the 615
pixel centres inside the fixed polygon. `MCI_valid_pixel_count` was always
restricted to that support, but the SAFE native-QA layer counts were
whole-window counts, so a QA diagnostic could report up to 1089 against a
615-pixel support. ACOLITE QA counts were already support-restricted. Every
extraction row now carries both bases: the unchanged `qa_<layer>_count` plus
`qa_<layer>_count_in_support` / `_fraction_in_support`, support-restricted
hard-invalid aggregates, explicit pixel-basis columns, and ACOLITE
`*_in_support` aliases. These fields are **diagnostic only**: they are written
to the output row and nothing else, and no band validity, index validity or
eligibility decision reads them.

**The correction changed no scientific count and no eligibility result.** The
code change was strictly additive — commit `e7c84c8` records 118 insertions and
0 deletions in
[`vombsjon_satellite_audit.py`](../src/twinwater_timesat/vombsjon_satellite_audit.py) —
so no existing computation was altered and the added fields are write-only. The
clean rerun therefore reproduces the first run's scientific results and adds the
missing diagnostic basis. Band validity, MCI validity, the 2/3 polygon
fractional support rule, the fixed 3×3 6-of-9 rule, the fixed polygon, the
ACOLITE flag layout and the SAFE QA classification are all unchanged. The first
run's outputs were never committed, so this is a code-level guarantee rather
than a committed run-to-run diff.

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
  coordinates and QC flags are preserved. Do not silently correct them. Under
  the v1.1 rule these two dates contribute no coordinate to the fixed pelagic
  polygon's construction and receive no actual-GPS 3×3 sensitivity extraction,
  but they **remain eligible for the primary fixed-polygon field comparison**,
  because that polygon does not depend on the per-date coordinate. The fixed
  temporal target is unaffected on those dates.
- The formal datum/CRS terminology for the handheld N/E GPS records. Their
  degree/minute/second conversions and stored decimal coordinates were
  verified, but the source files have no machine-readable CRS declaration.
- The ACOLITE **textual version string** remains
  `not_verifiable_from_supplied_files`: no per-scene file declares it, so no
  literal version-string equality with the freeze can be claimed. The stable
  source-code identity is the Git commit
  `64a02ff386e2985eef68ae00198b38e04f3c4a1f`, which is unchanged, and that is
  what the execution-gate closure should check. The v1.2 audit did verify
  `ancillary_data=True`, `s2_target_res=20`, `dsf_aot_estimate=tiled`,
  `l2r_export_geotiff=True` and `l2w_export_geotiff=True` from all 1,505
  discovered scene files.
- The unresolved items the committed v1.2 manifest records remain open and are
  retained as documented limitations, not errors requiring repair and not
  reinterpreted: the 2 longitude-minute flags; the 31 field dates without an
  accepted measured GPS; the absence of an authoritative Vombsjön open-water
  geometry; field vertical representativeness; the GPS CRS declaration not
  independently verified; the unavailable field sampling clock time; the
  ACOLITE textual version not verifiable from the supplied scene files; the 44
  L2A products without a unique L1C pair; and the 4 ACOLITE scenes with
  NetCDF/L1R-only style output, which are explicitly recorded as unavailable
  with **no rhos GeoTIFF fallback used**.
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
