"""Phase 6A orchestration: real Erken Sentinel-2 L1C / official L2A observation.

Processing order is fixed and enforced here:

    product pairing
    -> radiometric metadata harmonization
    -> native QA extraction
    -> frozen L2A SCL gate
    -> common 20 m grid
    -> pixel-level QA intersection
    -> NDCI / MCI
    -> spatial summary

QA is applied before index calculation and before spatial aggregation. The
pipeline stops after the QA/availability outputs; it never inspects CHLF, never
computes index-versus-field performance, never ranks L1C against L2A, and never
runs TIMESAT.
"""

from __future__ import annotations

import csv
import json
import platform as platform_module
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import rasterio
from rasterio.windows import Window

from .s2_grid import (
    GridAlignmentError,
    GridSpec,
    assert_same_grid,
    block_mean_reduce,
    categorical_any_invalid_reduce,
    coarse_window_for_target,
    extract_target_window_from_coarse,
    grid_spec_from_dataset,
    nesting_factor,
)
from .s2_indices import (
    IndexComputationError,
    band_validity,
    common_band_validity,
    compute_mci,
    compute_ndci,
    index_validity,
    mci_baseline_coefficient,
)
from .s2_native_qa import (
    NativeQAError,
    QA_ASSET_ABSENT,
    QA_ASSET_PRESENT,
    QA_ASSET_UNREADABLE,
    build_native_qa,
    decode_multiband_mask,
    qa_inventory_rows,
    scl_water_mask,
    select_qa_asset,
)
from .s2_pairing import (
    PAIRING_EXACT_UNIQUE,
    PAIRING_NO_L2A_REPRESENTATIVE,
    PAIRING_ROOT_NOT_PROVIDED,
    AcquisitionIdentity,
    PairingResult,
    build_identity,
    pair_l1c_to_l2a,
    pairing_audit_row,
)
from .s2_pilot_config import (
    PilotConfig,
    PilotScopeError,
    assert_no_prohibited_site,
    assert_output_path_allowed,
    assert_permitted_product_level,
    assert_portable_rows,
    sha256_of_file,
)
from .s2_pilot_summary import (
    attrition_table,
    qa_failure_counts,
    render_native_qa_audit,
    render_qa_findings,
    summarize_index_window,
    write_markdown,
    write_rows,
)
from .s2_radiometry import (
    RadiometryError,
    read_product_radiometry,
    reflectance_range_flags,
    sensing_metadata,
    to_physical_reflectance,
)
from .s2_safe import (
    SAFEDiscoveryError,
    SAFEProduct,
    canonical_band_name,
    discover_products,
    load_product,
    select_band_asset,
)
from .s2_scl import station_to_pixel, transform_station_coordinate

# Which native QA families contribute to canonical validity, and whether each is
# band-specific, is declared in the pilot configuration rather than fixed here,
# so the documented rule and the executed rule cannot drift apart. QA60 /
# MSK_CLOUDS is deliberately absent from those lists: it is inventoried for
# provenance only and is never the QA system, alone or otherwise.
DEFAULT_BAND_SPECIFIC_QA_FAMILIES: tuple[str, ...] = ("QUALIT",)
DEFAULT_COMMON_QA_FAMILIES: tuple[str, ...] = ("CLASSI",)

# Families inventoried for the archive audit, whether or not they feed validity.
INVENTORIED_QA_FAMILIES: tuple[str, ...] = (
    "QUALIT",
    "CLASSI",
    "DETFOO",
    "NODATA",
    "SATURA",
    "DEFECT",
    "TECQUA",
    "CLOUDS",
    "CLDPRB",
    "SNWPRB",
)


class PilotExecutionError(RuntimeError):
    """Raised when Phase 6A cannot proceed without a silent assumption."""


@dataclass
class ExtractionOutcome:
    """The result of extracting one product onto the frozen 3x3 window."""

    row: dict[str, Any]
    failure_reason: str | None = None


@dataclass
class PilotRunResult:
    """Everything one Phase 6A run produced, ready to be written and reported."""

    pairing_rows: list[dict[str, Any]] = field(default_factory=list)
    qa_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    extraction_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Frozen inputs
# ---------------------------------------------------------------------------


