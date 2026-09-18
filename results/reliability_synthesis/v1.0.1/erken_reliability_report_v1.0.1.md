# Erken reliability synthesis v1.0.1 — interpretive correction

**Correction status:** v1.0 numerical tables, figures, manifest and all frozen analysis outputs are unchanged. This version corrects interpretation only: leave-one-year-out ties are separated from reversals, the spline is described as producing a smoother curve rather than independently verified denoising, and `A_gap` is identified as an Erken-only retrospective explanatory variable. Statements that the synthesis itself did not execute the second freeze are retained as the scope of that saved-result analysis; the completed freeze is governed separately by `docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md`.

**Analysis date:** 2026-09-18  
**Starting commit:** `53d29783da2dc2899aa9012c40a3744718e2fd84`  
**Scope:** saved Erken outputs only; no reconstruction or satellite extraction rerun; no Vombsjön data or performance inspected; no second freeze executed.

## 简明中文结论

1. 在实际 Sentinel-2 采样掩膜下，点位误差以年为单位等权汇总后为：线性插值 0.203 (95% year-cluster bootstrap CI 0.154 to 0.250)；默认双逻辑 0.250 (95% year-cluster bootstrap CI 0.216 to 0.286)；平滑样条 0.223 (95% year-cluster bootstrap CI 0.186 to 0.257)。线性插值 nRMSE 对默认双逻辑在 7/7 年较低、对平滑样条在 6/7 年较低；这是点位误差上的稳定优势，但不等于它每个科学指标都最好。来源：`erken_reliability_actual_mask_equal_year_summary.csv` 与 `erken_reliability_actual_mask_paired_summary.csv`。
2. 全局峰值日期 <=10 天的年份等权达标率为：线性插值 0.714 (95% year-cluster bootstrap CI 0.429 to 1.000)；默认双逻辑 0.571 (95% year-cluster bootstrap CI 0.143 to 0.857)；平滑样条 0.571 (95% year-cluster bootstrap CI 0.143 to 0.857)。峰值日期与峰值幅度分开统计；多事件年份中全局最大值身份切换会造成很大的日期误差。来源：`erken_reliability_actual_mask_year_method.csv` 与 `erken_reliability_actual_mask_equal_year_summary.csv`。
3. 共同支持区间的绝对积分误差为：线性插值 157.5 (95% year-cluster bootstrap CI 86.6 to 245.8)；默认双逻辑 126.0 (95% year-cluster bootstrap CI 34.3 to 271.8)；平滑样条 187.1 (95% year-cluster bootstrap CI 131.5 to 256.8) ug day L^-1。默认双逻辑在积分上平均最好，却在 nRMSE、相关性和事件恢复上较弱；积分准确不能替代短期事件恢复充分。来源：`erken_reliability_actual_mask_equal_year_summary.csv`。
4. 18 个主要事件的恢复结果仍是后验冻结的次要/探索性分析，不能替代主分析的全局峰值指标。来源：`erken_reliability_event_year_method.csv` 与 `erken_reliability_event_equal_year_summary.csv`。
5. 随机删除与连续缺口都没有产生重建失败，但可靠性随缺测增强而总体下降，并受年份、方法、A_gap、峰值是否落在缺口内和实际移除观测数共同影响；不存在由这 7 个年份支持的通用缺口阈值。A_gap 由 Erken 完整参考序列事后计算，只是解释与分层变量，不能作为 Vomb 隐藏缺口内已知的运行输入。
6. 逐次剔除一年后，线性插值相对默认双逻辑或平滑样条的峰值日期优势在部分情况下变为持平，但没有反转；平滑样条与默认双逻辑之间则同时出现正负差异，说明两者的峰值日期优势会随被剔除年份改变。报告因此同时给出平均优势、逐年胜负与 leave-one-year-out 范围，不能把平均较低误差写成每年均优。
7. 所有主结果来自 7 个 Erken 年份。bootstrap 以整年为 cluster，区间只能反映这 7 年内部的年际不确定性，不能外推为通用湖泊可靠性界限。

## Analysis identity and statistical method

All scenario metrics were first averaged within year and stratum; years then received equal weight. Uncertainty used 10,000 whole-year bootstrap resamples with master seed `20260918` and two-sided percentile intervals at 95%. A SHA256-derived sub-seed was used per estimand. Resampling the year-level vector is algebraically equivalent to resampling complete year blocks after the prescribed within-year reduction, and therefore preserves all method and scenario pairing inside a year.

