"""Native Sentinel-2 product/band QA extraction and canonicalization.

This layer is kept strictly separate from the inherited frozen L2A-SCL
date/product gate. Native QA never replaces the frozen SCL rule; it adds
pixel-level provenance beneath it.

Two things this module refuses to do:

* invent a QA field the source product does not support; and
* treat a missing or unreadable QA family as "clean". Absence is recorded per
  family and the observation is flagged ``native_qa_incomplete``.

QA60 alone is never treated as the QA system. Canonical flags are split into
hard-invalid conditions (the radiometry is absent, lost, or optically
incompatible with a water-leaving signal) and diagnostic degradation conditions
retained for audit and possible later human freeze. That split is read from the
configuration, never decided from CHLF or index performance.

**Band-specific QA stays band-specific.** ``MSK_QUALIT`` is distributed per
spectral band, so a defect reported for B6 must not invalidate NDCI, whose
primary validity is B4 AND B5 only. This module therefore produces one
hard-invalid mask per band plus a separate common/product-level mask for
conditions that genuinely apply to every band (``MSK_CLASSI`` cloud/cirrus/snow
and the SCL water context).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .s2_safe import QAAsset, SAFEProduct, canonical_band_name


class NativeQAError(ValueError):
    """Raised when a native QA asset cannot be interpreted without guessing."""


QA_ASSET_PRESENT = "present"
QA_ASSET_ABSENT = "absent"
QA_ASSET_UNREADABLE = "unreadable"
QA_ASSET_UNSUPPORTED_FORMAT = "unsupported_format_vector_gml"
QA_ASSET_BAND_COUNT_MISMATCH = "band_count_mismatch"

COMMON_BAND_KEY = "__common__"


@dataclass
class QALayer:
    """One canonical QA condition resolved onto the target window.

    ``band`` is the spectral band the condition was reported for, or ``None``
    for a product-level condition that applies to every band.
    """

    name: str
    flags: np.ndarray
    source_family: str
    source_relative_path: str | None
    category: str
    band: str | None = None

    @property
    def key(self) -> str:
        """Return the provenance-preserving layer key used in outputs."""

        return f"{self.band}_{self.name}" if self.band else self.name


@dataclass
class NativeQAResult:
    """Canonical QA for one product on the frozen target window.

    ``hard_invalid_by_band`` holds the band-specific hard-invalid mask for each
    requested band; ``common_hard_invalid`` holds the product-level conditions
    that apply to all bands. A band's effective invalidity is the union of the
    two, which is what :func:`twinwater_timesat.s2_indices.band_validity`
    consumes.
    """

    common_hard_invalid: np.ndarray
    hard_invalid_by_band: dict[str, np.ndarray] = field(default_factory=dict)
    layers: dict[str, QALayer] = field(default_factory=dict)
    asset_status: dict[str, str] = field(default_factory=dict)
    incomplete_families: tuple[str, ...] = ()

    @property
    def native_qa_incomplete(self) -> bool:
        """True when at least one configured QA family was not usable."""

        return bool(self.incomplete_families)

    def hard_invalid_for(self, band: str) -> np.ndarray:
        """Return the effective hard-invalid mask for one band."""

        key = canonical_band_name(band)
        band_mask = self.hard_invalid_by_band.get(key)
        if band_mask is None:
            return self.common_hard_invalid.copy()
        return band_mask | self.common_hard_invalid

    def counts(self) -> dict[str, int]:
        """Return per-layer failing-pixel counts, keeping band provenance."""

        return {
            layer.key: int(np.count_nonzero(layer.flags))
            for layer in sorted(self.layers.values(), key=lambda item: item.key)
        }


def select_qa_asset(
    product: SAFEProduct, family: str, *, band: str | None = None
) -> tuple[QAAsset | None, str]:
    """Select one native QA asset for a family, reporting an explicit status.

    The requested band is canonicalized the same way discovered assets are, so a
    ``B4`` request matches a ``B04`` asset. A band-specific request never falls
    back to another spectral band's mask: if the requested per-band asset is
    absent, the family/band is reported absent rather than silently satisfied by
    an unrelated band.
    """

    candidates = list(product.qa_family(family))
    if not candidates:
        return None, QA_ASSET_ABSENT

    if band is not None:
        wanted = canonical_band_name(band)
        band_matches = [asset for asset in candidates if asset.band == wanted]
        if band_matches:
            candidates = band_matches
        else:
            # Product-level assets (B00-style) legitimately apply to all bands.
            # Anything else would be a different spectral band's mask.
            product_level = [asset for asset in candidates if asset.band is None]
            if not product_level:
                return None, QA_ASSET_ABSENT
            candidates = product_level
    else:
        product_level = [asset for asset in candidates if asset.band is None]
        if product_level:
            candidates = product_level

    rasters = [asset for asset in candidates if asset.is_raster]
    if not rasters:
        # Older baselines distribute GML vector masks. Phase 6A does not
        # rasterize them here; the gap is recorded rather than assumed clean.
        return candidates[0], QA_ASSET_UNSUPPORTED_FORMAT

    if len(rasters) > 1:
        rasters.sort(key=lambda asset: asset.relative_path)
    return rasters[0], QA_ASSET_PRESENT


def decode_multiband_mask(
    values: np.ndarray, band_names: Sequence[str], *, family: str
) -> dict[str, np.ndarray]:
    """Map a multi-band native mask onto its configured condition names.

    The actual band count is verified against the configured ordering. A
    mismatch is an explicit failure, because silently assuming an ordering is
    exactly the kind of hidden assumption Phase 6A forbids.
    """

    array = np.asarray(values)
    if array.ndim != 3:
        raise NativeQAError(
            f"{family} mask must be read as a 3-D (band, row, col) array; got "
            f"shape {array.shape}."
        )
    if array.shape[0] != len(band_names):
        raise NativeQAError(
            f"{family} mask declares {array.shape[0]} band(s) but the "
            f"configuration names {len(band_names)}: {list(band_names)}. "
            "Phase 6A refuses to guess the band ordering."
        )
    return {
        str(name): array[index].astype(bool)
        for index, name in enumerate(band_names)
    }


def scl_water_mask(scl_values: np.ndarray, *, water_class: int = 6) -> np.ndarray:
    """Return the pixel-level water-context mask from the paired L2A SCL.

    This is the common water context for both L1C and L2A so the two levels are
    evaluated on a comparable spatial support. Cloud, cirrus, snow, non-water
    and invalid classes are excluded by construction.
    """

    return np.asarray(scl_values) == int(water_class)


def _classify(name: str, hard: set[str], diagnostic: set[str]) -> str:
    if name in hard:
        return "hard_invalid"
    if name in diagnostic:
        return "diagnostic"
    raise NativeQAError(
        f"QA condition {name!r} is not classified as hard_invalid or "
        "diagnostic in the pilot configuration; Phase 6A does not categorize "
        "an unconfigured flag on its own."
    )


def build_native_qa(
    *,
    band_condition_flags: Mapping[str, Mapping[str, np.ndarray]],
    common_condition_flags: Mapping[str, np.ndarray],
    asset_status: Mapping[str, str],
    hard_invalid_flags: Sequence[str],
    diagnostic_flags: Sequence[str],
    source_families: Mapping[str, str],
    source_paths: Mapping[str, str | None],
    window_shape: tuple[int, int],
    bands: Sequence[str],
    water_mask: np.ndarray | None = None,
) -> NativeQAResult:
    """Canonicalize decoded native QA into band-specific and common hard masks.

    ``band_condition_flags`` maps a spectral band to its own decoded conditions
    (typically from that band's ``MSK_QUALIT``). ``common_condition_flags``
    holds product-level conditions such as ``MSK_CLASSI`` cloud/cirrus/snow.
    """

    hard_set = {str(name) for name in hard_invalid_flags}
    diagnostic_set = {str(name) for name in diagnostic_flags}
    canonical_bands = [canonical_band_name(band) for band in bands]

    layers: dict[str, QALayer] = {}
    common_hard = np.zeros(window_shape, dtype=bool)
    by_band: dict[str, np.ndarray] = {
        band: np.zeros(window_shape, dtype=bool) for band in canonical_bands
    }

    def _check_shape(name: str, flags: np.ndarray, label: str) -> np.ndarray:
        array = np.asarray(flags).astype(bool)
        if array.shape != window_shape:
            raise NativeQAError(
                f"QA condition {label} has shape {array.shape}; expected "
                f"{window_shape} on the frozen target window."
            )
        return array

    for band, conditions in band_condition_flags.items():
        key = canonical_band_name(band)
        if key not in by_band:
            raise NativeQAError(
                f"Band-specific QA was supplied for {band!r}, which is not one "
                f"of the requested pilot bands {canonical_bands}."
            )
        for name, flags in conditions.items():
            array = _check_shape(name, flags, f"{key}:{name}")
            category = _classify(name, hard_set, diagnostic_set)
            if category == "hard_invalid":
                by_band[key] |= array
            layer = QALayer(
                name=name,
                flags=array,
                source_family=str(source_families.get(f"{key}:{name}", "QUALIT")),
                source_relative_path=source_paths.get(f"{key}:{name}"),
                category=category,
                band=key,
            )
            layers[layer.key] = layer

    for name, flags in common_condition_flags.items():
        array = _check_shape(name, flags, name)
        category = _classify(name, hard_set, diagnostic_set)
        if category == "hard_invalid":
            common_hard |= array
        layer = QALayer(
            name=name,
            flags=array,
            source_family=str(source_families.get(name, "CLASSI")),
            source_relative_path=source_paths.get(name),
            category=category,
            band=None,
        )
        layers[layer.key] = layer

    if water_mask is not None:
        water = _check_shape("scl_not_water", water_mask, "scl_not_water")
        not_water = ~water
        common_hard |= not_water
        layers["scl_not_water"] = QALayer(
            name="scl_not_water",
            flags=not_water,
            source_family="SCL",
            source_relative_path=source_paths.get("scl_not_water"),
            category="hard_invalid",
            band=None,
        )

    incomplete = tuple(
        sorted(
            family
            for family, status in asset_status.items()
            if status != QA_ASSET_PRESENT
        )
    )

    return NativeQAResult(
        common_hard_invalid=common_hard,
        hard_invalid_by_band=by_band,
        layers=layers,
        asset_status=dict(asset_status),
        incomplete_families=incomplete,
    )


def qa_inventory_rows(
    product: SAFEProduct,
    *,
    families: Iterable[str],
    bands: Sequence[str],
) -> list[dict[str, Any]]:
    """Inventory the native QA assets a product actually contains.

    Missing and unsupported mask families are reported explicitly so the audit
    describes real archive heterogeneity across processing baselines.
    """

    rows: list[dict[str, Any]] = []
    for family in families:
        assets = product.qa_family(family)
        if not assets:
            rows.append(
                {
                    "product_id": product.product_id,
                    "product_level": product.level,
                    "qa_family": family,
                    "band": None,
                    "asset_relative_path": None,
                    "declared_resolution_m": None,
                    "asset_kind": None,
                    "asset_status": QA_ASSET_ABSENT,
                    "band_specific": None,
                }
            )
            continue
        for asset in assets:
            rows.append(
                {
                    "product_id": product.product_id,
                    "product_level": product.level,
                    "qa_family": family,
                    "band": asset.band,
                    "asset_relative_path": asset.relative_path,
                    "declared_resolution_m": asset.declared_resolution_m,
                    "asset_kind": "raster" if asset.is_raster else "vector",
                    "asset_status": (
                        QA_ASSET_PRESENT
                        if asset.is_raster
                        else QA_ASSET_UNSUPPORTED_FORMAT
                    ),
                    "band_specific": asset.band is not None,
                }
            )

    for asset in product.scl_assets:
        rows.append(
            {
                "product_id": product.product_id,
                "product_level": product.level,
                "qa_family": "SCL",
                "band": None,
                "asset_relative_path": asset.relative_path,
                "declared_resolution_m": asset.declared_resolution_m,
                "asset_kind": "raster",
                "asset_status": QA_ASSET_PRESENT,
                "band_specific": False,
            }
        )
    return rows
