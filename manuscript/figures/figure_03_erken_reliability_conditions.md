# Figure 3 — Erken reliability conditions

Figure production only; no reconstruction, reliability experiment, metric, aggregation, confidence interval or inferential comparison was recomputed.

Source commit: `988499b765717fe63e3abac64651fdf487fc216c`. Script: [47_plot_erken_reliability_conditions.py](../../scripts/47_plot_erken_reliability_conditions.py).
Runtime: Python 3.12.14; Matplotlib 3.10.8.

## Manuscript caption

Erken reconstruction reliability under controlled consecutive deletion windows. (a) Equal-year nRMSE for 10-, 20-, 30- and 45-calendar-day windows. (b) Equal-year nRMSE within the existing low, medium and high hidden-gap activity classes for 45-day windows. (c) Equal-year global-peak timing success within ±10 calendar days for 45-day windows with the dense-reference global peak outside or inside the deletion window. Points and 95% whole-year cluster-bootstrap intervals are copied exactly from the frozen summary tables. Scenario metrics were summarized within year and stratum before equal weighting across seven Erken years (2019–2025); the saved intervals use 10,000 whole-year resamples. Method offsets distinguish overlapping symbols, not different durations or strata. Panel (a) uses discrete ordered duration groups and connecting lines only as visual guides, not a fitted response or threshold.

The activity classes are the frozen duration-specific tertiles of continuous A_gap, a retrospective descriptor calculated from the hidden complete Erken reference. A_gap is the within-window total absolute daily change divided by the yearly common-support Q95−Q05 scale; it is not observed inside an unknown operational gap. No thresholds or bins were recalculated. Peak containment concerns the Erken dense-reference global annual peak under the frozen common-support rules, not Vombsjön observed-proxy validation. In boundary-truncated 2019 and 2025, this common-support maximum is not asserted to be the full-calendar-year maximum.

All three primary methods retain their frozen roles: linear interpolation is the untuned baseline, TIMESAT double logistic uses frozen effective defaults, and TIMESAT smoothing spline uses the Erken outer-fold selected setting inherited by the controlled-gap experiments, without scenario retuning. Per-method scenario counts in (a) are 1379/1525/1475/1367 in duration order; in (b), 456/455/456 for low/medium/high; in (c), 1122/245 for peak outside/inside. All selected metrics are available, with seven contributing years in every stratum. Overlapping windows are nested within years and are not independent seasonal replicates.

These descriptive conditions retain metric-specific method behavior. Interval overlap or separation is not a significance test; no universal gap-duration threshold or operational A_gap predictor is claimed. Erken nRMSE must not be compared directly with Vombsjön nRMSE because their normalization and estimands differ.

## Validation and provenance

PASS: all 27 plotted estimates and 54 interval endpoints match the committed source rows, including Matplotlib point/interval coordinates. CSV preserves exact source decimal strings and all source denominator fields. Panel (a) selects only nrmse and 10/20/30/45-day windows; panel (b) selects only 45-day nrmse and existing low/medium/high classes; panel (c) selects only 45-day peak_timing_success_10d and False/True peak-containment strata. Only the three primary methods are included, in manuscript order; saved analysis roles and favorable directions are checked. All selected rows have 7/7 metric-available years, zero reconstruction failures and zero unavailable metrics. No source result, config, protocol or freeze is written by this script.

- [erken_reliability_consecutive_duration_summary.csv](../../results/reliability_synthesis/v1.0/erken_reliability_consecutive_duration_summary.csv): SHA256 `acf112f1e687f63a7b842d19a6f15904f69e7f2fd8742d4639c0e4c1d286c4f5`; Git, local bytes and frozen manifest agree.
- [erken_reliability_consecutive_activity_summary.csv](../../results/reliability_synthesis/v1.0/erken_reliability_consecutive_activity_summary.csv): SHA256 `4cb72c969137ad38371fcfda2227f51358b157bb295c64de0212ff9107abb2c5`; Git, local bytes and frozen manifest agree.
- [erken_reliability_consecutive_peak_containment_summary.csv](../../results/reliability_synthesis/v1.0/erken_reliability_consecutive_peak_containment_summary.csv): SHA256 `af9d1526674d553b3d9bed003662c05ba7d634409dc0808a5d6e563ac6bb813d`; Git, local bytes and frozen manifest agree.

## Output SHA256

- [figure_03_erken_reliability_conditions.pdf](figure_03_erken_reliability_conditions.pdf): `bdac0c4d87c33813959f7dfb0a1d7bd5d4e5fd093521a5397254120ee27e25cc`
- [figure_03_erken_reliability_conditions.png](figure_03_erken_reliability_conditions.png): `700e8562ef64334d00ea14ebe2f1d4a35692d26c715ded837651887d31421333`
- [figure_03_erken_reliability_conditions.csv](figure_03_erken_reliability_conditions.csv): `3cb8267e95c81521934ac374d1ed3c28fc181e64b50638e6595cb877eea39146`

