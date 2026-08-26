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

Three local candidate copies were identified and confirmed byte-identical using file size and SHA256. All were 54,500 bytes and shared the SHA256 above. One was copied unchanged to the repository-relative ignored location `data/raw/SITES_CHL_ERK_20190417-20251130_L2_daily.csv`; the originals were not modified. Machine-specific candidate paths are intentionally excluded from public provenance.

## Measurement and interpretation caveats

- Fluorescence is corrected using weekly manually sampled laboratory chlorophyll.
- Measurements were originally collected at higher (hourly) temporal frequency; the daily product reports the 00:00 observation to minimize non-photochemical quenching.
- Measurement configurations and locations changed during the record.
- The source describes a YSI profiler during spring–fall and, for 2019–2022, a YSI sonde under ice.
- From 2023 onward, measurements include the Malma Island pumping system at approximately 3 m depth.
- Extrapolated values between laboratory measurements may occur.

These changes can create apparent discontinuities or differences in variance, magnitude, or seasonal structure that are not purely ecological. Phase 1.1 tracks a broad `measurement_regime` field: `pre_2023` covers the 2019–2022 portion, while `2023_onward` covers 2023–2025, during which the metadata indicate inclusion of the Malma Island pumping system. The label is a sensitivity/provenance device, not evidence of an instantaneous homogeneous switch, statistical significance, or causality.

## Observation domains

- `complete_reference` contains all available daily CHLF values, including ice-flagged dates. It preserves ecological/reference context and provenance.
- `open_water` contains dates where `PRESENCE_ICE == 0`. This is the preliminary domain for future Sentinel-2 reconstruction evaluation.

Open water is not equivalent to actual satellite availability. It does not yet encode acquisition dates, cloud screening, glint, atmospheric correction, shoreline QC, illumination, or any other Sentinel-2 usability criterion. Events under ice remain valid reference features but are outside this preliminary observable domain; inability to reconstruct them from Sentinel-2 is not automatically a temporal-method failure.

## Processing contract

The reader locates the single real header containing `TIMESTAMP`, `CHLF`, and `PRESENCE_ICE` after the source metadata block. Dates are parsed strictly as `YYYY-MM-DD`; CHLF is parsed numerically without modification; ice semantics follow the source definition `0 = no ice`, `1 = ice`. Rows are sorted chronologically. Nothing is interpolated, smoothed, normalized, silently dropped, or ice-filtered in the canonical processed dataset. Public run metadata contains the input basename, repository-relative raw path, file size, SHA256, environment, configuration, and run-time Git commit—never a user home or Downloads path.
