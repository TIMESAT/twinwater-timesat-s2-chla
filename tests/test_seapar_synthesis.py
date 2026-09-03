from __future__ import annotations

import pandas as pd
import pytest

from twinwater_timesat.seapar_actual import CV_METHOD, DEFAULT_METHOD
from twinwater_timesat.seapar_synthesis import (
    _comparison_delta,
    _controlled_summary,
    _equal_year_summary,
    _event_scenario_summary,
)


def test_event_scenario_summary_keeps_valid_miss_in_denominator() -> None:
    events = pd.DataFrame(
        {
            "mask_id": ["m1", "m1"],
            "method": [CV_METHOD, CV_METHOD],
            "event_status": ["matched", "missed_no_peak_within_15d"],
            "success_5d": [True, False],
            "success_10d": [True, False],
            "success_15d": [True, False],
            "absolute_timing_error_days": [4.0, float("nan")],
            "normalized_absolute_magnitude_error": [0.2, float("nan")],
        }
    )
    result = _event_scenario_summary(events).iloc[0]
    assert result["event_reference_count"] == 2
    assert result["event_recovery_fraction_10d"] == 0.5
    assert result["event_median_absolute_timing_error_matched_days"] == 4.0


def test_controlled_summary_retains_year_before_equal_year_aggregation() -> None:
    rows = []
    for year, nrmse in ((2020, 1.0), (2021, 100.0)):
        rows.append(
            {
                "year": year,
                "method": CV_METHOD,
                "deletion_fraction": 0.1,
                "reconstruction_status": "ok",
                "mae": nrmse,
                "rmse": nrmse,
                "nrmse": nrmse,
                "absolute_peak_date_error_days": 5.0,
                "normalized_absolute_peak_magnitude_error": 0.2,
                "absolute_integral_error": 1.0,
                "pearson_correlation": 0.9,
                "n_negative_reconstructed_days": 0,
                "peak_timing_success_5d": True,
                "peak_timing_success_10d": True,
                "peak_timing_success_15d": True,
                "event_recovery_fraction_5d": 0.5,
                "event_recovery_fraction_10d": 0.5,
                "event_recovery_fraction_15d": 0.5,
                "event_median_absolute_timing_error_matched_days": 4.0,
                "event_median_normalized_absolute_magnitude_error_matched": 0.2,
            }
        )
    within_year = _controlled_summary(
        pd.DataFrame(rows), ["year", "method", "deletion_fraction"]
    )
    assert len(within_year) == 2
    equal_year = _equal_year_summary(
        within_year, ["method", "deletion_fraction"]
    )
    assert equal_year.iloc[0]["equal_year_mean_mean_nrmse"] == 50.5
    assert equal_year.iloc[0]["n_years"] == 2


def test_default_vs_cv_delta_direction_is_cv_minus_default() -> None:
    table = pd.DataFrame(
        {
            "year": [2020, 2020],
            "method": [DEFAULT_METHOD, CV_METHOD],
            "nrmse": [0.3, 0.2],
            "recovery_fraction_10d": [0.25, 0.75],
        }
    )
    delta = _comparison_delta(
        table,
        keys=["year"],
        metrics=["nrmse", "recovery_fraction_10d"],
    ).iloc[0]
    assert delta["cv_minus_default_nrmse"] == pytest.approx(-0.1)
    assert delta["cv_minus_default_recovery_fraction_10d"] == pytest.approx(0.5)