Continuous metrics were not imputed when unavailable. Eligible peak-timing failures or missing reconstructed peaks would count as non-success, while reference-ineligible cases would be excluded and reported. In the saved inputs used here, every primary actual-mask, random-deletion and consecutive-gap reconstruction and every requested primary metric was available. The denominator audit nevertheless records every denominator explicitly.

## Primary actual-mask comparison

### Metric-specific strengths and limitations

- Linear interpolation had the lowest mean nRMSE (0.203 (95% year-cluster bootstrap CI 0.154 to 0.250)), the highest mean trajectory correlation (0.864 (95% year-cluster bootstrap CI 0.817 to 0.911)), and the lowest normalized peak-magnitude error (0.797 (95% year-cluster bootstrap CI 0.233 to 1.439)). It had lower nRMSE than default double logistic in 7/7 years and than the smoothing spline in 6/7 years. Its limitation is that local responsiveness does not guarantee correct annual-maximum identity or the lowest cumulative integral error.
- The smoothing spline was intermediate in mean nRMSE (0.223 (95% year-cluster bootstrap CI 0.186 to 0.257)) and correlation (0.830 (95% year-cluster bootstrap CI 0.800 to 0.863)). It produced smoother reconstructed curves with more flexibility than the default double logistic, but still attenuated or reordered peaks and had the largest mean absolute integral error (187.1 (95% year-cluster bootstrap CI 131.5 to 256.8) ug day L^-1).
- Default double logistic had the smallest descriptive mean absolute integral error (126.0 (95% year-cluster bootstrap CI 34.3 to 271.8) ug day L^-1), outperforming linear interpolation on this metric in 4/7 years and the smoothing spline in 6/7 years. However, its mean nRMSE (0.250 (95% year-cluster bootstrap CI 0.216 to 0.286)), correlation (0.742 (95% year-cluster bootstrap CI 0.693 to 0.795)), and normalized peak-magnitude error (1.304 (95% year-cluster bootstrap CI 0.774 to 1.851)) were least favorable. Pairwise bootstrap intervals for integral advantages included zero against linear interpolation and the spline, so the lower descriptive mean is not a universal or formal superiority claim.

### Cross-year stability and typical difficult years

- Linear interpolation: two largest peak-date errors occurred in 2025 (200.0 d), 2020 (31.0 d); nRMSE was highest in 2022 (0.276).
- TIMESAT double logistic (default): two largest peak-date errors occurred in 2025 (207.0 d), 2020 (151.0 d); nRMSE was highest in 2022 (0.335).
- TIMESAT smoothing spline: two largest peak-date errors occurred in 2025 (202.0 d), 2020 (151.0 d); nRMSE was highest in 2022 (0.280).

A lower equal-year mean is not evidence of year-by-year dominance. Paired year differences and their bootstrap intervals are in `erken_reliability_actual_mask_paired_summary.csv`; the complete year-level contrasts are in `erken_reliability_actual_mask_paired_year_differences.csv`.

### Leave-one-year-out re-summaries

