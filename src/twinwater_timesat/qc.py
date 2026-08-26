"""Quality-control summaries for the canonical Lake Erken daily record."""

from __future__ import annotations

import calendar
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a streaming SHA256 digest for a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duplicate_date_metrics(data: pd.DataFrame) -> dict[str, int]:
    """Count duplicated date values without dropping any rows."""

    counts = data["date"].value_counts(dropna=False)
    duplicated = counts[counts > 1]
    return {
        "duplicate_date_count": int(len(duplicated)),
        "duplicate_excess_row_count": int((duplicated - 1).sum()),
    }


def missing_calendar_dates(data: pd.DataFrame) -> pd.DatetimeIndex:
    """Return dates absent between the first and last observed dates, inclusive."""

    if data.empty:
        return pd.DatetimeIndex([])
    observed = pd.DatetimeIndex(data["date"].dropna().unique()).normalize()
    expected = pd.date_range(observed.min(), observed.max(), freq="D")
    return expected.difference(observed)


def yearly_coverage(data: pd.DataFrame) -> pd.DataFrame:
    """Describe full-year and within-observed-span calendar coverage."""

    if data.empty:
        return pd.DataFrame()
    record_start = data["date"].min().normalize()
    record_end = data["date"].max().normalize()
    rows: list[dict[str, object]] = []
    for year in range(record_start.year, record_end.year + 1):
        year_start = pd.Timestamp(year=year, month=1, day=1)
        year_end = pd.Timestamp(year=year, month=12, day=31)
        within_start = max(record_start, year_start)
        within_end = min(record_end, year_end)
        subset = data.loc[data["date"].dt.year.eq(year)]
        observed_dates = pd.DatetimeIndex(subset["date"].dropna().unique()).normalize()
        full_calendar = pd.date_range(year_start, year_end, freq="D")
        record_span = pd.date_range(within_start, within_end, freq="D")
        missing_full = full_calendar.difference(observed_dates)
        missing_span = record_span.difference(observed_dates)
        rows.append(
            {
                "year": year,
                "leap_year": calendar.isleap(year),
                "calendar_days": len(full_calendar),
                "record_partial_calendar_year": bool(
                    within_start != year_start or within_end != year_end
                ),
                "record_span_start": within_start,
                "record_span_end": within_end,
                "record_span_days": len(record_span),
                "observation_rows": len(subset),
                "unique_observed_dates": len(observed_dates),
                "missing_dates_within_record_span": len(missing_span),
                "missing_dates_full_calendar_year": len(missing_full),
            }
        )
    return pd.DataFrame(rows)


