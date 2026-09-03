# TIMESAT 4.4.1 double-logistic coarse-season source trace

Diagnostic scope: frozen core source commit `b20844140bf38543349552341212609fa18b24b1`.
No production source or configuration was changed.

## `p_seapar` mapping and coarse curve

In `fortran/season.f90`, subroutine `season` starts at line 4. Lines 46–56 map
`seasonpar` to the smoothing-spline control and build the preliminary daily curve:

```fortran
pval = 1000.d0 + (50000.d0 - 1000.d0) * seasonpar
if (pval < 1000.d0) pval = 1000.d0
if (pval > 50000.d0) pval = 50000.d0
call smoothingspline(...,pval,yfit(...),...)
```

Thus `p_seapar=0` maps exactly to `1000`, and `p_seapar=1` maps to `50000`.
Lines 57–70 extend the ends and clamp the preliminary curve to the base.

## Peak detection and filtering

`season.f90:95` calls `findallpeaks(yfit,...)`. The state machine is implemented in
`fortran/findallpeaks.f90:29–79`. `season.f90:107–130` then rejects unsupported
lobes and peaks below 1% of the largest preliminary peak; lines 132–147 remove
peaks separated by fewer than five internal days. Lines 158–160 call the internal
`initialdlpar`, which derives 20/50/80% transition positions and can reject seasons
without observation support (`season.f90:166–263`).

## Control of the final double logistic

`fortran/processtimeseries.f90:195–197` passes `p_seapar` to `season`, receiving
the preliminary curve, initial double-logistic parameters and season count. For
`fitmethod=1`, lines 207–214 call `processdl` with those initial parameters.
`fortran/processdl.f90:40–55` calls `findoddpoints` and `fitlogistic2`, then applies
the final range clamp. The preliminary curve therefore controls detected seasons
and initialization, while `processdl` controls the final nonlinear fit.

## One-pixel instrumentation

The diagnostic patch records the absolute preliminary curve immediately after the
base clamp, raw and filtered peak indices, actual `pval`, and initialized-season
count. An explicit override is applied only after the frozen mapping/clamp and only
in the isolated diagnostic build. With the override disabled, all seven final
365-day Erken curves are byte-identical to the frozen production binary.
