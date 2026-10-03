# Supplementary Information

**Metric-specific reliability of Sentinel-2 lake time-series reconstruction under incomplete sampling: dense-reference evaluation and transfer without retuning**

Abbreviations: LI, linear interpolation; DL, TIMESAT double logistic with default settings (`p_seapar` = 1); SS, TIMESAT smoothing spline; CV-DL, cross-validated double logistic (`p_seapar` = 0). Intervals are 95% percentile intervals from 10,000 bootstrap resamples of whole calendar years unless stated otherwise.

## S1. Observation support and satellite observation layer

### S1.1 Erken Sentinel-2 observation-mask implementation

Observation availability in Erken was defined from the native Scene Classification Layer (SCL) of the Level-2A archive, comprising 950 products on 926 unique calendar dates between 17 April 2019 and 30 November 2025. SCL determined only whether a date was observable at the station; it did not select a reflectance product or processor, and no CHLF, reflectance, spectral-index or reconstruction value entered the rule.

SCL class 6 was treated as water; classes 0, 1, 3, 8, 9, 10 and 11 as obviously invalid; classes 4, 5 and 7 as persistent non-water; and class 2 as a separate category. In the station-centred 3 × 3 window on the 20 m grid (60 × 60 m), a product passed when it contained at most one obviously invalid pixel, at least eight water pixels, a centre pixel outside the obviously invalid classes, no persistent non-water pixel and no class-2 pixel. Only 18 combinations of centre class and pixel-count categories occurred among the 950 windows, and no class-2 pixel occurred. In these data, requiring a water centre and requiring a centre that was not obviously invalid gave identical decisions.

The temporal observation unit was the calendar date. A date was usable when at least one same-day product passed, and it then contributed one observation. Twenty-four dates had two products: on five, one product passed and the other failed; on six, both passed; and on thirteen, neither passed. The rule retained 313 products and 307 usable dates. All 307 usable dates had a finite CHLF value; 19 fell outside the open-water period. The remaining 288 open-water dates formed the reconstruction inputs: 35, 56, 46, 36, 27, 40 and 48 dates for 2019–2025, respectively. The excluded non-open-water dates numbered 0, 0, 2, 2, 9, 1 and 5 in those years.

### S1.2 Window-size stability

The 1 × 1 and 5 × 5 windows were evaluated only as diagnostics of observation-mask stability; no reconstruction was performed with either window. The pixel-count thresholds were scaled to each window size. Under the preferred rule, the 1 × 1 window (water centre, no other pixel) passed 322 products and 315 usable dates; the 3 × 3 window (at most one invalid pixel, at least eight water) passed 313 products and 307 dates; and the 5 × 5 window (at most two invalid pixels, at least 23 water) passed 300 products and 295 dates. All three windows gave a median inter-observation interval of 5 days and a maximum gap of 120 days. Gaps longer than 10/20/30/45 days numbered 58/12/6/4, 57/15/8/4 and 59/17/9/4 for the 1 × 1, 3 × 3 and 5 × 5 windows, respectively. Within the 3 × 3 window, a strict all-water rule retained 301 dates and a relaxed rule (at most two invalid pixels, at least seven water) retained 310 (Figure S1).

### S1.3 Erken satellite-index–CHLF observation layer

Observed indices were paired with CHLF on exact calendar dates; nearest-date substitution and interpolation were not allowed. Three products were compared: Level-1C top-of-atmosphere reflectance, official Level-2A bottom-of-atmosphere reflectance and ACOLITE surface reflectance (`rhos`). Bands B4, B5 and B6 were extracted on a common 20 m grid. L1C and L2A digital numbers were converted with each product's additive offset and quantification value. ACOLITE applies the corresponding L1C offset and quantification internally, and its source baseline was retained as provenance only. The processing-baseline audit covered 306 dates with exact three-product source alignment and found no acquisition processed under more than one baseline. An empirical cross-baseline correction was therefore not identifiable, and none was applied.

NDCI and MCI were computed at pixel level. An observation required at least six valid pixels in the 3 × 3 window, and its value was the median of the valid pixel values. The primary comparison used processor-shared support: dates with exact L1C–L2A–ACOLITE alignment, open water, finite CHLF and eligibility for the same index in all three products. This gave 220 dates for MCI and 215 for NDCI. The primary statistic was the Spearman correlation with raw CHLF; Pearson correlation with log10(CHLF) was secondary.

The MCI association was positive for all three products, and the three MCI intervals overlapped (Table S1). NDCI associations were weaker, and the L1C NDCI interval included zero. An analysis of all eligible dates for each product used unequal date sets and is shown for completeness, not for comparing processors. A secondary leave-one-year-out regression, log10(CHLF) = a + b × index with one year held out, gave pooled held-out R² between −0.123 and 0.237. These secondary regressions did not provide a basis for a transferable absolute Chl-a calibration. The observation-layer analysis supports the relevance of the observed proxy to chlorophyll variability in Erken; it does not identify a best processor or define an absolute Chl-a calibration.

