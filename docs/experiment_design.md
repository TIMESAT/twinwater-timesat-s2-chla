# Experiment design

## Scientific question

Which seasonal characteristics of chlorophyll-sensitive Sentinel-2 time series can be reconstructed reliably under irregular observation and cloud-gap conditions, and where do temporal reconstruction methods fail?

## Study architecture

Lake Erken is the dense-reference temporal-development, controlled-gap, parameter-selection, and year-blocked-validation domain. Erken CHLF is a high-frequency pelagic chlorophyll reference, not literal daily satellite-surface Chl-a truth.

Lake Vombsjön is reserved for a later locked external transfer, withheld-Sentinel-2 reconstruction test, and extreme bloom-regime stress test. Temporal methods and settings will be frozen using Erken before application to Vombsjön; Vomb performance will not be used to retune them.

## Data layers

**Layer A — reference / field observations.** Examples are Erken CHLF and, later, Vomb fluorometric Chl-a.

**Layer B — actual Sentinel-2 observations or proxies.** Examples are reflectance, NDCI, MCI, quality-control information, and usable Sentinel-2 acquisition dates.

**Layer C — reconstructed daily estimates.** The frozen primary methods are linear interpolation, TIMESAT double logistic, and TIMESAT smoothing spline. Layer C products must never be called “daily satellite observations.”

## Frozen Phase 3 reconstruction benchmark

Contract v1.0.1 fixes the intentionally compact benchmark at exactly:

1. linear interpolation;
2. TIMESAT double logistic with frozen effective defaults; and
3. TIMESAT smoothing spline with the integer grid
   `{0,1,3,10,30,100,300,1000}`.

GAM and all other methods are excluded from the primary benchmark. Phase 3
infrastructure and pre-performance validation are implemented; scientific
reconstruction performance has not yet been generated or interpreted.

## Frozen validation

Erken uses the 288 authoritative actual-mask dates from the deterministic
Phase 2B-1 product. Seven outer LOYO folds cover 2019–2025. For each outer
fold, spline smoothing is selected only from the other six years using their
equal-weight mean withheld-date nRMSE. Controlled scenarios use frozen random
deletion and exhaustive consecutive gaps; no manually selected phase-targeted
gap category is part of the primary contract.

The main blocking unit is **year / season**. Daily observations are not independent calibration replicates, so random daily 70/30 splitting will not be the primary validation design. The code and tables preserve explicit year and day-of-year fields to support later leave-one-year-out analysis.

The common-support global-peak date is the primary candidate timing metric,
with ±10 days as the primary reliability criterion and ±5/±15 days as frozen
sensitivities. Onset/end are not primary Phase 3 outputs.

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

## Phase 2B-1 — deterministic temporal-sampling join

Phase 2B-1 uses calendar date to join the frozen SCL mask to every canonical
daily Erken reference row. It preserves inventory presence, frozen SCL
usability, finite-reference availability, open-water status, and the
preliminary intersection as separate fields. The join supplies descriptive
annual and interval diagnostics and explicit 2019/2025 boundary evidence.

Contract v1.0.1 promotes the 288 preliminary candidates to the frozen Phase 3
actual-mask sparse inputs. The year-specific common support is `open_water`
inside the inclusive first/last sparse-input boundary. Both boundary-truncated
years, 2019 and 2025, remain eligible under this method-independent support
rule and are explicitly flagged for interpretation.

## Phase 3 implementation boundary

Phase 3 now includes the machine-readable contract, authoritative sparse-input
and common-support builders, the three method adapters, nested spline
selection, point-wise and seasonal metrics, explicit failure schemas,
controlled-gap generators, deterministic preflight products, and a guarded
future benchmark CLI. The current stop boundary excludes Erken performance
comparison or ranking, controlled-gap performance execution, inferential
reliability-envelope modelling, Vombsjön inspection, and any transfer tuning.
