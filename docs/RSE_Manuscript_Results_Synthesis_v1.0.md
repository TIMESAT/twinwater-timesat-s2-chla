# RSE manuscript results synthesis v1.0

**Date:** 2026-10-03  
**Evidence baseline:** local repository commit c3db5b65a7cf6b5dc6d1a054e8004d3934f0c1c0  
**Scope:** manuscript interpretation, synthesis, and figure/table planning from existing frozen evidence; no new scientific analysis.

This document preserves the manuscript-level synthesis completed in the Work task. It is not a new scientific master, execution specification, analysis contract, progress ledger, or approved reviewer-response plan. The [active project master](Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md), [Erken reconstruction contract](Reconstruction_Analysis_Contract_v1.0.1.md), [transfer freeze v1.1](../config/erken_vomb_transfer_freeze_v1.1.json), and [locked-transfer execution specification](Vombsjon_Locked_Transfer_Execution_v1.0.md) retain authority. Scientific settings, method roles, processor roles, estimators, and failure rules are unchanged.

The local checkout contains committed Vombsjön transfer results. The [transfer manifest](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_manifest.json) records completed execution from clean implementation commit 50b2e4b9adecd789800d7b82ea9fbf3291848867, with no parameter tuning and no field use for tuning. The [execution-gate evidence](../results/vombsjon/execution_gate_closure/v1.0/vombsjon_execution_gate_manifest.json) records 7/7 PASS, and the [saved validation](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_validation.csv) records 9/9 PASS. Older performance-pending statements in STATUS.md and DATA_INVENTORY.md are stale relative to this committed evidence. Historical authorization flags in frozen records remain historical; they are not rewritten here. The requested documentation task leaves those ledgers and decisions.md untouched.

The preceding read-only inspection verified all 24 manifest input hashes, nine code hashes, and 15 listed output hashes against local bytes. One listed output, the approximately 1.13-GB Vombsjön daily-prediction CSV, is locally present and manifest-matched but excluded from Git tracking. It is not committed evidence for the figure recommendations below. The other 14 listed outputs are tracked. This document does not claim renewed access to raw external satellite archives or independent reverification of external licence documents. Committed provenance records and gate closure establish the recorded execution evidence; a preserved invocation is not execution job-log verification.

No performance was rerun, metrics recomputed, settings changed, new analysis introduced, or frozen role reinterpreted to create this document. Numerical values below are rounded for presentation from the already inspected committed tables. Figure and manuscript recommendations remain proposals, not newly accepted scientific decisions.

## 1. Strongest defensible manuscript-level conclusions

The strongest conclusion is that **reconstruction reliability depends on the metric, the year, and the missing observations**. Vombsjön supports the usefulness of simple interpolation for pointwise reconstruction, especially under longer acquisition blocks, but it does not reproduce a universal Erken method ranking. Peak timing remains substantially less dependable than successful curve generation or moderate trajectory correlation.

Linear interpolation provides a strong pointwise baseline in both lakes. Its advantage over default double logistic is less uniform in Vombsjön than in Erken, while its lower ACOLITE nRMSE relative to the transferred spline occurs in every Vombsjön year and withholding stratum. Longer missing-observation blocks degrade pointwise reconstruction, but correlation, peak timing, and integral behavior expose different method strengths.

The transfer therefore supports **metric-specific reliability**, not uniformly reliable bloom phenology or validated daily Chl-a reconstruction. Withheld Sentinel-2 MCI is the primary quantitative Vombsjön target. Field Chl-a provides complementary ecological/proxy-consistency evidence only. The seven valid ACOLITE field pairs are confined to 2019–2020; there is no contemporaneous valid fixed-polygon field–satellite validation in 2018.

## 2. Evidence hierarchy

| Evidence class | Evidence and defensible role |
|---|---|
| Primary quantitative evidence | Erken actual-mask reconstruction against withheld daily CHLF; Vombsjön ACOLITE reconstruction against withheld observed MCI |
| Planned secondary quantitative evidence | Erken controlled-gap experiments; Vombsjön conditionally identifiable observed-MCI peak timing |
| Sensitivity analyses | Official L2A processing sensitivity; Erken-selected CV double logistic; ±5/±15-day peak tolerances; separately labelled spatial sensitivities where available |
| Diagnostic/descriptive evidence | L1C diagnostic baseline; Vombsjön field-consistency pairs; supplementary Erken event analysis, explicitly secondary/exploratory rather than a replacement for global-peak evaluation |
| Unavailable or insufficient evidence | Daily Vombsjön field truth, validated unobserved ecological peaks, onset/end truth, Vombsjön integral accuracy, contemporaneous valid 2018 polygon field–satellite pairs, and a matched-calendar Vombsjön processor ranking |

