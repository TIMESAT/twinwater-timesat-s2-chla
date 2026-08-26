import numpy as np
import pandas as pd

from twinwater_timesat.seasonal import (
    annual_summary,
    detect_peaks_calendar_days,
)


def synthetic_daily(values: list[float], start: str = "2021-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "year": dates.year,
            "doy": dates.dayofyear,
            "CHLF": values,
            "PRESENCE_ICE": pd.Series([0] * len(values), dtype="Int64"),
            "ice_flag": pd.Series([0] * len(values), dtype="Int64"),
            "ice_free": pd.Series([True] * len(values), dtype="boolean"),
        }
    )


def test_annual_summary_statistics_on_synthetic_input() -> None:
    data = synthetic_daily([1.0, 2.0, 3.0, 4.0])
    result = annual_summary(data)
    complete = result.loc[result["scope"].eq("complete_record")].iloc[0]

    assert complete["observation_count"] == 4
    assert complete["min_chlf_ug_l"] == 1.0
    assert complete["median_chlf_ug_l"] == 2.5
    assert complete["mean_chlf_ug_l"] == 2.5
    assert complete["max_chlf_ug_l"] == 4.0
    assert complete["amplitude_chlf_ug_l"] == 3.0
    assert complete["global_max_date"] == "2021-01-04"
    assert np.isclose(complete["std_chlf_ug_l"], np.std([1, 2, 3, 4], ddof=1))


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
    assert [peak.date for peak in first] == [pd.Timestamp("2021-06-03"), pd.Timestamp("2021-06-08")]