**Table S1. Processor-specific Erken satellite-index associations with same-day CHLF.**

(a) Primary processor-shared support (2019–2025; seven years).

| Processor | Index | n matched dates | Spearman ρ (95% whole-year interval) | Pearson r with log10(CHLF), secondary (95% interval) | Pooled leave-one-year-out R², log10(CHLF), secondary |
|---|---|---:|---|---|---:|
| L1C TOA | MCI | 220 | 0.413 (0.247–0.545) | 0.472 (0.333–0.573) | 0.211 |
| L2A BOA | MCI | 220 | 0.510 (0.333–0.610) | 0.519 (0.460–0.594) | 0.237 |
| ACOLITE `rhos` | MCI | 220 | 0.458 (0.295–0.610) | 0.492 (0.360–0.594) | 0.231 |
| L1C TOA | NDCI | 215 | 0.162 (−0.015–0.299) | 0.301 (0.153–0.430) | 0.063 |
| L2A BOA | NDCI | 215 | 0.200 (0.024–0.356) | 0.020 (−0.085–0.259) | −0.123 |
| ACOLITE `rhos` | NDCI | 215 | 0.214 (0.044–0.377) | 0.290 (0.127–0.450) | 0.050 |

(b) Method-specific support (unequal date sets; not for processor comparison).

| Processor | MCI: n; Spearman ρ (95% interval) | NDCI: n; Spearman ρ (95% interval) |
|---|---|---|
| L1C | 269; 0.282 (0.111–0.416) | 269; 0.123 (−0.018–0.259) |
| L2A | 270; 0.410 (0.295–0.490) | 266; 0.215 (0.049–0.373) |
| ACOLITE | 224; 0.451 (0.304–0.600) | 223; 0.227 (0.068–0.380) |

Intervals use 10,000 whole-year resamples. P-values are not reported. Overlapping intervals do not identify a superior processor.

## S2. Companion reconstruction metrics and robustness

### S2.1 Erken actual-mask companion metrics

Table S2 reports all Erken actual-mask metrics defined in Section 2.3 for the 288-input mask and the 2019–2025 outer folds. The spline uses the outer-fold selections 10, 100, 100, 10, 10, 3 and 10. All 21 year × method reconstructions succeeded, and every metric was available in all seven years. MAE, RMSE and bias are in µg L⁻¹, defined as reconstruction minus reference over withheld common-support dates. Peak magnitude is normalized on the year-specific dense-reference Q95 − Q05 scale, and integral error is in µg d L⁻¹. Annual bias values are given for traceability (Table S2B); no equal-year bias summary was formed, and no new equal-year aggregation is introduced here. Point estimates are descriptive; paired contrasts (Table S2C) resample the same years for both methods.

### S2.2 Leave-one-year-out robustness

Each Erken year was omitted in turn, and the equal-year summaries and paired contrasts were recalculated (Table S2D). For nRMSE, MAE, RMSE, daily trajectory correlation and normalized peak-magnitude error, every pairwise contrast kept its full-record direction in all seven omissions. Absolute integral-error contrasts also kept their direction; default DL had lower absolute integral error than LI and SS in every omission, consistent with the descriptive status reported in Section 3.2. For peak timing, LI's ±10-day success advantage over DL and over SS became a tie in one omission and did not reverse; LI's mean absolute peak-date advantage remained positive but fell to approximately 3 days in one omission; and the SS–DL contrasts in peak-date error and ±10-day success took both signs. The directions of the pointwise and trajectory contrasts were stable to omission of any single year, whereas peak-timing contrasts remained more year-sensitive.

**Table S2. Erken actual-mask companion metrics and robustness.**

(A) Equal-year estimates (95% whole-year interval). All metrics: 7 of 7 years available, no reconstruction failures.

| Metric | LI | DL | SS |
|---|---|---|---|
| nRMSE | 0.203 (0.154–0.250) | 0.250 (0.216–0.286) | 0.223 (0.186–0.257) |
| MAE (µg L⁻¹) | 2.044 (1.354–2.833) | 3.053 (2.328–3.815) | 2.312 (1.733–3.010) |
| RMSE (µg L⁻¹) | 4.353 (2.735–6.114) | 5.331 (3.820–6.854) | 4.721 (3.278–6.280) |
| Daily trajectory r | 0.864 (0.817–0.911) | 0.742 (0.693–0.795) | 0.830 (0.800–0.863) |
| Absolute peak-date error (d) | 34.6 (1.6–91.1) | 54.4 (3.3–118.7) | 54.6 (4.4–117.9) |
| Peak success ±5 d | 0.571 (0.143–0.857) | 0.571 (0.143–0.857) | 0.429 (0.143–0.857) |
| Peak success ±10 d | 0.714 (0.429–1.000) | 0.571 (0.143–0.857) | 0.571 (0.143–0.857) |
| Peak success ±15 d | 0.714 (0.286–1.000) | 0.714 (0.429–1.000) | 0.714 (0.429–1.000) |
| Absolute peak-magnitude error (µg L⁻¹) | 18.02 (5.75–31.41) | 28.90 (16.64–40.44) | 22.89 (11.50–34.19) |
| Normalized peak-magnitude error | 0.797 (0.233–1.439) | 1.304 (0.774–1.851) | 1.039 (0.560–1.575) |
| Absolute integral error (µg d L⁻¹) | 157.5 (86.6–245.8) | 126.0 (34.3–271.8) | 187.1 (131.5–256.8) |
| Absolute relative integral error | 0.092 (0.056–0.134) | 0.077 (0.024–0.154) | 0.113 (0.086–0.146) |