Field reference, observed satellite proxy, and reconstructed daily estimate remain distinct layers. Erken's dense CHLF experiment isolates temporal sampling/reconstruction using masked versions of the same reference variable. It does not independently validate satellite retrieval accuracy. Vombsjön's withheld observations retain satellite observation uncertainty and are not error-free ecological truth.

## 3. Vombsjön primary ACOLITE results

In the following Vombsjön tables, triplets are ordered **linear interpolation / default double logistic / smoothing spline**. The spline uses the frozen Erken-selected p_smooth = 10; default double logistic retains p_seapar = 1.

| Withholding design | Equal-year nRMSE | Withheld-date trajectory r | Observed-peak success within ±10 days |
|---|---:|---:|---:|
| One isolated date | .165 / .170 / .182 | .755 / .745 / .729 | .400 / .400 / .300 |
| Two consecutive observed dates | .196 / .207 / .232 | .760 / .723 / .743 | .300 / .400 / .300 |
| Three consecutive observed dates | .221 / .238 / .269 | .738 / .693 / .740 | .300 / .433 / .300 |
| Four consecutive observed dates | .254 / .271 / .333 | .714 / .663 / .694 | .275 / .325 / .250 |

These estimates use ten years, 2017–2026. Pointwise strata contain respectively **315, 305, 295, and 285 scenarios**, giving 1,200 ACOLITE scenarios. Pointwise availability is complete. Native-MCI MAE and mean scenario RMSE have the same aggregate ordering as nRMSE. From isolated to four-date withholding, mean scenario RMSE rises from .002075 to .002966 for linear, .002140 to .003278 for double logistic, and .002362 to .003949 for spline.

The saved 95% year-cluster intervals for four-date nRMSE are:

- Linear: **.254 [.216, .293]**.
- Default double logistic: **.271 [.226, .323]**.
- Spline: **.333 [.283, .380]**.

These are descriptive method estimates, not a new paired significance test. Neither overlapping nor non-overlapping individual intervals substitutes for an unreported inferential comparison. Small aggregate bias also does not establish accurate individual predictions: four-date bias is approximately −.0000879/−.0000252/−.0000332 MCI, with all three saved intervals spanning zero.

Source: [committed equal-year summaries](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_equal_year_summary.csv).

## 4. Vombsjön per-year heterogeneity and influential-year limitations

| Year | Isolated nRMSE: linear / DL / spline | Four-date nRMSE: linear / DL / spline |
|---|---:|---:|
| 2017 | .190 / .218 / .201 | .284 / .287 / .364 |
| 2018 | .118 / .119 / .126 | .185 / .171 / .221 |
| 2019 | .169 / .209 / .175 | .309 / .371 / .414 |
| 2020 | .183 / .154 / .199 | .276 / .225 / .397 |
| 2021 | .105 / .104 / .124 | .167 / .199 / .250 |
| 2022 | .202 / .191 / .232 | .261 / .263 / .356 |
| 2023 | .107 / .132 / .130 | .195 / .220 / .275 |
| 2024 | .119 / .109 / .153 | .192 / .228 / .220 |
| 2025 | .215 / .226 / .238 | .304 / .315 / .411 |
| 2026 | .241 / .238 / .241 | .367 / .433 / .421 |

**Linear versus spline is directionally robust:** linear has lower nRMSE in every year in all four withholding strata. That result is not created by one or two exceptional years.

**Linear versus default double logistic is conditional:** their annual nRMSE wins are 5:5 under isolated withholding, 6:4 for two-date blocks, and 8:2 for three- and four-date blocks. Double logistic wins the longer-block comparisons in 2018 and 2020. Equal-year aggregation prevents years with more dates or overlapping scenarios from receiving greater aggregate weight, but does not eliminate influence from extreme annual metric values.

**A difficult year depends on the metric.** For four-date withholding, 2026 has high normalized errors and weak correlations, but its native-MCI RMSE is lower than in 2021 or 2024. In 2021, linear has nRMSE .167 and r .911 despite native RMSE .00400; in 2026, nRMSE is .367 and r .383 despite native RMSE only .00255. Training-based normalization and changing MCI amplitude affect the comparison.

