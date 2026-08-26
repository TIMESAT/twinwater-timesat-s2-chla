"""Robust, non-destructive ingestion for the SITES Lake Erken daily CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_SOURCE_COLUMNS = ("TIMESTAMP", "CHLF", "PRESENCE_ICE")
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none"}


class ErkenIngestionError(ValueError):
    """Raised when a source file cannot be parsed without ambiguity."""


@dataclass(frozen=True)
class ErkenIngestionResult:
    """Parsed daily data plus auditable header-discovery information."""

    data: pd.DataFrame
    header_line_number: int
    metadata_lines: tuple[str, ...]


def measurement_regime_for_year(year: int) -> str:
    """Assign the broad, non-causal source-provenance regime."""

    return "pre_2023" if int(year) <= 2022 else "2023_onward"


def _parse_csv_fields(line: str) -> list[str]:
    return [field.strip().lstrip("\ufeff") for field in next(csv.reader([line]))]


def find_tabular_header(
    lines: Iterable[str], required_columns: tuple[str, ...] = REQUIRED_SOURCE_COLUMNS
) -> int:
    """Return the zero-based unique header line containing all required columns."""

    line_list = list(lines)
    matches: list[int] = []
    required = set(required_columns)
    for index, line in enumerate(line_list):
        try:
            fields = _parse_csv_fields(line)
        except csv.Error:
            continue
        if required.issubset(fields):
            if len(fields) != len(set(fields)):
                raise ErkenIngestionError(
                    f"Duplicate column names in candidate header at line {index + 1}."
                )
            matches.append(index)

    if len(matches) != 1:
        raise ErkenIngestionError(
            "Expected exactly one tabular header containing "
            f"{required_columns}; found {len(matches)} candidate(s) at "
            f"lines {[index + 1 for index in matches]}."
        )
    return matches[0]


def _parse_chlf(values: pd.Series) -> pd.Series:
    stripped = values.astype("string").str.strip()
    missing = stripped.str.lower().isin(MISSING_TOKENS)
    numeric = pd.to_numeric(stripped.mask(missing), errors="coerce")
    invalid = numeric.isna() & ~missing
    if invalid.any():
        examples = sorted(stripped[invalid].dropna().unique().tolist())[:5]
        raise ErkenIngestionError(
            f"CHLF contains non-numeric, non-missing values: {examples}."
        )
    return numeric.astype("float64")


def _parse_ice(values: pd.Series) -> pd.Series:
    stripped = values.astype("string").str.strip()
    missing = stripped.str.lower().isin(MISSING_TOKENS)
    numeric = pd.to_numeric(stripped.mask(missing), errors="coerce")
    invalid_numeric = numeric.isna() & ~missing
    invalid_category = numeric.notna() & ~numeric.isin([0, 1])
    invalid_integer = numeric.notna() & (numeric % 1 != 0)
    invalid = invalid_numeric | invalid_category | invalid_integer
    if invalid.any():
        examples = sorted(stripped[invalid].dropna().unique().tolist())[:5]
        raise ErkenIngestionError(
            "PRESENCE_ICE cannot be interpreted using documented binary "
            f"semantics (0=no ice, 1=ice); invalid values: {examples}."
        )
    return numeric.astype("Int64")


def read_erken_csv(path: str | Path) -> ErkenIngestionResult:
    """Read the metadata-prefixed SITES CSV without interpolation or row removal."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Erken source CSV not found: {source}")

    text = source.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    header_index = find_tabular_header(lines)
    table_text = "\n".join(lines[header_index:])
    raw = pd.read_csv(
        StringIO(table_text),
        dtype="string",
        keep_default_na=False,
    )
    raw.columns = [str(column).strip() for column in raw.columns]

    missing_columns = set(REQUIRED_SOURCE_COLUMNS).difference(raw.columns)
    if missing_columns:
        raise ErkenIngestionError(
            f"Required columns disappeared during parsing: {sorted(missing_columns)}."
        )

    timestamp_text = raw["TIMESTAMP"].astype("string").str.strip()
    dates = pd.to_datetime(timestamp_text, format="%Y-%m-%d", errors="coerce")
    invalid_dates = dates.isna()
    if invalid_dates.any():
        examples = sorted(timestamp_text[invalid_dates].dropna().unique().tolist())[:5]
        raise ErkenIngestionError(
            f"TIMESTAMP values must use YYYY-MM-DD; invalid values: {examples}."
        )

    clean = pd.DataFrame(
        {
            "date": dates,
            "CHLF": _parse_chlf(raw["CHLF"]),
            "PRESENCE_ICE": _parse_ice(raw["PRESENCE_ICE"]),
        }
    )
    clean["year"] = clean["date"].dt.year.astype("int64")
    clean["doy"] = clean["date"].dt.dayofyear.astype("int64")
    clean["ice_flag"] = clean["PRESENCE_ICE"].astype("Int64")
    clean["open_water"] = clean["ice_flag"].eq(0).astype("boolean")
    clean["measurement_regime"] = clean["year"].map(measurement_regime_for_year).astype("string")
    clean = clean[
        [
            "date",
            "year",
            "doy",
            "CHLF",
            "PRESENCE_ICE",
            "ice_flag",
            "open_water",
            "measurement_regime",
        ]
    ].sort_values("date", kind="stable", ignore_index=True)

    if len(clean) != len(raw):
        raise ErkenIngestionError(
            "Internal row-count mismatch; ingestion would have lost or added rows."
        )

    return ErkenIngestionResult(
        data=clean,
        header_line_number=header_index + 1,
        metadata_lines=tuple(lines[:header_index]),
    )


def write_clean_csv(data: pd.DataFrame, path: str | Path) -> None:
    """Write canonical parsed values with no interpolation, smoothing, or filtering."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(destination, index=False, date_format="%Y-%m-%d", float_format="%.15g")


def read_clean_csv(path: str | Path) -> pd.DataFrame:
    """Read the canonical processed CSV with explicit dates and nullable ice fields."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(
            f"Clean Erken CSV not found: {source}. Run scripts/01_erken_qc.py first."
        )
    data = pd.read_csv(
        source,
        dtype={
            "PRESENCE_ICE": "Int64",
            "ice_flag": "Int64",
            "open_water": "boolean",
            "measurement_regime": "string",
        },
    )
    data["date"] = pd.to_datetime(data["date"], format="%Y-%m-%d", errors="raise")
    return data.sort_values("date", kind="stable", ignore_index=True)


def finite_chlf_mask(data: pd.DataFrame) -> pd.Series:
    """Identify finite, non-missing CHLF values without changing them."""

    return data["CHLF"].notna() & np.isfinite(data["CHLF"].to_numpy(dtype=float))