def build_qc_summary(
    data: pd.DataFrame,
    *,
    selected_source_path: str,
    copied_raw_path: str | Path,
    source_sha256: str,
    header_line_number: int,
) -> pd.DataFrame:
    """Build a compact long-form QC table for both record- and year-level checks."""

    if data.empty:
        raise ValueError("Cannot summarize an empty Erken dataset.")

    missing_dates = missing_calendar_dates(data)
    duplicates = duplicate_date_metrics(data)
    record_start = data["date"].min()
    record_end = data["date"].max()
    expected_days = len(pd.date_range(record_start, record_end, freq="D"))
    chlf = data["CHLF"].to_numpy(dtype=float)

    records: list[dict[str, object]] = []

    def add(metric: str, value: object, details: str = "") -> None:
        records.append({"metric": metric, "value": value, "details": details})

    add("selected_source_path", selected_source_path)
    add("copied_raw_path", str(copied_raw_path))
    add("copied_raw_filename", Path(copied_raw_path).name)
    add("source_sha256", source_sha256)
    add("detected_header_line_number", header_line_number)
    add("first_observation_date", record_start.date().isoformat())
    add("last_observation_date", record_end.date().isoformat())
    add("total_rows", len(data))
    add("unique_dates", data["date"].nunique())
    add("duplicate_date_count", duplicates["duplicate_date_count"])
    add("duplicate_excess_row_count", duplicates["duplicate_excess_row_count"])
    add("expected_calendar_days_observed_interval", expected_days)
    add("missing_calendar_dates", len(missing_dates), ";".join(missing_dates.strftime("%Y-%m-%d")))
    add("chlf_missing_count", int(data["CHLF"].isna().sum()))
    add("chlf_non_finite_count", int(np.isinf(chlf).sum()), "Infinite values; missing values are counted separately.")
    add("chlf_negative_value_count", int(np.sum(np.isfinite(chlf) & (chlf < 0))))

    ice_counts = data["PRESENCE_ICE"].value_counts(dropna=False).sort_index()
    categories: list[str] = []
    for category, count in ice_counts.items():
        label = "missing" if pd.isna(category) else str(int(category))
        categories.append(label)
        meaning = {"0": "no ice", "1": "ice", "missing": "missing"}.get(label, "undocumented")
        add(f"ice_flag_count_{label}", int(count), meaning)
    add("ice_flag_categories", ";".join(categories))

    for row in yearly_coverage(data).to_dict(orient="records"):
        year = int(row["year"])
        add(f"year_{year}_observation_rows", int(row["observation_rows"]))
        add(f"year_{year}_unique_dates", int(row["unique_observed_dates"]))
        add(
            f"year_{year}_missing_dates_within_record_span",
            int(row["missing_dates_within_record_span"]),
        )
        add(
            f"year_{year}_missing_dates_full_calendar_year",
            int(row["missing_dates_full_calendar_year"]),
        )
        add(f"year_{year}_calendar_days", int(row["calendar_days"]), "leap year" if row["leap_year"] else "common year")
        add(f"year_{year}_partial_calendar_year", bool(row["record_partial_calendar_year"]))

    return pd.DataFrame(records)


def render_qc_report(data: pd.DataFrame, qc_summary: pd.DataFrame) -> str:
    """Render a short Markdown report from computed QC values."""

    values = qc_summary.set_index("metric")["value"].to_dict()
    coverage = yearly_coverage(data)
    coverage_lines = [
        "| Year | Rows | Unique dates | Missing within record span | Missing full year | Leap year | Partial record year |",
        "|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for row in coverage.itertuples(index=False):
        coverage_lines.append(
            f"| {row.year} | {row.observation_rows} | {row.unique_observed_dates} | "
            f"{row.missing_dates_within_record_span} | {row.missing_dates_full_calendar_year} | "
            f"{'yes' if row.leap_year else 'no'} | "
            f"{'yes' if row.record_partial_calendar_year else 'no'} |"
        )

    ice_rows = qc_summary[qc_summary["metric"].str.startswith("ice_flag_count_")]
    ice_text = ", ".join(
        f"{row.metric.removeprefix('ice_flag_count_')}={row.value}"
        for row in ice_rows.itertuples(index=False)
    )
    return "\n".join(
        [
            "# Lake Erken Phase 1 QC report",
            "",
            f"- Source SHA256: `{values['source_sha256']}`",
            f"- Parsed header line: {values['detected_header_line_number']}",
            f"- Observed interval: {values['first_observation_date']} to {values['last_observation_date']}",
            f"- Rows / unique dates: {values['total_rows']} / {values['unique_dates']}",
            f"- Duplicate dates / excess rows: {values['duplicate_date_count']} / {values['duplicate_excess_row_count']}",
            f"- Missing calendar dates within the observed interval: {values['missing_calendar_dates']}",
            f"- CHLF missing / infinite / negative: {values['chlf_missing_count']} / {values['chlf_non_finite_count']} / {values['chlf_negative_value_count']}",
            f"- Ice categories and counts: {ice_text}",
            "",
            "No interpolation, smoothing, duplicate removal, or ice-period removal was performed.",
            "",
            "## Yearly calendar coverage",
            "",
            *coverage_lines,
            "",
            "2019 and 2025 are partial calendar years in the source record; their observed maxima are not guaranteed to be complete ecological annual maxima.",
            "",
        ]
    )