The 2026 ACOLITE support runs from **10 January to 3 August**. It is partial observed support, not a complete annual season. Other processors have their own boundaries; these are not silently aligned or extended.

Peak-error averages are more exposed to influential years than the linear–spline nRMSE ordering. In 2026, primary-method peak errors are approximately 95–107 days across designs. In 2017, spline's four-date mean peak error reaches 118.5 days. These values materially shape aggregate timing results. **No committed Vombsjön leave-one-year-out influence table exists in the inspected result package**, so robustness to deleting these years cannot be asserted. Years must not be deleted to improve the narrative.

Sources: [annual summaries](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_summary.csv), [eligibility and support](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv).

## 5. Gap/block-length dependence

In Vombsjön, primary-method nRMSE increases with block size in every year. Correlation and peak success are not strictly monotonic. The defensible statement is that **pointwise reconstruction deteriorated as more consecutive observed acquisitions were withheld**.

Vombsjön blocks contain two, three, or four observed dates; they are not two-, three-, or four-day gaps. Calendar spans vary with the observation calendar. The committed summaries do not establish a calendar-day failure threshold or a duration-adjusted processor comparison. Actual training and withheld dates remain available in the [scenario table](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_holdout_scenarios.csv).

Erken supplies the stronger calendar-duration evidence. Between 10- and 45-day deletion windows, equal-year nRMSE increases from **.208 to .238** for linear, **.227 to .280** for spline, and **.253 to .289** for default double logistic. The 45-day value exceeds the 10-day value in all seven years for every method. At fixed 45-day duration, low-to-high activity nRMSE rises from .216 to .273 for linear, .246 to .316 for spline, and .274 to .317 for double logistic.

For **45-day Erken windows containing the reference global peak**, linear retains the lowest nRMSE but has lower descriptive ±10-day peak success: **.252**, versus **.445** for spline and **.387** for double logistic. This is a particularly useful demonstration of metric-specific reliability, without interpreting overlapping uncertainty intervals as proof of a superior timing method.

Erken random deletion provides additional planned secondary evidence: from 10% to 50% deletion, equal-year nRMSE rises .209→.247 for linear, .228→.275 for spline, and .253→.288 for default double logistic. Binary peak success need not decline monotonically at every step.

A_gap is a retrospective descriptor obtained from Erken's hidden complete reference. It cannot become an observed operational predictor inside an unknown Vombsjön gap. Duration-specific activity tertiles retain their existing visualization role; exploratory random-density/max-gap strata must not be relabelled confirmatory.

Sources: [Erken duration summaries](../results/reliability_synthesis/v1.0/erken_reliability_consecutive_duration_summary.csv), [activity summaries](../results/reliability_synthesis/v1.0/erken_reliability_consecutive_activity_summary.csv), [peak-containment summaries](../results/reliability_synthesis/v1.0/erken_reliability_consecutive_peak_containment_summary.csv), [random-deletion summaries](../results/reliability_synthesis/v1.0/erken_reliability_random_equal_year_deletion.csv).

## 6. Metric-specific nRMSE, correlation, and peak behavior

Pointwise error, correlation, and peak timing do not produce interchangeable rankings:

- With three-date ACOLITE blocks, spline has marginally higher aggregate correlation than linear, **.740 versus .738**, while its nRMSE is substantially larger, **.269 versus .221**. The correlation difference is tiny relative to its uncertainty.
- Default double logistic has higher ±10-day peak success than linear in all three consecutive-block strata, despite higher aggregate pointwise error.
- Even timing summaries can disagree. With two-date blocks, linear has slightly lower mean absolute peak error than double logistic, **28.60 versus 28.98 days**, but lower ±10-day success, **.30 versus .40**.
- In 2020, default double logistic is a strong counterexample to a general linear-interpolation claim: four-date nRMSE is .225 versus .276 for linear, correlation .735 versus .691, and mean absolute peak error 5.25 versus 42 days.

Peak reliability remains limited. Four-date success is **.275 [.150, .400]** for linear, **.325 [.075, .575]** for double logistic, and **.250 [.125, .400]** for spline. Mean absolute peak errors for that design are **30.90, 27.38, and 41.54 days**, respectively.

The timing estimates use only **10/20/30/40 reference-eligible peak-withholding scenarios**, rather than all 315/305/295/285 pointwise scenarios. They concern the maximum of the available, QC-passed observed MCI series. They do not identify the true unobserved ecological bloom maximum. Repeated peak-withholding windows are nested within years, not independent peak events.

