# Erken Phase 6A real-data QA review record — 2026-09-17

> **Status: evidence record; not a scientific freeze.**
>
> This document records the completed Phase 6A QA-only real-data run and the
> observation-filtering rules that were already implemented when it ran. It
> does not select the final minimum valid-pixel threshold, amend the draft
> Phase 6A protocol, inspect CHLF, rank L1C against L2A, or authorize field
> matchup or reconstruction analysis.

## 1. Authoritative sources

- Governing draft protocol:
  [`Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md`](Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md)
- Machine-readable draft configuration:
  [`erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml`](../config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml)
- Frozen upstream observation-mask rule:
  `scl3x3_b1_w8_centernotbad_p0_class2zero_v1`
- Run provenance:
  [`erken_real_s2_pilot_provenance.json`](../results/phase6a/erken_real_s2_pilot_provenance.json)
- QA findings and attrition evidence:
  [`erken_real_s2_qa_findings.md`](../results/phase6a/qa/erken_real_s2_qa_findings.md) and
  [`erken_real_s2_qa_attrition.csv`](../results/phase6a/qa/erken_real_s2_qa_attrition.csv)
- Pairing and failure audits:
  [`erken_l1c_l2a_pairing_audit.csv`](../results/phase6a/erken_l1c_l2a_pairing_audit.csv) and
  [`erken_real_s2_pilot_failures.csv`](../results/phase6a/erken_real_s2_pilot_failures.csv)

The real-data run completed at `2026-09-17T12:02:57Z` on Linux using
Python 3.11.15, NumPy 1.26.4 and Rasterio 1.3.10. The recorded runtime commit
is `9baf3dcb8575b796ea1021b3c18284519bc699c5`; the real-data products were
committed in `74a3ae2` and subsequently merged to `main` in `02097c3`.

## 2. Reproducible observation-filtering sequence

The following stages must remain distinct in the manuscript and analysis.

### 2.1 Frozen date/product eligibility

The initial inventory contains 926 candidate calendar dates. The previously
frozen 3×3 L2A SCL rule selected 307 representative L2A dates and selected no
representative product for the other 619 dates. Those 619 dates are upstream
SCL-gate exclusions, not post-hoc reflectance or index outlier deletion.

The frozen 3×3 rule requires:

- at most one obvious-bad SCL pixel;
- at least eight water pixels;
- a centre pixel that is not an obvious-bad class;
- zero persistent non-water pixels (SCL classes 4, 5 and 7); and
- zero class-2 pixels.

No reflectance, NDCI, MCI, CHLF or downstream performance value influenced
this selection.

### 2.2 Deterministic L1C/L2A pairing

Of the 307 representative L2A dates, 306 have one exact L1C match based on
platform, sensing time, tile and orbit metadata. On 2019-06-06, two L1C
products share the same acquisition identity. The audit retains both candidate
IDs and does not choose one silently. Consequently, that date is unavailable
for paired L1C/L2A analysis, although its representative L2A product remains
documented.

### 2.3 Pixel-level masking before index calculation

For both L1C and L2A, a target pixel contributes only when the paired L2A SCL
classifies it as water (class 6), the required band values are finite, and no
applicable hard-invalid native QA flag is present. The hard-invalid flags are
`nodata`, `saturated`, `defective`, `msi_lost`, `opaque_cloud`, `cirrus` and
`snow_ice`. Band-specific `MSK_QUALIT` flags remain band-specific;
product-level `MSK_CLASSI` flags and the L2A SCL water context apply to every
band.

NDCI requires valid B4 and B5 pixels and a finite, positive denominator greater
than `1e-6`. MCI requires valid B4, B5 and B6 pixels. Indices are calculated
per pixel before the spatial median is taken.

Negative physical reflectance is retained. NDCI values are not clipped to
`[-1, 1]`, and range anomalies are diagnostic rather than an additional
outlier-deletion rule.

### 2.4 Observations with no valid 3×3 pixels

After pixel QA, 38 product rows, representing both product levels on 19
acquisition dates, have no valid pixels in the frozen 3×3 window. The dominant
full-window native QA condition is opaque cloud on 4 dates, cirrus on 14 dates
and snow/ice on 1 date. These failures are retained explicitly in the failure
audit rather than silently dropped.

### 2.5 Final date-level acceptance at the time of this review

