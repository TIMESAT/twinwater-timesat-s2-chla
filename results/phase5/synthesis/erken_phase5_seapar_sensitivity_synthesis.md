# Erken Phase S5 double-logistic seasonal-parameter sensitivity synthesis

**Status:** HARD HUMAN REVIEW GATE — stop before any Vombsjön inspection.

**Scope:** Erken only; secondary/descriptive sensitivity analysis. No method ranking, inferential model, universal gap threshold, or primary-result replacement.

## Training-only selection

- 2019: `p_seapar=0.0` (mean training nRMSE 0.235594).
- 2020: `p_seapar=0.0` (mean training nRMSE 0.239900).
- 2021: `p_seapar=0.0` (mean training nRMSE 0.247305).
- 2022: `p_seapar=0.0` (mean training nRMSE 0.226152).
- 2023: `p_seapar=0.0` (mean training nRMSE 0.249045).
- 2024: `p_seapar=0.0` (mean training nRMSE 0.241768).
- 2025: `p_seapar=0.0` (mean training nRMSE 0.232484).

All outer folds selected 0.0 from the frozen grid. Real candidate curves were not numerically identical; the S1 effectiveness gate passed.

## Actual-mask default-DL versus CV-DL

| Year | default nRMSE | CV nRMSE | default event ≤10 d | CV event ≤10 d | default abs. integral error | CV abs. integral error |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 0.272200 | 0.258686 | 0.500 | 0.500 | 544.432 | 455.089 |
| 2020 | 0.254481 | 0.232850 | 0.000 | 1.000 | 6.220 | 57.027 |
| 2021 | 0.210329 | 0.188419 | 0.500 | 1.000 | 131.333 | 161.524 |
| 2022 | 0.334949 | 0.315334 | 0.500 | 0.500 | 54.796 | 99.039 |
| 2023 | 0.178265 | 0.177977 | 0.333 | 0.333 | 71.452 | 76.948 |
| 2024 | 0.225656 | 0.221638 | 0.500 | 0.500 | 55.852 | 61.000 |
| 2025 | 0.277314 | 0.277345 | 0.000 | 0.000 | 17.634 | 65.621 |

CV-DL recovered 9/18 frozen events within 10 days versus 5/18 for default DL. The equal-year recovery fraction changed from 0.333 to 0.548. This is a sizeable descriptive increase, but no inferential materiality threshold was defined.

Point-wise nRMSE improved in 6/7 years. Absolute integral error increased in 6/7 years, so the event gain did come with a clear integral-error trade-off; 2025 also had a very small nRMSE increase.

## Controlled gaps (year-aware descriptive summaries)

Equal-year means below first summarize scenarios within each year and then weight the seven lake-years equally.

### Random deletion

| Deleted fraction | default mean nRMSE | CV mean nRMSE | default event ≤10 d | CV event ≤10 d |
|---:|---:|---:|---:|---:|
| 0.1 | 0.253208 | 0.242575 | 0.349 | 0.507 |
| 0.2 | 0.258083 | 0.247427 | 0.359 | 0.491 |
| 0.3 | 0.265363 | 0.251747 | 0.369 | 0.483 |
| 0.5 | 0.287634 | 0.279724 | 0.362 | 0.435 |

### Consecutive internal gaps

| Duration (d) | default mean nRMSE | CV mean nRMSE | default event ≤10 d | CV event ≤10 d |
|---:|---:|---:|---:|---:|
| 10 | 0.252666 | 0.241743 | 0.349 | 0.515 |
| 20 | 0.256504 | 0.246148 | 0.349 | 0.498 |
| 30 | 0.262998 | 0.253511 | 0.331 | 0.478 |
| 45 | 0.289130 | 0.283569 | 0.293 | 0.429 |

The machine-readable tables retain year, deletion fraction, duration, global-peak containment, continuous relative gap position, and continuous A_gap associations. The 2,800 and 5,746 masks are never treated as independent lake-years.

## Governance boundary

All S1–S4 audits passed; original Phase 3/4 outputs remained checksum-identical. No Vombsjön file, result, or performance was accessed. This packet ends at the required human-review gate.