Sources: [equal-year summaries](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_equal_year_summary.csv), [peak records](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_peak_metrics.csv).

## 7. Comparison between Erken and Vombsjön

| Finding | Erken | Vombsjön primary ACOLITE |
|---|---|---|
| Aggregate pointwise ordering | Linear, spline, default DL | Linear, default DL, spline |
| Linear–DL annual robustness | Lower linear nRMSE in 7/7 actual-mask years | Split under isolated withholding; stronger linear advantage for longer blocks |
| Correlation | Linear exceeds both alternatives in all seven actual-mask years | Ordering varies with year and block size |
| Peak timing | Large errors concentrated particularly in 2020 and 2025 | Large errors particularly in 2026, with additional method-specific extremes |
| Integral accuracy | Quantitatively evaluated; default DL has lowest descriptive mean absolute error | Unavailable without a dense reference |
| Hidden-gap activity | Directly characterizable retrospectively | Unknown inside real missing intervals |

Erken actual-mask nRMSE is **.203/.223/.250** for linear/spline/default DL, and correlation is **.864/.830/.742**. Linear has lower nRMSE than spline in six of seven years and than default DL in all seven. Saved leave-one-year-out summaries preserve the aggregate nRMSE ordering. Existing paired nRMSE intervals support these contrasts more directly than the Vombsjön tables, which do not contain corresponding paired-contrast inference.

Erken peak means are much less stable. In the already committed omission analysis, removing 2025 reduces mean absolute peak error from **34.57 to 7.0 days** for linear, **54.57 to 30.0** for spline, and **54.36 to 28.92** for double logistic. Linear's ±10-day advantage becomes a tie in some omission summaries but never reverses; the spline–double-logistic contrast can reverse. Follow the v1.0.1 interpretive correction rather than the superseded wording.

Default DL's Erken mean absolute common-support integral error is 126.0 µg·d/L, compared with 157.5 for linear and 187.1 for spline. This is a descriptive advantage: the saved paired difference intervals cross zero. Accurate integral estimation does not establish correct event timing.

**Numerical skill levels must not be directly compared between lakes.** Erken nRMSE uses dense-reference common-support Q95−Q05; Vombsjön uses scenario-specific retained-training MCI Q95−Q05. Erken correlation evaluates daily common-support trajectories, whereas Vombsjön correlation uses median-collapsed repeated withheld-date predictions. Erken calendar-day deletion windows differ from Vombsjön observed-acquisition blocks. The transferable result is the pattern of reliability and trade-offs, not a claim that a smaller nRMSE makes one lake easier or better reconstructed.

Sources: [Erken primary summaries](../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_equal_year_summary.csv), [paired contrasts](../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_paired_summary.csv), [saved omission summaries](../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_leave_one_year_out.csv), [corrected synthesis v1.0.1](../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md).

## 8. Separate L2A, L1C, and CV-DL interpretations

| Separate evidence layer | Isolated nRMSE: linear / DL / spline | Four-date nRMSE: linear / DL / spline |
|---|---:|---:|
| L2A sensitivity | .177 / .174 / .193 | .237 / .245 / .307 |
| L1C diagnostic | .204 / .194 / .226 | .262 / .276 / .329 |

Both reproduce the longer-block pointwise ordering, but default double logistic slightly leads isolated withholding. Other rankings change: in L1C four-date withholding, spline has the highest descriptive correlation and peak-success rate despite the largest pointwise error.

These are **within-processor observations**. ACOLITE, L2A, and L1C have 335, 419, and 408 eligible temporal dates, respectively, and their own training/test calendars. They yield 1,200, 1,536, and 1,492 scenarios. Differences combine processing, availability, and support; they cannot establish processor superiority. ACOLITE remains primary by its frozen aquatic-processing role, L2A remains a separate sensitivity, and L1C remains diagnostic.

L2A peak summaries use only **nine available years**: the 2025 observed maximum occurs on 26 December, its support boundary, and is nonidentifiable. Available peak-scenario counts are 9/18/26/34. The unavailable year remains visible rather than being silently removed from the evidence description.

CV double logistic retains its separately frozen p_seapar = 0 sensitivity role. In ACOLITE it slightly improves isolated nRMSE, .1701 to .1694, but worsens consecutive-block nRMSE; four-date nRMSE changes .2711 to .2820. Its isolated peak-success rate rises from .40 to .50 while mean absolute peak error rises from 22.3 to 39.0 days. It does not justify replacing the default primary benchmark.

