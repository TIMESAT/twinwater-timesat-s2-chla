# Codex Task — Phase 3 Erken Reconstruction Implementation

## Repository

Work in:

`twinwater-timesat-s2-chla`

## Governing scientific documents

The scientific design has completed and frozen **Phase 2B-2**.

The governing files are:

- `Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`
- `Reconstruction_Analysis_Contract_v1.0.1.md`

The contract was frozen **before inspection of reconstruction performance**.

Your task is to implement the frozen reconstruction-analysis contract exactly as specified.

Do **not** optimize, simplify, reinterpret, or improve the scientific design.

If either governing file is absent from the repository, stop and report that first. Do not reconstruct the contract from memory or invent missing rules.

---

# 1. Objective

Implement the infrastructure required for the **Phase 3 Erken pure temporal-reconstruction benchmark**.

This task is initially an **implementation, reproducibility, and validation task**, not a scientific-results task.

Do not interpret reconstruction performance in this task.

The primary reconstruction benchmark contains exactly three methods:

1. **Linear interpolation**
2. **TIMESAT double logistic**, using the frozen TIMESAT source revision's unmodified effective defaults
3. **TIMESAT smoothing spline**

Do **not** add:

- GAM
- Whittaker
- Savitzky–Golay
- DINEOF
- DINCAE
- any other reconstruction method

---

# 2. Frozen Erken experimental design

## 2.1 Primary years

Use:

`2019, 2020, 2021, 2022, 2023, 2024, 2025`

These define **seven outer leave-one-year-out (LOYO) folds**.

The year is the primary independent seasonal/generalization unit.

Daily values and repeated artificial masks are nested observations, not independent ecological replicates.

## 2.2 Actual-mask sparse inputs

A primary Erken sparse input satisfies:

`S2 usable AND open_water AND finite CHLF`

Use the existing deterministic Phase 2B-1 temporal-sampling/join products as the authoritative observation layer.

Do not regenerate or redefine the Sentinel-2 usability rule.

Expected frozen total:

`288 actual-mask sparse input dates`

A calendar date is one temporal observation unit even if multiple Sentinel-2 products exist on that date.

All reconstruction methods must receive identical sparse dates and CHLF values.

## 2.3 Year-specific common support

For year `y`:

`D_y = open_water ∩ [first sparse input date_y, last sparse input date_y]`

Primary evaluation is restricted to `D_y`.

No method receives credit for extrapolation before the first sparse input or after the last sparse input.

If open-water support is discontinuous within `D_y`, preserve the physical separation of those segments where relevant, especially for integration.

Artificial-gap experiments must not move the frozen common-support boundaries.

---

# 3. Reconstruction methods

## 3.1 M1 — Linear interpolation

Implement a fixed deterministic linear-interpolation baseline.

Requirements:

- no hyperparameter tuning;
- use the observed sparse date-value pairs directly;
- evaluate only inside common support;
- no primary boundary extrapolation.

## 3.2 M2 — TIMESAT double logistic

Use the double-logistic method implemented in the frozen TIMESAT source revision used for this study.

Use that revision's **unmodified effective default configuration**.

No Erken-specific double-logistic tuning is allowed.

### Mandatory pre-run implementation gate

Before generating **any reconstruction-performance output**, create an immutable machine-readable snapshot containing:

- TIMESAT version and/or git commit;
- if commit metadata is unavailable, an immutable source/build checksum;
- every effective double-logistic default parameter value used at runtime;
- checksum of the frozen defaults snapshot.

This snapshot becomes the frozen primary configuration.

If runtime defaults differ from the frozen snapshot, execution must fail loudly.

Do not silently adopt changed defaults.

The complete daily Erken reference must **never** be used to:

- decide how many seasons or peaks the double-logistic method should fit;
- alter coarse-season detection;
- modify fitting configuration;
- tune any double-logistic parameter.

Coarse-season detection and double-logistic fitting must operate only on the sparse input available to the method.

Do not report only `"default settings"` in provenance. Materialize the actual values.

## 3.3 M3 — TIMESAT smoothing spline

The only tuned spline-control parameter in the primary contract is the TIMESAT smoothing parameter.

The frozen integer candidate grid is exactly:

`{0, 1, 3, 10, 30, 100, 300, 1000}`

`0` is retained as the interpolation limit.

Do not refine, expand, or narrow this grid after reconstruction performance is inspected.

---

# 4. Smoothing-spline parameter selection

## 4.1 Outer LOYO

Each year from 2019 through 2025 serves once as the outer test year.

The complete daily reference trajectory of the outer test year must not influence selection of the smoothing parameter used for that fold.

