# Decisions log

## Decision 001 — Erken development domain

Lake Erken is the dense-reference temporal-development domain.

## Decision 002 — Locked Vombsjön transfer

Lake Vombsjön is reserved as a locked external transfer and stress-test domain. Temporal reconstruction parameters will not be retuned based on Vombsjön performance.

## Decision 003 — Year-blocked validation

Future temporal method selection will use year-blocked / leave-one-year-out validation rather than random daily train/test splitting. A day is not treated as an independent calibration replicate.

## Decision 004 — Phase 1 scope

Phase 1 is restricted to quality control and characterization of seasonal diversity. No reconstruction method or gap experiment is implemented.

## Decision 005 — Primary timing metric

Peak date is currently the primary planned cross-scale timing metric. Onset and end require more cautious interpretation, particularly for Sentinel-2 indices.

## Decision 006 — Observational domain

The canonical Erken reference retains every daily observation, including ice periods. Until actual Sentinel-2 observation and QC masks are introduced, the main future reconstruction-evaluation domain is `open_water`, defined as `PRESENCE_ICE == 0`.

## Decision 007 — Complete reference versus satellite-observable truth

Events during ice-covered periods remain valid features of the ecological/reference record but lie outside the preliminary satellite-observable domain. Failure to reconstruct such events from Sentinel-2 must not automatically be interpreted as temporal-reconstruction failure.

## Decision 008 — Measurement regime

The known 2023-era measurement-configuration change is tracked using the broad `pre_2023` and `2023_onward` provenance labels and will be included in sensitivity analyses. No causal attribution to the measurement change is assumed, and the boundary is not asserted to be an instantaneous homogeneous instrument switch.

## Decision 009 — Partial-year terminology

Calendar-year truncation and potential open-water-season truncation are distinct concepts and must not be conflated. Boundary status uses only source coverage and the observed ice state at the available boundary.

## Decision 010 — Exploratory peak rule

Local peak counts are exploratory only. They use unsmoothed open-water daily CHLF, `scipy.signal.find_peaks`, a 30-calendar-day minimum separation, and relative-prominence sensitivity thresholds of 0.10, 0.20, and 0.30 of each year's open-water amplitude. Complete-reference and open-water global annual maxima are always reported separately.