The Erken CV-DL sensitivity likewise demonstrates a trade-off: actual-mask mean nRMSE improves .250→.239, while absolute integral error increases 126.0→139.5 µg·d/L. The supplementary event analysis reports 17/18, 15/18, and 5/18 events recovered within ten days for linear, spline, and default DL. These are descriptive pooled event counts, not equal-year rates or primary global-peak validation. The event protocol followed inspection of global-maximum results and remains secondary/exploratory.

Sources: [Vombsjön equal-year summaries](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_equal_year_summary.csv), [Erken CV-DL sensitivity](../results/reliability_synthesis/v1.0/erken_reliability_double_logistic_cv_actual_mask_summary.csv), [Erken event evidence](../results/reliability_synthesis/v1.0/erken_reliability_event_equal_year_summary.csv), [event protocol](Seasonal_Event_Detection_and_Matching_Protocol_v1.0.md), [DL sensitivity protocol](Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0.md).

## 9. Complementary field consistency and the 2018 limitation

| Year | Field dates | Valid ACOLITE polygon pairs | L2A pairs | L1C pairs |
|---|---:|---:|---:|---:|
| 2018 | 6 | **0** | **0** | **0** |
| 2019 | 22 | 4 | 5 | 5 |
| 2020 | 26 | 3 | 4 | 4 |
| Total | 54 | **7** | 9 | 9 |

All 162 field-date × processor records, including unavailable pairs, remain in the evidence. The seven ACOLITE pairs qualitatively support lower MCI on two low-Chl-a spring dates and positive MCI on sampled higher-Chl-a dates. Examples are 1.206 µg/L with MCI −.000969 on 15 May 2019 and 33.9 µg/L with MCI .004618 on 20 August 2019. However, the paired Chl-a range is only **1.206–33.9 µg/L**, compared with **0.896–125.7 µg/L** in the complete field source. The paired subset misses the extreme 2018 regime. No field correlation or regression was produced by the locked execution.

For 2018 specifically:

- Four field dates have no same-day satellite product.
- The remaining two, **9 July and 20 August**, fail the frozen two-thirds polygon-validity requirement.
- Therefore, **2018 has no contemporaneous valid fixed-polygon field–satellite validation for any processor**.

The 2018 temporal MCI experiment remains informative. When its observed ACOLITE peak on 3 August is withheld alone, peak errors are **3 days for linear, 27 for default double logistic, and 41 for spline**. This is a satellite-proxy stress-test result, not validation of the field bloom peak. The extreme field record provides ecological context but cannot demonstrate reconstruction of an independently observed daily bloom maximum.

Additional limitations must remain explicit:

- Temporal reconstruction uses a fixed nominal-station 3×3 target at 20 m with at least six valid pixels; field evidence uses a different, fixed pelagic polygon with 615 target-grid pixel centres and a two-thirds validity rule.
- Field samples integrate approximately 0–2 m in 2018 and 0–6 m in 2019–2020. They are not satellite-surface Chl-a, and no well-mixed equivalence is assumed.
- Field sampling clock times are unavailable. Exact calendar-date matching is not a known acquisition-minus-sampling time interval.
- Actual-GPS 3×3 evidence is a separate, still sparser spatial sensitivity: three eligible ACOLITE observations and four each for L2A/L1C in the input audit.
- The two unresolved 2020 coordinate flags remain preserved. They are not silently corrected; the fixed-polygon comparison does not move with each field coordinate.
- L2A/L1C field pair counts also use different dates from ACOLITE, so they do not support a matched processor ranking.
- Community-composition explanations remain hypotheses rather than demonstrated causes of proxy or reconstruction behavior.

Erken provides stronger independent observation-layer support: ACOLITE MCI has same-date Spearman ρ **.458 [.295, .610]** over 220 common-support dates, but annual associations vary substantially. This supports chlorophyll sensitivity without establishing absolute retrieval accuracy or a transferable calibration. Erken's common-support processor analysis must not be mistaken for a corresponding matched-calendar Vombsjön analysis.

Sources: [Vombsjön field-consistency evidence](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv), [field source](../data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv), [canonical satellite audit](../results/vombsjon/satellite_input_audit/v1.2/vombsjon_satellite_input_audit_manifest.json), [Erken observation-layer results](../results/phase6c/erken_s2_chlf_association_summary.csv), [Erken annual associations](../results/phase6c/erken_s2_chlf_annual_association.csv).