## 4.2 Inner selection

For each outer fold:

1. remove the outer test year from smoothing-parameter selection;
2. for each candidate smoothing value, reconstruct each of the six remaining years separately using that year's own sparse inputs;
3. evaluate each training year only on that year's withheld daily reference dates;
4. compute year-specific nRMSE;
5. give every training year equal weight;
6. select the candidate with the lowest mean year-level nRMSE.

No cross-year chlorophyll curve is fitted.

"Inner selection" means year-blocked evaluation of the global smoothing-control candidate using only outer-training years.

## 4.3 Tuning metric

For training year `y`:

`RMSE_y = sqrt(mean((C_hat_t - C_t)^2))`

`Scale_y = Q95(C_y) - Q05(C_y)`

`nRMSE_y = RMSE_y / Scale_y`

The quantiles are computed from the method-independent daily reference over that year's common support.

For candidate `s`:

`Score(s) = mean_y[nRMSE_y(s)]`

Every outer-training year has equal weight.

Do **not** use any of the following for spline tuning:

- peak timing
- peak magnitude
- integral error
- correlation
- onset/end
- any other seasonal metric

## 4.4 Tie and failure rules

- The numerically lowest mean year-level nRMSE wins.
- If candidates are exactly tied at stored numerical precision, choose the **smaller smoothing parameter**.
- If a candidate fails to produce a valid required reconstruction/nRMSE for any outer-training year, mark that candidate **ineligible for that outer fold**.
- Never silently remove the failed year and average the remaining years.
- If all spline candidates are ineligible for an outer fold, record a spline-selection failure.
- Do not invent a new smoothing candidate.

Different outer folds may legitimately select different smoothing parameters.

---

# 5. Point-wise evaluation

Primary point-wise evaluation dates satisfy:

`common_support AND open_water AND finite_reference AND NOT sparse_input_date`

Thus primary point-wise metrics are calculated only on genuinely withheld daily reference values.

For every method and outer year implement:

- bias
- MAE
- RMSE
- nRMSE

Use:

`nRMSE = RMSE / (Q95 - Q05)`

where `Q95 - Q05` is calculated from the method-independent common-support daily reference for that year.

If the scale is zero or non-finite:

- nRMSE is unavailable;
- record an explicit reason;
- do not introduce an arbitrary epsilon.

Retain daily residuals as diagnostic observations, but do not treat them as independent ecological replicates in across-year summaries.

---

# 6. Seasonal metrics

All seasonal metrics must be implemented independently of the reconstruction algorithms.

Do not use TIMESAT's own seasonal-output definitions as the reference truth.

Apply identical metric definitions to:

- the complete daily reference;
- linear reconstruction;
- TIMESAT double-logistic reconstruction;
- TIMESAT smoothing-spline reconstruction.

## 6.1 Primary candidate timing metric — common-support global peak

Define the peak as:

`global maximum within the year-specific common support`

For each reconstruction calculate:

- reference peak date;
- reconstructed peak date;
- signed peak-date error:
  `t_peak,recon - t_peak,ref`;
- absolute peak-date error;
- distance to nearest common-support boundary;
- reference boundary-peak flag;
- reconstruction boundary-peak flag.

### Equal-maximum rule

If the global maximum occupies one contiguous multi-day plateau:

- represent its peak date by the temporal midpoint of that plateau.

If two or more **non-contiguous** events have exactly equal global maxima:

- flag `ambiguous_equal_global_maxima`;
- primary peak timing is unavailable for that case;
- retain the year for other metrics.

If the reference global maximum occurs on the first or last date of common support:

- flag `reference_peak_at_boundary`;
- do not silently treat it as an ordinary fully identifiable peak-timing case.

Multi-peak years remain eligible.

The primary peak remains the global maximum.

### Secondary-event restriction

Do **not** implement, as primary Contract v1.0.1 outputs:

- secondary-peak prominence detection;
- minimum event separation;
- missing-secondary-peak counts;
- extra-secondary-peak counts;
- event-matching algorithms;
- event-switching classifications requiring an unfrozen detector.

Any such analysis requires a separate versioned supplementary event-detection protocol.

## 6.2 Peak magnitude

Implement:

- signed peak-magnitude error;
- absolute peak-magnitude error;
- normalized absolute peak-magnitude error using the same yearly `Q95 - Q05` scale when valid.

## 6.3 Common-support integral

Calculate reference and reconstructed integrals over identical common support.

Use daily trapezoidal integration.

If common support contains disconnected open-water segments:

- integrate each contiguous open-water segment separately;
- sum segment integrals;
- do not bridge ice/non-open-water intervals.

Report:

- signed integral error;
- absolute integral error;
- relative integral error only where the reference integral is finite and meaningfully non-zero.

## 6.4 Trajectory agreement

Implement Pearson correlation between reconstructed and reference daily trajectories over identical eligible common-support dates.

Treat this as a supporting trajectory-agreement metric, not a substitute for magnitude-sensitive error.

## 6.5 Onset/end

Onset/end are not primary headline metrics in this implementation task.

Do not introduce a new onset/end definition unless explicitly requested under a separately frozen sensitivity protocol.

---

# 7. Peak reliability

Continuous error distributions remain primary.

Primary binary peak-timing criterion:

`absolute peak-date error <= 10 calendar days`

Pre-specified sensitivity criteria:

- `<= 5 days`
- `<= 15 days`

Do not invent binary thresholds for:

- RMSE
- nRMSE
- peak magnitude
- integral
- correlation

---

# 8. Failure and implausibility handling

Never silently drop or repair failures.

Record explicit status and/or reason fields for, where applicable:

- non-convergence;
- missing reconstruction;
- invalid or undefined metric;
- insufficient prediction support;
- ambiguous equal global maxima;
- boundary peak;
- negative reconstructed values;
- minimum reconstructed value;
- number of negative reconstructed days;
- fraction of negative reconstructed days;
- TIMESAT-specific diagnostics/failure codes.

Negative reconstructed values must **not** be clipped to zero in the primary implementation.

Any future zero-clipping analysis must be labelled as sensitivity analysis.

A method failure remains part of the reliability result and must not disappear silently from denominators.

---

# 9. Controlled-gap infrastructure

Implement the controlled-gap generators, provenance, and tests in this task.

Do **not** run the full expensive controlled-gap experiment unless explicitly requested later.

All controlled-gap experiments begin from the frozen actual-Sentinel-2 sparse inputs.

They introduce additional missingness.

They do not replace the real sampling structure with a nominal 5-day sequence.

The first and last sparse input dates are protected.

All methods must receive identical artificial masks for a given year/scenario/replicate.

## 9.1 Random deletion

Frozen deletion proportions:

- `10%`
- `20%`
- `30%`
- `50%`

Use:

`100 replicates per year × deletion level`

Only interior sparse observations may be deleted.

Define interior observations as the chronologically sorted sparse inputs excluding that year's first and last sparse input.

Let:

- `N_interior` = number of eligible interior sparse observations;
- `p` = deletion fraction.

Frozen deletion count:

`n_delete = floor(p * N_interior + 0.5)`

bounded to:

`[0, N_interior]`

Frozen master seed:

`20260901`

Deletion-level index:

- `k = 1` → 10%
- `k = 2` → 20%
- `k = 3` → 30%
- `k = 4` → 50%

Replicate:

`r = 1,...,100`

Frozen seed formula:

`seed = 20260901 + 100000 * (year - 2019) + 1000 * k + r`

Canonical RNG:

`numpy.random.Generator(numpy.random.PCG64(seed))`

Canonical sampling:

- draw from the chronologically sorted interior-date array;
- use `choice(..., size=n_delete, replace=False)`;
- sort selected deleted dates before storage.

For every random mask save:

- year;
- deletion level;
- level index;
- replicate index;
- seed;
- `N_interior`;
- `n_delete`;
- deleted-date list;
- observations remaining;
- resulting observation density;
- resulting maximum internal gap.

Do **not** assign `A_gap` to random-deletion masks because scattered deletion does not define one contiguous hidden interval.

## 9.2 Consecutive internal gap windows

Frozen calendar durations:

- `10 days`
- `20 days`
- `30 days`
- `45 days`

Use exhaustive daily sliding windows.

For duration `L`, a window starting on date `t` covers:

`[t, t + L - 1 day]`

Retain a window only if:

- it lies entirely inside one contiguous open-water segment of frozen common support;
- it does not delete the year's first sparse input;
- it does not delete the year's last sparse input;
- it removes at least one sparse observation.

For every retained window record:

- year;
- duration;
- window start date;
- window end date;
- observations removed;
- deleted sparse dates;
- contains reference global peak;
- window midpoint date;
- window midpoint relative position;
- reference range inside the window;
- maximum absolute daily change inside the window;
- net start-to-end reference change;
- `A_gap`.

## 9.3 Window midpoint relative position

Define:

`window_midpoint_relative_position`

on `[0,1]` as:

the midpoint's elapsed time from the first date of its contiguous common-support segment divided by that segment's total elapsed duration.

