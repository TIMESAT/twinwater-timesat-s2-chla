"""Consume already-generated ACOLITE GeoTIFFs for the Erken observation layer.

This module does not run atmospheric correction. It joins ACOLITE product
directories to the committed Phase 6A L1C pairing audit, reads ACOLITE surface
reflectance (``rhos``) and the ``l2_flags`` bit field, and constructs the same
NDCI/MCI and nested-window summaries used by the Phase 6A observation pilot.

The implementation deliberately keeps ACOLITE in a separate Phase 6B output
namespace. Existing Phase 6A products and governance are read-only inputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform as platform_module
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import rasterio
import yaml
from rasterio.transform import Affine
from rasterio.windows import Window

from .s2_grid import (
    GridAlignmentError,
    GridSpec,
    assert_same_grid,
    block_mean_reduce,
    categorical_any_invalid_reduce,
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
from .s2_pilot_summary import attrition_table, summarize_index_window, write_rows
from .s2_scl import station_to_pixel, transform_station_coordinate


DEFAULT_CONFIG_RELATIVE_PATH = "config/erken_acolite_observation_extraction_v1.0.yaml"
EXPECTED_SCHEMA_VERSION = "erken_acolite_observation_extraction_config_v1"
EXPECTED_WINDOWS = (1, 3, 5, 7, 11)
PRODUCT_ID_RE = re.compile(
    r"(?P<platform>S2[A-Z0-9])_MSIL1C_"
    r"(?P<acquisition>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_"
    r"(?P<orbit>R\d{3})_"
    r"(?P<tile>T\d{2}[A-Z]{3})_"
    r"(?P<generation>\d{8}T\d{6})",
    re.IGNORECASE,
)


class AcoliteConfigError(ValueError):
    """Raised when the ACOLITE extraction configuration is invalid."""


class AcoliteExtractionError(RuntimeError):
    """Raised when extraction would require an unrecorded assumption."""


class WindowCoverageError(AcoliteExtractionError):
    """Raised when a requested station-centred window is not fully covered."""


@dataclass(frozen=True)
class AcoliteConfig:
    """Validated extraction configuration plus its SHA256 identity."""

    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    def section(self, name: str) -> Mapping[str, Any]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise AcoliteConfigError(
                f"ACOLITE configuration section {name!r} must be a mapping."
            )
        return value

    @property
    def extraction_version(self) -> str:
        return str(self.values["extraction_version"])

    @property
    def status(self) -> str:
        return str(self.values["status"])


@dataclass(frozen=True)
class AcoliteProduct:
    """One source L1C product directory and its ACOLITE output directory."""

    product_id: str
    product_root: Path
    output_dir: Path


@dataclass
class AcoliteExtractionOutcome:
    """One primary 3x3 row plus nested-window sensitivity rows."""

    row: dict[str, Any]
    window_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass
class AcoliteRunResult:
    """In-memory products of one extraction run."""

    inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    phase6a_alignment_rows: list[dict[str, Any]] = field(default_factory=list)
    extraction_rows: list[dict[str, Any]] = field(default_factory=list)
    date_rows: list[dict[str, Any]] = field(default_factory=list)
    window_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)


def sha256_file(path: str | Path) -> str:
    """Return the byte-level SHA256 of one file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_acolite_config_path(repository_root: str | Path) -> Path:
    return Path(repository_root) / DEFAULT_CONFIG_RELATIVE_PATH


