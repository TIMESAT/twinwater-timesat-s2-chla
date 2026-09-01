# Experiment design

## Scientific question

Which seasonal characteristics of chlorophyll-sensitive Sentinel-2 time series can be reconstructed reliably under irregular observation and cloud-gap conditions, and where do temporal reconstruction methods fail?

## Study architecture

Lake Erken is the dense-reference temporal-development, controlled-gap, parameter-selection, and year-blocked-validation domain. Erken CHLF is a high-frequency pelagic chlorophyll reference, not literal daily satellite-surface Chl-a truth.

Lake Vombsjön is reserved for a later locked external transfer, withheld-Sentinel-2 reconstruction test, and extreme bloom-regime stress test. Temporal methods and settings will be frozen using Erken before application to Vombsjön; Vomb performance will not be used to retune them.

## Data layers

**Layer A — reference / field observations.** Examples are Erken CHLF and, later, Vomb fluorometric Chl-a.

**Layer B — actual Sentinel-2 observations or proxies.** Examples are reflectance, NDCI, MCI, quality-control information, and usable Sentinel-2 acquisition dates.

**Layer C — reconstructed daily estimates.** Future examples are TIMESAT spline, GAM, and linear interpolation. Layer C products must never be called “daily satellite observations.”

## Planned reconstruction benchmark (not implemented in Phase 1)

The intentionally compact future benchmark contains:

1. linear interpolation;
2. GAM;
3. TIMESAT spline.

## Planned validation (not implemented in Phase 1)

Future Erken experiments will use the frozen date-level Sentinel-2 SCL observation mask together with year-blocked or leave-one-year-out validation, controlled random deletion, consecutive gaps, phase-targeted gaps, withheld-date point-wise accuracy, and seasonal trajectory metrics.

The main blocking unit is **year / season**. Daily observations are not independent calibration replicates, so random daily 70/30 splitting will not be the primary validation design. The code and tables preserve explicit year and day-of-year fields to support later leave-one-year-out analysis.

Peak date is the primary planned timing metric. Onset and end may be evaluated for pure Chl-a-to-Chl-a reconstruction, but they must not automatically be interpreted as absolute bloom onset when applied to Sentinel-2 indices.

## Reference and preliminary observable domains

The canonical daily dataset retains every row. Annual characterization uses two explicit scopes:

- `complete_reference`: all available Erken CHLF dates, including ice-flagged days, for provenance and ecological/reference context;
- `open_water`: dates with `PRESENCE_ICE == 0`, defining the primary preliminary domain for future Sentinel-2 reconstruction evaluation.

`open_water` is not a Sentinel-2 observation mask. Phase 2A-3 now provides a separate SCL-based date-level mask for acquisition availability, obvious cloud/shadow/cirrus/snow rejection, and local water context. Its later intersection with `open_water` must remain explicit. Glint screening, atmospheric correction, shoreline QC, reflectance quality, and retrieval quality have not been introduced. A reference event under ice is outside the preliminary satellite-observable domain and must not automatically be scored as a temporal-reconstruction failure.

Calendar truncation and potential open-water-season truncation are recorded separately. If a partial record begins or ends while the lake is already flagged open water, the corresponding open-water boundary is conservatively classified as truncated; no claim of ecological seasonal completeness is made.

## Measurement-regime sensitivity

The broad provenance variable `measurement_regime` distinguishes the 2019–2022 (`pre_2023`) and 2023–2025 (`2023_onward`) portions. The latter period includes the Malma Island pumping system according to source metadata. Future performance should be described by regime as a sensitivity check, using year/season summaries rather than treating daily values as independent replicates. No instrumentation-versus-ecology causal attribution is assumed.

## Phase 2A — SCL spatial diagnostics and observation mask

Phase 2A uses Sentinel-2 L2A SCL only to characterize product availability and local classification/contamination around the Erken ground-reference coordinate. For each product it preserves the real raster CRS, affine transform, bounds, dimensions, resolution, transformed station coordinate, central pixel, and SCL class distribution for five candidate square neighborhoods.

Phase 2A-2 froze the primary neighborhood at 3×3, with 1×1 and 5×5 retained as sensitivity cases. Phase 2A-3 then inspected the discrete nine-pixel states, compared a compact pre-specified rule set, froze the SCL product rule, collapsed products to unique calendar dates, and created the final SCL-based observation mask. Using Sen2Cor SCL does not select Sen2Cor surface reflectance as the preferred water-reflectance product.

Erken CHLF remains Layer A temporal reference. Phase 2A does not interpret satellite reflectance as temporal truth and does not sample or reconstruct CHLF at Sentinel-2 dates.

## Phase 2A boundary

Work through Phase 2A-3 is restricted to Erken provenance/reference characterization, portable L2A SCL spatial diagnostics, SCL-only usability sensitivity, deterministic product-to-date collapse, and the date-level satellite observation mask. It does not implement reflectance processing, chlorophyll indices, CHLF sampling at usable dates, temporal reconstruction, reconstruction gap experiments, validation experiments, parameter tuning, or Vomb transfer.