(B) Annual bias (µg L⁻¹; reconstruction minus reference). Asterisk: boundary-truncated common support.

| Year | LI | DL | SS |
|---|---:|---:|---:|
| 2019* | −1.916 | −2.649 | −1.836 |
| 2020 | −0.448 | −0.027 | −0.552 |
| 2021 | 0.401 | 0.650 | 0.629 |
| 2022 | −0.800 | −0.297 | −0.886 |
| 2023 | 0.523 | 0.394 | 0.754 |
| 2024 | −0.163 | −0.228 | −0.513 |
| 2025* | 1.149 | −0.084 | 1.278 |

Annual bias is given for traceability. No equal-year bias estimate was formed.

(C) Paired contrasts: mean advantage of the first-named method (positive favours it), 95% paired whole-year interval; years favouring first / second method / tied.

| Metric | LI vs DL | LI vs SS | SS vs DL |
|---|---|---|---|
| nRMSE | 0.047 (0.016–0.084); 7/0/0 | 0.019 (0.007–0.033); 6/1/0 | 0.028 (0.004–0.053); 5/2/0 |
| MAE | 1.009 (0.664–1.344); 7/0/0 | 0.268 (0.105–0.453); 7/0/0 | 0.741 (0.450–0.962); 6/1/0 |
| RMSE | 0.978 (0.302–1.769); 7/0/0 | 0.368 (0.094–0.672); 6/1/0 | 0.610 (0.143–1.114); 5/2/0 |
| Daily trajectory r | 0.122 (0.052–0.197); 7/0/0 | 0.034 (0.015–0.056); 7/0/0 | 0.088 (0.033–0.146); 6/1/0 |
| Normalized peak magnitude | 0.507 (0.236–0.799); 7/0/0 | 0.242 (0.084–0.455); 7/0/0 | 0.265 (0.102–0.411); 6/1/0 |
| Absolute peak-date error (d) | 19.8 (−0.2–54.2); 5/2/0 | 20.0 (1.6–54.0); 6/1/0 | −0.2 (−5.3–4.7); 3/3/1 |
| Peak success ±10 d | 0.143 (0.000–0.429); 1/0/6 | 0.143 (0.000–0.429); 1/0/6 | 0.000 (−0.429–0.429); 1/1/5 |
| Absolute integral error (µg d L⁻¹) | −31.5 (−113.8–53.8); 3/4/0 | 29.6 (10.4–46.9); 6/1/0 | −61.1 (−143.8–33.3); 1/6/0 |

(D) Leave-one-year-out directional stability: range of the paired advantage across seven single-year omissions; whether every omission keeps the full-record direction.

| Metric | LI vs DL | LI vs SS | SS vs DL |
|---|---|---|---|
| nRMSE | 0.035–0.054; yes | 0.015–0.023; yes | 0.020–0.035; yes |
| Daily trajectory r | 0.098–0.140; yes | 0.024–0.038; yes | 0.070–0.104; yes |
| Normalized peak magnitude | 0.408–0.591; yes | 0.148–0.276; yes | 0.211–0.332; yes |
| Absolute peak-date error (d) | 3.1–23.9; yes | 3.3–23.5; yes | −2.1–1.8; no |
| Peak success ±10 d | 0.000–0.167; one tie, no reversal | 0.000–0.167; one tie, no reversal | −0.167–0.167; no |
| Absolute integral error (µg d L⁻¹) | −64.3 to −0.8; yes | 23.7–37.2; yes | −101.5 to −31.3; yes |

MAE and RMSE contrasts keep their direction in all omissions for all pairs. Point estimates in (A) are descriptive; (C) and (D) are paired contrasts.

### S2.3 Annual trajectories

Figure S2 shows the daily dense-reference trajectory, actual-mask inputs and the three reconstructions for each year from 2019 to 2025. It provides the trajectories underlying the annual metrics in Figure 2, including the 2020 and 2025 peak displacements and the 2020 contrast between integral agreement and peak timing.

## S3. Controlled missingness details

### S3.1 Random deletion