## Exact plotted values and availability

All values below retain the source decimal strings. Years are metric-available / in-stratum. Scenarios are metric-available / total; unavailable metrics and reconstruction failures are zero in every row. Full source fields, including analysis_role and coverage, are preserved in the CSV.

| Panel | Stratum | Method | Estimate | Lower 95% | Upper 95% | Years | Scenarios |
|---|---|---|---:|---:|---:|---|---|
| a | 10 | linear_interpolation | 0.20755877398837125 | 0.16065614897729455 | 0.2504072345110927 | 7/7 | 1379/1379 |
| a | 10 | timesat_double_logistic | 0.25266600306571951 | 0.21943187461877334 | 0.28800029563491958 | 7/7 | 1379/1379 |
| a | 10 | timesat_smoothing_spline | 0.22721113873999546 | 0.19254650493449971 | 0.2588310861863462 | 7/7 | 1379/1379 |
| a | 20 | linear_interpolation | 0.21362515732955747 | 0.17031346155877805 | 0.25409225223786269 | 7/7 | 1525/1525 |
| a | 20 | timesat_double_logistic | 0.25650434079641954 | 0.22418882665027917 | 0.29127597816434581 | 7/7 | 1525/1525 |
| a | 20 | timesat_smoothing_spline | 0.23534054270679028 | 0.2026344970656859 | 0.26367803181435573 | 7/7 | 1525/1525 |
| a | 30 | linear_interpolation | 0.22074099291942442 | 0.17858597529671574 | 0.25914990912498564 | 7/7 | 1475/1475 |
| a | 30 | timesat_double_logistic | 0.26299787947784214 | 0.23207486274648009 | 0.29580052316252503 | 7/7 | 1475/1475 |
| a | 30 | timesat_smoothing_spline | 0.24625412763592447 | 0.21492698321492382 | 0.27462033273336073 | 7/7 | 1475/1475 |
| a | 45 | linear_interpolation | 0.23778782213568619 | 0.19773743805739172 | 0.27668745361153479 | 7/7 | 1367/1367 |
| a | 45 | timesat_double_logistic | 0.28913048138190628 | 0.26349899152444856 | 0.31829329043933929 | 7/7 | 1367/1367 |
| a | 45 | timesat_smoothing_spline | 0.27964019293106174 | 0.24291417602447543 | 0.31541747109336399 | 7/7 | 1367/1367 |
| b | low | linear_interpolation | 0.21607838681088859 | 0.1698510324047002 | 0.25575534644262193 | 7/7 | 456/456 |
| b | low | timesat_double_logistic | 0.27408505838006281 | 0.24981417763573491 | 0.30322076775973433 | 7/7 | 456/456 |
| b | low | timesat_smoothing_spline | 0.24596575658195524 | 0.20954665963938532 | 0.27687828643641682 | 7/7 | 456/456 |
| b | medium | linear_interpolation | 0.23730723462905948 | 0.2034154433303548 | 0.27017345168033646 | 7/7 | 455/455 |
| b | medium | timesat_double_logistic | 0.28201045628340621 | 0.25097940688135489 | 0.31435056225723657 | 7/7 | 455/455 |
| b | medium | timesat_smoothing_spline | 0.28229151445186529 | 0.24962631639797594 | 0.31507504223119365 | 7/7 | 455/455 |
| b | high | linear_interpolation | 0.27345285448297602 | 0.23587051979558371 | 0.31370257104393934 | 7/7 | 456/456 |
| b | high | timesat_double_logistic | 0.31748701241566224 | 0.28625669038405982 | 0.34970633722608063 | 7/7 | 456/456 |
| b | high | timesat_smoothing_spline | 0.31621086566110918 | 0.27988207155379913 | 0.35663428425119337 | 7/7 | 456/456 |
| c | False | linear_interpolation | 0.7041415800036489 | 0.41419449005655901 | 0.98985586571793471 | 7/7 | 1122/1122 |
| c | False | timesat_double_logistic | 0.51710086618259798 | 0.16445316588173733 | 0.77360531185654324 | 7/7 | 1122/1122 |
| c | False | timesat_smoothing_spline | 0.56337220182984427 | 0.21423879896786305 | 0.84738580727202106 | 7/7 | 1122/1122 |
| c | True | linear_interpolation | 0.25158730158730153 | 0.067460317460317457 | 0.52380952380952372 | 7/7 | 245/245 |
| c | True | timesat_double_logistic | 0.38730158730158731 | 0.1492063492063492 | 0.64761904761904765 | 7/7 | 245/245 |
| c | True | timesat_smoothing_spline | 0.44523809523809532 | 0.20394841269841268 | 0.70317460317460323 | 7/7 | 245/245 |
