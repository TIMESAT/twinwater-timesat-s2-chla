import pandas as pd

from twinwater_timesat.qc import duplicate_date_metrics, missing_calendar_dates, yearly_coverage


def test_duplicate_date_detection_counts_dates_and_excess_rows() -> None:
    data = pd.DataFrame(
        {"date": pd.to_datetime(["2022-01-01", "2022-01-01", "2022-01-01", "2022-01-03"])}
    )
    assert duplicate_date_metrics(data) == {
        "duplicate_date_count": 1,
        "duplicate_excess_row_count": 2,
    }


def test_missing_calendar_date_detection() -> None:
    data = pd.DataFrame({"date": pd.to_datetime(["2022-01-01", "2022-01-03"])})
    missing = missing_calendar_dates(data)
    assert missing.tolist() == [pd.Timestamp("2022-01-02")]


def test_leap_year_coverage_and_doy() -> None:
    dates = pd.date_range("2020-01-01", "2020-12-31", freq="D")
    data = pd.DataFrame({"date": dates})
    coverage = yearly_coverage(data).iloc[0]
    assert coverage["leap_year"]
    assert coverage["calendar_days"] == 366
    assert coverage["missing_dates_full_calendar_year"] == 0
    assert pd.Timestamp("2020-12-31").dayofyear == 366
