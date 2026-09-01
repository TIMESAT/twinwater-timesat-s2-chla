# Incomplete Sentinel-2 Chlorophyll Time-Series Reconstruction — RSE Project Master v4.3.1

**Status:** Current master research framework  
**Version:** v4.3.1  
**Decision date:** 2026-09-01  
**Target journal:** *Remote Sensing of Environment* (RSE) — aspirational target  
**Core scientific contribution:** Metric-specific reliability of reconstructed seasonal dynamics under incomplete observations  
**Reconstruction benchmark:** linear interpolation, TIMESAT double-logistic reconstruction, and TIMESAT smoothing-spline reconstruction  
**Evaluation principle:** seasonal metrics and evaluation support are defined independently of reconstruction method; TIMESAT provides the double-logistic and smoothing-spline implementations used here but does not define metric truth or evaluation support
**Temporal-development/reference lake:** Erken, Sweden  
**Locked transfer / extreme-regime test lake:** Vombsjön, Skåne, Sweden

---

## 0. Clarification patch from v4.3

Version 4.3 retains the two-lake architecture and metric-specific reliability framework established in v4.2:

- **Erken = temporal reconstruction development, calibration and dense/high-frequency temporal-reference site**
- **Vombsjön = locked out-of-domain transfer site and extreme-regime stress test**

This clarification patch does not add a third lake, expand the benchmark into a model zoo, or convert the paper into an absolute cross-lake Chl-a retrieval study. TIMESAT remains an implementation platform rather than the organizing framework of the paper: it provides the double-logistic and smoothing-spline reconstructions, while the evaluation domain and seasonal metrics remain method-independent.

### 0.1 What is retained from v4.3

- Erken provides the daily reference record used to isolate sampling and temporal-reconstruction uncertainty.
- Vombsjön remains untouched during Erken method development and parameter selection.
- Satellite proxy/retrieval validation remains lake-specific.
- The compact primary benchmark is now **linear interpolation, TIMESAT double logistic, and TIMESAT smoothing spline**. GAM is removed from the primary benchmark.
- The primary realistic experiment uses actual usable Sentinel-2 observation dates.
- Controlled random deletion and exhaustive internal consecutive-gap windows remain secondary experiments; consecutive windows are characterized by objective relative position, global-peak containment and hidden-reference activity rather than by a separately hand-picked phase-gap set.
- Vomb 2018 remains an extreme high-amplitude / altered-community stress test.
- Field reference, observed satellite proxy and reconstructed daily estimate remain separate data layers.

### 0.2 Clarifications in v4.3.1

Version 4.3.1 is a clarification-only patch made before any reconstruction-performance inspection. It does **not** change the frozen years, methods, spline grid, peak-timing tolerance, random-deletion levels or consecutive-gap durations. It:

1. updates governance references to `Reconstruction_Analysis_Contract_v1.0.1.md`;
2. states correctly that TIMESAT provides both the double-logistic and smoothing-spline implementations, while evaluation remains method-independent;
3. requires an immutable pre-run snapshot of the effective TIMESAT double-logistic defaults/version before any performance output is generated;
4. fixes the random-deletion rounding, seed-derivation and RNG algorithm;
5. defines `A_gap` exactly as within-window total variation for consecutive windows only and requires each consecutive window to lie inside one contiguous open-water support segment;
6. replaces undefined rapid-rise/rapid-decline/secondary-event primary categories with objective gap-position and hidden-reference diagnostics; and
7. removes undefined secondary-event omission/matching outputs from the primary contract unless a separate event-detection protocol is frozen before event-level performance is inspected.

---

## 1. Core paper question and contribution

The paper must not be framed as:

- the first use of TIMESAT for aquatic phenology or the validation of TIMESAT as software;
- the first attempt to fill gaps in inland-water remote-sensing data;
- a contest to identify a universally best gap-filling algorithm; or
- a claim that reconstructed daily values are daily satellite observations.

The central question is:

> **Under realistic incomplete Sentinel-2 observation patterns, which seasonal characteristics of chlorophyll-sensitive time series remain reliable, under what combinations of gap duration, gap position and underlying temporal activity, and how well do those conclusions transfer to a contrasting lake without retuning?**

The key comparison is:

> **Point-wise reconstruction accuracy versus seasonal-metric accuracy.**

A method can have acceptable RMSE while shifting the seasonal peak, attenuating its magnitude, merging two peaks or missing a short event. Conversely, a curve with moderate point-wise error may still preserve the seasonal timing metric needed for monitoring. The paper therefore treats reliability as **metric-specific**, not as a single property of a reconstructed curve.

### 1.1 Research questions

#### RQ1 — Observation layer

Do lake-specific Sentinel-2 chlorophyll-sensitive indices contain defensible information about field Chl-a after atmospheric, spatial and matchup-quality controls?

#### RQ2 — Reconstruction layer

How do linear interpolation, TIMESAT double-logistic reconstruction and TIMESAT smoothing-spline reconstruction perform under actual Sentinel-2-like sampling when evaluated against the Erken daily reference series using common, method-independent evaluation rules?

#### RQ3 — Metric specificity

Do method rankings and reliability conclusions differ between point-wise errors and seasonal metrics such as peak timing, peak magnitude, trajectory shape and seasonal integral?

#### RQ4 — Reliability envelope

How does the probability of meeting a pre-specified metric tolerance change with observation density, maximum gap length, gap position and the temporal activity hidden within the gap?

#### RQ5 — Locked transfer

When the full workflow is frozen in Erken, how reliably does it reconstruct withheld Sentinel-2 observations in Vombsjön, and are the reconstructed seasonal patterns ecologically consistent with the available field Chl-a record?

### 1.2 Reviewer-proof literature positioning

#### Palmer et al. (2015)

Palmer et al. already used TIMESAT with ten years of MERIS observations to derive phytoplankton phenology metrics in Lake Balaton, compared smoothing approaches and evaluated mapped metrics against in situ Chl-a phenology. TIMESAT is therefore treated here as an established implementation platform rather than as the conceptual center of the study; in this benchmark it supplies both the double-logistic and smoothing-spline reconstructions. Consequently:

- aquatic use of TIMESAT is not the novelty;
- extracting bloom start, peak, end, duration or integral from water-colour time series is not by itself the novelty; and
- the paper must cite Palmer et al. directly and state how the present estimand differs.

The present paper instead focuses on **how reliably individual seasonal metrics survive incomplete, Sentinel-2-like observation patterns**, using method-independent metric definitions, a dense daily reference experiment, year-level independence, activity-aware gap characterization and locked transfer.

#### Si et al. (2025)

Si et al. systematically compared Kriging, Savitzky–Golay filtering, DINEOF and DINCAE for reconstructing missing inland-water Chl-a data in Lake Taihu. Therefore:

- inland-water gap filling is not an unoccupied research area;
- algorithm comparison alone is insufficient novelty; and
- this study should not imply that three one-dimensional smoothers represent the full gap-filling literature.

