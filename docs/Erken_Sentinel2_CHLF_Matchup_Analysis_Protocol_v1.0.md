# Erken Sentinel-2–CHLF Matchup Analysis Protocol v1.0

**Status: FROZEN before calculation of index–CHLF associations.**

## 1. Purpose

Phase 6C addresses the observation-layer question in the project master:
whether quality-controlled, station-neighbourhood Sentinel-2 NDCI and MCI
contain defensible information about same-day Erken CHLF. It compares L1C,
official ESA L2A/Sen2Cor and ACOLITE without changing the frozen observation
rule.

This phase does not select a temporal reconstruction method, run TIMESAT,
retune the 6/9 threshold, change atmospheric-correction settings, access
Vombsjön or claim that a satellite index is a direct Chl-a measurement.

The work remains in this repository because the governing reference data,
observation-selection table, code versions and provenance chain are already
here. Phase 6C writes only to `results/phase6c/` and does not overwrite Phase
6A or Phase 6B products.

## 2. Frozen inputs

- Daily reference: `data/processed/erken_daily_clean.csv`.
- Observation selection:
  `results/phase6b/observation_selection/erken_s2_observation_selection.csv`.
- Selection rule: `erken_s2_primary3x3_min6_v1`.
- Primary spatial support: station-centred 3×3 window on the 20 m grid.
- Methods: L1C TOA, official L2A BOA and ACOLITE `rhos`.
- Index summaries: pixel-level NDCI and MCI followed by the median of valid
  pixels. NDCI and MCI retain their separate eligibility counts.

The Phase 6C manifest records SHA256 identities for every input and for the
analysis configuration.

## 3. Exact-date matchup

Calendar date is the only matchup key. A Sentinel-2 observation is paired only
with the CHLF value recorded on the exact same date. Temporal tolerance is zero
days. Nearest-date matching, averaging over adjacent days, forward/backward
filling and temporal interpolation are forbidden.

Each joined row retains the original observation-selection status. Missing,
ambiguous, ineligible, ice-period and unavailable rows remain explicit in the
matchup audit; they are not silently discarded.

The scientific analysis requires finite CHLF and `open_water == True`. The
original CHLF and ice fields remain unchanged.

## 4. Analysis supports

### 4.1 Primary fair-comparison support

For each index separately, the primary comparison uses only dates satisfying
all of the following:

1. exact L1C/L2A/ACOLITE source alignment;
2. finite same-day CHLF;
3. open water;
4. that index is eligible under the frozen 6/9 rule for all three methods.

Therefore L1C, L2A and ACOLITE are evaluated against identical CHLF dates for
each index. NDCI and MCI may have different common-support date sets because
their valid-pixel rules are metric-specific.

### 4.2 Secondary method-specific support

A secondary descriptive analysis uses every finite, open-water, eligible
observation for each method and index. These samples can differ between
methods and must not be used as a direct processor ranking.

## 5. Frozen association metrics

The primary association metric is Spearman rank correlation between raw CHLF
and the index. It tests monotonic information without assuming a linear
index–CHLF relationship or normal CHLF distribution.

The secondary association metric is Pearson correlation between the index and
`log10(CHLF)`. CHLF must be strictly positive for this metric; any non-positive
value is retained in the audit but makes the log-scale metric unavailable.

Results are reported overall, by calendar year where at least three valid
pairs exist, and by the pre-existing measurement-regime label. P-values are
not headline evidence because daily observations within seasons are not
independent.

Uncertainty for pooled correlations uses 10,000 calendar-year cluster
bootstrap resamples with seed 20260917 and percentile 95% intervals. The
bootstrap resamples whole years and never individual dates. With only seven
year clusters, intervals are descriptive and interpreted cautiously.

## 6. Frozen predictive sensitivity

Predictive validation is secondary and exploratory. For every method and
index on the primary common support, fit:

`log10(CHLF) = intercept + slope × index`

using ordinary least squares with one outer calendar year held out. Predictor
standardization uses only the training years' mean and sample standard
deviation. There is no hyperparameter tuning. Predictions from all seven held
out years are retained.

Report held-out RMSE, MAE and R² in log10-CHLF units. A fold with insufficient
training/test support or a constant training predictor is explicitly
unavailable. This sensitivity evaluates a simple lake-specific proxy relation;
it is not an absolute transferable retrieval calibration.

## 7. Interpretation constraints

- The common-support analysis may compare methods descriptively, but v1.0
  does not authorize a single processor-winner declaration.
- Association does not establish causality or prove that NDCI/MCI is Chl-a.
- Results must report sample size and temporal support alongside every metric.
- The frozen 6/9 threshold, spatial support, QA masks and MCI wavelength rule
  cannot be changed after seeing Phase 6C results.
- No Vombsjön result may be inspected or used for tuning.
- Temporal reconstruction remains separate from raw satellite–reference
  validation.

## 8. Outputs and reproducibility

Phase 6C writes a complete matchup audit, long analysis-pair table,
association summaries, annual results, LOYO predictions and summaries,
figures, and a manifest under `results/phase6c/`.

The manifest records the protocol/config identities, input and output hashes,
repository commit, worktree state, software versions, support counts,
bootstrap settings and scientific guards. All CSV files use deterministic
LF-only serialization.
