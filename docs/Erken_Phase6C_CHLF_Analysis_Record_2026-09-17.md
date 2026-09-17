# Erken Phase 6C Sentinel-2–CHLF analysis record — 2026-09-17

## 1. Execution identity

The analysis was executed only after the Phase 6C protocol and configuration
were committed and pushed. The final run started from clean commit
`dc74167b503360f988c45831696da1be67586cb2`, after the Phase 6B unified
selection-table identity guard was added.

The complete machine-readable provenance is
`results/phase6c/erken_s2_chlf_analysis_manifest.json`. Its SHA256 is
`e1ba8553d67eacffb11e8d0cb52eb99af2859fffc563d69ada3aca33130ab731`.
All six CSV products and all four figures were reproduced byte-for-byte in an
independent rerun; only the manifest changed between the two runs because it
records the newer implementation commit.

No observation threshold, QA rule, spatial support, index definition or
atmospheric-correction setting was changed. No reconstruction or TIMESAT run
was executed, and Vombsjön was not accessed.

## 2. Matchup support

The complete audit retains 2,778 rows: 926 frozen dates × L1C, official L2A
and ACOLITE. Exact-same-date, finite, open-water, method-specific eligible
pairs are:

| Method | NDCI | MCI |
|---|---:|---:|
| L1C | 269 | 269 |
| L2A | 266 | 270 |
| ACOLITE | 223 | 224 |

The primary fair comparison uses identical dates across all three methods:

- NDCI: 215 dates;
- MCI: 220 dates.

No nearest-date or interpolated CHLF matchup was used.

## 3. Primary common-support results

Spearman rho between raw CHLF and the index is primary. Brackets give the
95% calendar-year cluster-bootstrap interval. Pearson correlation uses
log10(CHLF). LOYO RMSE and R² are from the pre-specified one-index linear model
and are expressed/evaluated in log10-CHLF space.

| Index | Method | n | Spearman rho [95% CI] | Pearson r | LOYO RMSE | LOYO R² |
|---|---|---:|---:|---:|---:|---:|
| NDCI | L1C | 215 | 0.162 [-0.015, 0.299] | 0.301 | 0.386 | 0.063 |
| NDCI | L2A | 215 | 0.200 [0.024, 0.356] | 0.020 | 0.422 | -0.123 |
| NDCI | ACOLITE | 215 | 0.214 [0.044, 0.377] | 0.290 | 0.389 | 0.050 |
| MCI | L1C | 220 | 0.413 [0.247, 0.545] | 0.472 | 0.352 | 0.211 |
| MCI | L2A | 220 | 0.510 [0.333, 0.610] | 0.519 | 0.346 | 0.237 |
| MCI | ACOLITE | 220 | 0.458 [0.295, 0.610] | 0.492 | 0.347 | 0.231 |

## 4. Interpretation

MCI contains a clearer and more consistent same-day CHLF signal than NDCI in
this Erken station-neighbourhood dataset. All three MCI variants have moderate
positive rank and log-linear associations, and their simple LOYO models retain
positive out-of-sample R² of approximately 0.21–0.24.

This is useful observation-layer evidence, but it is not a strong absolute
retrieval result. Most held-out log10-CHLF variance remains unexplained, and
the one-index models do not include independent optical or ecological
covariates.

NDCI associations are weak and less stable. The L1C Spearman interval includes
zero. L2A NDCI has near-zero pooled Pearson correlation and negative LOYO R².
The frozen common-support data contain three L2A NDCI medians outside the
nominal theoretical range below -1 (`2020-02-23`, `2024-10-04` and
`2025-10-19`). They were retained because the already-frozen protocol treats
the corresponding index-range diagnostic as non-exclusionary. No post-hoc
outlier removal or threshold change was made.

The three MCI uncertainty intervals overlap substantially. Therefore these
results do not support declaring L1C, L2A or ACOLITE the uniquely superior
processor. L2A and ACOLITE have very similar LOYO MCI errors, while L1C is only
slightly higher; those differences are descriptive and were not subjected to
a pre-specified paired superiority test.

## 5. Temporal heterogeneity

Annual rank associations vary materially. NDCI is negative in 2023 for all
three methods (rho from -0.53 to -0.43) and is close to zero in several later
year/method combinations. MCI remains positive in every method-year, but its
strength ranges from weak (for example ACOLITE 2021 rho = 0.125 and L2A 2022
rho = 0.149) to strong (ACOLITE 2025 rho = 0.785).

The pre-2023 versus 2023-onward sensitivity also differs by index and method.
This may reflect ecological, measurement-regime, atmospheric or sampling
differences. The broad regime label is not a randomized instrument change, so
the pattern must not be assigned a causal mechanism.

## 6. Scientific conclusion at this gate

The defensible Phase 6C conclusion is that same-day station-neighbourhood MCI
contains moderate but incomplete information about Erken CHLF across all three
reflectance sources. NDCI contains weaker and more temporally unstable
information. Phase 6C does not justify processor selection or a transferable
absolute Chl-a retrieval equation. Any later model expansion or sensitivity
analysis requires a separately frozen protocol and must retain the current
confirmatory results unchanged.

## 7. Post-analysis processing-baseline governance

Phase 6C pooled products from multiple Sentinel-2 processing baselines and did
not estimate or apply a cross-baseline correction. The pooled associations
remain valid as the frozen exploratory results actually calculated, but they
must not be interpreted as evidence that processing-baseline effects are
absent or as a causal estimate of such effects.

Decision 019 and
`Erken_Sentinel2_Processing_Baseline_Control_Protocol_v1.0.md` now govern this
issue. The exact baseline and B4/B5/B6 reflectance provenance must be audited
before any later baseline-adjusted analysis. Empirical correction is forbidden
without same-acquisition products processed under distinct baselines. This
governance addendum does not alter any Phase 6C data product or result.
