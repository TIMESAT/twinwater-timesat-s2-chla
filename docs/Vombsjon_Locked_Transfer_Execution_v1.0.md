# Vombsjön locked transfer execution specification v1.0

Status: frozen before any Vombsjön performance execution, 2026-10-02.
This execution specification implements the existing
[transfer freeze v1.1](../config/erken_vomb_transfer_freeze_v1.1.json),
[active master](Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md)
and [gate closure protocol](Vombsjon_Execution_Gate_Closure_Protocol_v1.0.md).
It is not a replacement scientific plan or a new parameter-selection stage.
Its exact byte SHA256 is pinned by the runner and recorded in each performance
manifest. Changes require a new version, preserving this specification.

## Entry points and authority

[Script 43](../scripts/43_vombsjon_locked_transfer.py) defaults to read-only
preflight. Only `--run-performance` enables real reconstruction and output.
[Script 44](../scripts/44_validate_vombsjon_locked_transfer.py) independently
checks saved output integrity, scenario coverage and numerical reductions;
`--preflight` checks inputs and predicted workload without evaluating performance.
Script 38 and the historical v1.0 loader remain unchanged. The dedicated
[module](../src/twinwater_timesat/vombsjon_locked_transfer.py) pins the v1.1
path, v2 schema, version and SHA256; no substitute configuration is accepted.
From transfer_freeze it imports only pure holdout and scaling utilities.

The committed three closure artifacts must match their verified SHA256 values,
record 7/7 PASS and clean-start closure, and be ancestors of the current checkout.
All committed v1.2 audit files and provenance must retain their closure-baseline
bytes. A fresh synthetic runtime and affine-equivariance probe must pass with
the registered binary. Gate artifacts and historical authorization=false are
never rewritten. Performance additionally requires a clean checkout containing
the committed implementation and this specification. Preflight may run on an
uncommitted implementation, but reports that performance prerequisite separately.
No output overwrite, substitute output root, processor fallback or tuning flags.

## Inputs and processor separation

Temporal input is exclusively the canonical v1.2
`vombsjon_same_day_observation_master.csv`: `method` identifies processor,
`date` the whole calendar date, `mci_observation_available` eligibility, and
`MCI_date_median` the native MCI observation. Require unique `(method,date)`
keys before any filtering, strict booleans, finite eligible MCI, the fixed nine
pixel support, no pooling and no independent counting of reprocessings. Retain
product IDs, baselines and existing exclusion provenance. Do not re-extract,
re-QC or re-deduplicate this already deduplicated table.

ACOLITE is primary, L2A a separate official-product sensitivity, L1C a diagnostic
baseline. Enumerate each processor's own dates independently. Identical scenarios
apply to reconstruction methods *within* a processor. Never intersect processor
dates to choose training or test sets and never pool their MCI scales. Report
processor-specific availability, support and denominators alongside outcomes;
cross-processor differences conflate sampling and processing and are descriptive,
not a matched processor ranking or basis for selection.

Retain all calendar years present. Exclude day 366 explicitly. Require at least
8 eligible dates per processor-year and at least 6 retained training dates per
scenario. Enumerate every internal isolated date and every internal sequence of
2, 3, or 4 acquisition dates, protecting first and last dates. Report excluded
years and unsupported block sizes, including zero-count cases. Retain partial-year
support; no cross-year fitting or extrapolation.

## Reconstruction and leakage boundary

Primary methods are linear interpolation, default double logistic (p_seapar=1),
and spline (p_smooth=10). CV double logistic (p_seapar=0) is separately labelled
secondary sensitivity, never part of the three-method primary support gate.
All other TIMESAT parameters come from the frozen snapshot.

For each scenario fit min/max scaling using training values only, mapping them
to 1000/9000; invert TIMESAT predictions to native MCI before evaluation. Compute
training Q05/Q95 with linear quantiles. Held-out values and all field variables
are unavailable to the fitting function. Zero/nonfinite training range makes the
scenario unavailable for every method; an invalid Q95-Q05 makes only nRMSE
unavailable. Keep all method statuses and missing outputs. No epsilon, clipping,
repair, replacement processor, retuning or full-series fit is introduced.
Daily predictions are scenario-specific estimates within retained training support.

## Exact estimators, denominators and bootstrap

Strata are processor × design (isolated/consecutive) × block size × method.
Never pool block sizes or designs into a headline score.

1. **Scenario:** if any primary method fails, all primary paired metrics for
   that scenario are unavailable. Otherwise evaluate the intersection of finite
   predictions from the three primary methods and finite withheld observations.
   Record requested and evaluable date counts. For errors prediction minus
   observation, bias is mean(error), MAE mean(abs(error)), RMSE
   sqrt(mean(error²)); nRMSE is this RMSE divided by training Q95-Q05.
   The CV sensitivity is evaluated on the same primary common dates only when
   its own predictions are finite at every such date and its fit succeeds. It
   never changes primary denominators. Its summaries carry its own availability.
2. **Year:** arithmetic mean of finite scenario metrics within each stratum;
   scenarios have equal weight, not pooled residual weight. Thus mean scenario
   RMSE, not sqrt of pooled squared errors, is the year RMSE estimator. Report
   total scenarios, method failures, primary-paired unavailable scenarios,
   finite-scenario denominator for each metric, requested and evaluable dates.
   No unavailable value is imputed as zero or removed from total counts.
