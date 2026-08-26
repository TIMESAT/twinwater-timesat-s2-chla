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

## Decision 006 — Exploratory peak rule

Local peak counts are exploratory only. They use unsmoothed ice-free daily CHLF, `scipy.signal.find_peaks`, a 30-calendar-day minimum separation, and relative-prominence sensitivity thresholds of 0.10, 0.20, and 0.30 of each year's ice-free amplitude. The observed global annual maximum is always reported separately.
