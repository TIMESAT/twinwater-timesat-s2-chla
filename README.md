# TIMESAT × Sentinel-2 × chlorophyll: reliability limits of temporal reconstruction in inland waters

This repository supports an RSE-oriented study asking: **Which seasonal characteristics of chlorophyll-sensitive Sentinel-2 time series can be reconstructed reliably under irregular observation and cloud-gap conditions, and where do temporal reconstruction methods fail?**

Lake Erken is the dense-reference development and future year-blocked calibration domain. Its daily SITES chlorophyll-fluorescence record is treated as a high-frequency pelagic chlorophyll reference—not literal daily Sentinel-2 surface chlorophyll truth and not an absolute cross-lake Chl-a retrieval calibration. Lake Vombsjön is reserved for later locked external transfer and extreme-regime stress testing after temporal settings have been frozen using Erken.

## Phase 1.1 scope

Implemented here:

- raw-data provenance and SHA256 verification;
- metadata-aware, strict CSV ingestion;
- preservation of original CHLF and ice values;
- date, duplicate, missingness, calendar, leap-year, CHLF, and ice QC;
- explicit `complete_reference` and `open_water` (`PRESENCE_ICE == 0`) domains;
- complete-reference and open-water annual summaries for 2019–2025;
- separate, unambiguous complete-reference and open-water annual global maxima;
- conservative open-water boundary-status fields distinct from calendar truncation;
- a broad, non-causal `measurement_regime` provenance flag (`pre_2023` / `2023_onward`);
- annual-level descriptive measurement-regime sensitivity summaries;
- exploratory `scipy.signal.find_peaks` sensitivity analysis with configured rules;
- diagnostic PNG and PDF figures;
- lightweight unit tests and simple run metadata.

Deliberately not implemented in Phase 1.1: TIMESAT, GAM, linear-interpolation experiments, parameter optimization, Sentinel-2 observation masks, any random/consecutive/phase-targeted gap experiment, leave-one-year-out reconstruction experiments, or Vombsjön transfer.

The canonical reference retains every observation, including ice periods. The main future reconstruction-evaluation domain is `open_water`, defined only by `PRESENCE_ICE == 0`. It is a preliminary physical-observability domain—not a set of valid Sentinel-2 acquisitions. Cloud, glint, atmospheric-correction, shoreline, and other satellite QC criteria remain future work.

## Setup

Python 3.11 or newer is required.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

The required raw file is:

`data/raw/SITES_CHL_ERK_20190417-20251130_L2_daily.csv`

Raw data are ignored by Git. The configured source SHA256 is checked before processing; no synthetic or interpolated substitute is created when the source is absent.

## Run Phase 1.1

From the repository root:

```bash
python scripts/01_erken_qc.py
python scripts/02_erken_season_summary.py
pytest
```

The first script writes the canonical non-interpolated daily CSV, QC table/report, and portable run metadata. The second writes annual, peak-sensitivity, complete-versus-open-water peak, and measurement-regime tables plus figures. Configuration is explicit in `config/`.

## Outputs

- `data/processed/erken_daily_clean.csv`: chronological canonical data with `date`, `year`, `doy`, original `CHLF`, original `PRESENCE_ICE`, derived `ice_flag`, `open_water`, and `measurement_regime`.
- `results/tables/erken_qc_summary.csv`: machine-readable QC metrics.
- `results/tables/erken_qc_report.md`: short human-readable QC report.
- `results/tables/erken_year_summary.csv`: complete-reference and open-water annual summaries, including open-water boundaries and truncation status.
- `results/tables/erken_peak_sensitivity.csv`: exploratory peak counts and detected dates across prominence thresholds.
- `results/tables/erken_complete_vs_openwater_peak.csv`: annual complete-reference versus open-water observed maxima.
- `results/tables/erken_measurement_regime_summary.csv`: descriptive distributions of annual open-water metrics within broad provenance regimes.
- `results/tables/erken_run_metadata.json`: source, environment, configuration, timestamp, and run-time Git metadata.
- `results/figures/`: five required diagnostics in high-resolution PNG and vector PDF.

## Provenance, licensing, and reproducibility

The Erken dataset is provided by the Swedish Infrastructure for Ecosystem Science (SITES), PID `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`, under CC BY 4.0. Required acknowledgement:

> This study has been made possible by data provided by the Swedish Infrastructure for Ecosystem Science (SITES).

The repository code is covered by the root `LICENSE`; SITES data retain their own licence and attribution requirements. See `docs/data_provenance.md` for methodological caveats and the duplicate-source audit, `docs/experiment_design.md` for the planned architecture, and `docs/decisions.md` for binding design choices.

Reproducibility principles are: immutable raw inputs, a recorded SHA256, strict and explicit parsing, no silent interpolation/filtering/de-duplication, portable repository-relative provenance, configuration outside analysis functions, year/season as the future validation unit, code-generated small derived outputs, and testable reusable modules rather than notebooks.
