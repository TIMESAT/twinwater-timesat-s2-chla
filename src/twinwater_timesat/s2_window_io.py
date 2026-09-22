"""Shared station-centred window reading for Sentinel-2 SAFE products.

These readers were factored out of the Erken Phase 6A pilot so a second lake
can reuse exactly the same low-level behaviour instead of copying it. Nothing
here is site-specific: the caller supplies the product, the target grid, the
pixel indices of the window centre, and the grid tolerances.

The rules enforced here are the ones the Phase 6A protocol fixed and that the
Erken/Vombsjon transfer freeze carries forward:

* continuous reflectance is reduced by reflectance-preserving block averaging,
  never by nearest neighbour;
* categorical QA is never interpolated - a coarse mask is expanded by exact
  footprint mapping and a fine Boolean mask is reduced by a conservative
  any-invalid rule, while a multi-class layer refuses to be reduced at all; and
* a window that is not fully inside the raster is an explicit failure, because
  the window is never padded.

Error message text is preserved verbatim from the Phase 6A implementation so
the frozen Erken audit wording is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

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
from .s2_safe import SAFEProduct, select_band_asset


def read_window(dataset: Any, *, row: int, col: int, size: int) -> np.ndarray:
    """Read an unpadded window, failing if the requested support is incomplete."""

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
            f"The requested {size}x{size} station-centred window is not fully "
            "inside the raster; Phase 6A does not pad the window."
        )
    window = Window(col_off=col_start, row_off=row_start, width=size, height=size)
    return dataset.read(window=window, boundless=False)


def read_target_band(
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
            values = read_window(
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


def read_categorical_window(
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
    MSK_QUALIT follows its spectral band (10 m for B4, 20 m for B5/B6) while
    MSK_CLASSI is 60 m - so all three geometries are handled explicitly:

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
            values = read_window(
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