Random deletion removed 10%, 20%, 30% or 50% of each year's interior actual-mask inputs, with the first and last inputs protected. Each year and level had 100 replicates, giving 700 masks per level and 2,800 masks in total. Across years and replicates, 3–5, 5–11, 8–16 and 13–27 interior inputs were deleted per year at the four levels, leaving 24–51, 22–45, 19–40 and 14–29 inputs, with longest resulting internal gaps of 15–60, 15–72, 15–85 and 20–117 days. Equal-year nRMSE increased with deletion level for all three methods (Table S3A). ±10-day peak-timing success declined across levels only for linear interpolation; for default double logistic and the smoothing spline, it fluctuated without a consistent decline.

### S3.2 Consecutive calendar-day deletion windows

Windows of 10, 20, 30 and 45 calendar days were slid exhaustively within contiguous open-water segments. Each retained window removed at least one input and no support endpoint. The four durations produced 1,379, 1,525, 1,475 and 1,367 windows (5,746 in total), removing 1–5, 1–8, 1–11 and 1–14 inputs, respectively. Equal-year nRMSE increased with window duration for all three methods (Table S3B). These calendar-day windows differ from the observed-acquisition blocks used in Vombsjön.

### S3.3 Hidden-gap activity

For a window [a, b] in year y,

`A_gap = Σ_(t=a+1,...,b) |C_t − C_(t−1)| / (Q95_y − Q05_y)`

where the sum includes only daily transitions lying wholly inside the window and the denominator is the dense-reference common-support scale. A_gap is computed from the dense reference that was deliberately hidden from each reconstruction. It is a retrospective descriptor of the concealed dynamics and is not available inside a real observation gap. Its association with error is summarized by the within-year Spearman correlation between A_gap and scenario nRMSE, averaged with equal year weight (Table S3C). The association was positive at every duration; intervals excluded zero for linear interpolation and default double logistic at all durations, and for the smoothing spline at 30 and 45 days. Low, medium and high activity classes are tertiles within each duration and are used for display.

### S3.4 Peak containment

±10-day success was compared between windows that did and did not contain the reference global peak (Table S3D). For linear interpolation, success was lower inside the window at every duration. For default double logistic and the smoothing spline, the reduction was clear only for 45-day windows; for 10-day windows, success inside and outside was similar for default double logistic (0.571 versus 0.578) and slightly higher inside for the smoothing spline (0.602 versus 0.589). The 45-day result reported in Section 3.3 therefore does not extend to all durations.

### S3.5 Implementation

For random deletion, the target count was n_delete = floor(p × N_interior + 0.5), and the replicate seed was 20260901 + 100000 × (year − 2019) + 1000 × k + r, where k = 1–4 indexes the deletion level and r = 1–100 the replicate. Deleted dates were drawn without replacement from the chronologically ordered interior inputs using a PCG64 generator. Consecutive windows were enumerated exhaustively without random sampling. All methods received identical masks, and spline settings were inherited from each year's outer-fold selection without scenario-specific retuning. Scenarios are nested within years: outcomes were averaged within year and stratum (deletion level, duration, activity class or peak containment) and then across years with equal weight. Uncertainty used 10,000 percentile bootstrap resamples of whole years (master seed 20260918, with a separate derived sub-seed for each estimand), using the same sampled years for all methods within a comparison. Peak success used reference-eligible scenarios as its denominator, with a failed or unavailable reconstructed peak counted as non-success.

**Table S3. Erken controlled-missingness details.**

(A) Random deletion of interior actual-mask inputs (700 masks per level). Equal-year estimates (95% whole-year interval).

| Level | nRMSE LI | nRMSE DL | nRMSE SS | ±10-d success LI | ±10-d success DL | ±10-d success SS |
|---|---|---|---|---|---|---|
| 10% | 0.209 (0.162–0.252) | 0.253 (0.221–0.288) | 0.228 (0.192–0.259) | 0.694 (0.401–0.977) | 0.577 (0.161–0.861) | 0.589 (0.271–0.883) |
| 20% | 0.217 (0.176–0.254) | 0.258 (0.226–0.291) | 0.236 (0.204–0.264) | 0.659 (0.353–0.936) | 0.579 (0.183–0.864) | 0.596 (0.317–0.864) |
| 30% | 0.225 (0.189–0.257) | 0.265 (0.240–0.295) | 0.243 (0.214–0.269) | 0.634 (0.327–0.904) | 0.594 (0.240–0.879) | 0.614 (0.341–0.867) |
| 50% | 0.247 (0.220–0.273) | 0.288 (0.267–0.312) | 0.275 (0.244–0.306) | 0.579 (0.317–0.811) | 0.566 (0.270–0.836) | 0.581 (0.329–0.803) |

(B) Consecutive calendar-day deletion windows.

