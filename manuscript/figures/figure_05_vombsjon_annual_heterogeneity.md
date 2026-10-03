# Figure 5 — Vombsjön annual heterogeneity

Figure production only; no reconstruction, metric, normalization, aggregation, correlation, confidence interval or statistical test was recomputed.

Source commit: `3743320302f5423ec3ad32a3562161dab579d58a`. Script: [46_plot_vombsjon_annual_heterogeneity.py](../../scripts/46_plot_vombsjon_annual_heterogeneity.py).
Runtime: Python 3.12.14; Matplotlib 3.10.8.

## Manuscript caption

Annual heterogeneity of locked ACOLITE MCI reconstruction under withholding of four consecutive observed acquisitions: (a) annual nRMSE, (b) withheld-date trajectory Pearson r, and (c) mean absolute observed-proxy peak timing error in calendar days. All points are the stored annual estimates for the three primary methods; no new uncertainty intervals are added. Thin lines are visual connections between annual estimates, not continuous temporal trajectories. All eligible years from 2017 through 2026 are retained, including 2018 and 2020. The asterisk marks partial observed ACOLITE support in 2026, from 10 January to 3 August, rather than a complete annual season. Four acquisitions do not represent a fixed four-day gap.

Peak timing refers to the maximum of the available QC-passed observed MCI series within annual support, not the true ecological bloom peak. This is satellite-MCI reconstruction evidence, not field validation; it does not imply contemporaneous field–satellite validation in 2018. Default TIMESAT double logistic retains p_seapar=1 and the smoothing spline retains the Erken-selected p_smooth=10. nRMSE and absolute peak error are saved within-year scenario means; correlation uses the saved within-year median-collapsed withheld-date predictions. Annual peak-error availability and support are reported below; unavailable values, if present, remain missing without imputation or connecting across them.

## Validation and sources

PASS: 90 plotted estimates exactly match committed annual-summary values, checked also against Matplotlib coordinates. All 90 expected records are retained. Unavailable annual values: 0. CSV preserves every selected source decimal string and denominator. Source bytes match both Git and the frozen manifest. Only ACOLITE, consecutive four-acquisition withholding and the three frozen primary methods are selected. Annual scenario totals agree with eligibility; all ten years are eligible. The 2026 support endpoints are explicitly checked. No source table, scientific result, configuration, freeze or execution specification is written by this script.

- [vombsjon_transfer_year_summary.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_summary.csv): SHA256 `c7d742df66238b046b6adc87b53f4cae578f6ab21e38437f32298948f06084b4`.
- [vombsjon_transfer_year_eligibility.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv): SHA256 `e0ccbb80786e3c9cc35f72d3e6fcb377e1f226b84c4addbab119dcda49ff01ba`.

## Annual availability and support

Dates are observed annual support, not assertions of full-year coverage. Scenario counts are per method; overlapping windows remain nested within years. Peak counts below are available annual peak-error scenarios for each of the three methods, in legend order.

| Year | Support start | Support end | Eligible dates | Four-acquisition scenarios | Available peak-error scenarios (linear / default DL / spline) |
|---|---|---|---:|---:|---|
| 2017 | 2017-01-27 | 2017-12-21 | 34 | 29 | 4 / 4 / 4 |
| 2018 | 2018-01-07 | 2018-11-28 | 45 | 40 | 4 / 4 / 4 |
| 2019 | 2019-01-02 | 2019-12-31 | 33 | 28 | 4 / 4 / 4 |
| 2020 | 2020-01-22 | 2020-12-25 | 28 | 23 | 4 / 4 / 4 |
| 2021 | 2021-01-09 | 2021-12-25 | 34 | 29 | 4 / 4 / 4 |
| 2022 | 2022-01-06 | 2022-11-20 | 31 | 26 | 4 / 4 / 4 |
| 2023 | 2023-02-08 | 2023-12-27 | 33 | 28 | 4 / 4 / 4 |
| 2024 | 2024-01-11 | 2024-12-01 | 27 | 22 | 4 / 4 / 4 |
| 2025 | 2025-01-15 | 2025-12-23 | 42 | 37 | 4 / 4 / 4 |
| 2026* | 2026-01-10 | 2026-08-03 | 28 | 23 | 4 / 4 / 4 |

