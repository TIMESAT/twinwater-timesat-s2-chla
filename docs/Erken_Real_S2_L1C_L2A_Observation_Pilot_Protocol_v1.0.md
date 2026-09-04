# Erken real Sentinel-2 L1C / official ESA L2A observation-layer pilot — Protocol v1.0

> **DRAFT — pending human review and freeze.**
>
> Nothing in this document is frozen. It does not amend
> `Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`, the
> `Reconstruction_Analysis_Contract_v1.0.1`, the frozen Erken SCL observation
> mask, the TIMESAT 4.4.1 defaults, or any Phase 3/4/5 output. No decision from
> this protocol has been appended to `docs/decisions.md`.

Machine-readable companion:
`config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml`.

## 1. Scope

Phase 6A builds an auditable real Sentinel-2 extraction and QA pipeline for
Lake Erken covering:

```
L1C / official L2A
  -> metadata + native QA
  -> B4 / B5 / B6 physical reflectance
  -> NDCI / MCI
  -> (future) field matchup
  -> (future) real-S2 reconstruction
```

Phase 6A implements and audits the observation layer only. It ends at the
QA/availability audit.

## 2. Exclusions

Phase 6A does not:

- inspect CHLF, in any form;
- compute NDCI/MCI versus field correlations, errors, regressions, rankings or
  any performance metric;
- rank L1C against L2A scientifically, or claim either product is better;
- perform retrieval calibration;
- run TIMESAT, or any reconstruction;
- touch Lake Vombsjön data, results, files, directories or products;
- alter frozen Phase 3/4/5 results, configurations, contracts, reconstruction
  outputs, TIMESAT defaults or TIMESAT source code.

The pipeline enforces the Vombsjön exclusion and the frozen-namespace
exclusion in code, not only by convention.

## 3. Repository responsibility

`twinwater-timesat-s2-chla` owns the manuscript-specific scientific observation
and analysis layer: real Sentinel-2 extraction, L1C/L2A metadata
harmonization, spatial extraction, QA harmonization, NDCI/MCI construction,
field-matchup preparation, temporal observation tables, later reconstruction
analyses and manuscript results.

The separate `s2-inlandwater-ac` repository owns execution of atmospheric
correction processors — ACOLITE, C2RCC/C2X, POLYMER and OC-SMART. No
atmospheric-correction processor is implemented, invoked or reimplemented
here. Phase 6A is restricted to Sentinel-2 L1C TOA and official ESA
L2A/Sen2Cor products.

## 4. Product levels

**L1C is the TOA baseline, not an atmospheric correction.** L1C reflectance is
top-of-atmosphere. It is retained as a transparent baseline in the sense of
master §10, and must never be described, labelled or interpreted as a
water-leaving or atmospherically corrected quantity.

**Official L2A is the Sen2Cor BOA baseline.** It is the ESA-distributed
Sen2Cor bottom-of-atmosphere product. Using Sen2Cor SCL for scene
classification does not select Sen2Cor reflectance as the preferred
water-reflectance product (Decision 011), and Phase 6A does not revisit that.

## 5. Frozen SCL inheritance

The frozen Erken observation rule remains authoritative and is inherited
unchanged:

- rule ID `scl3x3_b1_w8_centernotbad_p0_class2zero_v1`;
- calendar date as the temporal observation unit;
- station-centred 3×3 support on the 20 m grid.

Phase 6A does **not** reopen spatial-support selection, SCL rule selection or
temporal-unit selection.

Two QA layers are kept separate in both code and outputs:

1. the **frozen L2A-SCL product/date gate**, inherited as already governed; and
2. **native product/band QA**, new in Phase 6A.

Native QA never replaces the frozen SCL rule. Reflectance and index values
never influence SCL-gate selection.

## 6. Product and date pairing

Phase 6A starts from the already-frozen L2A observation-mask provenance in
`data/processed/erken_s2_observation_mask.csv`. For a date with a frozen
representative L2A product, that representative product is used. Products are
never re-selected using reflectance, NDCI, MCI, native QA attractiveness, CHLF
or downstream performance.

L1C is paired deterministically on acquisition metadata — platform, sensing
datetime, MGRS tile, and relative orbit where both sides declare it — not on
loose filename substring matching. The audit retains sensing datetime,
platform, tile, orbit, product identifiers, processing baseline and generation
metadata.

Pairing status is one of `exact_unique`, `ambiguous_multiple_candidates`,
`unmatched_no_candidate`, `metadata_incomplete` or `l1c_root_not_provided`.
When an exact pair is unavailable or ambiguous, the date is preserved, the L2A
provenance is preserved, the status is recorded explicitly, and no other
acquisition is silently substituted. The pairing audit contains every frozen
representative/candidate date, including failures.