The present benchmark is deliberately scoped to **one-dimensional seasonal trajectories** at stable water regions/station neighbourhoods. Its contribution is the contrast between point-wise and metric-level reliability and the empirical reliability envelope, not a leaderboard against image-scale spatiotemporal reconstruction methods.

#### Goodrich et al. (2026)

Goodrich et al. reviewed 122 Sentinel-2 aquatic Chl-a studies and identified limitations in validation evidence, geographic/individual-waterbody focus, methodological reporting and reproducibility. This study responds by requiring:

- explicit separation of retrieval and reconstruction validation;
- transparent scene, mask, matchup and quality-control provenance;
- year-level independent evaluation;
- a frozen cross-lake transfer test;
- standard point-wise performance statistics plus metric-specific outcomes;
- reproducible configurations, seeds, scene inventories and analysis outputs; and
- cautious claims that do not turn one transfer lake into universal validation.

### 1.3 Defensible novelty statement

The preferred novelty statement is:

> **This study quantifies the metric-specific reliability of one-dimensional seasonal chlorophyll-sensitive Sentinel-2 trajectories under realistic incomplete observations, identifies an empirical reliability envelope conditioned on gap length, gap position and underlying temporal activity, and tests a workflow frozen with a dense multi-year temporal reference in a contrasting lake.**

Do not use stronger “first-ever” language unless a formal systematic search later supports it.

---

## 2. Roles of the two lakes

### 2.1 Erken — temporal reconstruction development and dense/high-frequency reference site

Erken is used to develop and evaluate the **temporal reconstruction layer**.

Primary purposes:

- use the daily chlorophyll-fluorescence-derived series as a dense/high-frequency temporal reference;
- simulate Sentinel-2-like sparse sampling without initially introducing satellite retrieval error;
- compare reconstruction methods under identical sparse observation patterns;
- select and freeze reconstruction settings, including smoothing-spline settings implemented in TIMESAT, using year-level independent evaluation;
- quantify point-wise reconstruction error;
- quantify errors in seasonal timing, magnitude, integral and trajectory shape;
- estimate metric-specific reliability limits under realistic and controlled gaps;
- test whether gap activity explains failures that gap duration alone does not; and
- establish the frozen workflow before any Vomb transfer analysis is inspected for tuning.

Erken is **not** used to define an absolute Chl-a retrieval equation that is automatically transferred to Vombsjön.

#### Erken daily reference — known properties

The active SITES file covers:

- 2019-04-17 to 2025-11-30;
- daily temporal resolution;
- CHLF in µg L⁻¹; and
- an ice-presence flag.

The file header states that:

- fluorescence is corrected using weekly manually sampled laboratory chlorophyll;
- hourly data are collected, but the reported daily value is the 00:00 measurement to minimize non-photochemical quenching;
- CHLF comes from different measurement configurations over time;
- 2023 onward includes the Malma Island pumping system at 3 m depth; and
- extrapolated values between laboratory measurements may occur.

Therefore the series must be described as a **dense or high-frequency pelagic chlorophyll temporal reference**. It is not a literal daily Sentinel-2 surface reference, and it does not remove depth, spatial-support, platform-change or measurement-model uncertainty.

These limitations do not prevent its use for temporal reconstruction experiments because the primary Erken experiment reconstructs the same field-reference variable from masked versions of itself. They do limit any claim that the experiment directly validates satellite retrieval accuracy.

### 2.2 Vombsjön — locked transfer and extreme-regime stress-test site

Vombsjön is used for:

- independent lake-specific Sentinel-2 proxy/retrieval validation;
- application of the frozen temporal reconstruction workflow;
- primary quantitative transfer testing through withheld Sentinel-2 observations;
- testing transferability to a contrasting trophic and optical regime;
- stress-testing performance during an extreme high-amplitude bloom year; and
- examining whether phytoplankton community composition is associated with index–Chl-a residuals or reconstruction behaviour.

Do not retune reconstruction methods, parameters, metric definitions, tolerances, quality thresholds or gap scenarios because Vombsjön performs worse.

Vombsjön is an out-of-domain stress test, not a matched ecological control for Erken. A result from two Swedish lakes is evidence of transfer between these two systems, not proof of universal lake-scale generality.

---

## 3. Data model: keep observation, retrieval and reconstruction layers separate

The project must maintain three distinct data concepts.

### 3.1 Field reference

Examples:

- Erken daily CHLF / corrected chlorophyll temporal reference;
- Vombsjön fluorometric Chl-a observations.

Field records have their own measurement, depth, spatial-support and temporal-representativeness uncertainty.

### 3.2 Satellite observation / proxy

Examples:

- ACOLITE-derived reflectance;
- NDCI;
- MCI; and
- other chlorophyll-sensitive indices retained after pre-specified screening.

These are **observed satellite quantities**, not daily estimates and not automatically Chl-a concentration.

### 3.3 Reconstructed time series

Examples:

- TIMESAT smoothing-spline daily reconstruction;
- TIMESAT double-logistic daily reconstruction; and
- linear-interpolation daily reconstruction.

These are **model-reconstructed daily estimates**, never “daily satellite observations.”

### 3.4 Required identifiers and provenance

Every analysis-ready record should retain, where applicable:

- lake, station/region and date-time;
- source layer: field, observed satellite or reconstructed;
- Sentinel-2 product/scene identifier;
- atmospheric-correction method and version;
- extraction geometry and spatial statistic;
- valid-water pixel count and fraction;
- cloud, shadow, glint, ice and shoreline quality flags;
- observation-mask scenario and replicate identifier;
- reconstruction method and parameter/configuration identifier;
- LOYO fold and training/test-year status; and
- code version, data version and random seed.

---

## 4. Validation architecture

### Validation A — lake-specific satellite/proxy validation

For each lake separately:

**observed Sentinel-2 proxy ↔ field chlorophyll**

Purpose:

- establish that the observed satellite proxy contains relevant chlorophyll information;
- quantify observation/retrieval uncertainty before temporal reconstruction is evaluated; and
- determine whether proxy interpretation differs between lakes or bloom regimes.

Do not use any temporal reconstruction method, including the TIMESAT spline implementation, to replace raw satellite–field validation.

For Vombsjön, use the harmonized matchup table:

`Vombsjon_S2_field_matchup_master.csv`

Spatial extraction should prioritize actual field GPS when available. When actual GPS is unavailable, the paper nominal station may be used with explicit provenance.

Retrieval/proxy models and transformations must be validated within lake. An absolute Erken calibration cannot be transferred to Vombsjön without a separate, explicit transfer experiment.

### Validation B — pure temporal reconstruction calibration and evaluation in Erken

This is the cleanest temporal experiment.

Start with the eligible complete daily Erken reference curve:

**complete daily reference curve**

Apply a sparse observation mask:

**complete daily reference → sparse samples at Sentinel-2-like dates**

Reconstruct with:

- linear interpolation;
- TIMESAT double logistic using the frozen default configuration; and
- TIMESAT smoothing spline using the frozen integer candidate grid and Erken-only year-blocked selection rule.

