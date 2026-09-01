"""Deterministically join Erken daily reference data to the frozen S2 mask.

This module implements Phase 2B-1 data integration and descriptive sampling
audits only.  It does not define an analysis season, year eligibility,
reconstruction input, interpolation, or reconstruction performance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from twinwater_timesat.io import measurement_regime_for_year, read_clean_csv
from twinwater_timesat.seasonal import open_water_season_boundary_status


REFERENCE_START = pd.Timestamp("2019-04-17")
REFERENCE_END = pd.Timestamp("2025-11-30")
FROZEN_QC_RULE_ID = "scl3x3_b1_w8_centernotbad_p0_class2zero_v1"
FROZEN_MASK_VERSION = "erken_s2_observation_mask_v1"

DAILY_REQUIRED_COLUMNS = {
    "date",
    "year",
    "doy",
    "CHLF",
    "PRESENCE_ICE",
    "ice_flag",
    "open_water",
    "measurement_regime",
}

MASK_REQUIRED_COLUMNS = {
    "date",
    "year",
    "n_products_on_date",
    "n_products_passing",
    "s2_date_usable",
    "selected_product_id",
    "selected_platform",
    "selected_acquisition_datetime",
    "selected_processing_baseline",
    "selected_central_scl",
    "selected_water_pixel_count_3x3",
    "selected_bad_pixel_count_3x3",
    "selected_persistent_nonwater_pixel_count_3x3",
    "selected_class2_pixel_count_3x3",
    "selected_water_fraction_3x3",
    "selected_bad_scl_fraction_3x3",
    "qc_rule_id",
    "mask_version",
}

MASTER_COLUMNS = [
    "date",
    "year",
    "doy",
    "CHLF",
    "PRESENCE_ICE",
    "ice_flag",
    "open_water",
    "measurement_regime",
    "reference_value_available",
    "s2_inventory_date",
    "s2_date_usable",
    "n_products_on_date",
    "n_products_passing",
    "selected_product_id",
    "selected_platform",
    "selected_acquisition_datetime",
    "selected_processing_baseline",
    "selected_central_scl",
    "selected_water_pixel_count_3x3",
    "selected_bad_pixel_count_3x3",
    "selected_persistent_nonwater_pixel_count_3x3",
    "selected_class2_pixel_count_3x3",
    "selected_water_fraction_3x3",
    "selected_bad_scl_fraction_3x3",
    "qc_rule_id",
    "mask_version",
    "s2_openwater_reference_candidate",
]

GAP_COLUMNS = [
    "gap_id",
    "year",
    "previous_year",
    "next_year",
    "previous_date",
    "next_date",
    "gap_days",
    "crosses_year_boundary",
    "number_of_calendar_days_between",
    "number_of_daily_reference_days_between",
    "number_of_open_water_days_between",
    "number_of_ice_days_between",
    "number_of_reference_missing_days_between",
    "contains_ice_day",
    "interval_context",
]


def _require_columns(
    data: pd.DataFrame, required: set[str], *, table_name: str
) -> None:
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(
            f"{table_name} is missing required column(s): {', '.join(missing)}"
        )


def _coerce_bool(series: pd.Series, *, column: str) -> pd.Series:
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    normalized = series.astype("string").str.strip().str.lower()
    converted = normalized.map(mapping)
    if converted.isna().any():
        examples = sorted(normalized.loc[converted.isna()].dropna().unique())[:5]
        raise ValueError(
            f"Column {column!r} contains missing or invalid booleans: {examples}"
        )
    return converted.astype(bool)


def _coerce_numeric(
    series: pd.Series,
    *,
    column: str,
    allow_missing: bool,
) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    invalid = series.notna() & converted.isna()
    if invalid.any():
        examples = series.loc[invalid].astype(str).unique()[:5]
        raise ValueError(
            f"Column {column!r} contains non-numeric values: {examples.tolist()}"
        )
    if not allow_missing and converted.isna().any():
        raise ValueError(f"Column {column!r} contains missing values.")
    return converted


def _parse_dates(series: pd.Series, *, table_name: str) -> pd.Series:
    parsed = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        examples = series.loc[parsed.isna()].astype(str).unique()[:5]
        raise ValueError(
            f"{table_name} contains invalid YYYY-MM-DD date values: "
            f"{examples.tolist()}"
        )
    return parsed.dt.normalize()


def validate_daily_reference(
    data: pd.DataFrame,
    *,
    expected_start: str | pd.Timestamp | None = None,
    expected_end: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Validate the canonical daily table without repairing or dropping rows."""

    _require_columns(data, DAILY_REQUIRED_COLUMNS, table_name="Erken daily reference")
    if data.empty:
        raise ValueError("Erken daily reference contains no rows.")
    daily = data.copy()
    daily["date"] = _parse_dates(daily["date"], table_name="Erken daily reference")
    if daily["date"].duplicated().any():
        examples = (
            daily.loc[daily["date"].duplicated(keep=False), "date"]
            .dt.strftime("%Y-%m-%d")
            .unique()[:5]
        )
        raise ValueError(
            "Erken daily reference date keys must be unique; duplicated date(s): "
            f"{examples.tolist()}."
        )

    daily["year"] = _coerce_numeric(
        daily["year"], column="year", allow_missing=False
    )
    daily["doy"] = _coerce_numeric(
        daily["doy"], column="doy", allow_missing=False
    )
    for column in ("year", "doy"):
        if not np.allclose(daily[column], daily[column].round()):
            raise ValueError(f"Daily reference {column} must contain integers.")
        daily[column] = daily[column].astype(int)
    if not daily["year"].eq(daily["date"].dt.year).all():
        raise ValueError("Daily reference year values disagree with date.")
    if not daily["doy"].eq(daily["date"].dt.dayofyear).all():
        raise ValueError("Daily reference doy values disagree with date.")

    daily["CHLF"] = _coerce_numeric(
        daily["CHLF"], column="CHLF", allow_missing=True
    ).astype(float)
    for column in ("PRESENCE_ICE", "ice_flag"):
        daily[column] = _coerce_numeric(
            daily[column], column=column, allow_missing=False
        )
        if not daily[column].isin([0, 1]).all():
            bad = daily.loc[~daily[column].isin([0, 1]), column].unique()[:5]
            raise ValueError(
                f"Daily reference {column} must contain only 0 or 1; found "
                f"{bad.tolist()}."
            )
        daily[column] = daily[column].astype(int)
    if not daily["PRESENCE_ICE"].eq(daily["ice_flag"]).all():
        raise ValueError("PRESENCE_ICE and ice_flag are inconsistent.")

    daily["open_water"] = _coerce_bool(
        daily["open_water"], column="open_water"
    )
    if not daily["open_water"].eq(daily["ice_flag"].eq(0)).all():
        raise ValueError("open_water must equal (ice_flag == 0).")

    daily["measurement_regime"] = daily["measurement_regime"].astype("string")
    expected_regime = daily["year"].map(measurement_regime_for_year).astype("string")
    if not daily["measurement_regime"].eq(expected_regime).all():
        bad = daily.loc[
            ~daily["measurement_regime"].eq(expected_regime),
            ["date", "measurement_regime"],
        ].head()
        raise ValueError(
            "measurement_regime values disagree with the documented year mapping; "
            f"examples: {bad.to_dict(orient='records')}."
        )

    daily = daily.sort_values("date", kind="mergesort").reset_index(drop=True)
    if expected_start is not None:
        start = pd.Timestamp(expected_start).normalize()
        if daily["date"].min() != start:
            raise ValueError(
                f"Daily reference must begin {start.date()}, found "
                f"{daily['date'].min().date()}."
            )
    if expected_end is not None:
        end = pd.Timestamp(expected_end).normalize()
        if daily["date"].max() != end:
            raise ValueError(
                f"Daily reference must end {end.date()}, found "
                f"{daily['date'].max().date()}."
            )
    return daily


