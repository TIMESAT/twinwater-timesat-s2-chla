# Erken Sentinel-2 date-level SCL observation mask

## Scope

Phase 2A-3 defines the Sentinel-2 observation process for Lake Erken. It uses
only the committed L2A Scene Classification Layer (SCL) summaries. No CHLF,
reflectance, NDCI, MCI, atmospheric-correction performance, chlorophyll
retrieval, temporal reconstruction, or Vombsjön result was inspected or used
to choose the rule.

The primary interval is 2019-04-17 through 2025-11-30 inclusive. Phase 2A-2
already froze the spatial support at a station-centred 3×3 neighborhood of
20 m SCL pixels (60×60 m). The 1×1 and 5×5 windows remain sensitivity cases;
this analysis does not reopen the ROI decision.

## Validated input domain

The primary interval contains 950 products on 926 unique calendar dates.
Twenty-four dates contain two products, and no date contains more than two.
All 950 primary products have `processing_status == ok`, place the station
inside the raster, have a complete 3×3 window, contain exactly nine classified
pixels, and contain no unexpected SCL code. The platforms are S2A (415), S2B
(474), and S2C (61); processing baselines are N0500 (367), N0509 (1), N0510
(344), and N0511 (238).

The archive-level exact acquisition-datetime/tile warning is retained: two
products form one exact duplicate group outside the primary interval. There is
no such group in the primary interval. No product is silently removed.

## SCL taxonomy and observed 3×3 states

Water is SCL class 6. Obvious-bad classes are 0, 1, 3, 8, 9, 10, and 11.
Persistent non-water diagnostic classes are 4, 5, and 7. Class 2 remains a
separate category.

Only 18 combinations of centre class and the four integer count categories
occur in the 950 primary 3×3 rows. The dominant states are:

- nine obvious-bad pixels: 340 products;
- nine water pixels: 306 products;
- additional nine-bad-pixel states distinguished by centre class: class 8
  (175), class 10 (69), and class 11 (33);
- eight water plus one obvious-bad pixel: 7 products;
- seven water plus two obvious-bad pixels: 3 products;
- five water plus four obvious-bad pixels: 3 products.

The full discrete state table is
`results/tables/erken_s2_scl_3x3_state_frequency.csv`. No class-2 pixel occurs
in a primary 3×3 window. Persistent non-water pixels occur only in rare states
with three such pixels, not as an isolated single pixel. These facts explain
why some configured sensitivity rules are empirically equivalent: arbitrary
fine decimal thresholds would not represent independent choices in a
nine-pixel window.

## Pre-specified rule sensitivity

The compact candidate set changes one interpretable component at a time:

- obvious-bad allowance: 0, 1, or 2 pixels;
- water context: at least 5, 7, 8, or 9 of 9 pixels;
- centre treatment: centre is water versus centre is not obvious bad;
- persistent non-water allowance: zero versus one pixel;
- class-2 allowance: zero versus one pixel.

All rules retain zero persistent non-water and zero class-2 pixels except the
two explicit one-factor sensitivity cases. Because the four count categories
partition all nine pixels, some settings collapse to the same realized rule.
For example, water ≥5 with zero bad, persistent, and class-2 pixels is
effectively 9/9 water; water ≥5 and water ≥7 are equivalent when at most two
bad pixels and no other category are allowed.

The principal comparison is:

| Rule | Passing products | Usable dates | Median interval | Maximum gap | Gaps >10 / >20 / >30 / >45 d |
|---|---:|---:|---:|---:|---:|
| Strict diagnostic: 9/9 water | 306 | 301 | 5 d | 120 d | 58 / 16 / 8 / 4 |
| Preferred: ≤1 bad, ≥8 water | 313 | 307 | 5 d | 120 d | 57 / 15 / 8 / 4 |
| Relaxed: ≤2 bad, ≥7 water | 316 | 310 | 5 d | 120 d | 57 / 15 / 7 / 4 |

The strict rule loses six dates relative to the preferred rule because of one
edge pixel. The relaxed rule gains only three additional dates while allowing
two of nine pixels to be obvious-bad. Typical interval and long-gap behavior
are effectively unchanged. The evidence therefore does not support either a
fragile all-water requirement or the extra contamination allowed by the
relaxed rule.

Requiring the centre to be water or merely not obvious-bad gives identical
results in the current data. The latter is frozen because it encodes the
scientific intent not to create centre-classification-dependent missingness;
under the other primary thresholds, every currently passing centre is water.
Allowing one persistent non-water pixel or one class-2 pixel also changes no
current decision. Their primary allowances remain zero as conservative,
explicit rules rather than being relaxed for an unavailable count benefit.

## Frozen product-level rule

Rule ID:
`scl3x3_b1_w8_centernotbad_p0_class2zero_v1`.

A product passes when all of the following hold in the frozen 3×3 window:

- obvious-bad pixel count ≤1;
- water pixel count ≥8;
- centre pixel is not an obvious-bad class;
- persistent non-water pixel count is 0;
- class-2 pixel count is 0.

