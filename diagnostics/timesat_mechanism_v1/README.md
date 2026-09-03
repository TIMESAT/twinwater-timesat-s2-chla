# Erken TIMESAT mechanism diagnostic build

This directory records the isolated, diagnostic-only modification used by
`scripts/27_erken_timesat_mechanism_diagnostic.py`. It is not part of the
production TIMESAT runtime and does not alter any frozen reconstruction.

## Frozen baseline

- TIMESAT release: 4.4.1
- TIMESAT source commit: `b20844140bf38543349552341212609fa18b24b1`
- timesat-cli: 1.9.2
- production extension SHA256:
  `689d2a9b9a82c9732ffd046ff64b9586c826101216e3e19841e94d66f9ea0b3b`
- production Python: 3.12.12
- production NumPy: 2.5.2

## Isolated build

The source checkout was detached at the frozen source commit and patched with
[`timesat_v4.4.1_instrumentation.patch`](timesat_v4.4.1_instrumentation.patch).
The patch adds read-only one-pixel exports for the preliminary spline, its
effective smoothing value, raw and filtered peak indices, initialized season
count, plus an explicit diagnostic-only coarse-smoothing override. The final
double-logistic fitting code is unchanged.

The build used GNU Fortran 14.3.0, the frozen Python 3.12.12 interpreter, and
the same NumPy 2.5.2 ABI as the production extension. The resulting diagnostic
extension SHA256 is:

`da2c724274be3b73243ac6f078a0d86f5425fd30144039aa2a4c4d828d2a67d8`

The frozen source tree's Meson file omitted `preprocesstimeseries.f90` from its
source list even though the routine is called by the build. The isolated build
adds that existing source file to the build list; this is a linkage correction,
not an algorithm change. The patch also pins Meson to the frozen Python
interpreter.

Before any mechanism experiment, the diagnostic runtime is compared with the
production runtime for all seven Erken years. The final 365-day output arrays
must be byte-identical or the diagnostic aborts. The generated equivalence
table records this gate and any auxiliary `numseason` difference separately.

## Scope guard

The runner accepts only the dedicated diagnostic branch and writes only below
`results/diagnostics/erken_timesat_mechanism_v1`. It checks that all committed
Phase 3, Phase 4, and Phase 5 outputs still equal the canonical main base
commit before and after execution. It does not read or generate controlled-gap
or Vombsjön products.
