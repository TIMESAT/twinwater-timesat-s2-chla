# Lake Erken Sentinel-2 SCL spatial-window diagnostic

## Scope and reproducibility

This Phase 2A-2 analysis selects a spatial neighborhood for later Sentinel-2 observation-quality assessment. It does not define a usable acquisition, apply a water-fraction or bad-SCL cutoff, or use chlorophyll, reflectance, NDCI, MCI, atmospheric-correction, interpolation, or retrieval-performance information.

The analysis was run on 2026-09-01 from source commit `adfa6fbfaba83a3a0c9b3a2a8d6ad38f2e693646` using:

- `data/processed/erken_s2_l2a_inventory.csv`;
- `data/processed/erken_s2_scl_scene_summary.csv`;
- `python scripts/04_erken_s2_scl_roi_analysis.py`.

The inclusive primary interval is the Erken reference-record overlap, 2019-04-17 through 2025-11-30. Products before and after it remain in separate summaries. The analysis unit is an acquisition product, not a calendar date; same-date products are retained.

## Validation and analysis rules

A product/window row is valid when its processing status is `ok`, the station is inside the raster, the requested window is complete, the actual and requested pixel counts match, the SCL fractions are finite, and no unexpected SCL value occurs. Every product must have exactly one row for each of 1×1, 3×3, 5×5, 7×7, and 11×11. Product identity and acquisition metadata must agree between the inventory and scene/window tables.

The existing Phase 2A obvious-bad diagnostic comprises SCL classes `{0, 1, 3, 8, 9, 10, 11}`. Water is class 6. For this note:

- “dominated by non-water” means `water_fraction < 0.50`; this descriptive category includes clouds and is not a land diagnostic or a proposed threshold;
- “persistent non-water diagnostic” means vegetation, not-vegetated, or unclassified pixels (classes `{4, 5, 7}`);
- class 2 is kept separate because its meaning differs across processing baselines;
- all quoted `>= 0.50`, `>= 0.75`, `>= 0.90`, `>= 0.95`, and `== 1.00` frequencies are descriptive only.

## Inventory quality control

The archive contains 1,361 L2A products and 6,805 product/window rows spanning 2017-01-14 through 2026-08-25. All 1,361 products have an SCL raster, all five windows are complete and inside the raster, and all inventory and scene/window statuses are `ok`. No unexpected class value, missing diagnostic, clipped window, invalid coordinate, or class-count inconsistency was found.

There are 950 products in the primary overlap, 280 before it (2017-01-14 through 2019-04-14), and 131 after it (2025-12-03 through 2026-08-25). Forty-one acquisition dates contain two products (82 products total): 24 duplicated dates are in the primary interval, one is before, and 16 are after. One pre-reference pair has the same acquisition time and tile but different product-generation suffixes (2018-06-26); it is flagged and retained rather than silently deduplicated. The other same-date pairs are distinct acquisitions.

Full-archive platform counts are S2A 595, S2B 660, and S2C 106. Primary-overlap counts are 415, 474, and 61, respectively. Every product is tile `T34VCM`. Full-archive processing-baseline counts are N0500 647, N0509 1, N0510 344, N0511 254, and N0512 115; N0512 occurs only after the reference interval. The primary interval contains N0500 367, N0509 1, N0510 344, and N0511 238.

All rasters have one grid signature: EPSG:32634, 20 m pixels, 5,490 × 5,490 cells, affine origin `(300000, 6700020)`, and station row/column `(3200, 3347)`. There is no suspicious CRS, transform, resolution, dimension, or station-location change over time. Every product has two SCL raster candidates, consistently resolved by the extractor.

## Primary-overlap window results

The marginal distributions are strongly bimodal because clouds, cirrus, and snow/ice often cover the entire local neighborhood. Consequently, every window has median water fraction 0, water Q05/Q25 of 0, water Q75/Q95 of 1, minimum 0, median bad-SCL fraction 1, bad Q05/Q25 of 0, bad Q75/Q95 of 1, and maximum 1. These values describe acquisition conditions and do not show that the station is spatially non-water.

The more discriminating spatial comparison conditions on the 322 acquisitions whose centre pixel is SCL water:

| Window | Footprint | Water ≥ 0.50 | Water = 1.00 | Any bad pixel | Dominated by non-water | Centre-water Q05 | Centre-water window all water | Any persistent non-water |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1×1 | 20 m | 33.89% | 33.89% | 66.11% | 66.11% | 1.000 | 100.00% | 0.00% |
| 3×3 | 60 m | 34.00% | 32.21% | 67.68% | 66.00% | 1.000 | 95.03% | 0.21% |
| 5×5 | 100 m | 33.89% | 30.84% | 69.05% | 66.11% | 0.840 | 90.99% | 0.42% |
| 7×7 | 140 m | 34.11% | 29.89% | 70.00% | 65.89% | 0.777 | 88.20% | 0.42% |
| 11×11 | 220 m | 34.21% | 28.42% | 71.47% | 65.79% | 0.672 | 83.85% | 0.63% |