Compare each reconstruction with the withheld portions of the complete daily reference.

This experiment isolates:

> **sampling-pattern and temporal-reconstruction uncertainty**

from:

- atmospheric correction;
- index-to-Chl relationship;
- satellite retrieval error;
- spatial mismatch; and
- field–satellite measurement mismatch.

The primary mask must use actual usable Sentinel-2 observation dates after scene-level QC. A nominal five-day revisit schedule is not an acceptable substitute for the main experiment.

### Validation C — controlled gap experiments in Erken

Controlled experiments are secondary to the realistic Sentinel-2 mask and explain why and when reconstruction degrades. All controlled experiments begin from the frozen actual-Sentinel-2 sparse inputs; they do not replace the real sampling pattern with a nominal five-day sequence. The first and last sparse input dates are protected so that artificial missingness does not change common-support boundaries. All methods receive identical artificial masks.

#### C1. Random deletion

Frozen missing proportions are **10%, 20%, 30% and 50%** of eligible interior sparse inputs. Use **100 replicates** for every year × deletion level, with master seed `20260901`; deletion-count rounding, seed derivation and the canonical PCG64 random draw are fixed by Contract v1.0.1.

#### C2. Consecutive internal gaps

Frozen calendar durations are **10, 20, 30 and 45 days**. Use exhaustive sliding calendar windows rather than a small random sample of positions. Retain only windows that lie fully within one contiguous open-water segment of common support, preserve the first/last sparse input and remove at least one sparse observation. Report calendar duration and the number of sparse observations removed.

#### C3. Gap position and hidden-reference annotation

Do not create a separate manually selected set of rise/peak/decline gaps for the primary controlled analysis. Instead characterize every exhaustive consecutive-gap window with objective, frozen diagnostics: global-reference-peak containment, window midpoint date, relative midpoint position within its contiguous common-support segment, reference range, maximum absolute daily change and net start-to-end change.

No primary rapid-rise, rapid-decline or secondary-event categorical classifier is defined in v4.3.1. Low/medium/high activity classes, if needed for visualization, are defined only from duration-specific `A_gap` tertiles. Any additional phase/event classifier requires a separately versioned rule frozen before its performance relationship is inspected.

The complete reference is used only to characterize what was hidden; it is never supplied to the reconstruction method.

#### C4. Gap activity / underlying temporal change

Gap length alone is insufficient. A 20-day gap across a stable low period and a 20-day gap across a rapid bloom are not equivalent.

The frozen primary activity measure applies to consecutive windows only. For an eligible window `[a,b]`:

`A_gap = Σ_(t=a+1,...,b) |C_t − C_(t−1)| / (Q95_y − Q05_y)`

The numerator therefore includes only daily transitions whose two dates both lie inside the hidden window; entry/exit transitions are excluded. The denominator is the robust common-support reference amplitude for year `y`. If the denominator is zero/non-finite, the activity metric is unavailable and explicitly flagged rather than stabilized with an arbitrary epsilon.

Supporting diagnostics include reference range inside the window, maximum absolute daily change, net start-to-end change, reference-peak containment, relative midpoint position and number of sparse observations removed. `A_gap` is not assigned to scattered random-deletion masks; those are characterized by deletion fraction/count and resulting sampling-density/max-gap diagnostics. Do not create a weighted composite after seeing performance.

Keep `A_gap` continuous for primary modelling. If low/medium/high activity classes are needed for visualization, define them by tertiles within each gap-duration class.

**Important interpretation rule:** underlying gap activity is observable in the dense Erken validation experiment because the complete reference is retained. It is generally unknown inside a real operational cloud gap. It is therefore an explanatory and reliability-stratification variable, not an operational input.

For controlled gaps, do **not** re-tune the spline for each artificial mask. Use the smoothing parameter selected for that outer year by the frozen actual-mask Erken-only selection procedure. Linear interpolation remains fixed and double logistic remains on the frozen default TIMESAT configuration.

### Validation D — locked transfer to Vombsjön

After all method, parameter and metric decisions are completed using Erken only:

1. freeze analysis-season rules;
2. freeze quality-control and usable-observation rules;
3. freeze each reconstruction method and its settings;
4. freeze seasonal metric definitions, peak tie rules and tolerances;
5. freeze missingness scenarios and random seeds where applicable; and
6. apply the complete workflow to Vombsjön without retuning.

#### D1. Primary quantitative transfer validation — withheld Sentinel-2

Artificially withhold valid Vomb Sentinel-2 observations, reconstruct their index/proxy values and compare predictions with the withheld observed values.

The primary design should include both:

- isolated withheld observations; and
- blocks of consecutive observed dates or phase-relevant gaps, when the observed series supports them.

All methods must receive identical training observations and be evaluated at identical withheld dates. Whole acquisition dates, not individual pixels treated as independent samples, are the basic withholding units.

This test evaluates whether the **frozen one-dimensional reconstruction workflow transfers to another lake and satellite time series**. It does not provide an error-free reference because the withheld satellite observations still contain satellite observation uncertainty.

#### D2. Complementary ecological consistency check — field Chl-a

Use Vomb fluorometric Chl-a dates to examine:

- broad seasonal agreement;
- consistency of high and low states;
- whether a reconstructed peak is temporally compatible with field evidence;
- whether reconstruction/proxy residuals change with bloom regime or community composition; and
- whether the extreme 2018 season is qualitatively and quantitatively attenuated.

Vomb field data are too sparse to represent a complete daily reference curve. They must not be used as the primary quantitative validation of daily temporal reconstruction, exact onset/end, or an unobserved peak date.

### 4.1 Year-level independence and leave-one-year-out evaluation

The Erken record contains many daily values but seven annual records. The year/season is the independent replication unit for generalization claims.

Primary outer evaluation uses **2019–2025**, so every year serves once as the outer test year. The 2019 and 2025 records are boundary-truncated but remain eligible for common-support metrics; metrics requiring complete annual/seasonal boundaries are restricted rather than excluding the entire year.

For each outer fold:

- the outer test year's complete daily reference is unavailable to all parameter-selection decisions;
- linear interpolation uses no tuning;
- TIMESAT double logistic uses the frozen default configuration;
- the TIMESAT smoothing parameter is selected from `{0, 1, 3, 10, 30, 100, 300, 1000}` using only the six outer-training years;
- each candidate is evaluated separately on each training year's withheld daily dates using nRMSE normalized by that year's common-support `Q95-Q05`;
- the candidate score is the equal-weight mean of the six year-level nRMSE values;
- peak timing and other seasonal metrics are not used for spline tuning; and
- an invalid candidate-year result cannot be silently dropped from the selection score.

Different outer folds may select different smoothing parameters. This is a nested year-blocked parameter-selection result, not evidence of seven separate post-hoc models.

After LOYO and controlled-gap evaluation, final settings may be chosen using Erken-only cross-validated evidence and frozen in a dated transfer manifest before Vomb analysis. The final all-Erken configuration is not itself an independent Erken validation.