| Duration (windows; inputs removed) | nRMSE LI | nRMSE DL | nRMSE SS | ±10-d success (LI / DL / SS) |
|---|---|---|---|---|
| 10 d (1,379; 1–5) | 0.208 (0.161–0.250) | 0.253 (0.219–0.288) | 0.227 (0.193–0.259) | 0.690 / 0.578 / 0.589 |
| 20 d (1,525; 1–8) | 0.214 (0.170–0.254) | 0.257 (0.224–0.291) | 0.235 (0.203–0.264) | 0.668 / 0.575 / 0.592 |
| 30 d (1,475; 1–11) | 0.221 (0.179–0.259) | 0.263 (0.232–0.296) | 0.246 (0.215–0.275) | 0.650 / 0.559 / 0.593 |
| 45 d (1,367; 1–14) | 0.238 (0.198–0.277) | 0.289 (0.263–0.318) | 0.280 (0.243–0.315) | 0.610 / 0.482 / 0.547 |

(C) Hidden-gap activity: within-year Spearman correlation between A_gap and nRMSE (equal-year, seven years), with A_gap tertile cuts.

| Duration | A_gap tertile cuts (observed range) | LI | DL | SS |
|---|---|---|---|---|
| 10 d | 0.162 / 0.641 (0.007–6.456) | 0.273 (0.045–0.511) | 0.360 (0.248–0.484) | 0.197 (−0.028–0.420) |
| 20 d | 0.410 / 1.531 (0.025–11.128) | 0.367 (0.103–0.635) | 0.400 (0.306–0.489) | 0.240 (−0.003–0.498) |
| 30 d | 0.747 / 2.555 (0.049–15.484) | 0.421 (0.162–0.679) | 0.464 (0.385–0.544) | 0.309 (0.082–0.543) |
| 45 d | 1.260 / 4.190 (0.271–17.289) | 0.532 (0.276–0.731) | 0.416 (0.264–0.547) | 0.464 (0.312–0.618) |

45-day activity-class nRMSE (low / medium / high; 456 / 455 / 456 windows): LI 0.216 / 0.237 / 0.273; DL 0.274 / 0.282 / 0.317; SS 0.246 / 0.282 / 0.316.

(D) Peak containment: ±10-day success with the reference global peak outside / inside the window.

| Duration (windows outside / inside) | LI | DL | SS |
|---|---|---|---|
| 10 d (1,320 / 59) | 0.705 / 0.390 | 0.578 / 0.571 | 0.589 / 0.602 |
| 20 d (1,403 / 122) | 0.707 / 0.286 | 0.581 / 0.521 | 0.594 / 0.564 |
| 30 d (1,303 / 172) | 0.706 / 0.288 | 0.575 / 0.462 | 0.590 / 0.574 |
| 45 d (1,122 / 245) | 0.704 / 0.252 | 0.517 / 0.387 | 0.563 / 0.445 |

A_gap is computed retrospectively from the hidden dense reference and is not available inside a real observation gap; it is not an operational predictor. Overlapping windows are nested within years and are not independent seasonal replicates.

## S4. Sensitivities, diagnostics and exploratory analyses

### S4.1 Cross-validated double logistic

In Erken, `p_seapar` was selected from 0.0–1.0 in steps of 0.1 using only training years, with exact ties assigned to the larger value. All seven folds selected 0. Relative to the default (`p_seapar` = 1), the cross-validated setting gave lower nRMSE (0.239 versus 0.250), higher daily trajectory correlation (0.776 versus 0.742), higher ±10-day success (0.714 versus 0.571), similar mean absolute peak-date error (53.0 versus 54.4 days) and larger absolute integral error (139.5 versus 126.0 µg d L⁻¹) (Table S4C).

In Vombsjön, the cross-validated setting was transferred as a separately reported sensitivity and evaluated on the primary common dates; all of its fits succeeded. Isolated nRMSE changed little (0.1694 versus 0.1701), whereas four-acquisition nRMSE was higher (0.2820 versus 0.2711). Isolated ±10-day success increased from 0.40 to 0.50, while mean absolute observed-proxy peak error increased from 22.3 to 39.0 days. The sensitivity moved individual metrics in different directions and did not replace the default benchmark in either lake.

### S4.2 Vombsjön processor sensitivities

Official L2A (sensitivity) and L1C (diagnostic) were evaluated with the same withholding designs and estimators as primary ACOLITE, each on its own observation calendar (Table S4A–B). For L2A, the 2025 observed maximum occurred on 26 December at the support boundary and was not identifiable; L2A peak summaries therefore use nine years, with 9/18/26/34 reference-eligible scenarios. Differences between processors combine processing with observation availability and support, and they do not form a processor ranking.

### S4.3 Peak-tolerance sensitivity

Success at ±5, ±10 and ±15 days uses one denominator: all reference-eligible scenarios, with failed fits or unavailable reconstructed peaks counted as non-success (Table S4D). The reference is the maximum among quality-controlled observed MCI values within annual support, not the ecological bloom peak. Under ACOLITE four-acquisition withholding, the three methods had equal success at ±5 days (0.125), whereas default double logistic had the highest proportion at ±10 days (0.325) and ±15 days (0.550). No tolerance produced a uniform method ordering.

### S4.4 Native-MCI companion metrics