def validate_s2_mask(
    data: pd.DataFrame,
    *,
    expected_start: str | pd.Timestamp | None = None,
    expected_end: str | pd.Timestamp | None = None,
    expected_qc_rule_id: str = FROZEN_QC_RULE_ID,
    expected_mask_version: str = FROZEN_MASK_VERSION,
) -> pd.DataFrame:
    """Validate the frozen one-row-per-date S2 mask without changing it."""

    _require_columns(data, MASK_REQUIRED_COLUMNS, table_name="frozen S2 mask")
    if data.empty:
        raise ValueError("Frozen S2 mask contains no rows.")
    mask = data.copy()
    mask["date"] = _parse_dates(mask["date"], table_name="frozen S2 mask")
    if mask["date"].duplicated().any():
        examples = (
            mask.loc[mask["date"].duplicated(keep=False), "date"]
            .dt.strftime("%Y-%m-%d")
            .unique()[:5]
        )
        raise ValueError(
            "Frozen S2 mask date keys must be unique; duplicated date(s): "
            f"{examples.tolist()}."
        )
    mask["year"] = _coerce_numeric(
        mask["year"], column="year", allow_missing=False
    )
    if not np.allclose(mask["year"], mask["year"].round()):
        raise ValueError("Frozen S2 mask year must contain integers.")
    mask["year"] = mask["year"].astype(int)
    if not mask["year"].eq(mask["date"].dt.year).all():
        raise ValueError("Frozen S2 mask year values disagree with date.")

    for column in ("n_products_on_date", "n_products_passing"):
        mask[column] = _coerce_numeric(
            mask[column], column=column, allow_missing=False
        )
        if not np.allclose(mask[column], mask[column].round()):
            raise ValueError(f"Frozen S2 mask {column} must contain integers.")
        mask[column] = mask[column].astype(int)
    if mask["n_products_on_date"].lt(1).any():
        raise ValueError("n_products_on_date must be at least one on every mask row.")
    if mask["n_products_passing"].lt(0).any():
        raise ValueError("n_products_passing must be non-negative.")
    if mask["n_products_passing"].gt(mask["n_products_on_date"]).any():
        raise ValueError("n_products_passing cannot exceed n_products_on_date.")

    mask["s2_date_usable"] = _coerce_bool(
        mask["s2_date_usable"], column="s2_date_usable"
    )
    if not mask["s2_date_usable"].eq(mask["n_products_passing"].gt(0)).all():
        raise ValueError(
            "s2_date_usable must equal (n_products_passing > 0) on every mask row."
        )
    selected_missing = mask["selected_product_id"].isna()
    if (mask["s2_date_usable"] & selected_missing).any():
        raise ValueError("Usable S2 mask dates must have selected_product_id.")
    if (~mask["s2_date_usable"] & ~selected_missing).any():
        raise ValueError("Unusable S2 mask dates must not have selected_product_id.")

    rule_values = mask["qc_rule_id"].dropna().astype(str).unique().tolist()
    version_values = mask["mask_version"].dropna().astype(str).unique().tolist()
    if rule_values != [expected_qc_rule_id]:
        raise ValueError(
            f"Frozen S2 mask qc_rule_id must be {expected_qc_rule_id!r}; "
            f"found {rule_values}."
        )
    if version_values != [expected_mask_version]:
        raise ValueError(
            f"Frozen S2 mask mask_version must be {expected_mask_version!r}; "
            f"found {version_values}."
        )

    mask = mask.sort_values("date", kind="mergesort").reset_index(drop=True)
    if expected_start is not None:
        start = pd.Timestamp(expected_start).normalize()
        if mask["date"].min() != start:
            raise ValueError(
                f"Frozen S2 mask must begin {start.date()}, found "
                f"{mask['date'].min().date()}."
            )
    if expected_end is not None:
        end = pd.Timestamp(expected_end).normalize()
        if mask["date"].max() != end:
            raise ValueError(
                f"Frozen S2 mask must end {end.date()}, found "
                f"{mask['date'].max().date()}."
            )
    return mask


