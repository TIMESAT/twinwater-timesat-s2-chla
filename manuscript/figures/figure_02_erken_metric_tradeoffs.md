# Figure 2 — Erken metric trade-offs under the actual observation mask

Figure production only; no reconstruction, normalization, metric, aggregation, confidence interval, statistical test or new cross-metric score was computed.

Source commit: `175b0b3d3291cc889274c97847e48ab42dd80006`. Script: [48_plot_erken_metric_tradeoffs.py](../../scripts/48_plot_erken_metric_tradeoffs.py).
Runtime: Python 3.12.14; Matplotlib 3.10.8.

## Manuscript-ready caption

Metric-specific behavior of primary Erken reconstruction under the actual observation mask: (a) annual nRMSE, (b) absolute common-support global-peak date error in calendar days, and (c) absolute common-support seasonal integral error. Annual estimates for 2019–2025 are copied from the frozen primary_actual_mask table. The separated rightmost Equal-year category shows the saved equal-year estimate and 95% whole-year cluster-bootstrap interval for each method, based on seven equally weighted years and 10,000 whole-year resamples. Connecting lines only aid year-to-year reading; they do not represent a fitted temporal trend and do not connect to the aggregate category. Small horizontal offsets in the summary category distinguish methods without scientific meaning.

Asterisks mark 2019 and 2025 as boundary-truncated common support, directly from calendar_coverage_status. These years remain eligible and retained in the frozen summaries. The dense-reference Erken common-support global maximum is not asserted to be the full-calendar-year ecological maximum in those years. The integral is evaluated only over the frozen common support; this is neither a Vombsjön metric nor satellite-retrieval validation. The full 2020 and 2025 peak errors are shown on a linear axis, with no clipping, transformation, broken axis or omission.

Peak-error means are strongly influenced by particular years, especially 2025; this figure does not establish universal peak-timing superiority. The corrected v1.0.1 interpretation distinguishes ties from reversals in existing supporting omission summaries, but no leave-one-year-out results are plotted here. Linear interpolation has the lowest saved equal-year nRMSE, while default double logistic has the lowest descriptive equal-year absolute integral error. These metric-specific patterns do not establish a universal method ranking. Individual interval overlap or separation is not a significance test. No direct numerical comparison to Vombsjön is made.

All three methods preserve their primary roles: linear interpolation is the untuned baseline; TIMESAT double logistic retains frozen effective defaults; and TIMESAT smoothing spline uses the saved Erken outer-fold selected setting. No CV-DL result is included.

## Validation and sources

PASS: 63 annual plotted values, 9 equal-year estimates and 18 CI endpoints exactly match committed frozen source tables, including direct Matplotlib coordinate checks. All selected rows are primary_actual_mask and use only the three primary methods, with annual coverage exactly 2019–2025. All 21 annual reconstructions have reconstruction_status=ok and peak_timing_metric_status=ok; all 63 selected annual metrics are finite. Every aggregate reports 7/7 available years and 7/7 available outcomes, zero reconstruction failures and zero metric-unavailable outcomes. The CSV preserves every source decimal string and relevant support/status fields. The 2019/2025 boundary statuses are checked explicitly; all values and intervals fit within linear axes. No result, config, protocol, freeze or source table is written by this script.

- [erken_reliability_actual_mask_year_method.csv](../../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv): SHA256 `a09cfd20d60e74bfcbb2d90f2389420c0b1f4f6d4176a40e1b252b0c72d2fe9a`; committed, local and frozen-manifest bytes agree.
- [erken_reliability_actual_mask_equal_year_summary.csv](../../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_equal_year_summary.csv): SHA256 `b390777bcd4fc746ba7294a9131537bedb5ab7afcb363618606b654f9440ea2e`; committed, local and frozen-manifest bytes agree.
- [Corrected Erken synthesis v1.0.1](../../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md): interpretation authority.
- [RSE manuscript results synthesis v1.0](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md): manuscript synthesis authority.