Calendar date remains the observation unit, but pairing is decided on the
underlying acquisition metadata, not on equal calendar dates alone.

## 7. Reflectance conversion

Pilot bands are B4, B5 and B6, always as physical reflectance, never raw DN.

The single conversion rule is:

```
reflectance = (DN + add_offset) / quantification_value
```

Both terms are read from the product's own metadata:

- **L1C** — `QUANTIFICATION_VALUE`, and `RADIO_ADD_OFFSET` from
  `Radiometric_Offset_List` where present;
- **L2A** — `BOA_QUANTIFICATION_VALUE`, and `BOA_ADD_OFFSET` from
  `BOA_ADD_OFFSET_VALUES_LIST` where present.

`DN / 10000` is **not** implemented as a universal rule. The exact metadata
values and the conversion rule used are recorded per product and per band.

Band identity is resolved from the product's own `Spectral_Information_List`
where present; the canonical MSI band-id mapping is a documented fallback and
the source actually used is recorded as `band_id_source`. Product-declared
central wavelengths are recorded as diagnostics.

Offset handling is **baseline-aware**, because absence of an offset list means
different things at different baselines:

- for a baseline **before** `N0400`, the offset convention did not exist, so the
  additive offset is zero **by product definition** and is recorded explicitly
  as `offset_source=absent_no_offset_list_pre_N0400`;
- for a baseline **at or after** `N0400`, an offset list is expected, so its
  absence is an explicit `radiometric_metadata_unusable` failure. A malformed
  product, a new baseline, or a parser failure must never be read as a
  pre-offset product;
- if the processing baseline **cannot be determined at all**, the observation is
  an explicit failure rather than a guessed convention.

The baseline is read from the product metadata `PROCESSING_BASELINE`, with the
compact product name as an audited fallback; the source used is recorded as
`processing_baseline_source`.

An offset list that is declared but omits a required band, or that contains no
usable per-band entry, is likewise an explicit failure, as is an absent or
non-finite quantification value. No constant is ever invented.

Negative physical reflectance is **not** clamped before index calculation. The
metadata-derived value is preserved and out-of-range values are flagged as
diagnostics.

## 8. Metadata requirements

Per product, Phase 6A requires and records: product identifier, product level,
platform, sensing datetime, MGRS tile, relative orbit where available,
processing baseline, generation time where available, quantification value,
per-band additive offset, band-id source, and the discovered asset paths as
product-relative paths. Missing or inconsistent required metadata produce an
explicit failure record, never a silent default.

## 9. Native QA

Product-native masks and metadata actually present in each SAFE product are
mapped into a canonical QA schema. QA60 alone is never used as the QA system.

The archive spans multiple processing baselines and layouts. Discovery
tolerates layout differences rather than assuming one filename or mask
convention for all 2019–2025 products, and records what was found per product.

Canonical QA distinguishes two categories:

**A. Hard invalid** — the required band/pixel cannot support the index because
the MSI radiometry itself is absent, lost, or optically incompatible with a
water-leaving signal: `nodata`, `saturated`, `defective`, `msi_lost`,
`opaque_cloud`, `cirrus`, `snow_ice`, plus the SCL non-water condition of §9.

**B. Diagnostic** — degradation retained for audit and possible later human
freeze: `partially_corrected`, `msi_degraded`, `ancillary_degraded`,
`ancillary_lost`. These are not hard rejects in v1.0.

`ancillary_lost` is deliberately **diagnostic**, not hard: the official mask
semantics identify lost *ancillary* data, which does not by itself establish
that the reflectance sample is absent. Promoting it — or any other diagnostic
flag — to a hard reject is **not** decided using CHLF or index performance; the
incidence is reported for human review. This split is DRAFT pending human
freeze (`qa_split_status` in the configuration).

**Band-specific QA stays band-specific.** `MSK_QUALIT` is distributed per
spectral band, so its conditions produce one hard-invalid mask *per band*.
`MSK_CLASSI` and the SCL water context are product-level and apply to every
band. Collapsing the two would let a B6-only defect invalidate NDCI, whose
primary validity is B4 AND B5 only. Effective validity is therefore:

```
B4_valid = finite(B4) AND NOT B4_hard_invalid AND NOT common_hard_invalid
B5_valid = finite(B5) AND NOT B5_hard_invalid AND NOT common_hard_invalid
B6_valid = finite(B6) AND NOT B6_hard_invalid AND NOT common_hard_invalid
```

