# Erken Phase 6D processing-baseline control

This directory contains the governed Sentinel-2 processing-baseline audit for
the frozen Erken Phase 6A/6B observation products.

The audit confirms:

- 2,778 observation-selection rows across 926 candidate dates;
- 306 exact L1C/L2A/ACOLITE source-alignment dates;
- 613 available L1C/L2A products with verified metadata-derived additive
  offset and quantification conversion;
- 1,358 ACOLITE source-L1C products representing 1,357 acquisition
  identities;
- one duplicate acquisition with two products under the same `N0500`
  baseline;
- zero same-acquisition products spanning distinct processing baselines;
- all frozen Phase 6C output hashes unchanged.

The mandatory gate is
`HOLD_EMPIRICAL_HARMONIZATION_NOT_IDENTIFIABLE`. No empirical baseline
correction was estimated or applied. B4/B5/B6 summaries are descriptive
provenance and must not be interpreted as cross-baseline correction
coefficients.

The governing protocol is
`docs/Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md`, and the
machine-readable configuration is
`config/erken_s2_processing_baseline_control_v1.0.yaml`.