## Annual availability and support

Counts and statuses below are identical across the three methods for each year. Sparse-input endpoints bound the frozen common support; n_common_support_dates counts the eligible support dates rather than asserting an uninterrupted calendar interval. All displayed metrics are available; unavailable annual values and aggregate values: none.

| Year | First sparse input | Last sparse input | Sparse inputs | Pointwise evaluation dates | Common-support dates | Calendar coverage status |
|---|---|---|---:|---:|---:|---|
| 2019* | 2019-04-17 | 2019-12-05 | 35 | 198 | 233 | boundary_truncated_common_support |
| 2020 | 2020-01-19 | 2020-11-22 | 56 | 247 | 303 | complete_calendar_year_source_coverage |
| 2021 | 2021-03-19 | 2021-12-04 | 46 | 215 | 261 | complete_calendar_year_source_coverage |
| 2022 | 2022-04-18 | 2022-12-09 | 36 | 200 | 236 | complete_calendar_year_source_coverage |
| 2023 | 2023-04-21 | 2023-11-29 | 27 | 196 | 223 | complete_calendar_year_source_coverage |
| 2024 | 2024-04-17 | 2024-11-28 | 40 | 186 | 226 | complete_calendar_year_source_coverage |
| 2025* | 2025-03-21 | 2025-11-26 | 48 | 203 | 251 | boundary_truncated_common_support |

## Output SHA256

- [figure_02_erken_metric_tradeoffs.pdf](figure_02_erken_metric_tradeoffs.pdf): `be63e08aa64bae7c8ebbe33ef8e12138ce0dbf36445f5513b4da1e0ae440cdf8`
- [figure_02_erken_metric_tradeoffs.png](figure_02_erken_metric_tradeoffs.png): `41ffe1e6fac200b03c15bde9677298c6343c2884cf8b8147ffa6a3c3b925d313`
- [figure_02_erken_metric_tradeoffs.csv](figure_02_erken_metric_tradeoffs.csv): `8882f6c85512d00df7dafb6cc1dfb4601bc9bc38fa07cf5106d2871b8c2172a9`

## Exact annual plotted values

Original source decimal strings, without presentation rounding.

