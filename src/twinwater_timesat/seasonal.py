"""Annual summaries and exploratory peak characterization for Lake Erken."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .qc import duplicate_date_metrics, yearly_coverage


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


def _scope_summary(
    subset: pd.DataFrame,
    *,
    year: int,
    scope: str,
    record_partial_year: bool,
    ice_free_observation_count: int,
) -> dict[str, object]:
    chlf = subset["CHLF"].to_numpy(dtype=float)
    finite_mask = np.isfinite(chlf)
    finite = subset.loc[finite_mask].copy()
    values = finite["CHLF"]
    result: dict[str, object] = {
        "year": year,
        "scope": scope,
        "record_partial_calendar_year": record_partial_year,
        "first_observed_date": subset["date"].min().date().isoformat() if not subset.empty else None,
        "last_observed_date": subset["date"].max().date().isoformat() if not subset.empty else None,
        "observation_count": len(subset),
        "ice_free_observation_count": ice_free_observation_count,
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
    maxima = finite.loc[values.eq(maximum)].sort_values("date")
    first_max = maxima.iloc[0]
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if len(values) > 1 else np.nan
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
            "coefficient_of_variation": std / mean if np.isfinite(std) and not np.isclose(mean, 0.0) else np.nan,
            "global_max_qualification": (
                "observed-period maximum; partial source calendar year"
                if record_partial_year
                else (
                    "ice-free-scope observed maximum; source record spans complete calendar year"
                    if scope == "ice_free"
                    else "complete-calendar-year observed maximum"
                )
            ),
        }
    )
    return result


def annual_summary(data: pd.DataFrame, years: Iterable[int] | None = None) -> pd.DataFrame:
    """Calculate complete-record and ice-free annual summaries without smoothing."""

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
        ice_free_mask = year_data["ice_free"].fillna(False).astype(bool)
        ice_free = year_data.loc[ice_free_mask]
        for scope, subset in (("complete_record", year_data), ("ice_free", ice_free)):
            row = _scope_summary(
                subset,
                year=year,
                scope=scope,
                record_partial_year=partial,
                ice_free_observation_count=len(ice_free),
            )
            row.update(
                {
                    "calendar_days": int(coverage.loc[year, "calendar_days"]),
                    "unique_observed_dates": int(coverage.loc[year, "unique_observed_dates"]),
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
        {"date": pd.to_datetime(pd.Series(dates), errors="raise"), "value": pd.Series(values, dtype=float)}
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
        for position, prominence in zip(positions, properties["prominences"], strict=True):
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
    """Explore local-peak counts across relative-prominence settings."""

    ensure_unique_dates(data)
    coverage = yearly_coverage(data).set_index("year")
    rows: list[dict[str, object]] = []
    for year in years:
        all_year = data.loc[data["year"].eq(year)].copy()
        if all_year.empty:
            continue
        finite_all = all_year.loc[np.isfinite(all_year["CHLF"].to_numpy(dtype=float))]
        annual_maximum = float(finite_all["CHLF"].max())
        annual_max_rows = finite_all.loc[finite_all["CHLF"].eq(annual_maximum)].sort_values("date")
        annual_max_row = annual_max_rows.iloc[0]

        ice_free_mask = all_year["ice_free"].fillna(False).astype(bool)
        analysis = all_year.loc[ice_free_mask & np.isfinite(all_year["CHLF"].to_numpy(dtype=float))]
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
            rows.append(
                {
                    "year": year,
                    "analysis_scope": "ice_free",
                    "record_partial_calendar_year": bool(
                        coverage.loc[year, "record_partial_calendar_year"]
                    ),
                    "minimum_separation_days": minimum_separation_days,
                    "prominence_fraction_of_within_year_amplitude": fraction,
                    "absolute_prominence_chlf_ug_l": absolute_prominence,
                    "within_year_min_chlf_ug_l": within_min,
                    "within_year_max_chlf_ug_l": within_max,
                    "within_year_amplitude_chlf_ug_l": amplitude,
                    "detected_peak_count": len(peaks),
                    "detected_peak_dates": ";".join(peak.date.date().isoformat() for peak in peaks),
                    "detected_peak_doys": ";".join(str(peak.date.dayofyear) for peak in peaks),
                    "detected_peak_magnitudes_chlf_ug_l": ";".join(f"{peak.value:.10g}" for peak in peaks),
                    "detected_peak_prominences_chlf_ug_l": ";".join(f"{peak.prominence:.10g}" for peak in peaks),
                    "annual_global_max_date_complete_record": annual_max_row["date"].date().isoformat(),
                    "annual_global_max_doy_complete_record": int(annual_max_row["doy"]),
                    "annual_global_max_chlf_ug_l_complete_record": annual_maximum,
                }
            )
    return pd.DataFrame(rows)