Outputs retain band provenance: `qa_<band>_<reason>` columns record which
spectral band a flag came from, alongside an aggregate `qa_<reason>` column for
the canonical schema field.

`MSK_CLOUDS` / QA60 is inventoried as optional provenance and cross-check only
where a product carries it, and never contributes to canonical validity.

Raw/native mask provenance is retained alongside the canonical Boolean fields.
QA provenance is never reduced to a single Boolean, and no QA field
unsupported by the source products is invented.

**Missing QA families.** When a QA family is absent or unreadable for a
product, the observation is retained, the gap is recorded per family, and the
row is flagged `native_qa_incomplete`. Absence is never silently treated as
"clean". *This policy is DRAFT and requires human freeze* — see §16.

**Pixel-level water context.** The paired/native L2A SCL water classification
is the common water-context mask for both L1C and L2A, so the two levels are
evaluated on a comparable spatial support. Pixels classified as
cloud/cirrus/snow/non-water/invalid do not contribute to index summaries. An
L1C product without an exact L2A pair therefore cannot receive the common
water context and is recorded as an explicit failure rather than being
evaluated on a different support.

## 10. Common spatial grid

The primary analysis support remains the frozen 20 m grid and the frozen
station-centred 3×3 window.

- For official L2A, validated R20m B4/B5/B6 assets are preferred where
  available and appropriate.
- For L1C, B5 and B6 define the native 20 m target grid, and native 10 m B4 is
  reduced onto the exact B5/B6 20 m grid by reflectance-preserving block
  averaging. Nearest neighbour is forbidden for continuous reflectance.

CRS, affine transform, dimensions, pixel centres and exact nesting are audited
before any reduction. A real misalignment is an explicit failure, never a
silent resample.

Categorical QA masks are never interpolated. Bilinear, cubic, spline, Lanczos
and averaging resampling are forbidden for categorical layers.

Native QA masks genuinely appear at three resolutions — `MSK_QUALIT` follows its
spectral band (10 m for B4, 20 m for B5/B6) while `MSK_CLASSI` is 60 m — so all
three geometries are handled explicitly:

- **A. mask on the target grid** — read the exact target window;
- **B. mask coarser than the target** — exact footprint expansion, so a source
  categorical pixel covers exactly its nested 20 m cells;
- **C. mask finer than the target** — exact nested conservative reduction: a
  target pixel is flagged when **any** contributing fine pixel is flagged.

Case C applies to Boolean condition masks only. A multi-class layer such as SCL
is never reduced this way; the pipeline refuses rather than inventing a class
value. In every case the grids must be exactly nested and co-registered, and a
misalignment is an explicit failure. Interpolation is never allowed to invent
class values.

## 11. Pixel validity and index-specific validity

Indices are computed at pixel level only after physical reflectance, then QA,
then valid-pixel determination.

- **NDCI primary validity:** `B4 valid AND B5 valid`.
- **MCI primary validity:** `B4 valid AND B5 valid AND B6 valid`.
- **`common_B456_valid`** is recorded additionally, for later same-support
  sensitivity analysis.

Within the frozen 3×3 area, counts and fractions are retained per native QA
failure reason.

## 12. Index definitions

```
NDCI = (B5 - B4) / (B5 + B4)
```

with an explicit, pre-specified numerical denominator guard: the denominator
must be finite and strictly greater than `denominator_epsilon = 1e-6` in
reflectance units. The guard is numerical, not selected using CHLF or
performance. Zero/near-zero denominators and non-finite results are flagged.
Invalid values are never silently replaced, and NDCI is never silently clipped
to [-1, 1]; theoretical-range anomalies are recorded as diagnostics.

```
MCI = B5 - [ B4 + ((lambda_B5 - lambda_B4) / (lambda_B6 - lambda_B4)) * (B6 - B4) ]
```

Nominal centre wavelengths (B4 665 nm, B5 705 nm, B6 740 nm) live in the
machine-readable config, not inside a function. Platform-specific wavelengths
are recorded in the config as inactive reference only; activating them would
be a scientific change requiring human freeze.

The primary processing order is fixed:

```
reflectance -> QA -> valid pixels -> pixel-level NDCI/MCI -> spatial summary
```

The primary index is never computed from already spatially averaged
reflectance.

## 13. Spatial summaries

The primary spatial statistic is the **median of valid pixel-level index
values** within the frozen 3×3 support. Retained per product/date/index:
valid pixel count and fraction, median, mean, standard deviation, IQR, minimum
and maximum, native-QA failure counts and fractions (per band and aggregated),
frozen SCL status, processing baseline, platform, product ID, sensing datetime,
tile, and L1C/L2A pairing status.

