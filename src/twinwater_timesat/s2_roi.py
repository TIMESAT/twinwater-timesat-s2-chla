"""Scientific diagnostics for selecting an Erken SCL spatial window.

This module analyses the portable Phase 2A product inventory and long-format
scene/window table.  It deliberately does not construct a usable-acquisition
mask or select water/bad-SCL thresholds.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


WINDOW_SIZES = (1, 3, 5, 7, 11)
BAD_SCL_CLASSES = (0, 1, 3, 8, 9, 10, 11)
PERSISTENT_NONWATER_CLASSES = (4, 5, 7)
WATER_THRESHOLDS = (0.50, 0.75, 0.90, 0.95)
SCL_CLASS_LABELS = {
    0: "No data",
    1: "Saturated/defective",
    2: "Dark area / topo shadow",
    3: "Cloud shadow",
    4: "Vegetation",
    5: "Not vegetated",
    6: "Water",
    7: "Unclassified",
    8: "Cloud, medium probability",
    9: "Cloud, high probability",
    10: "Thin cirrus",
    11: "Snow/ice",
}

INVENTORY_REQUIRED_COLUMNS = {
    "product_id",
    "platform",
    "acquisition_datetime",
    "acquisition_date",
    "tile_id",
    "processing_baseline",
    "scl_candidate_count",
    "scl_found",
    "processing_status",
}

SCENE_REQUIRED_COLUMNS = {
    "product_id",
    "platform",
    "acquisition_datetime",
    "acquisition_date",
    "tile_id",
    "processing_baseline",
    "scl_crs",
    "raster_transform_a",
    "raster_transform_b",
    "raster_transform_c",
    "raster_transform_d",
    "raster_transform_e",
    "raster_transform_f",
    "pixel_size_x",
    "pixel_size_y",
    "raster_width",
    "raster_height",
    "station_lat",
    "station_lon",
    "station_crs",
    "station_x",
    "station_y",
    "central_row",
    "central_col",
    "station_inside_raster",
    "central_scl",
    "window_size",
    "requested_pixel_count",
    "actual_pixel_count",
    "window_complete",
    "unexpected_scl_count",
    "water_fraction",
    "bad_scl_fraction",
    "processing_status",
} | {f"scl_{code}_count" for code in range(12)} | {
    f"scl_{code}_fraction" for code in range(12)
}


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
    invalid = converted.isna()
    if invalid.any():
        examples = sorted(normalized.loc[invalid].dropna().unique())[:5]
        raise ValueError(
            f"Column {column!r} contains missing or invalid booleans: {examples}"
        )
    return converted.astype(bool)


def _coerce_numeric(
    data: pd.DataFrame, columns: Iterable[str], *, table_name: str
) -> None:
    for column in columns:
        original_nonmissing = data[column].notna()
        converted = pd.to_numeric(data[column], errors="coerce")
        newly_missing = original_nonmissing & converted.isna()
        if newly_missing.any():
            examples = data.loc[newly_missing, column].astype(str).unique()[:5]
            raise ValueError(
                f"{table_name} column {column!r} contains non-numeric values: "
                f"{examples.tolist()}"
            )
        data[column] = converted


def read_and_validate_diagnostics(
    inventory_path: str | Path,
    scene_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read, cross-check, and annotate the two Phase 2A diagnostic tables."""

    inventory_path = Path(inventory_path)
    scene_path = Path(scene_path)
    if not inventory_path.is_file():
        raise FileNotFoundError(f"S2 inventory CSV not found: {inventory_path}")
    if not scene_path.is_file():
        raise FileNotFoundError(f"S2 scene/window CSV not found: {scene_path}")

    inventory = pd.read_csv(inventory_path)
    scenes = pd.read_csv(scene_path)
    _require_columns(
        inventory, INVENTORY_REQUIRED_COLUMNS, table_name="S2 inventory CSV"
    )
    _require_columns(
        scenes, SCENE_REQUIRED_COLUMNS, table_name="S2 scene/window CSV"
    )
    if inventory.empty:
        raise ValueError("S2 inventory CSV contains no product rows.")
    if scenes.empty:
        raise ValueError("S2 scene/window CSV contains no scene/window rows.")

    if inventory["product_id"].isna().any() or inventory["product_id"].duplicated().any():
        raise ValueError("Inventory product_id values must be non-missing and unique.")
    if scenes[["product_id", "window_size"]].duplicated().any():
        raise ValueError("Scene product_id/window_size pairs must be unique.")

    inventory["scl_found"] = _coerce_bool(
        inventory["scl_found"], column="scl_found"
    )
    scenes["station_inside_raster"] = _coerce_bool(
        scenes["station_inside_raster"], column="station_inside_raster"
    )
    scenes["window_complete"] = _coerce_bool(
        scenes["window_complete"], column="window_complete"
    )

    inventory_numeric = ["scl_candidate_count"]
    scene_numeric = [
        "raster_transform_a",
        "raster_transform_b",
        "raster_transform_c",
        "raster_transform_d",
        "raster_transform_e",
        "raster_transform_f",
        "pixel_size_x",
        "pixel_size_y",
        "raster_width",
        "raster_height",
        "station_lat",
        "station_lon",
        "station_x",
        "station_y",
        "central_row",
        "central_col",
        "central_scl",
        "window_size",
        "requested_pixel_count",
        "actual_pixel_count",
        "unexpected_scl_count",
        "water_fraction",
        "bad_scl_fraction",
    ] + [f"scl_{code}_{suffix}" for code in range(12) for suffix in ("count", "fraction")]
    _coerce_numeric(inventory, inventory_numeric, table_name="S2 inventory CSV")
    _coerce_numeric(scenes, scene_numeric, table_name="S2 scene/window CSV")
    if not np.allclose(
        scenes["window_size"], scenes["window_size"].round(), equal_nan=False
    ):
        raise ValueError("window_size must contain integer pixel dimensions.")
    scenes["window_size"] = scenes["window_size"].astype(int)

    for table, name in ((inventory, "inventory"), (scenes, "scene/window")):
        parsed = pd.to_datetime(table["acquisition_date"], errors="coerce")
        if parsed.isna().any():
            bad = table.loc[parsed.isna(), "acquisition_date"].astype(str).unique()[:5]
            raise ValueError(f"Invalid {name} acquisition_date value(s): {bad.tolist()}")
        table["date"] = parsed.dt.normalize()

    inventory_products = set(inventory["product_id"])
    scene_products = set(scenes["product_id"])
    if inventory_products != scene_products:
        only_inventory = sorted(inventory_products - scene_products)[:3]
        only_scenes = sorted(scene_products - inventory_products)[:3]
        raise ValueError(
            "Inventory and scene/window product sets differ; "
            f"inventory-only={only_inventory}, scene-only={only_scenes}."
        )

    expected_windows = set(WINDOW_SIZES)
    window_sets = scenes.groupby("product_id", sort=False)["window_size"].agg(
        lambda values: frozenset(int(value) for value in values)
    )
    bad_window_sets = window_sets.loc[window_sets.ne(frozenset(expected_windows))]
    if not bad_window_sets.empty:
        example = bad_window_sets.index[0]
        raise ValueError(
            "Every product must have exactly one row for each candidate window "
            f"{list(WINDOW_SIZES)}; {example!r} has {sorted(bad_window_sets.iloc[0])}."
        )

    inventory_keys = inventory.set_index("product_id")
    scene_keys = scenes.drop_duplicates("product_id").set_index("product_id")
    for column in (
        "platform",
        "acquisition_datetime",
        "acquisition_date",
        "tile_id",
        "processing_baseline",
    ):
        left = inventory_keys[column].astype("string").sort_index()
        right = scene_keys[column].astype("string").sort_index()
        if not left.equals(right):
            raise ValueError(
                f"Inventory and scene/window metadata disagree in column {column!r}."
            )

    scenes["analysis_valid"] = (
        scenes["processing_status"].eq("ok")
        & scenes["station_inside_raster"]
        & scenes["window_complete"]
        & scenes["actual_pixel_count"].eq(scenes["requested_pixel_count"])
        & scenes["unexpected_scl_count"].eq(0)
        & scenes["water_fraction"].notna()
        & scenes["bad_scl_fraction"].notna()
    )
    valid = scenes.loc[scenes["analysis_valid"]]
    if valid.empty:
        raise ValueError("No valid, complete station-centred diagnostic windows remain.")

    expected_pixels = valid["window_size"].pow(2)
    if not valid["requested_pixel_count"].eq(expected_pixels).all():
        raise ValueError("Valid rows contain a requested pixel count inconsistent with window_size².")

    fraction_columns = [f"scl_{code}_fraction" for code in range(12)]
    if (
        (valid[fraction_columns + ["water_fraction", "bad_scl_fraction"]] < -1e-12).any().any()
        or (valid[fraction_columns + ["water_fraction", "bad_scl_fraction"]] > 1 + 1e-12).any().any()
    ):
        raise ValueError("Valid rows contain SCL fractions outside [0, 1].")
    if not np.allclose(valid[fraction_columns].sum(axis=1), 1.0, atol=1e-9):
        raise ValueError("Valid rows do not have SCL class fractions summing to one.")
    count_columns = [f"scl_{code}_count" for code in range(12)]
    if (valid[count_columns] < 0).any().any():
        raise ValueError("Valid rows contain negative SCL class counts.")
    if not np.allclose(
        valid[count_columns].sum(axis=1), valid["actual_pixel_count"], atol=1e-9
    ):
        raise ValueError("Valid rows do not have SCL class counts summing to actual pixels.")
    if not np.allclose(
        valid[count_columns].to_numpy(dtype=float)
        / valid["actual_pixel_count"].to_numpy(dtype=float)[:, None],
        valid[fraction_columns].to_numpy(dtype=float),
        atol=1e-9,
    ):
        raise ValueError("Valid SCL class counts and fractions are inconsistent.")
    if not np.allclose(valid["water_fraction"], valid["scl_6_fraction"], atol=1e-9):
        raise ValueError("water_fraction does not equal scl_6_fraction in valid rows.")
    expected_bad = valid[[f"scl_{code}_fraction" for code in BAD_SCL_CLASSES]].sum(axis=1)
    if not np.allclose(valid["bad_scl_fraction"], expected_bad, atol=1e-9):
        raise ValueError("bad_scl_fraction does not match the documented obvious-bad classes.")

    scenes["persistent_nonwater_fraction"] = scenes[
        [f"scl_{code}_fraction" for code in PERSISTENT_NONWATER_CLASSES]
    ].sum(axis=1, min_count=len(PERSISTENT_NONWATER_CLASSES))
    scenes["year"] = scenes["date"].dt.year
    scenes["month"] = scenes["date"].dt.month
    inventory["year"] = inventory["date"].dt.year
    inventory["month"] = inventory["date"].dt.month
    return inventory, scenes


