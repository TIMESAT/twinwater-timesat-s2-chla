# Lake Erken data provenance

## Identity and scientific role

The Phase 1 source is **Lake Erken chlorophyll fluorescence, Sweden**, provided by the **Swedish Infrastructure for Ecosystem Science (SITES)**. Its role is a dense, high-frequency pelagic chlorophyll reference for developing and evaluating temporal reconstruction methods. It must not be described as literal daily Sentinel-2 surface Chl-a truth or used as cross-lake absolute Chl-a retrieval calibration for Vombsjön.

- PID: `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`
- Licence: CC BY 4.0
- Source period stated in the file: 2019-04-17 through 2025-11-30
- CHLF unit: µg L^-1
- Source filename: `SITES_CHL_ERK_20190417-20251130_L2_daily.csv`
- SHA256: `335a6bb464c59b0f70d5ab18277c590d033c291e2417049c95804cf5368d60d4`
- Size: 54,500 bytes

Required acknowledgement:

> This study has been made possible by data provided by the Swedish Infrastructure for Ecosystem Science (SITES).

## Local source selection and duplicate audit

The selected source was:

`/Users/zzcai/Downloads/SITES_CHL_ERK_20190417-20251130_L2_daily/SITES_CHL_ERK_20190417-20251130_L2_daily.csv`

Two additional credible candidates were found:

- `/Users/zzcai/Documents/GitHub/twinwater-timesat-s2-chla/SITES_CHL_ERK_20190417-20251130_L2_daily/SITES_CHL_ERK_20190417-20251130_L2_daily.csv`
- `/Users/zzcai/Downloads/TWIN_Water_RSE_Project_Active_v4/SITES_CHL_ERK_20190417-20251130_L2_daily.csv`

All three files were 54,500 bytes, shared the SHA256 above, and were confirmed byte-identical. The selected file was copied unchanged to `data/raw/`; the originals were not modified.

## Measurement and interpretation caveats

- Fluorescence is corrected using weekly manually sampled laboratory chlorophyll.
- Measurements were originally collected at higher (hourly) temporal frequency; the daily product reports the 00:00 observation to minimize non-photochemical quenching.
- Measurement configurations and locations changed during the record.
- The source describes a YSI profiler during spring–fall and, for 2019–2022, a YSI sonde under ice.
- From 2023 onward, measurements include the Malma Island pumping system at approximately 3 m depth.
- Extrapolated values between laboratory measurements may occur.

These changes can create apparent discontinuities or differences in variance, magnitude, or seasonal structure that are not purely ecological. Phase 1 characterizes the record but does not attribute observed interannual differences to a single cause.

## Processing contract

The reader locates the single real header containing `TIMESTAMP`, `CHLF`, and `PRESENCE_ICE` after the source metadata block. Dates are parsed strictly as `YYYY-MM-DD`; CHLF is parsed numerically without modification; ice semantics follow the source definition `0 = no ice`, `1 = ice`. Rows are sorted chronologically. Nothing is interpolated, smoothed, normalized, silently dropped, or ice-filtered in the canonical processed dataset.
