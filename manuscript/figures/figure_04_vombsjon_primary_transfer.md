# Figure 4 — Primary Vombsjön locked transfer

Production figure only; no reconstruction, performance metric, aggregation, correlation, confidence interval, or statistical test was computed.

Source commit: `3813285f56294b4c52c64733b47bd3c06cb0135e`. Script: [45_plot_vombsjon_primary_transfer.py](../../scripts/45_plot_vombsjon_primary_transfer.py).
Runtime: Python 3.12.14; Matplotlib 3.10.8.

## Caption

ACOLITE MCI locked transfer: (a) equal-year nRMSE, (b) equal-year withheld-date trajectory Pearson correlation, and (c) equal-year proportion of reference-eligible scenarios with reconstructed observed-proxy peak within ±10 calendar days. Points and intervals are copied from the frozen summary; intervals are the saved 95% percentile intervals from 10,000 whole-year bootstrap draws. All plotted metrics have 10/10 available years (2017–2026); 2026 has partial observed support. Horizontal offsets separate methods within each design and have no numerical meaning. Two, three and four refer to consecutive observed acquisitions withheld, not calendar-day gap lengths.

Pointwise scenario counts per method are 315/305/295/285. Peak reference-eligible counts per method are only 10/20/30/40; overlapping scenarios remain nested within years. Peak success uses all reference-eligible scenarios, with unavailable reconstruction peaks or failed fits counted as non-success under the frozen rule. The peak reference is the maximum of the available QC-passed observed MCI series, not the true ecological bloom maximum. Default double logistic retains p_seapar=1; the transferred spline retains the Erken-selected p_smooth=10. Correlation is the saved arithmetic equal-year summary of within-year, median-collapsed withheld-date predictions. Individual interval overlap or separation is not a significance test.

## Validation and provenance

PASS: all 36 plotted estimates and 72 interval endpoints match committed source values, including direct checks of Matplotlib point and interval coordinates. Exported CSV preserves source decimal strings exactly. Peak denominators independently match counts of saved reference_eligible=True records; no peak statistic was recalculated.

- [vombsjon_transfer_equal_year_summary.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_equal_year_summary.csv): SHA256 `af3efcd45da4f01f74a90ff1d16483f1b4374188d3b6e60bc5338409035ae2a1`; committed bytes, local bytes, and frozen manifest agree.
- [vombsjon_transfer_peak_metrics.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_peak_metrics.csv): SHA256 `92a5b93ecc3e1ad9def88afa421567b80e0b46616008f61a6ed879c75f75b00a`; committed bytes, local bytes, and frozen manifest agree.

## Output SHA256

- [figure_04_vombsjon_primary_transfer.pdf](figure_04_vombsjon_primary_transfer.pdf): `1f0a9178beb820ac748897101e26b3ee1c5e139afe19f44e659577fc4e8cb3c5`
- [figure_04_vombsjon_primary_transfer.png](figure_04_vombsjon_primary_transfer.png): `010d554c4ddb0efbc633f135fc6ea3679e2a938785fb4ea15dec7eb9a5d17fd2`
- [figure_04_vombsjon_primary_transfer.csv](figure_04_vombsjon_primary_transfer.csv): `148b4f1f1ae10a7dacb12ffab0e0168a1edd4c673cdec3b83bebae2ead506884`

## Exact plotted values

Original CSV decimal strings; no presentation rounding. Design 1 is isolated; designs 2–4 are consecutive acquisitions.