def select_analysis_periods(
    scenes: pd.DataFrame,
    *,
    reference_start: str | pd.Timestamp,
    reference_end: str | pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """Return valid rows partitioned around the inclusive reference interval."""

    start = pd.Timestamp(reference_start).normalize()
    end = pd.Timestamp(reference_end).normalize()
    if start > end:
        raise ValueError("reference_start must be on or before reference_end.")
    valid = scenes.loc[scenes["analysis_valid"]].copy()
    periods = {
        "primary_overlap": valid.loc[valid["date"].between(start, end)].copy(),
        "before_reference": valid.loc[valid["date"].lt(start)].copy(),
        "after_reference": valid.loc[valid["date"].gt(end)].copy(),
    }
    if periods["primary_overlap"].empty:
        raise ValueError(
            f"No valid diagnostic rows overlap {start.date()} through {end.date()}."
        )
    return periods


def _quantile(values: pd.Series, probability: float) -> float:
    return float(values.quantile(probability))


def _fraction(condition: pd.Series) -> float:
    return float(condition.mean())


def _summary_statistics(group: pd.DataFrame) -> dict[str, float | int]:
    water = group["water_fraction"]
    bad = group["bad_scl_fraction"]
    persistent_counts = group[
        [f"scl_{code}_count" for code in PERSISTENT_NONWATER_CLASSES]
    ].sum(axis=1)
    output: dict[str, float | int] = {
        "n_scenes": int(len(group)),
        "water_fraction_median": float(water.median()),
        "water_fraction_q05": _quantile(water, 0.05),
        "water_fraction_q25": _quantile(water, 0.25),
        "water_fraction_q75": _quantile(water, 0.75),
        "water_fraction_q95": _quantile(water, 0.95),
        "water_fraction_min": float(water.min()),
        "bad_scl_fraction_median": float(bad.median()),
        "bad_scl_fraction_q05": _quantile(bad, 0.05),
        "bad_scl_fraction_q25": _quantile(bad, 0.25),
        "bad_scl_fraction_q75": _quantile(bad, 0.75),
        "bad_scl_fraction_q95": _quantile(bad, 0.95),
        "bad_scl_fraction_max": float(bad.max()),
        "fraction_water_ge_0_50": _fraction(water.ge(0.50)),
        "fraction_water_ge_0_75": _fraction(water.ge(0.75)),
        "fraction_water_ge_0_90": _fraction(water.ge(0.90)),
        "fraction_water_ge_0_95": _fraction(water.ge(0.95)),
        "fraction_water_eq_1_00": _fraction(water.eq(1.0)),
        "fraction_any_bad_scl": _fraction(bad.gt(0)),
        "fraction_dominated_by_nonwater": _fraction(water.lt(0.50)),
        "fraction_any_persistent_nonwater": _fraction(
            group["persistent_nonwater_fraction"].gt(0)
        ),
        "pixel_weighted_persistent_nonwater_fraction": float(
            persistent_counts.sum() / group["actual_pixel_count"].sum()
        ),
    }
    central_water = group.loc[group["central_scl"].eq(6)]
    output["n_central_water_scenes"] = int(len(central_water))
    output["central_water_water_fraction_q05"] = (
        _quantile(central_water["water_fraction"], 0.05)
        if not central_water.empty
        else np.nan
    )
    output["fraction_central_water_scenes_window_all_water"] = (
        _fraction(central_water["water_fraction"].eq(1.0))
        if not central_water.empty
        else np.nan
    )
    output["fraction_central_water_scenes_any_bad_scl"] = (
        _fraction(central_water["bad_scl_fraction"].gt(0))
        if not central_water.empty
        else np.nan
    )
    return output


def summarize_windows(scenes: pd.DataFrame) -> pd.DataFrame:
    """Build one principal-statistics row per candidate window."""

    rows = []
    for window_size in WINDOW_SIZES:
        group = scenes.loc[scenes["window_size"].eq(window_size)]
        if group.empty:
            raise ValueError(f"No valid rows are available for the {window_size}x{window_size} window.")
        rows.append(
            {
                "window_size": window_size,
                "window_label": f"{window_size}x{window_size}",
                "window_span_m": float(window_size * group["pixel_size_x"].median()),
                "center_to_edge_m": float(window_size * group["pixel_size_x"].median() / 2),
                **_summary_statistics(group),
            }
        )
    return pd.DataFrame(rows)


def summarize_years(scenes: pd.DataFrame) -> pd.DataFrame:
    """Build one full-statistics row per acquisition year and window."""

    rows = []
    for (year, window_size), group in scenes.groupby(
        ["year", "window_size"], sort=True
    ):
        rows.append(
            {
                "year": int(year),
                "window_size": int(window_size),
                "window_label": f"{int(window_size)}x{int(window_size)}",
                **_summary_statistics(group),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "window_size"]).reset_index(drop=True)


def summarize_outside_periods(periods: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summarize valid rows before and after the primary reference interval."""

    rows = []
    for period in ("before_reference", "after_reference"):
        data = periods[period]
        if data.empty:
            continue
        for window_size in WINDOW_SIZES:
            group = data.loc[data["window_size"].eq(window_size)]
            rows.append(
                {
                    "analysis_period": period,
                    "date_min": group["date"].min().date().isoformat(),
                    "date_max": group["date"].max().date().isoformat(),
                    "window_size": window_size,
                    "window_label": f"{window_size}x{window_size}",
                    **_summary_statistics(group),
                }
            )
    return pd.DataFrame(rows)


def summarize_strata(scenes: pd.DataFrame) -> pd.DataFrame:
    """Summarize month, platform, and processing-baseline strata."""

    rows = []
    specifications = (
        ("month", "month"),
        ("platform", "platform"),
        ("processing_baseline", "processing_baseline"),
    )
    for stratum_type, column in specifications:
        for (value, window_size), group in scenes.groupby(
            [column, "window_size"], sort=True
        ):
            stats = _summary_statistics(group)
            rows.append(
                {
                    "stratum_type": stratum_type,
                    "stratum_value": f"{int(value):02d}" if stratum_type == "month" else str(value),
                    "window_size": int(window_size),
                    "n_scenes": stats["n_scenes"],
                    "water_fraction_median": stats["water_fraction_median"],
                    "water_fraction_q05": stats["water_fraction_q05"],
                    "water_fraction_q25": stats["water_fraction_q25"],
                    "water_fraction_q75": stats["water_fraction_q75"],
                    "water_fraction_q95": stats["water_fraction_q95"],
                    "bad_scl_fraction_median": stats["bad_scl_fraction_median"],
                    "bad_scl_fraction_q05": stats["bad_scl_fraction_q05"],
                    "bad_scl_fraction_q95": stats["bad_scl_fraction_q95"],
                    "fraction_water_eq_1_00": stats["fraction_water_eq_1_00"],
                    "fraction_any_bad_scl": stats["fraction_any_bad_scl"],
                    "fraction_dominated_by_nonwater": stats[
                        "fraction_dominated_by_nonwater"
                    ],
                    "fraction_any_persistent_nonwater": stats[
                        "fraction_any_persistent_nonwater"
                    ],
                }
            )
    return pd.DataFrame(rows)


def summarize_central_pixel(scenes: pd.DataFrame) -> pd.DataFrame:
    """Tabulate SCL frequencies for the single station-centred pixel."""

    central = scenes.loc[scenes["window_size"].eq(1)]
    counts = central["central_scl"].value_counts()
    rows = []
    for code in range(12):
        count = int(counts.get(code, 0))
        rows.append(
            {
                "scl_code": code,
                "scl_class": SCL_CLASS_LABELS[code],
                "count": count,
                "fraction": count / len(central),
                "is_water": code == 6,
                "is_obvious_bad": code in BAD_SCL_CLASSES,
                "is_persistent_nonwater_diagnostic": code
                in PERSISTENT_NONWATER_CLASSES,
            }
        )
    return pd.DataFrame(rows)


def summarize_adjacent_transitions(scenes: pd.DataFrame) -> pd.DataFrame:
    """Build paired acquisition-level diagnostics for adjacent windows."""

    metrics = ["water_fraction", "bad_scl_fraction", "persistent_nonwater_fraction"]
    pivots = {
        metric: scenes.pivot(index="product_id", columns="window_size", values=metric)
        for metric in metrics
    }
    central = (
        scenes.loc[scenes["window_size"].eq(1), ["product_id", "central_scl"]]
        .set_index("product_id")["central_scl"]
    )
    rows = []
    for window_from, window_to in zip(WINDOW_SIZES[:-1], WINDOW_SIZES[1:], strict=True):
        delta_water = pivots["water_fraction"][window_to] - pivots["water_fraction"][window_from]
        delta_bad = pivots["bad_scl_fraction"][window_to] - pivots["bad_scl_fraction"][window_from]
        delta_persistent = (
            pivots["persistent_nonwater_fraction"][window_to]
            - pivots["persistent_nonwater_fraction"][window_from]
        )
        central_water_ids = central.index[central.eq(6)]
        central_water_delta = delta_water.loc[central_water_ids]
        central_from = pivots["water_fraction"].loc[central_water_ids, window_from]
        central_to = pivots["water_fraction"].loc[central_water_ids, window_to]
        central_to_bad = pivots["bad_scl_fraction"].loc[central_water_ids, window_to]
        row: dict[str, float | int | str] = {
            "window_from": window_from,
            "window_to": window_to,
            "transition": f"{window_from}x{window_from} to {window_to}x{window_to}",
            "n_paired_scenes": int(len(delta_water)),
            "delta_water_fraction_median": float(delta_water.median()),
            "delta_water_fraction_q05": _quantile(delta_water, 0.05),
            "delta_water_fraction_q25": _quantile(delta_water, 0.25),
            "delta_water_fraction_q75": _quantile(delta_water, 0.75),
            "delta_water_fraction_q95": _quantile(delta_water, 0.95),
            "fraction_water_decreased": _fraction(delta_water.lt(0)),
            "fraction_water_increased": _fraction(delta_water.gt(0)),
            "fraction_water_unchanged": _fraction(delta_water.eq(0)),
            "delta_bad_scl_fraction_median": float(delta_bad.median()),
            "delta_bad_scl_fraction_q05": _quantile(delta_bad, 0.05),
            "delta_bad_scl_fraction_q95": _quantile(delta_bad, 0.95),
            "fraction_bad_scl_increased": _fraction(delta_bad.gt(0)),
            "delta_persistent_nonwater_fraction_median": float(
                delta_persistent.median()
            ),
            "fraction_persistent_nonwater_increased": _fraction(
                delta_persistent.gt(0)
            ),
            "n_central_water_scenes": int(len(central_water_delta)),
            "central_water_delta_water_fraction_q05": _quantile(
                central_water_delta, 0.05
            ),
            "central_water_fraction_water_decreased": _fraction(
                central_water_delta.lt(0)
            ),
            "central_water_from_all_water_fraction": _fraction(central_from.eq(1)),
            "central_water_to_all_water_fraction": _fraction(central_to.eq(1)),
            "central_water_to_water_fraction_q05": _quantile(central_to, 0.05),
            "central_water_to_any_bad_scl_fraction": _fraction(central_to_bad.gt(0)),
        }
        for threshold in WATER_THRESHOLDS:
            suffix = f"{threshold:.2f}".replace(".", "_")
            old = pivots["water_fraction"][window_from].ge(threshold)
            new = pivots["water_fraction"][window_to].ge(threshold)
            row[f"n_lost_water_ge_{suffix}"] = int((old & ~new).sum())
            row[f"n_gained_water_ge_{suffix}"] = int((~old & new).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def build_inventory_qc(
    inventory: pd.DataFrame,
    scenes: pd.DataFrame,
    *,
    reference_start: str | pd.Timestamp,
    reference_end: str | pd.Timestamp,
) -> pd.DataFrame:
    """Create a compact, machine-readable inventory and schema QC audit."""

    start = pd.Timestamp(reference_start).normalize()
    end = pd.Timestamp(reference_end).normalize()
    product_count = len(inventory)
    product_validity = scenes.groupby("product_id")["analysis_valid"].all()
    station_inside = scenes.groupby("product_id")["station_inside_raster"].all()
    duplicate_date_mask = inventory["acquisition_date"].duplicated(keep=False)
    exact_duplicate_mask = inventory.duplicated(
        ["acquisition_datetime", "tile_id"], keep=False
    )
    exact_groups = (
        inventory.loc[exact_duplicate_mask]
        .groupby(["acquisition_datetime", "tile_id"])
        .ngroups
    )
    grid_columns = [
        "scl_crs",
        "raster_transform_a",
        "raster_transform_b",
        "raster_transform_c",
        "raster_transform_d",
        "raster_transform_e",
        "raster_transform_f",
        "pixel_size_x",
        "pixel_size_y",
        "raster_width",
        "raster_height",
        "station_lat",
        "station_lon",
        "station_crs",
        "station_x",
        "station_y",
        "central_row",
        "central_col",
    ]
    grid_signatures = scenes[grid_columns].drop_duplicates()
    rows: list[dict[str, object]] = []

    def add(
        section: str,
        metric: str,
        value: object,
        *,
        count_for_fraction: int | None = None,
        detail: str = "",
    ) -> None:
        rows.append(
            {
                "section": section,
                "metric": metric,
                "value": value,
                "fraction_of_products": (
                    count_for_fraction / product_count
                    if count_for_fraction is not None
                    else np.nan
                ),
                "detail": detail,
            }
        )

    add("inventory", "total_products", product_count, count_for_fraction=product_count)
    add("inventory", "scene_window_rows", len(scenes))
    add("inventory", "acquisition_date_min", inventory["date"].min().date().isoformat())
    add("inventory", "acquisition_date_max", inventory["date"].max().date().isoformat())
    overlap_products = int(inventory["date"].between(start, end).sum())
    before_products = int(inventory["date"].lt(start).sum())
    after_products = int(inventory["date"].gt(end).sum())
    add("period", "primary_overlap_products", overlap_products, count_for_fraction=overlap_products)
    add("period", "before_reference_products", before_products, count_for_fraction=before_products)
    add("period", "after_reference_products", after_products, count_for_fraction=after_products)
    scl_found_count = int(inventory["scl_found"].sum())
    inside_count = int(station_inside.sum())
    valid_count = int(product_validity.sum())
    add("validity", "scl_found_products", scl_found_count, count_for_fraction=scl_found_count)
    add("validity", "station_inside_all_windows_products", inside_count, count_for_fraction=inside_count)
    add("validity", "valid_all_windows_products", valid_count, count_for_fraction=valid_count)
    add(
        "validity",
        "missing_or_invalid_diagnostic_products",
        product_count - valid_count,
        count_for_fraction=product_count - valid_count,
    )
    duplicate_date_count = int(inventory.loc[duplicate_date_mask, "acquisition_date"].nunique())
    duplicate_product_rows = int(duplicate_date_mask.sum())
    add("duplicates", "duplicate_acquisition_dates", duplicate_date_count)
    add(
        "duplicates",
        "products_on_duplicate_acquisition_dates",
        duplicate_product_rows,
        count_for_fraction=duplicate_product_rows,
        detail="Products are retained; a date is not treated as a unique acquisition key.",
    )
    add("duplicates", "exact_datetime_tile_duplicate_groups", exact_groups)
    add(
        "duplicates",
        "products_in_exact_datetime_tile_duplicate_groups",
        int(exact_duplicate_mask.sum()),
        count_for_fraction=int(exact_duplicate_mask.sum()),
    )
    add(
        "duplicates",
        "maximum_products_per_acquisition_date",
        int(inventory.groupby("acquisition_date").size().max()),
    )
    for status, count in inventory["processing_status"].value_counts(dropna=False).sort_index().items():
        add(
            "inventory_processing_status",
            str(status),
            int(count),
            count_for_fraction=int(count),
        )
    for status, count in scenes["processing_status"].value_counts(dropna=False).sort_index().items():
        add(
            "scene_window_processing_status",
            str(status),
            int(count),
            detail=f"Fraction of {len(scenes)} scene/window rows: {int(count) / len(scenes):.10g}.",
        )
    for column, section in (
        ("platform", "platform"),
        ("tile_id", "tile"),
        ("processing_baseline", "processing_baseline"),
        ("scl_candidate_count", "scl_candidate_count"),
    ):
        for value, count in inventory[column].value_counts(dropna=False).sort_index().items():
            add(section, str(value), int(count), count_for_fraction=int(count))
    resolution = (
        scenes[["product_id", "pixel_size_x", "pixel_size_y"]]
        .drop_duplicates("product_id")
        .value_counts(["pixel_size_x", "pixel_size_y"])
    )
    for (pixel_x, pixel_y), count in resolution.items():
        add(
            "raster_resolution_m",
            f"{pixel_x:g}x{pixel_y:g}",
            int(count),
            count_for_fraction=int(count),
        )
    add("raster_metadata", "unique_grid_signatures", len(grid_signatures))
    add(
        "raster_metadata",
        "grid_change_flag",
        int(len(grid_signatures) > 1),
        detail=(
            "1 means CRS, affine transform, resolution, dimensions, station "
            "coordinate, or station row/column changed."
        ),
    )
    add(
        "raster_metadata",
        "unexpected_scl_pixel_count",
        int(scenes["unexpected_scl_count"].fillna(0).sum()),
    )
    return pd.DataFrame(rows)


def build_analysis_tables(
    inventory: pd.DataFrame,
    scenes: pd.DataFrame,
    *,
    reference_start: str | pd.Timestamp,
    reference_end: str | pd.Timestamp,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Build all Phase 2A-2 tables and return the primary-overlap rows."""

    periods = select_analysis_periods(
        scenes, reference_start=reference_start, reference_end=reference_end
    )
    primary = periods["primary_overlap"]
    tables = {
        "erken_s2_scl_inventory_qc_summary.csv": build_inventory_qc(
            inventory,
            scenes,
            reference_start=reference_start,
            reference_end=reference_end,
        ),
        "erken_s2_scl_window_summary.csv": summarize_windows(primary),
        "erken_s2_scl_window_year_summary.csv": summarize_years(primary),
        "erken_s2_scl_window_stratified_summary.csv": summarize_strata(primary),
        "erken_s2_scl_window_transition_summary.csv": summarize_adjacent_transitions(primary),
        "erken_s2_scl_central_pixel_class_frequency.csv": summarize_central_pixel(primary),
        "erken_s2_scl_window_outside_reference_summary.csv": summarize_outside_periods(periods),
    }
    return tables, primary


def write_analysis_tables(
    tables: dict[str, pd.DataFrame], output_directory: str | Path
) -> list[Path]:
    """Write deterministic CSV outputs and return their paths."""

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, table in tables.items():
        path = output_directory / filename
        table.to_csv(
            path,
            index=False,
            float_format="%.10g",
            lineterminator="\n",
        )
        paths.append(path)
    return paths


def _plot_style() -> dict[str, object]:
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
    figure.savefig(pdf, facecolor="white")
    plt.close(figure)
    return [png, pdf]


def _empirical_probability(values: pd.Series, grid: np.ndarray, *, mode: str) -> np.ndarray:
    array = values.to_numpy(dtype=float)
    if mode == "at_least":
        return np.array([(array >= threshold).mean() for threshold in grid])
    if mode == "at_most":
        return np.array([(array <= threshold).mean() for threshold in grid])
    raise ValueError(f"Unknown empirical probability mode: {mode}")


def generate_roi_figures(
    primary: pd.DataFrame,
    year_summary: pd.DataFrame,
    central_frequency: pd.DataFrame,
    output_directory: str | Path,
) -> list[Path]:
    """Generate the five Phase 2A-2 diagnostic figures as PNG and PDF."""

    output_directory = Path(output_directory)
    colors = plt.get_cmap("tab10").colors
    outputs: list[Path] = []

    with plt.rc_context(_plot_style()):
        grid = np.linspace(0, 1, 201)
        fig, ax = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
        for index, window_size in enumerate(WINDOW_SIZES):
            values = primary.loc[
                primary["window_size"].eq(window_size), "water_fraction"
            ]
            probability = _empirical_probability(values, grid, mode="at_least")
            ax.step(
                grid,
                probability,
                where="post",
                color=colors[index],
                linewidth=1.5,
                label=f"{window_size}x{window_size}",
            )
        for threshold in WATER_THRESHOLDS:
            ax.axvline(threshold, color="#6b7280", linewidth=0.6, alpha=0.28)
        ax.set(
            title="Erken SCL water-fraction distributions by station-centred window",
            xlabel="SCL water fraction",
            ylabel="Fraction of acquisitions at or above value",
            xlim=(0, 1),
            ylim=(-0.01, 1.01),
        )
        ax.legend(frameon=False, ncol=5, loc="upper center")
        ax.text(
            0.01,
            0.02,
            "Primary overlap; guide lines are descriptive, not QC thresholds",
            transform=ax.transAxes,
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_06_erken_s2_water_fraction_by_window"
            )
        )

    with plt.rc_context(_plot_style()):
        grid = np.linspace(0, 1, 201)
        fig, ax = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
        for index, window_size in enumerate(WINDOW_SIZES):
            values = primary.loc[
                primary["window_size"].eq(window_size), "bad_scl_fraction"
            ]
            probability = _empirical_probability(values, grid, mode="at_most")
            ax.step(
                grid,
                probability,
                where="post",
                color=colors[index],
                linewidth=1.5,
                label=f"{window_size}x{window_size}",
            )
        ax.set(
            title="Erken obvious-bad SCL-fraction distributions by window",
            xlabel="Obvious-bad SCL fraction",
            ylabel="Fraction of acquisitions at or below value",
            xlim=(0, 1),
            ylim=(-0.01, 1.01),
        )
        ax.set_yticks(np.linspace(0, 1, 6))
        ax.legend(frameon=False, ncol=5, loc="lower center")
        ax.text(
            0.01,
            0.98,
            "Classes 0, 1, 3, 8, 9, 10, 11; no usability cutoff applied",
            transform=ax.transAxes,
            va="top",
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_07_erken_s2_bad_fraction_by_window"
            )
        )

    with plt.rc_context(_plot_style()):
        heatmap = year_summary.pivot(
            index="year", columns="window_size", values="fraction_water_eq_1_00"
        ).reindex(columns=WINDOW_SIZES)
        fig, ax = plt.subplots(figsize=(7.2, 5.0), constrained_layout=True)
        image = ax.imshow(heatmap.to_numpy(), cmap="Blues", vmin=0, vmax=0.5, aspect="auto")
        ax.grid(False)
        ax.set_xticks(range(len(WINDOW_SIZES)), [f"{w}x{w}" for w in WINDOW_SIZES])
        ax.set_yticks(range(len(heatmap.index)), [str(year) for year in heatmap.index])
        ax.set(
            title="Yearly fraction of Erken acquisitions with an all-water SCL window",
            xlabel="Station-centred window",
            ylabel="Acquisition year",
        )
        for row_index in range(heatmap.shape[0]):
            for column_index in range(heatmap.shape[1]):
                value = heatmap.iloc[row_index, column_index]
                ax.text(
                    column_index,
                    row_index,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    color="white" if value > 0.30 else "#111827",
                    fontsize=8,
                )
        colorbar = fig.colorbar(image, ax=ax, shrink=0.88)
        colorbar.set_label("Fraction all water")
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_08_erken_s2_all_water_year_heatmap"
            )
        )

    with plt.rc_context(_plot_style()):
        central_water = primary.loc[primary["central_scl"].eq(6)]
        paired = central_water.pivot(
            index="product_id", columns="window_size", values="water_fraction"
        ).reindex(columns=WINDOW_SIZES)
        fig, axes = plt.subplots(
            2,
            1,
            figsize=(8.2, 7.0),
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": [2.2, 1]},
        )
        x = np.arange(len(WINDOW_SIZES))
        for values in paired.to_numpy():
            axes[0].plot(x, values, color="#6b7280", alpha=0.055, linewidth=0.6)
        axes[0].plot(
            x,
            paired.median().to_numpy(),
            color=colors[0],
            marker="o",
            linewidth=1.8,
            label="Median",
        )
        axes[0].plot(
            x,
            paired.quantile(0.05).to_numpy(),
            color=colors[1],
            marker="s",
            linewidth=1.6,
            label="Q05",
        )
        axes[0].set(
            title="Paired spatial expansion for acquisitions with a water centre pixel",
            ylabel="SCL water fraction",
            ylim=(-0.02, 1.02),
        )
        axes[0].legend(frameon=False, loc="lower left")
        all_water = paired.eq(1).mean()
        any_bad = (
            central_water.pivot(
                index="product_id", columns="window_size", values="bad_scl_fraction"
            )
            .reindex(columns=WINDOW_SIZES)
            .gt(0)
            .mean()
        )
        axes[1].plot(
            x,
            all_water.to_numpy(),
            color=colors[0],
            marker="o",
            linewidth=1.8,
            label="Entire window is water",
        )
        axes[1].plot(
            x,
            any_bad.to_numpy(),
            color=colors[3],
            marker="o",
            linewidth=1.8,
            label="Any obvious-bad pixel",
        )
        axes[1].set(
            xlabel="Station-centred window",
            ylabel="Fraction of centre-water scenes",
            ylim=(-0.02, 1.02),
        )
        axes[1].set_xticks(x, [f"{w}x{w}" for w in WINDOW_SIZES])
        axes[1].legend(frameon=False, ncol=2, loc="center left")
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_09_erken_s2_paired_window_expansion"
            )
        )

    with plt.rc_context(_plot_style()):
        frequency = central_frequency.copy()
        colors_by_class = []
        for row in frequency.itertuples(index=False):
            if row.is_water:
                colors_by_class.append(colors[0])
            elif row.is_obvious_bad:
                colors_by_class.append(colors[3])
            else:
                colors_by_class.append("#6b7280")
        fig, ax = plt.subplots(figsize=(9.0, 5.0), constrained_layout=True)
        bars = ax.bar(
            frequency["scl_code"],
            frequency["fraction"],
            color=colors_by_class,
            width=0.75,
        )
        ax.set(
            title="Erken station-centre SCL class frequency",
            xlabel="SCL class code",
            ylabel="Fraction of acquisitions",
            xticks=range(12),
            ylim=(0, max(0.40, float(frequency["fraction"].max()) * 1.18)),
        )
        for bar, fraction in zip(bars, frequency["fraction"], strict=True):
            if fraction > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.008,
                    f"{fraction:.1%}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
        ax.legend(
            handles=[
                Patch(facecolor=colors[0], label="Water (6)"),
                Patch(facecolor=colors[3], label="Obvious bad classes"),
                Patch(facecolor="#6b7280", label="Other non-water classes"),
            ],
            frameon=False,
            ncol=3,
            loc="upper center",
        )
        ax.text(
            0.01,
            0.02,
            "Only codes 6, 8, 9, 10 and 11 occur in the primary overlap",
            transform=ax.transAxes,
            va="bottom",
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_10_erken_s2_central_pixel_frequency"
            )
        )
    return outputs
