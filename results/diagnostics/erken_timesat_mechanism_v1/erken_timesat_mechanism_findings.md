# Erken TIMESAT mechanism diagnostic findings

Status: diagnostic only. These results do not select or recommend a production
parameter, retune a frozen method, or modify any Phase 3/4/5 result.

## 1. Is smoothing spline `p_smooth=0` close to linear interpolation?

They are of the same broad error scale but are not empirically equivalent on
the frozen withheld dates. Equal-year mean RMSE is 4.35309 for linear and
4.91148 for spline-0; equal-year mean nRMSE is 0.203463 and 0.232343,
respectively. Thus spline-0 has +0.558394 RMSE and +0.028880 nRMSE (14.2%
relative to linear's nRMSE). Spline-0 has lower yearly RMSE only in 2022 (one
of seven years). Equal-year correlation is 0.863893 for linear and 0.829164 for
spline-0. Event recovery is identical at 10 days (0.952381), higher for
spline-0 at 5 days (0.797619 versus 0.738095), and lower at 15 days (0.952381
versus 1.0). Neither curve has negative reconstructed values.

## 2. Does spline-0 show geometry unavailable to linear interpolation?

Yes. Of 280 within-segment adjacent-observation intervals, spline-0 leaves the
range of its two endpoint observations in 123 (43.9%) and changes derivative
sign in 124 (44.3%). A linear segment cannot leave its endpoint range or
create an internal direction reversal. This is a geometric observation, not a
claim that every overshoot is scientifically wrong.

## 3. Are those spline behaviors associated with larger withheld errors?

Descriptively, yes. Among 277 intervals with withheld evaluation dates, mean
`spline0 RMSE - linear RMSE` is 0.617857 for intervals with endpoint-range
overshoot and 0.045491 without it; medians are 0.083275 and 0.010923. The
Pearson association between normalized maximum overshoot and the RMSE
difference is 0.719429 (Spearman 0.304749). The largest normalized overshoot
and largest RMSE disadvantage occur in the same interval, 2020-08-01 through
2020-08-09: normalized overshoot 0.685214, positive overshoot 14.424765 CHLF,
and RMSE difference 8.827249. These are interval-level associations and do not
establish causality.

## 4. What is the exact `p_seapar` mapping?

At frozen TIMESAT source commit
`b20844140bf38543349552341212609fa18b24b1`, `fortran/season.f90:47` uses:

```fortran
pval = 1000.d0 + (50000.d0 - 1000.d0) * seasonpar
```

Lines 49–52 clamp this value to `[1000, 50000]`; line 56 passes it to
`smoothingspline`. Therefore `p_seapar=0` is exactly 1000 and `p_seapar=1` is
exactly 50000. The native parameter cannot reach coarse-spline smoothing below
1000. `season.f90:95` calls `findallpeaks`; subsequent filtering and
`initialdlpar` define season initialization passed through
`processtimeseries.f90:195–214` to the unchanged final `processdl` fit. The
full trace is in `double_logistic_coarse_season_source_trace.md`.

## 5. Does direct smoothing below 1000 expose more Erken coarse peaks?

Yes. The total number of filtered coarse peaks within frozen common support is:

| Direct coarse smoothing | 1000 | 300 | 100 | 30 | 10 | 3 | 1 | 0 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Filtered peaks, seven-year total | 11 | 12 | 19 | 28 | 37 | 44 | 49 | 61 |

At smoothing 0, every year has more filtered common-support peaks than at
1000. This establishes parameter effectiveness; it does not establish that
all additional peaks represent reference bloom events.

## 6. Do additional coarse peaks survive into the final double-logistic curve?

Some do, but the response is not monotonic. Final-curve matches among the 18
frozen events are 10, 10, 10, 10, 12, 11, 11, and 9 across the ordered grid
1000, 300, 100, 30, 10, 3, 1, 0. Relative to 1000, smoothing 10 adds nearby
coarse peaks for four reference events, loses one nearby coarse peak, and
adds two final event matches. The much larger coarse-peak count at smoothing
0 does not persist as more final event matches. The unchanged final fitting
and season handling therefore suppress or reorganize many added coarse peaks.

