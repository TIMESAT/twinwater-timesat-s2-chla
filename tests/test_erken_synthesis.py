from __future__ import annotations

import pandas as pd

from twinwater_timesat.erken_synthesis import (
    INPUT_PATHS,
    _event_scenario_summary,
    _summary,
)


def test_phase_d_input_allowlist_is_erken_only() -> None:
    assert INPUT_PATHS
    assert all("vomb" not in path.lower() for path in INPUT_PATHS)


def test_event_scenario_summary_keeps_misses_in_available_denominator() -> None:
    events = pd.DataFrame(
        {
            "mask_id": ["m1", "m1"],
            "method": ["linear_interpolation", "linear_interpolation"],
            "event_status": ["matched", "missed_no_peak_within_15d"],
            "success_5d": [True, False],
            "success_10d": [True, False],
            "success_15d": [True, False],
            "absolute_timing_error_days": [4.0, float("nan")],
            "normalized_absolute_magnitude_error": [0.2, float("nan")],
        }
    )
    summary = _event_scenario_summary(events).iloc[0]
    assert summary["event_reference_count"] == 2
    assert summary["event_matched_count"] == 1
    assert summary["event_missed_count"] == 1
    assert summary["event_recovery_fraction_10d"] == 0.5
    assert summary["event_median_absolute_timing_error_matched_days"] == 4.0


def test_controlled_summary_remains_grouped_by_year() -> None:
    rows = []
    for year, nrmse in ((2020, 1.0), (2021, 100.0)):
        rows.append(
            {
                "year": year,
                "method": "linear_interpolation",
                "deletion_fraction": 0.1,
                "reconstruction_status": "ok",
                "nrmse": nrmse,
                "absolute_peak_date_error_days": 5.0,
                "peak_timing_success_10d": True,
                "event_recovery_fraction_10d": 0.5,
                "absolute_integral_error": 1.0,
                "pearson_correlation": 0.9,
                "n_negative_reconstructed_days": 0,
            }
        )
    summary = _summary(
        pd.DataFrame(rows), ["year", "method", "deletion_fraction"]
    )
    assert len(summary) == 2
    assert summary.set_index("year").loc[2020, "median_nrmse"] == 1.0
    assert summary.set_index("year").loc[2021, "median_nrmse"] == 100.0