Daily errors may be reported as diagnostic distributions, but uncertainty intervals and hypothesis-level conclusions must respect clustering by year and mask replicate. Do not present thousands of daily residuals as thousands of independent ecological replicates.

---

## 5. Reconstruction methods — keep the benchmark compact and scientifically distinct

The main manuscript uses three reconstruction strategies:

1. **Linear interpolation** — simple deterministic baseline with minimal structural assumptions.
2. **TIMESAT double logistic** — season-structured parametric reconstruction using the current frozen TIMESAT default configuration, including its internal multi-season handling.
3. **TIMESAT smoothing spline** — flexible spline reconstruction with an explicitly controlled smoothing continuum.

Do not add GAM or Whittaker to the primary benchmark. They may be discussed as alternative smoothers in the literature, but adding closely related smoothers would shift the paper toward an algorithm leaderboard rather than strengthen the metric-specific reliability question.

For the spline, the frozen integer smoothing grid is `{0, 1, 3, 10, 30, 100, 300, 1000}`. `0` retains the interpolation limit. The grid and selection procedure are frozen before performance comparison.

For double logistic, use the unmodified default configuration from the frozen TIMESAT source revision without Erken-specific tuning. Before any performance output is generated, the implementation must materialize an immutable machine-readable snapshot of the TIMESAT version/commit (or source/build checksum) and all effective default parameter values; runtime mismatch with that snapshot must fail. The complete daily reference cannot be used to decide how many seasons/peaks the sparse reconstruction should fit.

The three methods therefore span a transparent local interpolation baseline, a constrained/season-structured parametric reconstruction and a flexible tunable spline reconstruction without creating a large model zoo.

### 5.1 Why DINEOF/DINCAE are not required in the main benchmark

Si et al. (2025) demonstrate that image-scale or spatiotemporal matrix methods, including DINEOF and DINCAE, are relevant to inland-water gap reconstruction. Their omission must therefore be explained, not ignored.

The present study’s estimand is a **one-dimensional seasonal trajectory** extracted from a stable water region or station neighbourhood. DINEOF and DINCAE typically exploit spatial covariance across images/pixels and answer a broader seamless image-reconstruction question. Adding them would change the data object, computational design and paper question.

Accordingly:

- the compact benchmark is representative, not exhaustive;
- no claim should be made that the selected methods dominate all inland-water gap-filling approaches;
- the contribution comes from deep metric-specific validation and transfer, not algorithm count; and
- spatially explicit DINEOF/DINCAE comparison can be identified as a separate future study.

### 5.2 Fair comparison rules

- Give all methods the same observed values, timestamps, masks and analysis boundaries.
- Freeze method-specific hyperparameter search spaces before outer evaluation.
- Prevent interpolation from silently becoming extrapolation at seasonal boundaries.
- Record whether a method fails to return a curve or metric.
- Count non-convergence, missing peaks and implausible curves as outcomes, not silently discarded cases.
- Do not select a method solely because it performs best on the Vomb transfer lake.

---

## 6. Evaluation strategy

Evaluation must distinguish point-wise accuracy, seasonal-metric accuracy and reliability classification. **All seasonal metrics and their evaluation support are defined independently of the reconstruction method.** The same mathematical definitions are applied to the daily reference and to linear, TIMESAT double-logistic and TIMESAT smoothing-spline reconstructions; TIMESAT method outputs do not define the reference metric truth.

### 6.1 Point-wise reconstruction accuracy

Primary point-wise evaluation uses only dates within common support that are open water, have a finite daily reference, and were **not** supplied as sparse reconstruction inputs.

Frozen primary diagnostics are:

- mean error / bias;
- MAE;
- RMSE; and
- nRMSE = RMSE / (`Q95 - Q05`) using the method-independent common-support reference scale for that year.

If `Q95 - Q05` is zero or non-finite, nRMSE is unavailable and explicitly flagged; do not add an arbitrary epsilon. Pearson correlation is retained as a supporting trajectory-agreement metric, not as a replacement for magnitude-sensitive error.

Across-year summaries are first computed at year level. Daily residuals are diagnostic nested observations, not independent ecological replicates.

### 6.2 Seasonal and ecological trajectory metrics

Primary candidate and supporting metrics:

| Metric | Role | Erken Chl-a-to-Chl-a experiment | Real Sentinel-2 index application |
|---|---|---|---|
| Peak date error | Pre-specified primary candidate | Directly comparable | Comparable as index-peak timing |
| Peak magnitude error | Key supporting metric | Comparable in Chl-a units | Comparable only in the same index/proxy scale |
| Seasonal trajectory agreement | Key supporting metric | Yes | Yes, within index/proxy scale |
| Seasonal integral error | Supporting metric | Yes | Index-season integral only |
| Onset/end/duration | Secondary/sensitivity | Valid under common Chl-a threshold | Index-season metrics unless independently validated |

The exact formulas, support, tie handling, missing-metric handling and tolerances are frozen in `Reconstruction_Analysis_Contract_v1.0.1.md` before outer evaluation and before viewing Vomb transfer performance.

### 6.3 Point-wise accuracy versus seasonal-metric accuracy

The Results must directly compare method rankings across outcome types.

Required questions:

- Does the method with lowest RMSE also have lowest peak-date error?
- Does smoothing improve point-wise error while attenuating peak magnitude?
- Do rankings change under high-activity versus low-activity gaps?
- Are rankings stable across years?

Report rank agreement or disagreement descriptively across years and scenarios. Avoid collapsing all outcomes into an opaque single score unless its weights were justified and frozen in advance.

### 6.4 Empirical metric-specific reliability envelope

Replace claims of a universal “failure boundary” with an **empirical reliability envelope**.

For the primary binary peak-timing outcome, define success as:

`S_peak = 1 if absolute peak-date error ≤ 10 calendar days; otherwise 0`

Pre-specified sensitivity thresholds are ±5 d and ±15 d. Other primary metrics remain continuous unless an independently justified threshold is added as an explicitly labelled sensitivity analysis.

Estimate or summarize:

`P(S_(m,h) = 1 | gap length, gap position, gap activity, observation density, year)`

The envelope should be shown as empirical tables, curves or probability surfaces with uncertainty, for example:

- success probability versus consecutive gap length, stratified by activity;
- success probability for rise, peak, decline and stable-period gaps;
- error distributions across low-, medium- and high-activity gaps; and
- year-specific results to show whether an apparent threshold depends on one season.

The envelope is:

- metric-specific;
- method-specific;
- conditional on the observed ranges of Erken sampling and bloom dynamics;
- transferable to Vomb only as a hypothesis tested with frozen settings; and
- not a universal physical law or guaranteed operational threshold.

Primary reporting retains continuous errors. Binary success probability is an interpretable supplement for peak timing and uses the frozen ±10 d threshold, with ±5 d and ±15 d sensitivities.

### 6.5 Robustness and uncertainty summaries

