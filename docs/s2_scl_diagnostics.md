# Lake Erken Sentinel-2 L2A SCL diagnostics

## Scientific purpose and boundary

Phase 2A uses the Sentinel-2 L2A Scene Classification Layer only to characterize product availability and the spatial SCL environment around the Lake Erken reference coordinate:

- latitude: `59.84029`;
- longitude: `18.625827`;
- coordinate reference system: `EPSG:4326`.

The daily Erken CHLF record remains the high-frequency pelagic temporal reference. SCL is not chlorophyll truth, and this workflow reads no reflectance, NDCI, MCI, atmospheric-correction product, or CHLF value.

The five neighborhoods (1×1, 3×3, 5×5, 7×7, and 11×11) were generated as diagnostic candidates. Phase 2A extraction did not select an ROI, bad-SCL threshold, water-fraction threshold, or usable/unusable acquisition rule. The subsequent real-output analysis selected 3×3 as the primary spatial neighborhood, with 1×1 and 5×5 retained for sensitivity; see `docs/erken_s2_scl_roi_diagnostic.md`. All usability thresholds remain unset. Use of the Sen2Cor-produced SCL layer does not select Sen2Cor reflectance as the preferred inland-water reflectance product.

## Supported product organization

The discovery and metadata logic supports unpacked archives containing:

1. standard compact-name `.SAFE` L2A product directories;
2. compact-name L2A product directories without the `.SAFE` suffix;
3. otherwise named product directories containing `MTD_MSIL2A.xml`.

Within each product, SCL rasters may be JP2, GeoTIFF (`.tif`), or `.tiff` files at any depth. Standard `GRANULE/.../IMG_DATA/R20m/*_SCL_20m.jp2` organization is preferred. When a product tile ID is known, matching paths are preferred. If multiple equally preferred SCL rasters remain, the product is recorded as `ambiguous_scl`; no arbitrary raster is selected.

Compressed SAFE ZIP files are not opened in place. They must be unpacked or exposed through a normal directory layout on the server. GDAL/rasterio must support the archive's raster encoding, including the JPEG2000 driver for JP2 inputs.

Product metadata are parsed from the compact product identifier when available, with `MTD_MSIL2A.xml` fallback for product URI, acquisition time, processing baseline, and platform. The processing baseline is preserved as the standard `Nxxxx` code because SCL class-2 wording/behavior can differ between baselines. Tile ID may also be recovered from the selected SCL path.

## Spatial method

For every selected SCL raster, the workflow records its declared CRS, six affine-transform coefficients, bounds, dimensions, and x/y resolution. The station longitude/latitude is transformed with `pyproj` using explicit x/y ordering. Pixel row and column are calculated using the inverse raster affine transform, never from filenames or assumed offsets.

Centered windows are clipped to real raster bounds. They are never synthetically padded. `requested_pixel_count`, `actual_pixel_count`, and `window_complete` make boundary clipping explicit. A station outside the raster is retained as `station_outside_raster` with its calculated out-of-range row/column and zero extracted pixels.

## SCL classes and diagnostic aggregates

Every scene/window row preserves separate counts and fractions for:

| Code | Meaning |
|---:|---|
| 0 | No data |
| 1 | Saturated or defective |
| 2 | Topographic cast shadow / dark area, depending on processing baseline |
| 3 | Cloud shadow |
| 4 | Vegetation |
| 5 | Not vegetated |
| 6 | Water |
| 7 | Unclassified |
| 8 | Cloud medium probability |
| 9 | Cloud high probability |
| 10 | Thin cirrus |
| 11 | Snow or ice |

`water_fraction` is the fraction equal to class 6. `bad_scl_fraction` is the fraction in `{0, 1, 3, 8, 9, 10, 11}`. Both are diagnostics only. Unexpected numeric class values are retained through `unexpected_scl_count` and `unexpected_scl_values` rather than silently coerced.

## Product inventory schema

`data/processed/erken_s2_l2a_inventory.csv` contains one row per discovered product:

- identity: `product_id`, `platform`, `acquisition_datetime`, `acquisition_date`, `tile_id`, `processing_baseline`;
- SCL discovery: `scl_raster_relative_path`, `scl_candidate_count`, `scl_found`;
- audit status: `processing_status`, `processing_note`.

The SCL path is relative to the runtime input root. The server root itself is never saved.

## Scene/window schema

`data/processed/erken_s2_scl_scene_summary.csv` contains one row per product and requested window size. It retains multiple products on the same date.

- product metadata: the six inventory identity fields;
- raster provenance: relative SCL path, CRS, affine coefficients, four bounds, pixel sizes, width, and height;
- station lookup: latitude, longitude, source CRS, transformed x/y, central row/column, central SCL, and inside-raster flag;
- window audit: size, requested and actual counts, and completeness;
- SCL composition: `scl_0_count` through `scl_11_count`, corresponding fractions, unexpected-value diagnostics, water fraction, and bad-SCL fraction;
- processing audit: status and note.

Failed products still produce one placeholder scene row per requested window. This keeps product existence distinct from SCL contamination and avoids creating synthetic missing acquisition dates.

## Processing statuses

| Status | Meaning |
|---|---|
| `ok` | SCL raster processed and the requested window was complete |
| `window_clipped` | Station was inside, but the requested window reached a raster boundary |
| `missing_scl` | Product exists but no SCL JP2/GeoTIFF was found |
| `ambiguous_scl` | Multiple equally preferred SCL rasters remained |
| `raster_open_error` | The selected raster could not be opened |
| `raster_read_error` | Raster opened but the central pixel could not be read |
| `window_read_error` | At least one requested centered window could not be read |
| `missing_raster_crs` | Raster opened but declared no CRS |
| `coordinate_transform_error` | Station coordinate could not be transformed |
| `station_outside_raster` | Transformed station lies outside the raster |

## Server command

```bash
python scripts/03_erken_s2_scl_diagnostics.py \
  --input-root /path/on/server/to/Sentinel2/L2A \
  --output data/processed/erken_s2_scl_scene_summary.csv \
  --inventory-output data/processed/erken_s2_l2a_inventory.csv
```

After the server run, inspect product counts, tile IDs, row/column and transform stability, baseline/year coverage, central SCL values, class fractions by neighborhood, clipped windows, and all non-`ok` statuses. The committed real-output review is implemented by `scripts/04_erken_s2_scl_roi_analysis.py`. It selects the spatial neighborhood only and does not define the final usability threshold.