The definition and date-collapse ranking are versioned in
`config/erken_s2_observation_mask.yaml`; the Python module does not hide a
second rule definition.

## Calendar-date collapse

The temporal observation unit is a unique calendar date, not a product. All
products remain in the product QC table for provenance. A date is usable when
at least one product on that date passes the frozen product rule. Two passing
same-day products still produce one temporal observation.

When multiple products pass, one representative is selected for provenance in
this deterministic order:

1. lowest 3×3 obvious-bad fraction;
2. highest 3×3 water fraction;
3. lowest 3×3 persistent non-water fraction;
4. prefer centre SCL class 6;
5. earliest acquisition datetime;
6. lexical product ID.

The representative product does not alter the date-level any-product-passes
decision. Of the 24 multi-product dates, five are rescued because one product
passes and another fails, six have two passing products, and thirteen have no
passing product. The complete resolution audit is
`results/tables/erken_s2_same_day_product_resolution.csv`.

## Final mask and temporal availability

The frozen rule passes 313 of 950 products (32.95%) and retains 307 of 926
calendar dates (33.15%). Annual usable-date counts are:

| Year | Candidate dates | Usable dates | First usable | Last usable |
|---|---:|---:|---|---|
| 2019 | 96 | 35 | 2019-04-17 | 2019-12-05 |
| 2020 | 134 | 56 | 2020-01-19 | 2020-11-22 |
| 2021 | 137 | 48 | 2021-02-27 | 2021-12-17 |
| 2022 | 134 | 38 | 2022-03-24 | 2022-12-09 |
| 2023 | 136 | 36 | 2023-01-01 | 2023-11-29 |
| 2024 | 136 | 41 | 2024-03-28 | 2024-11-28 |
| 2025 | 153 | 53 | 2025-01-20 | 2025-11-26 |

Across all usable dates, the median interval is 5 days (Q25 3 days, Q75 10
days). The maximum inter-observation gap is 120 days, from 2023-11-29 to
2024-03-28. There are 57 gaps longer than 10 days, 15 longer than 20 days, 8
longer than 30 days, and 4 longer than 45 days. These include seasonal/winter
availability structure and are descriptive observation-process properties,
not reconstruction experiments.

The preferred product pass fractions are 33.7% for S2A, 33.1% for S2B, and
26.2% for S2C. Baseline-specific values range from 27.0% (N0510) to 37.9%
(N0500), excluding the single N0509 product. These strata are strongly
confounded with acquisition year and season. More importantly for rule
selection, movement from strict to preferred to relaxed changes platform and
baseline pass fractions only slightly, and annual preferred counts remain
between the strict and relaxed counts with differences of at most a few dates.
There is no qualitative platform, baseline, or year-specific reversal that
would justify a different primary rule.

## Frozen spatial sensitivity check

Count thresholds were scaled conservatively by pixel fraction for the already
defined 1×1 and 5×5 sensitivity windows. For the preferred rule this yields:

| Window | Effective rule | Passing products | Usable dates | Median interval | Maximum gap |
|---|---|---:|---:|---:|---:|
| 1×1 | water centre; no bad/other pixel | 322 | 315 | 5 d | 120 d |
| 3×3 | ≤1 bad; ≥8 water | 313 | 307 | 5 d | 120 d |
| 5×5 | ≤2 bad; ≥23 water | 300 | 295 | 5 d | 120 d |

The usable-date count shifts by +8 dates for 1×1 and −12 dates for 5×5, but
the median and maximum gap behavior and the qualitative strict/preferred/
relaxed ordering remain stable. This sensitivity does not change the
scientific conclusion and does not reopen the frozen 3×3 primary ROI.

## Outputs and reproducibility

Run from the repository root:

```bash
python scripts/05_erken_s2_observation_mask.py
```

The primary output is
`data/processed/erken_s2_observation_mask.csv`, with exactly one row per
inventory date in the primary interval. Product QC, discrete-state,
candidate-rule, annual, monthly, stratified, same-day, input-audit, and spatial
sensitivity tables are written under `results/tables/`. Five observation-only
diagnostic figures are written as PNG and PDF under `results/figures/`.

## Limitations and next boundary

SCL is a categorical scene classifier, not an inland-water optical quality
guarantee. This mask rejects obvious cloud/shadow/cirrus/snow classes and
requires local water context, but it does not assess glint, adjacency effects,
sub-pixel shore influence, atmospheric-correction suitability, reflectance
quality, or retrieval quality. The apparent platform/baseline differences are
descriptive and temporally confounded.

Satellite QC usability and Erken open-water/reference eligibility must remain
separate fields in the next phase. Before sampling daily CHLF, the next step
must implement and audit a deterministic date join between this mask and the
canonical Erken daily table, explicitly retain the SCL-usable versus
open-water/reference-eligible distinction, and specify the handling of any
missing daily reference value. No TIMESAT input has been validated by this
phase, and no reconstruction should begin from these outputs alone.