- Treat year as the main independent unit.
- Treat repeated masks within a year as nested simulations, not new years.
- Use identical replicate seeds across methods.
- Report medians, interquartile ranges and uncertainty intervals in addition to means where distributions are skewed.
- Report complete year-by-method results rather than only pooled scores.
- Distinguish method-selection results from final locked-transfer results.
- Correct or clearly structure multiplicity if formal hypothesis tests are used across many metrics and scenarios.

---

## 7. Seasonal timing metrics — v4.3.1 frozen method-independent decision

This section is critical because operational Sentinel-2 application uses an index/proxy, not necessarily Chl-a concentration. Metric definitions are external to the reconstruction method: they are computed from the reference and reconstructed trajectories using identical pre-specified rules.

### 7.1 Peak date — pre-specified primary candidate metric

Peak date remains the most defensible **candidate** cross-scale timing metric because a stable monotonic index–Chl-a relationship is more likely to preserve rank and peak ordering than an amplitude-derived onset threshold.

However, the paper must not state in advance that peak timing is the most reliable metric. Its robustness is an empirical result.

Required language:

> **Peak timing was pre-specified as the primary candidate timing metric; its reliability relative to magnitude, trajectory and other metrics was evaluated rather than assumed.**

Frozen peak-date rules are:

- analysis domain = year-specific common support;
- primary peak = global maximum within that support;
- one contiguous equal-maximum plateau is represented by its temporal midpoint;
- non-contiguous exactly equal global maxima are flagged `ambiguous_equal_global_maxima` and peak timing is unavailable for that case;
- multi-peak years are retained and the global maximum remains the primary peak;
- a reference peak on the first or last common-support date is flagged as a boundary-identifiability case; and
- no minimum-prominence event detector is used to redefine the primary global peak after performance is seen.

Primary errors are:

`absolute peak-date error = |date_peak,reconstruction − date_peak,reference|`

and signed peak-date error to distinguish early from late estimates.

For Vomb withheld-Sentinel-2 tests, peak timing can be evaluated only when the withheld-observation design and observed seasonal support make the comparison identifiable. Do not infer an exact unobserved field peak from sparse Chl-a samples.

### 7.2 Onset and termination in pure Erken Chl-a reconstruction

Onset/end are valid to evaluate when both reference and reconstruction are expressed in the **same Chl-a-related variable**.

If an amplitude-based threshold is used, define the threshold from the complete reference curve once.

For year `y`:

`T_y = B_y + p × A_y`

Then apply the same `T_y` to:

- the complete field reference;
- smoothing-spline reconstruction implemented in TIMESAT;
- TIMESAT double-logistic reconstruction; and
- linear reconstruction.

Do **not** allow each reconstruction to calculate its own validation threshold from its reconstructed amplitude. That would allow magnitude error to move the threshold and potentially conceal timing error.

Amplitude-threshold sensitivity, such as 10%, 20% and 30%, should be supplementary unless a single threshold has an independently justified monitoring interpretation.

### 7.3 Onset/end from real Sentinel-2 indices

For NDCI, MCI or another index:

- relative-amplitude onset/end are **index-season metrics**;
- they are not automatically equivalent to absolute Chl-a bloom onset/end; and
- they should not be the headline ecological claim.

Do not claim that any reconstruction method detects the true Chl-a bloom onset from an index unless independent evidence supports that interpretation.

Use onset/end as secondary or sensitivity metrics, with a clear distinction between:

- **validation mode:** common threshold on the same reference-variable scale; and
- **application mode:** relative index-season threshold whose ecological meaning is more limited.

### 7.4 Metrics not recommended as primary cross-scale timing metrics

#### Cumulative-integral 50% date

This measure is shape-sensitive and not invariant to nonlinear transformations between Chl-a and an index. Use only if interpreted as the temporal distribution of the seasonal integral, not as a universal bloom-timing measure.

#### Maximum growth-rate date

This can be informative, but a nonlinear index–Chl relationship can shift the date of maximum derivative. Retain only as a supporting/sensitivity metric unless the observation relationship is well constrained.

### 7.5 Multi-peak and flat-peak caution

A single global peak date may be unstable in seasons with two similarly high blooms or a long plateau. Rather than excluding these years automatically:

- flag peak multiplicity and plateau width from the complete reference;
- report whether the reconstructed global peak switches between events;
- retain multi-peak years without introducing an unfrozen secondary-event detector; and
- test whether peak-date reliability differs between single- and multi-peak years.

This is part of the reliability question, not merely a data-cleaning inconvenience. However, v4.3.1 does not define a primary secondary-event prominence/separation/matching algorithm. Event omission, extra-event counts and event switching are therefore not confirmatory primary outputs unless a separate event-detection protocol is frozen before event-level performance is inspected.

---

## 8. Vombsjön field dataset — canonical facts

The canonical harmonized Vomb field table is:

`Vombsjon_S2_field_matchup_master.csv`

It contains 54 fluorometric Chl-a dates:

- 2018: 6;
- 2019: 22;
- 2020: 26; and
- total: 54.

The 2019–2020 fluorometric values match the DiCyano working file on all 48 common dates.

### 8.1 Sampling depth

According to Rabow et al. (2025):

- 2018: water-column integrated sample from approximately 0–2 m; and
- 2019–2020: water-column integrated sample from approximately 0–6 m.

This creates vertical-representativeness uncertainty relative to surface-sensitive satellite observations and confounds direct cross-year retrieval comparisons. The 2018–2020 change must be reported, not silently harmonized.

### 8.2 Sampling location

Paper nominal sampling position:

- latitude: 55.6775;
- longitude: 13.60889.

The authors’ metadata show that actual boat locations vary within a limited lake area and are not always the same Sentinel-2 pixel.

Rule:

- use measured daily GPS when available;
- otherwise use the nominal paper station with explicit provenance; and
- test spatial extraction sensitivity rather than treating nearby pixels or locations as independent replicates.

### 8.3 Coordinate QC issue

Two 2020 dates are currently unresolved:

- 2020-06-10; and
- 2020-06-24.

The supplied longitude uses `13°35′xx″ E`, unlike the dominant `13°36′xx″ E` pattern.

Do not silently correct these coordinates. Keep them flagged until confirmed.

### 8.4 Role in v4.3.1 validation

The 54 field dates support:

- lake-specific observed proxy–Chl-a validation;
- checks of broad seasonal and high/low-state consistency;
- analysis of residuals by community composition and sampling regime; and
- ecological interpretation of the locked reconstruction.

They do not provide a complete daily temporal reference for the primary Vomb reconstruction test. Withheld Sentinel-2 observations carry that primary quantitative transfer role.

---

## 9. Vomb 2018 — treat as a scientific asset with explicit limits

Vomb 2018 should not be removed or down-weighted simply because Chl-a is much higher than in later years.

The published study reports:

- a much larger Chl-a maximum in 2018 than in 2019–2020;
- strong dinoflagellate dominance in 2018;
- cyanobacterial dominance during important parts of 2019; and
- a different community structure again in 2020.

Therefore 2018 is a natural:

> **extreme high-amplitude / altered-community stress test**

Priority questions:

- Does the frozen reconstruction preserve the timing of the dominant observed index peak?
- Does smoothing attenuate the extreme proxy amplitude?
- How are results affected when a high-activity gap overlaps the bloom maximum?
- Does reconstruction skill differ among bloom/community regimes?
- Are NDCI/MCI residuals associated with phytoplankton composition?

Limits:

- only six field Chl-a dates are available in 2018;
- sampling depth differs from 2019–2020;
- the exact daily field peak is not observed; and
- changes in proxy response cannot be attributed uniquely to community composition because concentration, sampling depth, optical conditions and observation availability also differ.

Accordingly, 2018 supports an extreme-regime stress test and cautious mechanism hypotheses, not strong causal retrieval claims.

---

## 10. Atmospheric correction — supporting factor, not the entire paper

Atmospheric correction remains important but should not dominate Paper 1.

The key downstream question is:

> **Do plausible atmospheric-correction choices materially change the metric-specific seasonal conclusions?**

A practical design is:

- one primary aquatic atmospheric correction;
- TOA/L1C or another transparent baseline where scientifically useful; and
- one additional independent AC method only if already available or feasible.

Do not expand Paper 1 into a large AC × index × lake × reconstruction factorial experiment.

The primary AC and QC workflow should be selected using pre-specified evidence before final reconstruction evaluation. If multiple AC products are retained, distinguish:

- changes in observed proxy values;
- changes in which dates pass QC; and
- downstream changes in reconstructed metrics.

---

## 11. Retrieval uncertainty versus temporal reconstruction uncertainty

Keep these separate throughout Methods, Results and Discussion.

### 11.1 Retrieval / observation uncertainty

Includes:

- atmospheric correction;
- adjacency effects;
- glint;
- residual cloud or shadow contamination;
- shoreline mixing;
- index–Chl relationship;
- spatial mismatch;
- field–satellite temporal mismatch; and
- vertical sampling mismatch.

### 11.2 Temporal reconstruction uncertainty

Includes:

- observation density;
- timing irregularity;
- consecutive gap length;
- position of a gap relative to seasonal dynamics;
- underlying activity hidden within the gap;
- smoothing settings;
- bloom growth and decline rate;
- peak width and plateau behaviour; and
- multi-peak structure.

The pure Erken experiment is specifically designed to isolate the second group by masking and reconstructing the same reference variable.

The Vomb withheld-Sentinel-2 experiment tests transfer of the reconstruction layer but retains uncertainty in the observed satellite proxy. The Vomb field comparison reconnects the observed/reconstructed proxy to ecological interpretation but is too sparse to isolate daily reconstruction error.

---

## 12. Spatial rules

### 12.1 Field-matchup products

Use station-centred extraction.

For Vomb:

- use actual GPS on each date when available;
- use the nominal station only when actual GPS is unavailable;
- retain coordinate provenance and QC; and
- test spatial extraction sensitivity rather than assuming all samples belong to one fixed pixel.

### 12.2 Seasonal Sentinel-2 products

Retain a stable open-water/core-water region in addition to field-station neighbourhoods.

The temporal reconstruction target should be explicitly identified as, for example:

- station-neighbourhood median proxy; or
- stable core-water median proxy.

Do not switch the target region between dates based on the observed signal. Do not treat adjacent pixels as independent replicates.

### 12.3 Spatial versus temporal scope

The main v4.3.1 reliability envelope applies to the selected one-dimensional regional trajectory. It does not automatically describe pixel-scale map reconstruction or spatial bloom extent. Any mapped examples are illustrative unless a separate spatial validation design is added.

---

## 13. RSE-level minimum evidence package — v4.3.1

The project should ideally contain:

- explicit positioning against Palmer et al. (2015), Si et al. (2025) and Goodrich et al. (2026);
- defensible lake-specific raw Sentinel-2 proxy validation;
- a continuous multi-year Erken daily temporal reference with limitations documented;
- a scene-level usable Sentinel-2 observation inventory and realistic-mask experiment;
- linear interpolation + TIMESAT double-logistic + TIMESAT smoothing-spline benchmark;
- year-level independent/LOYO evaluation in Erken;
- controlled random deletion plus exhaustive internal consecutive-gap experiments with objective position/activity annotation;
- gap-activity / underlying-change characterization;
- point-wise withheld-date accuracy;
- direct comparison of point-wise and seasonal-metric rankings;
- peak timing as a pre-specified candidate rather than a predetermined winner;
- metric-specific continuous error distributions and reliability probabilities;
- an empirical reliability envelope with uncertainty and scope limits;
- all temporal settings frozen before Vomb transfer;
- Vomb withheld-Sentinel-2 tests as the primary quantitative transfer evidence;
- Vomb field Chl-a as a complementary ecological consistency check;
- Vomb 2018 extreme-regime analysis with sampling-depth caveats;
- separation of retrieval and temporal reconstruction uncertainty; and
- reproducible code, configurations, scene inventory, masks, seeds and processing provenance.

Not required for Paper 1:

- Landsat/HLS;
- a large model zoo;
- four or more atmospheric-correction algorithms;
- many Chl-a machine-learning retrieval models;
- catchment-causality analysis;
- many additional lakes;
- DINEOF/DINCAE image-scale reconstruction; or
- universal reliability thresholds for all inland waters.

### 13.1 Minimum claim supported by each evidence layer

| Evidence layer | Claim it can support | Claim it cannot support alone |
|---|---|---|
| Erken masked-field experiment | Reconstruction performance under known daily dynamics | Satellite retrieval accuracy |
| Erken LOYO | Across-year robustness within Erken | Universal cross-lake generality |
| Vomb withheld Sentinel-2 | Locked transfer to a contrasting satellite proxy series | Exact daily field Chl-a reconstruction |
| Vomb field matchup | Proxy relevance and ecological consistency | Complete temporal reconstruction validation |
| Two-lake synthesis | Evidence across two contrasting systems | Global operational validity |

---

## 14. Immediate priority order

### P0 — activate v4.3.1 and freeze project governance

- Use `Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md` as the single active scientific master.
- Archive v4.3 and earlier masters outside the active Project after confirming this file and the frozen contract are complete.
- Use `DATA_INVENTORY_v4.3.1.md` so the active inventory points to v4.3.1 and `Reconstruction_Analysis_Contract_v1.0.1.md`.
- Do not maintain a separate competing reviewer-response framework.

### P1 — build the usable Sentinel-2 observation inventories

For every Erken and Vomb acquisition, record:

- acquisition date/time;
- product and scene identifier;
- processing baseline and AC method;
- target extraction region;
- valid water pixels and fraction;
- cloud, shadow, glint, ice and shoreline flags;
- reason for exclusion; and
- final usable/not-usable decision.

The Erken inventory defines the primary realistic sampling mask. The Vomb inventory defines the locked transfer series.

### P2 — freeze the analysis contract before performance comparison

**Current v4.3.1 status: COMPLETE / FROZEN.** The governing file is `Reconstruction_Analysis_Contract_v1.0.1.md`, frozen on 2026-09-01 before first reconstruction-performance comparison.

The contract freezes:

- 2019–2025 as seven outer Erken year-level folds;
- the 288 actual-mask sparse input dates under the S2-usable + open-water + finite-CHLF rule;
- year-specific common support and no-primary-extrapolation rules;
- method-independent point-wise and seasonal metrics;
- common-support peak/plateau/tie/multi-peak rules;
- ±10 d primary peak-timing reliability with ±5/±15 d sensitivities;
- the spline integer grid and year-blocked nRMSE selection procedure;
- TIMESAT double logistic at frozen defaults;
- explicit failure/non-convergence/negative-value handling; and
- random/consecutive controlled-gap scenarios, deterministic randomization, position diagnostics and activity definition.

Do not modify these primary-analysis rules after inspecting performance without incrementing the contract version and explicitly reclassifying the affected analysis.

### P3 — implement the pure Erken benchmark with LOYO

Inputs:

- daily Erken reference with frozen year-specific common-support rules; and
- actual usable Sentinel-2 observation masks.

Methods:

- linear interpolation;
- TIMESAT double logistic using frozen defaults; and
- TIMESAT smoothing spline with the frozen grid and year-blocked selection rule.

Outputs:

- fold-specific daily reconstructions;
- withheld-date errors;
- peak-date and peak-magnitude errors;
- trajectory and integral errors;
- year-level summaries.

### P4 — run controlled activity-aware gap experiments

Generate metric-specific error and success-probability results for:

- random deletion at 10/20/30/50% with 100 replicates;
- exhaustive internal consecutive gaps of 10/20/30/45 calendar days;
- reference-derived relative-position/global-peak/activity annotations on the consecutive windows;
- continuous `A_gap`, with duration-specific activity tertiles used only when categorical visualization is useful; and

Build the empirical reliability envelope with year-aware uncertainty.

### P5 — second freeze: select transfer settings

Use Erken-only LOYO evidence. Do not choose a single “winner” solely from pooled RMSE.

Freeze:

- the setting for every benchmark method carried forward;
- any designated primary workflow using a pre-specified decision hierarchy;
- quality and mask rules;
- metric definitions; and
- all transfer-analysis scripts/configurations.

Create a dated freeze manifest before evaluating Vomb transfer results.

### P6 — complete the Vomb raw satellite matchup audit

Extend `Vombsjon_S2_field_matchup_master.csv` or a linked analysis table with:

- Sentinel-2 scene ID;
- acquisition-time difference;
- AC method/version;
- NDCI/MCI and retained proxy values;
- spatial extraction statistics;
- valid-pixel count/fraction;
- GPS/nominal-location provenance; and
- matchup and scene QC.

Resolve or transparently retain the two coordinate flags.

### P7 — execute the locked Vomb transfer

Primary:

- withheld-Sentinel-2 reconstruction at identical test dates across methods;
- isolated and blocked withholding where supported; and
- quantitative error and metric results in index/proxy units.

Complementary:

- ecological consistency with sparse field Chl-a;
- 2018 extreme-regime analysis; and
- residual patterns by community composition and sampling regime.

No Vomb-driven retuning is permitted in the confirmatory result. Any later adapted result must be labelled exploratory and kept separate.

### P8 — prepare reproducibility and manuscript evidence

- release or archive scene inventories, configs, seeds and derived evaluation tables;
- record code commit, environment and input checksums;
- preserve fold- and year-specific outputs;
- generate a transparent analysis flowchart; and
- make every main figure reproducible from versioned analysis tables.

---

## 15. Suggested manuscript logic — v4.3.1

### 15.1 Introduction

1. Inland-water Sentinel-2 records are incomplete and irregular because of clouds and water-specific quality-control losses.
2. Palmer et al. established that TIMESAT can support aquatic phytoplankton phenology analysis; TIMESAT is therefore background implementation context rather than the paper’s organizing novelty.
3. Si et al. show that inland-water gap filling already includes statistical and deep-learning approaches; algorithm comparison or seamless filling alone is not the gap addressed here.
4. Point-wise accuracy does not guarantee preservation of ecologically meaningful seasonal metrics.
5. Reliability should depend on what metric is required and on both the observation gap and the hidden dynamics occurring within it.
6. Goodrich et al. motivate stronger validation evidence, transparent methods and broader transfer testing for Sentinel-2 aquatic Chl-a studies.
7. This study quantifies metric-specific reliability with a dense multi-year reference, year-level independence and locked transfer to a contrasting lake.

### 15.2 Methods

1. study lakes and field datasets;
2. Sentinel-2 preprocessing, atmospheric correction and scene QC;
3. lake-specific observed proxy validation;
4. definitions of field, observed satellite and reconstructed layers;
5. Erken daily-reference eligibility and analysis season;
6. linear interpolation, TIMESAT double-logistic reconstruction and TIMESAT smoothing-spline reconstruction;
7. actual usable Sentinel-2 mask;
8. controlled random deletion and exhaustive blocked gaps with objective position/activity annotations;
9. gap-activity / underlying-change metrics;
10. method-independent point-wise and seasonal metric definitions;
11. LOYO and year-aware uncertainty;
12. empirical reliability-envelope estimation;
13. freeze protocol; and
14. primary Vomb withheld-Sentinel-2 transfer plus complementary field check.

### 15.3 Results

1. field and Sentinel-2 availability, QC and matchup evidence;
2. lake-specific observed proxy–Chl-a performance;
3. Erken LOYO reconstruction skill under the realistic mask;
4. disagreement or agreement between point-wise and seasonal-metric rankings;
5. error versus gap length, relative position/global-peak containment and activity;
6. empirical metric-specific reliability envelopes;
7. peak timing relative to other candidate metrics;
8. locked Vomb withheld-Sentinel-2 transfer;
9. complementary consistency with Vomb field Chl-a; and
10. Vomb 2018 extreme-regime behaviour.

### 15.4 Discussion

1. why reliability is a property of a metric and use case, not merely a reconstructed curve;
2. why gap activity modifies the effect of gap length;
3. when simple interpolation is sufficient and when smoothing changes seasonal conclusions;
4. whether peak timing proved robust rather than assuming that it did;
5. why onset/end from indices require cautious interpretation;
6. what transferred from Erken to Vomb and what did not;
7. relative importance of observation/retrieval and reconstruction uncertainty;
8. relation to Palmer et al. and Si et al.;
9. response to reproducibility and validation-evidence concerns raised by Goodrich et al.; and
10. limits of a two-lake, one-dimensional trajectory study.

### 15.5 Recommended headline figure set

1. Two-lake design and validation hierarchy.
2. Year-by-year observation-availability calendar and actual masks.
3. Example Erken reference/masked/reconstructed curves for low- and high-activity gaps.
4. LOYO point-wise and seasonal-metric performance by year and method.
5. Direct method-rank comparison: point-wise accuracy versus seasonal-metric accuracy.
6. Metric-specific reliability envelope across gap length × activity, with relative gap position and global-peak containment where informative.
7. Locked Vomb withheld-Sentinel-2 transfer results.
8. Vomb field consistency and 2018 extreme-regime case.

