# Vombsjön raw satellite/product and matchup audit protocol v1.1

**Status: implemented, not yet executed on the real archives.**

**Amendment classification: pre-performance scientific amendment.** It was made
**before any Vombsjön performance was inspected**. No Vombsjön satellite value,
no Vombsjön field–satellite association, no correlation, no regression, no
reconstruction metric and no method ranking existed or was consulted when the
rules below were chosen. Nothing in this amendment was tuned.

**Scope of the amendment: horizontal field-validation spatial support only.**

**Supersedes:** [`Vombsjon_Satellite_Input_Audit_Protocol_v1.0.md`](Vombsjon_Satellite_Input_Audit_Protocol_v1.0.md)
and [`config/vombsjon_satellite_input_audit_v1.0.yaml`](../config/vombsjon_satellite_input_audit_v1.0.yaml),
both preserved unchanged for provenance. The v1.0 configuration is deliberately
no longer loadable by the audit code: re-running it would execute a
field-validation rule the current freeze does not authorize.

**Authority:** [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json),
which amends [`config/erken_vomb_transfer_freeze_v1.0.json`](../config/erken_vomb_transfer_freeze_v1.0.json)
(also preserved). Every scientific rule here is read from the v1.1 freeze and
cross-checked against it before any product is opened.

**Executable configuration:** [`config/vombsjon_satellite_input_audit_v1.1.yaml`](../config/vombsjon_satellite_input_audit_v1.1.yaml).

**Entry point:** [`scripts/41_vombsjon_satellite_input_audit.py`](../scripts/41_vombsjon_satellite_input_audit.py).

## 1. What changed, and why

v1.0 compared field Chl-a with satellite values taken at the **actual field GPS
of the day, in a 3×3 window, with the paper nominal station as a fallback**
where no GPS was recorded. That made the compared spatial support move between
dates and differ in kind between dates that happen to carry a GPS record and
dates that do not. A difference between two field dates could then be a
difference in where the satellite was sampled rather than a difference in the
water.

v1.1 replaces that primary support with **one fixed pelagic sampling-area
polygon, used identically on every field date**.

| Layer | v1.0 | v1.1 |
|---|---|---|
| Temporal reconstruction target | fixed nominal-station 3×3, min 6/9 | **unchanged** |
| Primary field validation | actual-GPS 3×3, nominal-point fallback | **fixed pelagic convex-hull polygon, ≥2/3 valid** |
| Actual-GPS 3×3 | primary | **secondary spatial sensitivity only** |
| Nominal-point fallback in field validation | allowed | **removed** |

## 2. Temporal reconstruction target — unchanged

The observation layer intended for later TIMESAT reconstruction is unchanged:

- 55.6775 N, 13.60889 E, WGS84;
- the common 20 m grid;
- a fixed 3×3 window;
- at least 6 of 9 valid MCI pixels;
- spatially fixed for every date and never moved by field GPS.

This target is neither enlarged nor replaced. The polygon below is a separate
support with a separate purpose.

## 3. Primary field-validation support — fixed pelagic polygon

### 3.1 Construction

Built deterministically from the committed field source alone,
[`data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv`](../data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv),
which is never modified:

1. accept a coordinate only when
   `coordinate_source_for_matchup == "measured_GPS"` **and**
   `coordinate_qc == "ok"`;
2. explicitly exclude the unresolved flags, **2020-06-10** and **2020-06-24**,
   and every date with no measured GPS, recording the reason for each;
3. add the paper nominal station 55.6775 N, 13.60889 E as an anchor point;
4. project the accepted coordinates to EPSG:32633 — the UTM zone containing the
   station, verified against the station longitude at run time;
5. take their **convex hull**, with **no buffer**; and
6. store the polygon in both EPSG:32633 and WGS84.

The hull is computed by Andrew's monotone chain on lexicographically sorted
unique coordinates, so the vertex set and order are reproducible byte for byte
and do not depend on a hull solver's tie-breaking.

**On the committed source as it stands, 21 coordinate rows are accepted**, plus
the nominal anchor: 22 construction inputs.