## 10. Uncertainty and denominator interpretation

Preserve the committed **scenario → year → equal-year** reductions and **10,000 whole-year bootstrap draws**. For Vombsjön, the frozen seed is 20260918, reinitialized within each processor/design/block stratum, with the same sampled year indices reused across methods and metrics. Report the existing percentile intervals, available years, finite bootstrap draws, and scenario counts. Do not introduce independent-date/window bootstraps, new pooled denominators, post hoc significance tests, or failure penalties.

Vombsjön RMSE is the mean of scenario RMSEs, not the square root of pooled squared residuals. For isolated one-point scenarios, RMSE equals absolute error. nRMSE uses each scenario's retained-training Q95−Q05. Correlation uses median-collapsed predictions at repeated withheld dates and arithmetic averaging across available years, not a Fisher transformation. These distinctions matter when interpreting non-monotonic correlations across block sizes.

All **16,912 scenario–method status records are successful**, including the separate CV-DL sensitivity. No reconstructed peak is unavailable among reference-eligible peak records in this run. Nevertheless, successful fitting does not establish scientific reliability, and non-reference-eligible scenarios remain distinct from identifiable peak tests.

The frozen handling remains authoritative even where no fit failure occurred:

- A primary-method failure makes the primary paired scenario metrics unavailable; sensitivity availability cannot alter primary support.
- Continuous metrics retain finite-value availability denominators and explicit unavailable counts; no missing metric is imputed as zero.
- Peak reliability uses all reference-eligible scenarios as its denominator, with fit failure or an unavailable reconstructed peak counted as non-success.
- Non-reference-eligible peak scenarios remain recorded but do not enter that reliability denominator.
- A year without an available metric is retained as unavailable; bootstrap draws preserve that availability structure. With fewer than two available years, the point estimate may remain but the interval is unavailable.
- Negative predictions are not clipped, and invalid scales receive no arbitrary epsilon.

Seven Erken and ten Vombsjön years remain modest numbers of seasonal replication units. Thousands of daily values or overlapping windows do not increase that number. Erken's existing paired and omission analyses can be reported; equivalent Vombsjön analyses must not be implied to exist.

Sources: [execution specification](Vombsjon_Locked_Transfer_Execution_v1.0.md), [method statuses](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_method_status.csv), [year summaries and denominators](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_summary.csv), [Erken denominator audit](../results/reliability_synthesis/v1.0/erken_reliability_denominator_audit.csv).

## 11. Likely reviewer concerns and existing evidence

| Likely concern | Existing committed response | Remaining limitation |
|---|---|---|
| Was transfer tuned after seeing Vombsjön? | Erken-only freeze, fixed spline setting, execution hashes, training-only scaling checks, no-tuning manifest | Transfer covers one contrasting lake |
| Are thousands of overlapping windows treated as independent? | Year-first summaries and whole-year bootstrap | Seven Erken and ten Vombsjön year clusters remain modest |
| Do exceptional years drive conclusions? | Complete annual tables; Erken paired and omission analyses | No committed Vombsjön omission analysis; peak tails remain influential |
| Is default double logistic an unfair comparator? | Separate training-selected seasonal-parameter sensitivity | Sensitivity helps some metrics and harms others |
| Does lower RMSE establish better phenology? | Committed correlation, peak, integral, and peak-containment contrasts | Sparse Vombsjön observations do not reveal the true daily ecological peak |
| Is ACOLITE actually superior? | Frozen processing roles and processor-specific availability tables | Vombsjön calendars are unmatched; no processor ranking |
| Is 2018 externally validated? | Full field availability and exclusion records | Zero valid contemporaneous polygon pairs |
| Does moving field support contaminate comparison? | Pre-performance fixed-polygon amendment and preserved coordinate flags | Horizontal and vertical support still differ from the temporal target |
| Could processing provenance explain results? | Gate closure, native QA, corrected ancillary setting, source identities, and baseline audit | No unsupported empirical baseline harmonization; raw archives were not reverified in this task |
| Are the results reproducible from committed artifacts? | Committed frozen configuration, code identities, validation, predictions at withheld dates, and summary tables | The manifest-matched daily-prediction file is local but untracked |

The ancillary-data correction conformed processing to an existing frozen requirement; it was not selected by Vombsjön performance. The Erken processing-baseline audit found no same-acquisition cross-baseline pairs supporting empirical harmonization. Neither issue licenses a new adjustment after inspecting performance.

