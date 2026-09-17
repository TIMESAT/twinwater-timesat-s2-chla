# Decisions log

## Decision 001 — Erken development domain

Lake Erken is the dense-reference temporal-development domain.

## Decision 002 — Locked Vombsjön transfer

Lake Vombsjön is reserved as a locked external transfer and stress-test domain. Temporal reconstruction parameters will not be retuned based on Vombsjön performance.

## Decision 003 — Year-blocked validation

Future temporal method selection will use year-blocked / leave-one-year-out validation rather than random daily train/test splitting. A day is not treated as an independent calibration replicate.

## Decision 004 — Phase 1 scope

Phase 1 is restricted to quality control and characterization of seasonal diversity. No reconstruction method or gap experiment is implemented.

## Decision 005 — Primary timing metric

Peak date is currently the primary planned cross-scale timing metric. Onset and end require more cautious interpretation, particularly for Sentinel-2 indices.

## Decision 006 — Observational domain

The canonical Erken reference retains every daily observation, including ice periods. Until actual Sentinel-2 observation and QC masks are introduced, the main future reconstruction-evaluation domain is `open_water`, defined as `PRESENCE_ICE == 0`.

## Decision 007 — Complete reference versus satellite-observable truth

Events during ice-covered periods remain valid features of the ecological/reference record but lie outside the preliminary satellite-observable domain. Failure to reconstruct such events from Sentinel-2 must not automatically be interpreted as temporal-reconstruction failure.

## Decision 008 — Measurement regime

The known 2023-era measurement-configuration change is tracked using the broad `pre_2023` and `2023_onward` provenance labels and will be included in sensitivity analyses. No causal attribution to the measurement change is assumed, and the boundary is not asserted to be an instantaneous homogeneous instrument switch.

## Decision 009 — Partial-year terminology

Calendar-year truncation and potential open-water-season truncation are distinct concepts and must not be conflated. Boundary status uses only source coverage and the observed ice state at the available boundary.

## Decision 010 — Exploratory peak rule

Local peak counts are exploratory only. They use unsmoothed open-water daily CHLF, `scipy.signal.find_peaks`, a 30-calendar-day minimum separation, and relative-prominence sensitivity thresholds of 0.10, 0.20, and 0.30 of each year's open-water amplitude. Complete-reference and open-water global annual maxima are always reported separately.

## Decision 011 — Phase 2A SCL diagnostic boundary

Sentinel-2 L2A SCL is used only to inventory acquisitions/products and diagnose the spatial classification environment around the Erken reference coordinate. Raw SCL classes remain separate, while `bad_scl_fraction` and `water_fraction` are diagnostic summaries only. The final ROI and all usability thresholds remain unset until real server-derived distributions are inspected and then explicitly frozen. This use of Sen2Cor SCL does not select Sen2Cor reflectance as the preferred water-reflectance product.

## Decision 012 — Erken SCL spatial neighborhood

The primary Erken SCL observation-quality neighborhood is 3×3 pixels at 20 m resolution. The 1×1 and 5×5 windows are retained as spatial sensitivity cases; 7×7 and 11×11 are not primary candidates because expansion increasingly mixes obvious-bad and isolated land-like SCL classes into otherwise water-centred acquisitions without a demonstrated robustness benefit. This decision freezes only spatial support. No final water-fraction threshold, bad-SCL threshold, or usable-acquisition mask is frozen.

## Decision 013 — Sentinel-2 temporal observation unit

The temporal reconstruction observation unit is a unique calendar date, not a Sentinel-2 product. Same-day products remain at product level for provenance and QC, but a date is usable when at least one product passes the frozen scene-quality rule and contributes at most one temporal observation. When more than one product passes, the representative product is selected deterministically by lowest bad-SCL fraction, highest water fraction, lowest persistent non-water fraction, centre-water preference, earliest acquisition datetime, and lexical product ID. This avoids duplicating one daily Erken reference value merely because multiple Sentinel-2 products exist on that date.

## Decision 014 — Erken Sentinel-2 SCL usability rule

