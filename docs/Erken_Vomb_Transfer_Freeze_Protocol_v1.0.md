# Erken-only second transfer freeze protocol v1.0

**Status: FROZEN on 2026-09-18 before any Vombsjön input audit or performance
analysis.**

## 1. Scope and change-control status

This protocol implements the second freeze required by the active scientific
master and Section 12 of
`Reconstruction_Analysis_Contract_v1.0.1.md`. It selects the settings carried
from Erken into the locked Vombsjön transfer. It does not inspect or execute a
Vombsjön performance analysis. The first reconstruction contract, all Erken
results, and the reliability synthesis v1.0 remain unchanged.

The executable authority is
`config/erken_vomb_transfer_freeze_v1.0.json`. The dated manifest under
`results/transfer_freeze/v1.0/` records exact checksums. Any later scientific
setting change requires a new version and cannot replace this freeze in place.

## 2. Erken-only decision hierarchy

The final settings use the following pre-specified hierarchy:

1. retain all three scientifically distinct primary benchmark methods;
2. retain the frozen default double-logistic configuration unchanged;
3. select the final spline control by the original candidate grid, withheld-day
   nRMSE, year-first equal weighting, explicit candidate failure rule, and
   smaller-value exact tie break;
4. select the satellite proxy from the frozen Erken observation-layer evidence;
5. select the processing role from the master’s pre-specified aquatic-AC design,
   not from a claim of processor superiority; and
6. keep every Vomb result unavailable during selection.

No single pooled metric determines a method winner. All three primary methods
are carried forward because Erken showed metric-specific trade-offs. The
CV-selected double logistic remains a separately labelled sensitivity.

## 3. Final spline calculation

`erken_phase3_spline_candidate_year_nrmse.csv` stores each candidate-year
score once in every outer fold for which that year was a training year. The
six repeated copies for each candidate-year are byte-numerically identical.
The transfer calculation therefore checks the repetitions, keeps one value for
each of seven years, and gives the seven years equal weight.

| `p_smooth` | Equal-year mean nRMSE | Difference from best | Rank |
|---:|---:|---:|---:|
| 0 | 0.232342812 | 0.020197373 | 8 |
| 1 | 0.218186671 | 0.006041233 | 5 |
| 3 | 0.213787899 | 0.001642460 | 3 |
| **10** | **0.212145438** | **0.000000000** | **1** |
| 30 | 0.212278215 | 0.000132776 | 2 |
| 100 | 0.214232010 | 0.002086572 | 4 |
| 300 | 0.219149049 | 0.007003611 | 6 |
| 1000 | 0.228724922 | 0.016579483 | 7 |

The final spline value is therefore `p_smooth = 10`. This is an all-Erken
application of the original scoring rule. It is not the mode of the seven
outer-fold selections, a new tuning rule, or an independent Erken validation.

## 4. Method, parameter, basis and role

| Method | Frozen parameter/configuration | Erken basis | Transfer analysis role |
|---|---|---|---|
| Linear interpolation | Piecewise linear, retained dates only, no extrapolation | Untuned primary baseline; lowest mean point error in Erken but not uniformly best by year or metric | Primary simple baseline |
| TIMESAT double logistic | TIMESAT 4.4.1, `p_fitmethod=1`, `p_seapar=1`, every other value from `timesat_double_logistic_defaults_v4.4.1.json` | Original pre-performance default; better descriptive integral accuracy on average but weaker point/peak outcomes | Primary frozen-default benchmark |
| TIMESAT smoothing spline | TIMESAT 4.4.1, `p_fitmethod=2`, `p_smooth=10`, other effective settings inherited from the frozen snapshot | Seven-year equal-weight nRMSE minimum under the original candidate rule | Primary Erken-selected spline |
| CV double logistic | `p_fitmethod=1`, `p_seapar=0`; other defaults unchanged | All seven Erken outer folds selected 0 in the pre-frozen secondary sensitivity | Secondary sensitivity only; never replaces the default benchmark |

The TIMESAT core is version 4.4.1 at commit
`b20844140bf38543349552341212609fa18b24b1`; TIMESAT CLI is version 1.9.2 at
commit `258b50565b322d9f5bafd9df9b822c80ca09a847`. The registered macOS CPython
3.12 binary and source hashes remain those in the frozen defaults snapshot.
Runtime execution must pass that existing identity gate.

## 5. Satellite proxy and processing product

MCI is the primary proxy because the frozen Erken Phase 6C common-support
analysis found a clearer and more stable same-day CHLF association for MCI than
for NDCI. MCI remains an observed proxy, not an absolute Chl-a estimate. It is
calculated at pixel level from B4/B5/B6 with fixed nominal wavelengths
665/705/740 nm and summarized by the median of valid pixels.

ACOLITE `rhos` MCI is the primary processing product. This choice implements
the master’s pre-specified primary aquatic atmospheric-correction role. It is
not a declaration that ACOLITE outperformed L1C or L2A: the three Erken MCI
uncertainty intervals overlapped, and Phase 6C prohibited a unique processor
winner. Official L2A MCI is retained as a separate processing sensitivity and
L1C MCI as a transparent diagnostic baseline. They are not pooled and there
is no silent product fallback.

