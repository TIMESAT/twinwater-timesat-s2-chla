# INTERNAL — DO NOT INCLUDE IN SUBMISSION

Provenance map for the Supplementary Information. The scientific SI file
(`supplementary_information_v1.0.md`) contains no repository paths; this file
records where each item comes from. All sources are committed repository files.
No SI item depends on the untracked Vombsjön daily-prediction CSV.

| SI item | Authoritative repository files |
|---|---|
| Table S1 | `results/phase6c/erken_s2_chlf_association_summary.csv`; `results/phase6c/erken_s2_chlf_loyo_summary.csv`; `results/phase6d/processing_baseline/erken_s2_processing_baseline_gate.json` (S1.3 baseline text) |
| Table S2 | `results/reliability_synthesis/v1.0/erken_reliability_actual_mask_equal_year_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_actual_mask_paired_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_actual_mask_leave_one_year_out_stability.csv` (with `..._leave_one_year_out.csv`, `..._leave_one_year_out_paired.csv`); `results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv` (annual bias); `results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv` (outer-fold spline values) |
| Table S3 | `results/reliability_synthesis/v1.0/erken_reliability_random_equal_year_deletion.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_duration_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_continuous_associations_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_activity_tertile_cuts.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_activity_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_peak_containment_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_observations_removed_summary.csv`; `docs/Reconstruction_Analysis_Contract_v1.0.1.md` §10 (S3.5 implementation) |
| Table S4 | `results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_equal_year_summary.csv`; `results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv`; `results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_peak_metrics.csv`; `results/reliability_synthesis/v1.0/erken_reliability_double_logistic_cv_actual_mask_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_event_equal_year_summary.csv` and `results/phase3/event_actual_mask/erken_phase3_actual_mask_event_year_method_summary.csv` (S4.5); `docs/Seasonal_Event_Detection_and_Matching_Protocol_v1.0.md`; `docs/Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md` |
| Table S5 | `results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv` (all 162 rows; built by `scripts/51_build_supplementary_table_s5.py`); `results/vombsjon/satellite_input_audit/v1.2/vombsjon_satellite_input_audit_manifest.json` (polygon area 247766.33349609375 m², 6 vertices, eligibility counts); `results/vombsjon/satellite_input_audit/v1.2/vombsjon_field_sampling_area_provenance.csv`; `results/vombsjon/satellite_input_audit/v1.2/vombsjon_field_gps_3x3_sensitivity.csv` (S5.4); `results/vombsjon/field_input_audit/v1.0/vombsjon_field_input_audit_report.md` |
| Figure S1 | `results/tables/erken_s2_scl_spatial_rule_sensitivity.csv` (plotted); `results/tables/erken_s2_scl_qc_rule_sensitivity.csv`, `results/tables/erken_s2_scl_qc_rule_year_summary.csv` (context); built by `scripts/50_build_supplementary_figures.py` |
| Figure S2 | `results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv`; built by `scripts/50_build_supplementary_figures.py` |
| Figure S3 | `results/reliability_synthesis/v1.0/erken_reliability_random_equal_year_deletion.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_peak_containment_summary.csv`; `results/reliability_synthesis/v1.0/erken_reliability_consecutive_continuous_associations_summary.csv`; built by `scripts/50_build_supplementary_figures.py` |

Provenance notes:
- Scripts 50 and 51 perform no fitting, recomputation or inference; they read committed tables and plot or reformat values.
- Script number 32 is already used (`scripts/32_validate_manuscript.py`), so the supplementary scripts use the next unused numbers, 50 and 51.
- Table S4C Erken default-DL intervals come from the paired cross-validation summary; they differ slightly from the primary summary used in Table S2A because of separate resample sub-seeds, while point estimates are identical.
- Vombsjön morphometry (S5.1) was checked against Rabow et al. (2025).
- Dryad dataset version and licence remain unverified (repository STATUS "To verify").
