# Vombsjön raw satellite/product and matchup audit protocol v1.0

**Status: implemented, not yet executed on the real archives.**

**Authority:** this protocol executes the stage that
[`Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md`](Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md)
names as `vombsjon_input_and_raw_satellite_matchup_audit_only`, and that
[`STATUS.md`](STATUS.md) lists as original-plan pending item 1. It selects no
scientific setting. Every scientific rule it applies is read from
[`config/erken_vomb_transfer_freeze_v1.0.json`](../config/erken_vomb_transfer_freeze_v1.0.json)
and is cross-checked against that file before any product is opened.

**Executable configuration:**
[`config/vombsjon_satellite_input_audit_v1.0.yaml`](../config/vombsjon_satellite_input_audit_v1.0.yaml).

**Entry point:** [`scripts/41_vombsjon_satellite_input_audit.py`](../scripts/41_vombsjon_satellite_input_audit.py).

## 1. Scope

This audit may:

- inventory every discovered Vombsjön L1C, official ESA L2A and ACOLITE
  product before any scientific filtering;
- audit L1C/L2A pairing in both directions;
- discover the ACOLITE output layout that actually exists and link each scene
  to a source L1C acquisition;
- extract the frozen fixed-station target and, separately, the field-location
  target;
- apply the frozen QC;
- reduce multiple eligible same-date observations per method; and
- materialize a derived field-satellite matchup table.

This audit must **not** run TIMESAT, create daily reconstructed curves, perform
withheld-observation experiments, compute reconstruction metrics, tune any rule
using Vombsjön, choose a processor from Vombsjön performance, or change a
frozen transfer setting. It must not modify the committed field source or any
Erken protocol, configuration, result or manifest.

The Erken Phase 6A and Phase 6B scope guards remain in force and unchanged.
This audit does not disable them and does not reuse the Erken orchestrators; it
reuses only the site-independent low-level Sentinel-2 and ACOLITE utilities
that those orchestrators now share
([`s2_window_io.py`](../src/twinwater_timesat/s2_window_io.py) and
[`s2_acolite_io.py`](../src/twinwater_timesat/s2_acolite_io.py)).

## 2. Freeze cross-check gate

Before any product is opened, the audit loads the frozen transfer
configuration, verifies its `freeze_version` and its declared
`next_authorized_stage`, and compares every rule listed under
`freeze.crosscheck` with the value this audit actually implements. A single
mismatch stops the run with an explicit message. This is the mechanism that
prevents a Vombsjön run from quietly executing a rule the second freeze did not
authorize.

The committed field source is verified by SHA256 and row count before it is
read. A changed checksum stops the run rather than recording a mismatched
identity.

## 3. Fixed temporal target

The scientific time-series target is a fixed station-centred 3×3 window on the
common 20 m grid around 55.6775 N, 13.60889 E. It does **not** move between
dates according to field GPS.

Per product and per target:

1. reflectance is converted from the product's own metadata;
2. pixel-level QA is applied;
3. pixel-level B4/B5/B6 give pixel-level MCI (and NDCI);
4. the observation value is the **median of the surviving pixel-level MCI**;
5. at least **6 of 9** valid MCI pixels are required.

Negative reflectance and negative MCI are retained. Invalid pixels are never
filled. The valid pixel count and fraction are preserved on every row.

## 4. Product roles

| Method | Quantity | Role |
|---|---|---|
| ACOLITE | `rhos` (L2R) | primary observation product |
| Official L2A | BOA reflectance | separate processing sensitivity |
| L1C | TOA reflectance | separate transparent diagnostic baseline |

Reflectance quantities are never pooled and there is no silent fallback from
one processor to another. A method whose required input is missing yields an
explicitly unavailable observation for that product, never a substituted value
from a different processor.

## 5. Radiometry

For L1C and L2A, reflectance is `(DN + add_offset) / quantification_value`,
with both terms read from the product's own metadata by the existing
metadata-aware, baseline-aware logic. `DN / 10000` is never applied as a
universal rule. The processing baseline, its provenance, the per-band offset
source and the conversion rule actually applied are retained on every row.

## 6. QA

L1C and L2A reuse the existing conservative native QA machinery: band-specific
`MSK_QUALIT`, product-level `MSK_CLASSI`, and the paired official L2A SCL water
context applied to both levels.

ACOLITE uses its own `L2R rhos` products together with the matching `L2W
l2_flags` raster from the same ACOLITE output basename. Unknown `l2_flags` bits
count as hard invalid.

The frozen transfer rule is stricter than the Erken Phase 6A draft: **a
required QA family that is absent or unreadable makes the affected observation
unavailable.** The row and the reason are retained; absence is never treated as
clean and invalid pixels are never filled. The required families are
`QUALIT`, `CLASSI` and the SCL water context for the SAFE levels, and the
matching `l2_flags` raster for ACOLITE.

## 7. Same-day handling

Acquisition/product-level rows are preserved first, in
`vombsjon_product_extraction_master.csv` and
`vombsjon_fixed_station_observation_master.csv`. Only then, and separately for
each method, are multiple eligible observations on the same calendar date
reduced to the **median of their observation-level medians**. The reduced table
retains the contributing product identifiers, their sensing datetimes, their
valid pixel counts, and the identifiers and statuses of the products that were
present but not eligible. Methods are never pooled.

## 8. Field matchup layer

The committed source
[`data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv`](../data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv)
is read-only. The audit builds a separate derived table.

- Actual field GPS is used where available.
- The nominal paper station is used only as a fallback, labelled
  `nominal_station_fallback`.
