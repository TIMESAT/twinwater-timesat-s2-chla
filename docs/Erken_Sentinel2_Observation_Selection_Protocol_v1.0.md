# Erken Sentinel-2 Observation Selection Protocol v1.0

**Status: FROZEN before CHLF inspection and field-matchup analysis.**

## 1. Purpose and scope

This protocol freezes the post-extraction observation-selection rule for the
Erken Sentinel-2 L1C, official ESA L2A/Sen2Cor and ACOLITE observation layers.
It consumes only the committed Phase 6A and Phase 6B QA and index products.

This protocol does not inspect CHLF, calculate index-versus-field performance,
rank atmospheric-correction processors, run a reconstruction, alter Phase
3/4/5 results, or access Vombsjön.

The historical Phase 6A and ACOLITE extraction configurations and provenance
manifests remain unchanged. They accurately record the pre-freeze extraction
runs. The post-pilot selection is governed separately by
`config/erken_s2_observation_selection_v1.0.yaml`.

## 2. Evidence used for the freeze

The decision uses only pre-specified QA attrition at 9/9, at least 8/9, at
least 6/9 and at least 5/9 in the frozen 3×3 window. CHLF, field correlation,
retrieval error, reconstruction performance and visual preference were not
used.

For the 306 exact Phase 6A L1C pairs, ACOLITE retains 223 common-B456
observations at 9/9, 226 at at least 8/9, 234 at at least 6/9 and 235 at at
least 5/9. Moving from at least 6/9 to at least 5/9 therefore adds only one
ACOLITE observation. For the Phase 6A L1C and L2A products, at least 6/9 and
at least 5/9 retain identical counts for NDCI, MCI and common-B456 support.

## 3. Frozen primary valid-pixel rule

The frozen rule identifier is `erken_s2_primary3x3_min6_v1`.

- The primary support remains the station-centred 3×3 window on the 20 m grid.
- The window contains nine pixels.
- An index observation is eligible only when at least six required pixels pass
  the already-defined pixel-level radiometry, QA and index-validity rules.
- The same threshold applies to L1C, L2A and ACOLITE.
- NDCI eligibility uses `NDCI_valid_pixel_count >= 6`.
- MCI eligibility uses `MCI_valid_pixel_count >= 6`.
- Same-product B4/B5/B6 support uses `common_B456_valid_count >= 6`.
- The primary value remains the median of the surviving pixel-level index
  values. Invalid pixels are not filled and do not enter the median.
- Rows below the threshold remain in the audit table and are marked
  ineligible. They are never silently deleted.

The 1×1, 5×5, 7×7 and 11×11 products remain secondary spatial-sensitivity
outputs. They do not define observation eligibility.

## 4. QA-family and diagnostic-flag freeze

Validity-contributing QA families required by the extraction configuration
must be present and readable. If one is absent or unreadable, the affected
method observation and its index metrics are unavailable. The pipeline must
not assume that an absent QA family is clean.

Optional or legacy QA families that do not contribute to the configured
validity mask remain inventory/provenance only. Their absence is recorded and
does not independently reject an observation.

The existing diagnostic degradation flags remain diagnostic. No diagnostic
flag is promoted to a hard reject in this freeze. Existing hard-invalid flags
for Phase 6A and ACOLITE remain unchanged.

## 5. MCI wavelengths

MCI continues to use the fixed nominal wavelengths B4 = 665 nm, B5 = 705 nm
and B6 = 740 nm. Platform-specific wavelengths remain recorded reference
metadata and are inactive. This freeze does not recompute historical index
values.

## 6. Unified selection table

The deterministic output is
`results/phase6b/observation_selection/erken_s2_observation_selection.csv`.
It contains one row for each of the 926 frozen Phase 6A candidate dates and
each of the three methods, for exactly 2,778 rows.

Every row retains source alignment, product availability, required-QA status,
source failure reason, valid-pixel counts, available index medians and separate
NDCI, MCI and common-B456 selection statuses. Missing, ambiguous, technically
unavailable and below-threshold observations remain explicit.

The 306 exact L1C/L2A/ACOLITE source alignments are labelled for later fair
method comparison. This label does not itself make a metric eligible; the
metric-specific 6/9 rule must also pass. No all-method common-support
intersection or processor ranking is defined here.

## 7. Reproducibility and stopping rule

The machine-readable manifest records hashes of the frozen config and every
input table, the repository commit used to generate the table, row counts and
eligibility counts. The generator rejects any governed input containing CHLF
or `PRESENCE_ICE`.

Completion of this table authorizes preparation for the later field-matchup
stage. It does not itself authorize CHLF inspection, scientific processor
ranking, retrieval calibration, reconstruction or TIMESAT execution.