*2026 is partial observed support ending on 3 August. Unavailable annual values: none.

## Output SHA256

- [figure_05_vombsjon_annual_heterogeneity.pdf](figure_05_vombsjon_annual_heterogeneity.pdf): `19a8f9b6a3f5dc7d52e29b41c3ad3dc3c3cc7a4780329014fd37ec5bd2b5bf72`
- [figure_05_vombsjon_annual_heterogeneity.png](figure_05_vombsjon_annual_heterogeneity.png): `59d17e18759496a5fbefe13341f258a119ed134fa5d3b076cae5a097a6f7158d`
- [figure_05_vombsjon_annual_heterogeneity.csv](figure_05_vombsjon_annual_heterogeneity.csv): `eb3f13480656170f80e7401bb91ca07b48aaa4379fc468798c723eedf9507036`

## Exact plotted values

Original frozen decimal strings, with no presentation rounding. All rows use ACOLITE and four-consecutive-observed-acquisition withholding.

| Panel | Year | Frozen method | Estimate | Available scenarios |
|---|---:|---|---:|---:|
| a | 2017 | linear_interpolation | 0.2838622447537784 | 29 |
| a | 2017 | timesat_double_logistic | 0.28654162368469954 | 29 |
| a | 2017 | timesat_smoothing_spline | 0.36445649986333667 | 29 |
| a | 2018 | linear_interpolation | 0.1846368830459372 | 40 |
| a | 2018 | timesat_double_logistic | 0.1707136691192527 | 40 |
| a | 2018 | timesat_smoothing_spline | 0.2208486775141051 | 40 |
| a | 2019 | linear_interpolation | 0.3093803168392601 | 28 |
| a | 2019 | timesat_double_logistic | 0.3713620473287454 | 28 |
| a | 2019 | timesat_smoothing_spline | 0.41366317500929156 | 28 |
| a | 2020 | linear_interpolation | 0.2761936636875665 | 23 |
| a | 2020 | timesat_double_logistic | 0.22496455366107937 | 23 |
| a | 2020 | timesat_smoothing_spline | 0.39744516629826526 | 23 |
| a | 2021 | linear_interpolation | 0.1665215005578187 | 29 |
| a | 2021 | timesat_double_logistic | 0.19857106165228758 | 29 |
| a | 2021 | timesat_smoothing_spline | 0.24997612664601276 | 29 |
| a | 2022 | linear_interpolation | 0.26083262847743865 | 26 |
| a | 2022 | timesat_double_logistic | 0.26290650822135214 | 26 |
| a | 2022 | timesat_smoothing_spline | 0.35555697368364064 | 26 |
| a | 2023 | linear_interpolation | 0.19479205612671466 | 28 |
| a | 2023 | timesat_double_logistic | 0.21999095007794703 | 28 |
| a | 2023 | timesat_smoothing_spline | 0.27510627943188126 | 28 |
| a | 2024 | linear_interpolation | 0.1921044998128316 | 22 |
| a | 2024 | timesat_double_logistic | 0.22793499703478923 | 22 |
| a | 2024 | timesat_smoothing_spline | 0.2197712386671649 | 22 |
| a | 2025 | linear_interpolation | 0.3044022474097595 | 37 |
| a | 2025 | timesat_double_logistic | 0.31477303430190684 | 37 |
| a | 2025 | timesat_smoothing_spline | 0.411314767126861 | 37 |
| a | 2026 | linear_interpolation | 0.3669711973469344 | 23 |
| a | 2026 | timesat_double_logistic | 0.43341703928112474 | 23 |
| a | 2026 | timesat_smoothing_spline | 0.4206137571572687 | 23 |
| b | 2017 | linear_interpolation | 0.6547805064010015 | 29 |
| b | 2017 | timesat_double_logistic | 0.6524906856296246 | 29 |
| b | 2017 | timesat_smoothing_spline | 0.6156784272024676 | 29 |
| b | 2018 | linear_interpolation | 0.8486634355342756 | 40 |
| b | 2018 | timesat_double_logistic | 0.8382951774953553 | 40 |
| b | 2018 | timesat_smoothing_spline | 0.8649217385283782 | 40 |
| b | 2019 | linear_interpolation | 0.6597966606619148 | 28 |
| b | 2019 | timesat_double_logistic | 0.56851218743277 | 28 |
| b | 2019 | timesat_smoothing_spline | 0.6888978697231231 | 28 |
| b | 2020 | linear_interpolation | 0.690541536027114 | 23 |
| b | 2020 | timesat_double_logistic | 0.734554165214946 | 23 |
| b | 2020 | timesat_smoothing_spline | 0.5807580301393817 | 23 |
| b | 2021 | linear_interpolation | 0.9111146411886216 | 29 |
| b | 2021 | timesat_double_logistic | 0.8412086029398594 | 29 |
| b | 2021 | timesat_smoothing_spline | 0.890550508114552 | 29 |
| b | 2022 | linear_interpolation | 0.6506764618614544 | 26 |
| b | 2022 | timesat_double_logistic | 0.6267157408746774 | 26 |
| b | 2022 | timesat_smoothing_spline | 0.536472393241127 | 26 |
| b | 2023 | linear_interpolation | 0.8075352158491137 | 28 |
| b | 2023 | timesat_double_logistic | 0.7613601047013305 | 28 |
| b | 2023 | timesat_smoothing_spline | 0.7006031428091245 | 28 |
| b | 2024 | linear_interpolation | 0.8603312043676982 | 22 |
| b | 2024 | timesat_double_logistic | 0.7908746481223545 | 22 |
| b | 2024 | timesat_smoothing_spline | 0.8744529558817995 | 22 |
| b | 2025 | linear_interpolation | 0.6722389395842928 | 37 |
| b | 2025 | timesat_double_logistic | 0.6374822503802279 | 37 |
| b | 2025 | timesat_smoothing_spline | 0.640661282990224 | 37 |
| b | 2026 | linear_interpolation | 0.3825395597447281 | 23 |
| b | 2026 | timesat_double_logistic | 0.17393011782349468 | 23 |
| b | 2026 | timesat_smoothing_spline | 0.5518470151617585 | 23 |
| c | 2017 | linear_interpolation | 37.25 | 4 |
| c | 2017 | timesat_double_logistic | 53.25 | 4 |
| c | 2017 | timesat_smoothing_spline | 118.5 | 4 |
| c | 2018 | linear_interpolation | 26.75 | 4 |
| c | 2018 | timesat_double_logistic | 21.25 | 4 |
| c | 2018 | timesat_smoothing_spline | 42.375 | 4 |
| c | 2019 | linear_interpolation | 20.0 | 4 |
| c | 2019 | timesat_double_logistic | 32.75 | 4 |
| c | 2019 | timesat_smoothing_spline | 29.75 | 4 |
| c | 2020 | linear_interpolation | 42.0 | 4 |
| c | 2020 | timesat_double_logistic | 5.25 | 4 |
| c | 2020 | timesat_smoothing_spline | 48.25 | 4 |
| c | 2021 | linear_interpolation | 16.0 | 4 |
| c | 2021 | timesat_double_logistic | 5.0 | 4 |
| c | 2021 | timesat_smoothing_spline | 13.125 | 4 |
| c | 2022 | linear_interpolation | 13.5 | 4 |
| c | 2022 | timesat_double_logistic | 8.75 | 4 |
| c | 2022 | timesat_smoothing_spline | 9.0 | 4 |
| c | 2023 | linear_interpolation | 17.5 | 4 |
| c | 2023 | timesat_double_logistic | 16.75 | 4 |
| c | 2023 | timesat_smoothing_spline | 21.375 | 4 |
| c | 2024 | linear_interpolation | 24.0 | 4 |
| c | 2024 | timesat_double_logistic | 8.25 | 4 |
| c | 2024 | timesat_smoothing_spline | 14.25 | 4 |
| c | 2025 | linear_interpolation | 17.0 | 4 |
| c | 2025 | timesat_double_logistic | 15.75 | 4 |
| c | 2025 | timesat_smoothing_spline | 20.75 | 4 |
| c | 2026 | linear_interpolation | 95.0 | 4 |
| c | 2026 | timesat_double_logistic | 106.75 | 4 |
| c | 2026 | timesat_smoothing_spline | 98.0 | 4 |