def read_frozen_observation_mask(path: str | Path) -> list[dict[str, Any]]:
    """Read the frozen date-level SCL observation mask without modifying it."""

    source = Path(path)
    if not source.is_file():
        raise PilotExecutionError(
            f"Frozen observation mask not found: {source}. Phase 6A inherits it "
            "and never regenerates it."
        )
    with source.open(encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise PilotExecutionError(f"Frozen observation mask is empty: {source}.")
    return rows


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Archive indexing
# ---------------------------------------------------------------------------


def index_archive(
    root: str | Path | None,
    *,
    level: str,
    config: PilotConfig,
) -> dict[str, SAFEProduct]:
    """Index one archive root by product identifier, refusing out-of-scope input."""

    if root is None:
        return {}
    assert_permitted_product_level(level, config)
    assert_no_prohibited_site(root, config, context=f"{level} archive root")

    products: dict[str, SAFEProduct] = {}
    for product_path in discover_products(root, level=level):
        assert_no_prohibited_site(
            product_path.name, config, context=f"{level} product name"
        )
        try:
            product = load_product(product_path)
        except SAFEDiscoveryError:
            continue
        if product.level != level.upper():
            continue
        products[product.product_id] = product
    return products


def archive_identities(
    products: Mapping[str, SAFEProduct], *, level: str
) -> list[AcquisitionIdentity]:
    """Build acquisition identities from product metadata, then product names."""

    identities: list[AcquisitionIdentity] = []
    for product_id, product in sorted(products.items()):
        metadata = sensing_metadata(product.root, level)
        identities.append(
            build_identity(
                product_id=product_id,
                level=level,
                name_fallback=product.root.name,
                metadata=metadata,
            )
        )
    return identities


# ---------------------------------------------------------------------------
# Window extraction
# ---------------------------------------------------------------------------


def _read_window(
    dataset: Any, *, row: int, col: int, size: int
) -> np.ndarray:
    """Read an unpadded window, failing if the frozen window is not complete."""

    half = size // 2
    row_start = row - half
    col_start = col - half
    if (
        row_start < 0
        or col_start < 0
        or row_start + size > dataset.height
        or col_start + size > dataset.width
    ):
        raise GridAlignmentError(
            "The frozen 3x3 window is not fully inside the raster; Phase 6A "
            "does not pad the window."
        )
    window = Window(col_off=col_start, row_off=row_start, width=size, height=size)
    return dataset.read(window=window, boundless=False)


def _read_target_band(
    product: SAFEProduct,
    band: str,
    *,
    target: GridSpec,
    target_row: int,
    target_col: int,
    window_size: int,
    prefer_resolution_m: int,
    grid_config: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read one band onto the frozen target window, reducing 10 m B4 if needed.

    Continuous reflectance is only ever reduced by block averaging; a band that
    is neither on the target grid nor exactly nested inside it is an explicit
    failure.
    """

    asset = select_band_asset(product, band, prefer_resolution_m=prefer_resolution_m)
    origin_tolerance = float(grid_config.get("origin_tolerance_m", 1e-3))
    pixel_tolerance = float(grid_config.get("pixel_size_tolerance_m", 1e-3))

    with rasterio.open(asset.path) as dataset:
        spec = grid_spec_from_dataset(dataset)
        provenance: dict[str, Any] = {
            f"{band}_asset_relative_path": asset.relative_path,
            f"{band}_native_pixel_size_m": spec.pixel_size_x,
            f"{band}_grid_alignment": None,
        }

        if (
            abs(spec.pixel_size_x - target.pixel_size_x) <= pixel_tolerance
            and abs(spec.pixel_size_y - target.pixel_size_y) <= pixel_tolerance
        ):
            assert_same_grid(
                spec,
                target,
                origin_tolerance_m=origin_tolerance,
                pixel_size_tolerance_m=pixel_tolerance,
                left_label=f"{band} raster",
                right_label="target 20 m grid",
            )
            values = _read_window(
                dataset, row=target_row, col=target_col, size=window_size
            )[0]
            provenance[f"{band}_grid_alignment"] = "native_target_grid"
            return values.astype("float64"), provenance

        factor = nesting_factor(
            spec,
            target,
            origin_tolerance_m=origin_tolerance,
            pixel_size_tolerance_m=pixel_tolerance,
            fine_label=f"{band} raster",
            coarse_label="target 20 m grid",
        )
        fine_row = target_row * factor
        fine_col = target_col * factor
        half = window_size // 2
        fine_start_row = (target_row - half) * factor
        fine_start_col = (target_col - half) * factor
        fine_size = window_size * factor
        if (
            fine_start_row < 0
            or fine_start_col < 0
            or fine_start_row + fine_size > dataset.height
            or fine_start_col + fine_size > dataset.width
        ):
            raise GridAlignmentError(
                f"The frozen window footprint is not fully inside the {band} "
                "raster at its native resolution."
            )
        window = Window(
            col_off=fine_start_col,
            row_off=fine_start_row,
            width=fine_size,
            height=fine_size,
        )
        fine_values = dataset.read(1, window=window, boundless=False).astype("float64")

    reduced = block_mean_reduce(fine_values, factor)
    provenance[f"{band}_grid_alignment"] = f"block_mean_reduce_x{factor}"
    return reduced, provenance


def _read_categorical_window(
    path: str | Path,
    *,
    target: GridSpec,
    target_row: int,
    target_col: int,
    window_size: int,
    grid_config: Mapping[str, Any],
    boolean_conditions: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a categorical mask onto the target window without interpolation.

    Native Sentinel-2 QA masks are distributed at several resolutions -
    ``MSK_QUALIT`` follows its spectral band (10 m for B4, 20 m for B5/B6) while
    ``MSK_CLASSI`` is 60 m - so all three geometries are handled explicitly:

    A. mask already on the target grid -> exact target window;
    B. mask coarser than the target -> exact footprint expansion;
    C. mask finer than the target -> exact nested conservative any-invalid
       reduction, where a target pixel is flagged when ANY contributing fine
       pixel is flagged.

    Case C is only meaningful for Boolean condition masks; ``boolean_conditions``
    must be ``False`` for a multi-class layer such as SCL, which then refuses to
    be reduced rather than inventing a class value. Grids that are not exactly
    nested and co-registered fail explicitly.

    Returns the window plus provenance naming the case applied and the mask's
    observed native pixel size. Official QA filenames carry no resolution token,
    so the observed size is the only trustworthy record of it.
    """

    origin_tolerance = float(grid_config.get("origin_tolerance_m", 1e-3))
    pixel_tolerance = float(grid_config.get("pixel_size_tolerance_m", 1e-3))

    with rasterio.open(path) as dataset:
        spec = grid_spec_from_dataset(dataset)

        # --- case A: already on the frozen target grid -----------------------
        if (
            abs(spec.pixel_size_x - target.pixel_size_x) <= pixel_tolerance
            and abs(spec.pixel_size_y - target.pixel_size_y) <= pixel_tolerance
        ):
            assert_same_grid(
                spec,
                target,
                origin_tolerance_m=origin_tolerance,
                pixel_size_tolerance_m=pixel_tolerance,
                left_label="categorical mask",
                right_label="target 20 m grid",
            )
            values = _read_window(
                dataset, row=target_row, col=target_col, size=window_size
            )
            return values, {
                "alignment": "native_target_grid",
                "native_pixel_size_m": spec.pixel_size_x,
            }

        half = window_size // 2

        # --- case C: mask finer than the target grid -------------------------
        if spec.pixel_size_x < target.pixel_size_x:
            if not boolean_conditions:
                raise GridAlignmentError(
                    f"Categorical mask at {spec.pixel_size_x} m is finer than "
                    f"the {target.pixel_size_x} m target grid, but it is not a "
                    "Boolean condition mask; Phase 6A will not reduce a "
                    "multi-class layer and refuses to invent a class value."
                )
            factor = nesting_factor(
                spec,
                target,
                origin_tolerance_m=origin_tolerance,
                pixel_size_tolerance_m=pixel_tolerance,
                fine_label="categorical mask",
                coarse_label="target 20 m grid",
            )
            fine_start_row = (target_row - half) * factor
            fine_start_col = (target_col - half) * factor
            fine_size = window_size * factor
            if (
                fine_start_row < 0
                or fine_start_col < 0
                or fine_start_row + fine_size > dataset.height
                or fine_start_col + fine_size > dataset.width
            ):
                raise GridAlignmentError(
                    "Fine categorical mask does not cover the frozen window."
                )
            fine = dataset.read(
                window=Window(
                    col_off=fine_start_col,
                    row_off=fine_start_row,
                    width=fine_size,
                    height=fine_size,
                ),
                boundless=False,
            )
            reduced = np.stack(
                [
                    categorical_any_invalid_reduce(fine[index] != 0, factor)
                    for index in range(fine.shape[0])
                ]
            )
            return reduced.astype("uint8"), {
                "alignment": f"any_invalid_reduce_x{factor}",
                "native_pixel_size_m": spec.pixel_size_x,
            }

        # --- case B: mask coarser than the target grid -----------------------
        factor = nesting_factor(
            target,
            spec,
            origin_tolerance_m=origin_tolerance,
            pixel_size_tolerance_m=pixel_tolerance,
            fine_label="target 20 m grid",
            coarse_label="categorical mask",
        )
        row_start, col_start, size = coarse_window_for_target(
            target_row=target_row - half,
            target_col=target_col - half,
            target_size=window_size,
            factor=factor,
        )
        if (
            row_start < 0
            or col_start < 0
            or row_start + size > dataset.height
            or col_start + size > dataset.width
        ):
            raise GridAlignmentError(
                "Coarse categorical mask does not cover the frozen window."
            )
        window = Window(
            col_off=col_start, row_off=row_start, width=size, height=size
        )
        coarse = dataset.read(window=window, boundless=False)
        coarse_pixel_size = spec.pixel_size_x

    expanded = np.stack(
        [
            extract_target_window_from_coarse(
                coarse[index],
                coarse_row_offset=row_start,
                coarse_col_offset=col_start,
                target_row=target_row - window_size // 2,
                target_col=target_col - window_size // 2,
                target_size=window_size,
                factor=factor,
            )
            for index in range(coarse.shape[0])
        ]
    )
    return expanded, {
        "alignment": f"exact_footprint_expand_x{factor}",
        "native_pixel_size_m": coarse_pixel_size,
    }


# ---------------------------------------------------------------------------
# Per-product extraction
# ---------------------------------------------------------------------------


def extract_product(
    product: SAFEProduct,
    *,
    config: PilotConfig,
    scl_product: SAFEProduct | None,
    base_row: Mapping[str, Any],
) -> ExtractionOutcome:
    """Extract reflectance, QA and indices for one product on the frozen window.

    Every failure mode returns an explicit ``failure_reason`` and keeps the row,
    so no date or product is silently dropped for being inconvenient.
    """

    row: dict[str, Any] = dict(base_row)
    inherited = config.section("inherited_frozen")
    radiometry_config = config.section("radiometry")
    grid_config = config.section("grid")
    qa_config = config.section("native_qa")
    index_config = config.section("indices")
    summary_config = config.section("spatial_summary")

    bands = tuple(str(band) for band in radiometry_config["pilot_bands"])
    window_size = int(summary_config["window_size"])
    window_pixels = window_size * window_size
    target_resolution = int(grid_config["target_resolution_m"])
    station = inherited["station"]

    row["product_level"] = product.level
    row["native_qa_incomplete"] = None

    # --- radiometric metadata -------------------------------------------------
    try:
        product_radiometry = read_product_radiometry(
            product.root,
            product_id=product.product_id,
            level=product.level,
            bands=bands,
            canonical_band_ids=radiometry_config["canonical_band_ids"],
            missing_offset_list_is_zero_offset=bool(
                radiometry_config.get("missing_offset_list_is_zero_offset", True)
            ),
            offset_convention_minimum_baseline=str(
                radiometry_config.get(
                    "offset_convention_minimum_baseline", "N0400"
                )
            ),
        )
    except RadiometryError as error:
        row["failure_reason"] = f"radiometric_metadata_unusable: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    row["quantification_value"] = product_radiometry.quantification_value
    row["product_metadata_relative_path"] = product_radiometry.metadata_relative_path
    row["radiometry_processing_baseline"] = product_radiometry.processing_baseline
    row["radiometry_processing_baseline_source"] = (
        product_radiometry.processing_baseline_source
    )
    row["radiometry_offset_expected_for_baseline"] = product_radiometry.offset_expected
    for band, terms in product_radiometry.bands.items():
        row[f"{band}_band_id"] = terms.band_id
        row[f"{band}_band_id_source"] = terms.band_id_source
        row[f"{band}_add_offset"] = terms.add_offset
        row[f"{band}_offset_source"] = terms.offset_source
        row[f"{band}_conversion_rule"] = terms.conversion_rule()
        row[f"{band}_product_central_wavelength_nm"] = terms.central_wavelength_nm

    # --- target grid ----------------------------------------------------------
    try:
        target_asset = select_band_asset(
            product, "B5", prefer_resolution_m=target_resolution
        )
        with rasterio.open(target_asset.path) as dataset:
            target = grid_spec_from_dataset(dataset)
        if abs(target.pixel_size_x - target_resolution) > float(
            grid_config.get("pixel_size_tolerance_m", 1e-3)
        ):
            raise GridAlignmentError(
                f"B5 raster pixel size {target.pixel_size_x} m does not define "
                f"the frozen {target_resolution} m analysis grid."
            )
    except (SAFEDiscoveryError, GridAlignmentError, rasterio.RasterioIOError) as error:
        row["failure_reason"] = f"target_grid_unresolved: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    row.update(
        {f"target_grid_{key}": value for key, value in target.audit().items()}
    )

    try:
        station_x, station_y = transform_station_coordinate(
            station_lon=float(station["longitude"]),
            station_lat=float(station["latitude"]),
            station_crs=str(station["crs"]),
            raster_crs=target.crs,
        )
    except Exception as error:  # noqa: BLE001 - reported, never silently absorbed
        row["failure_reason"] = f"station_projection_failed: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    location = station_to_pixel(
        target.transform,
        raster_width=target.width,
        raster_height=target.height,
        station_x=station_x,
        station_y=station_y,
    )
    row["station_row"] = location.row
    row["station_col"] = location.col
    row["station_inside_raster"] = location.inside
    if not location.inside:
        row["failure_reason"] = "station_outside_raster"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    # --- reflectance ----------------------------------------------------------
    reflectance: dict[str, np.ndarray] = {}
    try:
        for band in bands:
            digital_numbers, provenance = _read_target_band(
                product,
                band,
                target=target,
                target_row=location.row,
                target_col=location.col,
                window_size=window_size,
                prefer_resolution_m=target_resolution,
                grid_config=grid_config,
            )
            row.update(provenance)
            terms = product_radiometry.bands[band]
            values = to_physical_reflectance(digital_numbers, terms)
            reflectance[band] = values
            flags = reflectance_range_flags(
                values,
                minimum=float(radiometry_config["diagnostic_reflectance_min"]),
                maximum=float(radiometry_config["diagnostic_reflectance_max"]),
            )
            for name, mask in flags.items():
                row[f"{band}_reflectance_{name}_count"] = int(
                    np.count_nonzero(mask)
                )
            row[f"{band}_reflectance_mean_diagnostic"] = (
                float(np.nanmean(values)) if np.any(np.isfinite(values)) else None
            )
    except (
        SAFEDiscoveryError,
        GridAlignmentError,
        rasterio.RasterioIOError,
    ) as error:
        row["failure_reason"] = f"reflectance_extraction_failed: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    # --- native QA ------------------------------------------------------------
    # MSK_QUALIT is per spectral band and stays band-specific; MSK_CLASSI is
    # product-level and applies to every band. Collapsing the two would let a
    # B6-only defect invalidate NDCI, which requires B4 and B5 only.
    band_condition_flags: dict[str, dict[str, np.ndarray]] = {}
    common_condition_flags: dict[str, np.ndarray] = {}
    source_families: dict[str, str] = {}
    source_paths: dict[str, str | None] = {}
    asset_status: dict[str, str] = {}
    window_shape = (window_size, window_size)

    qualit_names = [str(name) for name in qa_config["msk_qualit_bands"]]
    classi_names = [str(name) for name in qa_config["msk_classi_bands"]]
    hard_flags = [str(name) for name in qa_config["hard_invalid_flags"]]
    diagnostic_flags = [str(name) for name in qa_config["diagnostic_flags"]]
    configured = set(hard_flags) | set(diagnostic_flags)

    family_band_names = {"QUALIT": qualit_names, "CLASSI": classi_names}
    qa_families: list[tuple[str, list[str], bool]] = []
    for family in qa_config.get(
        "band_specific_qa_families", DEFAULT_BAND_SPECIFIC_QA_FAMILIES
    ):
        qa_families.append((str(family), family_band_names[str(family)], True))
    for family in qa_config.get("common_qa_families", DEFAULT_COMMON_QA_FAMILIES):
        qa_families.append((str(family), family_band_names[str(family)], False))

    for family, band_names, per_band in qa_families:
        targets = bands if per_band else (None,)
        family_status = QA_ASSET_ABSENT
        for band in targets:
            slot = canonical_band_name(band) if band is not None else "product"
            asset, status = select_qa_asset(product, family, band=band)
            if asset is None or status != QA_ASSET_PRESENT:
                asset_status[f"{family}:{slot}"] = status
                continue
            try:
                values, qa_geometry = _read_categorical_window(
                    asset.path,
                    target=target,
                    target_row=location.row,
                    target_col=location.col,
                    window_size=window_size,
                    grid_config=grid_config,
                    boolean_conditions=True,
                )
                decoded = decode_multiband_mask(values, band_names, family=family)
            except (
                GridAlignmentError,
                NativeQAError,
                rasterio.RasterioIOError,
            ) as error:
                asset_status[f"{family}:{slot}"] = QA_ASSET_UNREADABLE
                row[f"qa_{family.lower()}_{slot.lower()}_error"] = str(error)
                continue

            row[f"qa_{family.lower()}_{slot.lower()}_asset_relative_path"] = (
                asset.relative_path
            )
            row[f"qa_{family.lower()}_{slot.lower()}_grid_alignment"] = (
                qa_geometry["alignment"]
            )
            row[f"qa_{family.lower()}_{slot.lower()}_native_pixel_size_m"] = (
                qa_geometry["native_pixel_size_m"]
            )

            for name, flags in decoded.items():
                if name not in configured:
                    continue
                if per_band:
                    key = canonical_band_name(band)
                    slot_flags = band_condition_flags.setdefault(key, {})
                    existing = slot_flags.get(name)
                    slot_flags[name] = (
                        flags if existing is None else (existing | flags)
                    )
                    source_families[f"{key}:{name}"] = family
                    source_paths[f"{key}:{name}"] = asset.relative_path
                else:
                    existing = common_condition_flags.get(name)
                    common_condition_flags[name] = (
                        flags if existing is None else (existing | flags)
                    )
                    source_families[name] = family
                    source_paths[name] = asset.relative_path

            asset_status[f"{family}:{slot}"] = QA_ASSET_PRESENT
            family_status = QA_ASSET_PRESENT
        row[f"qa_family_{family.lower()}_status"] = family_status

    # --- frozen L2A SCL water context ----------------------------------------
    water_mask: np.ndarray | None = None
    water_config = qa_config["pixel_water_context"]
    if product.level.upper() in {
        str(level).upper() for level in water_config["applies_to"]
    }:
        if scl_product is None:
            row["failure_reason"] = (
                "no_paired_l2a_scl_for_common_water_context"
            )
            return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])
        if not scl_product.scl_assets:
            row["failure_reason"] = "paired_l2a_product_has_no_scl_raster"
            return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])
        scl_asset = min(
            scl_product.scl_assets,
            key=lambda asset: (
                0 if asset.declared_resolution_m == target_resolution else 1,
                asset.relative_path,
            ),
        )
        try:
            scl_window, scl_geometry = _read_categorical_window(
                scl_asset.path,
                target=target,
                target_row=location.row,
                target_col=location.col,
                window_size=window_size,
                grid_config=grid_config,
                boolean_conditions=False,
            )
            scl_values = scl_window[0]
        except (GridAlignmentError, rasterio.RasterioIOError) as error:
            row["failure_reason"] = f"scl_water_context_failed: {error}"
            return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])
        water_mask = scl_water_mask(
            scl_values, water_class=int(water_config["require_scl_class"])
        )
        source_paths["scl_not_water"] = scl_asset.relative_path
        row["scl_asset_relative_path"] = scl_asset.relative_path
        row["scl_grid_alignment"] = scl_geometry["alignment"]
        row["scl_native_pixel_size_m"] = scl_geometry["native_pixel_size_m"]
        row["scl_water_pixel_count"] = int(np.count_nonzero(water_mask))

    # --- canonicalize ---------------------------------------------------------
    try:
        qa_result = build_native_qa(
            band_condition_flags=band_condition_flags,
            common_condition_flags=common_condition_flags,
            asset_status=asset_status,
            hard_invalid_flags=hard_flags,
            diagnostic_flags=diagnostic_flags,
            source_families=source_families,
            source_paths=source_paths,
            window_shape=window_shape,
            bands=bands,
            water_mask=water_mask,
        )
    except NativeQAError as error:
        row["failure_reason"] = f"native_qa_canonicalization_failed: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    row["native_qa_incomplete"] = qa_result.native_qa_incomplete
    row["native_qa_incomplete_families"] = (
        ";".join(qa_result.incomplete_families) or None
    )
    row.update(qa_failure_counts(qa_result.layers, window_pixel_count=window_pixels))

    # --- validity and indices -------------------------------------------------
    try:
        validity = band_validity(
            reflectance,
            {
                band: qa_result.hard_invalid_by_band.get(
                    canonical_band_name(band), np.zeros(window_shape, dtype=bool)
                )
                for band in reflectance
            },
            common_hard_invalid=qa_result.common_hard_invalid,
        )
        ndci_valid = index_validity(
            validity, tuple(str(b) for b in index_config["ndci"]["required_bands"])
        )
        mci_valid = index_validity(
            validity, tuple(str(b) for b in index_config["mci"]["required_bands"])
        )
        common_valid = common_band_validity(validity)

        ndci = compute_ndci(
            reflectance["B4"],
            reflectance["B5"],
            valid=ndci_valid,
            denominator_epsilon=float(index_config["ndci"]["denominator_epsilon"]),
            require_positive_denominator=bool(
                index_config["ndci"]["require_positive_denominator"]
            ),
            theoretical_min=float(index_config["ndci"]["theoretical_min"]),
            theoretical_max=float(index_config["ndci"]["theoretical_max"]),
        )
        coefficient = mci_baseline_coefficient(
            index_config["nominal_central_wavelength_nm"]
        )
        mci = compute_mci(
            reflectance["B4"],
            reflectance["B5"],
            reflectance["B6"],
            valid=mci_valid,
            baseline_coefficient=coefficient,
        )
    except IndexComputationError as error:
        row["failure_reason"] = f"index_computation_failed: {error}"
        return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])

    for band in bands:
        row[f"{band}_valid_count"] = int(np.count_nonzero(validity[band]))
    row["common_B456_valid_count"] = int(np.count_nonzero(common_valid))
    row["mci_baseline_coefficient"] = coefficient

    row.update(
        summarize_index_window(
            ndci.values, ndci.valid, prefix="NDCI", window_pixel_count=window_pixels
        )
    )
    row.update(
        summarize_index_window(
            mci.values, mci.valid, prefix="MCI", window_pixel_count=window_pixels
        )
    )
    for name, count in ndci.diagnostic_counts().items():
        row[f"NDCI_diag_{name}"] = count
    for name, count in mci.diagnostic_counts().items():
        row[f"MCI_diag_{name}"] = count

    row["ndci_valid_pixel_count"] = row["NDCI_valid_pixel_count"]
    row["mci_valid_pixel_count"] = row["MCI_valid_pixel_count"]
    # Deliberately NOT named *_qc_pass: the final minimum valid-pixel threshold
    # is not frozen, so these state only that at least one pixel survived QA.
    row["ndci_has_any_valid_pixel"] = row["ndci_valid_pixel_count"] > 0
    row["mci_has_any_valid_pixel"] = row["mci_valid_pixel_count"] > 0
    row["final_valid_pixel_threshold_status"] = "NOT_SELECTED_REQUIRES_HUMAN_FREEZE"
    row["failure_reason"] = (
        None
        if row["ndci_valid_pixel_count"] or row["mci_valid_pixel_count"]
        else "no_valid_pixels_after_qa_in_frozen_3x3_window"
    )
    return ExtractionOutcome(row=row, failure_reason=row["failure_reason"])


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_pilot(
    *,
    config: PilotConfig,
    repository_root: str | Path,
    l2a_root: str | Path | None,
    l1c_root: str | Path | None,
) -> PilotRunResult:
    """Run the Phase 6A observation pilot over the frozen candidate dates."""

    root = Path(repository_root)
    inherited = config.section("inherited_frozen")
    pairing_config = config.section("pairing")

    mask_rows = read_frozen_observation_mask(
        root / str(inherited["observation_mask_table"])
    )

    l2a_products = index_archive(l2a_root, level="L2A", config=config)
    l1c_products = index_archive(l1c_root, level="L1C", config=config)
    l1c_identities = archive_identities(l1c_products, level="L1C")

    result = PilotRunResult()
    seen_qa_inventory: set[str] = set()

    for mask_row in mask_rows:
        date = str(mask_row.get("date", ""))
        year = _as_int(mask_row.get("year"))
        usable = _as_bool(mask_row.get("s2_date_usable"))
        product_id = (mask_row.get("selected_product_id") or "").strip() or None

        representative_status = (
            "frozen_representative"
            if product_id
            else "no_representative_frozen_scl_gate_failed"
        )

        l2a_identity: AcquisitionIdentity | None = None
        l2a_product = l2a_products.get(product_id) if product_id else None
        if product_id:
            metadata = (
                sensing_metadata(l2a_product.root, "L2A") if l2a_product else {}
            )
            l2a_identity = build_identity(
                product_id=product_id,
                level="L2A",
                name_fallback=product_id,
                metadata=metadata,
            )

        if l2a_identity is None:
            # The frozen SCL gate left this date without a representative
            # product, so there is nothing to pair; say exactly that.
            pairing = PairingResult(
                status=PAIRING_NO_L2A_REPRESENTATIVE,
                l1c=None,
                candidate_product_ids=(),
                detail=(
                    "The frozen SCL observation mask selected no representative "
                    "L2A product for this date."
                ),
            )
        else:
            pairing = pair_l1c_to_l2a(
                l2a_identity,
                l1c_identities,
                tolerance_seconds=float(
                    pairing_config["sensing_datetime_tolerance_seconds"]
                ),
                compare_orbit="relative_orbit"
                in [str(f) for f in pairing_config.get("optional_key_fields", [])],
                l1c_root_provided=l1c_root is not None,
            )

        result.pairing_rows.append(
            pairing_audit_row(
                date=date,
                year=year,
                l2a_representative_status=representative_status,
                scl_gate_pass=usable,
                l2a=l2a_identity,
                result=pairing,
            )
        )

        base_row: dict[str, Any] = {
            "date": date,
            "year": year,
            "scl_gate_pass": usable,
            "scl_gate_rule_id": str(inherited["scl_gate_rule_id"]),
            "l2a_representative_status": representative_status,
            "l1c_pairing_status": pairing.status,
            "failure_reason": None,
        }

        if not product_id:
            row = dict(base_row)
            row["product_level"] = None
            row["failure_reason"] = "no_frozen_representative_l2a_product_for_date"
            result.extraction_rows.append(row)
            result.failure_rows.append(row)
            continue

        # L2A extraction ------------------------------------------------------
        if l2a_product is None:
            row = dict(base_row)
            row["product_level"] = "L2A"
            row["product_id"] = product_id
            row["failure_reason"] = (
                "frozen_representative_l2a_product_not_found_in_archive"
                if l2a_root is not None
                else "l2a_root_not_provided"
            )
            result.extraction_rows.append(row)
            result.failure_rows.append(row)
        else:
            if l2a_product.product_id not in seen_qa_inventory:
                result.qa_inventory_rows.extend(
                    qa_inventory_rows(
                        l2a_product,
                        families=INVENTORIED_QA_FAMILIES,
                        bands=tuple(
                            str(band)
                            for band in config.section("radiometry")["pilot_bands"]
                        ),
                    )
                )
                seen_qa_inventory.add(l2a_product.product_id)

            row_base = dict(base_row)
            row_base.update(_identity_columns(l2a_identity))
            outcome = extract_product(
                l2a_product,
                config=config,
                scl_product=l2a_product,
                base_row=row_base,
            )
            result.extraction_rows.append(outcome.row)
            if outcome.failure_reason:
                result.failure_rows.append(outcome.row)

        # L1C extraction ------------------------------------------------------
        row_base = dict(base_row)
        if pairing.status != PAIRING_EXACT_UNIQUE:
            row = row_base
            row["product_level"] = "L1C"
            row["failure_reason"] = f"l1c_not_extracted: {pairing.status}"
            result.extraction_rows.append(row)
            result.failure_rows.append(row)
            continue

        l1c_product = l1c_products.get(pairing.l1c.product_id) if pairing.l1c else None
        if l1c_product is None:
            row = row_base
            row["product_level"] = "L1C"
            row["failure_reason"] = "paired_l1c_product_not_loadable"
            result.extraction_rows.append(row)
            result.failure_rows.append(row)
            continue

        if l1c_product.product_id not in seen_qa_inventory:
            result.qa_inventory_rows.extend(
                qa_inventory_rows(
                    l1c_product,
                    families=INVENTORIED_QA_FAMILIES,
                    bands=tuple(
                        str(band)
                        for band in config.section("radiometry")["pilot_bands"]
                    ),
                )
            )
            seen_qa_inventory.add(l1c_product.product_id)

        row_base.update(_identity_columns(pairing.l1c))
        outcome = extract_product(
            l1c_product,
            config=config,
            scl_product=l2a_product,
            base_row=row_base,
        )
        result.extraction_rows.append(outcome.row)
        if outcome.failure_reason:
            result.failure_rows.append(outcome.row)

    result.counts = _run_counts(result, mask_rows)
    return result