- The two unresolved 2020 coordinate flags (2020-06-10 and 2020-06-24) are
  **not** silently corrected. Those field rows and their QC text are preserved,
  their coordinate provenance is recorded as
  `unresolved_flag_retained_extraction_withheld`, and satellite extraction at
  the disputed field location is withheld rather than performed at either
  candidate longitude minute. The fixed temporal target is unaffected on those
  dates.
- Satellite values for the field location are extracted separately from the
  fixed temporal target, and both are retained on the matchup row.

The temporal rule is the exact same calendar date, with a zero-day tolerance,
matching the frozen Erken matchup rule and the frozen whole-calendar-date
observation unit. Widening it would be a new scientific decision, not part of
this audit.

The source table records no sampling clock time. The matchup therefore retains
the satellite sensing datetime, the acquisition-minus-field-date difference in
days, and the offset in hours from the field calendar date at 00:00 UTC, and
states explicitly that the sampling time is unavailable.

Retained per matchup row: scene/product identifier, sensing datetime,
acquisition-time difference, product level and method, processing baseline and
provenance, the coordinates actually used, the coordinate provenance, spatial
statistics, valid pixel count and fraction, QA state, and NDCI and MCI where
available. **No regression, correlation, ranking or performance model is fitted
here.**

## 9. Raw product audit

Every discovered product is inventoried before scientific filtering, including
products that later fail. Retained: product identifier, acquisition datetime,
platform, tile, relative orbit where declared, processing baseline and
generation metadata, the source path relative to the supplied runtime root,
ACOLITE product linkage, missing or ambiguous pairing, and discovery failures.

## 10. ACOLITE layout

The Vombsjön ACOLITE layout is **not** assumed to match the Erken
`ACOLITE_ERKEN/<L1C product>/acolite` layout. Discovery walks the supplied root,
treats any directory that directly contains an `L2R rhos` GeoTIFF as an ACOLITE
output directory, groups files by the ACOLITE output basename, and records the
observed relative layout pattern in both the inventory and the manifest. Raw
ACOLITE files are only read; nothing is moved, renamed or modified.

NetCDF outputs are inventoried for provenance and are never read as a
substitute for the required GeoTIFF `rhos`/`l2_flags` pair. A scene that carries
only NetCDF is an explicitly recorded unavailability.

Each scene is linked to a source L1C acquisition in a fixed, recorded order:
ancestor directory name, ACOLITE output basename acquisition identity, then a
declared `inputfile` setting. An ambiguous or absent link is recorded as such
and never guessed.

## 11. ACOLITE identity verification

The freeze declares the external workflow commit, ACOLITE source commit,
version string, inland profile, 20 m resolution, polygon clipping, ancillary
data and `L2R_rhos` output. The audit compares those with whatever the
discovered ACOLITE settings and `run.json` files actually declare. Anything the
files do not state is reported as
`not_verifiable_from_supplied_files` in the manifest's `unresolved_items`,
never assumed to match.

A declared flag-exponent setting that differs from the configured bit layout is
an extraction failure for that scene, because the decoder would otherwise
misread the bit field.

## 12. Outputs

All outputs are written under
`results/vombsjon/satellite_input_audit/v1.0/`. Writes outside that namespace,
and writes into any frozen or protected namespace, are refused in code.

| File | Content |
|---|---|
| `vombsjon_l1c_inventory.csv` | every discovered L1C product |
| `vombsjon_l2a_inventory.csv` | every discovered official L2A product |
| `vombsjon_l1c_l2a_pairing_audit.csv` | pairing in both directions, including failures |
| `vombsjon_acolite_inventory.csv` | every discovered ACOLITE scene, its layout, assets and linkage |
| `vombsjon_native_qa_inventory.csv` | native QA assets each SAFE product actually contains |
| `vombsjon_product_extraction_master.csv` | one row per method, product and target |
| `vombsjon_fixed_station_observation_master.csv` | fixed-target observation rows with the frozen eligibility decision |
| `vombsjon_same_day_observation_master.csv` | per-method, per-calendar-date reduction with contributing provenance |
| `vombsjon_field_satellite_matchup_master.csv` | derived field-satellite matchup table |
| `vombsjon_extraction_failures.csv` | every recorded discovery and extraction failure |
| `vombsjon_satellite_input_audit_manifest.json` | run identity, rules, counts, ACOLITE identity, unresolved items |

The manifest retains the repository commit and worktree state, the runtime
input roots, the configuration and freeze checksums, the freeze cross-check
result, the source field CSV checksum, product counts and acquisition date
ranges, the extraction and QC rules actually applied, the ACOLITE identity that
the files establish, and an explicit `unresolved_items` list.

Table rows carry paths relative to the supplied runtime root, so no committed
table embeds a machine-specific archive path. The manifest records the SHA256
identity of each runtime root by default; `--record-absolute-roots` additionally
writes the literal paths for an operator's own records.

## 13. Running it

```
python scripts/41_vombsjon_satellite_input_audit.py \
  --l1c-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L1C/T33UVB \
  --l2a-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L2A/T33UVB \
  --acolite-root /projects/eko/fs7/pers/ZC/TWIN_water/ACOLITE_VOMBSJON \
  --output-root results/vombsjon/satellite_input_audit/v1.0 \
  --require-real-archive
```

Without `--require-real-archive` a missing root produces a clean stop rather
than a guessed path or synthetic output.

## 14. Next gate

Completing this audit does not authorize performance execution. The locked
Vombsjön transfer remains a separate stage, and the execution gates in
`config/erken_vomb_transfer_freeze_v1.0.json` still apply: a failed gate stops
the work rather than changing a setting or falling back to another product.