| Panel | Acquisitions | Frozen method | Estimate | Lower 95% | Upper 95% | Available scenarios |
|---|---:|---|---:|---:|---:|---:|
| a | 1 | linear_interpolation | 0.16484462125055904 | 0.13586761622403323 | 0.19423651341582834 | 315 |
| a | 1 | timesat_double_logistic | 0.1700832982418267 | 0.13933290275013463 | 0.20043402032246482 | 315 |
| a | 1 | timesat_smoothing_spline | 0.18203311489607704 | 0.1542760255254438 | 0.20963431615872458 | 315 |
| a | 2 | linear_interpolation | 0.19598049148305363 | 0.1606303721244729 | 0.23020686343785318 | 305 |
| a | 2 | timesat_double_logistic | 0.20718823383415885 | 0.1689631363315984 | 0.24590500827002676 | 305 |
| a | 2 | timesat_smoothing_spline | 0.23157761563108262 | 0.19218453605451466 | 0.26980366917388926 | 305 |
| a | 3 | linear_interpolation | 0.2214839878562947 | 0.18130106354603412 | 0.26071325362660985 | 295 |
| a | 3 | timesat_double_logistic | 0.23837095001489805 | 0.19678867750364304 | 0.2813486062771314 | 295 |
| a | 3 | timesat_smoothing_spline | 0.2687118661275231 | 0.21826538131695827 | 0.31699474496497854 | 295 |
| a | 4 | linear_interpolation | 0.25396972380580396 | 0.21559277975583913 | 0.2934329364357148 | 285 |
| a | 4 | timesat_double_logistic | 0.2711175484363185 | 0.22615434208515134 | 0.3226240628083049 | 285 |
| a | 4 | timesat_smoothing_spline | 0.3328752661397828 | 0.28326848275760264 | 0.3800627853371472 | 285 |
| b | 1 | linear_interpolation | 0.7548156071004845 | 0.6882085106353404 | 0.8183927630436488 | 315 |
| b | 1 | timesat_double_logistic | 0.7454177729770152 | 0.6757005261686748 | 0.8140043042442987 | 315 |
| b | 1 | timesat_smoothing_spline | 0.7292038157499093 | 0.6638644413319673 | 0.7920566051025323 | 315 |
| b | 2 | linear_interpolation | 0.7596495779797665 | 0.6823678352825758 | 0.8321806736134902 | 305 |
| b | 2 | timesat_double_logistic | 0.72270493011602 | 0.6358883869130894 | 0.8036743842940631 | 305 |
| b | 2 | timesat_smoothing_spline | 0.7425046834094354 | 0.6591389239435854 | 0.8201152550831128 | 305 |
| b | 3 | linear_interpolation | 0.7382007709573513 | 0.6387829379946821 | 0.8227527705019626 | 295 |
| b | 3 | timesat_double_logistic | 0.6925325728911836 | 0.5749259152015889 | 0.7845942891384543 | 295 |
| b | 3 | timesat_smoothing_spline | 0.7399022726842642 | 0.6359621761602907 | 0.829683990724271 | 295 |
| b | 4 | linear_interpolation | 0.7138218161220216 | 0.618385336447254 | 0.7989828239831357 | 285 |
| b | 4 | timesat_double_logistic | 0.6625423680614639 | 0.5300964164383097 | 0.7602384511917839 | 285 |
| b | 4 | timesat_smoothing_spline | 0.6944843363791936 | 0.6179346221882622 | 0.7767726714550203 | 285 |
| c | 1 | linear_interpolation | 0.4 | 0.1 | 0.7 | 10 |
| c | 1 | timesat_double_logistic | 0.4 | 0.1 | 0.7 | 10 |
| c | 1 | timesat_smoothing_spline | 0.3 | 0.0 | 0.6 | 10 |
| c | 2 | linear_interpolation | 0.3 | 0.05 | 0.55 | 20 |
| c | 2 | timesat_double_logistic | 0.4 | 0.1 | 0.7 | 20 |
| c | 2 | timesat_smoothing_spline | 0.3 | 0.15 | 0.45 | 20 |
| c | 3 | linear_interpolation | 0.29999999999999993 | 0.16666666666666666 | 0.4333333333333333 | 30 |
| c | 3 | timesat_double_logistic | 0.4333333333333333 | 0.13333333333333333 | 0.7333333333333333 | 30 |
| c | 3 | timesat_smoothing_spline | 0.29999999999999993 | 0.13333333333333333 | 0.4666666666666666 | 30 |
| c | 4 | linear_interpolation | 0.275 | 0.15 | 0.4 | 40 |
| c | 4 | timesat_double_logistic | 0.325 | 0.075 | 0.575 | 40 |
| c | 4 | timesat_smoothing_spline | 0.25 | 0.125 | 0.4 | 40 |
