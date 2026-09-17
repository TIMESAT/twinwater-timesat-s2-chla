# Erken Sentinel-2 Processing-Baseline Control Protocol v1.0

**Status: FROZEN before the processing-baseline audit and before any empirical
cross-baseline correction.**

## 1. Purpose

This protocol governs the Sentinel-2 processing-baseline changes represented
in the Erken L1C, official L2A/Sen2Cor and ACOLITE observation layers. A
processing baseline is part of the measurement-generating process. It is not
treated as an optional sensitivity label or replaced by calendar year.

This control is additive. It does not overwrite the frozen Phase 6A/6B
products or the already reported Phase 6C results. Phase 6C remains a pooled,
exploratory observation-layer analysis and must not be interpreted as a causal
estimate of a processing-baseline effect.

## 2. Authoritative product context

Copernicus Sentinel-2 Collection-1 reprocessed the historical L1C and L2A
archive to provide a consistent time series with updated calibration,
geometry, product format and, for L2A, processing algorithms. The governed
Collection-1 acquisition windows are:

- PB 05.00 (`N0500`): 2015-07-04 through 2021-12-31;
- PB 05.10 (`N0510`): 2022-01-01 through 2023-12-13;
- PB 05.11 (`N0511`): a small number of exceptional historical products.

PB 05.10 entered nominal operations on 2023-12-13. PB 05.11 entered nominal
operations on 2024-07-23. The exact product baseline remains authoritative at
the row level; the dates above do not license replacing product metadata with
a date-only classification.

`processing_baseline` and generation timing are distinct provenance axes. The
audit records both the exact baseline and generation lag. A product generated
within 30 days of sensing is labelled `near_sensing_generation`; a longer lag
is labelled `delayed_generation`. These labels describe the local archive and
do not replace the official baseline.

Official references:

- <https://sentiwiki.copernicus.eu/web/s2-processing>
- <https://sentiwiki.copernicus.eu/web/s2-products>

## 3. Existing radiometric conversion

Phase 6A already converts L1C and L2A digital numbers to physical reflectance
using the product's own metadata:

```
reflectance = (DN + add_offset) / quantification_value
```

L1C uses `RADIO_ADD_OFFSET`; L2A uses `BOA_ADD_OFFSET`. At PB `N0400` or later,
the required offset metadata must be present and usable. Its absence is a
failure and is never interpreted as a zero offset. Negative physical
reflectance is preserved and not clipped.

ACOLITE remains a separate `rhos` reflectance quantity. Its output GeoTIFF
scale and offset are applied during extraction, and its source L1C processing
baseline is retained. L1C TOA, official L2A BOA and ACOLITE `rhos` are not
pooled into one numerical reflectance scale.

## 4. Baseline audit

The audit uses the frozen 3×3, 20 m support and retains B4, B5 and B6
reflectance counts and summaries for every available method observation. It
records:

- source product and acquisition identity;
- exact processing baseline;
- sensing time, generation time and generation lag;
- official Collection-1 or nominal-operational context;
- L1C/L2A paired-baseline consistency;
- B4/B5/B6 valid counts, median, mean, SD, IQR, minimum and maximum;
- the already applied metadata-derived radiometric conversion status.

An exact L1C/L2A pair with unequal processing baselines is a hard audit
failure. An available product without a parseable baseline is also a hard
failure. ACOLITE must retain the baseline of its exact source L1C product.

## 5. Empirical harmonization gate

Band reflectances can diagnose a baseline transition, but they do not by
themselves identify a cross-baseline correction. Lake-water reflectance varies
with season, atmosphere and ecological state. Estimating a baseline adjustment
from non-overlapping years could remove a real ecological change.

An empirical correction is therefore forbidden unless the archive contains
the same acquisition identity processed under at least two distinct baselines.
Acquisition identity is platform, sensing datetime, relative orbit and MGRS
tile. A later correction would require a separately frozen paired-
harmonization protocol and must be specific to product level, reflectance
quantity, platform and band as supported by the paired evidence.

CHLF, calendar year and sensing date cannot define or tune a processing-
baseline correction. A same-baseline duplicate is useful for reproducibility
but does not identify a cross-baseline transformation.

When no same-acquisition cross-baseline pair exists, the mandatory outcome is:

`HOLD_EMPIRICAL_HARMONIZATION_NOT_IDENTIFIABLE`

This HOLD is not a data-processing failure. It prevents an unsupported
correction while preserving the correctly metadata-scaled reflectances and
the exact baseline strata.

## 6. Phase 6C protection and stopping rule

The Phase 6C manifest and every output hash it governs must remain byte
identical. This audit does not read CHLF, recompute association or LOYO
results, rank processors, run reconstruction or TIMESAT, or access Vombsjön.

The audit stops after writing baseline provenance, reflectance summaries and
the harmonization gate. A future baseline-adjusted scientific analysis
requires a new frozen protocol; it cannot silently replace the published
Phase 6C tables.
