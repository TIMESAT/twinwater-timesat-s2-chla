# Codex Task — Implement Seasonal Event Protocol v1.0

## Objective

Implement and freeze the supplementary Erken seasonal-event analysis before
any real event-level reconstruction performance is computed.

## Authority and classification

- Parent contract: `Reconstruction_Analysis_Contract_v1.0.1`, unchanged.
- Event protocol: `Seasonal_Event_Detection_and_Matching_Protocol_v1.0`.
- Classification: secondary/exploratory because annual/global-maximum results
  were inspected before this supplementary protocol was frozen.
- Existing actual-mask benchmark products are immutable parent artifacts.

## Required implementation

1. Add the frozen Markdown protocol and a self-checking machine-readable JSON
   configuration containing every event rule and regression target.
2. Add a dedicated reference-event, reconstruction-candidate, and one-to-one
   matching module.
3. Detect reference events only from raw daily CHLF inside the existing frozen
   common support, processing physical open-water segments separately.
4. Use reference `find_peaks(distance=30, prominence=0.30*Scale_y,
   plateau_size=(1,None))` and reconstruction-candidate
   `find_peaks(plateau_size=(1,None))` exactly.
5. Match only within year, segment, and ±15 days; optimize cardinality, total
   absolute timing error, then the earliest reconstructed-time sequence.
6. Keep magnitude entirely outside detection and matching.
7. Add deterministic synthetic tests for plateaus, segmentation, candidate
   amplitude independence, matching, ties, thresholds, misses, and unavailable
   failed/incomplete reconstructions.
8. Add a reference-only preflight that fails unless the frozen 18 Erken event
   dates, identifiers, yearly counts, and Q95-Q05 scales reproduce exactly.
9. Verify and retain checksums for the existing actual-mask parent benchmark.

## Stop boundary

Do not calculate event recovery on real linear, TIMESAT double-logistic, or
TIMESAT smoothing-spline outputs in this task. Do not run controlled-gap
performance or Vombsjön. Do not alter the parent contract, methods, defaults,
masks, support, spline grid/selections, primary metrics, or existing benchmark
products. Stop after implementation, tests, reference-only preflight, commit,
and push.