3. **Equal-year:** arithmetic mean of available year estimates for the same
   stratum and metric. Report eligible-year total and available-year denominator,
   and scenario total/available counts. A year with no available metric is
   retained with an unavailable estimate. These are conditional estimates;
   missingness/coverage accompanies every estimate. No numerical failure penalty
   is invented for continuous metrics.
4. **Bootstrap:** use NumPy Generator(PCG64(20260918)), 10,000 draws. Within each
   processor/design/block stratum, sort all scenario-eligible years and draw N
   whole-year indices with replacement, N equal to that stratum's year count.
   Reinitialize this seed per stratum, and reuse the same index matrix across
   methods and metrics. Carry unavailable year estimates through each draw;
   average finite sampled estimates, with an all-unavailable draw unavailable.
   Report finite-draw count; percentile 2.5/97.5 bounds use linear quantiles.
   Fewer than two available years: point estimate retained, CI unavailable.
   No independent date/scenario bootstrap or cross-processor paired inference.
5. **Trajectory correlation:** within processor/year/design/block/method, take
   the median of repeated paired-valid withheld predictions at each date. Compute
   Pearson r against the observed MCI at those dates only with at least three
   dates and nonzero variance in both vectors. Otherwise unavailable. Store the
   collapsed rows and date count. Aggregate r arithmetically across available
   years with the same whole-year bootstrap; no Fisher transformation.
6. **Observed-proxy peak:** reuse the existing global-peak rule: equal maxima on
   consecutive calendar days form a plateau with temporal midpoint; maxima
   separated by a calendar gap are ambiguous. A reference peak touching a support
   boundary is nonidentifiable. A scenario is reference-eligible only when that
   midpoint is an actual held-out date. Compare with the reconstructed daily
   global peak on identical support; ambiguous or boundary reconstruction peaks
   are unavailable. Record signed/absolute calendar-day errors and <=5/10/15-day
   indicators. Continuous peak-error denominators require all three primary
   peaks to be identifiable and all primary fits to succeed. Reliability uses
   *all reference-eligible scenarios* as denominator: fit failure/unavailable
   peak counts as non-success, with reason counts retained. Non-reference-eligible
   scenarios are excluded from this denominator but retained in the peak table.
   Apply scenario-to-year/equal-year/bootstrap rules above to these quantities.
   No unobserved field peak truth or integral-accuracy score is produced.

## Complementary field consistency

Use only v1.2 `vombsjon_field_satellite_matchup_master.csv`, whose support must
be `fixed_pelagic_convex_hull_polygon`, with identical support every date, no
nominal fallback, no coordinate correction, exact same calendar-date matching
and the frozen two-thirds polygon validity rule. Preserve all 162 date/processor
rows, unavailable pairs, coordinate flags and depth caveats. The output is a
labelled paired-evidence table of observed polygon MCI and field Chl-a for
complementary ecological/proxy inspection, including 2018. It performs no
calibration, regression, invented high/low threshold or daily-truth comparison.
Neither nominal-station temporal 3×3 nor GPS 3×3 enters this table. The field
values are loaded only after temporal reconstruction/evaluation completes.
Preflight validates field support/availability metadata without loading Chl-a.

## Outputs and validation

Only `results/vombsjon/locked_transfer/v1.0/` is writable by performance.
Each name starts `vombsjon_transfer_`:

| Suffix | Contents |
|---|---|
| input_audit.csv | Existing temporal rows plus explicit day-366/eligibility status |
| year_eligibility.csv | Processor/year/design counts and support |
| holdout_scenarios.csv | Protected training/test dates and scenario IDs |
| training_scales.csv | Training-only extrema, affine coefficients and Q05/Q95 |
| method_status.csv | Every scenario/method status and failure reason |
| daily_predictions.csv | Native-MCI scenario curves within support |
| withheld_predictions.csv | Requested observations, predictions, errors and paired flags |
| scenario_metrics.csv | Point metrics and explicit availability/counts |
| peak_metrics.csv | Peak identifiability, errors and reliability indicators |
| date_collapsed_predictions.csv | Median repeated withheld predictions per date |
| year_summary.csv | Long-form metric estimates and denominator columns |
| equal_year_summary.csv | Equal-year estimates, counts and bootstrap intervals |
| field_consistency.csv | Fixed-polygon exact-date complementary evidence only |
| runtime_validation.json | Fresh synthetic runtime probe |
| validation.csv | Integrity and numerical audit outcomes |
| manifest.json | Commit, clean-start state, exact input/code/specification/output hashes |

The manifest records the specification SHA256, frozen historical authorization
false, explicit invocation, native MCI units, processor/method roles and no-tuning
assertions. Completion requires script 44 validation; it verifies file coverage
and hashes, immutable evidence, exhaustive scenario/date coverage, training-only
scales, paired masks, metrics, aggregation and field support without rerunning
TIMESAT. Partial output from an interrupted run is never accepted as complete.
Synthetic tests must establish leakage resistance by mutating withheld values,
failure retention, processor separation, exact metric/aggregation estimators,
peak boundaries, input tampering rejection and preflight's no-performance path.