def _identity_columns(identity: AcquisitionIdentity | None) -> dict[str, Any]:
    if identity is None:
        return {}
    return {
        "product_id": identity.product_id,
        "sensing_datetime": identity.sensing_datetime_utc,
        "platform": identity.platform,
        "tile": identity.tile_id,
        "orbit": identity.relative_orbit,
        "processing_baseline": identity.processing_baseline,
        "generation_time": identity.generation_time_utc,
    }


def _run_counts(
    result: PilotRunResult, mask_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    representative = sum(
        1 for row in mask_rows if (row.get("selected_product_id") or "").strip()
    )
    exact_pairs = sum(
        1
        for row in result.pairing_rows
        if row["l1c_pairing_status"] == PAIRING_EXACT_UNIQUE
    )
    # Dates that never had an L2A representative are not L1C pairing failures.
    unresolved = sum(
        1
        for row in result.pairing_rows
        if row["l1c_pairing_status"]
        not in {
            PAIRING_EXACT_UNIQUE,
            PAIRING_ROOT_NOT_PROVIDED,
            PAIRING_NO_L2A_REPRESENTATIVE,
        }
    )
    no_representative = sum(
        1
        for row in result.pairing_rows
        if row["l1c_pairing_status"] == PAIRING_NO_L2A_REPRESENTATIVE
    )
    return {
        "candidate_dates": len(mask_rows),
        "frozen_representative_l2a_dates": representative,
        "dates_without_l2a_representative": no_representative,
        "exact_l1c_l2a_pairs": exact_pairs,
        "unmatched_or_ambiguous_dates": unresolved,
        "extraction_rows": len(result.extraction_rows),
        "failure_rows": len(result.failure_rows),
        "qa_inventory_rows": len(result.qa_inventory_rows),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _git_commit(repository_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover - git is present in this project
        return None
    output = completed.stdout.strip()
    return output or None


def build_provenance_manifest(
    *,
    config: PilotConfig,
    repository_root: str | Path,
    result: PilotRunResult,
    l1c_root_provided: bool,
    l2a_root_provided: bool,
) -> dict[str, Any]:
    """Build a portable provenance manifest; archive roots are never recorded."""

    root = Path(repository_root)
    inherited = config.section("inherited_frozen")

    governing: list[dict[str, Any]] = []
    for key in (
        "observation_mask_config",
        "observation_mask_table",
        "l2a_inventory_table",
    ):
        relative = str(inherited[key])
        path = root / relative
        governing.append(
            {
                "path": relative,
                "sha256": sha256_of_file(path) if path.is_file() else None,
            }
        )

    return {
        "pilot_version": config.pilot_version,
        "pilot_status": config.status,
        "processing_timestamp_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "pilot_config": {
            "path": config.source_relative_path,
            "sha256": config.sha256,
        },
        "inherited_frozen_governance": governing,
        "scl_gate_rule_id": str(inherited["scl_gate_rule_id"]),
        "mask_version": str(inherited["mask_version"]),
        "real_l1c_root_provided": bool(l1c_root_provided),
        "real_l2a_root_provided": bool(l2a_root_provided),
        "real_products_processed": int(
            sum(
                1
                for row in result.extraction_rows
                if row.get("product_metadata_relative_path")
            )
        ),
        "python_version": sys.version.split()[0],
        "platform": platform_module.platform(terse=True),
        "package_versions": {
            "numpy": np.__version__,
            "rasterio": rasterio.__version__,
        },
        "git_commit_at_run_time": _git_commit(root),
        "counts": dict(result.counts),
        "stopping_rule": (
            "Phase 6A stops after QA/availability outputs. No CHLF inspection, "
            "no field matchup, no index-versus-field performance, no L1C/L2A "
            "scientific ranking, and no TIMESAT reconstruction."
        ),
        "final_minimum_valid_pixel_threshold": "NOT_SELECTED_REQUIRES_HUMAN_FREEZE",
    }


def write_outputs(
    result: PilotRunResult,
    *,
    config: PilotConfig,
    repository_root: str | Path,
    output_root: str | Path,
    l1c_root_provided: bool,
    l2a_root_provided: bool,
) -> dict[str, Path]:
    """Write every Phase 6A output inside the isolated results/phase6a namespace."""

    root = Path(repository_root)
    files = config.section("outputs")["files"]
    attrition_config = config.section("attrition")
    thresholds = [int(value) for value in attrition_config["minimum_valid_pixel_thresholds"]]
    count_columns = {
        "NDCI": "ndci_valid_pixel_count",
        "MCI": "mci_valid_pixel_count",
        "common_B456": "common_B456_valid_count",
    }

    output_root_path = Path(output_root)
    written: dict[str, Path] = {}

    def _target(key: str) -> Path:
        configured = Path(str(files[key]))
        default_root = Path(str(config.section("outputs")["root"]))
        try:
            relative = configured.relative_to(default_root)
        except ValueError:  # pragma: no cover - configuration keeps them nested
            relative = Path(configured.name)
        candidate = output_root_path / relative
        return assert_output_path_allowed(candidate, config, repository_root=root)

    assert_portable_rows(result.pairing_rows, context="pairing audit")
    assert_portable_rows(result.extraction_rows, context="extraction master")
    assert_portable_rows(result.qa_inventory_rows, context="native QA inventory")

    written["pairing_audit"] = write_rows(result.pairing_rows, _target("pairing_audit"))
    written["native_qa_inventory"] = write_rows(
        result.qa_inventory_rows, _target("native_qa_inventory")
    )
    written["extraction_master"] = write_rows(
        result.extraction_rows, _target("extraction_master")
    )
    written["failure_audit"] = write_rows(
        result.failure_rows, _target("failure_audit")
    )

    from .s2_pilot_summary import collapse_to_date_observations

    date_rows: list[dict[str, Any]] = []
    for level in ("L2A", "L1C"):
        members = [
            row for row in result.extraction_rows if row.get("product_level") == level
        ]
        date_rows.extend(collapse_to_date_observations(members, level=level))
    written["date_observation_master"] = write_rows(
        date_rows, _target("date_observation_master")
    )

    overall_attrition = attrition_table(
        result.extraction_rows,
        thresholds=thresholds,
        count_columns=count_columns,
        group_columns=("product_level",),
    )
    written["attrition_table"] = write_rows(
        overall_attrition, _target("attrition_table")
    )
    written["annual_attrition_table"] = write_rows(
        attrition_table(
            result.extraction_rows,
            thresholds=thresholds,
            count_columns=count_columns,
            group_columns=("product_level", "year"),
        ),
        _target("annual_attrition_table"),
    )
    written["baseline_platform_audit"] = write_rows(
        attrition_table(
            result.extraction_rows,
            thresholds=thresholds,
            count_columns=count_columns,
            group_columns=("product_level", "processing_baseline", "platform"),
        ),
        _target("baseline_platform_audit"),
    )

    written["native_qa_audit_document"] = write_markdown(
        render_native_qa_audit(result.qa_inventory_rows, result.extraction_rows),
        _target("native_qa_audit_document"),
    )
    written["qa_findings_document"] = write_markdown(
        render_qa_findings(
            result.extraction_rows,
            result.pairing_rows,
            overall_attrition,
            result.counts,
        ),
        _target("qa_findings_document"),
    )

    manifest = build_provenance_manifest(
        config=config,
        repository_root=root,
        result=result,
        l1c_root_provided=l1c_root_provided,
        l2a_root_provided=l2a_root_provided,
    )
    manifest_path = _target("provenance_manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    written["provenance_manifest"] = manifest_path

    return written
