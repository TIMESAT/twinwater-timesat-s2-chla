# Reconstruction Analysis Contract v1.0.1

**Project:** Incomplete Sentinel-2 Chlorophyll Time-Series Reconstruction  
**Status:** FROZEN before first reconstruction-performance comparison  
**Freeze date:** 2026-09-01  
**Patch status:** Clarification-only update before any reconstruction-performance inspection  
**Applies to:** Erken primary reconstruction experiments and the Erken-only selection stage before locked Vombsjön transfer  
**Scientific master:** `Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`

---

## 1. Purpose of this freeze

This contract fixes the analysis rules that could otherwise be changed after seeing reconstruction performance. It freezes the **experimental rules and parameter-selection procedures**, not necessarily a single final smoothing value. The first performance comparison may begin only after the implementation reproduces this contract and its tests.

A later, second freeze will select the final Erken-supported reconstruction settings for transfer to Vombsjön. Vombsjön results must not be used to retune methods, thresholds, masks, metric definitions or parameter-selection rules.

Any post-performance change to this contract requires a new version with an explicit change log and must be labelled as confirmatory, sensitivity or exploratory according to when and why the change was made.

---

## 2. Independent units and eligible years

### 2.1 Primary Erken years

Primary Erken reconstruction evaluation uses **2019–2025**, giving seven outer year-level folds.

The year is the primary independent seasonal/generalization unit. Daily values and repeated artificial masks are nested observations, not independent ecological replicates.

### 2.2 Boundary-truncated years

2019 and 2025 remain eligible for primary reconstruction evaluation within their observed/common support. They are not discarded at the year level.

Metric-specific restrictions apply:

- 2019 and 2025 are eligible for point-wise reconstruction error, common-support peak timing, common-support peak magnitude, trajectory agreement and common-support integral.
- No primary claim is made that the common-support maximum in 2019 or 2025 is the true full-calendar-year global maximum.
- Metrics requiring complete seasonal boundaries, including full-season onset/end or full-calendar-year integral, are not primary metrics for these boundary-truncated records.
- Onset/end metrics are secondary/sensitivity metrics for the project in general.

---

## 3. Primary sparse input and common support

### 3.1 Actual-Sentinel-2 primary sparse input

For an Erken date to be a primary sparse input it must satisfy all of the following:

1. frozen Sentinel-2 date-level scene QC says the date is usable;
2. `open_water == True`;
3. the daily CHLF reference value is finite/available.

This is the existing `s2_openwater_reference_candidate` logic. Under the frozen Phase 2B-1 join it yields **288 actual-mask sparse inputs** across 2019–2025.

All reconstruction methods receive identical input dates and CHLF values. A calendar date is one temporal observation unit even if multiple Sentinel-2 products exist on that date.

### 3.2 Year-specific common support

For year `y`, define:

`D_y = open_water ∩ [first sparse input date_y, last sparse input date_y]`

Primary evaluation is restricted to `D_y`.

No method receives credit for extrapolation before the first sparse input or after the last sparse input. Artificial-gap experiments do not move these boundaries.

If the physical open-water domain is interrupted within `D_y`, disconnected open-water segments remain physically separated for integration and related support calculations; no integral is bridged across ice/non-open-water intervals.

---

## 4. Reconstruction methods

The primary benchmark contains exactly three reconstruction strategies.

### M1 — Linear interpolation

- Fixed deterministic baseline.
- No hyperparameter tuning.
- Uses the observed sparse date-value pairs directly.
- Predictions are evaluated only inside the common support; no primary boundary extrapolation.

### M2 — TIMESAT double logistic

- Use the double-logistic method implemented in the frozen TIMESAT source revision used for the study.
- Use that revision's **unmodified effective default configuration** for double-logistic fitting; no Erken-specific double-logistic tuning is allowed in the primary analysis.
- **Pre-run implementation gate:** before any reconstruction-performance output is generated, the implementation must materialize a machine-readable snapshot containing the TIMESAT version/commit (or, if unavailable, an immutable source/build checksum) and every effective double-logistic default parameter value. That snapshot becomes the frozen configuration for all primary Erken runs.
- If runtime defaults differ from the frozen snapshot, execution must fail rather than silently adopting changed defaults.
- Coarse-season detection and double-logistic fitting must operate only on the sparse input available to the method. The complete daily Erken reference must not be used to tell the method how many seasons/peaks to fit or to alter the fitting configuration.
- “Default settings” alone is insufficient for final reproducibility reporting.

