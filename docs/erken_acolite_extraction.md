# Erken ACOLITE extraction implementation note

This implementation consumes ACOLITE products produced by the separate
`s2-inlandwater-ac` workflow. It does not execute ACOLITE and does not modify
the existing Phase 6A L1C/L2A protocol or results.

The extractor maps ACOLITE `L2R_rhos` bands nearest 665, 705 and 740 nm to the
logical B4, B5 and B6 inputs. `rhos` is used rather than `Rrs` because ACOLITE
defines surface reflectance as `rhos = pi * Rrs`, and the existing Phase 6A
indices are reflectance-based. The actual selected wavelength and GeoTIFF path
are retained in every successful record.

All source-product directories discovered under `ACOLITE_ERKEN` are extracted,
including dates outside the Phase 6A interval. The committed Phase 6A pairing
audit is then joined as a comparison-subset annotation:

- the exact paired L1C product ID identifies the Phase 6A-comparable subset;
- products outside that subset remain in the ACOLITE product master and are
  labelled explicitly;
- missing, duplicate or ambiguous products and bands are explicit failures;
- the alignment audit retains every Phase 6A candidate date, including dates
  rejected by the frozen upstream gate and exact products absent from the
  ACOLITE archive.

The product-level master never drops same-day products. For the date-level
master, one product is used only when it is unique or when exactly one product
is the already-frozen Phase 6A exact L1C match. Otherwise, the date remains an
explicit ambiguous record rather than receiving a silent selection.

The ACOLITE `l2_flags` raster is decoded as a bit field. Non-water/SWIR,
cirrus, high-TOA, out-of-scene and DEM-shadow bits are hard invalid. Negative
surface reflectance remains a diagnostic and is not clipped, preserving the
Phase 6A treatment of negative reflectance. Every configured flag count is
reported separately. When the archived ACOLITE settings declare flag-exponent
positions, the extractor verifies them against the configured mapping and
fails explicitly on a mismatch; undeclared positions use the recorded ACOLITE
official defaults rather than being inferred from observed pixel values.

The analysis grid is 20 m. Native 20 m ACOLITE rasters are read directly;
exactly nested 10 m rasters are reduced using 2×2 block means for continuous
reflectance and conservative any-flagged reduction for QA. Any other
resolution, grid disagreement, incomplete station window or reprojection need
is an explicit failure. No interpolating resampling is performed.

NDCI, MCI, the numerical denominator guard, nominal MCI wavelengths and the
1×1, 3×3, 5×5, 7×7 and 11×11 windows match the Phase 6A definitions. The 3×3
window remains primary; the other windows are descriptive sensitivity cases.
The final minimum valid-pixel threshold remains unselected.

Configuration:
[`erken_acolite_observation_extraction_v1.0.yaml`](../config/erken_acolite_observation_extraction_v1.0.yaml).

Server command and expected layout:
[`results/phase6b/acolite/README.md`](../results/phase6b/acolite/README.md).