### 3.2 No clipping

This repository holds **no authoritative Vombsjön lake or open-water geometry**.
The hull is therefore **not clipped** and no outline is invented. Excluding
non-water pixels remains the job of the existing per-product native QA and the
SCL water context, exactly as for the temporal target. If an authoritative,
unambiguously identified geometry is supplied later, clipping becomes a new
versioned decision, not a silent code change.

### 3.3 Raster support

- the same common 20 m target grid as the temporal target;
- a pixel belongs to the polygon when **its centre lies inside the polygon**,
  tested by a crossing-number rule with a half-open convention in *y* plus an
  explicit on-edge test at a 1 nm numerical tolerance — a guard against
  floating-point round-off, not a buffer;
- the polygon is read through the smallest odd, centre-anchored **square**
  window that fully contains it, so the existing station-centred readers and
  their categorical-QA handling are reused unchanged. The mask then selects
  exactly the polygon pixels. The run refuses to summarize a polygon the square
  does not fully contain;
- categorical QA is never interpolated;
- the exact polygon pixel count is recorded per product, and it is the
  denominator of every reported fraction.

### 3.4 Extraction order

Per product and per method, for every acquisition on an exact field calendar
date:

1. physical reflectance from the product's own metadata;
2. the existing method-specific native QA, applied **before** any aggregation;
3. **pixel-level** MCI (and NDCI) from B4/B5/B6;
4. restriction to the polygon pixels;
5. summary of the surviving valid MCI: median (the primary statistic), mean,
   SD, IQR, min, max, valid pixel count, total polygon pixel count and valid
   pixel fraction.

Invalid pixels are never filled. Negative reflectance and negative MCI are
never clipped. Product roles are never pooled.

### 3.5 Polygon availability rule

The frozen 6-of-9 count rule belongs to the 3×3 temporal target and is **not**
reused here: "at least 6 valid pixels" on a polygon of several hundred pixels
would be no support rule at all. The polygon instead uses a pre-specified
**fractional** rule, fixed before any Vombsjön value was read:

- required QA must be complete; **and**
- at least **two thirds** of the polygon's target-grid pixels must be valid for
  MCI.

Recorded per row: `polygon_total_pixel_count`, `MCI_valid_pixel_count`,
`MCI_valid_pixel_fraction`, `polygon_observation_eligible` and an explicit
availability or failure reason. Missing support and low support stay
distinguishable: an unavailable observation is `None`, a formed observation
below the fraction is `False`.

The temporal-target 6-of-9 rule is untouched.

## 4. Same-day product handling

CDSE can hold several reprocessed products for one acquisition or date.

- every product-level polygon extraction row is preserved in
  `vombsjon_field_polygon_product_master.csv`;
- then, separately by method, only QC-eligible polygon observations are
  retained and reduced to the **median of their observation-level medians**;
- contributing product identifiers, sensing datetimes, processing baselines and
  valid pixel counts are retained, as are the excluded identifiers and their
  statuses;
- reprocessings are never counted as independent field matchups.

`vombsjon_field_satellite_matchup_master.csv` therefore holds **one date-level
row per field date and method**.

## 5. Actual-GPS 3×3 — secondary spatial sensitivity

Retained only as a sensitivity, for dates with a reliable measured coordinate:

- accepted only when `coordinate_source_for_matchup == "measured_GPS"` and
  `coordinate_qc == "ok"`;
- the same 20 m grid, the same 3×3 window, the same 6-of-9 rule;
- **no** nominal fallback, **no** extraction where GPS is missing, and **no**
  extraction for 2020-06-10 or 2020-06-24;
- never used to tune the polygon.

It exists to answer, later, whether the fixed pelagic-area signal represents the
locations where the boat actually sampled. It is not the primary
field-validation support.

## 6. Missing and flagged GPS dates

For the **primary polygon** comparison:

- dates without measured GPS remain usable, because the same fixed polygon is
  used on every date; and