### M3 — TIMESAT smoothing spline

The only tuned spline-control parameter in the primary contract is the TIMESAT smoothing parameter.

The frozen integer candidate grid is:

`{0, 1, 3, 10, 30, 100, 300, 1000}`

`0` is retained as the interpolation limit. The grid must not be refined, expanded or narrowed after reconstruction performance is inspected for the primary analysis.

---

## 5. Smoothing-spline parameter selection

### 5.1 Outer year-level evaluation

Each year from 2019 through 2025 serves once as the outer test year. Its complete daily reference trajectory must not influence selection of the smoothing parameter used to evaluate that outer fold.

### 5.2 Inner selection over the six outer-training years

For a given outer fold:

1. remove the outer test year from parameter selection;
2. for each candidate smoothing value, reconstruct each of the remaining six years separately from that year’s own sparse inputs;
3. evaluate each reconstructed training year on its withheld daily reference dates using year-specific nRMSE;
4. give each of the six years equal weight; and
5. select the candidate with the lowest mean year-level nRMSE.

No cross-year chlorophyll curve is fit. “Inner selection” refers to year-blocked evaluation of the global smoothing-control candidate using only outer-training years.

### 5.3 Tuning metric

For year `y`:

`RMSE_y = sqrt(mean((C_hat_t - C_t)^2))`

`Scale_y = Q95(C_y) - Q05(C_y)`

`nRMSE_y = RMSE_y / Scale_y`

The quantiles are computed from the method-independent daily reference over the year-specific common support.

For candidate `s`:

`Score(s) = mean_y[nRMSE_y(s)]`

where the mean gives equal weight to each outer-training year.

Peak timing, peak magnitude, integral error, correlation and any other seasonal metric are **not** used to tune the smoothing parameter.

### 5.4 Tie and failure rule during parameter selection

- The numerically lowest mean year-level nRMSE wins.
- If candidates are exactly tied at the stored numerical precision, choose the **smaller smoothing parameter**.
- A candidate that fails to produce a valid required reconstruction/nRMSE for any outer-training year is ineligible for that outer fold rather than being scored after silently dropping the failed year.
- If all spline candidates are ineligible in an outer fold, record a spline-selection failure for that fold; do not improvise a new candidate value.

Different outer folds may legitimately select different smoothing parameters.

---

## 6. Point-wise evaluation

### 6.1 Evaluation dates

Primary point-wise performance is computed only at dates satisfying:

`common support AND open_water AND reference available AND NOT sparse input date`

Thus the primary point-wise scores evaluate genuinely withheld daily reference values rather than fit at reconstruction input dates.

### 6.2 Primary point-wise metrics

For every method and outer year report:

- bias;
- MAE;
- RMSE; and
- nRMSE using `Q95 - Q05` of the common-support reference as the scale.

If the scale is zero, non-finite or otherwise invalid, nRMSE is unavailable and the case is explicitly flagged; no arbitrary epsilon is introduced.

Across-year summaries are based first on year-level metrics. Daily residuals may be shown diagnostically but must not be treated as independent ecological replicates.

---

## 7. Seasonal metrics

All seasonal metrics are defined externally to the reconstruction algorithms and applied identically to the daily reference and each reconstructed trajectory over the same support.

### 7.1 Primary candidate seasonal timing metric — common-support peak date

The peak is the **global maximum within the year-specific common support**.

For each reconstruction report:

- signed peak-date error: `t_peak,recon - t_peak,ref`;
- absolute peak-date error;
- peak distance to the nearest common-support boundary; and
- reference/reconstruction boundary-peak flags.

#### Equal maxima / plateau rule