Native-MCI bias, MAE and RMSE are reported for each processor and method (×10⁻³; Table S4E). MCI is a reflectance-difference index without concentration units. Because each isolated scenario withholds one date, scenario RMSE equals absolute error, and isolated MAE equals isolated RMSE. Year-level RMSE is the mean of scenario RMSEs. In the isolated and four-acquisition designs shown, equal-year bias was small relative to MAE for every processor and method.

**Table S4. Sensitivities, processor diagnostics, timing tolerances and native-MCI companion metrics.**

Vombsjön processor calendars are independent; rows are not compared across processors. ACOLITE is the primary series, L2A a sensitivity and L1C a diagnostic. Peak timing refers to the maximum among quality-controlled observed MCI values within annual support, not the ecological bloom peak.

(A) Processor roles and support.

| Processor | Role | Observed dates, 2017–2026 | 2026 support ends | Scenarios (isolated / 2 / 3 / 4 acquisitions) | Peak-identifiable years |
|---|---|---:|---|---|---:|
| ACOLITE `rhos` | Primary | 335 | 3 August | 315 / 305 / 295 / 285 (1,200) | 10 |
| L2A BOA | Sensitivity | 419 | 20 September | 399 / 389 / 379 / 369 (1,536) | 9 |
| L1C TOA | Diagnostic | 408 | 11 August | 388 / 378 / 368 / 358 (1,492) | 10 |

(B) L2A and L1C metrics under isolated and four-acquisition withholding (LI / DL / SS).

| Processor, design | nRMSE | Withheld-date r | ±10-d success | Mean absolute peak error (d) |
|---|---|---|---|---|
| L2A, isolated | 0.177 / 0.174 / 0.193 | 0.680 / 0.696 / 0.662 | 0.667 / 0.556 / 0.444 | 21.6 / 20.9 / 27.1 |
| L2A, 4 acquisitions | 0.237 / 0.245 / 0.307 | 0.695 / 0.647 / 0.667 | 0.278 / 0.333 / 0.278 | 34.2 / 26.7 / 32.3 |
| L1C, isolated | 0.204 / 0.194 / 0.226 | 0.576 / 0.587 / 0.557 | 0.500 / 0.500 / 0.300 | 32.8 / 34.6 / 49.5 |
| L1C, 4 acquisitions | 0.262 / 0.276 / 0.329 | 0.619 / 0.527 / 0.623 | 0.275 / 0.300 / 0.350 | 43.7 / 38.4 / 38.0 |

(C) Cross-validated (`p_seapar` = 0; secondary sensitivity) versus default (`p_seapar` = 1) double logistic.

| Setting | Metric | CV-DL | Default DL |
|---|---|---|---|
| Erken, actual mask | nRMSE | 0.239 (0.207–0.273) | 0.250 (0.215–0.286) |
| Erken, actual mask | Daily trajectory r | 0.776 (0.732–0.817) | 0.742 (0.693–0.796) |
| Erken, actual mask | ±10-d success | 0.714 (0.425–1.000) | 0.571 (0.143–0.857) |
| Erken, actual mask | Absolute peak-date error (d) | 53.0 (2.4–115.9) | 54.4 (3.4–118.0) |
| Erken, actual mask | Absolute integral error (µg d L⁻¹) | 139.5 (68.2–250.3) | 126.0 (34.4–271.2) |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | nRMSE | 0.1694 / 0.2087 / 0.2415 / 0.2820 | 0.1701 / 0.2072 / 0.2384 / 0.2711 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | Withheld-date r | 0.755 / 0.724 / 0.692 / 0.673 | 0.745 / 0.723 / 0.693 / 0.663 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | ±10-d success | 0.500 / 0.400 / 0.333 / 0.350 | 0.400 / 0.400 / 0.433 / 0.325 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | Mean absolute observed-proxy peak error (d) | 39.0 / 32.5 / 30.1 / 34.3 | 22.3 / 29.0 / 31.2 / 27.4 |

Peak errors are rounded half up to one decimal. Erken default-DL intervals in this panel come from the paired cross-validation analysis and differ slightly from Table S2A because of separate resample sub-seeds; point estimates are identical. No integral metric is evaluated for Vombsjön.

(D) ACOLITE peak-tolerance sensitivity, ±5 / ±10 / ±15 days (denominators 10 / 20 / 30 / 40 reference-eligible scenarios).

| Design | LI | DL | SS | CV-DL |
|---|---|---|---|---|
| Isolated | 0.200 / 0.400 / 0.600 | 0.100 / 0.400 / 0.400 | 0.100 / 0.300 / 0.500 | 0.300 / 0.500 / 0.500 |
| 2 acquisitions | 0.100 / 0.300 / 0.450 | 0.100 / 0.400 / 0.550 | 0.150 / 0.300 / 0.350 | 0.350 / 0.400 / 0.500 |
| 3 acquisitions | 0.133 / 0.300 / 0.400 | 0.200 / 0.433 / 0.633 | 0.233 / 0.300 / 0.367 | 0.267 / 0.333 / 0.567 |
| 4 acquisitions | 0.125 / 0.275 / 0.375 | 0.125 / 0.325 / 0.550 | 0.125 / 0.250 / 0.300 | 0.200 / 0.350 / 0.500 |