- the two unresolved GPS dates are **not** discarded merely because their exact
  point is uncertain — their coordinate QC flags are preserved in the matchup
  table.

For **polygon construction** and the **GPS 3×3 sensitivity**, both groups are
excluded. The distinction is explicit in the outputs: every field row carries
`coordinate_status`, `coordinate_contributed_to_polygon` and
`gps_3x3_sensitivity_eligible`.

## 7. Field depth and representativeness

`echo_depth_m` and `integrated_sample_depth_m` are preserved. The committed
source's facts are carried, not reinterpreted: 2018 integrated samples are
0–2 m, 2019–2020 generally 0–6 m where recorded, and echo depths where
available are those of the deeper pelagic station.

Field Chl-a is **not** treated as literal satellite-surface Chl-a, and **no
"well mixed, therefore vertically identical" rule is coded**. This amendment
concerns horizontal spatial support only; vertical field-versus-satellite
representativeness remains a documented limitation and appears in the
manifest's `unresolved_items`.

## 8. Product roles, radiometry and QA — unchanged

ACOLITE `rhos` MCI is the primary observation product, official L2A BOA MCI a
separate sensitivity, and L1C TOA MCI a separate diagnostic baseline. Quantities
are never pooled and there is no silent processor fallback. Radiometry stays
metadata-aware and baseline-aware, and a required QA family that is absent or
unreadable makes the affected observation unavailable.

**Readability is not availability.** Each extraction row now carries both
`extraction_successful` (the rasters were read and the indices computed) and
`observation_available` (the scientific statement, false whenever required QA
was incomplete, whatever the rasters did).

### 8.1 QA diagnostic counts: read window versus extraction support

**Diagnostic-only correction, applied after the first real v1.1 run. No
scientific rule changed.**

A polygon target is read through an enclosing square window (33×33 = 1089
pixels in the first real run) while the observation itself only ever uses the
615 pixel centres inside the fixed polygon. The reported `MCI_valid_pixel_count`
was always restricted to that support, but the SAFE native-QA layer counts
(`qa_scl_not_water_count`, `qa_opaque_cloud_count`, the per-band `MSK_QUALIT`
layers, and so on) were whole-enclosing-window counts. A QA diagnostic could
therefore report up to 1089 against a 615-pixel support, which is misleading
and blocks any reading of why a polygon observation failed QC. ACOLITE QA
counts were already support-restricted.

Every extraction row therefore now carries both bases:

- `qa_<layer>_count` — unchanged, the whole enclosing read window, preserved
  for provenance and comparability with the first run;
- `qa_<layer>_count_in_support` and `qa_<layer>_fraction_in_support` — the same
  layer counted over the pixels the target actually summarizes;