- If the global maximum occupies one contiguous multi-day plateau, the peak date is the temporal midpoint of that plateau.
- If two or more non-contiguous events have exactly equal global maxima, peak timing is flagged `ambiguous_equal_global_maxima` and is unavailable for the primary peak-date metric; the year remains eligible for other metrics.
- If the reference global maximum occurs at the first or last day of common support, flag `reference_peak_at_boundary`; do not treat it as an ordinary fully identifiable peak-timing case.

Multi-peak years are retained. The primary peak is the global maximum; no year is excluded simply because secondary peaks exist.

**Secondary-event rule:** Contract v1.0.1 does not freeze a prominence threshold, minimum event separation or event-matching tolerance for secondary peaks. Therefore missing/extra-secondary-peak counts and event-switching classifications are **not primary v1.0.1 outputs**. Any event-level analysis requires a separate, versioned supplementary event-detection rule frozen before event-level performance is inspected.

### 7.2 Peak magnitude

Report the signed and absolute peak-magnitude error. Also report normalized absolute peak-magnitude error using the same `Q95 - Q05` reference scale when valid.

### 7.3 Common-support integral

Compute reference and reconstructed integrals over identical common support. Use daily trapezoidal integration within each contiguous open-water segment and sum segment integrals. Do not bridge ice/non-open-water gaps.

Report signed and absolute integral error. Relative error may be reported when the reference integral is finite and meaningfully non-zero.

### 7.4 Trajectory agreement

Use Pearson correlation between the reconstructed and reference daily trajectories over identical eligible common-support dates as a supporting shape/agreement metric. It does not replace magnitude-sensitive point-wise metrics.

### 7.5 Onset/end

Onset/end are not primary headline outcomes in this contract. They may be evaluated as pre-labelled sensitivity/secondary analyses only with a method-independent definition and with explicit recognition of boundary truncation and variable/index interpretation.

---

## 8. Reliability definition

Continuous error distributions remain primary.

The primary binary peak-timing reliability criterion is:

`absolute peak-date error <= 10 calendar days`

Pre-specified sensitivity thresholds are:

`<= 5 days` and `<= 15 days`

No primary binary success thresholds are defined for RMSE/nRMSE, peak magnitude, integral or correlation unless an independent monitoring/use-case justification is established in a later, explicitly labelled sensitivity analysis. Such thresholds must not be invented after seeing performance and then presented as confirmatory.

---

## 9. Failure and implausibility handling

Primary analysis must never silently drop or repair method failures.

Explicitly record, as applicable:

- non-convergence;
- missing reconstruction output;
- invalid/undefined metric;
- insufficient prediction support;
- ambiguous equal global maxima;
- boundary peak;
- negative reconstructed values;
- minimum reconstructed value and number/fraction of negative days; and
- method-specific diagnostic/failure codes.

Negative reconstructed values are **not clipped to zero** in the primary analysis. A zero-clipping analysis, if later scientifically useful, must be labelled sensitivity analysis.

A method failure remains part of the reliability result; it must not be removed from denominators without an explicitly reported reason and matching failure count.

---

## 10. Controlled-gap experiments

Controlled gaps are secondary to the actual Sentinel-2 mask and are used to explain when/why reconstruction reliability degrades.

### 10.1 Starting point

All controlled-gap experiments begin from the year’s frozen actual-Sentinel-2 sparse input. They introduce additional missingness; they do not replace the observed sampling structure with an idealized nominal five-day sequence.

The first and last sparse input dates are protected from artificial deletion so that controlled gaps do not alter the frozen common-support boundaries.

All methods receive exactly the same artificial mask for a given year/scenario/replicate.

### 10.2 Random deletion

Frozen deletion proportions:

`10%, 20%, 30%, 50%`