The raw final `nseason` return is preserved in every B1/B2 scenario summary as
requested. It is not used for this inference: the single-pixel extension's
ancillary return can contain unstable/uninitialized-looking values, whereas
the explicitly instrumented internal count and final daily curves are stable.

## 7. Where are the 18 events lost?

The table below separates final misses with no filtered coarse peak within 15
days (coarse-detection bottleneck) from final misses despite such a coarse peak
(final-fitting bottleneck). It also retains the observed cases where a final
peak matches without a nearby filtered coarse peak rather than forcing them
into either bottleneck category.

| Coarse smoothing | Coarse + final matched | Coarse bottleneck | Final-fit bottleneck | Final match without nearby filtered coarse peak |
|---:|---:|---:|---:|---:|
| 1000 | 10 | 8 | 0 | 0 |
| 300 | 10 | 8 | 0 | 0 |
| 100 | 9 | 7 | 1 | 1 |
| 30 | 9 | 6 | 2 | 1 |
| 10 | 9 | 2 | 4 | 3 |
| 3 | 10 | 4 | 3 | 1 |
| 1 | 9 | 2 | 5 | 2 |
| 0 | 7 | 3 | 6 | 2 |

At the current lowest native value (1000), all eight final misses are already
absent at filtered coarse-season detection. As smoothing is reduced, that
bottleneck falls in several scenarios while final-fit bottlenecks appear.

## 8. Does the evidence support an independent `p_coarse_smooth` parameter?

It supports exposing an independent, backward-compatible control for governed
research and mechanism testing: the current `p_seapar` mapping cannot probe
below 1000, and the isolated override demonstrably changes coarse peak
detection, final trajectories, withheld errors, and event recovery. It does
not support adopting any non-default value in production from this experiment
alone. Responses differ by year and metric, and no value improves all outcomes.

For context only, equal-year mean nRMSE across the direct grid is 0.238893,
0.239747, 0.234375, 0.239305, 0.233267, 0.239377, 0.242299, and 0.243988 in
the same order. These values are diagnostic observations, not a selection.

## 9. Smallest backward-compatible API shape

Add an optional `p_coarse_smooth` keyword/config field whose default is
`None`. When `None`, execute the frozen mapping and clamp byte-for-byte. When a
finite nonnegative value is supplied, pass it only to the preliminary
`smoothingspline` call; retain `p_seapar` and all subsequent peak filtering,
initialization, and final double-logistic fitting unchanged. Record both the
requested and effective values in runtime provenance. The default-null path
must pass byte-equivalence tests against TIMESAT 4.4.1 before any governed use.
No such production API change was implemented here.

## Reproducibility and scope evidence

- Diagnostic code commit: `ba5a64bbe0678f1154cfe8a187ee7e967c172015`
- Canonical main base: `add063e89a47b31605c354d3c4cdb87b01412056`
- Frozen TIMESAT source commit: `b20844140bf38543349552341212609fa18b24b1`
- Frozen production extension SHA256:
  `689d2a9b9a82c9732ffd046ff64b9586c826101216e3e19841e94d66f9ea0b3b`
- Diagnostic extension SHA256:
  `da2c724274be3b73243ac6f078a0d86f5425fd30144039aa2a4c4d828d2a67d8`
- Instrumentation patch SHA256:
  `4f2943e64bcbe2009a30d28307e18426f45f3a138dc3918f3a90223d089e1ebb`
- All seven default diagnostic final curves equal both the production-runtime
  output and saved frozen Phase 3 common-support curves byte-for-byte.
- Two complete final diagnostic reruns produced identical SHA256 values for all
  43 output files.
- No controlled-gap run was performed, no Vombsjön product was read, and no
  frozen Phase 3/4/5 result was modified.