If the support segment has zero duration, mark the value unavailable.

## 9.4 Frozen `A_gap`

`A_gap` applies only to consecutive internal gap windows.

For eligible window `[a,b]`:

`A_gap = sum_(t=a+1,...,b) abs(C_t - C_(t-1)) / (Q95_y - Q05_y)`

The numerator includes only transitions whose two dates are both inside `[a,b]`.

Do **not** include:

- the transition entering the window;
- the transition leaving the window.

If `Q95_y - Q05_y` is zero or non-finite:

- `A_gap` is unavailable;
- explicitly flag it;
- do not add epsilon.

Keep `A_gap` continuous in primary modelling.

If low/medium/high activity groups are later needed only for visualization, define them by `A_gap` tertiles **within each gap-duration class**.

Do not create a new weighted activity index.

Do not implement primary categorical labels such as:

- `rapid_rise`
- `rapid_decline`
- `secondary_event`

## 9.5 Controlled-gap spline setting

Do not retune the spline separately for each artificial gap.

For every controlled-gap scenario in a given outer year:

- use the smoothing parameter selected for that outer fold from the frozen actual-mask Erken-only selection procedure;
- linear interpolation remains fixed;
- double logistic remains on the frozen TIMESAT default configuration.

---

# 10. Reliability-envelope data products

Do not finalize an inferential statistical model in this implementation task unless already explicitly specified in the repository.

Prepare clean tables that support the frozen relationships.

For consecutive internal windows, retain variables needed for analyses of the form:

`error or success ~ method + gap duration + window_midpoint_relative_position + contains_reference_global_peak + A_gap + observations_removed + year structure`

For random deletion, retain variables needed for analyses of the form:

`error or success ~ method + deletion fraction + observations remaining/density + resulting maximum internal gap + year structure`

The final statistical summarization must respect year/replicate clustering.

Do not redefine frozen reconstruction targets or the peak-reliability threshold.

Do not claim a universal gap-length failure threshold.

---

# 11. Required implementation architecture

Inspect the existing repository structure first.

Reuse existing modules, naming conventions, CLI patterns, provenance design, and test structure where appropriate.

Do not create a disconnected parallel pipeline if existing infrastructure can be extended cleanly.

Implement, as appropriate:

- machine-readable reconstruction contract/config;
- common-support functions;
- metric-eligibility functions;
- linear reconstruction;
- TIMESAT double-logistic wrapper/interface;
- TIMESAT smoothing-spline wrapper/interface;
- TIMESAT defaults snapshot/freeze gate;
- nested LOYO spline-selection logic;
- point-wise metric functions;
- seasonal metric functions;
- deterministic random-deletion generator;
- exhaustive consecutive-gap generator;
- `A_gap` and window-diagnostic functions;
- provenance/failure schemas;
- CLI entry points consistent with the repository;
- unit tests;
- integration tests;
- documentation mapping every frozen contract rule to code.

Prefer deterministic, transparent intermediate products such as:

- CSV
- JSON
- Parquet

rather than opaque binary products.

Do not modify existing frozen Phase 2A or Phase 2B-1 observation-mask products.

---

# 12. Required provenance

Every experiment/output must retain enough information to reproduce it.

Include, where applicable:

- contract version;
- repository code commit;
- TIMESAT version/commit or source/build checksum;
- effective double-logistic defaults;
- checksum of the frozen defaults snapshot;
- spline candidate grid;
- selected spline value by outer fold;
- sparse input dates;
- support boundaries;
- outer test year;
- inner selection years;
- method;
- mask/scenario identifier;
- deletion level or gap duration;
- random seed;
- RNG specification;
- replicate identifier;
- deleted dates;
- reconstruction status;
- failure reason;
- metric eligibility flags;
- metric failure flags.

---

# 13. Mandatory tests

Tests must verify at minimum all of the following.

## 13.1 Year/fold structure

- 2019–2025 generate exactly seven outer folds.
- Each outer fold contains exactly one held-out year.
- The remaining six years are the only years available for spline parameter selection.

## 13.2 Sparse-input layer

- The authoritative Phase 2B-1 data produce exactly 288 actual-mask sparse input dates.
- Sparse-input eligibility is not regenerated or redefined.
- All three methods receive identical sparse dates and values.

## 13.3 Common support

- Common-support boundaries are method-independent.
- No primary prediction is scored outside common support.
- Artificial masks do not move frozen support boundaries.

## 13.4 Point-wise evaluation

