# Data layout and policy

This repository treats the Lake Erken chlorophyll-fluorescence record as a high-frequency pelagic temporal reference. It is not literal daily Sentinel-2 surface chlorophyll truth and is not a cross-lake absolute Chl-a retrieval calibration for Lake Vombsjön.

## Directories

- `raw/`: an unchanged local copy of `SITES_CHL_ERK_20190417-20251130_L2_daily.csv`. Raw files are ignored by Git; place the source file here before running Phase 1.
- `interim/`: disposable intermediate files, ignored by Git. Phase 1 currently does not require any.
- `processed/`: reproducible, non-interpolated parsed data. `erken_daily_clean.csv` retains every input row, the original `CHLF` measurement, the original `PRESENCE_ICE` value, and derived calendar/provenance fields.

The canonical processed dataset is sorted chronologically but is not interpolated, smoothed, normalized, de-duplicated, or filtered for ice. Any duplicate dates are retained and reported; annual analysis stops rather than silently resolving them.

Derived fields include:

- `open_water`: `True` exactly where `PRESENCE_ICE == 0`. It is the preliminary domain for future Sentinel-2 reconstruction evaluation, but it is not equivalent to a valid Sentinel-2 observation date.
- `measurement_regime`: `pre_2023` for the 2019–2022 portion and `2023_onward` for the 2023–2025 portion. This broad provenance flag supports sensitivity analysis and is not a causal or instantaneous instrument-switch claim.

Annual outputs distinguish `complete_reference` (all daily rows) from `open_water`. Ice events remain valid reference features even when outside the preliminary satellite-observable domain.

In the annual table, `open_water_day_count` is the number of dates explicitly flagged open water. `open_water_duration_days` is the inclusive calendar span from the first to the last open-water observation; it can exceed the count if ice-flagged dates occur inside that span. Neither field infers conditions outside source coverage.

## Phase 2A Sentinel-2 SCL diagnostics

The external Sentinel-2 L2A archive is supplied to `scripts/03_erken_s2_scl_diagnostics.py` at runtime and is never copied into this repository. The script can generate two small processed tables:

- `processed/erken_s2_l2a_inventory.csv`: one row per discovered L2A product, including products with missing or unusable SCL files;
- `processed/erken_s2_scl_scene_summary.csv`: one row per product and candidate window size, preserving SCL classes 0–11 separately.

These tables describe SCL spatial context only. They contain no reflectance, NDCI, MCI, atmospheric-correction output, CHLF sampling, final usability flag, or synthetic acquisition dates. The full schema and status categories are documented in `docs/s2_scl_diagnostics.md`.

## Source and attribution

- Dataset: Lake Erken chlorophyll fluorescence, Sweden
- Provider: Swedish Infrastructure for Ecosystem Science (SITES)
- PID: `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`
- Licence: CC BY 4.0

Required acknowledgement:

> This study has been made possible by data provided by the Swedish Infrastructure for Ecosystem Science (SITES).

See `docs/data_provenance.md` for the source hash, duplicate-source audit, and methodological caveats.