- Linear interpolation vs TIMESAT double logistic (default), `nrmse`: full advantage for method A 0.047; leave-one-year-out range 0.035 to 0.054; direction kept.
- Linear interpolation vs TIMESAT double logistic (default), `absolute_integral_error`: full advantage for method A -31.500; leave-one-year-out range -64.272 to -0.807; direction kept.
- Linear interpolation vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; some leave-one-year-out summaries tied, and none reversed the linear-interpolation advantage.
- Linear interpolation vs TIMESAT smoothing spline, `nrmse`: full advantage for method A 0.019; leave-one-year-out range 0.015 to 0.023; direction kept.
- Linear interpolation vs TIMESAT smoothing spline, `absolute_integral_error`: full advantage for method A 29.614; leave-one-year-out range 23.673 to 37.191; direction kept.
- Linear interpolation vs TIMESAT smoothing spline, `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; some leave-one-year-out summaries tied, and none reversed the linear-interpolation advantage.
- TIMESAT smoothing spline vs TIMESAT double logistic (default), `nrmse`: full advantage for method A 0.028; leave-one-year-out range 0.020 to 0.035; direction kept.
- TIMESAT smoothing spline vs TIMESAT double logistic (default), `absolute_integral_error`: full advantage for method A -61.114; leave-one-year-out range -101.463 to -31.261; direction kept.
- TIMESAT smoothing spline vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.000; leave-one-year-out range -0.167 to 0.167; the contrast took both signs, so the two methods alternated in advantage across leave-one-year-out summaries.

These are re-summaries only: no method was refit and no parameter was retuned. Full results are in `erken_reliability_actual_mask_leave_one_year_out*.csv`.

### Supplementary event recovery

- Linear interpolation: equal-year event recovery <=10 d 0.952 (95% year-cluster bootstrap CI 0.857 to 1.000); pooled descriptive <=10 d count 17/18; pooled descriptive count 18 matched, 0 missed, 0 unavailable among 18 reference-event rows.
- TIMESAT double logistic (default): equal-year event recovery <=10 d 0.333 (95% year-cluster bootstrap CI 0.167 to 0.476); pooled descriptive <=10 d count 5/18; pooled descriptive count 8 matched, 10 missed, 0 unavailable among 18 reference-event rows.
- TIMESAT smoothing spline: equal-year event recovery <=10 d 0.833 (95% year-cluster bootstrap CI 0.690 to 0.952); pooled descriptive <=10 d count 15/18; pooled descriptive count 15 matched, 3 missed, 0 unavailable among 18 reference-event rows.

## Missingness response

### Random deletion

- Linear interpolation: nRMSE 0.209 (95% year-cluster bootstrap CI 0.162 to 0.252) at 10% deletion and 0.247 (95% year-cluster bootstrap CI 0.220 to 0.273) at 50%; 50% deletion peak-date <=10 d rate 0.579 (95% year-cluster bootstrap CI 0.317 to 0.811). Coverage at 50% spanned density 0.063-0.100 and maximum internal gap 20-117 d.
- TIMESAT double logistic (default): nRMSE 0.253 (95% year-cluster bootstrap CI 0.221 to 0.288) at 10% deletion and 0.288 (95% year-cluster bootstrap CI 0.267 to 0.312) at 50%; 50% deletion peak-date <=10 d rate 0.566 (95% year-cluster bootstrap CI 0.270 to 0.836). Coverage at 50% spanned density 0.063-0.100 and maximum internal gap 20-117 d.
- TIMESAT smoothing spline: nRMSE 0.228 (95% year-cluster bootstrap CI 0.192 to 0.259) at 10% deletion and 0.275 (95% year-cluster bootstrap CI 0.244 to 0.306) at 50%; 50% deletion peak-date <=10 d rate 0.581 (95% year-cluster bootstrap CI 0.329 to 0.803). Coverage at 50% spanned density 0.063-0.100 and maximum internal gap 20-117 d.

Deletion-fraction curves are confirmatory controlled-gap summaries. Additional tertile displays for remaining density and realized maximum internal gap are explicitly labelled `exploratory_post_hoc_visual_stratification`; they do not redefine the frozen primary analysis. See `erken_reliability_random_covariate_strata_summary.csv` and the continuous within-year associations.

- Linear interpolation: equal-year mean within-year Spearman nRMSE association was -0.327 (-0.570 to -0.062) with remaining density and 0.261 (0.026 to 0.472) with realized maximum internal gap; all 7 years contributed.
- TIMESAT double logistic (default): equal-year mean within-year Spearman nRMSE association was -0.420 (-0.508 to -0.328) with remaining density and 0.350 (0.253 to 0.450) with realized maximum internal gap; all 7 years contributed.
- TIMESAT smoothing spline: equal-year mean within-year Spearman nRMSE association was -0.285 (-0.521 to -0.042) with remaining density and 0.262 (0.043 to 0.464) with realized maximum internal gap; all 7 years contributed.

### Consecutive internal gaps

- Linear interpolation: nRMSE 0.208 (95% year-cluster bootstrap CI 0.161 to 0.250) for 10-d windows and 0.238 (95% year-cluster bootstrap CI 0.198 to 0.277) for 45-d windows; 45-d peak-date <=10 d rate 0.610 (95% year-cluster bootstrap CI 0.323 to 0.878). Within 45-d windows, low-activity nRMSE was 0.216 (95% year-cluster bootstrap CI 0.170 to 0.256) and high-activity nRMSE was 0.273 (95% year-cluster bootstrap CI 0.236 to 0.314).
- TIMESAT double logistic (default): nRMSE 0.253 (95% year-cluster bootstrap CI 0.219 to 0.288) for 10-d windows and 0.289 (95% year-cluster bootstrap CI 0.263 to 0.318) for 45-d windows; 45-d peak-date <=10 d rate 0.482 (95% year-cluster bootstrap CI 0.171 to 0.744). Within 45-d windows, low-activity nRMSE was 0.274 (95% year-cluster bootstrap CI 0.250 to 0.303) and high-activity nRMSE was 0.317 (95% year-cluster bootstrap CI 0.286 to 0.350).
- TIMESAT smoothing spline: nRMSE 0.227 (95% year-cluster bootstrap CI 0.193 to 0.259) for 10-d windows and 0.280 (95% year-cluster bootstrap CI 0.243 to 0.315) for 45-d windows; 45-d peak-date <=10 d rate 0.547 (95% year-cluster bootstrap CI 0.249 to 0.822). Within 45-d windows, low-activity nRMSE was 0.246 (95% year-cluster bootstrap CI 0.210 to 0.277) and high-activity nRMSE was 0.316 (95% year-cluster bootstrap CI 0.280 to 0.357).

A_gap remains continuous in the primary association table. It is calculated retrospectively from the complete Erken reference trajectory and is not a known operational input inside a hidden Vomb gap. Low/medium/high labels are used only for visualization and were formed from tertiles inside each frozen duration, as required by the contract. Relative midpoint position and observations removed are retained continuously in `erken_reliability_consecutive_continuous_associations*.csv`; exact observations-removed strata are in `erken_reliability_consecutive_observations_removed_summary.csv`.

- Linear interpolation (45-d windows): equal-year mean within-year Spearman nRMSE association was 0.532 with A_gap, -0.017 with relative midpoint position, and 0.047 with observations removed; 7 years contributed to each nRMSE association.
- TIMESAT double logistic (default) (45-d windows): equal-year mean within-year Spearman nRMSE association was 0.416 with A_gap, 0.020 with relative midpoint position, and 0.076 with observations removed; 7 years contributed to each nRMSE association.
- TIMESAT smoothing spline (45-d windows): equal-year mean within-year Spearman nRMSE association was 0.464 with A_gap, 0.052 with relative midpoint position, and 0.071 with observations removed; 7 years contributed to each nRMSE association.

### Peak containment

- Linear interpolation: 45-d windows not containing/containing the reference global peak had <=10 d rates 0.704 (95% year-cluster bootstrap CI 0.414 to 0.990) / 0.252 (95% year-cluster bootstrap CI 0.067 to 0.524); the peak-containing stratum included 7 years and 245 scenario-method rows.
- TIMESAT double logistic (default): 45-d windows not containing/containing the reference global peak had <=10 d rates 0.517 (95% year-cluster bootstrap CI 0.164 to 0.774) / 0.387 (95% year-cluster bootstrap CI 0.149 to 0.648); the peak-containing stratum included 7 years and 245 scenario-method rows.
- TIMESAT smoothing spline: 45-d windows not containing/containing the reference global peak had <=10 d rates 0.563 (95% year-cluster bootstrap CI 0.214 to 0.847) / 0.445 (95% year-cluster bootstrap CI 0.204 to 0.703); the peak-containing stratum included 7 years and 245 scenario-method rows.

Sparse peak-containing strata have wide, discrete seven-year bootstrap intervals. They are evidence about the observed Erken scenarios, not universal operational thresholds.

## Double-logistic CV sensitivity (separate from the primary comparison)

The training-only CV sensitivity changed actual-mask nRMSE from 0.250 (95% year-cluster bootstrap CI 0.215 to 0.286) under the frozen default to 0.239 (95% year-cluster bootstrap CI 0.207 to 0.273). Absolute common-support integral error changed from 126.0 (95% year-cluster bootstrap CI 34.4 to 271.2) to 139.5 (95% year-cluster bootstrap CI 68.2 to 250.3) ug day L^-1. This remains a secondary sensitivity and does not replace the default double-logistic primary result. Controlled-gap sensitivity summaries are in `erken_reliability_double_logistic_cv_controlled_summary.csv`.

## Failures, missingness and support limits

Across the primary tables audited here, the summed method-family failure count was 0 and the summed metric-unavailable count was 0. These zero counts are empirical outcomes, not proof that a successful curve is scientifically reliable. The complete audit is `erken_reliability_denominator_audit.csv`.

The 2019 and 2025 records are boundary-truncated. They remain eligible only for frozen common-support metrics; neither their common-support maximum nor integral is claimed to represent the full calendar year. Controlled-gap coverage ranges and contributing-year counts appear on every long-format summary row.

## Implications for the future second freeze

This synthesis provides evidence for, but does not execute, the second Erken-only freeze. The freeze decision still needs to record: (i) whether the workflow prioritizes point-wise/trajectory fidelity, global-peak timing, cumulative integral, or an explicit hierarchy among them; (ii) whether the primary transfer workflow carries the frozen default double logistic only or also a clearly labelled CV sensitivity; (iii) how reconstructed values will be represented at unsupported or high-activity gaps; and (iv) the exact transfer manifest, quality rules and reporting language. No setting should be chosen from a single pooled metric.

## English Results draft

Under the actual Sentinel-2 sampling mask, equal-year mean nRMSE was 0.203 (95% year-cluster bootstrap CI 0.154 to 0.250) for linear interpolation, 0.223 (95% year-cluster bootstrap CI 0.186 to 0.257) for the smoothing spline, and 0.250 (95% year-cluster bootstrap CI 0.216 to 0.286) for the default double-logistic reconstruction. The corresponding mean trajectory correlations were 0.864 (95% year-cluster bootstrap CI 0.817 to 0.911), 0.830 (95% year-cluster bootstrap CI 0.800 to 0.863), and 0.742 (95% year-cluster bootstrap CI 0.693 to 0.795). Rankings differed by outcome: the default double logistic had the smallest equal-year absolute common-support integral error (126.0 (95% year-cluster bootstrap CI 34.3 to 271.8) ug day L^-1), whereas linear interpolation and the smoothing spline had errors of 157.5 (95% year-cluster bootstrap CI 86.6 to 245.8) and 187.1 (95% year-cluster bootstrap CI 131.5 to 256.8) ug day L^-1, respectively. Global-peak timing success within 10 d was 0.714 (95% year-cluster bootstrap CI 0.429 to 1.000), 0.571 (95% year-cluster bootstrap CI 0.143 to 0.857), and 0.571 (95% year-cluster bootstrap CI 0.143 to 0.857). Thus, point-wise fidelity, peak timing, peak magnitude, trajectory agreement, and seasonal integral did not identify a uniformly best method.

Additional missingness degraded reliability without defining a universal gap-duration threshold. Random-deletion and consecutive-gap responses were summarized within each year before years were equally weighted. For consecutive windows, higher A_gap strata generally had larger nRMSE than lower-activity windows of the same duration, while windows containing the reference global peak showed lower peak-timing success. Remaining observation density, realized maximum internal gap, relative gap position, and the number of removed observations showed method- and year-dependent associations. All primary reconstructions completed, but completion alone did not imply reliable seasonal metrics.

## English Discussion draft

The Erken results support a metric-specific interpretation of temporal reconstruction. Linear interpolation was most responsive to observed local variation and had the lowest average point-wise error, but its advantage was not universal across years or outcomes. The default double-logistic representation better preserved the common-support integral on average while more often altering the identity, timing, or magnitude of the dominant seasonal peak. The smoothing spline occupied an intermediate position for several outcomes but could still attenuate or reorder peaks. These contrasts separate four claims that are often conflated: a low average error does not imply year-by-year superiority; an accurate peak date does not ensure accurate peak magnitude; an accurate integral does not demonstrate short-event recovery; and a numerically complete reconstructed curve is not evidence that its scientific metrics are reliable.

The controlled experiments further show why gap length is insufficient as an operational rule. Reliability depended on realized observation density and maximum internal gap for scattered deletion, and on duration, relative position, global-peak containment, removed-observation count, and hidden reference activity for consecutive gaps. The last quantity is available retrospectively in Erken and cannot be assumed known inside an operational Vomb gap. Because only seven Erken years contribute independent clusters, the intervals are necessarily coarse and cannot justify a general lake-wide threshold. The future transfer freeze should therefore encode a metric-priority hierarchy and uncertainty-reporting rule rather than designate one universally superior reconstruction method.

## Reproduction

```bash
python scripts/33_erken_reliability_synthesis.py
pytest -q
python scripts/34_validate_erken_reliability_synthesis.py
```

The v1.0 synthesis script reads only the eight allowlisted saved Erken result files recorded in `config/erken_reliability_synthesis_v1.0.json`. Reproduce the v1.0.1 interpretive correction and its checksum manifest with `python scripts/35_prepare_erken_transfer_freeze.py` after the synthetic TIMESAT runtime validation has been materialized.
