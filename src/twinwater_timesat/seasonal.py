"""Annual summaries and exploratory peak characterization for Lake Erken."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .qc import duplicate_date_metrics, yearly_coverage


COMPLETE_REFERENCE_SCOPE = "complete_reference"
OPEN_WATER_SCOPE = "open_water"


@dataclass(frozen=True)
class DetectedPeak:
    date: pd.Timestamp
    value: float
    prominence: float


def ensure_unique_dates(data: pd.DataFrame) -> None:
    """Fail explicitly when date duplication would make annual analysis ambiguous."""

    metrics = duplicate_date_metrics(data)
    if metrics["duplicate_date_count"]:
        raise ValueError(
            "Annual characterization requires unique daily dates; found "
            f"{metrics['duplicate_date_count']} duplicated date value(s). "
            "The canonical dataset remains unchanged."
        )


def _measurement_regime(year_data: pd.DataFrame) -> str:
    regimes = year_data["measurement_regime"].dropna().unique().tolist()
    if len(regimes) != 1:
        raise ValueError(
            "Expected exactly one measurement_regime per year; found "
            f"{regimes}."
        )
    return str(regimes[0])


def open_water_season_boundary_status(year_data: pd.DataFrame) -> str:
    """Classify calendar truncation using only coverage bounds and boundary ice flags."""

    if year_data.empty:
        return "uncertain"
    ordered = year_data.sort_values("date", kind="stable")
    first = ordered.iloc[0]
    last = ordered.iloc[-1]
    year = int(first["year"])
    year_start = pd.Timestamp(year=year, month=1, day=1)
    year_end = pd.Timestamp(year=year, month=12, day=31)
    statuses: list[str] = []

    if first["date"].normalize() > year_start:
        statuses.append(
            "left_truncated"
            if pd.notna(first["PRESENCE_ICE"]) and int(first["PRESENCE_ICE"]) == 0
            else "left_boundary_uncertain"
        )
    if last["date"].normalize() < year_end:
        statuses.append(
            "right_truncated"
            if pd.notna(last["PRESENCE_ICE"]) and int(last["PRESENCE_ICE"]) == 0
            else "right_boundary_uncertain"
        )
    return ";".join(statuses) if statuses else "not_calendar_truncated"


def _open_water_context(year_data: pd.DataFrame) -> dict[str, object]:
    mask = year_data["open_water"].fillna(False).astype(bool)
    open_water = year_data.loc[mask].sort_values("date", kind="stable")
    if open_water.empty:
        start_date = end_date = None
        start_doy = end_doy = np.nan
        duration = 0
    else:
        start = open_water.iloc[0]
        end = open_water.iloc[-1]
        start_date = start["date"].date().isoformat()
        end_date = end["date"].date().isoformat()
        start_doy = int(start["doy"])
        end_doy = int(end["doy"])
        duration = int((end["date"] - start["date"]).days + 1)
    return {
        "open_water_start_date": start_date,
        "open_water_end_date": end_date,
        "open_water_start_doy": start_doy,
        "open_water_end_doy": end_doy,
        "open_water_duration_days": duration,
        "open_water_day_count": len(open_water),
        "open_water_season_boundary_status": open_water_season_boundary_status(year_data),
    }


def _scope_summary(
    subset: pd.DataFrame,
    *,
    year: int,
    scope: str,
    record_partial_year: bool,
    measurement_regime: str,
    open_water_context: dict[str, object],
) -> dict[str, object]:
    chlf = subset["CHLF"].to_numpy(dtype=float)
    finite_mask = np.isfinite(chlf)
    finite = subset.loc[finite_mask].copy()
    values = finite["CHLF"]
    result: dict[str, object] = {
        "year": year,
        "measurement_regime": measurement_regime,
        "scope": scope,
        "record_partial_calendar_year": record_partial_year,
        **open_water_context,
        "first_observed_date": (
            subset["date"].min().date().isoformat() if not subset.empty else None
        ),
        "last_observed_date": (
            subset["date"].max().date().isoformat() if not subset.empty else None
        ),
        "observation_count": len(subset),
        "finite_chlf_count": len(finite),
        "missing_chlf_count": int(subset["CHLF"].isna().sum()),
    }
    if finite.empty:
        result.update(
            {
                key: np.nan
                for key in [
                    "min_chlf_ug_l",
                    "q25_chlf_ug_l",
                    "median_chlf_ug_l",
                    "mean_chlf_ug_l",
                    "q75_chlf_ug_l",
                    "q95_chlf_ug_l",
                    "max_chlf_ug_l",
                    "global_max_doy",
                    "amplitude_chlf_ug_l",
                    "std_chlf_ug_l",
                    "coefficient_of_variation",
                    "global_max_tie_count",
                ]
            }
        )
        result["global_max_date"] = None
        result["global_max_qualification"] = "no finite observations"
        return result

    maximum = float(values.max())
    maxima = finite.loc[values.eq(maximum)].sort_values("date", kind="stable")
    first_max = maxima.iloc[0]
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if len(values) > 1 else np.nan
    if scope == OPEN_WATER_SCOPE:
        qualification = (
            "observed open-water maximum; "
            f"boundary status={open_water_context['open_water_season_boundary_status']}"
        )
    elif record_partial_year:
        qualification = "observed-period complete-reference maximum; partial calendar year"
    else:
        qualification = "complete-calendar-year complete-reference observed maximum"

    result.update(
        {
            "min_chlf_ug_l": float(values.min()),
            "q25_chlf_ug_l": float(values.quantile(0.25)),
            "median_chlf_ug_l": float(values.median()),
            "mean_chlf_ug_l": mean,
            "q75_chlf_ug_l": float(values.quantile(0.75)),
            "q95_chlf_ug_l": float(values.quantile(0.95)),
            "max_chlf_ug_l": maximum,
            "global_max_date": first_max["date"].date().isoformat(),
            "global_max_doy": int(first_max["doy"]),
            "global_max_tie_count": len(maxima),
            "amplitude_chlf_ug_l": maximum - float(values.min()),
            "std_chlf_ug_l": std,
            "coefficient_of_variation": (
                std / mean
                if np.isfinite(std) and not np.isclose(mean, 0.0)
                else np.nan
            ),
            "global_max_qualification": qualification,
        }
    )
    return result


def annual_summary(
    data: pd.DataFrame, years: Iterable[int] | None = None
) -> pd.DataFrame:
    """Calculate complete-reference and open-water annual summaries."""

    ensure_unique_dates(data)
    if years is None:
        years = sorted(data["year"].unique().tolist())
    coverage = yearly_coverage(data).set_index("year")
    rows: list[dict[str, object]] = []
    for year in years:
        year_data = data.loc[data["year"].eq(year)].copy()
        if year_data.empty:
            continue
        partial = bool(coverage.loc[year, "record_partial_calendar_year"])
        context = _open_water_context(year_data)
        open_water_mask = year_data["open_water"].fillna(False).astype(bool)
        open_water = year_data.loc[open_water_mask]
        for scope, subset in (
            (COMPLETE_REFERENCE_SCOPE, year_data),
            (OPEN_WATER_SCOPE, open_water),
        ):
            row = _scope_summary(
                subset,
                year=year,
                scope=scope,
                record_partial_year=partial,
                measurement_regime=_measurement_regime(year_data),
                open_water_context=context,
            )
            row.update(
                {
                    "calendar_days": int(coverage.loc[year, "calendar_days"]),
                    "unique_observed_dates": int(
                        coverage.loc[year, "unique_observed_dates"]
                    ),
                    "missing_dates_within_record_span": int(
                        coverage.loc[year, "missing_dates_within_record_span"]
                    ),
                    "missing_dates_full_calendar_year": int(
                        coverage.loc[year, "missing_dates_full_calendar_year"]
                    ),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _first_global_max(subset: pd.DataFrame) -> pd.Series | None:
    finite = subset.loc[np.isfinite(subset["CHLF"].to_numpy(dtype=float))]
    if finite.empty:
        return None
    maximum = float(finite["CHLF"].max())
    return (
        finite.loc[finite["CHLF"].eq(maximum)]
        .sort_values("date", kind="stable")
        .iloc[0]
    )


def complete_vs_open_water_peak_summary(
    data: pd.DataFrame, years: Iterable[int] | None = None
) -> pd.DataFrame:
    """Compare complete-reference and open-water observed annual maxima."""

    ensure_unique_dates(data)
    if years is None:
        years = sorted(data["year"].unique().tolist())
    coverage = yearly_coverage(data).set_index("year")
    rows: list[dict[str, object]] = []
    for year in years:
        year_data = data.loc[data["year"].eq(year)].copy()
        if year_data.empty:
            continue
        open_water = year_data.loc[year_data["open_water"].fillna(False).astype(bool)]
        complete_peak = _first_global_max(year_data)
        open_water_peak = _first_global_max(open_water)
        if complete_peak is None:
            raise ValueError(f"Year {year} has no finite complete-reference CHLF values.")

        complete_date = pd.Timestamp(complete_peak["date"])
        complete_value = float(complete_peak["CHLF"])
        complete_ice = (
            int(complete_peak["PRESENCE_ICE"])
            if pd.notna(complete_peak["PRESENCE_ICE"])
            else pd.NA
        )
        if open_water_peak is None:
            open_date = pd.NaT
            open_value = np.nan
            open_doy = np.nan
            date_difference = np.nan
            magnitude_difference = np.nan
            maxima_differ = True
        else:
            open_date = pd.Timestamp(open_water_peak["date"])
            open_value = float(open_water_peak["CHLF"])
            open_doy = int(open_water_peak["doy"])
            date_difference = int((open_date - complete_date).days)
            magnitude_difference = complete_value - open_value
            maxima_differ = bool(
                open_date != complete_date
                or not np.isclose(open_value, complete_value, rtol=0.0, atol=1e-12)
            )
        rows.append(
            {
                "year": year,
                "measurement_regime": _measurement_regime(year_data),
                "record_partial_calendar_year": bool(
                    coverage.loc[year, "record_partial_calendar_year"]
                ),
                "open_water_season_boundary_status": open_water_season_boundary_status(
                    year_data
                ),
                "complete_reference_max_date": complete_date.date().isoformat(),
                "complete_reference_max_doy": int(complete_peak["doy"]),
                "complete_reference_max_chlf_ug_l": complete_value,
                "complete_reference_max_ice_flag": complete_ice,
                "open_water_max_date": (
                    open_date.date().isoformat() if pd.notna(open_date) else None
                ),
                "open_water_max_doy": open_doy,
                "open_water_max_chlf_ug_l": open_value,
                "peak_date_difference_days_open_water_minus_complete": date_difference,
                "peak_magnitude_difference_chlf_ug_l_complete_minus_open_water": magnitude_difference,
                "maxima_differ": maxima_differ,
                "complete_reference_max_occurred_under_ice": complete_ice == 1,
            }
        )
    return pd.DataFrame(rows)


def _contiguous_finite_runs(series: pd.Series) -> list[pd.Series]:
    finite = series[np.isfinite(series.to_numpy(dtype=float))]
    if finite.empty:
        return []
    group = finite.index.to_series().diff().dt.days.ne(1).cumsum()
    return [part for _, part in finite.groupby(group)]


def detect_peaks_calendar_days(
    dates: Sequence[pd.Timestamp] | pd.Series,
    values: Sequence[float] | pd.Series,
    *,
    minimum_separation_days: int,
    absolute_prominence: float,
) -> list[DetectedPeak]:
    """Detect raw-series peaks and enforce separation using calendar days."""

    if minimum_separation_days < 1:
        raise ValueError("minimum_separation_days must be at least 1.")
    if absolute_prominence < 0:
        raise ValueError("absolute_prominence cannot be negative.")

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(pd.Series(dates), errors="raise"),
            "value": pd.Series(values, dtype=float),
        }
    ).sort_values("date", kind="stable")
    if frame["date"].duplicated().any():
        raise ValueError("Peak detection requires unique dates.")
    daily = frame.set_index("date")["value"]

    candidates: list[DetectedPeak] = []
    for run in _contiguous_finite_runs(daily):
        if len(run) < 3:
            continue
        positions, properties = find_peaks(
            run.to_numpy(dtype=float), prominence=absolute_prominence
        )
        for position, prominence in zip(
            positions, properties["prominences"], strict=True
        ):
            candidates.append(
                DetectedPeak(
                    date=pd.Timestamp(run.index[position]),
                    value=float(run.iloc[position]),
                    prominence=float(prominence),
                )
            )

    accepted: list[DetectedPeak] = []
    for candidate in sorted(candidates, key=lambda peak: (-peak.prominence, peak.date)):
        if all(
            abs((candidate.date - chosen.date).days) >= minimum_separation_days
            for chosen in accepted
        ):
            accepted.append(candidate)
    return sorted(accepted, key=lambda peak: peak.date)


def peak_sensitivity_summary(
    data: pd.DataFrame,
    *,
    years: Iterable[int],
    minimum_separation_days: int,
    prominence_fractions: Iterable[float],
) -> pd.DataFrame:
    """Explore open-water local-peak counts across relative-prominence settings."""

    ensure_unique_dates(data)
    coverage = yearly_coverage(data).set_index("year")
    comparison = complete_vs_open_water_peak_summary(data, years).set_index("year")
    rows: list[dict[str, object]] = []
    for year in years:
        all_year = data.loc[data["year"].eq(year)].copy()
        if all_year.empty:
            continue
        open_water_mask = all_year["open_water"].fillna(False).astype(bool)
        analysis = all_year.loc[
            open_water_mask & np.isfinite(all_year["CHLF"].to_numpy(dtype=float))
        ]
        within_min = float(analysis["CHLF"].min())
        within_max = float(analysis["CHLF"].max())
        amplitude = within_max - within_min
        for fraction in prominence_fractions:
            if not 0 < fraction <= 1:
                raise ValueError("Prominence fractions must be in (0, 1].")
            absolute_prominence = fraction * amplitude
            peaks = (
                detect_peaks_calendar_days(
                    analysis["date"],
                    analysis["CHLF"],
                    minimum_separation_days=minimum_separation_days,
                    absolute_prominence=absolute_prominence,
                )
                if amplitude > 0
                else []
            )
            peak_comparison = comparison.loc[year]
            rows.append(
                {
                    "year": year,
                    "measurement_regime": _measurement_regime(all_year),
                    "analysis_scope": OPEN_WATER_SCOPE,
                    "record_partial_calendar_year": bool(
                        coverage.loc[year, "record_partial_calendar_year"]
                    ),
                    "open_water_season_boundary_status": open_water_season_boundary_status(
                        all_year
                    ),
                    "minimum_separation_days": minimum_separation_days,
                    "prominence_fraction_of_within_year_amplitude": fraction,
                    "absolute_prominence_chlf_ug_l": absolute_prominence,
                    "within_year_min_chlf_ug_l": within_min,
                    "within_year_max_chlf_ug_l": within_max,
                    "within_year_amplitude_chlf_ug_l": amplitude,
                    "detected_peak_count": len(peaks),
                    "detected_peak_dates": ";".join(
                        peak.date.date().isoformat() for peak in peaks
                    ),
                    "detected_peak_doys": ";".join(
                        str(peak.date.dayofyear) for peak in peaks
                    ),
                    "detected_peak_magnitudes_chlf_ug_l": ";".join(
                        f"{peak.value:.10g}" for peak in peaks
                    ),
                    "detected_peak_prominences_chlf_ug_l": ";".join(
                        f"{peak.prominence:.10g}" for peak in peaks
                    ),
                    "annual_global_max_date_complete_reference": peak_comparison[
                        "complete_reference_max_date"
                    ],
                    "annual_global_max_doy_complete_reference": peak_comparison[
                        "complete_reference_max_doy"
                    ],
                    "annual_global_max_chlf_ug_l_complete_reference": peak_comparison[
                        "complete_reference_max_chlf_ug_l"
                    ],
                    "annual_global_max_date_open_water": peak_comparison[
                        "open_water_max_date"
                    ],
                    "annual_global_max_doy_open_water": peak_comparison[
                        "open_water_max_doy"
                    ],
                    "annual_global_max_chlf_ug_l_open_water": peak_comparison[
                        "open_water_max_chlf_ug_l"
                    ],
                }
            )
    return pd.DataFrame(rows)


def measurement_regime_summary(
    annual: pd.DataFrame,
    peak_sensitivity: pd.DataFrame,
    *,
    primary_prominence_fraction: float,
) -> pd.DataFrame:
    """Describe annual open-water metrics within broad provenance regimes."""

    open_water = annual.loc[annual["scope"].eq(OPEN_WATER_SCOPE)].copy()
    primary_peaks = peak_sensitivity.loc[
        np.isclose(
            peak_sensitivity["prominence_fraction_of_within_year_amplitude"],
            primary_prominence_fraction,
        )
    ][["year", "detected_peak_count"]]
    open_water = open_water.merge(
        primary_peaks, on="year", how="left", validate="one_to_one"
    )
    metrics = {
        "yearly_median_chlf_ug_l": ("median_chlf_ug_l", "µg L^-1"),
        "yearly_mean_chlf_ug_l": ("mean_chlf_ug_l", "µg L^-1"),
        "yearly_maximum_chlf_ug_l": ("max_chlf_ug_l", "µg L^-1"),
        "yearly_amplitude_chlf_ug_l": ("amplitude_chlf_ug_l", "µg L^-1"),
        "yearly_peak_doy": ("global_max_doy", "day of year"),
        "yearly_exploratory_peak_count_primary": ("detected_peak_count", "count"),
    }
    rows: list[dict[str, object]] = []
    known_regimes = ["pre_2023", "2023_onward"]
    unexpected = set(open_water["measurement_regime"].dropna()).difference(known_regimes)
    if unexpected:
        raise ValueError(f"Unexpected measurement_regime labels: {sorted(unexpected)}")
    for regime in known_regimes:
        group = open_water.loc[open_water["measurement_regime"].eq(regime)]
        if group.empty:
            continue
        years = sorted(group["year"].astype(int).tolist())
        for metric_name, (column, unit) in metrics.items():
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            rows.append(
                {
                    "measurement_regime": regime,
                    "analysis_scope": OPEN_WATER_SCOPE,
                    "annual_metric": metric_name,
                    "unit": unit,
                    "years_represented": ";".join(str(year) for year in years),
                    "year_count": len(years),
                    "partial_calendar_year_count": int(
                        group["record_partial_calendar_year"].sum()
                    ),
                    "annual_value_count": len(values),
                    "minimum": float(values.min()),
                    "q25": float(values.quantile(0.25)),
                    "median": float(values.median()),
                    "mean": float(values.mean()),
                    "q75": float(values.quantile(0.75)),
                    "maximum": float(values.max()),
                    "standard_deviation": (
                        float(values.std(ddof=1)) if len(values) > 1 else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)