def load_acolite_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> AcoliteConfig:
    """Load and validate the draft ACOLITE extraction configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise AcoliteConfigError(f"ACOLITE configuration not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise AcoliteConfigError("ACOLITE configuration must be a YAML mapping.")
    if str(values.get("schema_version")) != EXPECTED_SCHEMA_VERSION:
        raise AcoliteConfigError(
            f"Unexpected schema_version {values.get('schema_version')!r}; "
            f"expected {EXPECTED_SCHEMA_VERSION!r}."
        )

    required = (
        "scope",
        "inputs",
        "reflectance",
        "grid",
        "qa",
        "indices",
        "spatial_summary",
        "outputs",
    )
    missing = [name for name in required if not isinstance(values.get(name), Mapping)]
    if missing:
        raise AcoliteConfigError(
            f"Missing or invalid ACOLITE configuration section(s): {missing}."
        )

    spatial = values["spatial_summary"]
    windows = tuple(int(value) for value in spatial.get("window_sizes", []))
    if windows != EXPECTED_WINDOWS:
        raise AcoliteConfigError(
            f"window_sizes must remain exactly {list(EXPECTED_WINDOWS)}; got "
            f"{list(windows)}."
        )
    if int(spatial.get("primary_window_size", 0)) != 3:
        raise AcoliteConfigError("The primary ACOLITE support must remain 3x3.")

    reflectance = values["reflectance"]
    logical_bands = reflectance.get("logical_bands")
    if not isinstance(logical_bands, Mapping) or tuple(logical_bands) != (
        "B4",
        "B5",
        "B6",
    ):
        raise AcoliteConfigError(
            "reflectance.logical_bands must declare B4, B5 and B6 in order."
        )
    if str(reflectance.get("quantity", "")).lower() != "rhos":
        raise AcoliteConfigError(
            "The v1.0 extractor must use ACOLITE L2R rhos, not Rrs or rhot."
        )
    if (
        str(values["inputs"].get("extraction_scope"))
        != "all_discovered_acolite_products"
    ):
        raise AcoliteConfigError(
            "The v1.0 extraction scope must include every discovered ACOLITE "
            "product; the Phase 6A audit is an annotation, not a deletion gate."
        )

    qa = values["qa"]
    exponents = qa.get("flag_exponents")
    if not isinstance(exponents, Mapping):
        raise AcoliteConfigError("qa.flag_exponents must be a mapping.")
    exponent_values = [int(value) for value in exponents.values()]
    if len(exponent_values) != len(set(exponent_values)) or any(
        value < 0 for value in exponent_values
    ):
        raise AcoliteConfigError(
            "qa.flag_exponents must contain unique non-negative integers."
        )
    known_flags = set(str(name) for name in exponents)
    setting_keys = qa.get("flag_exponent_setting_keys")
    if not isinstance(setting_keys, Mapping) or set(setting_keys) != known_flags:
        raise AcoliteConfigError(
            "qa.flag_exponent_setting_keys must map every configured flag "
            "name exactly once."
        )
    for key in ("hard_invalid_flags", "diagnostic_flags"):
        declared = {str(name) for name in qa.get(key, [])}
        unknown = sorted(declared - known_flags)
        if unknown:
            raise AcoliteConfigError(f"{key} contains unknown flags: {unknown}.")
    if str(qa.get("unknown_bits_policy")) != "hard_invalid":
        raise AcoliteConfigError(
            "Unknown ACOLITE l2_flags bits must remain hard invalid in v1.0."
        )

    root = Path(repository_root).resolve() if repository_root is not None else None
    if root is not None:
        try:
            relative = config_path.resolve().relative_to(root).as_posix()
        except ValueError:
            relative = config_path.name
    else:
        relative = config_path.name
    return AcoliteConfig(
        values=values,
        source_relative_path=relative,
        sha256=sha256_file(config_path),
    )


def _assert_erken_only(value: Any, config: AcoliteConfig, *, context: str) -> None:
    text = str(value).lower()
    detected = sorted(
        {
            str(token).lower()
            for token in config.section("scope").get("prohibited_site_tokens", [])
            if str(token).lower() in text
        }
    )
    if detected:
        raise AcoliteExtractionError(
            f"ACOLITE extraction is restricted to Erken; {context} contains "
            f"prohibited site token(s) {detected}: {value!r}."
        )


def _product_id(name: str) -> str:
    return name[:-5] if name.upper().endswith(".SAFE") else name


def discover_acolite_products(
    root: str | Path, *, config: AcoliteConfig
) -> list[AcoliteProduct]:
    """Discover the documented ``ACOLITE_ERKEN/<L1C>/acolite`` layout."""

    archive = Path(root)
    if not archive.is_dir():
        raise AcoliteExtractionError(
            f"ACOLITE archive root is not a directory: {archive}"
        )
    _assert_erken_only(archive, config, context="archive root")
    output_name = str(
        config.section("inputs")["expected_product_output_subdirectory"]
    )

    candidates: list[Path] = []
    if (archive / output_name).is_dir():
        candidates.append(archive)
    candidates.extend(
        path
        for path in sorted(archive.iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / output_name).is_dir()
    )

    products: list[AcoliteProduct] = []
    for product_root in candidates:
        product_id = _product_id(product_root.name)
        if "_MSIL1C_" not in product_id.upper():
            continue
        _assert_erken_only(product_id, config, context="source product ID")
        products.append(
            AcoliteProduct(
                product_id=product_id,
                product_root=product_root,
                output_dir=product_root / output_name,
            )
        )
    return products


def read_phase6a_pairing_audit(path: str | Path) -> list[dict[str, Any]]:
    """Read the committed Phase 6A date/product pairing audit."""

    source = Path(path)
    if not source.is_file():
        raise AcoliteExtractionError(f"Phase 6A pairing audit not found: {source}")
    with source.open(encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise AcoliteExtractionError(f"Phase 6A pairing audit is empty: {source}")
    required = {
        "date",
        "year",
        "l2a_representative_status",
        "scl_gate_pass",
        "l2a_product_id",
        "l1c_pairing_status",
        "l1c_product_id",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise AcoliteExtractionError(
            f"Phase 6A pairing audit is missing columns: {missing}."
        )
    return rows


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _rhos_candidates(
    product: AcoliteProduct, *, config: AcoliteConfig
) -> list[tuple[float, Path]]:
    marker = str(config.section("reflectance")["filename_marker"])
    pattern = re.compile(
        rf"{re.escape(marker)}(?P<wavelength>\d+(?:\.\d+)?)\.tiff?$",
        re.IGNORECASE,
    )
    candidates: list[tuple[float, Path]] = []
    for path in sorted(product.output_dir.glob("*.tif*"), key=lambda item: item.name):
        match = pattern.search(path.name)
        if match:
            candidates.append((float(match.group("wavelength")), path))
    return candidates


def select_rhos_assets(
    product: AcoliteProduct, *, config: AcoliteConfig
) -> dict[str, tuple[float, Path]]:
    """Select one unambiguous nearest ACOLITE rhos band for B4/B5/B6."""

    candidates = _rhos_candidates(product, config=config)
    if not candidates:
        raise AcoliteExtractionError("no_l2r_rhos_geotiffs")
    reflectance = config.section("reflectance")
    tolerance = float(reflectance["maximum_wavelength_difference_nm"])
    selected: dict[str, tuple[float, Path]] = {}
    used: set[Path] = set()
    for band, details in reflectance["logical_bands"].items():
        target = float(details["target_wavelength_nm"])
        distances = [(abs(wavelength - target), wavelength, path) for wavelength, path in candidates]
        minimum = min(distance for distance, _, _ in distances)
        nearest = [item for item in distances if math.isclose(item[0], minimum, abs_tol=1e-12)]
        if minimum > tolerance:
            raise AcoliteExtractionError(
                f"no_rhos_band_within_{tolerance:g}nm_for_{band}_target_{target:g}nm"
            )
        if len(nearest) != 1:
            names = ";".join(path.name for _, _, path in nearest)
            raise AcoliteExtractionError(
                f"ambiguous_nearest_rhos_band_for_{band}: {names}"
            )
        _, wavelength, path = nearest[0]
        if path in used:
            raise AcoliteExtractionError(
                f"one_rhos_asset_would_supply_multiple_logical_bands: {path.name}"
            )
        used.add(path)
        selected[str(band)] = (wavelength, path)
    return selected


def select_flags_asset(
    product: AcoliteProduct, *, config: AcoliteConfig, rhos_asset: Path
) -> Path:
    """Select the l2_flags GeoTIFF from the same ACOLITE output basename."""

    marker = str(config.section("qa")["flags_filename_marker"])
    prefix = rhos_asset.name.split("_L2R_", 1)[0]
    candidates = [
        path
        for path in sorted(product.output_dir.glob("*.tif*"), key=lambda item: item.name)
        if path.name.lower().endswith(marker.lower())
        and path.name.split("_L2W_", 1)[0] == prefix
    ]
    if not candidates:
        raise AcoliteExtractionError("matching_l2w_l2_flags_geotiff_not_found")
    if len(candidates) > 1:
        raise AcoliteExtractionError(
            "ambiguous_matching_l2w_l2_flags_geotiff: "
            + ";".join(path.name for path in candidates)
        )
    return candidates[0]


def decode_l2_flags(
    values: np.ndarray,
    *,
    config: AcoliteConfig,
    nodata_mask: np.ndarray | None = None,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Decode configured ACOLITE bits and build a conservative hard mask."""

    array = np.asarray(values)
    if array.ndim != 2:
        raise AcoliteExtractionError(
            f"ACOLITE l2_flags must be two-dimensional; got {array.shape}."
        )
    if not np.all(np.isfinite(array)):
        raise AcoliteExtractionError(
            "ACOLITE l2_flags contains non-finite unmasked values."
        )
    integer = array.astype("int64")
    if np.any(integer < 0) or not np.array_equal(integer.astype(array.dtype), array):
        raise AcoliteExtractionError(
            "ACOLITE l2_flags must contain non-negative integer bit fields."
        )

    qa = config.section("qa")
    layers: dict[str, np.ndarray] = {}
    known_mask = 0
    for name, exponent in qa["flag_exponents"].items():
        bit = 1 << int(exponent)
        known_mask |= bit
        layers[str(name)] = (integer & bit) != 0
    unknown = (integer & ~known_mask) != 0
    layers["unknown_bits"] = unknown

    hard_names = [str(name) for name in qa["hard_invalid_flags"]]
    hard = np.zeros(integer.shape, dtype=bool)
    for name in hard_names:
        hard |= layers[name]
    hard |= unknown
    nodata = (
        np.zeros(integer.shape, dtype=bool)
        if nodata_mask is None
        else np.asarray(nodata_mask).astype(bool)
    )
    if nodata.shape != integer.shape:
        raise AcoliteExtractionError("l2_flags nodata mask shape does not match data.")
    layers["flags_nodata"] = nodata
    hard |= nodata
    return layers, hard, integer