def read_and_validate_temporal_inputs(
    daily_path: str | Path,
    mask_path: str | Path,
    *,
    reference_start: str | pd.Timestamp = REFERENCE_START,
    reference_end: str | pd.Timestamp = REFERENCE_END,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read and validate both committed Phase 2B-1 source tables."""

    daily_path = Path(daily_path)
    mask_path = Path(mask_path)
    if not daily_path.is_file():
        raise FileNotFoundError(f"Canonical Erken daily CSV not found: {daily_path}")
    if not mask_path.is_file():
        raise FileNotFoundError(f"Frozen S2 observation mask not found: {mask_path}")
    daily = read_clean_csv(daily_path)
    mask = pd.read_csv(mask_path)
    return (
        validate_daily_reference(
            daily, expected_start=reference_start, expected_end=reference_end
        ),
        validate_s2_mask(
            mask, expected_start=reference_start, expected_end=reference_end
        ),
    )


def join_daily_reference_and_s2_mask(
    daily: pd.DataFrame, mask: pd.DataFrame
) -> pd.DataFrame:
    """Left-join the unique-date S2 mask onto every daily reference row."""

    daily = validate_daily_reference(daily)
    mask = validate_s2_mask(mask)
    satellite = mask.drop(columns=["year"]).copy()
    satellite["s2_inventory_date"] = True
    joined = daily.merge(
        satellite,
        on="date",
        how="left",
        sort=False,
        validate="one_to_one",
    )
    joined["s2_inventory_date"] = joined["s2_inventory_date"].fillna(False).astype(bool)
    joined["s2_date_usable"] = joined["s2_date_usable"].fillna(False).astype(bool)
    chlf = joined["CHLF"].to_numpy(dtype=float)
    joined["reference_value_available"] = joined["CHLF"].notna() & np.isfinite(chlf)
    joined["s2_openwater_reference_candidate"] = (
        joined["s2_date_usable"]
        & joined["open_water"]
        & joined["reference_value_available"]
    ).astype(bool)
    joined = joined.sort_values("date", kind="mergesort").reset_index(drop=True)
    if len(joined) != len(daily) or joined["date"].duplicated().any():
        raise AssertionError("Deterministic date join changed the daily reference key space.")
    return joined[MASTER_COLUMNS]


def _interval_statistics(dates: pd.Series) -> dict[str, Any]:
    ordered = pd.Series(pd.to_datetime(dates).sort_values().unique())
    gaps = ordered.diff().dt.days.dropna()
    return {
        "n_intervals": int(len(gaps)),
        "median_interval_days": float(gaps.median()) if not gaps.empty else np.nan,
        "q25_interval_days": float(gaps.quantile(0.25)) if not gaps.empty else np.nan,
        "q75_interval_days": float(gaps.quantile(0.75)) if not gaps.empty else np.nan,
        "maximum_interval_days": int(gaps.max()) if not gaps.empty else np.nan,
        "n_intervals_gt_10_days": int(gaps.gt(10).sum()),
        "n_intervals_gt_20_days": int(gaps.gt(20).sum()),
        "n_intervals_gt_30_days": int(gaps.gt(30).sum()),
        "n_intervals_gt_45_days": int(gaps.gt(45).sum()),
    }


def build_candidate_gaps(master: pd.DataFrame) -> pd.DataFrame:
    """Describe every global interval between consecutive preliminary candidates."""

    _require_columns(
        master,
        {
            "date",
            "open_water",
            "ice_flag",
            "reference_value_available",
            "s2_openwater_reference_candidate",
        },
        table_name="temporal sampling master",
    )
    candidates = master.loc[
        master["s2_openwater_reference_candidate"], "date"
    ].sort_values()
    rows: list[dict[str, Any]] = []
    for gap_id, (previous, next_date) in enumerate(
        zip(candidates.iloc[:-1], candidates.iloc[1:], strict=True), start=1
    ):
        between = master.loc[master["date"].gt(previous) & master["date"].lt(next_date)]
        crosses_year = bool(previous.year != next_date.year)
        contains_ice = bool(between["ice_flag"].eq(1).any())
        if crosses_year:
            context = "crosses_year_boundary"
        elif contains_ice:
            context = "contains_ice_day"
        else:
            context = "within_openwater_calendar_span"
        rows.append(
            {
                "gap_id": gap_id,
                "year": int(next_date.year),
                "previous_year": int(previous.year),
                "next_year": int(next_date.year),
                "previous_date": previous,
                "next_date": next_date,
                "gap_days": int((next_date - previous).days),
                "crosses_year_boundary": crosses_year,
                "number_of_calendar_days_between": int(
                    max((next_date - previous).days - 1, 0)
                ),
                "number_of_daily_reference_days_between": int(len(between)),
                "number_of_open_water_days_between": int(
                    between["open_water"].sum()
                ),
                "number_of_ice_days_between": int(between["ice_flag"].eq(1).sum()),
                "number_of_reference_missing_days_between": int(
                    (~between["reference_value_available"]).sum()
                ),
                "contains_ice_day": contains_ice,
                "interval_context": context,
            }
        )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def build_year_summary(master: pd.DataFrame) -> pd.DataFrame:
    """Build descriptive sampling diagnostics separately for each reference year."""

    rows: list[dict[str, Any]] = []
    for year, group in master.groupby("year", sort=True):
        candidates = group.loc[group["s2_openwater_reference_candidate"], "date"]
        usable = group.loc[group["s2_date_usable"], "date"]
        open_water = group.loc[group["open_water"], "date"]
        regimes = group["measurement_regime"].dropna().unique().tolist()
        if len(regimes) != 1:
            raise ValueError(
                f"Expected one measurement regime in {year}; found {regimes}."
            )
        year_start = pd.Timestamp(year=int(year), month=1, day=1)
        year_end = pd.Timestamp(year=int(year), month=12, day=31)
        rows.append(
            {
                "year": int(year),
                "measurement_regime": str(regimes[0]),
                "reference_start_date": group["date"].min(),
                "reference_end_date": group["date"].max(),
                "record_partial_calendar_year": bool(
                    group["date"].min() > year_start or group["date"].max() < year_end
                ),
                "n_daily_reference_days": int(len(group)),
                "n_reference_values_available": int(
                    group["reference_value_available"].sum()
                ),
                "n_open_water_days": int(group["open_water"].sum()),
                "first_open_water_date": (
                    open_water.min() if not open_water.empty else pd.NaT
                ),
                "last_open_water_date": (
                    open_water.max() if not open_water.empty else pd.NaT
                ),
                "n_s2_inventory_dates": int(group["s2_inventory_date"].sum()),
                "n_s2_usable_dates": int(group["s2_date_usable"].sum()),
                "first_s2_usable_date": (
                    usable.min() if not usable.empty else pd.NaT
                ),
                "last_s2_usable_date": (
                    usable.max() if not usable.empty else pd.NaT
                ),
                "n_s2_usable_but_not_openwater": int(
                    (group["s2_date_usable"] & ~group["open_water"]).sum()
                ),
                "n_s2_usable_reference_missing": int(
                    (
                        group["s2_date_usable"]
                        & ~group["reference_value_available"]
                    ).sum()
                ),
                "n_preliminary_sparse_candidates": int(len(candidates)),
                "first_preliminary_sparse_candidate": (
                    candidates.min() if not candidates.empty else pd.NaT
                ),
                "last_preliminary_sparse_candidate": (
                    candidates.max() if not candidates.empty else pd.NaT
                ),
                **_interval_statistics(candidates),
            }
        )
    return pd.DataFrame(rows)


def _linear_slope(values: pd.Series) -> float:
    finite = values.loc[np.isfinite(values.to_numpy(dtype=float))]
    if len(finite) < 2:
        return np.nan
    return float(np.polyfit(np.arange(len(finite)), finite.to_numpy(dtype=float), 1)[0])


def build_boundary_audit(
    master: pd.DataFrame,
    *,
    years: Sequence[int] = (2019, 2025),
    adjacent_days: int = 14,
) -> pd.DataFrame:
    """Quantify partial-year boundary evidence without defining eligibility."""

    rows: list[dict[str, Any]] = []
    for year in years:
        group = master.loc[master["year"].eq(year)].sort_values("date")
        if group.empty:
            raise ValueError(f"Boundary audit year {year} is absent from the master table.")
        year_start = pd.Timestamp(year=year, month=1, day=1)
        year_end = pd.Timestamp(year=year, month=12, day=31)
        left_truncated = bool(group["date"].min() > year_start)
        right_truncated = bool(group["date"].max() < year_end)
        if left_truncated and not right_truncated:
            side = "left"
            boundary = group.iloc[0]
            adjacent = group.head(adjacent_days)
        elif right_truncated and not left_truncated:
            side = "right"
            boundary = group.iloc[-1]
            adjacent = group.tail(adjacent_days)
        elif left_truncated and right_truncated:
            side = "both"
            boundary = group.iloc[0]
            adjacent = group.head(adjacent_days)
        else:
            side = "none"
            boundary = group.iloc[0]
            adjacent = group.head(adjacent_days)

        finite = group.loc[group["reference_value_available"]]
        if finite.empty:
            max_date = pd.NaT
            max_chlf = np.nan
            annual_median = np.nan
            days_max_from_start = np.nan
            days_max_to_end = np.nan
            nearest_side = "unavailable"
            nearest_days = np.nan
        else:
            max_chlf = float(finite["CHLF"].max())
            max_row = finite.loc[finite["CHLF"].eq(max_chlf)].iloc[0]
            max_date = max_row["date"]
            annual_median = float(finite["CHLF"].median())
            days_max_from_start = int((max_date - group["date"].min()).days)
            days_max_to_end = int((group["date"].max() - max_date).days)
            nearest_side = (
                "reference_start"
                if days_max_from_start <= days_max_to_end
                else "reference_end"
            )
            nearest_days = min(days_max_from_start, days_max_to_end)

        open_dates = group.loc[group["open_water"], "date"]
        usable_dates = group.loc[group["s2_date_usable"], "date"]
        candidates = group.loc[group["s2_openwater_reference_candidate"], "date"]
        adjacent_median = float(adjacent["CHLF"].median())
        boundary_chlf = float(boundary["CHLF"])
        above_year = bool(boundary_chlf > annual_median)
        above_adjacent = bool(boundary_chlf > adjacent_median)
        relative_elevated = bool(above_year and above_adjacent)
        if side == "left":
            evidence = (
                "Reference begins after Jan 1 while the boundary is "
                f"{'open water' if boundary['open_water'] else 'not open water'}; "
                f"boundary CHLF is {'above' if above_year else 'not above'} the "
                "observed-year median and "
                f"{'above' if above_adjacent else 'not above'} the first-"
                f"{adjacent_days}-day median. Earlier trajectory is unobserved."
            )
        elif side == "right":
            evidence = (
                "Reference ends before Dec 31 while the boundary is "
                f"{'open water' if boundary['open_water'] else 'not open water'}; "
                f"boundary CHLF is {'above' if above_year else 'not above'} the "
                "observed-year median and "
                f"{'above' if above_adjacent else 'not above'} the last-"
                f"{adjacent_days}-day median. Later trajectory is unobserved."
            )
        else:
            evidence = "No single partial-calendar-year boundary side applies."

        rows.append(
            {
                "year": year,
                "measurement_regime": str(group["measurement_regime"].iloc[0]),
                "reference_start_date": group["date"].min(),
                "reference_end_date": group["date"].max(),
                "calendar_days_missing_before_reference": int(
                    (group["date"].min() - year_start).days
                ),
                "calendar_days_missing_after_reference": int(
                    (year_end - group["date"].max()).days
                ),
                "partial_year_boundary_side": side,
                "open_water_season_boundary_status": open_water_season_boundary_status(
                    group
                ),
                "first_open_water_date": (
                    open_dates.min() if not open_dates.empty else pd.NaT
                ),
                "last_open_water_date": (
                    open_dates.max() if not open_dates.empty else pd.NaT
                ),
                "first_s2_usable_date": (
                    usable_dates.min() if not usable_dates.empty else pd.NaT
                ),
                "last_s2_usable_date": (
                    usable_dates.max() if not usable_dates.empty else pd.NaT
                ),
                "first_preliminary_sparse_candidate": (
                    candidates.min() if not candidates.empty else pd.NaT
                ),
                "last_preliminary_sparse_candidate": (
                    candidates.max() if not candidates.empty else pd.NaT
                ),
                "n_preliminary_sparse_candidates": int(len(candidates)),
                "days_from_reference_start_to_first_candidate": (
                    int((candidates.min() - group["date"].min()).days)
                    if not candidates.empty
                    else np.nan
                ),
                "days_from_last_candidate_to_reference_end": (
                    int((group["date"].max() - candidates.max()).days)
                    if not candidates.empty
                    else np.nan
                ),
                "reference_start_chlf": float(group.iloc[0]["CHLF"]),
                "reference_end_chlf": float(group.iloc[-1]["CHLF"]),
                "audited_boundary_date": boundary["date"],
                "audited_boundary_chlf": boundary_chlf,
                "audited_boundary_open_water": bool(boundary["open_water"]),
                "observed_year_chlf_median": annual_median,
                "adjacent_window_days": adjacent_days,
                "adjacent_boundary_chlf_median": adjacent_median,
                "boundary_chlf_above_observed_year_median": above_year,
                "boundary_chlf_above_adjacent_window_median": above_adjacent,
                "boundary_chlf_elevated_relative_to_observed_context": relative_elevated,
                "adjacent_boundary_chlf_slope_per_day": _linear_slope(
                    adjacent["CHLF"]
                ),
                "observed_annual_max_chlf": max_chlf,
                "observed_annual_max_date": max_date,
                "annual_max_days_from_reference_start": days_max_from_start,
                "annual_max_days_to_reference_end": days_max_to_end,
                "annual_max_nearest_reference_boundary": nearest_side,
                "annual_max_nearest_boundary_distance_days": nearest_days,
                "annual_max_boundary_assessment": (
                    f"Observed annual maximum is {nearest_days} day(s) from "
                    f"{nearest_side}; no near-boundary cutoff is applied."
                ),
                "boundary_trajectory_evidence": evidence,
                "requires_later_year_eligibility_decision": True,
            }
        )
    return pd.DataFrame(rows)


def _add_metric(
    rows: list[dict[str, Any]],
    section: str,
    metric: str,
    value: Any,
    detail: str = "",
) -> None:
    rows.append(
        {"section": section, "metric": metric, "value": value, "detail": detail}
    )


def build_join_qc(
    daily: pd.DataFrame,
    mask: pd.DataFrame,
    master: pd.DataFrame,
    gaps: pd.DataFrame,
) -> pd.DataFrame:
    """Build input, join, interval, and reconciliation audit metrics."""

    rows: list[dict[str, Any]] = []
    expected_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    missing_dates = expected_dates.difference(pd.DatetimeIndex(daily["date"]))
    chlf = daily["CHLF"].to_numpy(dtype=float)
    regime_transitions = daily.loc[
        daily["measurement_regime"].ne(daily["measurement_regime"].shift()),
        ["date", "measurement_regime"],
    ]
    transition_text = ";".join(
        f"{row.date.date()}={row.measurement_regime}"
        for row in regime_transitions.itertuples(index=False)
    )

    _add_metric(rows, "daily_reference", "total_rows", len(daily))
    _add_metric(rows, "daily_reference", "unique_dates", daily["date"].nunique())
    _add_metric(rows, "daily_reference", "date_min", daily["date"].min())
    _add_metric(rows, "daily_reference", "date_max", daily["date"].max())
    _add_metric(rows, "daily_reference", "duplicate_dates", int(daily["date"].duplicated().sum()))
    _add_metric(
        rows,
        "daily_reference",
        "missing_calendar_dates",
        len(missing_dates),
        ";".join(missing_dates.strftime("%Y-%m-%d")),
    )
    _add_metric(rows, "daily_reference", "missing_chlf_values", int(daily["CHLF"].isna().sum()))
    _add_metric(
        rows,
        "daily_reference",
        "nonfinite_nonmissing_chlf_values",
        int((daily["CHLF"].notna() & ~np.isfinite(chlf)).sum()),
    )
    _add_metric(rows, "daily_reference", "negative_chlf_values", int((daily["CHLF"] < 0).sum()))
    _add_metric(
        rows,
        "daily_reference",
        "presence_ice_ice_flag_inconsistencies",
        int((~daily["PRESENCE_ICE"].eq(daily["ice_flag"])).sum()),
    )
    _add_metric(
        rows,
        "daily_reference",
        "open_water_inconsistencies",
        int((~daily["open_water"].eq(daily["ice_flag"].eq(0))).sum()),
    )
    for regime, count in daily["measurement_regime"].value_counts().sort_index().items():
        _add_metric(rows, "measurement_regime", str(regime), int(count))
    _add_metric(rows, "measurement_regime", "transitions", len(regime_transitions), transition_text)

    _add_metric(rows, "frozen_s2_mask", "total_rows", len(mask))
    _add_metric(rows, "frozen_s2_mask", "unique_dates", mask["date"].nunique())
    _add_metric(rows, "frozen_s2_mask", "date_min", mask["date"].min())
    _add_metric(rows, "frozen_s2_mask", "date_max", mask["date"].max())
    _add_metric(rows, "frozen_s2_mask", "duplicate_dates", int(mask["date"].duplicated().sum()))
    _add_metric(rows, "frozen_s2_mask", "s2_date_usable", int(mask["s2_date_usable"].sum()))
    _add_metric(rows, "frozen_s2_mask", "unique_usable_dates", mask.loc[mask["s2_date_usable"], "date"].nunique())
    _add_metric(rows, "frozen_s2_mask", "mask_version", ";".join(mask["mask_version"].unique()))
    _add_metric(rows, "frozen_s2_mask", "qc_rule_id", ";".join(mask["qc_rule_id"].unique()))
    _add_metric(rows, "frozen_s2_mask", "sum_n_products_on_date", int(mask["n_products_on_date"].sum()))
    _add_metric(rows, "frozen_s2_mask", "sum_n_products_passing", int(mask["n_products_passing"].sum()))
    _add_metric(
        rows,
        "frozen_s2_mask",
        "usable_dates_missing_selected_product_id",
        int(mask.loc[mask["s2_date_usable"], "selected_product_id"].isna().sum()),
    )
    _add_metric(
        rows,
        "frozen_s2_mask",
        "unusable_dates_with_selected_product_id",
        int(mask.loc[~mask["s2_date_usable"], "selected_product_id"].notna().sum()),
    )

    matched_mask = mask["date"].isin(daily["date"])
    usable_mask = mask["s2_date_usable"]
    usable_without_daily = int((usable_mask & ~matched_mask).sum())
    usable_master = master["s2_date_usable"]
    reference_missing = usable_master & ~master["reference_value_available"]
    not_openwater_exclusive = (
        usable_master
        & master["reference_value_available"]
        & ~master["open_water"]
    )
    candidates = master["s2_openwater_reference_candidate"]
    left = int(usable_mask.sum())
    right = int(
        usable_without_daily
        + reference_missing.sum()
        + not_openwater_exclusive.sum()
        + candidates.sum()
    )
    if left != right:
        raise AssertionError(
            "S2-usable reconciliation identity failed: "
            f"left={left}, classified total={right}."
        )

    _add_metric(rows, "date_join", "mask_dates_matching_daily_reference", int(matched_mask.sum()))
    _add_metric(rows, "date_join", "mask_dates_without_daily_reference_row", int((~matched_mask).sum()))
    _add_metric(rows, "date_join", "s2_usable_dates_matching_daily_reference", int((usable_mask & matched_mask).sum()))
    _add_metric(rows, "date_join", "s2_usable_dates_without_daily_reference_row", usable_without_daily)
    _add_metric(rows, "date_join", "s2_usable_dates_with_reference_missing", int(reference_missing.sum()))
    _add_metric(
        rows,
        "date_join",
        "s2_usable_dates_not_openwater",
        int((usable_master & ~master["open_water"]).sum()),
    )
    _add_metric(rows, "date_join", "preliminary_sparse_candidates", int(candidates.sum()))
    _add_metric(rows, "reconciliation", "n_s2_usable_lhs", left)
    _add_metric(
        rows,
        "reconciliation",
        "n_preliminary_candidates",
        int(candidates.sum()),
        "Mutually exclusive category 1: matched daily row, finite CHLF, open water.",
    )
    _add_metric(
        rows,
        "reconciliation",
        "n_s2_usable_but_not_openwater",
        int(not_openwater_exclusive.sum()),
        "Mutually exclusive category 2: matched finite CHLF, not open water.",
    )
    _add_metric(
        rows,
        "reconciliation",
        "n_s2_usable_but_reference_missing",
        int(reference_missing.sum()),
        "Mutually exclusive category 3: matched row, missing/non-finite CHLF.",
    )
    _add_metric(
        rows,
        "reconciliation",
        "n_s2_usable_without_daily_row",
        usable_without_daily,
        "Mutually exclusive category 4: date absent from daily reference.",
    )
    _add_metric(rows, "reconciliation", "classified_total_rhs", right)
    _add_metric(rows, "reconciliation", "identity_difference", left - right)
    _add_metric(rows, "reconciliation", "identity_passed", left == right)

    for label, flag in (
        ("s2_usable", master["s2_date_usable"]),
        ("preliminary_candidate", master["s2_openwater_reference_candidate"]),
    ):
        stats = _interval_statistics(master.loc[flag, "date"])
        for metric, value in stats.items():
            _add_metric(rows, f"{label}_calendar_intervals", metric, value)
    _add_metric(rows, "preliminary_candidate_intervals", "n_cross_year_intervals", int(gaps["crosses_year_boundary"].sum()))
    _add_metric(rows, "preliminary_candidate_intervals", "n_intervals_containing_ice", int(gaps["contains_ice_day"].sum()))
    return pd.DataFrame(rows)


def build_temporal_sampling_analysis(
    daily: pd.DataFrame, mask: pd.DataFrame
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Build the joined master table and all Phase 2B-1 audit tables."""

    master = join_daily_reference_and_s2_mask(daily, mask)
    gaps = build_candidate_gaps(master)
    tables = {
        "erken_temporal_sampling_join_qc.csv": build_join_qc(
            daily, mask, master, gaps
        ),
        "erken_temporal_sampling_year_summary.csv": build_year_summary(master),
        "erken_temporal_sampling_gaps.csv": gaps,
        "erken_reference_boundary_audit.csv": build_boundary_audit(master),
    }
    return tables, master


def _format_dates_for_csv(table: pd.DataFrame) -> pd.DataFrame:
    output = table.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.strftime("%Y-%m-%d").where(
                output[column].notna(), ""
            )
    return output


def write_csv_table(table: pd.DataFrame, path: str | Path) -> Path:
    """Write one deterministic portable CSV."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _format_dates_for_csv(table).to_csv(
        path,
        index=False,
        float_format="%.10g",
        lineterminator="\n",
    )
    return path


def write_temporal_sampling_outputs(
    tables: Mapping[str, pd.DataFrame],
    master: pd.DataFrame,
    *,
    tables_directory: str | Path,
    master_path: str | Path,
) -> list[Path]:
    """Write all Phase 2B-1 CSV outputs."""

    tables_directory = Path(tables_directory)
    outputs = [
        write_csv_table(table, tables_directory / filename)
        for filename, table in tables.items()
    ]
    outputs.append(write_csv_table(master, master_path))
    return outputs


def _plot_style() -> dict[str, Any]:
    return {
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "grid.linewidth": 0.5,
        "savefig.bbox": "tight",
    }


def _save_figure(
    figure: plt.Figure, output_directory: Path, stem: str
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    png = output_directory / f"{stem}.png"
    pdf = output_directory / f"{stem}.pdf"
    figure.savefig(png, dpi=300, facecolor="white")
    figure.savefig(
        pdf,
        facecolor="white",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)
    return [png, pdf]


def generate_temporal_sampling_figures(
    master: pd.DataFrame,
    year_summary: pd.DataFrame,
    output_directory: str | Path,
) -> list[Path]:
    """Generate four descriptive Phase 2B-1 sampling/boundary figures."""

    output_directory = Path(output_directory)
    colors = plt.get_cmap("tab10").colors
    outputs: list[Path] = []

    with plt.rc_context(_plot_style()):
        plot = master.copy()
        plot["plot_doy"] = plot["date"].dt.dayofyear
        fig, ax = plt.subplots(figsize=(10.2, 5.2), constrained_layout=True)
        ax.scatter(
            plot["plot_doy"],
            plot["year"],
            s=4,
            color="#d1d5db",
            linewidths=0,
            label="Daily reference",
        )
        open_water = plot.loc[plot["open_water"]]
        ax.scatter(
            open_water["plot_doy"],
            open_water["year"],
            s=6,
            color="#a7d8c9",
            linewidths=0,
            label="Open water",
        )
        usable = plot.loc[plot["s2_date_usable"]]
        ax.vlines(
            usable["plot_doy"],
            usable["year"] - 0.18,
            usable["year"] + 0.18,
            color="#374151",
            linewidth=0.7,
        )
        candidate = plot.loc[plot["s2_openwater_reference_candidate"]]
        ax.scatter(
            candidate["plot_doy"],
            candidate["year"],
            s=12,
            color=colors[0],
            linewidths=0,
            label="Preliminary candidate",
        )
        month_starts = pd.date_range("2024-01-01", "2024-12-01", freq="MS")
        ax.set_xticks(
            month_starts.dayofyear,
            [date.strftime("%b") for date in month_starts],
        )
        ax.set(
            title="Erken daily reference and frozen Sentinel-2 sampling layers",
            xlabel="Calendar month",
            ylabel="Year",
            yticks=sorted(plot["year"].unique()),
            xlim=(1, 366),
        )
        handles, labels = ax.get_legend_handles_labels()
        handles.insert(
            2,
            Line2D([0], [0], color="#374151", linewidth=1.5),
        )
        labels.insert(2, "Frozen S2-usable date")
        ax.legend(
            handles,
            labels,
            frameon=False,
            ncol=2,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
        )
        outputs.extend(
            _save_figure(
                fig,
                output_directory,
                "figure_16_erken_temporal_sampling_calendar",
            )
        )

    with plt.rc_context(_plot_style()):
        fig, ax = plt.subplots(figsize=(8.2, 4.6), constrained_layout=True)
        bars = ax.bar(
            year_summary["year"].astype(str),
            year_summary["n_preliminary_sparse_candidates"],
            color=colors[0],
            width=0.72,
        )
        ax.bar_label(bars, padding=3, fontsize=8)
        ax.set(
            title="Preliminary open-water/reference Sentinel-2 candidates by year",
            xlabel="Reference year",
            ylabel="Unique preliminary candidate dates",
        )
        ax.text(
            0.01,
            0.98,
            "Descriptive only; analysis-season and year eligibility remain unfrozen",
            transform=ax.transAxes,
            va="top",
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig,
                output_directory,
                "figure_17_erken_temporal_candidate_counts_by_year",
            )
        )

    with plt.rc_context(_plot_style()):
        years = sorted(master["year"].unique())
        gap_values = []
        for year in years:
            dates = master.loc[
                master["year"].eq(year)
                & master["s2_openwater_reference_candidate"],
                "date",
            ].sort_values()
            gap_values.append(dates.diff().dt.days.dropna().to_numpy())
        fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
        box = ax.boxplot(
            gap_values,
            labels=[str(year) for year in years],
            patch_artist=True,
            showfliers=True,
            medianprops={"color": "#111827", "linewidth": 1.4},
        )
        for patch in box["boxes"]:
            patch.set_facecolor(colors[0])
            patch.set_alpha(0.55)
        ax.set(
            title="Within-year intervals between preliminary candidate dates",
            xlabel="Reference year",
            ylabel="Calendar interval (days)",
        )
        ax.text(
            0.01,
            0.98,
            "Cross-year/winter intervals are reported separately in the gap table",
            transform=ax.transAxes,
            va="top",
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig,
                output_directory,
                "figure_18_erken_temporal_candidate_interval_distribution",
            )
        )

    with plt.rc_context(_plot_style()):
        fig, axes = plt.subplots(
            2, 1, figsize=(10.0, 7.2), constrained_layout=True
        )
        for ax, year in zip(axes, (2019, 2025), strict=True):
            group = master.loc[master["year"].eq(year)]
            candidate = group.loc[group["s2_openwater_reference_candidate"]]
            ax.plot(
                group["date"],
                group["CHLF"],
                color="#4b5563",
                linewidth=0.9,
                label="Daily Erken CHLF",
            )
            ax.scatter(
                candidate["date"],
                candidate["CHLF"],
                color=colors[0],
                s=20,
                zorder=3,
                label="Preliminary candidate date",
            )
            ax.set(
                title=f"{year} partial reference-year boundary audit",
                ylabel="CHLF (µg L⁻¹)",
            )
            ax.text(
                0.99,
                0.96,
                (
                    "Reference begins 17 Apr; left eligibility unresolved"
                    if year == 2019
                    else "Reference ends 30 Nov; right eligibility unresolved"
                ),
                transform=ax.transAxes,
                ha="right",
                va="top",
                color="#4b5563",
                fontsize=8,
            )
        axes[-1].set_xlabel("Calendar date")
        axes[0].legend(frameon=False, ncol=2, loc="upper center")
        fig.suptitle(
            "Boundary evidence only: frozen S2 QC was not altered using CHLF",
            fontsize=11,
        )
        outputs.extend(
            _save_figure(
                fig,
                output_directory,
                "figure_19_erken_reference_boundary_chlf_audit",
            )
        )
    return outputs
