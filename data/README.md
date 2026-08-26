# Data layout and policy

This repository treats the Lake Erken chlorophyll-fluorescence record as a high-frequency pelagic temporal reference. It is not literal daily Sentinel-2 surface chlorophyll truth and is not a cross-lake absolute Chl-a retrieval calibration for Lake Vombsjön.

## Directories

- `raw/`: an unchanged local copy of `SITES_CHL_ERK_20190417-20251130_L2_daily.csv`. Raw files are ignored by Git; place the source file here before running Phase 1.
- `interim/`: disposable intermediate files, ignored by Git. Phase 1 currently does not require any.
- `processed/`: reproducible, non-interpolated parsed data. `erken_daily_clean.csv` retains every input row, the original `CHLF` measurement, the original `PRESENCE_ICE` value, and derived calendar/ice fields.

The canonical processed dataset is sorted chronologically but is not interpolated, smoothed, normalized, de-duplicated, or filtered for ice. Any duplicate dates are retained and reported; annual analysis stops rather than silently resolving them.

## Source and attribution

- Dataset: Lake Erken chlorophyll fluorescence, Sweden
- Provider: Swedish Infrastructure for Ecosystem Science (SITES)
- PID: `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`
- Licence: CC BY 4.0

Required acknowledgement:

> This study has been made possible by data provided by the Swedish Infrastructure for Ecosystem Science (SITES).

See `docs/data_provenance.md` for the source hash, duplicate-source audit, and methodological caveats.
