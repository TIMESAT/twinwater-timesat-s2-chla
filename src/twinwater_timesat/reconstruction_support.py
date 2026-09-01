"""Authoritative sparse inputs, common support, and LOYO fold structure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    EXPECTED_SPARSE_DATES,
    PRIMARY_YEARS,
    OuterFold,
    build_outer_folds,
)


REQUIRED_MASTER_COLUMNS = {
    "date",
    "year",
    "doy",
    "CHLF",
    "open_water",
    "reference_value_available",
    "s2_inventory_date",
    "s2_date_usable",
    "s2_openwater_reference_candidate",
    "qc_rule_id",
    "mask_version",
}


def _coerce_bool(series: pd.Series, *, column: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        if series.isna().any():
            raise ValueError(f"{column} contains missing booleans.")
        return series.astype(bool)
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }
    converted = series.astype("string").str.strip().str.lower().map(mapping)
    if converted.isna().any():
        examples = series.loc[converted.isna()].astype(str).unique()[:5]
        raise ValueError(f"{column} contains invalid booleans: {examples.tolist()}")
    return converted.astype(bool)


def validate_phase3_master(
    data: pd.DataFrame, *, expected_sparse_dates: int = EXPECTED_SPARSE_DATES
) -> pd.DataFrame:
    """Validate the committed Phase 2B-1 master without redefining eligibility."""

    missing = sorted(REQUIRED_MASTER_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(
            "Phase 2B-1 temporal master is missing required columns: "
            + ", ".join(missing)
        )
    if data.empty:
        raise ValueError("Phase 2B-1 temporal master contains no rows.")
    master = data.copy()
    master["date"] = pd.to_datetime(
        master["date"], format="%Y-%m-%d", errors="coerce"
    )
    if master["date"].isna().any():
        raise ValueError("Phase 2B-1 temporal master contains malformed dates.")
    master["date"] = master["date"].dt.normalize()
    if master["date"].duplicated().any():
        dates = master.loc[
            master["date"].duplicated(keep=False), "date"
        ].dt.strftime("%Y-%m-%d")
        raise ValueError(
            "Phase 2B-1 temporal master date keys must be unique; examples: "
            f"{dates.unique()[:5].tolist()}."
        )
    master = master.sort_values("date", kind="mergesort").reset_index(drop=True)

    master["year"] = pd.to_numeric(master["year"], errors="raise").astype(int)
    master["doy"] = pd.to_numeric(master["doy"], errors="raise").astype(int)
    master["CHLF"] = pd.to_numeric(master["CHLF"], errors="coerce").astype(float)
    if not master["year"].eq(master["date"].dt.year).all():
        raise ValueError("Temporal master year values disagree with date.")
    if not master["doy"].eq(master["date"].dt.dayofyear).all():
        raise ValueError("Temporal master doy values disagree with date.")
    years = tuple(sorted(master["year"].unique()))
    if years != PRIMARY_YEARS:
        raise ValueError(
            f"Phase 3 master years must be exactly {PRIMARY_YEARS}; found {years}."
        )

    bool_columns = (
        "open_water",
        "reference_value_available",
        "s2_inventory_date",
        "s2_date_usable",
        "s2_openwater_reference_candidate",
    )
    for column in bool_columns:
        master[column] = _coerce_bool(master[column], column=column)

    finite = master["CHLF"].notna() & np.isfinite(master["CHLF"].to_numpy())
    if not master["reference_value_available"].eq(finite).all():
        raise ValueError(
            "reference_value_available is inconsistent with finite CHLF values."
        )
    audited_formula = (
        master["s2_date_usable"]
        & master["open_water"]
        & master["reference_value_available"]
    )
    if not master["s2_openwater_reference_candidate"].eq(audited_formula).all():
        raise ValueError(
            "Authoritative s2_openwater_reference_candidate is inconsistent with "
            "the frozen Phase 2B-1 definition. It will not be silently regenerated."
        )
    count = int(master["s2_openwater_reference_candidate"].sum())
    if count != expected_sparse_dates:
        raise ValueError(
            f"Frozen Phase 3 sparse-input count must be {expected_sparse_dates}; "
            f"found {count}."
        )
    return master


def read_phase3_master(path: str | Path) -> pd.DataFrame:
    """Read and validate the committed Phase 2B-1 daily master."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Phase 2B-1 temporal master not found: {path}")
    return validate_phase3_master(pd.read_csv(path))


