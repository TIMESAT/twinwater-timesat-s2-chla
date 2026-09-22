"""Site-independent readers for already-generated ACOLITE GeoTIFF products.

This module runs no atmospheric correction. It holds the low-level ACOLITE
primitives that were previously embedded in the Erken Phase 6B extractor so a
second lake can reuse the identical numerical behaviour instead of copying it:

* nearest-wavelength selection of ``L2R rhos`` band rasters, with ambiguity and
  out-of-tolerance selection treated as explicit failures;
* selection of the ``L2W l2_flags`` raster that belongs to the same ACOLITE
  output basename;
* decoding of the ``l2_flags`` bit field into named conditions plus a
  conservative hard-invalid mask in which unknown bits count as invalid;
* derivation of the exact 20 m target grid from the product's own transform;
  and
* unpadded station-centred window reads with exact block-mean reduction for
  reflectance and exact any-flagged reduction for categorical conditions.

Nothing here knows about a lake, a configuration schema, or an output
namespace. Callers pass explicit values and keep their own provenance. Error
message text is preserved verbatim from the Phase 6B implementation so the
frozen Erken audit wording is unchanged; the Erken module re-raises these
errors as its own exception type.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from rasterio.transform import Affine
from rasterio.windows import Window

from .s2_grid import (
    GridAlignmentError,
    GridSpec,
    block_mean_reduce,
    categorical_any_invalid_reduce,
    nesting_factor,
)


class AcoliteReadError(RuntimeError):
    """Raised when an ACOLITE product cannot be read without an assumption."""


class AcoliteWindowCoverageError(AcoliteReadError):
    """Raised when a requested station-centred window is not fully covered."""


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------


def rhos_candidates(
    directory: str | Path, *, filename_marker: str
) -> list[tuple[float, Path]]:
    """Return ``(wavelength_nm, path)`` for every rhos GeoTIFF in a directory."""

    pattern = re.compile(
        rf"{re.escape(str(filename_marker))}(?P<wavelength>\d+(?:\.\d+)?)\.tiff?$",
        re.IGNORECASE,
    )
    candidates: list[tuple[float, Path]] = []
    for path in sorted(Path(directory).glob("*.tif*"), key=lambda item: item.name):
        match = pattern.search(path.name)
        if match:
            candidates.append((float(match.group("wavelength")), path))
    return candidates


def select_nearest_rhos_assets(
    candidates: Sequence[tuple[float, Path]],
    *,
    target_wavelengths_nm: Mapping[str, float],
    maximum_difference_nm: float,
) -> dict[str, tuple[float, Path]]:
    """Select one unambiguous nearest rhos raster for each logical band.

    A tie between two equally near rasters, a nearest raster outside the
    tolerance, or one raster that would serve two logical bands are all
    explicit failures rather than an arbitrary pick.
    """

    if not candidates:
        raise AcoliteReadError("no_l2r_rhos_geotiffs")
    tolerance = float(maximum_difference_nm)
    selected: dict[str, tuple[float, Path]] = {}
    used: set[Path] = set()
    for band, target_wavelength in target_wavelengths_nm.items():
        target = float(target_wavelength)
        distances = [
            (abs(wavelength - target), wavelength, path)
            for wavelength, path in candidates
        ]
        minimum = min(distance for distance, _, _ in distances)
        nearest = [
            item for item in distances if math.isclose(item[0], minimum, abs_tol=1e-12)
        ]
        if minimum > tolerance:
            raise AcoliteReadError(
                f"no_rhos_band_within_{tolerance:g}nm_for_{band}_target_{target:g}nm"
            )
        if len(nearest) != 1:
            names = ";".join(path.name for _, _, path in nearest)
            raise AcoliteReadError(f"ambiguous_nearest_rhos_band_for_{band}: {names}")
        _, wavelength, path = nearest[0]
        if path in used:
            raise AcoliteReadError(
                f"one_rhos_asset_would_supply_multiple_logical_bands: {path.name}"
            )
        used.add(path)
        selected[str(band)] = (wavelength, path)
    return selected


def scene_basename(asset_name: str, *, infix: str) -> str:
    """Return the ACOLITE output basename in front of an ``_L2R_``/``_L2W_`` infix."""

    return str(asset_name).split(infix, 1)[0]


def select_matching_flags_asset(
    directory: str | Path,
    *,
    rhos_asset: Path,
    flags_filename_marker: str,
    reflectance_infix: str = "_L2R_",
    flags_infix: str = "_L2W_",
) -> Path:
    """Select the l2_flags raster belonging to the same ACOLITE output basename."""

    marker = str(flags_filename_marker)
    prefix = scene_basename(rhos_asset.name, infix=reflectance_infix)
    candidates = [
        path
        for path in sorted(Path(directory).glob("*.tif*"), key=lambda item: item.name)
        if path.name.lower().endswith(marker.lower())
        and scene_basename(path.name, infix=flags_infix) == prefix
    ]
    if not candidates:
        raise AcoliteReadError("matching_l2w_l2_flags_geotiff_not_found")
    if len(candidates) > 1:
        raise AcoliteReadError(
            "ambiguous_matching_l2w_l2_flags_geotiff: "
            + ";".join(path.name for path in candidates)
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Flag decoding
# ---------------------------------------------------------------------------


def decode_flag_bits(
    values: np.ndarray,
    *,
    flag_exponents: Mapping[str, Any],
    hard_invalid_flags: Sequence[str],
    nodata_mask: np.ndarray | None = None,
    unknown_bits_hard: bool = True,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Decode named ACOLITE bits and build a conservative hard-invalid mask.

    Any bit that is set but not named in ``flag_exponents`` is reported as
    ``unknown_bits`` and, by default, counts as hard invalid: an unrecognised
    condition is never assumed benign.
    """

    array = np.asarray(values)
    if array.ndim != 2:
        raise AcoliteReadError(
            f"ACOLITE l2_flags must be two-dimensional; got {array.shape}."
        )
    if not np.all(np.isfinite(array)):
        raise AcoliteReadError(
            "ACOLITE l2_flags contains non-finite unmasked values."
        )
    integer = array.astype("int64")
    if np.any(integer < 0) or not np.array_equal(integer.astype(array.dtype), array):
        raise AcoliteReadError(
            "ACOLITE l2_flags must contain non-negative integer bit fields."
        )

    layers: dict[str, np.ndarray] = {}
    known_mask = 0
    for name, exponent in flag_exponents.items():
        bit = 1 << int(exponent)
        known_mask |= bit
        layers[str(name)] = (integer & bit) != 0
    unknown = (integer & ~known_mask) != 0
    layers["unknown_bits"] = unknown

    hard = np.zeros(integer.shape, dtype=bool)
    for name in (str(item) for item in hard_invalid_flags):
        hard |= layers[name]
    if unknown_bits_hard:
        hard |= unknown
    nodata = (
        np.zeros(integer.shape, dtype=bool)
        if nodata_mask is None
        else np.asarray(nodata_mask).astype(bool)
    )
    if nodata.shape != integer.shape:
        raise AcoliteReadError("l2_flags nodata mask shape does not match data.")
    layers["flags_nodata"] = nodata
    hard |= nodata
    return layers, hard, integer