---

## 16. Stable project rules

> This project develops an RSE-oriented paper on the **metric-specific reliability** of reconstructed seasonal chlorophyll-sensitive Sentinel-2 dynamics under incomplete observations.
>
> Erken is the dense/high-frequency temporal-reference development and calibration site. Vombsjön is the locked external transfer and extreme-regime stress-test site.
>
> Erken is not literal Sentinel-2 surface ground truth. Vomb sparse field Chl-a is not a complete daily temporal reference.
>
> Satellite retrieval/proxy validation remains lake-specific. Do not transfer an absolute Erken Chl-a calibration to Vombsjön without independent justification.
>
> Always distinguish field reference, observed satellite proxy and model-reconstructed daily estimate.
>
> All daily reconstructed outputs, including smoothing-spline outputs produced with TIMESAT, are reconstructed estimates, never daily satellite observations.
>
> The main reconstruction benchmark is linear interpolation + TIMESAT double logistic + TIMESAT smoothing spline. Seasonal metrics and support remain external, method-independent evaluation definitions; TIMESAT supplies two reconstruction implementations, not the definition of metric truth.
>
> Seasonal metrics and evaluation support are defined independently of reconstruction method. TIMESAT must not define the reference season, metric truth, or method-specific evaluation domain.
>
> Temporal method and parameter selection must use Erken-only year-level independent evidence and must be frozen before Vomb transfer.
>
> Peak date is the pre-specified primary candidate timing metric, not a metric assumed in advance to be reliable.
>
> Point-wise accuracy and seasonal-metric accuracy must be evaluated and compared separately.
>
> Controlled gap experiments must include underlying gap activity and objective gap position as well as gap duration.
>
> Report an empirical, metric-specific reliability envelope. Do not claim a universal failure threshold.
>
> Vomb withheld-Sentinel-2 reconstruction is the primary quantitative transfer validation. Vomb field Chl-a is a complementary ecological consistency check.
>
> Vomb 2018 is an extreme-regime stress test, not an outlier to be removed, but its sparse sampling and different sampling depth constrain causal interpretation.
>
> Daily values and repeated masks are not independent ecological replicates; year/season is the primary unit for generalization.
>
> Atmospheric correction is a supporting uncertainty factor, not the whole paper.
>
> Any new dataset, method or experiment should be added only if it strengthens the central question: **which seasonal metrics remain reliable under incomplete observations, under what conditions, and do those conditions transfer?**

---

## 17. Versioning rule and history

This file is the **current active master** once accepted by the project owner.

When a major scientific decision changes:

1. update the current master;
2. increment the version;
3. record the date and decision;
4. archive older versions outside the active ChatGPT Project;
5. keep only the current master plus essential active data/reference files in the Project; and
6. avoid maintaining multiple competing scientific-summary files in the active Project.

### Version history

- **v3:** Vomb development / Erken validation architecture.
- **v4 — 2026-08-23:** Erken changed to dense-reference temporal development/calibration site; Vomb changed to locked transfer and extreme-regime stress-test site. Timing-metric rules revised to distinguish Chl-a reconstruction metrics from real Sentinel-2 index metrics.
- **v4.1 — 2026-08-31:** Retained the v4 lake roles and compact benchmark but reframed novelty as metric-specific reliability under incomplete observations. Replaced universal failure-boundary language with an empirical reliability envelope; added gap activity / underlying temporal change; made peak timing a pre-specified primary candidate; required LOYO/year-level independence; designated Vomb withheld Sentinel-2 as the primary quantitative transfer validation and field Chl-a as a complementary ecological consistency check; standardized Erken as a dense/high-frequency temporal reference; and incorporated reviewer-proof positioning against Palmer et al. (2015), Si et al. (2025) and Goodrich et al. (2026).
- **v4.2 — 2026-09-01:** Reframed the study around method-independent reconstruction reliability rather than TIMESAT as the organizing framework. The benchmark was described symmetrically as linear interpolation, GAM smoothing and smoothing-spline reconstruction implemented in TIMESAT. Seasonal metric truth and evaluation support were explicitly independent of reconstruction method. The version also recorded the completed Erken observation-layer status through Phase 2B-1: 307 frozen S2-usable dates and 288 preliminary open-water/reference candidates, while leaving the final reconstruction analysis contract for Phase 2B-2 to be frozen before model comparison.
- **v4.3 — 2026-09-01:** Freezes Phase 2B-2 through `Reconstruction_Analysis_Contract_v1.0.md`. Replaces GAM with the TIMESAT double-logistic method in the primary benchmark; freezes 2019–2025 as seven outer LOYO folds, promotes the 288 open-water/reference candidates to final actual-mask sparse inputs, fixes method-independent common support, freezes the spline integer grid `{0,1,3,10,30,100,300,1000}` and equal-year nRMSE selection, retains TIMESAT double logistic at documented defaults, sets ±10 d primary peak-timing reliability with ±5/±15 d sensitivity, and freezes the random/consecutive activity-aware controlled-gap protocol before any reconstruction-performance comparison.
- **v4.3.1 — 2026-09-01:** Clarification-only pre-performance patch aligned with Contract v1.0.1. Corrects TIMESAT's role as the implementation platform for both double logistic and smoothing spline; requires a frozen snapshot of effective double-logistic defaults; fixes random-deletion rounding/seed/RNG details; defines consecutive-window support and `A_gap` exactly; replaces undefined phase/secondary-event categories with objective position/activity diagnostics; and removes undefined secondary-event matching from primary outputs. No primary scientific method, year, spline grid, peak tolerance or controlled-gap scenario changed.

---

## 18. Key literature anchoring v4.3.1

Goodrich, S., Schaeffer, B., Meyers, K., Salls, W. B., King, T. V., Seegers, B. N., Cronin-Golomb, O., Demaree, D., & Reif, M. (2026). Sentinel-2 for chlorophyll-a water quality monitoring: A review of validation evidence and application potential. *International Journal of Remote Sensing, 47*(9), 3820–3845. <https://doi.org/10.1080/01431161.2026.2637851>

Palmer, S. C. J., Odermatt, D., Hunter, P. D., Brockmann, C., Présing, M., Balzter, H., & Tóth, V. R. (2015). Satellite remote sensing of phytoplankton phenology in Lake Balaton using 10 years of MERIS observations. *Remote Sensing of Environment, 158*, 441–452. <https://doi.org/10.1016/j.rse.2014.11.021>

Si, Y., Shen, M., Cao, Z., Qiu, Z., Yang, C., Yin, H., & Duan, H. (2025). Evaluation of gap-filling methods for inland water color remote sensing data: A case study in Lake Taihu. *Remote Sensing, 17*(23), 3843. <https://doi.org/10.3390/rs17233843>

Rabow, S., Johansson, E., Carlsson, P., & Rengefors, K. (2025). Unexpected shift from cyanobacterial to dinoflagellate dominance due to a summer drought. *Harmful Algae, 142*, 102787. <https://doi.org/10.1016/j.hal.2024.102787>
