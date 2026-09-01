# TIMESAT × Sentinel-2 × chlorophyll: reliability limits of temporal reconstruction in inland waters

This repository supports an RSE-oriented study asking: **Which seasonal characteristics of chlorophyll-sensitive Sentinel-2 time series can be reconstructed reliably under irregular observation and cloud-gap conditions, and where do temporal reconstruction methods fail?**

Lake Erken is the dense-reference development and future year-blocked calibration domain. Its daily SITES chlorophyll-fluorescence record is treated as a high-frequency pelagic chlorophyll reference—not literal daily Sentinel-2 surface chlorophyll truth and not an absolute cross-lake Chl-a retrieval calibration. Lake Vombsjön is reserved for later locked external transfer and extreme-regime stress testing after temporal settings have been frozen using Erken.

## Implemented scope

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

Phase 2A additionally provides a portable Sentinel-2 L2A Scene Classification Layer (SCL) diagnostic workflow for the Erken reference coordinate (`59.84029° N`, `18.625827° E`, EPSG:4326). It discovers unpacked L2A products, reads each real SCL geotransform and CRS, locates the station pixel, and reports raw SCL class counts/fractions for centered 1×1, 3×3, 5×5, 7×7, and 11×11 neighborhoods. A separate inventory records products with missing, ambiguous, unreadable, or spatially non-overlapping SCL rasters.

Phase 2A-2 validates and analyzes the committed real-server outputs over the Erken reference-record overlap. The evidence supports a 3×3 primary SCL neighborhood, with 1×1 and 5×5 retained as spatial sensitivity cases. Reproducible window, year, month, platform, baseline, transition, central-pixel, and inventory-QC tables plus five diagnostic figures document this choice. This freezes spatial support only, not a water/bad-SCL usability threshold or final acquisition mask.

Phase 2A-3 freezes the SCL usability rule and the temporal observation unit. A 3×3 product passes with at most one obvious-bad pixel, at least eight water pixels, a centre that is not obvious bad, no persistent non-water pixel, and no class-2 pixel. Same-day products remain available for provenance, but the temporal mask contains one row per calendar date and a date is usable when any product passes. The primary interval contains 950 products on 926 dates; 313 products pass and produce 307 unique usable dates. Compact rule and 1×1/5×5 spatial sensitivity analyses support the decision without using CHLF or reconstruction outcomes.

Deliberately not implemented through Phase 2A-3: Sentinel-2 reflectance or chlorophyll indices, atmospheric-correction selection, CHLF sampling at satellite dates, TIMESAT, GAM, linear interpolation, parameter optimization, reconstruction gap experiments, leave-one-year-out reconstruction, or Vombsjön transfer.

The canonical reference retains every observation, including ice periods. The main future reconstruction-evaluation domain is `open_water`, defined only by `PRESENCE_ICE == 0`. It is a preliminary physical-observability domain—not a set of valid Sentinel-2 acquisitions. Phase 2A-3 separately supplies an SCL-based cloud/shadow/cirrus/snow and local-water-context mask. Glint, atmospheric-correction, shoreline, reflectance, and retrieval-quality criteria remain future work.

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

The Phase 2A SCL workflow requires `rasterio` and `pyproj`; both are declared project dependencies. Actual Sentinel-2 SAFE/JP2 archives remain external runtime inputs and must not be committed.

## Run Phase 1.1

From the repository root:

```bash
python scripts/01_erken_qc.py
python scripts/02_erken_season_summary.py
pytest
```

The first script writes the canonical non-interpolated daily CSV, QC table/report, and portable run metadata. The second writes annual, peak-sensitivity, complete-versus-open-water peak, and measurement-regime tables plus figures. Configuration is explicit in `config/`.

## Run Phase 2A SCL diagnostics

After syncing this repository to the server, run from the repository root:

```bash
python scripts/03_erken_s2_scl_diagnostics.py \
  --input-root /path/on/server/to/Sentinel2/L2A \
  --output data/processed/erken_s2_scl_scene_summary.csv \
  --inventory-output data/processed/erken_s2_l2a_inventory.csv
```

The server root is supplied only at runtime and is never written to either CSV. Multiple products on the same date remain separate. Running on an empty archive writes header-only tables; it does not invent missing acquisition dates. See `docs/s2_scl_diagnostics.md` for supported layouts, output fields, status semantics, and remaining server checks.

## Run Phase 2A-2 SCL spatial-window analysis

After committing the two real-server CSV outputs, run locally from the repository root:

```bash
python scripts/04_erken_s2_scl_roi_analysis.py
```

