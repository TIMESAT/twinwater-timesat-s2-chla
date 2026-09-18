from __future__ import annotations

import numpy as np
import pandas as pd

from twinwater_timesat.reliability_synthesis import (
    INPUT_PATHS,
    MetricSpec,
    _assign_tertiles,
    _metric_vector,
    _paired_year_differences,
    _scenario_year_summary,
    cluster_bootstrap_mean_ci,
)


def test_input_allowlist_is_erken_only() -> None:
    assert INPUT_PATHS
    assert all("vomb" not in path.lower() for path in INPUT_PATHS)


def test_cluster_bootstrap_is_deterministic_and_uses_year_values() -> None:
    first = cluster_bootstrap_mean_ci([1.0, 2.0, 3.0], key="same")
    second = cluster_bootstrap_mean_ci([1.0, 2.0, 3.0], key="same")
    assert first == second
    assert first[0] == 2.0
    assert first[3] == 3
    assert first[1] <= first[0] <= first[2]


def test_scenario_summary_weights_scenarios_within_year_only() -> None:
    rows = []
    for value in [0.0] * 100:
        rows.append(
            {
                "year": 2020,
                "method": "linear_interpolation",
                "level": 1,
                "reconstruction_status": "ok",
                "n_negative_reconstructed_days": 0,
                "nrmse": value,
                "coverage": 1.0,
            }
        )
    rows.append(
        {
            "year": 2021,
            "method": "linear_interpolation",
            "level": 1,
            "reconstruction_status": "ok",
            "n_negative_reconstructed_days": 0,
            "nrmse": 10.0,
            "coverage": 2.0,
        }
    )
    table = _scenario_year_summary(
        pd.DataFrame(rows),
        strata=("level",),
        metrics=(MetricSpec("nrmse", "nRMSE", "fraction", "lower"),),
        coverage_columns=("coverage",),
    )
    assert len(table) == 2
    assert table.set_index("year").loc[2020, "nrmse"] == 0.0
    assert table.set_index("year").loc[2021, "nrmse"] == 10.0
    assert table["n_scenarios"].tolist() == [100, 1]


def test_peak_failure_is_retained_as_non_success() -> None:
    data = pd.DataFrame(
        {
            "reference_peak_status": ["ok", "ok"],
            "reference_peak_at_boundary": [False, False],
            "peak_timing_success_10d": [True, pd.NA],
        }
    )
    values, ineligible = _metric_vector(
        data,
        MetricSpec("peak_timing_success_10d", "success", "fraction", "higher", True),
    )
    assert ineligible == 0
    assert values.tolist() == [1.0, 0.0]


def test_paired_advantage_has_common_positive_interpretation() -> None:
    year = pd.DataFrame(
        {
            "year": [2020, 2020],
            "method": ["a", "b"],
            "error": [1.0, 2.0],
            "correlation": [0.8, 0.5],
        }
    )
    paired = _paired_year_differences(
        year,
        strata=(),
        metrics=(
            MetricSpec("error", "error", "x", "lower"),
            MetricSpec("correlation", "correlation", "r", "higher"),
        ),
        method_pairs=(("a", "b"),),
    ).set_index("metric")
    assert paired.loc["error", "raw_difference_a_minus_b"] == -1.0
    assert paired.loc["error", "advantage_for_method_a"] == 1.0
    assert np.isclose(paired.loc["correlation", "advantage_for_method_a"], 0.3)


def test_tertiles_are_derived_within_duration() -> None:
    data = pd.DataFrame(
        {
            "duration_days": [10, 10, 10, 20, 20, 20],
            "a_gap": [0.0, 1.0, 2.0, 100.0, 200.0, 300.0],
        }
    )
    assigned, cuts = _assign_tertiles(
        data,
        value_column="a_gap",
        group_columns=("duration_days",),
        output_column="activity_class",
    )
    assert assigned.groupby("duration_days")["activity_class"].apply(set).to_dict() == {
        10: {"low", "medium", "high"},
        20: {"low", "medium", "high"},
    }
    cut_table = cuts.set_index("duration_days")
    assert cut_table.loc[10, "upper_tertile_cut"] < cut_table.loc[20, "lower_tertile_cut"]


def test_global_tertiles_support_no_group_columns() -> None:
    assigned, cuts = _assign_tertiles(
        pd.DataFrame({"value": [1.0, 2.0, 3.0]}),
        value_column="value",
        group_columns=(),
        output_column="class",
    )
    assert assigned["class"].tolist() == ["low", "medium", "high"]
    assert len(cuts) == 1
