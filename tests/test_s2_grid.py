"""Common 20 m grid alignment, continuous reduction and categorical mapping."""

from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from twinwater_timesat.s2_grid import (
    GridAlignmentError,
    GridSpec,
    assert_resampling_allowed,
    assert_same_grid,
    block_mean_reduce,
    categorical_any_invalid_reduce,
    categorical_expand,
    coarse_window_for_target,
    extract_target_window_from_coarse,
    nesting_factor,
    pixel_centre_coordinates,
)


CRS = "EPSG:32634"
ORIGIN_X = 366840.0
ORIGIN_Y = 6636120.0


def spec(resolution: float, size: int, *, origin_x: float = ORIGIN_X) -> GridSpec:
    return GridSpec(
        crs=CRS,
        transform=Affine(resolution, 0.0, origin_x, 0.0, -resolution, ORIGIN_Y),
        width=size,
        height=size,
    )


def test_identical_grids_are_accepted():
    assert_same_grid(spec(20.0, 12), spec(20.0, 12))


def test_shifted_origin_is_an_explicit_failure():
    with pytest.raises(GridAlignmentError, match="origin mismatch"):
        assert_same_grid(spec(20.0, 12), spec(20.0, 12, origin_x=ORIGIN_X + 10.0))


def test_crs_mismatch_is_an_explicit_failure():
    other = GridSpec(
        crs="EPSG:32633",
        transform=Affine(20.0, 0.0, ORIGIN_X, 0.0, -20.0, ORIGIN_Y),
        width=12,
        height=12,
    )
    with pytest.raises(GridAlignmentError, match="CRS mismatch"):
        assert_same_grid(spec(20.0, 12), other)


def test_dimension_mismatch_is_an_explicit_failure():
    with pytest.raises(GridAlignmentError, match="dimension mismatch"):
        assert_same_grid(spec(20.0, 12), spec(20.0, 24))


def test_rotated_transform_is_refused():
    rotated = GridSpec(
        crs=CRS,
        transform=Affine(20.0, 1.0, ORIGIN_X, 0.5, -20.0, ORIGIN_Y),
        width=12,
        height=12,
    )
    with pytest.raises(GridAlignmentError, match="rotated"):
        assert_same_grid(rotated, spec(20.0, 12))


def test_b4_10m_nests_exactly_inside_the_b5_b6_20m_grid():
    assert nesting_factor(spec(10.0, 24), spec(20.0, 12)) == 2


def test_60m_mask_nests_exactly_around_the_20m_grid():
    assert nesting_factor(spec(20.0, 12), spec(60.0, 4)) == 3


def test_non_integer_nesting_is_an_explicit_failure():
    with pytest.raises(GridAlignmentError, match="integer"):
        nesting_factor(spec(15.0, 16), spec(20.0, 12))


def test_misaligned_origin_blocks_nesting():
    with pytest.raises(GridAlignmentError, match="common origin"):
        nesting_factor(spec(10.0, 24, origin_x=ORIGIN_X + 5.0), spec(20.0, 12))


def test_dimensions_must_match_the_nesting_factor():
    with pytest.raises(GridAlignmentError, match="not 2x"):
        nesting_factor(spec(10.0, 20), spec(20.0, 12))


def test_block_mean_preserves_reflectance():
    fine = np.array(
        [
            [0.10, 0.20, 1.0, 1.0],
            [0.30, 0.40, 1.0, 1.0],
            [0.0, 0.0, 0.5, 0.5],
            [0.0, 0.0, 0.5, 0.5],
        ]
    )
    reduced = block_mean_reduce(fine, 2)
    assert reduced.shape == (2, 2)
    assert reduced[0, 0] == pytest.approx(0.25)
    assert reduced[0, 1] == pytest.approx(1.0)
    assert reduced[1, 1] == pytest.approx(0.5)


def test_block_mean_is_not_nearest_neighbour():
    fine = np.array([[0.0, 0.0], [0.0, 0.4]])
    assert block_mean_reduce(fine, 2)[0, 0] == pytest.approx(0.1)


def test_block_mean_propagates_missing_radiometry():
    fine = np.array([[np.nan, 0.2], [0.2, 0.2]])
    assert np.isnan(block_mean_reduce(fine, 2)[0, 0])


def test_block_mean_refuses_a_non_multiple_shape():
    with pytest.raises(GridAlignmentError, match="exact multiple"):
        block_mean_reduce(np.zeros((3, 3)), 2)


def test_categorical_expansion_replicates_exact_class_values():
    coarse = np.array([[1, 2], [3, 4]])
    expanded = categorical_expand(coarse, 3)
    assert expanded.shape == (6, 6)
    assert set(np.unique(expanded).tolist()) == {1, 2, 3, 4}
    assert (expanded[0:3, 0:3] == 1).all()
    assert (expanded[3:6, 3:6] == 4).all()


def test_categorical_expansion_never_invents_a_class_value():
    coarse = np.array([[0, 8]])
    expanded = categorical_expand(coarse, 3)
    # Interpolation would produce intermediate codes such as 4; exact footprint
    # mapping cannot.
    assert set(np.unique(expanded).tolist()) == {0, 8}


def test_conservative_any_invalid_reduction():
    fine = np.array(
        [
            [False, False, False, False],
            [False, True, False, False],
            [False, False, False, False],
            [False, False, False, False],
        ]
    )
    reduced = categorical_any_invalid_reduce(fine, 2)
    assert reduced.tolist() == [[True, False], [False, False]]


def test_60m_to_20m_propagation_covers_the_frozen_window():
    # The frozen 3x3 window at 20 m rows/cols 4-6 spans 60 m cells (1,1)-(2,2).
    row_start, col_start, size = coarse_window_for_target(
        target_row=4, target_col=4, target_size=3, factor=3
    )
    assert (row_start, col_start, size) == (1, 1, 2)

    coarse = np.array([[10, 20], [30, 40]])
    window = extract_target_window_from_coarse(
        coarse,
        coarse_row_offset=row_start,
        coarse_col_offset=col_start,
        target_row=4,
        target_col=4,
        target_size=3,
        factor=3,
    )
    assert window.shape == (3, 3)
    # 20 m rows 4-5 / cols 4-5 fall in coarse cell (1,1)=10; row/col 6 in (2,2).
    assert window.tolist() == [[10, 10, 20], [10, 10, 20], [30, 30, 40]]


def test_coarse_block_must_cover_the_window():
    with pytest.raises(GridAlignmentError, match="does not fully cover"):
        extract_target_window_from_coarse(
            np.array([[1]]),
            coarse_row_offset=1,
            coarse_col_offset=1,
            target_row=4,
            target_col=4,
            target_size=3,
            factor=3,
        )


@pytest.mark.parametrize(
    "method", ["bilinear", "cubic", "cubic_spline", "lanczos", "average"]
)
def test_interpolating_resampling_is_refused_for_categorical_qa(method):
    with pytest.raises(GridAlignmentError, match="invent class values"):
        assert_resampling_allowed(method, categorical=True)


def test_nearest_neighbour_is_refused_for_continuous_reflectance():
    with pytest.raises(GridAlignmentError, match="reflectance-preserving"):
        assert_resampling_allowed("nearest", categorical=False)


def test_nearest_neighbour_is_allowed_for_categorical_qa():
    assert_resampling_allowed("nearest", categorical=True)


def test_pixel_centre_coordinates_are_audited_from_the_transform():
    x, y = pixel_centre_coordinates(spec(20.0, 12), 0, 0)
    assert x == pytest.approx(ORIGIN_X + 10.0)
    assert y == pytest.approx(ORIGIN_Y - 10.0)