Four-acquisition values for the other processors (±5 / ±10 / ±15 days):

| Processor | LI | DL | SS |
|---|---|---|---|
| L2A | 0.167 / 0.278 / 0.417 | 0.111 / 0.333 / 0.500 | 0.194 / 0.278 / 0.333 |
| L1C | 0.100 / 0.275 / 0.375 | 0.100 / 0.300 / 0.500 | 0.225 / 0.350 / 0.525 |

(E) Native-MCI companion metrics (equal-year means; ×10⁻³).

| Processor | Method | Bias, isolated | Bias, 4 acquisitions | MAE, isolated | MAE, 4 acquisitions | RMSE, isolated | RMSE, 4 acquisitions |
|---|---|---:|---:|---:|---:|---:|---:|
| ACOLITE | LI | −0.091 | −0.088 | 2.075 | 2.542 | 2.075 | 2.966 |
| ACOLITE | Default DL | −0.110 | −0.025 | 2.140 | 2.838 | 2.140 | 3.278 |
| ACOLITE | SS | −0.078 | −0.033 | 2.362 | 3.475 | 2.362 | 3.949 |
| ACOLITE | CV-DL | −0.073 | 0.080 | 2.097 | 2.890 | 2.097 | 3.327 |
| L2A | LI | −0.059 | −0.002 | 2.614 | 2.887 | 2.614 | 3.388 |
| L2A | Default DL | −0.062 | 0.130 | 2.543 | 3.078 | 2.543 | 3.569 |
| L2A | SS | −0.097 | −0.105 | 2.862 | 3.874 | 2.862 | 4.441 |
| L1C | LI | −0.054 | −0.033 | 2.331 | 2.473 | 2.331 | 2.912 |
| L1C | Default DL | −0.058 | −0.014 | 2.209 | 2.614 | 2.209 | 3.074 |
| L1C | SS | −0.088 | −0.010 | 2.590 | 3.299 | 2.590 | 3.767 |

Isolated MAE equals isolated RMSE because each isolated scenario withholds one date. MCI is a reflectance-difference index without concentration units.

### S4.5 Exploratory Erken multiple-event analysis (secondary/exploratory)

The event protocol was frozen after the global-maximum results had been inspected. It is therefore secondary and exploratory and does not replace the predefined global-peak evaluation. Reference events were detected within each open-water segment without smoothing, using a minimum separation of 30 days and a prominence of at least 0.30 × the yearly Q95 − Q05 scale. This identified 18 events: 2, 3, 2, 2, 3, 2 and 4 in 2019–2025. Reconstructed candidates were detected without height, prominence or separation thresholds and could match a reference event only within the same year and segment and within 15 days. One-to-one assignment first maximized the number of matched events and then minimized total timing error.

Pooled counts of events recovered within ±10 days were 17, 15 and 5 of 18 for linear interpolation, the smoothing spline and default double logistic, respectively. Equal-year ±10-day recovery fractions were 0.952 (0.857–1.000), 0.833 (0.690–0.952) and 0.333 (0.167–0.476). The cross-validated double logistic gave an equal-year recovery fraction of 0.548 (0.310–0.786), compared with 0.333 for the default in the same paired analysis. Pooled counts and equal-year fractions are different estimands, and neither is a primary result.

## S5. Vombsjön field proxy-consistency support

### S5.1 Field data and coordinate audit

Lake Vombsjön is a eutrophic lake with a surface area of 11.8 km², a mean depth of 6.6 m and a maximum depth of 16 m (Rabow et al., 2025). The field record comprises 54 sampling dates (6 in 2018, 22 in 2019 and 26 in 2020) of laboratory fluorometric Chl-a from water-column-integrated samples, over 0–2 m in 2018 and 0–6 m in 2019–2020 (Rabow et al., 2025). Twenty-one dates have a measured GPS coordinate that passed quality control, and 31 dates have no measured coordinate. Two dates, 2020-06-10 and 2020-06-24, carry a measured coordinate with an unresolved longitude discrepancy in the source data and were retained without correction. Unresolved and missing coordinates contribute no polygon vertex; these dates remain eligible for the fixed-polygon comparison because the polygon does not depend on any date's coordinate. Field sampling clock times are unavailable.

### S5.2 Fixed spatial support