def _target_grid(source: GridSpec, *, config: AcoliteConfig) -> tuple[GridSpec, int]:
    """Return the 20 m target grid and exact native-to-target factor."""

    grid = config.section("grid")
    target_resolution = float(grid["target_resolution_m"])
    tolerance = float(grid.get("pixel_size_tolerance_m", 1e-3))
    if abs(source.pixel_size_x - source.pixel_size_y) > tolerance:
        raise GridAlignmentError(
            f"ACOLITE pixels are not square: {source.pixel_size_x} x "
            f"{source.pixel_size_y} m."
        )
    accepted = [float(value) for value in grid["accepted_native_resolutions_m"]]
    if not any(abs(source.pixel_size_x - value) <= tolerance for value in accepted):
        raise GridAlignmentError(
            f"ACOLITE native resolution {source.pixel_size_x:g} m is not in "
            f"the accepted set {accepted}."
        )

    ratio = target_resolution / source.pixel_size_x
    factor = int(round(ratio))
    if factor < 1 or abs(ratio - factor) > 1e-6:
        raise GridAlignmentError(
            f"ACOLITE {source.pixel_size_x:g} m pixels do not nest exactly "
            f"inside the {target_resolution:g} m target grid."
        )
    if source.width % factor or source.height % factor:
        raise GridAlignmentError(
            f"ACOLITE raster dimensions {source.width}x{source.height} are not "
            f"divisible by the exact reduction factor {factor}."
        )
    if factor == 1:
        return source, 1

    transform = Affine(
        source.transform.a * factor,
        source.transform.b,
        source.transform.c,
        source.transform.d,
        source.transform.e * factor,
        source.transform.f,
    )
    target = GridSpec(
        crs=source.crs,
        transform=transform,
        width=source.width // factor,
        height=source.height // factor,
    )
    nesting_factor(
        source,
        target,
        origin_tolerance_m=float(grid.get("origin_tolerance_m", 1e-3)),
        pixel_size_tolerance_m=tolerance,
        fine_label="ACOLITE native grid",
        coarse_label="20 m target grid",
    )
    return target, factor