The script validates the inventory and scene/window schemas and their cross-table consistency before writing results. See `docs/erken_s2_scl_roi_diagnostic.md` for the analysis rules, results, 3×3 recommendation, and limitations.

## Run Phase 2A-3 SCL observation-mask analysis

Run locally from the repository root using the committed Phase 2A inputs:

```bash
python scripts/05_erken_s2_observation_mask.py
```

The script validates the versioned rule configuration, builds product-level
3×3 QC variables, evaluates the compact pre-specified rule set, resolves
same-day products deterministically, performs the frozen 1×1/5×5 sensitivity
check, and writes the one-row-per-date mask. See
`docs/erken_s2_observation_mask.md` for the selection evidence and limitations.

## Outputs

- `data/processed/erken_daily_clean.csv`: chronological canonical data with `date`, `year`, `doy`, original `CHLF`, original `PRESENCE_ICE`, derived `ice_flag`, `open_water`, and `measurement_regime`.
- `results/tables/erken_qc_summary.csv`: machine-readable QC metrics.
- `results/tables/erken_qc_report.md`: short human-readable QC report.
- `results/tables/erken_year_summary.csv`: complete-reference and open-water annual summaries, including open-water boundaries and truncation status.
- `results/tables/erken_peak_sensitivity.csv`: exploratory peak counts and detected dates across prominence thresholds.
- `results/tables/erken_complete_vs_openwater_peak.csv`: annual complete-reference versus open-water observed maxima.
- `results/tables/erken_measurement_regime_summary.csv`: descriptive distributions of annual open-water metrics within broad provenance regimes.
- `results/tables/erken_run_metadata.json`: source, environment, configuration, timestamp, and run-time Git metadata.
- `results/figures/`: Phase 1 and Phase 2A-2 diagnostics in high-resolution PNG and vector PDF.
- `data/processed/erken_s2_scl_scene_summary.csv`: real server-derived long table with one row per product and diagnostic neighborhood size.
- `data/processed/erken_s2_l2a_inventory.csv`: real server-derived product inventory distinguishing product absence from SCL processing status.
- `results/tables/erken_s2_scl_window_summary.csv`: principal primary-overlap statistics for each candidate window.
- `results/tables/erken_s2_scl_window_year_summary.csv`: annual window diagnostics.
- `results/tables/erken_s2_scl_window_stratified_summary.csv`: month, platform, and processing-baseline diagnostics.
- `results/tables/erken_s2_scl_window_transition_summary.csv`: paired adjacent-window changes.
- `results/tables/erken_s2_scl_central_pixel_class_frequency.csv`: primary-overlap station-centre SCL frequencies.
- `results/tables/erken_s2_scl_window_outside_reference_summary.csv`: separate pre/post-reference summaries.
- `results/tables/erken_s2_scl_inventory_qc_summary.csv`: archive, validity, duplicate, platform, baseline, resolution, and grid checks.
- `data/processed/erken_s2_observation_mask.csv`: frozen date-level Sentinel-2 availability mask with one row per primary-interval inventory date.
- `results/tables/erken_s2_scl_product_qc.csv`: product-level frozen 3×3 SCL counts, fractions, centre flags, and final-rule outcome.
- `results/tables/erken_s2_scl_3x3_state_frequency.csv`: observed discrete nine-pixel SCL state frequencies.
- `results/tables/erken_s2_scl_qc_rule_sensitivity.csv`: product/date retention and temporal-gap summaries for every configured rule.
- `results/tables/erken_s2_scl_qc_rule_year_summary.csv`: annual candidate and usable-date counts by rule.
- `results/tables/erken_s2_same_day_product_resolution.csv`: complete provenance and deterministic resolution for multi-product dates.
- `results/tables/erken_s2_scl_spatial_rule_sensitivity.csv`: 1×1, 3×3, and 5×5 checks for the strict, preferred, and relaxed rules.

## Provenance, licensing, and reproducibility

The Erken dataset is provided by the Swedish Infrastructure for Ecosystem Science (SITES), PID `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`, under CC BY 4.0. Required acknowledgement:

> This study has been made possible by data provided by the Swedish Infrastructure for Ecosystem Science (SITES).

The repository code is covered by the root `LICENSE`; SITES data retain their own licence and attribution requirements. See `docs/data_provenance.md` for methodological caveats and the duplicate-source audit, `docs/experiment_design.md` for the planned architecture, and `docs/decisions.md` for binding design choices.

Reproducibility principles are: immutable raw inputs, a recorded SHA256, strict and explicit parsing, no silent interpolation/filtering/de-duplication, portable repository-relative provenance, configuration outside analysis functions, year/season as the future validation unit, code-generated small derived outputs, and testable reusable modules rather than notebooks.