- Sparse input dates are excluded from primary point-wise evaluation.
- Only open-water, finite-reference, common-support withheld dates are scored.
- nRMSE uses the frozen yearly `Q95 - Q05` denominator.
- Invalid scales produce explicit unavailable metrics rather than epsilon stabilization.

## 13.5 Spline grid and selection

- Spline grid is exactly:
  `{0,1,3,10,30,100,300,1000}`
- Outer-test daily reference cannot enter parameter selection.
- Peak metrics cannot enter spline tuning.
- Candidate scoring uses equal weighting of six year-level nRMSE values.
- Failed candidate-years cannot be silently dropped.
- Exact numerical ties choose the smaller smoothing parameter.
- No unlisted smoothing value can be introduced.

## 13.6 Double logistic

- The defaults snapshot exists before any performance execution.
- The snapshot contains TIMESAT version/commit or immutable checksum.
- The snapshot contains all effective double-logistic defaults.
- Runtime-default mismatch fails loudly.
- Complete daily reference cannot affect double-logistic configuration or season detection.

## 13.7 Peak metrics

- Global peak is calculated only inside common support.
- A contiguous equal-maximum plateau resolves to its temporal midpoint.
- Non-contiguous exactly equal global maxima return `ambiguous_equal_global_maxima`.
- Boundary peak flags are deterministic.
- No unfrozen secondary-event detector is invoked.

## 13.8 Failure handling

- Negative values are recorded, not clipped.
- Non-convergence and missing outputs remain visible.
- Undefined metrics receive explicit status/reason values.
- Method failures cannot disappear through silent row filtering.

## 13.9 Random deletion

- Frozen rounding rule is reproduced exactly.
- Frozen seed formula is reproduced exactly.
- NumPy `Generator(PCG64(seed))` is used.
- Same year/level/replicate always produces identical deleted dates.
- First and last sparse dates are never deleted.
- Sampling occurs without replacement.
- Stored deleted dates are chronologically sorted.

## 13.10 Consecutive gaps

- Window durations are exactly 10, 20, 30, and 45 calendar days.
- Windows are exhaustive daily sliding windows.
- Windows cannot cross an open-water discontinuity.
- First and last sparse inputs remain protected.
- Windows removing zero sparse observations are excluded.

## 13.11 `A_gap`

- `A_gap` is calculated only for consecutive windows.
- Only transitions fully inside the hidden window are included.
- Entry and exit transitions are excluded.
- Invalid `Q95-Q05` produces an explicit unavailable value.
- Random-deletion masks do not receive `A_gap`.

## 13.12 Determinism

- Repeated execution with identical inputs/configuration produces identical masks, fold definitions, selected parameters, provenance, and derived deterministic tables.

---

# 14. Pre-performance gate

Before producing any scientific reconstruction-performance comparison, verify and report:

1. governing contract detected as `Reconstruction_Analysis_Contract_v1.0.1`;
2. input observation/join products passed structural validation;
3. 288 sparse dates reproduced;
4. seven LOYO folds reproduced;
5. common-support rules reproduced;
6. TIMESAT double-logistic defaults snapshot created and frozen;
7. runtime defaults match the snapshot;
8. spline candidate grid matches the contract exactly;
9. random-mask reproducibility tests pass;
10. consecutive-window tests pass;
11. leakage-prevention tests pass;
12. deterministic rerun tests pass.

If any item fails, stop before performance generation.

---

# 15. Stop condition for this task

This task is **implementation and validation only**.

Do not:

- inspect which reconstruction method is best;
- rank the methods scientifically;
- tune anything based on outer-year performance;
- change the frozen contract because one method performs poorly;
- create performance figures intended for scientific interpretation;
- inspect Vombsjön results;
- retune anything using Vombsjön.

At the end of this task, report:

1. all files added or modified;
2. exact contract-to-code mapping;
3. tests executed and exact results;
4. TIMESAT version/default snapshot that was frozen;
5. any blocker or ambiguity;
6. whether all pre-performance gates passed;
7. explicit confirmation that no reconstruction-performance comparison was scientifically inspected or interpreted.

If the repository conflicts with `Reconstruction_Analysis_Contract_v1.0.1.md`, **stop and report the conflict instead of resolving it scientifically yourself**.

---

# 16. Expected completion state

A successful completion means:

- the frozen scientific contract has a transparent implementation;
- all critical leakage and determinism tests pass;
- TIMESAT double-logistic defaults are immutably captured;
- the repository is ready to run the first true Phase 3 Erken reconstruction benchmark;
- no performance-driven methodological decisions have yet been made.

Do not proceed to scientific interpretation until the implementation has been independently audited.
