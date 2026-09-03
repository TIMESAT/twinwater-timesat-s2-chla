from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.mechanism_diagnostic import (
    COARSE_SMOOTHING_GRID,
    P_SEAPAR_GRID,
    build_interval_geometry_table,
    classify_mechanism_case,
    interval_geometry,
    nonzero_derivative_sign_changes,
    p_seapar_to_internal_smoothing,
)


def test_diagnostic_grids_are_exact_and_not_selection_grids() -> None:
    assert P_SEAPAR_GRID == (
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    )
    assert COARSE_SMOOTHING_GRID == (1000.0, 300.0, 100.0, 30.0, 10.0, 3.0, 1.0, 0.0)


@pytest.mark.parametrize(
    ("p_seapar", "expected"),
    [(0.0, 1000.0), (0.1, 5900.0), (0.5, 25500.0), (1.0, 50000.0)],
)
def test_frozen_p_seapar_mapping(p_seapar: float, expected: float) -> None:
    assert p_seapar_to_internal_smoothing(p_seapar) == expected


def test_p_seapar_mapping_rejects_out_of_range_values() -> None:
    for value in (-0.1, 1.1, np.nan):
        with pytest.raises(ValueError):
            p_seapar_to_internal_smoothing(value)


def test_interval_geometry_records_signed_endpoint_overshoot() -> None:
    result = interval_geometry(
        [0.5, 1.5, 4.0, -1.0], lower_endpoint=1.0, upper_endpoint=3.0, scale=2.0
    )
    assert result["n_interior_points"] == 4
    assert result["n_outside_endpoint_range"] == 3
    assert result["spline0_exceeds_endpoint_range"]
    assert result["fraction_outside_endpoint_range"] == 0.75
    assert result["max_positive_overshoot"] == 1.0
    assert result["max_negative_overshoot"] == -2.0
    assert result["max_negative_overshoot_magnitude"] == 2.0
    assert result["normalized_max_absolute_overshoot"] == 1.0


def test_derivative_sign_changes_ignore_exact_plateaus() -> None:
    assert nonzero_derivative_sign_changes([1, 2, 2, 3, 2, 2, 1, 4]) == 2
    assert nonzero_derivative_sign_changes([1, 1, 1]) == 0


@pytest.mark.parametrize(
    ("coarse", "status", "expected"),
    [
        (False, "missed_no_peak_within_15d", "coarse_season_detection_bottleneck"),
        (True, "missed_no_peak_within_15d", "final_double_logistic_fitting_bottleneck"),
        (False, "matched", "final_fit_peak_without_nearby_filtered_coarse_peak"),
        (True, "matched", "coarse_and_final_peak_within_15d"),
    ],
)
def test_mechanism_case_is_a_factual_transition(
    coarse: bool, status: str, expected: str
) -> None:
    assert classify_mechanism_case(coarse, status) == expected


def test_interval_table_refuses_cross_segment_geometry() -> None:
    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    support = pd.DataFrame(
        {
            "date": dates,
            "year": 2020,
            "CHLF": [1.0, 2.0, 3.0],
            "common_support": True,
            "reference_value_available": True,
            "s2_openwater_reference_candidate": [True, False, True],
            "common_support_segment_id": ["s1", "s1", "s2"],
        }
    )
    curves = pd.concat(
        [
            pd.DataFrame(
                {
                    "date": dates,
                    "year": 2020,
                    "method": method,
                    "prediction": [1.0, 2.0, 3.0],
                }
            )
            for method in (
                "linear_interpolation",
                "timesat_smoothing_spline_0",
                "timesat_smoothing_spline_selected",
            )
        ],
        ignore_index=True,
    )
    table = build_interval_geometry_table(support, curves, {2020: 100})
    assert len(table) == 1
    assert table.loc[0, "interval_status"] == "unavailable_cross_segment"
    assert not table.loc[0, "spline0_exceeds_endpoint_range"]
    assert np.isnan(table.loc[0, "spline0_withheld_rmse"])