Evidence anchors: [transfer manifest](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_manifest.json), [saved validation](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_validation.csv), [gate status](../results/vombsjon/execution_gate_closure/v1.0/vombsjon_execution_gate_status.csv), [baseline audit](../results/phase6d/processing_baseline/erken_s2_processing_baseline_gate.json), and the annual, sensitivity, and field tables linked above.

## 12. Proposed Results structure and transition into Discussion

1. **Observation support and validation coverage:** usable dates, annual boundaries, processor calendars, observation-layer proxy evidence, and field-pair attrition.
2. **Erken actual-mask reconstruction:** pointwise fidelity, trajectory agreement, peak timing, and integral trade-offs.
3. **Erken reliability under controlled missingness:** duration, hidden activity, and peak containment; show where rankings diverge.
4. **Locked Vombsjön ACOLITE transfer:** pointwise degradation across acquisition blocks, followed by annual heterogeneity.
5. **Metric-specific transfer and separate sensitivities:** correlation and identifiable proxy peaks; concise L2A and CV-DL findings, with L1C diagnostic detail in Supplementary Information.
6. **Complementary ecological evidence:** seven ACOLITE field pairs, the 2018 satellite stress test, and explicit absence of 2018 paired field validation.

The Results-to-Discussion transition should follow the observed mismatch between metrics: modest pointwise error and moderate correlation coexist with unreliable maximum timing, while influential years and different observation supports constrain generalization. Discussion can then explain representation trade-offs, distinguish sampling uncertainty from observation/proxy uncertainty, and assess what transferred. It should not infer physiological or community mechanisms from these comparisons.

The organizing argument is metric-specific reliability, not an algorithm leaderboard or the validation of TIMESAT as software. Peak timing was a pre-specified candidate; its robustness was evaluated rather than assumed. Erken's exploratory event analysis can explain annual-maximum identity problems without replacing the primary metric.

## 13. Proposed main-text figures and tables

A minimum set is **five figures and two compact tables**. These are manuscript-production proposals under the original plan, not changes to the frozen design. Generate them only from committed frozen outputs, preserving existing estimators and uncertainty.

| Item | Content and purpose | Committed source basis |
|---|---|---|
| Figure 1 — Design and support | Two panels: validation hierarchy and annual observation coverage, including partial support and field-pair availability | Governing documents, Erken sampling evidence, Vombsjön input audit, year eligibility, and field-consistency table |
| Figure 2 — Erken metric trade-offs | Three panels: annual nRMSE, absolute peak error, and integral error, with existing equal-year summaries | Erken reliability actual-mask year and equal-year tables |
| Figure 3 — Erken reliability conditions | Two panels: error by duration/activity and peak success by duration/peak containment; full cell intervals and coverage in SI | Existing duration, activity, and peak-containment summary tables |
| Figure 4 — Primary Vombsjön transfer | Three panels: nRMSE, withheld-date correlation, and observed-peak ±10-day success across four withholding designs, with saved intervals | Vombsjön equal-year summary, with metric-specific denominators |
| Figure 5 — Vombsjön annual heterogeneity | Three compact panels for four-date nRMSE, correlation, and absolute peak error across all ten years; remaining designs in SI | Vombsjön year summary and eligibility table |
| Table 1 — Evidence and availability | Lake, target, support, years, usable dates, field pairs, and validation role | Existing input, eligibility, and field evidence |
| Table 2 — Frozen methods and estimands | Method settings, processor roles, normalization, peak eligibility, and aggregation definitions | Reconstruction contract, transfer freeze, and execution specification |

Figure 4 establishes the aggregate block response; Figure 5 tests whether that message conceals annual heterogeneity. Their roles are distinct. Use consistent method colors and make direction-of-better-performance explicit. Label peak timing as observed-proxy timing and display its much smaller denominator. Do not draw cross-processor rankings or join the two lakes on a common numerical nRMSE scale.

This set avoids standalone main-text processor leaderboards, redundant example curves, and a field scatterplot whose seven points would carry too much narrative weight. A short field-consistency paragraph and Table 1 are sufficient in the main text. There is no need for a separate main-text 2018 figure implying field validation.

The untracked Vombsjön daily-prediction CSV must not be described as a committed source for new daily-curve figures. Committed [withheld predictions](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_withheld_predictions.csv) and [date-collapsed predictions](../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_date_collapsed_predictions.csv) support observed-versus-predicted point displays. Date-collapsed points combine scenario predictions; they are not one full-series fitted daily trajectory.