The complete quantiles and diagnostic threshold frequencies are in `results/tables/erken_s2_scl_window_summary.csv`. Across centre-water acquisitions, expansion from 1×1 to 3×3 lowers water fraction in 4.97%; the adjacent reductions occur in 6.52% for 3×3 to 5×5, 9.94% for 5×5 to 7×7, and 14.60% for 7×7 to 11×11. The centre-water Q05 remains 1.0 at 3×3, then falls to 0.840, 0.777, and 0.672. Thus 3×3 adds an eight-neighbor context without measurable lower-tail deterioration at Q05; larger footprints increasingly mix cloud edges or other classes into otherwise water-centred acquisitions.

Persistent classes are uncommon: they occur in 2, 4, 4, and 6 of 950 acquisitions for 3×3, 5×5, 7×7, and 11×11. Pixel-weighted persistent-class fractions remain below 0.09% in every window; class 7 and class 2 never occur. The 11×11 window nevertheless contains isolated cautionary cases, including a centre-water acquisition on 2025-09-04 with 20.66% vegetation/not-vegetated pixels and a centre-cirrus acquisition on 2023-09-23 with 53.72% not-vegetated pixels. These events could reflect classification artifacts, transient local features, or genuine land/vegetation influence. They are not a temporally persistent signature and cannot be attributed specifically to Malma Island or shoreline geometry from SCL alone. The SCL evidence therefore does not prove that 7×7 or 11×11 intersects Malma, but the 11×11 footprint is less spatially conservative and adds avoidable heterogeneous cases.

## Central pixel and temporal stability

The station-centre pixel is water in 322/950 acquisitions (33.89%). Every non-water centre classification is an obvious-bad class: medium-probability cloud 180 (18.95%), high-probability cloud 340 (35.79%), thin cirrus 74 (7.79%), and snow/ice 34 (3.58%). No centre pixel is class 0–5 or 7. The centre is therefore stable as pelagic water with respect to persistent land-like classes; its frequent non-water state is atmospheric/seasonal contamination, not evidence of an incorrectly located land pixel.

The fraction of all-water windows varies by acquisition year and season, but the ordering with window size is consistent. At 3×3 it ranges from 25.0% in 2023 to 41.0% in 2020. The 1×1 all-water fraction by month is lowest in December (12.1%) and roughly 18% in January–March, reaches 53.9% in June, then decreases through autumn. This strong seasonal pattern shows why cloudy or snow/ice scenes must not be interpreted as spatial ROI failure.

At 3×3, all-water fractions are 33.3% for S2A, 32.1% for S2B, and 26.2% for S2C; S2C has only 61 primary-interval products and occurs late in the record. Corresponding baseline values are 37.1% for N0500, 100% for the single N0509 product, 26.2% for N0510, and 33.2% for N0511. Baseline is confounded with year, season, platform availability, and reprocessing history, so these descriptive differences do not establish a processing-baseline effect. No baseline changes the raster grid, and class 2 is absent. Processing baseline therefore does not materially change the 3×3 spatial recommendation, although it remains provenance for later threshold sensitivity checks.

The 280 pre-reference and 131 post-reference acquisitions show the same broad pattern: increasing window size reduces the fraction of all-water windows, with no contrary spatial regime. They are reported separately and are not used to select the primary ROI.

## ROI recommendation

**Preferred primary spatial window: 3×3 SCL pixels (60 m across, 30 m from centre to footprint edge).** It is the smallest candidate that supplies a genuine local water context rather than a single-pixel label. Among centre-water acquisitions, 95.03% remain entirely water and Q05 remains 1.0, while persistent land-like classes occur in only 0.21% of acquisitions.

**Sensitivity windows: 1×1 and 5×5.** The 1×1 result tests sensitivity to a single central SCL pixel but is too fragile to represent local context. The 5×5 result tests modest spatial expansion; its centre-water Q05 already falls to 0.84 and only 90.99% remain all water, so it should not replace 3×3 without a later, explicit benefit.

**Not recommended as primary windows: 7×7 and 11×11.** They add little evidence of better local robustness while increasing centre-water contamination and reducing the lower tail. The 11×11 case has the clearest isolated vegetation/not-vegetated incursions. This is an SCL-based spatial precaution, not proof of Malma or shoreline intersection.

This recommendation freezes only the candidate spatial neighborhood for the next QC-design step. The final observation-usability mask is not frozen. In particular, this analysis does not require 100% water, select a maximum `bad_scl_fraction`, decide how water and bad fractions interact, or determine special treatment of snow/ice, class 2, mixed classes, or same-date acquisitions.

## Outputs and limitations

The script writes:

- principal window statistics and outside-reference summaries;
- year, month, platform, and baseline summaries;
- paired adjacent-window changes;
- centre-pixel class frequencies;
- inventory QC metrics;
- five diagnostic figures in PNG and PDF.

SCL is a categorical Sen2Cor diagnostic, not water reflectance or chlorophyll truth. The archive is not balanced across months, platforms, years, or processing baselines. Baseline groups are observationally confounded, S2C has limited overlap, and the single N0509 product cannot support a group conclusion. The analysis has no shoreline polygon, island-distance calculation, or per-pixel directional map, so it cannot identify Malma geometrically. A later threshold analysis must keep product-level acquisition identity, use the selected 3×3 neighborhood, evaluate plausible water/bad tolerances without optimizing against chlorophyll retrieval performance, and retain 1×1/5×5 spatial sensitivity checks.