The primary AC workflow is fixed to the clean external
`s2-inlandwater-ac` commit
`6b5fe1f31a4e4d477c2ad552c97f3c2f442b8b0c`, ACOLITE source commit
`64a02ff386e2985eef68ae00198b38e04f3c4a1f`, inland profile, 20 m output,
polygon clipping, ancillary data enabled, and `L2R_rhos` output. The processing
ROI is a computational crop only; the scientific time-series target is the
fixed 3×3 nominal-station neighbourhood. The Vomb input audit must verify the
exact external versions and settings before performance is run.

No empirical processing-baseline correction is applied. Product metadata
controls radiometric offset and quantification, exact baseline strata are
retained, reflectance quantities are not pooled, and negative reflectance or
MCI values are not clipped.

## 6. Spatial support, QC, dates and season

- The temporal target is the median proxy in a fixed station-centred 3×3
  window on the 20 m grid around 55.6775 N, 13.60889 E.
- MCI requires valid B4, B5 and B6 and at least 6 of 9 valid pixels. Missing
  required QA makes the observation unavailable; invalid pixels are not filled.
- Multiple eligible primary-product observations on one calendar date are
  reduced to the median of their observation-level medians. The whole unique
  calendar date is the withholding unit.
- Field matchups use actual GPS when available and the nominal coordinate only
  as a provenance-labelled fallback. GPS variation never moves the primary
  temporal target between dates. The two known coordinate flags cannot be
  silently corrected.
- Fits are separate by calendar year. Day 366 is excluded and recorded because
  the frozen TIMESAT setting uses `p_ignoreday=366`.
- Scenario support runs from the first to the last retained training date.
  Endpoints cannot be withheld, cross-year fitting and extrapolation are
  forbidden, and partial coverage remains explicit.

## 7. Scale compatibility and leakage boundary

MCI is signed and much smaller in magnitude than Erken CHLF, while the frozen
TIMESAT input-validity range is `p_ylu=[0,10000]`. Each year and holdout
scenario therefore fits a positive affine transform from retained training
observations only: training minimum maps to 1000 and training maximum maps to
9000. Predictions are inverse-transformed to native MCI units before
evaluation. Held-out values cannot affect the transform, constant/non-finite
training ranges make the scenario unavailable, and predictions are never
clipped.

This preserves ordering and timing while keeping every training input inside
the frozen absolute valid-data range. Relative TIMESAT controls such as start
cutoffs and `p_seapar` retain their meaning. The delivered runtime validation
also checks positive-affine equivariance for both TIMESAT methods on synthetic
data. The transfer must stop if that test or the runtime identity gate fails.

## 8. Locked holdout and evaluation design

After QC and date deduplication, a year requires at least eight eligible dates
and every scenario must retain at least six training dates. The first and last
dates are protected.

- Isolated design: exhaustively withhold each internal eligible date once.
- Consecutive design: exhaustively withhold each internal contiguous sequence
  of 2, 3 and 4 observed acquisition dates.
- No scenarios are randomly subsampled. Seed 20260918 governs the later 10,000
  replicate percentile bootstrap of whole calendar years.
- All methods receive identical training dates and are evaluated only on
  finite held-out MCI dates where all three primary predictions are finite.
  Every failure remains in the audit; an all-method paired comparison is
  unavailable if any primary method fails.

Primary quantitative transfer metrics are native-MCI bias, MAE, RMSE and
nRMSE. The nRMSE denominator is the retained-training-observation `Q95-Q05`
with linear quantiles. An invalid denominator stays unavailable without an
epsilon. Repeated block predictions are collapsed to one median prediction per
year, design, block size and date before a trajectory correlation is computed.

Observed-proxy peak timing is secondary and conditionally identifiable. It is
evaluated only when a scenario withholds the full observed-series global MCI
peak and the peak is not a boundary or ambiguous non-contiguous equal maximum.
The primary tolerance remains ±10 d, with ±5/±15 d sensitivities. A
reconstructed index integral may be described, but without a dense Vomb
reference it is not an integral-accuracy validation.

## 9. Validation roles and non-operational Erken variables

Withheld Sentinel-2 MCI is the primary quantitative transfer validation of the
temporal reconstruction layer. Vomb field Chl-a is limited to lake-specific
proxy validation and complementary ecological consistency, including broad
seasonal/high-low states and the 2018 extreme regime. Sparse field observations
cannot serve as daily truth, exact unobserved peak truth, or a tuning target.

`A_gap` is available in Erken only because the complete reference trajectory
was retained behind each artificial gap. It is a retrospective explanatory
and reliability-stratification variable. It is not known inside an operational
Vomb hidden gap and is not a transfer input or gating threshold.

## 10. Completion and next gate

This second freeze is scientifically complete: no reconstruction parameter,
proxy, product role, QC threshold, support rule, holdout rule, seed, metric or
failure rule remains to be selected from Vomb performance. The external Vomb
files, product identities, licences, checksums, ROI coverage and coordinate
flags remain unverified inputs. That is an execution gate for the next raw
data audit, not permission to alter the frozen settings.

The next authorized stage is only the Vomb input and raw satellite/matchup
audit. Vomb reconstruction performance remains out of scope for this freeze.