def _native_window(
    dataset: Any,
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> np.ma.MaskedArray:
    half = target_size // 2
    target_row_start = target_row - half
    target_col_start = target_col - half
    native_row_start = target_row_start * factor
    native_col_start = target_col_start * factor
    native_size = target_size * factor
    if (
        native_row_start < 0
        or native_col_start < 0
        or native_row_start + native_size > dataset.height
        or native_col_start + native_size > dataset.width
    ):
        raise WindowCoverageError(
            f"The requested {target_size}x{target_size} target window is not "
            "fully covered by the ACOLITE raster."
        )
    return dataset.read(
        1,
        window=Window(
            col_off=native_col_start,
            row_off=native_row_start,
            width=native_size,
            height=native_size,
        ),
        boundless=False,
        masked=True,
    )


def _read_reflectance_window(
    dataset: Any,
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    masked = _native_window(
        dataset,
        target_row=target_row,
        target_col=target_col,
        target_size=target_size,
        factor=factor,
    )
    nodata = np.ma.getmaskarray(masked)
    values = np.asarray(masked.filled(np.nan), dtype="float64")
    scale = float(dataset.scales[0]) if dataset.scales else 1.0
    offset = float(dataset.offsets[0]) if dataset.offsets else 0.0
    if not math.isfinite(scale) or not math.isfinite(offset):
        raise AcoliteExtractionError("ACOLITE GeoTIFF scale/offset is non-finite.")
    values = values * scale + offset
    if factor > 1:
        values = block_mean_reduce(values, factor)
        nodata = categorical_any_invalid_reduce(nodata, factor)
    return values, nodata, scale, offset


def _read_flags_window(
    dataset: Any,
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
    config: AcoliteConfig,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    masked = _native_window(
        dataset,
        target_row=target_row,
        target_col=target_col,
        target_size=target_size,
        factor=factor,
    )
    nodata = np.ma.getmaskarray(masked)
    values = np.asarray(masked.filled(0))
    layers, hard, integer = decode_l2_flags(
        values, config=config, nodata_mask=nodata
    )
    if factor == 1:
        return layers, hard, integer

    reduced_layers = {
        name: categorical_any_invalid_reduce(flags, factor)
        for name, flags in layers.items()
    }
    reduced_hard = categorical_any_invalid_reduce(hard, factor)
    # Bitwise OR preserves which fine-grid conditions occurred in each 20 m
    # target cell; it is used only as a diagnostic value, never interpolation.
    height, width = integer.shape
    reshaped = integer.reshape(
        height // factor, factor, width // factor, factor
    )
    reduced_integer = np.bitwise_or.reduce(
        np.bitwise_or.reduce(reshaped, axis=3), axis=1
    )
    return reduced_layers, reduced_hard, reduced_integer


def _center_crop(values: np.ndarray, size: int) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise AcoliteExtractionError(
            f"Nested-window source must be square and two-dimensional: {array.shape}."
        )
    outer = array.shape[0]
    if size <= 0 or size % 2 == 0 or size > outer or outer % 2 == 0:
        raise AcoliteExtractionError(
            f"Cannot crop {size}x{size} from {outer}x{outer}."
        )
    offset = (outer - size) // 2
    return array[offset : offset + size, offset : offset + size]


def _apply_statistics(
    base: Mapping[str, Any],
    *,
    size: int,
    primary_size: int,
    target_resolution_m: int,
    reflectance: Mapping[str, np.ndarray],
    validity: Mapping[str, np.ndarray],
    common_valid: np.ndarray,
    flag_layers: Mapping[str, np.ndarray],
    hard_invalid: np.ndarray,
    flag_values: np.ndarray,
    ndci: Any,
    mci: Any,
    config: AcoliteConfig,
    include_window_columns: bool,
) -> dict[str, Any]:
    row = dict(base)
    pixels = size * size
    if include_window_columns:
        row.update(
            {
                "spatial_analysis_role": (
                    "primary_3x3_support"
                    if size == primary_size
                    else "secondary_exploratory_sensitivity"
                ),
                "window_size": size,
                "window_pixel_count": pixels,
                "grid_resolution_m": target_resolution_m,
                "window_side_length_m": size * target_resolution_m,
            }
        )

    reflectance_config = config.section("reflectance")
    diagnostic_minimum = float(reflectance_config["diagnostic_minimum"])
    diagnostic_maximum = float(reflectance_config["diagnostic_maximum"])
    for band in ("B4", "B5", "B6"):
        values = _center_crop(reflectance[band], size)
        valid = _center_crop(validity[band], size).astype(bool)
        row.update(
            summarize_index_window(
                values,
                valid,
                prefix=f"{band}_reflectance",
                window_pixel_count=pixels,
            )
        )
        row[f"{band}_reflectance_nonfinite_count"] = int(
            np.count_nonzero(~np.isfinite(values))
        )
        row[f"{band}_reflectance_below_range_count"] = int(
            np.count_nonzero(np.isfinite(values) & (values < diagnostic_minimum))
        )
        row[f"{band}_reflectance_above_range_count"] = int(
            np.count_nonzero(np.isfinite(values) & (values > diagnostic_maximum))
        )

    for name, flags in sorted(flag_layers.items()):
        count = int(np.count_nonzero(_center_crop(flags, size)))
        row[f"qa_acolite_{name}_count"] = count
        row[f"qa_acolite_{name}_fraction"] = count / pixels
    hard_count = int(np.count_nonzero(_center_crop(hard_invalid, size)))
    row["qa_acolite_hard_invalid_count"] = hard_count
    row["qa_acolite_hard_invalid_fraction"] = hard_count / pixels
    cropped_flag_values = _center_crop(flag_values, size)
    row["qa_acolite_any_flag_count"] = int(
        np.count_nonzero(cropped_flag_values != 0)
    )
    row["qa_acolite_flag_value_max"] = int(np.max(cropped_flag_values))

    row["common_B456_valid_count"] = int(
        np.count_nonzero(_center_crop(common_valid, size))
    )
    ndci_values = _center_crop(ndci.values, size)
    ndci_valid = _center_crop(ndci.valid, size)
    mci_values = _center_crop(mci.values, size)
    mci_valid = _center_crop(mci.valid, size)
    row.update(
        summarize_index_window(
            ndci_values, ndci_valid, prefix="NDCI", window_pixel_count=pixels
        )
    )
    row.update(
        summarize_index_window(
            mci_values, mci_valid, prefix="MCI", window_pixel_count=pixels
        )
    )
    for name, flags in ndci.diagnostics.items():
        row[f"NDCI_diag_{name}"] = int(
            np.count_nonzero(_center_crop(flags, size))
        )
    for name, flags in mci.diagnostics.items():
        row[f"MCI_diag_{name}"] = int(
            np.count_nonzero(_center_crop(flags, size))
        )

    row["ndci_valid_pixel_count"] = row["NDCI_valid_pixel_count"]
    row["mci_valid_pixel_count"] = row["MCI_valid_pixel_count"]
    row["ndci_has_any_valid_pixel"] = row["ndci_valid_pixel_count"] > 0
    row["mci_has_any_valid_pixel"] = row["mci_valid_pixel_count"] > 0
    row["final_valid_pixel_threshold_status"] = str(
        config.section("spatial_summary")["final_valid_pixel_threshold_status"]
    )
    if row["ndci_valid_pixel_count"] or row["mci_valid_pixel_count"]:
        row["failure_reason"] = None
    elif size == primary_size:
        row["failure_reason"] = "no_valid_pixels_after_acolite_qa_in_3x3_window"
    else:
        row["failure_reason"] = (
            f"no_valid_pixels_after_acolite_qa_in_{size}x{size}_window"
        )
    return row


def _settings_paths(product: AcoliteProduct) -> list[Path]:
    return sorted(
        {
            *product.output_dir.glob("acolite-settings.txt"),
            *product.output_dir.glob("acolite_run_*_settings*.txt"),
        },
        key=lambda path: path.name,
    )


def _settings_provenance(product: AcoliteProduct, *, archive_root: Path) -> dict[str, Any]:
    run_json = sorted(product.output_dir.glob("run.json"))
    settings = _settings_paths(product)
    return {
        "acolite_run_json_relative_path": (
            _relative(run_json[0], archive_root) if len(run_json) == 1 else None
        ),
        "acolite_run_json_sha256": (
            sha256_file(run_json[0]) if len(run_json) == 1 else None
        ),
        "acolite_run_json_candidate_count": len(run_json),
        "acolite_settings_relative_paths": (
            ";".join(_relative(path, archive_root) for path in settings) or None
        ),
        "acolite_settings_sha256": (
            ";".join(sha256_file(path) for path in settings) or None
        ),
    }


def _validate_flag_exponent_settings(
    product: AcoliteProduct, *, config: AcoliteConfig
) -> dict[str, Any]:
    """Refuse customized ACOLITE flag positions that would be misdecoded."""

    qa = config.section("qa")
    expected = {str(name): int(value) for name, value in qa["flag_exponents"].items()}
    keys = {
        str(name): str(value)
        for name, value in qa["flag_exponent_setting_keys"].items()
    }
    observed_by_key: dict[str, set[int]] = {setting: set() for setting in keys.values()}
    for path in _settings_paths(product):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw = (part.strip() for part in stripped.split("=", 1))
            if key not in observed_by_key:
                continue
            try:
                value = int(raw.split("#", 1)[0].strip())
            except ValueError as error:
                raise AcoliteExtractionError(
                    f"invalid {key} value {raw!r} in {path.name}"
                ) from error
            observed_by_key[key].add(value)

    declared = 0
    for name, expected_value in expected.items():
        setting = keys[name]
        observed = observed_by_key[setting]
        if len(observed) > 1:
            raise AcoliteExtractionError(
                f"conflicting {setting} values in ACOLITE settings: "
                f"{sorted(observed)}"
            )
        if observed:
            declared += 1
            actual = next(iter(observed))
            if actual != expected_value:
                raise AcoliteExtractionError(
                    f"{setting}={actual} differs from configured exponent "
                    f"{expected_value}"
                )
    return {
        "acolite_flag_exponent_validation_status": (
            "all_declared_values_match"
            if declared == len(expected)
            else "declared_values_match_remaining_use_official_defaults"
            if declared
            else "not_declared_use_official_defaults"
        ),
        "acolite_flag_exponents_declared_count": declared,
    }


def extract_acolite_product(
    product: AcoliteProduct,
    *,
    archive_root: str | Path,
    config: AcoliteConfig,
    base_row: Mapping[str, Any],
    window_sizes: Sequence[int] = EXPECTED_WINDOWS,
) -> AcoliteExtractionOutcome:
    """Extract one ACOLITE product on the requested nested 20 m windows."""

    archive = Path(archive_root)
    row = dict(base_row)
    row.update(_settings_provenance(product, archive_root=archive))
    row["acolite_product_directory"] = _relative(product.product_root, archive)
    row["atmospheric_correction_method"] = str(
        config.section("inputs")["atmospheric_correction_method"]
    )
    row["reflectance_quantity"] = str(config.section("reflectance")["quantity"])
    row["failure_reason"] = None

    try:
        row.update(_validate_flag_exponent_settings(product, config=config))
        selected = select_rhos_assets(product, config=config)
        flags_path = select_flags_asset(
            product, config=config, rhos_asset=selected["B4"][1]
        )
    except AcoliteExtractionError as error:
        row["failure_reason"] = f"acolite_input_validation_failed: {error}"
        return AcoliteExtractionOutcome(
            row=row, failure_reason=row["failure_reason"]
        )

    row["acolite_l2_flags_relative_path"] = _relative(flags_path, archive)
    for band, (wavelength, path) in selected.items():
        row[f"{band}_selected_wavelength_nm"] = wavelength
        row[f"{band}_rhos_relative_path"] = _relative(path, archive)

    datasets: dict[str, Any] = {}
    flags_dataset: Any | None = None
    try:
        for band, (_, path) in selected.items():
            datasets[band] = rasterio.open(path)
        flags_dataset = rasterio.open(flags_path)

        source = grid_spec_from_dataset(datasets["B4"])
        grid_config = config.section("grid")
        for band in ("B5", "B6"):
            assert_same_grid(
                source,
                grid_spec_from_dataset(datasets[band]),
                origin_tolerance_m=float(grid_config["origin_tolerance_m"]),
                pixel_size_tolerance_m=float(grid_config["pixel_size_tolerance_m"]),
                left_label="ACOLITE B4 rhos",
                right_label=f"ACOLITE {band} rhos",
            )
        assert_same_grid(
            source,
            grid_spec_from_dataset(flags_dataset),
            origin_tolerance_m=float(grid_config["origin_tolerance_m"]),
            pixel_size_tolerance_m=float(grid_config["pixel_size_tolerance_m"]),
            left_label="ACOLITE rhos",
            right_label="ACOLITE l2_flags",
        )
        target, factor = _target_grid(source, config=config)
        row.update(
            {f"target_grid_{name}": value for name, value in target.audit().items()}
        )
        row["acolite_native_resolution_m"] = source.pixel_size_x
        row["native_to_target_reduction_factor"] = factor

        station = grid_config["station"]
        station_x, station_y = transform_station_coordinate(
            station_lon=float(station["longitude"]),
            station_lat=float(station["latitude"]),
            station_crs=str(station["crs"]),
            raster_crs=target.crs,
        )
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
            raise AcoliteExtractionError("station_outside_acolite_raster")

        maximum_size = max(int(value) for value in window_sizes)
        reflectance: dict[str, np.ndarray] = {}
        band_nodata: dict[str, np.ndarray] = {}
        for band in ("B4", "B5", "B6"):
            values, nodata, scale, offset = _read_reflectance_window(
                datasets[band],
                target_row=location.row,
                target_col=location.col,
                target_size=maximum_size,
                factor=factor,
            )
            reflectance[band] = values
            band_nodata[band] = nodata
            row[f"{band}_geotiff_scale"] = scale
            row[f"{band}_geotiff_offset"] = offset
            row[f"{band}_geotiff_nodata"] = datasets[band].nodata

        flag_layers, hard_invalid, flag_values = _read_flags_window(
            flags_dataset,
            target_row=location.row,
            target_col=location.col,
            target_size=maximum_size,
            factor=factor,
            config=config,
        )

        validity = band_validity(
            reflectance,
            band_nodata,
            common_hard_invalid=hard_invalid,
        )
        indices = config.section("indices")
        ndci_valid = index_validity(
            validity, tuple(str(value) for value in indices["ndci"]["required_bands"])
        )
        mci_valid = index_validity(
            validity, tuple(str(value) for value in indices["mci"]["required_bands"])
        )
        common_valid = common_band_validity(validity)
        ndci = compute_ndci(
            reflectance["B4"],
            reflectance["B5"],
            valid=ndci_valid,
            denominator_epsilon=float(indices["ndci"]["denominator_epsilon"]),
            require_positive_denominator=bool(
                indices["ndci"]["require_positive_denominator"]
            ),
            theoretical_min=float(indices["ndci"]["theoretical_min"]),
            theoretical_max=float(indices["ndci"]["theoretical_max"]),
        )
        coefficient = mci_baseline_coefficient(
            indices["nominal_central_wavelength_nm"]
        )
        mci = compute_mci(
            reflectance["B4"],
            reflectance["B5"],
            reflectance["B6"],
            valid=mci_valid,
            baseline_coefficient=coefficient,
        )
        row["mci_baseline_coefficient"] = coefficient

        primary_size = int(
            config.section("spatial_summary")["primary_window_size"]
        )
        target_resolution = int(grid_config["target_resolution_m"])
        primary = _apply_statistics(
            row,
            size=primary_size,
            primary_size=primary_size,
            target_resolution_m=target_resolution,
            reflectance=reflectance,
            validity=validity,
            common_valid=common_valid,
            flag_layers=flag_layers,
            hard_invalid=hard_invalid,
            flag_values=flag_values,
            ndci=ndci,
            mci=mci,
            config=config,
            include_window_columns=False,
        )
        window_rows = [
            _apply_statistics(
                row,
                size=int(size),
                primary_size=primary_size,
                target_resolution_m=target_resolution,
                reflectance=reflectance,
                validity=validity,
                common_valid=common_valid,
                flag_layers=flag_layers,
                hard_invalid=hard_invalid,
                flag_values=flag_values,
                ndci=ndci,
                mci=mci,
                config=config,
                include_window_columns=True,
            )
            for size in window_sizes
        ]
        return AcoliteExtractionOutcome(
            row=primary,
            window_rows=window_rows,
            failure_reason=primary.get("failure_reason"),
        )
    except WindowCoverageError:
        raise
    except (
        AcoliteExtractionError,
        GridAlignmentError,
        IndexComputationError,
        rasterio.RasterioError,
        OSError,
        ValueError,
    ) as error:
        row["failure_reason"] = f"acolite_extraction_failed: {error}"
        return AcoliteExtractionOutcome(
            row=row, failure_reason=row["failure_reason"]
        )
    finally:
        for dataset in datasets.values():
            dataset.close()
        if flags_dataset is not None:
            flags_dataset.close()


def _unavailable_window_rows(
    row: Mapping[str, Any],
    *,
    window_sizes: Sequence[int],
    config: AcoliteConfig,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    primary = int(config.section("spatial_summary")["primary_window_size"])
    resolution = int(config.section("grid")["target_resolution_m"])
    rows: list[dict[str, Any]] = []
    for size in window_sizes:
        item = dict(row)
        item.update(
            {
                "spatial_analysis_role": (
                    "primary_3x3_support"
                    if int(size) == primary
                    else "secondary_exploratory_sensitivity"
                ),
                "window_size": int(size),
                "window_pixel_count": int(size) * int(size),
                "grid_resolution_m": resolution,
                "window_side_length_m": int(size) * resolution,
                "failure_reason": reason or row.get("failure_reason") or "unavailable",
            }
        )
        rows.append(item)
    return rows


def _extract_with_boundary_fallback(
    product: AcoliteProduct,
    *,
    archive_root: Path,
    config: AcoliteConfig,
    base_row: Mapping[str, Any],
    window_sizes: Sequence[int],
) -> AcoliteExtractionOutcome:
    primary = int(config.section("spatial_summary")["primary_window_size"])
    candidates = [int(value) for value in window_sizes]
    unavailable: list[dict[str, Any]] = []
    while primary in candidates:
        try:
            outcome = extract_acolite_product(
                product,
                archive_root=archive_root,
                config=config,
                base_row=base_row,
                window_sizes=tuple(candidates),
            )
        except WindowCoverageError as error:
            failed_size = candidates.pop()
            unavailable.extend(
                _unavailable_window_rows(
                    {**base_row, "failure_reason": str(error)},
                    window_sizes=(failed_size,),
                    config=config,
                    reason=f"window_coverage_failed: {error}",
                )
            )
            continue
        outcome.window_rows.extend(unavailable)
        outcome.window_rows.sort(key=lambda item: int(item["window_size"]))
        return outcome

    row = dict(base_row)
    row["failure_reason"] = "window_coverage_failed_for_primary_3x3_support"
    return AcoliteExtractionOutcome(
        row=row,
        window_rows=_unavailable_window_rows(
            row, window_sizes=window_sizes, config=config
        ),
        failure_reason=row["failure_reason"],
    )


def _pairing_base_row(
    pairing: Mapping[str, Any], *, config: AcoliteConfig
) -> dict[str, Any]:
    """Return the portable Phase 6A fields used by the alignment audit."""

    return {
        "date": pairing.get("date"),
        "year": int(pairing["year"]) if str(pairing.get("year", "")).strip() else None,
        "scl_gate_pass": str(pairing.get("scl_gate_pass", "")).lower() == "true",
        "l2a_representative_status": pairing.get("l2a_representative_status"),
        "l2a_product_id": pairing.get("l2a_product_id") or None,
        "l1c_pairing_status": pairing.get("l1c_pairing_status"),
        "source_l1c_product_id": pairing.get("l1c_product_id") or None,
        "atmospheric_correction_method": config.section("inputs")[
            "atmospheric_correction_method"
        ],
        "reflectance_quantity": config.section("reflectance")["quantity"],
    }


def _product_base_row(
    product: AcoliteProduct,
    *,
    config: AcoliteConfig,
    exact_pairing_by_product: Mapping[str, Mapping[str, Any]],
    pairing_by_date: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Build product provenance and annotate, rather than enforce, Phase 6A."""

    match = PRODUCT_ID_RE.fullmatch(product.product_id)
    if match is None:
        raise AcoliteExtractionError(
            f"source_l1c_product_id_unparseable: {product.product_id}"
        )
    acquisition = datetime.strptime(
        match.group("acquisition"), "%Y%m%dT%H%M%S"
    )
    date = acquisition.date().isoformat()
    exact = exact_pairing_by_product.get(product.product_id)
    date_in_audit = date in pairing_by_date
    if exact is not None:
        subset_status = "phase6a_exact_l1c_pair"
    elif date_in_audit:
        subset_status = "date_in_phase6a_audit_but_not_exact_source_product"
    else:
        subset_status = "outside_phase6a_pairing_audit"

    return {
        "date": date,
        "year": acquisition.year,
        "source_l1c_product_id": product.product_id,
        "platform": match.group("platform").upper(),
        "sensing_datetime": acquisition.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tile": match.group("tile").upper(),
        "orbit": int(match.group("orbit")[1:]),
        "processing_baseline": match.group("baseline").upper(),
        "generation_time": datetime.strptime(
            match.group("generation"), "%Y%m%dT%H%M%S"
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase6a_date_in_pairing_audit": date_in_audit,
        "phase6a_exact_pair_eligible": exact is not None,
        "phase6a_subset_status": subset_status,
        "scl_gate_pass": (
            str(exact.get("scl_gate_pass", "")).lower() == "true"
            if exact is not None
            else None
        ),
        "l2a_representative_status": (
            exact.get("l2a_representative_status") if exact is not None else None
        ),
        "l2a_product_id": exact.get("l2a_product_id") if exact is not None else None,
        "l1c_pairing_status": (
            exact.get("l1c_pairing_status") if exact is not None else None
        ),
        "atmospheric_correction_method": config.section("inputs")[
            "atmospheric_correction_method"
        ],
        "reflectance_quantity": config.section("reflectance")["quantity"],
        "failure_reason": None,
    }


def _inventory_row(
    product: AcoliteProduct,
    *,
    archive_root: Path,
    config: AcoliteConfig,
    eligible_ids: set[str],
) -> dict[str, Any]:
    rhos = _rhos_candidates(product, config=config)
    flags_marker = str(config.section("qa")["flags_filename_marker"])
    flags = [
        path
        for path in product.output_dir.glob("*.tif*")
        if path.name.lower().endswith(flags_marker.lower())
    ]
    match = PRODUCT_ID_RE.search(product.product_id)
    row = {
        "source_l1c_product_id": product.product_id,
        "source_product_directory": _relative(product.product_root, archive_root),
        "acolite_output_directory": _relative(product.output_dir, archive_root),
        "platform": match.group("platform").upper() if match else None,
        "acquisition_date": (
            datetime.strptime(match.group("acquisition"), "%Y%m%dT%H%M%S")
            .date()
            .isoformat()
            if match
            else None
        ),
        "tile": match.group("tile").upper() if match else None,
        "phase6a_exact_pair_eligible": product.product_id in eligible_ids,
        "rhos_geotiff_count": len(rhos),
        "rhos_wavelengths_nm": ";".join(f"{wave:g}" for wave, _ in rhos) or None,
        "l2_flags_geotiff_count": len(flags),
    }
    row.update(_settings_provenance(product, archive_root=archive_root))
    return row


def _phase6a_alignment_rows(
    pairing_rows: Sequence[Mapping[str, Any]],
    *,
    products_by_id: Mapping[str, Sequence[AcoliteProduct]],
    config: AcoliteConfig,
) -> list[dict[str, Any]]:
    """Retain every Phase 6A date and report ACOLITE archive alignment."""

    rows: list[dict[str, Any]] = []
    for pairing in pairing_rows:
        row = _pairing_base_row(pairing, config=config)
        source_id = str(pairing.get("l1c_product_id") or "")
        matches = products_by_id.get(source_id, []) if source_id else []
        row["acolite_product_directory_count"] = len(matches)
        if pairing.get("l2a_representative_status") != "frozen_representative":
            status = "not_eligible_no_frozen_l2a_representative"
        elif pairing.get("l1c_pairing_status") != "exact_unique":
            status = f"not_eligible_l1c_pairing_{pairing.get('l1c_pairing_status')}"
        elif not matches:
            status = "eligible_exact_l1c_product_missing_from_acolite_archive"
        elif len(matches) > 1:
            status = "eligible_exact_l1c_product_ambiguous_duplicate_directories"
        else:
            status = "eligible_exact_l1c_product_found"
        row["acolite_phase6a_alignment_status"] = status
        rows.append(row)
    return rows


def _collapse_product_rows_to_dates(
    product_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create one deterministic date row without discarding product-level rows."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in product_rows:
        grouped.setdefault(str(row.get("date") or ""), []).append(row)

    collapsed: list[dict[str, Any]] = []
    for date in sorted(grouped):
        members = grouped[date]
        exact = [row for row in members if row.get("phase6a_exact_pair_eligible") is True]
        if len(members) == 1:
            selected = dict(members[0])
            selected["date_selection_status"] = "unique_acolite_product_for_date"
        elif len(exact) == 1:
            selected = dict(exact[0])
            selected["date_selection_status"] = "frozen_phase6a_exact_l1c_product"
        else:
            first = members[0]
            selected = {
                "date": date or None,
                "year": first.get("year"),
                "source_l1c_product_id": None,
                "atmospheric_correction_method": first.get(
                    "atmospheric_correction_method"
                ),
                "reflectance_quantity": first.get("reflectance_quantity"),
                "date_selection_status": "ambiguous_multiple_acolite_products",
                "failure_reason": "ambiguous_multiple_acolite_products_for_date",
            }
        selected["n_acolite_products_considered"] = len(members)
        selected["acolite_product_ids_considered"] = ";".join(
            sorted(str(row.get("source_l1c_product_id")) for row in members)
        )
        collapsed.append(selected)
    return collapsed


def run_acolite_extraction(
    *,
    config: AcoliteConfig,
    repository_root: str | Path,
    acolite_root: str | Path,
) -> AcoliteRunResult:
    """Extract all discovered products and annotate the Phase 6A subset."""

    repository = Path(repository_root)
    archive = Path(acolite_root)
    _assert_erken_only(archive, config, context="archive root")
    pairing_path = repository / str(
        config.section("inputs")["phase6a_pairing_audit"]
    )
    pairing_rows = read_phase6a_pairing_audit(pairing_path)
    products = discover_acolite_products(archive, config=config)

    by_id: dict[str, list[AcoliteProduct]] = {}
    for product in products:
        by_id.setdefault(product.product_id, []).append(product)
    exact_pairing_by_product = {
        str(row["l1c_product_id"]): row
        for row in pairing_rows
        if row.get("l1c_pairing_status") == "exact_unique"
        and str(row.get("l1c_product_id", "")).strip()
    }
    eligible_ids = set(exact_pairing_by_product)
    pairing_by_date: dict[str, list[Mapping[str, Any]]] = {}
    for row in pairing_rows:
        pairing_by_date.setdefault(str(row.get("date") or ""), []).append(row)

    result = AcoliteRunResult()
    result.inventory_rows = [
        _inventory_row(
            product,
            archive_root=archive,
            config=config,
            eligible_ids=eligible_ids,
        )
        for product in products
    ]
    result.phase6a_alignment_rows = _phase6a_alignment_rows(
        pairing_rows,
        products_by_id=by_id,
        config=config,
    )
    windows = tuple(
        int(value) for value in config.section("spatial_summary")["window_sizes"]
    )

    for product in products:
        try:
            base = _product_base_row(
                product,
                config=config,
                exact_pairing_by_product=exact_pairing_by_product,
                pairing_by_date=pairing_by_date,
            )
        except AcoliteExtractionError as error:
            base = {
                "source_l1c_product_id": product.product_id,
                "atmospheric_correction_method": config.section("inputs")[
                    "atmospheric_correction_method"
                ],
                "reflectance_quantity": config.section("reflectance")["quantity"],
                "failure_reason": str(error),
            }
            result.extraction_rows.append(base)
            result.window_rows.extend(
                _unavailable_window_rows(base, window_sizes=windows, config=config)
            )
            result.failure_rows.append(base)
            continue

        if len(by_id[product.product_id]) != 1:
            base["failure_reason"] = (
                "ambiguous_duplicate_acolite_source_product_directories"
            )
            result.extraction_rows.append(base)
            result.window_rows.extend(
                _unavailable_window_rows(base, window_sizes=windows, config=config)
            )
            result.failure_rows.append(base)
            continue

        outcome = _extract_with_boundary_fallback(
            product,
            archive_root=archive,
            config=config,
            base_row=base,
            window_sizes=windows,
        )
        result.extraction_rows.append(outcome.row)
        result.window_rows.extend(
            outcome.window_rows
            or _unavailable_window_rows(
                outcome.row, window_sizes=windows, config=config
            )
        )
        if outcome.failure_reason:
            result.failure_rows.append(outcome.row)

    result.date_rows = _collapse_product_rows_to_dates(result.extraction_rows)
    result.counts = {
        "phase6a_candidate_dates": len(pairing_rows),
        "phase6a_frozen_representative_l2a_dates": sum(
            row.get("l2a_representative_status") == "frozen_representative"
            for row in pairing_rows
        ),
        "phase6a_exact_l1c_pairs": len(eligible_ids),
        "acolite_product_directories_discovered": len(products),
        "eligible_acolite_products_found": sum(
            len(by_id.get(product_id, [])) == 1 for product_id in eligible_ids
        ),
        "successful_primary_extractions": sum(
            not bool(row.get("failure_reason"))
            for row in result.extraction_rows
        ),
        "extraction_rows": len(result.extraction_rows),
        "date_observation_rows": len(result.date_rows),
        "spatial_sensitivity_rows": len(result.window_rows),
        "failure_rows": len(result.failure_rows),
    }
    return result


def _assert_output_path(
    path: Path, *, config: AcoliteConfig, repository_root: Path
) -> Path:
    repository = repository_root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repository).as_posix()
    except ValueError as error:
        raise AcoliteExtractionError(
            f"ACOLITE output escapes the repository: {resolved}."
        ) from error
    allowed = str(config.section("outputs")["root"]).strip("/")
    if relative != allowed and not relative.startswith(f"{allowed}/"):
        raise AcoliteExtractionError(
            f"ACOLITE outputs must remain under {allowed!r}; refused {relative!r}."
        )
    _assert_erken_only(relative, config, context="output path")
    return resolved


def _git_value(repository_root: Path, arguments: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    value = completed.stdout.strip()
    return value or None


def build_provenance_manifest(
    *,
    config: AcoliteConfig,
    repository_root: Path,
    result: AcoliteRunResult,
) -> dict[str, Any]:
    pairing_relative = str(config.section("inputs")["phase6a_pairing_audit"])
    pairing_path = repository_root / pairing_relative
    status = _git_value(repository_root, ("status", "--porcelain"))
    return {
        "extraction_version": config.extraction_version,
        "status": config.status,
        "processing_timestamp_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "config": {
            "path": config.source_relative_path,
            "sha256": config.sha256,
        },
        "phase6a_pairing_audit": {
            "path": pairing_relative,
            "sha256": sha256_file(pairing_path),
        },
        "repository_commit": _git_value(repository_root, ("rev-parse", "HEAD")),
        "repository_worktree_dirty": bool(status),
        "python_version": sys.version.split()[0],
        "platform": platform_module.platform(terse=True),
        "package_versions": {
            "numpy": np.__version__,
            "rasterio": rasterio.__version__,
        },
        "reflectance_quantity": "rhos",
        "counts": dict(result.counts),
        "chlf_inspected": False,
        "field_matchup_generated": False,
        "processor_performance_generated": False,
        "timesat_run": False,
        "final_minimum_valid_pixel_threshold": (
            "NOT_SELECTED_REQUIRES_HUMAN_FREEZE"
        ),
    }


def write_acolite_outputs(
    result: AcoliteRunResult,
    *,
    config: AcoliteConfig,
    repository_root: str | Path,
    output_root: str | Path,
) -> dict[str, Path]:
    """Write portable ACOLITE tables under ``results/phase6b/acolite``."""

    repository = Path(repository_root)
    configured_root = Path(str(config.section("outputs")["root"]))
    requested_root = Path(output_root)
    if not requested_root.is_absolute():
        requested_root = repository / requested_root
    requested_root = _assert_output_path(
        requested_root, config=config, repository_root=repository
    )
    files = config.section("outputs")["files"]

    def target(key: str) -> Path:
        configured = Path(str(files[key]))
        relative = configured.relative_to(configured_root)
        return _assert_output_path(
            requested_root / relative,
            config=config,
            repository_root=repository,
        )

    written: dict[str, Path] = {}
    written["inventory"] = write_rows(result.inventory_rows, target("inventory"))
    written["phase6a_alignment_audit"] = write_rows(
        result.phase6a_alignment_rows, target("phase6a_alignment_audit")
    )
    written["extraction_master"] = write_rows(
        result.extraction_rows, target("extraction_master")
    )
    written["date_observation_master"] = write_rows(
        result.date_rows, target("date_observation_master")
    )
    written["product_window_indices"] = write_rows(
        result.window_rows, target("product_window_indices")
    )
    written["failure_audit"] = write_rows(
        result.failure_rows, target("failure_audit")
    )
    thresholds = [
        int(value)
        for value in config.section("spatial_summary")["qa_only_attrition_thresholds"]
    ]
    attrition = attrition_table(
        result.extraction_rows,
        thresholds=thresholds,
        count_columns={
            "NDCI": "ndci_valid_pixel_count",
            "MCI": "mci_valid_pixel_count",
            "common_B456": "common_B456_valid_count",
        },
        group_columns=("atmospheric_correction_method",),
    )
    written["attrition_table"] = write_rows(attrition, target("attrition_table"))

    manifest_path = target("provenance_manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            build_provenance_manifest(
                config=config,
                repository_root=repository,
                result=result,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    written["provenance_manifest"] = manifest_path
    return written