The frozen primary rule is `scl3x3_b1_w8_centernotbad_p0_class2zero_v1`. In the frozen 3×3 neighborhood, a product passes only when it has at most one obvious-bad SCL pixel, at least eight water pixels, a centre pixel that is not an obvious-bad class, zero persistent non-water pixels (classes 4, 5, and 7), and zero class-2 pixels. The rule retains 307 of 926 primary-interval calendar dates. It avoids the fragility of requiring 9/9 water pixels while rejecting the extra contamination of the two-bad-pixel sensitivity rule; neither choice materially changes typical or maximum temporal gaps. The rule was selected entirely from the SCL observation process without CHLF, reflectance, index, retrieval, or reconstruction results. This freezes the satellite observation mask only and does not validate TIMESAT input.

## Decision 015 — Deterministic Erken temporal-sampling join

Calendar date is the unique deterministic key for joining the frozen date-level Sentinel-2 mask to the canonical daily Erken reference. The daily reference key space is preserved. Sentinel-2 inventory presence, frozen SCL usability, reference availability, open-water status, and their preliminary intersection remain separate fields; satellite metadata are not forward-filled. Their intersection is explicitly preliminary and does not freeze an analysis season, reconstruction input mask, or 2019/2025 year eligibility.

## Decision 016 — Phase 3 contract activation

`Reconstruction_Analysis_Contract_v1.0.1.md` and
`Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md` are the
authoritative Phase 3 scientific governance. Their exact repository copies and
SHA256 values are frozen by the machine-readable contract. The primary Erken
benchmark is exactly linear interpolation, TIMESAT double logistic at the
frozen effective defaults, and TIMESAT smoothing spline. It uses the 288
authoritative sparse dates, 2019–2025 LOYO, method-independent common support,
the frozen spline grid/selection rule, external metric definitions, explicit
failure retention, and the frozen controlled-gap protocol. Phase 3
implementation and pre-performance gates may proceed without generating or
interpreting reconstruction performance; any post-performance scientific rule
change requires a new contract version.

## Decision 017 — Erken primary observation-validity freeze

The primary Erken Sentinel-2 observation rule is
`erken_s2_primary3x3_min6_v1`. Within the frozen station-centred 3×3 window on
the 20 m grid, NDCI and MCI are independently eligible when at least six of the
nine pixels pass their already-defined pixel-level validity rules. Same-product
B4/B5/B6 comparisons require at least six common-valid pixels. The same
threshold applies to L1C, official L2A/Sen2Cor and ACOLITE. The decision was
made only from pre-specified QA attrition, before CHLF inspection or field
performance. Required validity-contributing QA families that are missing or
unreadable make the affected observation unavailable; missing optional or
legacy QA remains recorded only. Existing diagnostic flags remain diagnostic,
and MCI continues to use the fixed nominal 665/705/740 nm wavelengths. The
governing protocol is `Erken_Sentinel2_Observation_Selection_Protocol_v1.0.md`
and the machine-readable configuration is
`erken_s2_observation_selection_v1.0.yaml`.

## Decision 018 — Erken Sentinel-2–CHLF matchup analysis

Phase 6C remains in this repository and uses exact calendar-date matching
between the frozen Erken observation-selection table and the canonical daily
CHLF reference. Nearest-date matching and temporal interpolation are
forbidden. The primary fair comparison is metric-specific common support:
finite open-water CHLF, exact L1C/L2A/ACOLITE source alignment, and eligibility
for the same index under the frozen 6/9 rule for all three methods. The primary
association metric is Spearman correlation between raw CHLF and the index;
Pearson correlation with log10(CHLF) is secondary. Pooled uncertainty uses a
calendar-year cluster bootstrap, and a one-predictor LOYO linear model on
log10(CHLF) is a secondary exploratory sensitivity. The analysis cannot
retune observation rules, declare a processor winner, run reconstruction or
inspect Vombsjön. The governing files are
`Erken_Sentinel2_CHLF_Matchup_Analysis_Protocol_v1.0.md` and
`erken_s2_chlf_matchup_analysis_v1.0.yaml`.