| Panel | Year | Frozen method | Estimate |
|---|---:|---|---:|
| a | 2019 | linear_interpolation | 0.26288729503827002 |
| a | 2019 | timesat_double_logistic | 0.27219968749762552 |
| a | 2019 | timesat_smoothing_spline | 0.26186729250703922 |
| a | 2020 | linear_interpolation | 0.1440014905395498 |
| a | 2020 | timesat_double_logistic | 0.2544808156460599 |
| a | 2020 | timesat_smoothing_spline | 0.19003406902709849 |
| a | 2021 | linear_interpolation | 0.092279945871914099 |
| a | 2021 | timesat_double_logistic | 0.21032940574689091 |
| a | 2021 | timesat_smoothing_spline | 0.13694863141055991 |
| a | 2022 | linear_interpolation | 0.2758177999996948 |
| a | 2022 | timesat_double_logistic | 0.33494913303686952 |
| a | 2022 | timesat_smoothing_spline | 0.27992976781082851 |
| a | 2023 | linear_interpolation | 0.1720799384738452 |
| a | 2023 | timesat_double_logistic | 0.17826547736930359 |
| a | 2023 | timesat_smoothing_spline | 0.1972956847045749 |
| a | 2024 | linear_interpolation | 0.2113979799410835 |
| a | 2024 | timesat_double_logistic | 0.2256556615274308 |
| a | 2024 | timesat_smoothing_spline | 0.2267324676336879 |
| a | 2025 | linear_interpolation | 0.26577856783337478 |
| a | 2025 | timesat_double_logistic | 0.27731404480319322 |
| a | 2025 | timesat_smoothing_spline | 0.26769766622592078 |
| b | 2019 | linear_interpolation | 1 |
| b | 2019 | timesat_double_logistic | 4.5 |
| b | 2019 | timesat_smoothing_spline | 9 |
| b | 2020 | linear_interpolation | 31 |
| b | 2020 | timesat_double_logistic | 151 |
| b | 2020 | timesat_smoothing_spline | 151 |
| b | 2021 | linear_interpolation | 0 |
| b | 2021 | timesat_double_logistic | 14 |
| b | 2021 | timesat_smoothing_spline | 3 |
| b | 2022 | linear_interpolation | 6 |
| b | 2022 | timesat_double_logistic | 1 |
| b | 2022 | timesat_smoothing_spline | 13 |
| b | 2023 | linear_interpolation | 0 |
| b | 2023 | timesat_double_logistic | 2 |
| b | 2023 | timesat_smoothing_spline | 1 |
| b | 2024 | linear_interpolation | 4 |
| b | 2024 | timesat_double_logistic | 1 |
| b | 2024 | timesat_smoothing_spline | 3 |
| b | 2025 | linear_interpolation | 200 |
| b | 2025 | timesat_double_logistic | 207 |
| b | 2025 | timesat_smoothing_spline | 202 |
| c | 2019 | linear_interpolation | 379.29943400000002 |
| c | 2019 | timesat_double_logistic | 544.4316727329483 |
| c | 2019 | timesat_smoothing_spline | 363.45422468674087 |
| c | 2020 | linear_interpolation | 110.75313074999964 |
| c | 2020 | timesat_double_logistic | 6.2204850313642055 |
| c | 2020 | timesat_smoothing_spline | 132.23792701935554 |
| c | 2021 | linear_interpolation | 86.268280000000004 |
| c | 2021 | timesat_double_logistic | 131.33297694917292 |
| c | 2021 | timesat_smoothing_spline | 135.82623523171517 |
| c | 2022 | linear_interpolation | 159.94292500000029 |
| c | 2022 | timesat_double_logistic | 54.795726626892247 |
| c | 2022 | timesat_smoothing_spline | 177.40676447727219 |
| c | 2023 | linear_interpolation | 102.4164679999999 |
| c | 2023 | timesat_double_logistic | 71.451679160701588 |
| c | 2023 | timesat_smoothing_spline | 147.21321584831412 |
| c | 2024 | linear_interpolation | 30.246232999999847 |
| c | 2024 | timesat_double_logistic | 55.851695520046178 |
| c | 2024 | timesat_smoothing_spline | 95.509797011676241 |
| c | 2025 | linear_interpolation | 233.29240400000023 |
| c | 2025 | timesat_double_logistic | 17.634128755241363 |
| c | 2025 | timesat_smoothing_spline | 257.87106221327213 |

## Exact equal-year summaries and intervals

All rows have 7/7 available years and 7/7 available outcomes; zero unavailable outcomes.

| Panel | Frozen method | Estimate | Lower 95% | Upper 95% |
|---|---|---:|---:|---:|
| a | linear_interpolation | 0.20346328824253318 | 0.15423000640126977 | 0.24994963452897953 |
| a | timesat_double_logistic | 0.25045631794676765 | 0.21611260832949394 | 0.285794013880103 |
| a | timesat_smoothing_spline | 0.22292936847424422 | 0.18616606387343279 | 0.25668448864710969 |
| b | linear_interpolation | 34.571428571428569 | 1.5714285714285714 | 91.142857142857139 |
| b | timesat_double_logistic | 54.357142857142854 | 3.2857142857142856 | 118.71428571428571 |
| b | timesat_smoothing_spline | 54.571428571428569 | 4.4285714285714288 | 117.85714285714286 |
| c | linear_interpolation | 157.45983924999999 | 86.591649964285651 | 245.83363900000015 |
| c | timesat_double_logistic | 125.95976639662383 | 34.293694751546248 | 271.77796890112029 |
| c | timesat_smoothing_spline | 187.0741752126209 | 131.53749436880071 | 256.75613874488533 |
