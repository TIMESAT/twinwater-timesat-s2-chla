# Erken temporal-sampling join and audit

## Scope and provenance

Phase 2B-1 deterministically joins the canonical daily Erken reference
(`data/processed/erken_daily_clean.csv`) to the frozen date-level Sentinel-2
mask (`data/processed/erken_s2_observation_mask.csv`). The work started from
commit `144b59b49b84b939260397573ff7e89556757ed1` (`Build Erken SCL observation
mask`). It is a data-integration and descriptive sampling audit only.

The Sentinel-2 scene-quality rule was frozen before this join and was not
altered using CHLF values.

The frozen rule remains
`scl3x3_b1_w8_centernotbad_p0_class2zero_v1`, the mask version remains
`erken_s2_observation_mask_v1`, and the temporal observation unit remains one
unique calendar date. This phase does not run or select TIMESAT, GAM, linear
interpolation, LOYO, controlled gaps, performance metrics, seasonal metrics,
or Vombsjön transfer.

## Deterministic join and flags

Calendar `date` is the unique join key. A one-to-one left join preserves all
2,420 daily reference rows from 2019-04-17 through 2025-11-30. It neither
invents nor forward-fills satellite metadata. On dates absent from the
Sentinel-2 inventory, `s2_inventory_date` and `s2_date_usable` are false and
satellite provenance fields remain missing.

The output keeps the observation layers separate:

- `reference_value_available`: CHLF is present and finite on the daily row;
- `s2_inventory_date`: at least one Sentinel-2 product is represented on the
  date in the frozen inventory;
- `s2_date_usable`: at least one same-day product passes the frozen SCL rule;
- `open_water`: the previously derived physical flag, equivalent to
  `PRESENCE_ICE == 0`;
- `s2_openwater_reference_candidate`: exactly `s2_date_usable AND open_water
  AND reference_value_available`.

The preliminary sparse-candidate flag is not yet the final reconstruction
input mask because analysis-season and year-eligibility rules remain to be
frozen.

## Input and join audit

The daily reference contains 2,420 unique dates, no duplicate or missing
calendar dates, no missing/non-finite/negative CHLF values, and no
`PRESENCE_ICE`/`ice_flag` or `open_water` inconsistencies. The measurement
regime has 1,355 `pre_2023` rows and 1,065 `2023_onward` rows, with the only
transition on 2023-01-01.

The frozen mask contains 926 unique inventory dates and 307 unique usable
dates, with no duplicate dates or selected-product inconsistencies. Its 950
products include 313 passing products. Product/date totals and same-day
selection fields pass the frozen-mask consistency checks.

All 926 inventory dates and all 307 usable dates match daily-reference rows.
No usable date lacks CHLF. Nineteen usable dates are ice/non-open-water, leaving
288 preliminary candidates. The programmatically checked, mutually exclusive
reconciliation is:

```text
307 usable dates
= 288 preliminary open-water/reference candidates
+ 19 usable but non-open-water dates
+ 0 usable dates with a missing/non-finite reference value
+ 0 usable dates without a daily-reference row
```

## Annual sampling diagnostics

Intervals in this table are within-year calendar-day differences between
consecutive preliminary candidates. Counts are descriptive observation-design
diagnostics, not reconstruction performance or failure thresholds.

| Year | Candidates | First | Last | Median | Q25 | Q75 | Maximum | >10 | >20 | >30 | >45 |
|---:|---:|:---|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 35 | 2019-04-17 | 2019-12-05 | 5 | 2.25 | 10 | 25 | 7 | 1 | 0 | 0 |
| 2020 | 56 | 2020-01-19 | 2020-11-22 | 3 | 2 | 7 | 22 | 7 | 1 | 0 | 0 |
| 2021 | 46 | 2021-03-19 | 2021-12-04 | 5 | 3 | 10 | 15 | 5 | 0 | 0 | 0 |
| 2022 | 36 | 2022-04-18 | 2022-12-09 | 5 | 3 | 10 | 20 | 7 | 0 | 0 | 0 |
| 2023 | 27 | 2023-04-21 | 2023-11-29 | 4 | 2.25 | 9.5 | 42 | 6 | 4 | 1 | 0 |
| 2024 | 40 | 2024-04-17 | 2024-11-28 | 5 | 3 | 7 | 20 | 5 | 0 | 0 | 0 |
| 2025 | 48 | 2025-03-21 | 2025-11-26 | 5 | 2.5 | 7 | 15 | 6 | 0 | 0 | 0 |

Usable-but-non-open-water counts are 0, 0, 2, 2, 9, 1, and 5 for 2019
through 2025, respectively. Every year has zero usable dates with a missing
reference value.

## Calendar-interval and winter context

The 307 frozen usable dates have a global median interval of 5 days and a
maximum of 120 days. The 288 preliminary candidates have 287 consecutive
intervals, a median of 5 days, and a maximum of 140 days. Six candidate
intervals cross a year boundary and six contain ice days. These categories
are retained explicitly in `erken_temporal_sampling_gaps.csv`.

The five largest candidate intervals are cross-year intervals of 140, 135,
133, 117, and 113 days. They include winter/ice context and must not be
confused with internal open-water calendar spans. The largest within-year
candidate interval is 42 days (2023-10-18 to 2023-11-29). These facts do not
define a reconstruction gap threshold, an analysis season, or reliability.

## Partial-year boundary evidence

### 2019

The reference begins on 2019-04-17, 106 calendar days after 1 January, while
the available boundary is already open water; the conservative boundary
status is `left_truncated`. The first candidate is the reference start and the
last is 2019-12-05 (35 candidates; 0 and 26 days from the corresponding
reference boundaries). Boundary CHLF is 4.89651, above the observed-year
median (2.80601) and first-14-day median (3.419985), with a first-window slope
of -0.275175 per day. Earlier trajectory is unobserved. The observed maximum
is 60.8949 on 2019-08-26, 131 days after the reference start and 127 days
before its end; no near-boundary cutoff is applied.

### 2025

The reference ends on 2025-11-30, 31 calendar days before 31 December, while
the available boundary is open water; the conservative boundary status is
`right_truncated`. The first candidate is 2025-03-21 and the last is
2025-11-26 (48 candidates; 79 and 4 days from the corresponding reference
boundaries). Boundary CHLF is 9.25375, above the observed-year median
(5.61248) and last-14-day median (8.49862), with a last-window slope of
+0.105419 per day. Later trajectory is unobserved. The observed maximum is
83.4709 on 2025-10-14, 286 days after the reference start and 47 days before
its end; no near-boundary cutoff is applied.

Both years therefore require a later scientific decision about seasonal and
LOYO eligibility. Phase 2B-1 makes no inclusion or exclusion decision.

## Outputs and reproduction

Run from the repository root:

```bash
python scripts/06_erken_temporal_sampling_join.py
```

The script writes the daily master table, four audit tables, and four figures
in PNG and PDF formats. `--help` documents path overrides and
`--skip-figures` supports table-only verification.

Known limitations are deliberate: CHLF is a high-frequency pelagic temporal
reference rather than literal satellite-surface chlorophyll truth; the broad
measurement-regime flag is provenance rather than causal attribution; SCL
does not address glint, reflectance, atmospheric-correction, shoreline, or
retrieval quality; open-water bounds can be non-contiguous; and no final
analysis season, year eligibility, reconstruction input, or reliability
criterion is defined here.
