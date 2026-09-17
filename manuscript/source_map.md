# Manuscript result source map

This file maps the headline values in `manuscript.md` to committed evidence.
It is an audit aid, not a new analysis.

| Manuscript result | Authoritative committed source |
|---|---|
| 2,420 daily CHLF records and 1,950 open-water days | `results/tables/erken_qc_report.md` |
| 950 products, 926 dates, 307 usable dates | `docs/erken_s2_observation_mask.md` |
| 288 reconstruction inputs and annual sampling gaps | `docs/erken_temporal_sampling_join.md` |
| Actual-mask year-method metrics | `results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv` |
| 18 reference events and method-level recovery | `results/phase3/event_actual_mask/erken_phase3_actual_mask_event_metrics.csv` |
| 2,800 random masks and 5,746 consecutive windows | `results/phase4/synthesis/erken_phase_d_synthesis.md` |
| Primary controlled-gap summaries | `results/phase4/synthesis/erken_phase_d_random_year_method_deletion_summary.csv`; `results/phase4/synthesis/erken_phase_d_consecutive_year_method_duration_summary.csv` |
| Double-logistic parameter selection and sensitivity | `results/phase5/synthesis/erken_phase5_seapar_sensitivity_synthesis.md` and associated Phase 5 CSV files |
| Real Sentinel-2 NDCI and MCI results | `docs/Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md` and `results/phase6c/*.csv` |
| Radiometric offset and processing-baseline control | `docs/Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md`; `results/phase6d/processing_baseline/erken_s2_processing_baseline_gate.json` |

The manuscript reports the primary benchmark separately from the secondary
seasonal-event and double-logistic parameter sensitivity analyses. It does not
convert repeated artificial masks into independent lake-year replicates.