- Delete only interior sparse observations, defined as the chronologically sorted sparse inputs excluding the first and last sparse input of that year.
- Use **100 replicates** per `year × deletion level`.
- Frozen master seed: `20260901`.
- Let `N_interior` be the number of eligible interior sparse observations and `p` the deletion proportion. The target deletion count is `n_delete = floor(p × N_interior + 0.5)`, bounded to `[0, N_interior]`.
- Deletion-level index `k = 1,2,3,4` corresponds respectively to `10%,20%,30%,50%`; replicate index `r = 1,...,100`.
- The replicate seed is frozen as `seed = 20260901 + 100000 × (year - 2019) + 1000 × k + r`.
- The canonical random draw is from the chronologically sorted interior-date array using NumPy `Generator(PCG64(seed)).choice(..., size=n_delete, replace=False)`. Selected dates are sorted before storage.
- Save `N_interior`, `n_delete`, `seed` and the deleted-date list in the experiment output/manifest.
- `A_gap` is not assigned to random-deletion masks because they do not define a single contiguous hidden interval. Random-deletion results are instead characterized by deletion fraction/count and the resulting temporal sampling diagnostics (including observation count/density and maximum internal gap).

### 10.3 Consecutive internal gap windows

Frozen calendar durations:

`10, 20, 30, 45 days`

Use exhaustive sliding calendar windows rather than sampling a small number of random positions.

For duration `L`, a window beginning on date `t` covers `[t, t + L - 1 day]`.

Retain only windows that:

- lie entirely within a single contiguous open-water segment of the frozen common support;
- do not delete the first or last sparse input; and
- delete at least one sparse observation.

Record both calendar-window duration and the number of sparse observations actually removed.

### 10.4 Gap position and reference-derived annotations

Do not create a separate manually chosen set of “rise/peak/decline gaps” for the primary controlled experiment. Instead, characterize every exhaustive consecutive-gap window using objective quantities derived from the complete hidden Erken reference.

Frozen primary annotations/diagnostics are:

- `contains_reference_global_peak`;
- `window_midpoint_date`;
- `window_midpoint_relative_position`, defined on `[0,1]` as the window midpoint's elapsed time from the first date of its contiguous common-support segment divided by that segment's total elapsed duration (set unavailable for a zero-duration segment);
- reference range inside the window;
- maximum absolute daily change inside the window; and
- net start-to-end reference change inside the window.

No primary `rapid_rise`, `rapid_decline`, `low_activity` or `secondary_event` categorical labels are defined in v1.0.1. Low/medium/high activity classes, if needed for visualization, are derived only from the frozen duration-specific `A_gap` tertile rule in Section 10.5. Any additional phase/event classifier requires a separate versioned rule frozen before its performance relationship is inspected.

The complete reference may be used only to characterize what was hidden by an artificial gap; it must not be supplied to the reconstruction method.

### 10.5 Primary gap-activity variable

`A_gap` is defined for each **consecutive internal gap window** only. For an eligible calendar window `[a,b]` lying within one contiguous open-water support segment:

`A_gap = sum_(t=a+1,...,b) |C_t - C_(t-1)| / (Q95_y - Q05_y)`

Thus the numerator contains only day-to-day transitions whose two dates both lie inside the hidden window; the transition entering the window and the transition leaving the window are not included. `C_t` is the complete daily Erken reference and the denominator is the robust common-support reference amplitude for that year.

If `Q95_y - Q05_y` is zero or non-finite, `A_gap` is unavailable and explicitly flagged; no epsilon is added.

Supporting window diagnostics include:

- reference range inside the window;
- maximum absolute daily change inside the window;
- net start-to-end change;
- whether the global reference peak lies inside the window;
- window midpoint relative position; and
- number of sparse observations removed.

Do not create a new weighted activity score after performance is seen.

`A_gap` remains continuous in primary modelling. If low/medium/high activity categories are needed for visualization, define them by tertiles **within each gap-duration class** so that duration and accumulated total variation are not mechanically conflated.

### 10.6 Spline setting under controlled gaps

Do not re-tune the spline separately for each artificial gap.

For each outer year, use the smoothing parameter selected for that outer fold by the actual-mask Erken-only selection procedure in Section 5. Linear interpolation remains fixed; double logistic remains on the frozen TIMESAT default configuration.

---

## 11. Primary reliability-envelope covariates

The two controlled experiment families are summarized separately because a contiguous hidden window and scattered random deletion do not share the same gap descriptors.

For consecutive internal windows, primary covariates are of the form:

`error or success ~ method + gap duration + window_midpoint_relative_position + contains_reference_global_peak + A_gap + observations_removed + year structure`

For random deletion, primary covariates are of the form:

`error or success ~ method + deletion fraction + observations remaining/density + resulting maximum internal gap + year structure`

The exact statistical model used to summarize these envelopes may be implemented after the reconstruction outputs exist, but it must respect year/replicate clustering and must not redefine the frozen reconstruction targets or success threshold.

Primary interpretation is empirical and metric-specific. Do not claim a universal gap-length failure threshold.

---

## 12. Second freeze before Vombsjön

After Erken LOYO and controlled-gap results are complete:

1. choose the final Erken-supported spline setting/workflow using the pre-specified evidence hierarchy;
2. retain the fixed TIMESAT double-logistic default benchmark/configuration as implemented;
3. retain all observation-mask, common-support, metric, failure and reliability rules from this contract unless a versioned sensitivity change is explicitly declared;
4. create a dated machine-readable freeze manifest; and
5. only then inspect Vombsjön transfer performance for the locked test.

No Vombsjön result may be used to retune Erken-derived settings.

---

## 13. Required implementation provenance

The repository implementation must write or retain enough information to reconstruct every experiment, including:

- contract version;
- code commit;
- TIMESAT version/commit;
- effective TIMESAT double-logistic defaults and frozen defaults-snapshot checksum;
- spline candidate grid;
- selected spline value by outer fold;
- all sparse input dates;
- support boundaries;
- outer test year and inner selection years;
- mask/scenario identifier;
- random seed, RNG specification and replicate identifier;
- reconstruction/failure status; and
- metric-eligibility/failure flags.

The implementation must contain tests showing that outer-test daily reference values cannot leak into smoothing-parameter selection or TIMESAT double-logistic configuration/season detection.

---

## 14. Frozen decisions summary

**Methods:** Linear interpolation; TIMESAT double logistic (default); TIMESAT smoothing spline.  
**Years:** 2019–2025, seven outer year-level folds.  
**Actual-mask sparse inputs:** frozen S2 usable + open water + finite CHLF; 288 dates under current join.  
**Common support:** open water between first and last sparse input within year; no primary extrapolation.  
**Spline grid:** `{0, 1, 3, 10, 30, 100, 300, 1000}`.  
**Spline selection:** Erken-only outer-training years; equal-year mean withheld-day nRMSE; peak metrics excluded from tuning.  
**Peak metric:** common-support global maximum date.  
**Peak reliability:** primary ±10 d; sensitivity ±5 d and ±15 d.  
**Random deletion:** 10/20/30/50%, 100 replicates, frozen rounding/seed/RNG algorithm from Section 10.2.  
**Consecutive gaps:** exhaustive internal 10/20/30/45-calendar-day windows.  
**Gap activity:** normalized within-window total variation `A_gap` for consecutive gaps only.  
**Failures:** explicit; no silent deletion; no primary negative clipping.  
**Transfer:** second Erken-only freeze before Vombsjön; no Vomb retuning.

---

## 15. Change log

- **v1.0 — 2026-09-01:** First frozen reconstruction-analysis contract. Replaces the provisional Phase 2B-2 rules in Project Master v4.2. Primary benchmark set to linear interpolation, TIMESAT multi-season/default double logistic, and TIMESAT smoothing spline; freezes seven-year Erken LOYO, common-support evaluation, spline integer grid and year-blocked selection rule, peak timing tolerance, failure handling, and controlled-gap protocol.
- **v1.0.1 — 2026-09-01:** Clarification-only patch made before any reconstruction-performance inspection. Requires a pre-run immutable snapshot of TIMESAT double-logistic defaults; fixes the random-deletion rounding, seed derivation and RNG; restricts consecutive windows to a single contiguous open-water segment; defines the exact within-window `A_gap` summation; separates random-deletion from consecutive-gap reliability covariates; and removes undefined rapid-rise/decline and secondary-event classifications from primary v1.0.1 outputs. No frozen scientific method, year, spline grid, peak tolerance or gap-duration/deletion scenario was changed.