def parse_flag_exponent_settings(
    settings_paths: Iterable[str | Path], *, setting_keys: Iterable[str]
) -> dict[str, set[int]]:
    """Read declared ACOLITE flag-exponent settings from run settings files.

    Returns one set of declared values per requested setting key so the caller
    can refuse a customized bit layout that its decoder would misinterpret. A
    value that is present but unparseable is an explicit failure.
    """

    observed: dict[str, set[int]] = {str(key): set() for key in setting_keys}
    for item in settings_paths:
        path = Path(item)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw = (part.strip() for part in stripped.split("=", 1))
            if key not in observed:
                continue
            try:
                value = int(raw.split("#", 1)[0].strip())
            except ValueError as error:
                raise AcoliteReadError(
                    f"invalid {key} value {raw!r} in {path.name}"
                ) from error
            observed[key].add(value)
    return observed


# ---------------------------------------------------------------------------
# Grid and window reading
# ---------------------------------------------------------------------------


def derive_target_grid(
    source: GridSpec,
    *,
    target_resolution_m: float,
    accepted_native_resolutions_m: Sequence[float],
    origin_tolerance_m: float = 1e-3,
    pixel_size_tolerance_m: float = 1e-3,
) -> tuple[GridSpec, int]:
    """Return the target grid and the exact native-to-target reduction factor."""

    target_resolution = float(target_resolution_m)
    tolerance = float(pixel_size_tolerance_m)
    if abs(source.pixel_size_x - source.pixel_size_y) > tolerance:
        raise GridAlignmentError(
            f"ACOLITE pixels are not square: {source.pixel_size_x} x "
            f"{source.pixel_size_y} m."
        )
    accepted = [float(value) for value in accepted_native_resolutions_m]
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
        origin_tolerance_m=float(origin_tolerance_m),
        pixel_size_tolerance_m=tolerance,
        fine_label="ACOLITE native grid",
        coarse_label="20 m target grid",
    )
    return target, factor


def read_native_window(
    dataset: Any,
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> np.ma.MaskedArray:
    """Read the native-resolution footprint of one target-grid window."""

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
        raise AcoliteWindowCoverageError(
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


def read_reflectance_window(
    dataset: Any,
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Read one rhos window onto the target grid, applying the GeoTIFF terms.

    The raster's own scale/offset are applied and an exact block mean brings a
    finer native grid onto the target grid. Negative reflectance is preserved;
    masked source pixels become ``NaN`` and are reported as nodata.
    """

    masked = read_native_window(
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
        raise AcoliteReadError("ACOLITE GeoTIFF scale/offset is non-finite.")
    values = values * scale + offset
    if factor > 1:
        values = block_mean_reduce(values, factor)
        nodata = categorical_any_invalid_reduce(nodata, factor)
    return values, nodata, scale, offset


def reduce_flag_window(
    layers: Mapping[str, np.ndarray],
    hard: np.ndarray,
    integer: np.ndarray,
    *,
    factor: int,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Reduce decoded flags onto a coarser target grid without interpolation."""

    if factor == 1:
        return dict(layers), hard, integer

    reduced_layers = {
        name: categorical_any_invalid_reduce(flags, factor)
        for name, flags in layers.items()
    }
    reduced_hard = categorical_any_invalid_reduce(hard, factor)
    # Bitwise OR preserves which fine-grid conditions occurred in each target
    # cell; it is used only as a diagnostic value, never interpolation.
    height, width = integer.shape
    reshaped = integer.reshape(height // factor, factor, width // factor, factor)
    reduced_integer = np.bitwise_or.reduce(
        np.bitwise_or.reduce(reshaped, axis=3), axis=1
    )
    return reduced_layers, reduced_hard, reduced_integer