The field comparison used one fixed pelagic area, identical on every field date: the unbuffered convex hull, in a projected metric reference frame, of the 21 accepted GPS coordinates plus the nominal station (55.6775° N, 13.60889° E) as an anchor. The anchor lies inside the hull rather than on its boundary. The hull has six vertices and an area of 247,766 m² (0.248 km²), and 615 pixel centres on the common 20 m grid fall inside it. It was not clipped to a shoreline because no authoritative open-water geometry was available; non-water pixels were excluded by each product's native quality assessment. A polygon observation required at least two-thirds of the 615 pixels to be valid, and its value was the median of valid pixel-level MCI. No nominal-point fallback and no date-specific movement were used. This support is distinct from the fixed nominal-station 3 × 3 window used for the temporal MCI series.

### S5.3 Exact-date matchup

Field and satellite observations were paired on exact calendar dates, with zero temporal tolerance and no nearest-date substitution. Same-day products of one processor were reduced to the median of their observation-level medians. Valid exact-date pairs numbered 7 for ACOLITE (0, 4 and 3 in 2018, 2019 and 2020), 9 for L2A (0, 5 and 4) and 9 for L1C (0, 5 and 4). Twenty-nine field dates per processor had no same-day product, and same-day polygon observations fell below two-thirds validity on 18 dates for ACOLITE and 16 each for L2A and L1C. No processor had a valid 2018 pair: four 2018 dates had no product, and on 9 July and 20 August the polygon fell below two-thirds validity.

Valid ACOLITE pairs covered field Chl-a of 1.206–33.9 µg L⁻¹, and valid L2A and L1C pairs covered 1.206–49.8 µg L⁻¹, whereas the complete field record spans 0.896–125.7 µg L⁻¹. Integrated-water-column samples are not equivalent to satellite-surface Chl-a, and exact-date pairing does not resolve differences in horizontal support, vertical support or sampling time. The pairs were examined descriptively only: no calibration, regression or correlation was calculated, and field values did not enter fitting or tuning. The complete record of all 54 field dates and three processors is given in Table S5.

### S5.4 Actual-GPS 3 × 3 sensitivity

As a secondary spatial audit, a 3 × 3 window was extracted at each date's accepted measured coordinate, without nominal fallback and without extraction for the two unresolved dates. Of the 21 accepted-GPS dates, 11 had no same-day product. Exact-date eligibility was 3 dates for ACOLITE and 4 each for L2A and L1C. This sensitivity was not used to construct or tune the fixed polygon and is not the governing field comparison.

**Table S5. Complete Vombsjön field–satellite proxy-consistency audit.** Table S5 lists all 162 records (54 field dates × 3 processors) with field date, year, processor and role, field Chl-a (µg L⁻¹), integrated sampling depth, coordinate status, whether the date contributed a polygon vertex, the number of same-day products, polygon observation status, polygon MCI and valid-pixel count and fraction for valid pairs, the valid-pair flag and the reason a pair was unavailable. Polygon MCI is the same-day median of valid pixel-level MCI over the fixed pelagic polygon (615 pixel centres on the 20 m grid). Valid exact-date pairs: ACOLITE 7 (2018/2019/2020: 0/4/3), L2A 9 (0/5/4) and L1C 9 (0/5/4). Field values entered no fitting, tuning or method selection. Sampling clock times are unavailable. Integrated-water-column Chl-a is not treated as satellite-surface Chl-a.

## Supplementary figure captions

**Figure S1. Erken Sentinel-2 observation-mask window-size stability.** (a) Usable observation dates in 2019–2025 for 1 × 1, 3 × 3 and 5 × 5 station-centred SCL windows under strict, preferred and relaxed pixel-count rules, with thresholds scaled to window size. (b) Number of inter-observation gaps longer than 10, 20, 30 and 45 days for each window under the preferred scaled rule. The 3 × 3 window with the preferred rule is the frozen primary observation mask; the 1 × 1 and 5 × 5 windows are spatial-rule diagnostics and were not used for reconstruction.

**Figure S2. Annual Erken dense-reference trajectories and actual-mask reconstructions, 2019–2025.** Each panel shows daily CHLF (dense reference), actual-mask Sentinel-2 input dates, and the linear-interpolation, default TIMESAT double-logistic and TIMESAT smoothing-spline reconstructions within that year's common support; dotted lines mark the common-support boundaries. The smoothing spline uses each year's outer-fold smoothing value, shown in the panel title. Asterisks mark the boundary-truncated common support in 2019 and 2025, whose common-support maxima are not interpreted as full-year maxima. Y-axis limits vary among years to preserve within-year detail.

**Figure S3. Extended Erken controlled-missingness results.** (a) Equal-year nRMSE and (b) ±10-day global-peak timing success under random deletion of 10%, 20%, 30% and 50% of interior actual-mask inputs. (c) ±10-day success for 10-, 20-, 30- and 45-day calendar-day deletion windows with the reference global peak outside (open symbols) or inside (filled symbols) the window; intervals are omitted for legibility. (d) Equal-year within-year Spearman correlation between $A_{\mathrm{gap}}$ and nRMSE by window duration. Bars show 95% whole-year bootstrap intervals. $A_{\mathrm{gap}}$ is computed retrospectively from the hidden dense reference and is unavailable inside a real observation gap.