The final minimum number of valid pixels required to accept an observation has
**not** been selected. The QA-only pilot reports the pre-specified alternatives
9/9, at least 8/9, at least 6/9 and at least 5/9:

| Product/index support | 9/9 | ≥8/9 | ≥6/9 | ≥5/9 |
|---|---:|---:|---:|---:|
| L1C NDCI | 281/306 | 286/306 | 286/306 | 286/306 |
| L1C MCI / common B456 | 281/306 | 286/306 | 286/306 | 286/306 |
| L2A NDCI | 274/307 | 281/307 | 283/307 | 283/307 |
| L2A MCI / common B456 | 282/307 | 287/307 | 287/307 | 287/307 |

These counts were evidence for a later human decision; this Phase 6A review
did not declare one threshold scientifically superior. The subsequent
pre-field-matchup freeze selected at least 6/9 using only QA attrition, without
CHLF, index-versus-field performance, reconstruction performance, visual
preference or knowledge of later scientific results. See Decision 017 and
`Erken_Sentinel2_Observation_Selection_Protocol_v1.0.md`.

## 3. Spatial-window interpretation

The 20 m, station-centred 3×3 window remains the primary support. The 1×1,
5×5, 7×7 and 11×11 results are secondary spatial-sensitivity products. They do
not replace the 3×3 result and must not be used to retune the frozen SCL rule or
select the final valid-pixel threshold from downstream performance.

The completed run contains 1,233 product extraction rows and 6,165
spatial-sensitivity rows, exactly five nested windows per extraction row.

## 4. Items resolved by the post-pilot freeze

Decision 017 and the frozen post-pilot protocol resolved these items before
field-matchup analysis:

1. the final minimum valid-pixel threshold;
2. the policy for absent or unreadable native QA families;
3. whether any current diagnostic degradation flag becomes a hard reject; and
4. whether MCI continues to use nominal wavelengths or changes to
   platform-specific wavelengths.

The related documentation-alignment item was resolved at the same freeze.
The current real-data products report `native_qa_incomplete = false` for all
613 processed product rows because the configured validity-contributing
`QUALIT` and `CLASSI` families are present. The native QA inventory separately
records absent optional or legacy families. The final protocol should state
unambiguously whether `native_qa_incomplete` refers only to configured
validity-contributing families or to every inventoried optional family.

## 5. Manuscript reporting constraints

The Methods section should describe the ordered, pre-defined eligibility and
pixel-masking rules above and report the resulting attrition at each stage. It
should not summarize the procedure only as “problematic observations were
removed,” because that would obscure the difference between the frozen SCL
date gate, metadata pairing failure, pixel-level QA and the still-unselected
date-level valid-pixel threshold.

The frozen primary rule may now be reported as at least 6/9 valid pixels in the
3×3 window. Accepted counts must be taken from the unified post-pilot selection
table, which preserves unavailable and below-threshold rows explicitly.

## 6. Checksums of the reviewed evidence

| File | SHA256 |
|---|---|
| `results/phase6a/erken_real_s2_pilot_provenance.json` | `886ab3fe09e32bd613f16d1ac4af6bfd8cfca04509edbe84e63a6ce3f4730927` |
| `results/phase6a/erken_l1c_l2a_pairing_audit.csv` | `7c9209492ebc03fe09aea5004f67d8907ee0fddadbaf7cce40ac1c74cbd3d754` |
| `results/phase6a/erken_real_s2_pilot_failures.csv` | `05b4774fc9d48a9ef740d39f8d18290bf0eee8d6c85f9d2d612b64f8adb08286` |
| `results/phase6a/qa/erken_real_s2_qa_attrition.csv` | `2c1ac727a6f62b320e0dae8c83efbedf8b53cacb08420bf5228246bc6193e84a` |
| `results/phase6a/qa/erken_real_s2_qa_findings.md` | `a8782212d5649138fb0dd0ab4490796edaf19a4f584dd04c841ee440315f07b3` |
| `results/phase6a/spatial_sensitivity/erken_real_s2_product_window_indices.csv` | `c76eb822fe2ca2e2366a33f8cdba9140f77e6ca64ebb3b84fcbb288e93c4eddb` |

No CHLF, field-matchup performance, L1C/L2A scientific ranking or TIMESAT
reconstruction was generated or inspected in preparing this record.