- aggregates `qa_common_hard_invalid_*_in_support`,
  `qa_<band>_hard_invalid_*_in_support` (the effective mask band validity
  consumes) and `qa_<band>_band_specific_hard_invalid_*_in_support` (that
  band's own share), with bands in the canonical `B04`/`B05`/`B06` form already
  used by the QA columns;
- `qa_whole_window_count_pixel_basis`, `qa_in_support_count_pixel_basis` and
  `qa_support_is_whole_read_window`, so each denominator is explicit; and
- ACOLITE `qa_acolite_<layer>_count_in_support` aliases carrying the same
  values as the existing support-restricted ACOLITE columns, so one column name
  reads the same way across every method.

For a point target the support is the whole window, so the two bases agree by
construction.

These fields are **diagnostic only**. They are derived from the same QA masks
that validity already uses, they are written to the output row and nothing
else, and no band validity, index validity or eligibility decision reads them.
**Band validity, MCI validity, the 2/3 polygon fractional support rule, the
fixed 3×3 6-of-9 rule, the fixed polygon, the ACOLITE flag layout and the SAFE
QA classification are all unchanged.**

`qa_layer_counts_may_overlap` is recorded as a reminder that a pixel can carry
several flags at once. These counts must not be summed, and no causal
attribution of any failed observation may be drawn from them until the
support-restricted counts have actually been produced by a rerun and read.

## 9. ACOLITE identity and provenance

The ACOLITE layout is discovered at run time and recorded; it is not assumed to
match the Erken layout. NetCDF outputs are inventoried and never read as a
substitute for the required GeoTIFF `rhos`/`l2_flags` pair.

ACOLITE identity is read from the settings files **and from `run.json`, which
is now really parsed**: only a JSON object, only a top-level key that exactly
matches a requested setting name, and only a scalar value. A nested structure, a
list, an unparseable file or an unrecognised key yields nothing, and each
declared value records whether it came from a settings file or `run.json`.
Anything the files do not state is reported as
`not_verifiable_from_supplied_files`, never guessed.

## 10. Provenance identifiers

A SHA256 of a path string identifies a path, not file content. Those fields are
named `*_root_path_sha256` and the manifest states explicitly that they are not
content checksums. Alongside them the manifest carries **inventory
fingerprints**: a SHA256 over sorted `<id>\t<root-relative path>` lines, one per
discovered product or scene, for L1C, L2A and ACOLITE. These identify the set of
products actually found, independent of walk order and mount point, and are
labelled as not being raster-content checksums.

## 11. Outputs

All under `results/vombsjon/satellite_input_audit/v1.1/`. Writes outside that
namespace, into any frozen or protected namespace, or into the preserved v1.0
namespace, are refused in code.

| File | Content |
|---|---|
| `vombsjon_field_sampling_area.geojson` | the fixed pelagic polygon in WGS84, with its construction properties |
| `vombsjon_field_sampling_area_provenance.csv` | every offered coordinate with its accept/reject reason, the hull vertices, and the polygon summary |
| `vombsjon_l1c_inventory.csv` | every discovered L1C product |
| `vombsjon_l2a_inventory.csv` | every discovered official L2A product |
| `vombsjon_l1c_l2a_pairing_audit.csv` | pairing in both directions, including failures |
| `vombsjon_acolite_inventory.csv` | every ACOLITE scene, its layout, assets, declared settings and linkage |
| `vombsjon_native_qa_inventory.csv` | native QA assets each SAFE product actually contains |
| `vombsjon_product_extraction_master.csv` | one row per method, product and support |
| `vombsjon_fixed_station_observation_master.csv` | fixed 3×3 temporal-target rows with the 6-of-9 decision |
| `vombsjon_same_day_observation_master.csv` | per-method, per-calendar-date reduction of the temporal target |
| `vombsjon_field_polygon_product_master.csv` | product-level polygon rows with the fractional-support decision |
| `vombsjon_field_satellite_matchup_master.csv` | **one date-level row per field date × method** after same-day reduction |
| `vombsjon_field_gps_3x3_sensitivity.csv` | secondary actual-GPS 3×3 sensitivity, with explicit not-extracted statuses |
| `vombsjon_extraction_failures.csv` | every recorded discovery and extraction failure |
| `vombsjon_satellite_input_audit_manifest.json` | run identity, amendment record, freeze cross-check, polygon provenance, counts, ACOLITE identity, unresolved items |

Table rows carry paths relative to the supplied runtime root, so no committed
table embeds a machine-specific archive path.

## 12. Running it

```
python scripts/41_vombsjon_satellite_input_audit.py \
  --l1c-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L1C/T33UVB \
  --l2a-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L2A/T33UVB \
  --acolite-root /projects/eko/fs7/pers/ZC/TWIN_water/ACOLITE_VOMBSJON \
  --output-root results/vombsjon/satellite_input_audit/v1.1 \
  --require-real-archive
```

Without `--require-real-archive` a missing root produces a clean stop rather
than a guessed path or synthetic output.

## 13. Next gate

Completing this audit does not authorize performance execution. The locked
Vombsjön transfer remains a separate stage, and the execution gates in
`config/erken_vomb_transfer_freeze_v1.1.json` still apply: a failed gate stops
the work rather than changing a setting or falling back to another product. No
regression, correlation, ranking or performance model is fitted by this audit.
