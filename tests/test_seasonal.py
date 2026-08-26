import numpy as np
import pandas as pd

from twinwater_timesat.io import measurement_regime_for_year
from twinwater_timesat.seasonal import (
    annual_summary,
    complete_vs_open_water_peak_summary,
    detect_peaks_calendar_days,
)


def synthetic_daily(
    values: list[float],
    start: str = "2021-01-01",
    ice_flags: list[int] | None = None,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    flags = ice_flags if ice_flags is not None else [0] * len(values)
    return pd.DataFrame(
        {
            "date": dates,
            "year": dates.year,
            "doy": dates.dayofyear,
            "CHLF": values,
            "PRESENCE_ICE": pd.Series(flags, dtype="Int64"),
            "ice_flag": pd.Series(flags, dtype="Int64"),
            "open_water": pd.Series([flag == 0 for flag in flags], dtype="boolean"),
            "measurement_regime": pd.Series(
                [measurement_regime_for_year(year) for year in dates.year],
                dtype="string",
            ),
        }
    )


def test_annual_summary_statistics_on_synthetic_input() -> None:
    data = synthetic_daily([1.0, 2.0, 3.0, 4.0])
    result = annual_summary(data)
    complete = result.loc[result["scope"].eq("complete_reference")].iloc[0]

    assert complete["observation_count"] == 4
    assert complete["min_chlf_ug_l"] == 1.0
    assert complete["median_chlf_ug_l"] == 2.5
    assert complete["mean_chlf_ug_l"] == 2.5
    assert complete["max_chlf_ug_l"] == 4.0
    assert complete["amplitude_chlf_ug_l"] == 3.0
    assert complete["global_max_date"] == "2021-01-04"
    assert np.isclose(complete["std_chlf_ug_l"], np.std([1, 2, 3, 4], ddof=1))


def test_open_water_scope_excludes_ice_and_complete_reference_retains_it() -> None:
    data = synthetic_daily([2.0, 12.0, 5.0], ice_flags=[0, 1, 0])
    result = annual_summary(data)
    complete = result.loc[result["scope"].eq("complete_reference")].iloc[0]
    open_water = result.loc[result["scope"].eq("open_water")].iloc[0]

    assert complete["observation_count"] == 3
    assert complete["max_chlf_ug_l"] == 12.0
    assert open_water["observation_count"] == 2
    assert open_water["open_water_day_count"] == 2
    assert open_water["max_chlf_ug_l"] == 5.0


def test_complete_under_ice_and_open_water_peak_differ_like_2024() -> None:
    data = synthetic_daily(
        [43.3439, 10.0, 8.0, 9.0, 43.0049],
        start="2024-04-03",
        ice_flags=[1, 0, 0, 0, 0],
    )
    comparison = complete_vs_open_water_peak_summary(data).iloc[0]

    assert comparison["complete_reference_max_date"] == "2024-04-03"
    assert comparison["complete_reference_max_ice_flag"] == 1
    assert comparison["complete_reference_max_occurred_under_ice"]
    assert comparison["open_water_max_date"] == "2024-04-07"
    assert np.isclose(comparison["open_water_max_chlf_ug_l"], 43.0049)
    assert comparison["peak_date_difference_days_open_water_minus_complete"] == 4
    assert comparison["maxima_differ"]


def test_partial_calendar_status_is_separate_from_open_water_boundary_status() -> None:
    left_dates = pd.date_range("2019-04-17", "2019-12-31", freq="D")
    left = synthetic_daily([1.0] * len(left_dates), start="2019-04-17")
    left_summary = annual_summary(left).iloc[0]
    assert left_summary["record_partial_calendar_year"]
    assert left_summary["open_water_season_boundary_status"] == "left_truncated"

    right_dates = pd.date_range("2025-01-01", "2025-11-30", freq="D")
    right = synthetic_daily([1.0] * len(right_dates), start="2025-01-01")
    right_summary = annual_summary(right).iloc[0]
    assert right_summary["record_partial_calendar_year"]
    assert right_summary["open_water_season_boundary_status"] == "right_truncated"

    complete_dates = pd.date_range("2020-01-01", "2020-12-31", freq="D")
    complete = synthetic_daily([1.0] * len(complete_dates), start="2020-01-01")
    complete_summary = annual_summary(complete).iloc[0]
    assert not complete_summary["record_partial_calendar_year"]
    assert (
        complete_summary["open_water_season_boundary_status"]
        == "not_calendar_truncated"
    )


def test_complete_vs_open_water_peak_comparison_is_deterministic() -> None:
    data = synthetic_daily([2.0, 8.0, 5.0], ice_flags=[0, 1, 0])
    first = complete_vs_open_water_peak_summary(data)
    second = complete_vs_open_water_peak_summary(data)
    pd.testing.assert_frame_equal(first, second)


def test_peak_detection_is_deterministic_under_fixed_settings() -> None:
    dates = pd.date_range("2021-06-01", periods=12, freq="D")
    values = [0, 1, 4, 1, 0, 0, 1, 5, 1, 0, 3, 0]
    first = detect_peaks_calendar_days(
        dates, values, minimum_separation_days=4, absolute_prominence=2.0
    )
    second = detect_peaks_calendar_days(
        dates, values, minimum_separation_days=4, absolute_prominence=2.0
    )

    assert first == second
    assert [peak.date for peak in first] == [
        pd.Timestamp("2021-06-03"),
        pd.Timestamp("2021-06-08"),
    ]