def build_sparse_inputs(master: pd.DataFrame) -> pd.DataFrame:
    """Extract, but never recalculate, the authoritative sparse-input layer."""

    checked = validate_phase3_master(master)
    sparse = checked.loc[
        checked["s2_openwater_reference_candidate"],
        [
            "date",
            "year",
            "doy",
            "CHLF",
            "qc_rule_id",
            "mask_version",
        ],
    ].copy()
    sparse.insert(0, "sparse_input_id", range(1, len(sparse) + 1))
    sparse["sparse_input_source_flag"] = "s2_openwater_reference_candidate"
    return sparse.reset_index(drop=True)


def _segment_ids(dates: pd.Series) -> pd.Series:
    ordered = pd.to_datetime(dates)
    breaks = ordered.diff().dt.days.ne(1)
    if not breaks.empty:
        breaks.iloc[0] = True
    return breaks.cumsum().astype(int)


def build_common_support(master: pd.DataFrame) -> pd.DataFrame:
    """Build method-independent common support and physical segment identifiers."""

    checked = validate_phase3_master(master)
    rows: list[pd.DataFrame] = []
    for year in PRIMARY_YEARS:
        group = checked.loc[checked["year"].eq(year)].copy()
        sparse_dates = group.loc[
            group["s2_openwater_reference_candidate"], "date"
        ].sort_values()
        if sparse_dates.empty:
            raise ValueError(f"Year {year} has no authoritative sparse inputs.")
        first_sparse = sparse_dates.iloc[0]
        last_sparse = sparse_dates.iloc[-1]
        group["first_sparse_input_date"] = first_sparse
        group["last_sparse_input_date"] = last_sparse
        group["inside_frozen_sparse_boundaries"] = group["date"].between(
            first_sparse, last_sparse, inclusive="both"
        )
        group["common_support"] = (
            group["inside_frozen_sparse_boundaries"] & group["open_water"]
        )
        group["common_support_segment_id"] = pd.Series(pd.NA, index=group.index)
        support_index = group.index[group["common_support"]]
        segment = _segment_ids(group.loc[support_index, "date"])
        group.loc[support_index, "common_support_segment_id"] = [
            f"{year}_segment_{value}" for value in segment
        ]
        rows.append(group)
    output = pd.concat(rows, ignore_index=True)
    output["common_support_segment_id"] = output[
        "common_support_segment_id"
    ].astype("string")
    return output


def build_common_support_summary(support: pd.DataFrame) -> pd.DataFrame:
    """Summarize immutable support boundaries and segment counts by year."""

    rows: list[dict[str, Any]] = []
    for year in PRIMARY_YEARS:
        group = support.loc[support["year"].eq(year)]
        eligible = group.loc[group["common_support"]]
        sparse = group.loc[group["s2_openwater_reference_candidate"]]
        rows.append(
            {
                "year": year,
                "first_sparse_input_date": sparse["date"].min(),
                "last_sparse_input_date": sparse["date"].max(),
                "n_sparse_inputs": int(len(sparse)),
                "n_common_support_days": int(len(eligible)),
                "n_common_support_segments": int(
                    eligible["common_support_segment_id"].nunique()
                ),
                "first_common_support_date": eligible["date"].min(),
                "last_common_support_date": eligible["date"].max(),
                "q05_reference": float(eligible["CHLF"].quantile(0.05)),
                "q95_reference": float(eligible["CHLF"].quantile(0.95)),
                "q95_minus_q05": float(
                    eligible["CHLF"].quantile(0.95)
                    - eligible["CHLF"].quantile(0.05)
                ),
            }
        )
    return pd.DataFrame(rows)


def pointwise_evaluation_mask(year_support: pd.DataFrame) -> pd.Series:
    """Return the frozen genuinely-withheld point-wise evaluation mask."""

    required = {
        "common_support",
        "open_water",
        "reference_value_available",
        "s2_openwater_reference_candidate",
    }
    missing = sorted(required - set(year_support.columns))
    if missing:
        raise ValueError(f"Support table lacks columns: {missing}")
    return (
        year_support["common_support"]
        & year_support["open_water"]
        & year_support["reference_value_available"]
        & ~year_support["s2_openwater_reference_candidate"]
    )


def folds_to_table(folds: Iterable[OuterFold] | None = None) -> pd.DataFrame:
    """Serialize the exact seven folds without reference values."""

    selected = tuple(build_outer_folds() if folds is None else folds)
    return pd.DataFrame(
        [
            {
                "fold_id": fold.fold_id,
                "outer_test_year": fold.outer_test_year,
                "inner_training_years": ";".join(
                    str(year) for year in fold.inner_training_years
                ),
                "n_inner_training_years": len(fold.inner_training_years),
            }
            for fold in selected
        ]
    )