## 14. Proposed supplementary figures and tables

| Supplementary figures | Supplementary tables |
|---|---|
| All-year Erken reference/reconstruction trajectories | Complete annual metrics, existing intervals, and denominators |
| All-year Vombsjön observed-versus-withheld-predicted points from committed files | Full processor-specific eligibility, dates, support, and scenario counts |
| Separate L2A sensitivity and L1C diagnostic result panels | Native-MCI bias/MAE/RMSE, all peak errors, and ±5/±10/±15-day outcomes |
| CV double-logistic sensitivity and exploratory event recovery | Erken paired contrasts and existing omission-stability results |
| Random-deletion results and fuller activity/position/containment displays | Field pairs, unavailable reasons, spatial/depth limitations, and provenance/validation summary |
| Field-pair scatterplots without fitted regressions, plus spatial-support illustration | Frozen parameter-selection and runtime evidence |

Keep processor calendars and quantities separate in SI as in the main paper. Label event recovery as secondary/exploratory and distinguish pooled event counts from equal-year recovery estimates. Any selected illustration must be explicitly descriptive; all-year displays prevent cherry-picking. The field scatterplots should retain year/date labels and unavailable-evidence counts, without new coefficients or regression lines.

## 15. Prioritized manuscript-production actions and analysis boundary

The next production actions are:

1. Generate the primary ACOLITE block-response figure with the saved intervals and metric-specific denominators.
2. Generate the annual Vombsjön comparison, making 2018, 2020, and partial-year 2026 visible without excluding any year.
3. Prepare the compact Erken duration/activity and peak-containment figure from existing reliability tables.
4. Rewrite the two-lake Results and Discussion using the evidence hierarchy above; reconcile stale status and source-map statements only in a later authorized editing task.
5. Assemble SI and resolve the archival presentation of the untracked daily-prediction artifact before using daily curves in a reproducibility claim.

No figure generation or manuscript rewrite is performed by saving this synthesis. Priorities are recommendations, not claims that production is complete.

Under the repository's review-suggestion triage, manuscript integration, figures from saved outputs, evidence mapping, and reproducibility presentation are **Original-plan pending**. Reconciliation of the evidenced stale progress statements is a **Necessary correction** to documentation; it is not performed here and requires no reinterpretation of frozen science.

Remaining manuscript work can use the existing annual tables to display method ordering and influential values, consolidate support/availability/failure denominators, and present all-year observed-versus-withheld-predicted points. These activities preserve the current scientific design and estimators.

An additional display of existing scenario errors against actual date spans would be an **Optional enhancement**, descriptive only, without new bins, thresholds, fitted reliability models, or inference. It is not required for the minimum figure set and has not been generated or accepted as a new analysis.

New field regressions, calendar-gap models, formal Vombsjön omission analyses, or processor-common-calendar experiments must not silently enter the manuscript as existing frozen evidence. They are outside this task and are not prerequisites for writing the defensible current findings. No new performance experiment is needed to communicate the evidence already available.

## 16. Claims that should explicitly be avoided

- “Linear interpolation is universally best.”
- “The Erken method ranking transferred unchanged.”
- “ACOLITE outperformed L2A/L1C on a matched comparison.”
- “2018 has valid contemporaneous field–satellite validation.”
- “The extreme 2018 field bloom or its true peak was accurately reconstructed.”
- “Moderate correlation, low average bias, or successful fitting establishes reliable phenology.”
- “Four withheld acquisitions correspond to a fixed calendar-day gap.”
- “A universal gap-duration threshold was established.”
- “Erken and Vombsjön nRMSE values directly measure relative lake difficulty.”
- “Vombsjön peak conclusions are robust to removing influential years.”
- “Field Chl-a validates daily reconstructed MCI, onset/end, or integral accuracy.”
- “Community composition caused the observed method or proxy differences.”
- “The spline independently demonstrated denoising.”
- “All manifest-listed daily outputs are committed in Git.”
- “Thousands of overlapping scenarios constitute thousands of independent seasonal replicates.”
- “The supplementary event analysis is an independent confirmatory replacement for the primary global-peak outcome.”

The defensible closing claim remains: **the frozen two-lake evidence supports metric-specific temporal reconstruction reliability, with a strong pointwise role for simple interpolation, variable timing and shape trade-offs, and sharply limited ecological validation of Vombsjön's reconstructed daily proxy.**
