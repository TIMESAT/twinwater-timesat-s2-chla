# Seasonal Event Detection and Matching Protocol v1.0

**Status:** FROZEN before any real event-level reconstruction performance  
**Analysis class:** SECONDARY / EXPLORATORY  
**Parent contract:** `Reconstruction_Analysis_Contract_v1.0.1`  
**Reason for classification:** annual/global-maximum reconstruction results were already inspected before this supplementary protocol was frozen.

## 1. Purpose and non-interference rule

This protocol adds a supplementary event-level question:

> Can major seasonal bloom events be temporally recovered even when the identity of the annual/global maximum changes?

It does not replace or revise the already frozen and reported common-support
global-maximum metric. Event detection and matching must never affect spline
selection, TIMESAT defaults, observation masks, common support, controlled-gap
design, or any primary Phase 3 metric.

The protocol is frozen before event recovery is calculated for any real linear,
TIMESAT double-logistic, or TIMESAT smoothing-spline reconstruction.

## 2. Reference series and support

Use the existing published daily Erken CHLF reference exactly as used in Phase
3. Use the frozen year-specific common support and its existing contiguous
open-water segment identifiers.

Reference values receive no smoothing, clipping, outlier deletion, or other
preprocessing. In particular, do not use Savitzky–Golay, LOESS, splines,
rolling summaries, or any other filter.

For year `y`, define:

`Scale_y = Q95(CHLF_y) - Q05(CHLF_y)`

from the daily reference over the full frozen common support. Use the same
linear quantile convention as Phase 3. Detect events in each disconnected
open-water segment separately; no detection window may bridge a physical
support discontinuity.

## 3. Reference major-event detection

For each contiguous common-support segment, call
`scipy.signal.find_peaks` exactly as follows:

```python
find_peaks(
    reference_values,
    distance=30,
    prominence=0.30 * Scale_y,
    plateau_size=(1, None),
)
```

There is no height threshold, width threshold, or `wlen`. Record the SciPy
version. Store the actual yearly scale and prominence threshold with every
reference event.

For a detected plateau, use the exact temporal midpoint between the dates at
the returned left and right plateau edges. This may be a half-day timestamp for
an even-length plateau. Order all detected events chronologically within year
and assign identifiers `ERK_<year>_E01`, `E02`, and so on.

### 3.1 Frozen reference-only regression target

The detector must reproduce exactly 18 events:

| Year | Event dates |
|---|---|
| 2019 | 2019-08-26; 2019-10-12 |
| 2020 | 2020-04-18; 2020-08-09; 2020-09-09 |
| 2021 | 2021-04-08; 2021-08-09 |
| 2022 | 2022-08-07; 2022-09-26 |
| 2023 | 2023-04-23; 2023-07-31; 2023-09-01 |
| 2024 | 2024-07-19; 2024-08-31 |
| 2025 | 2025-03-30; 2025-07-14; 2025-08-28; 2025-10-14 |

Yearly counts are `2019=2`, `2020=3`, `2021=2`, `2022=2`, `2023=3`,
`2024=2`, and `2025=4`; total count is 18.

Frozen yearly `Q95-Q05` regression values are:

| Year | Scale |
|---|---:|
| 2019 | 28.561548 |
| 2020 | 21.051459 |
| 2021 | 22.15631 |
| 2022 | 16.804815 |
| 2023 | 10.6621499 |
| 2024 | 16.3173875 |
| 2025 | 29.979275 |

Reference-only preflight must fail on any event, date, identifier, count, or
yearly-scale mismatch. Thresholds must not be changed to force agreement.

## 4. Reconstruction peak candidates

This section is implemented now but may be exercised only with synthetic data
until a later explicitly authorized real event-performance run.

For each contiguous common-support segment of a valid, complete reconstruction,
call exactly:

```python
find_peaks(
    reconstructed_values,
    plateau_size=(1, None),
)
```

Apply no smoothing and no minimum prominence, height, distance, width, or
`wlen`. Candidate detection is deliberately amplitude-agnostic. Event identity
or matching must not depend on reconstructed magnitude. Reconstructed
prominence may be retained only as a diagnostic and must never enter detection
or matching.

Use the exact temporal midpoint of the detected plateau. Process disconnected
support segments separately.

If reconstruction fails or any required common-support prediction is missing
or non-finite, candidate detection and event metrics are unavailable. Such a
case is not an ordinary missed event.

## 5. One-to-one event matching

A reference event and reconstructed candidate are eligible to match only when
all three conditions hold:

1. same year;
2. same contiguous open-water segment; and
3. absolute timing difference no greater than 15 calendar days.

Matching is one-to-one and uses the following lexicographic optimization:

1. maximize the number of matched reference events;
2. minimize total absolute timing error;
3. for an exact remaining tie, order reference events chronologically and
   choose the lexicographically earliest reconstructed peak-time sequence.

Magnitude, prominence, height, and amplitude must never decide eligibility,
identity, assignment, or a tie.

For a valid reconstruction with no matched candidate within ±15 days, record:

- `event_status = missed_no_peak_within_15d`;
- signed and absolute timing errors unavailable;
- `success_5d = False`;
- `success_10d = False`;
- `success_15d = False`.

For a failed reconstruction or incomplete required support, use an explicit
unavailable status/reason and leave all event success fields unavailable.

## 6. Matched-event metrics

For each matched reference event report:

- signed timing error in calendar days (`reconstructed - reference`);
- absolute timing error;
- `success_5d`;
- `success_10d`, the main supplementary event-timing threshold;
- `success_15d`;
- reference magnitude;
- reconstructed matched-event magnitude;
- signed magnitude error;
- absolute magnitude error; and
- normalized absolute magnitude error divided by yearly `Q95-Q05` when valid.

Magnitude is a metric after assignment and is independent of event identity and
timing matching.

The following are not headline metrics in v1.0:

- extra reconstructed peak count;
- false-positive bloom rate;
- reconstructed peak-count accuracy; and
- spring-versus-summer dominance classification.

## 7. Frozen spline settings and analysis boundary

Do not retune the spline. If real event performance is explicitly authorized
later, use the already frozen actual-mask outer-fold selections:

| Outer year | Smoothing |
|---|---:|
| 2019 | 10 |
| 2020 | 100 |
| 2021 | 100 |
| 2022 | 10 |
| 2023 | 10 |
| 2024 | 3 |
| 2025 | 10 |

Protocol v1.0 implementation stops after unit/integration tests and a
reference-only preflight. Do not calculate real reconstruction event recovery,
run controlled-gap performance, inspect Vombsjön, rank methods, or produce
interpretive event figures in this freeze task.

## 8. Change control

Any change to the detector, thresholds, plateau rule, candidate definition,
matching objective, eligibility window, metric definitions, or frozen
reference regression targets requires a new protocol version. Because the
analysis is secondary/exploratory, later results must remain labelled as such.