Because the final minimum valid-pixel threshold is deliberately not frozen, the
per-record fields are named `ndci_has_any_valid_pixel` and
`mci_has_any_valid_pixel`. They state only that at least one pixel survived QA
and are **not** a QC acceptance decision; each row also carries
`final_valid_pixel_threshold_status = NOT_SELECTED_REQUIRES_HUMAN_FREEZE`.

## 14. QA-only attrition analysis

Attrition is reported for the pre-specified pilot set of minimum valid-pixel
counts in the nine-pixel window: **9/9, ≥8/9, ≥6/9, ≥5/9**, overall, by year,
and by processing baseline and platform.

This set was checked against the master v4.3.1, the Reconstruction Analysis
Contract v1.0.1, its machine-readable JSON and `docs/decisions.md`: no
already-governed minimum-valid-pixel rule exists, so the pilot set supersedes
nothing.

The purpose of the attrition table is to let the human freeze the final
minimum-valid-pixel criterion **before** field-matchup analysis. Phase 6A does
not select that threshold and does not declare any threshold scientifically
superior. Selection must never use CHLF, index-versus-field performance,
reconstruction performance, visual preference or knowledge of later results.

## 15. Provenance and failure handling

Outputs live only under `results/phase6a/`. Phase 3, 4 and 5 outputs are never
overwritten; the pipeline refuses to write into protected prefixes.

Two concise Markdown audits accompany the tables on a real run: a native QA
inventory audit describing the mask families, resolutions, band-specific versus
product-level scope, baseline/platform layout differences and missing or
unsupported families actually found; and a QA/data-availability findings
document reporting counts, pairing outcomes, valid-pixel distributions,
attrition at the pre-specified thresholds and retained failures. Neither makes
a scientific performance claim.

A provenance manifest records pilot version, config identity and SHA256,
inherited frozen governance identities, runtime software versions, git commit,
and the run's counts. Real archive roots are runtime inputs and are never
written into repository outputs; only product-relative asset paths are stored.

Failures are explicit records. Dates and products are never silently dropped
because they are inconvenient: every frozen representative/candidate date
remains represented with a `failure_reason` wherever a value could not be
produced.

## 16. Stopping rule

Phase 6A stops after the QA/availability outputs are generated. It does not
proceed automatically to CHLF matchup. The human must first review and freeze
the final index-validity threshold.

The pipeline stops and requests human review if: repository or branch identity
is wrong; unexpected working-tree changes exist; an action would modify frozen
outputs; an action would access Vombsjön; a scientific choice would require
looking at CHLF or later performance; SAFE metadata semantics are ambiguous
enough that silent assumptions would be required; L1C/L2A pairing cannot be
made deterministic; a product baseline/layout cannot be parsed safely; or the
final minimum-valid-pixel threshold would need to be chosen from downstream
performance.

**Open items requiring human freeze before Phase 6B:**

1. the final minimum valid-pixel threshold (§14);
2. the missing-QA-family policy (§9) — currently retain-and-flag;
3. whether any diagnostic degradation flag (`partially_corrected`,
   `msi_degraded`, `ancillary_degraded`, `ancillary_lost`) becomes a hard
   reject (§9);
4. whether platform-specific centre wavelengths replace the nominal MCI
   constants (§12).

## 17. Future atmospheric-correction insertion point

Later phases may consume ACOLITE, C2RCC/C2X, POLYMER or OC-SMART outputs
produced in `s2-inlandwater-ac`. The observation contract is designed so this
requires no change to it: an additional processor enters as a new
`product_level` value with its own reflectance-conversion adapter, while
pairing, the frozen SCL gate, the common 20 m grid, the canonical QA schema,
index definitions, the 3×3 summary and the attrition reporting all remain as
specified here. Adding a processor must not alter the frozen SCL inheritance
or the observation unit.

## 18. Real-data execution

The real Sentinel-2 SAFE archive resides on the Linux/HPC server, not
necessarily on the development Mac. Pipeline implementation and real-data
execution are therefore separate. Real input roots are supplied as CLI
arguments or environment variables; no absolute archive path is committed.

Intended Linux repository:
`/projects/eko/fs7/pers/ZC/Core/Github/twinwater-timesat-s2-chla`.

When real roots are unavailable, the pipeline is exercised with minimal
controlled fixtures only. Synthetic scientific outputs are never generated and
real processing is never claimed to have succeeded.
