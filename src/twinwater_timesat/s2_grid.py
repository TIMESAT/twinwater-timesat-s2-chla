"""Common 20 m grid alignment for reflectance and categorical QA layers.

The frozen Erken analysis support is a station-centred 3x3 window on the 20 m
grid. Phase 6A brings every layer onto that exact grid under two rules:

* continuous reflectance is reduced by reflectance-preserving block averaging -
  nearest neighbour is forbidden;
* categorical QA is never interpolated - a coarse mask is expanded by exact
  footprint mapping, and a fine mask is reduced by a conservative any-invalid
  rule.

Grids must be exactly nested and co-registered. A real misalignment raises an
explicit failure; Phase 6A never resamples its way past one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from rasterio.transform import Affine


class GridAlignmentError(ValueError):
    """Raised when two rasters are not exactly nested or co-registered."""


FORBIDDEN_CONTINUOUS_RESAMPLING: frozenset[str] = frozenset({"nearest"})
FORBIDDEN_CATEGORICAL_RESAMPLING: frozenset[str] = frozenset(
    {"bilinear", "cubic", "cubic_spline", "lanczos", "average"}
)


@dataclass(frozen=True)
class GridSpec:
    """The geometry of one raster, as read from its own affine transform."""

    crs: str
    transform: Affine
    width: int
    height: int

    @property
    def pixel_size_x(self) -> float:
        return abs(float(self.transform.a))

    @property
    def pixel_size_y(self) -> float:
        return abs(float(self.transform.e))

    @property
    def origin_x(self) -> float:
        return float(self.transform.c)

    @property
    def origin_y(self) -> float:
        return float(self.transform.f)

    def audit(self) -> dict[str, Any]:
        """Return the auditable geometry fields recorded for every product."""

        return {
            "crs": self.crs,
            "transform_a": float(self.transform.a),
            "transform_b": float(self.transform.b),
            "transform_c": float(self.transform.c),
            "transform_d": float(self.transform.d),
            "transform_e": float(self.transform.e),
            "transform_f": float(self.transform.f),
            "width": int(self.width),
            "height": int(self.height),
            "pixel_size_x": self.pixel_size_x,
            "pixel_size_y": self.pixel_size_y,
        }


def grid_spec_from_dataset(dataset: Any) -> GridSpec:
    """Build a :class:`GridSpec` from an open rasterio dataset."""

    crs = dataset.crs
    return GridSpec(
        crs=str(crs.to_string()) if crs is not None else "",
        transform=dataset.transform,
        width=int(dataset.width),
        height=int(dataset.height),
    )


def _assert_axis_aligned(spec: GridSpec, label: str) -> None:
    if abs(float(spec.transform.b)) > 0 or abs(float(spec.transform.d)) > 0:
        raise GridAlignmentError(
            f"{label} raster has a rotated/sheared affine transform; Phase 6A "
            "requires axis-aligned Sentinel-2 grids."
        )


def assert_same_grid(
    left: GridSpec,
    right: GridSpec,
    *,
    origin_tolerance_m: float = 1e-3,
    pixel_size_tolerance_m: float = 1e-3,
    left_label: str = "left",
    right_label: str = "right",
) -> None:
    """Require two rasters to be the identical grid, not merely similar."""

    _assert_axis_aligned(left, left_label)
    _assert_axis_aligned(right, right_label)
    if left.crs != right.crs:
        raise GridAlignmentError(
            f"CRS mismatch between {left_label} ({left.crs}) and {right_label} "
            f"({right.crs})."
        )
    if (
        abs(left.pixel_size_x - right.pixel_size_x) > pixel_size_tolerance_m
        or abs(left.pixel_size_y - right.pixel_size_y) > pixel_size_tolerance_m
    ):
        raise GridAlignmentError(
            f"Pixel size mismatch between {left_label} "
            f"({left.pixel_size_x}x{left.pixel_size_y} m) and {right_label} "
            f"({right.pixel_size_x}x{right.pixel_size_y} m)."
        )
    if (
        abs(left.origin_x - right.origin_x) > origin_tolerance_m
        or abs(left.origin_y - right.origin_y) > origin_tolerance_m
    ):
        raise GridAlignmentError(
            f"Grid origin mismatch between {left_label} "
            f"({left.origin_x}, {left.origin_y}) and {right_label} "
            f"({right.origin_x}, {right.origin_y})."
        )
    if left.width != right.width or left.height != right.height:
        raise GridAlignmentError(
            f"Raster dimension mismatch between {left_label} "
            f"({left.width}x{left.height}) and {right_label} "
            f"({right.width}x{right.height})."
        )


def nesting_factor(
    fine: GridSpec,
    coarse: GridSpec,
    *,
    origin_tolerance_m: float = 1e-3,
    pixel_size_tolerance_m: float = 1e-3,
    fine_label: str = "fine",
    coarse_label: str = "coarse",
) -> int:
    """Return the exact integer factor by which ``fine`` nests inside ``coarse``."""

    _assert_axis_aligned(fine, fine_label)
    _assert_axis_aligned(coarse, coarse_label)
    if fine.crs != coarse.crs:
        raise GridAlignmentError(
            f"CRS mismatch between {fine_label} ({fine.crs}) and {coarse_label} "
            f"({coarse.crs}); Phase 6A does not reproject to force nesting."
        )
    if fine.pixel_size_x <= 0 or fine.pixel_size_y <= 0:
        raise GridAlignmentError(f"{fine_label} raster has a non-positive pixel size.")

    ratio_x = coarse.pixel_size_x / fine.pixel_size_x
    ratio_y = coarse.pixel_size_y / fine.pixel_size_y
    factor = int(round(ratio_x))
    if (
        factor < 1
        or abs(ratio_x - factor) > 1e-6
        or abs(ratio_y - factor) > 1e-6
    ):
        raise GridAlignmentError(
            f"{fine_label} ({fine.pixel_size_x} m) does not nest by an integer "
            f"factor inside {coarse_label} ({coarse.pixel_size_x} m); "
            f"ratio={ratio_x:.6f}."
        )
    if (
        abs(fine.origin_x - coarse.origin_x) > origin_tolerance_m
        or abs(fine.origin_y - coarse.origin_y) > origin_tolerance_m
    ):
        raise GridAlignmentError(
            f"{fine_label} and {coarse_label} grids share no common origin "
            f"({fine.origin_x}, {fine.origin_y}) vs "
            f"({coarse.origin_x}, {coarse.origin_y}); exact nesting is required."
        )
    expected_width = coarse.width * factor
    expected_height = coarse.height * factor
    if fine.width != expected_width or fine.height != expected_height:
        raise GridAlignmentError(
            f"{fine_label} dimensions {fine.width}x{fine.height} are not "
            f"{factor}x the {coarse_label} dimensions "
            f"{coarse.width}x{coarse.height}."
        )
    return factor


def block_mean_reduce(values: np.ndarray, factor: int) -> np.ndarray:
    """Reduce a continuous array by an exact ``factor`` block mean.

    This is the reflectance-preserving reduction used to bring native 10 m L1C
    B4 onto the exact B5/B6 20 m grid. ``NaN`` inputs propagate: a block
    containing any missing radiometry yields ``NaN`` rather than a partially
    supported mean.
    """

    if factor < 1:
        raise GridAlignmentError("Block reduction factor must be a positive integer.")
    array = np.asarray(values, dtype="float64")
    if array.ndim != 2:
        raise GridAlignmentError("Block reduction requires a two-dimensional array.")
    if factor == 1:
        return array.copy()
    height, width = array.shape
    if height % factor or width % factor:
        raise GridAlignmentError(
            f"Array shape {array.shape} is not an exact multiple of the block "
            f"factor {factor}; Phase 6A does not pad or crop to force a fit."
        )
    reshaped = array.reshape(height // factor, factor, width // factor, factor)
    return reshaped.mean(axis=(1, 3))


def categorical_expand(values: np.ndarray, factor: int) -> np.ndarray:
    """Expand a coarse categorical array by exact footprint replication.

    Each source class value covers exactly the ``factor`` x ``factor`` finer
    cells it spans. No interpolation is involved, so no class value can be
    invented.
    """

    if factor < 1:
        raise GridAlignmentError("Expansion factor must be a positive integer.")
    array = np.asarray(values)
    if array.ndim != 2:
        raise GridAlignmentError("Categorical expansion requires a 2-D array.")
    return np.repeat(np.repeat(array, factor, axis=0), factor, axis=1)


def categorical_any_invalid_reduce(flags: np.ndarray, factor: int) -> np.ndarray:
    """Reduce a fine Boolean invalidity mask conservatively to a coarse grid.

    A coarse cell is invalid when any nested fine cell is invalid. This is the
    documented conservative rule; it never averages or interpolates class codes.
    """

    if factor < 1:
        raise GridAlignmentError("Reduction factor must be a positive integer.")
    array = np.asarray(flags).astype(bool)
    if array.ndim != 2:
        raise GridAlignmentError("Categorical reduction requires a 2-D array.")
    if factor == 1:
        return array.copy()
    height, width = array.shape
    if height % factor or width % factor:
        raise GridAlignmentError(
            f"Mask shape {array.shape} is not an exact multiple of the "
            f"reduction factor {factor}."
        )
    reshaped = array.reshape(height // factor, factor, width // factor, factor)
    return reshaped.any(axis=(1, 3))


def coarse_window_for_target(
    *,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> tuple[int, int, int]:
    """Return the coarse row/col offset and size covering a target-grid window.

    Used to read the minimum 60 m mask footprint that fully covers the frozen
    20 m 3x3 window, so the expansion below stays exact.
    """

    if factor < 1:
        raise GridAlignmentError("Nesting factor must be a positive integer.")
    row_start = target_row // factor
    col_start = target_col // factor
    row_stop = (target_row + target_size - 1) // factor + 1
    col_stop = (target_col + target_size - 1) // factor + 1
    size = max(row_stop - row_start, col_stop - col_start)
    return row_start, col_start, size


def extract_target_window_from_coarse(
    coarse_values: np.ndarray,
    *,
    coarse_row_offset: int,
    coarse_col_offset: int,
    target_row: int,
    target_col: int,
    target_size: int,
    factor: int,
) -> np.ndarray:
    """Expand a coarse categorical block and cut the exact target-grid window."""

    expanded = categorical_expand(coarse_values, factor)
    row_start = target_row - coarse_row_offset * factor
    col_start = target_col - coarse_col_offset * factor
    if row_start < 0 or col_start < 0:
        raise GridAlignmentError(
            "Coarse block does not cover the requested target window origin."
        )
    row_stop = row_start + target_size
    col_stop = col_start + target_size
    if row_stop > expanded.shape[0] or col_stop > expanded.shape[1]:
        raise GridAlignmentError(
            "Coarse block does not fully cover the requested target window."
        )
    return expanded[row_start:row_stop, col_start:col_stop]


def assert_resampling_allowed(method: str, *, categorical: bool) -> None:
    """Refuse resampling methods that would corrupt reflectance or class codes."""

    name = str(method).strip().lower()
    if categorical and name in FORBIDDEN_CATEGORICAL_RESAMPLING:
        raise GridAlignmentError(
            f"Resampling method {method!r} is forbidden for categorical QA; "
            "interpolation must never invent class values."
        )
    if not categorical and name in FORBIDDEN_CONTINUOUS_RESAMPLING:
        raise GridAlignmentError(
            f"Resampling method {method!r} is forbidden for continuous "
            "reflectance; use reflectance-preserving block averaging."
        )


def pixel_centre_coordinates(spec: GridSpec, row: int, col: int) -> tuple[float, float]:
    """Return the map coordinates of one pixel centre, for alignment audits."""

    x = spec.transform.c + (col + 0.5) * spec.transform.a
    y = spec.transform.f + (row + 0.5) * spec.transform.e
    if not (math.isfinite(x) and math.isfinite(y)):
        raise GridAlignmentError("Pixel centre calculation produced non-finite values.")
    return float(x), float(y)
