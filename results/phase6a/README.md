# Phase 6A — Erken real Sentinel-2 L1C / official ESA L2A observation pilot

**Status of this namespace: real-data QA-only run completed; human freeze of
the final observation-validity decisions remains pending.**

This directory is the isolated Phase 6A output namespace. Phase 3, 4 and 5
outputs are never written here and are never modified by this pilot; the
pipeline refuses to write outside `results/phase6a/`.

## Completed real-data run

The real Sentinel-2 SAFE archive was processed on the Linux/HPC server. The
committed run completed at `2026-09-17T12:02:57Z` and produced:

- 926 candidate calendar dates;
- 307 frozen representative L2A dates;
- 306 exact L1C/L2A pairs and one ambiguous L1C pairing;
- 1,233 product extraction rows;
- 6,165 spatial-sensitivity rows, covering five nested windows per product;
- 658 explicit failure/audit rows; and
- 22,070 native QA inventory rows.

The authoritative processing identity, software versions and counts are in
[`erken_real_s2_pilot_provenance.json`](erken_real_s2_pilot_provenance.json).
The interpreted QA record, filtering sequence and remaining human decisions
are documented in
[`Erken_Phase6A_QA_Review_Record_2026-09-17.md`](../../docs/Erken_Phase6A_QA_Review_Record_2026-09-17.md).

## Real-data run

On the Linux server, from
`/projects/eko/fs7/pers/ZC/Core/Github/twinwater-timesat-s2-chla`:

```bash
python scripts/26_erken_phase6a_real_s2_pilot.py \
  --l1c-root /path/to/Erken/L1C \
  --l2a-root /path/to/Erken/L2A \
  --output-root results/phase6a \
  --require-real-archive
```

The two archive roots are runtime inputs; they are never committed and never
appear in any output. `ERKEN_S2_L1C_ROOT` and `ERKEN_S2_L2A_ROOT` can be used
instead of the flags.

## Outputs of the real run

| File | Content |
|---|---|
| `erken_l1c_l2a_pairing_audit.csv` | every frozen candidate date, including pairing failures |
| `qa/erken_l1c_l2a_native_qa_inventory.csv` | native QA assets actually present per product |
| `erken_real_s2_product_extraction_master.csv` | per-product reflectance/QA/index master |
| `erken_real_s2_date_observation_master.csv` | date-level L1C/L2A observation master |
| `qa/erken_real_s2_qa_attrition.csv` | QA-only attrition at 9/9, ≥8/9, ≥6/9, ≥5/9 |
| `qa/erken_real_s2_qa_attrition_annual.csv` | the same attrition by year |
| `qa/erken_real_s2_baseline_platform_qa_audit.csv` | attrition by processing baseline and platform |
| `erken_real_s2_pilot_provenance.json` | portable provenance manifest |
| `erken_real_s2_pilot_failures.csv` | explicit failure/run audit |
| `spatial_sensitivity/erken_real_s2_product_window_indices.csv` | per-product B4/B5/B6, NDCI and MCI summaries at 1×1, 3×3, 5×5, 7×7 and 11×11 |
| `spatial_sensitivity/erken_real_s2_window_summary.csv` | descriptive availability by product level, metric and window |
| `spatial_sensitivity/erken_real_s2_window_annual_summary.csv` | descriptive availability by product level, year, metric and window |
| `spatial_sensitivity/erken_l1c_l2a_window_comparison.csv` | paired descriptive L1C-minus-L2A differences; no scientific ranking |

## Stopping rule

The first real-data run stops after these QA/availability outputs. It does not
inspect CHLF, does not compute index-versus-field performance, does not rank
L1C against L2A, and does not run TIMESAT. The human must review the attrition
evidence and freeze the final minimum valid-pixel threshold before any
field-matchup analysis begins.

The five-window products are secondary/exploratory. The original 3×3 master,
date-level master and attrition tables remain the primary Phase 6A outputs and
are not replaced or retuned by this sensitivity analysis.

Governance: `docs/Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md`
(DRAFT) and `config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml` (DRAFT).
