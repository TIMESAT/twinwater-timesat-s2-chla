"""Build a calendar-date Sentinel-2 SCL observation mask for Lake Erken.

The module consumes the committed Phase 2A inventory and SCL window summaries.
It uses SCL only: no chlorophyll, reflectance, index, or reconstruction value is
read or used to define scene usability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, floor
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from twinwater_timesat.s2_roi import (
    BAD_SCL_CLASSES,
    PERSISTENT_NONWATER_CLASSES,
)


CENTER_PIXEL_RULES = {"water", "not_obvious_bad"}
DATE_COLLAPSE_RANKING = [
    "lowest_bad_scl_fraction",
    "highest_water_fraction",
    "lowest_persistent_nonwater_fraction",
    "central_scl_is_water",
    "earliest_acquisition_datetime",
    "lexical_product_id",
]
PRIMARY_PRODUCT_QC_COLUMNS = [
    "product_id",
    "platform",
    "acquisition_datetime",
    "date",
    "processing_baseline",
    "central_scl",
    "water_pixel_count_3x3",
    "bad_pixel_count_3x3",
    "persistent_nonwater_pixel_count_3x3",
    "class2_pixel_count_3x3",
    "water_fraction_3x3",
    "bad_scl_fraction_3x3",
    "persistent_nonwater_fraction_3x3",
    "class2_fraction_3x3",
    "central_is_water",
    "central_is_obvious_bad",
    "central_is_persistent_nonwater",
    "central_is_class2",
    "passes_final_rule",
    "final_rule_failure_reasons",
    "qc_rule_id",
    "mask_version",
]


@dataclass(frozen=True)
class QcRule:
    """An integer-pixel SCL usability rule for one square neighborhood."""

    rule_id: str
    rule_label: str
    role: str
    maximum_bad_pixels: int
    minimum_water_pixels: int
    center_pixel_rule: str
    maximum_persistent_nonwater_pixels: int
    maximum_class2_pixels: int


def _require_columns(
    data: pd.DataFrame, required: set[str], *, table_name: str
) -> None:
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(
            f"{table_name} is missing required column(s): {', '.join(missing)}"
        )


def _parse_date(value: Any, *, field: str) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value).normalize()
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {field}: {value!r}.") from error
    if pd.isna(parsed):
        raise ValueError(f"Invalid {field}: {value!r}.")
    return parsed


def rule_from_mapping(data: Mapping[str, Any], *, window_size: int) -> QcRule:
    """Parse and validate one configured rule."""

    required = {
        "rule_id",
        "rule_label",
        "role",
        "maximum_bad_pixels",
        "minimum_water_pixels",
        "center_pixel_rule",
        "maximum_persistent_nonwater_pixels",
        "maximum_class2_pixels",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"QC rule is missing field(s): {', '.join(missing)}")
    pixel_count = window_size**2
    integer_fields = (
        "maximum_bad_pixels",
        "minimum_water_pixels",
        "maximum_persistent_nonwater_pixels",
        "maximum_class2_pixels",
    )
    values: dict[str, int] = {}
    for field in integer_fields:
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"QC rule {field} must be an integer, got {value!r}.")
        if not 0 <= value <= pixel_count:
            raise ValueError(
                f"QC rule {field}={value} is outside 0..{pixel_count} "
                f"for a {window_size}x{window_size} window."
            )
        values[field] = value
    center_rule = str(data["center_pixel_rule"])
    if center_rule not in CENTER_PIXEL_RULES:
        raise ValueError(
            "QC rule center_pixel_rule must be 'water' or 'not_obvious_bad'."
        )
    rule_id = str(data["rule_id"]).strip()
    if not rule_id:
        raise ValueError("QC rule rule_id must not be empty.")
    return QcRule(
        rule_id=rule_id,
        rule_label=str(data["rule_label"]),
        role=str(data["role"]),
        center_pixel_rule=center_rule,
        **values,
    )


def load_mask_config(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate the versioned SCL mask configuration."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"S2 observation-mask config not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("S2 observation-mask config must be a YAML mapping.")
    required = {
        "mask_version",
        "reference_interval",
        "roi_window_size",
        "spatial_sensitivity_windows",
        "water_scl_class",
        "bad_scl_classes",
        "persistent_nonwater_scl_classes",
        "class2_scl_class",
        "final_rule",
        "date_collapse",
        "candidate_rules",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Mask config is missing field(s): {', '.join(missing)}")

    window_size = config["roi_window_size"]
    if isinstance(window_size, bool) or not isinstance(window_size, int):
        raise ValueError("roi_window_size must be an integer.")
    if window_size != 3:
        raise ValueError("Phase 2A-2 froze roi_window_size at 3.")
    if list(config["spatial_sensitivity_windows"]) != [1, 5]:
        raise ValueError("spatial_sensitivity_windows must preserve the frozen [1, 5] cases.")
    if int(config["water_scl_class"]) != 6:
        raise ValueError("water_scl_class must be 6.")
    if tuple(config["bad_scl_classes"]) != BAD_SCL_CLASSES:
        raise ValueError(
            f"bad_scl_classes must be the documented classes {list(BAD_SCL_CLASSES)}."
        )
    if tuple(config["persistent_nonwater_scl_classes"]) != PERSISTENT_NONWATER_CLASSES:
        raise ValueError(
            "persistent_nonwater_scl_classes must be the documented classes "
            f"{list(PERSISTENT_NONWATER_CLASSES)}."
        )
    if int(config["class2_scl_class"]) != 2:
        raise ValueError("class2_scl_class must be 2 and remain separate.")

    interval = config["reference_interval"]
    if not isinstance(interval, dict) or not {"start", "end"}.issubset(interval):
        raise ValueError("reference_interval must contain start and end.")
    start = _parse_date(interval["start"], field="reference_interval.start")
    end = _parse_date(interval["end"], field="reference_interval.end")
    if start > end:
        raise ValueError("reference_interval.start must be on or before end.")

    collapse = config["date_collapse"]
    if not isinstance(collapse, dict):
        raise ValueError("date_collapse must be a mapping.")
    if collapse.get("observation_unit") != "calendar_date":
        raise ValueError("date_collapse.observation_unit must be calendar_date.")
    if collapse.get("usable_when") != "any_product_passes":
        raise ValueError("date_collapse.usable_when must be any_product_passes.")
    if collapse.get("representative_product_ranking") != DATE_COLLAPSE_RANKING:
        raise ValueError(
            "representative_product_ranking does not match the frozen deterministic order."
        )

    final_rule = rule_from_mapping(config["final_rule"], window_size=window_size)
    candidate_data = config["candidate_rules"]
    if not isinstance(candidate_data, list) or not candidate_data:
        raise ValueError("candidate_rules must be a non-empty list.")
    candidate_rules = [
        rule_from_mapping(item, window_size=window_size) for item in candidate_data
    ]
    ids = [rule.rule_id for rule in candidate_rules]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate rule_id values must be unique.")
    matching = [rule for rule in candidate_rules if rule.rule_id == final_rule.rule_id]
    if matching != [final_rule]:
        raise ValueError(
            "final_rule must appear exactly and identically in candidate_rules."
        )
    if str(config["mask_version"]).strip() == "":
        raise ValueError("mask_version must not be empty.")

    validated = dict(config)
    validated["reference_start"] = start
    validated["reference_end"] = end
    validated["final_rule_object"] = final_rule
    validated["candidate_rule_objects"] = candidate_rules
    return validated


def build_product_qc(
    inventory: pd.DataFrame,
    scenes: pd.DataFrame,
    *,
    window_size: int,
    reference_start: str | pd.Timestamp,
    reference_end: str | pd.Timestamp,
) -> pd.DataFrame:
    """Build product-level SCL count variables for one reference interval."""

    _require_columns(
        inventory,
        {
            "product_id",
            "platform",
            "acquisition_datetime",
            "date",
            "processing_baseline",
            "processing_status",
            "tile_id",
        },
        table_name="validated S2 inventory",
    )
    required_scene = {
        "product_id",
        "platform",
        "acquisition_datetime",
        "date",
        "processing_baseline",
        "central_scl",
        "window_size",
        "requested_pixel_count",
        "actual_pixel_count",
        "analysis_valid",
    } | {f"scl_{code}_count" for code in range(12)}
    _require_columns(scenes, required_scene, table_name="validated S2 scene table")

    start = _parse_date(reference_start, field="reference_start")
    end = _parse_date(reference_end, field="reference_end")
    if start > end:
        raise ValueError("reference_start must be on or before reference_end.")
    primary_inventory = inventory.loc[inventory["date"].between(start, end)].copy()
    if primary_inventory.empty:
        raise ValueError("No inventory products occur in the configured interval.")
    selected = scenes.loc[
        scenes["date"].between(start, end) & scenes["window_size"].eq(window_size)
    ].copy()
    if selected.empty:
        raise ValueError(f"No {window_size}x{window_size} SCL rows occur in the interval.")
    if selected["product_id"].duplicated().any():
        raise ValueError(
            f"The {window_size}x{window_size} scene rows contain duplicate product_id values."
        )
    inventory_ids = set(primary_inventory["product_id"])
    selected_ids = set(selected["product_id"])
    if inventory_ids != selected_ids:
        raise ValueError(
            "Primary inventory and selected window product sets differ; every product "
            "must remain available for provenance."
        )
    if not selected["analysis_valid"].all():
        invalid = selected.loc[~selected["analysis_valid"], "product_id"].tolist()[:5]
        raise ValueError(
            "Primary interval contains invalid selected-window SCL rows; examples: "
            f"{invalid}."
        )
    pixel_count = window_size**2
    if not selected["requested_pixel_count"].eq(pixel_count).all():
        raise ValueError("Selected SCL rows do not match the expected window pixel count.")
    if not selected["actual_pixel_count"].eq(pixel_count).all():
        raise ValueError("Selected SCL rows are incomplete.")

    count_columns = [f"scl_{code}_count" for code in range(12)]
    counts = selected[count_columns].apply(pd.to_numeric, errors="coerce")
    if counts.isna().any().any() or (counts < 0).any().any():
        raise ValueError("Selected SCL class counts must be complete and non-negative.")
    if not np.allclose(counts.sum(axis=1), pixel_count):
        raise ValueError("Selected SCL class counts do not sum to the window pixel count.")
    if not np.allclose(counts, counts.round()):
        raise ValueError("Selected SCL class counts must be integers.")

    selected["water_pixel_count"] = counts["scl_6_count"].astype(int)
    selected["bad_pixel_count"] = counts[
        [f"scl_{code}_count" for code in BAD_SCL_CLASSES]
    ].sum(axis=1).astype(int)
    selected["persistent_nonwater_pixel_count"] = counts[
        [f"scl_{code}_count" for code in PERSISTENT_NONWATER_CLASSES]
    ].sum(axis=1).astype(int)
    selected["class2_pixel_count"] = counts["scl_2_count"].astype(int)
    partition = selected[
        [
            "water_pixel_count",
            "bad_pixel_count",
            "persistent_nonwater_pixel_count",
            "class2_pixel_count",
        ]
    ].sum(axis=1)
    if not partition.eq(pixel_count).all():
        raise ValueError(
            "Water, obvious-bad, persistent-nonwater, and class-2 counts do not "
            "partition the selected SCL window."
        )
    selected["water_fraction"] = selected["water_pixel_count"] / pixel_count
    selected["bad_scl_fraction"] = selected["bad_pixel_count"] / pixel_count
    selected["persistent_nonwater_fraction"] = (
        selected["persistent_nonwater_pixel_count"] / pixel_count
    )
    selected["class2_fraction"] = selected["class2_pixel_count"] / pixel_count
    selected["central_scl"] = selected["central_scl"].astype(int)
    selected["central_is_water"] = selected["central_scl"].eq(6)
    selected["central_is_obvious_bad"] = selected["central_scl"].isin(
        BAD_SCL_CLASSES
    )
    selected["central_is_persistent_nonwater"] = selected["central_scl"].isin(
        PERSISTENT_NONWATER_CLASSES
    )
    selected["central_is_class2"] = selected["central_scl"].eq(2)
    acquisition = pd.to_datetime(
        selected["acquisition_datetime"], errors="coerce", utc=True
    )
    if acquisition.isna().any():
        bad = selected.loc[acquisition.isna(), "acquisition_datetime"].tolist()[:5]
        raise ValueError(f"Invalid acquisition_datetime value(s): {bad}.")
    selected["_acquisition_sort"] = acquisition
    selected["date"] = pd.to_datetime(selected["date"]).dt.normalize()
    selected["year"] = selected["date"].dt.year.astype(int)
    selected["month"] = selected["date"].dt.month.astype(int)
    selected["window_size"] = int(window_size)
    selected = selected.sort_values(
        ["date", "_acquisition_sort", "product_id"], kind="mergesort"
    ).reset_index(drop=True)
    return selected[
        [
            "product_id",
            "platform",
            "acquisition_datetime",
            "date",
            "year",
            "month",
            "processing_baseline",
            "central_scl",
            "window_size",
            "water_pixel_count",
            "bad_pixel_count",
            "persistent_nonwater_pixel_count",
            "class2_pixel_count",
            "water_fraction",
            "bad_scl_fraction",
            "persistent_nonwater_fraction",
            "class2_fraction",
            "central_is_water",
            "central_is_obvious_bad",
            "central_is_persistent_nonwater",
            "central_is_class2",
            "_acquisition_sort",
        ]
    ]


def evaluate_rule(product_qc: pd.DataFrame, rule: QcRule) -> pd.Series:
    """Return one product-level pass/fail boolean per input row."""

    _require_columns(
        product_qc,
        {
            "water_pixel_count",
            "bad_pixel_count",
            "persistent_nonwater_pixel_count",
            "class2_pixel_count",
            "central_is_water",
            "central_is_obvious_bad",
        },
        table_name="product QC table",
    )
    center_pass = (
        product_qc["central_is_water"]
        if rule.center_pixel_rule == "water"
        else ~product_qc["central_is_obvious_bad"]
    )
    passed = (
        product_qc["bad_pixel_count"].le(rule.maximum_bad_pixels)
        & product_qc["water_pixel_count"].ge(rule.minimum_water_pixels)
        & center_pass
        & product_qc["persistent_nonwater_pixel_count"].le(
            rule.maximum_persistent_nonwater_pixels
        )
        & product_qc["class2_pixel_count"].le(rule.maximum_class2_pixels)
    )
    return passed.astype(bool).rename("passes_rule")


def rule_failure_reasons(product_qc: pd.DataFrame, rule: QcRule) -> pd.Series:
    """Create deterministic semicolon-delimited failure reasons per product."""

    evaluate_rule(product_qc, rule)
    reasons: list[str] = []
    for row in product_qc.itertuples(index=False):
        row_reasons = []
        if row.bad_pixel_count > rule.maximum_bad_pixels:
            row_reasons.append("too_many_obvious_bad_pixels")
        if row.water_pixel_count < rule.minimum_water_pixels:
            row_reasons.append("insufficient_water_pixels")
        if rule.center_pixel_rule == "water" and not row.central_is_water:
            row_reasons.append("center_not_water")
        if rule.center_pixel_rule == "not_obvious_bad" and row.central_is_obvious_bad:
            row_reasons.append("center_obvious_bad")
        if (
            row.persistent_nonwater_pixel_count
            > rule.maximum_persistent_nonwater_pixels
        ):
            row_reasons.append("persistent_nonwater_present")
        if row.class2_pixel_count > rule.maximum_class2_pixels:
            row_reasons.append("class2_present")
        reasons.append("pass" if not row_reasons else ";".join(row_reasons))
    return pd.Series(reasons, index=product_qc.index, name="rule_failure_reasons")


def summarize_state_space(product_qc: pd.DataFrame) -> pd.DataFrame:
    """Count the discrete SCL states actually observed in the selected window."""

    state_columns = [
        "central_scl",
        "water_pixel_count",
        "bad_pixel_count",
        "persistent_nonwater_pixel_count",
        "class2_pixel_count",
    ]
    _require_columns(product_qc, set(state_columns), table_name="product QC table")
    result = (
        product_qc.groupby(state_columns, dropna=False, sort=True)
        .size()
        .rename("n_products")
        .reset_index()
    )
    result["fraction_of_products"] = result["n_products"] / len(product_qc)
    return result.sort_values(
        ["n_products", *state_columns],
        ascending=[False, True, False, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def collapse_products_to_dates(
    product_qc: pd.DataFrame,
    rule: QcRule,
    *,
    mask_version: str,
) -> pd.DataFrame:
    """Collapse product QC to one calendar-date row using the frozen ranking."""

    required = {
        "product_id",
        "platform",
        "acquisition_datetime",
        "date",
        "processing_baseline",
        "central_scl",
        "water_pixel_count",
        "bad_pixel_count",
        "persistent_nonwater_pixel_count",
        "class2_pixel_count",
        "water_fraction",
        "bad_scl_fraction",
        "persistent_nonwater_fraction",
        "central_is_water",
        "_acquisition_sort",
    }
    _require_columns(product_qc, required, table_name="product QC table")
    if product_qc["product_id"].isna().any():
        raise ValueError("product QC product_id values must be non-missing.")
    working = product_qc.copy()
    working["passes_rule"] = evaluate_rule(working, rule)
    working["_failure"] = rule_failure_reasons(working, rule)
    rows: list[dict[str, Any]] = []
    for date, group in working.groupby("date", sort=True):
        ordered_all = group.sort_values(
            ["_acquisition_sort", "product_id"], kind="mergesort"
        )
        passing = group.loc[group["passes_rule"]].copy()
        passing = passing.sort_values(
            [
                "bad_scl_fraction",
                "water_fraction",
                "persistent_nonwater_fraction",
                "central_is_water",
                "_acquisition_sort",
                "product_id",
            ],
            ascending=[True, False, True, False, True, True],
            kind="mergesort",
        )
        selected = passing.iloc[0] if not passing.empty else None
        n_products = int(len(group))
        n_passing = int(len(passing))
        row: dict[str, Any] = {
            "date": pd.Timestamp(date).normalize(),
            "year": int(pd.Timestamp(date).year),
            "n_products_on_date": n_products,
            "n_products_passing": n_passing,
            "s2_date_usable": bool(n_passing > 0),
            "all_product_ids": ";".join(ordered_all["product_id"].astype(str)),
            "product_pass_status": ";".join(
                f"{item.product_id}={'pass' if item.passes_rule else 'fail'}"
                for item in ordered_all.itertuples(index=False)
            ),
            "date_rescued_by_alternate_product": bool(
                n_products > 1 and 0 < n_passing < n_products
            ),
            "selected_product_id": pd.NA,
            "selected_platform": pd.NA,
            "selected_acquisition_datetime": pd.NA,
            "selected_processing_baseline": pd.NA,
            "selected_central_scl": pd.NA,
            "selected_water_pixel_count_3x3": pd.NA,
            "selected_bad_pixel_count_3x3": pd.NA,
            "selected_persistent_nonwater_pixel_count_3x3": pd.NA,
            "selected_class2_pixel_count_3x3": pd.NA,
            "selected_water_fraction_3x3": np.nan,
            "selected_bad_scl_fraction_3x3": np.nan,
            "selected_persistent_nonwater_fraction_3x3": np.nan,
            "qc_rule_id": rule.rule_id,
            "mask_version": mask_version,
            "reason_if_unusable": (
                pd.NA
                if n_passing
                else "no_product_on_date_passed_scene_quality_rule"
            ),
        }
        if selected is not None:
            row.update(
                {
                    "selected_product_id": selected["product_id"],
                    "selected_platform": selected["platform"],
                    "selected_acquisition_datetime": selected[
                        "acquisition_datetime"
                    ],
                    "selected_processing_baseline": selected[
                        "processing_baseline"
                    ],
                    "selected_central_scl": int(selected["central_scl"]),
                    "selected_water_pixel_count_3x3": int(
                        selected["water_pixel_count"]
                    ),
                    "selected_bad_pixel_count_3x3": int(
                        selected["bad_pixel_count"]
                    ),
                    "selected_persistent_nonwater_pixel_count_3x3": int(
                        selected["persistent_nonwater_pixel_count"]
                    ),
                    "selected_class2_pixel_count_3x3": int(
                        selected["class2_pixel_count"]
                    ),
                    "selected_water_fraction_3x3": float(
                        selected["water_fraction"]
                    ),
                    "selected_bad_scl_fraction_3x3": float(
                        selected["bad_scl_fraction"]
                    ),
                    "selected_persistent_nonwater_fraction_3x3": float(
                        selected["persistent_nonwater_fraction"]
                    ),
                }
            )
        rows.append(row)
    result = pd.DataFrame(rows).sort_values("date", kind="mergesort").reset_index(
        drop=True
    )
    if result["date"].duplicated().any():
        raise AssertionError("Date collapse produced duplicate calendar dates.")
    return result


def _gap_statistics(date_mask: pd.DataFrame) -> dict[str, Any]:
    usable = date_mask.loc[date_mask["s2_date_usable"], "date"].sort_values()
    gaps = usable.diff().dt.days.dropna()
    return {
        "first_usable_date": usable.min() if not usable.empty else pd.NaT,
        "last_usable_date": usable.max() if not usable.empty else pd.NaT,
        "median_interval_days": float(gaps.median()) if not gaps.empty else np.nan,
        "q25_interval_days": float(gaps.quantile(0.25)) if not gaps.empty else np.nan,
        "q75_interval_days": float(gaps.quantile(0.75)) if not gaps.empty else np.nan,
        "maximum_gap_days": int(gaps.max()) if not gaps.empty else np.nan,
        "n_gaps_gt_10_days": int(gaps.gt(10).sum()),
        "n_gaps_gt_20_days": int(gaps.gt(20).sum()),
        "n_gaps_gt_30_days": int(gaps.gt(30).sum()),
        "n_gaps_gt_45_days": int(gaps.gt(45).sum()),
    }


def summarize_rule_sensitivity(
    product_qc: pd.DataFrame,
    rules: Sequence[QcRule],
    *,
    mask_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """Summarize product/date retention, annual counts, months, and gaps."""

    total_products = len(product_qc)
    total_dates = product_qc["date"].nunique()
    years = list(
        range(int(product_qc["year"].min()), int(product_qc["year"].max()) + 1)
    )
    summaries: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []
    month_rows: list[dict[str, Any]] = []
    date_masks: dict[str, pd.DataFrame] = {}

    for rule in rules:
        product_pass = evaluate_rule(product_qc, rule)
        date_mask = collapse_products_to_dates(
            product_qc, rule, mask_version=mask_version
        )
        date_masks[rule.rule_id] = date_mask
        row: dict[str, Any] = {
            "rule_id": rule.rule_id,
            "rule_label": rule.rule_label,
            "rule_role": rule.role,
            "roi_window_size": int(product_qc["window_size"].iloc[0]),
            "maximum_bad_pixels": rule.maximum_bad_pixels,
            "minimum_water_pixels": rule.minimum_water_pixels,
            "center_pixel_rule": rule.center_pixel_rule,
            "maximum_persistent_nonwater_pixels": rule.maximum_persistent_nonwater_pixels,
            "maximum_class2_pixels": rule.maximum_class2_pixels,
            "n_products": total_products,
            "n_products_passing": int(product_pass.sum()),
            "product_pass_fraction": float(product_pass.mean()),
            "n_candidate_dates": total_dates,
            "n_usable_dates": int(date_mask["s2_date_usable"].sum()),
            "date_retention_fraction": float(date_mask["s2_date_usable"].mean()),
            "n_dates_with_multiple_products": int(
                date_mask["n_products_on_date"].gt(1).sum()
            ),
            "n_dates_rescued_by_alternate_product": int(
                date_mask["date_rescued_by_alternate_product"].sum()
            ),
            "n_dates_with_multiple_passing_products": int(
                date_mask["n_products_passing"].gt(1).sum()
            ),
            **_gap_statistics(date_mask),
        }
        for year in years:
            row[f"usable_dates_{year}"] = int(
                date_mask.loc[date_mask["year"].eq(year), "s2_date_usable"].sum()
            )
        summaries.append(row)

        for year in years:
            products_year = product_qc.loc[product_qc["year"].eq(year)]
            dates_year = date_mask.loc[date_mask["year"].eq(year)]
            usable_dates = dates_year.loc[dates_year["s2_date_usable"], "date"]
            year_rows.append(
                {
                    "rule_id": rule.rule_id,
                    "rule_label": rule.rule_label,
                    "rule_role": rule.role,
                    "year": year,
                    "n_products": int(len(products_year)),
                    "n_products_passing": int(product_pass.loc[products_year.index].sum()),
                    "product_pass_fraction": (
                        float(product_pass.loc[products_year.index].mean())
                        if not products_year.empty
                        else np.nan
                    ),
                    "n_candidate_dates": int(len(dates_year)),
                    "n_usable_dates": int(dates_year["s2_date_usable"].sum()),
                    "date_retention_fraction": (
                        float(dates_year["s2_date_usable"].mean())
                        if not dates_year.empty
                        else np.nan
                    ),
                    "first_usable_date": (
                        usable_dates.min() if not usable_dates.empty else pd.NaT
                    ),
                    "last_usable_date": (
                        usable_dates.max() if not usable_dates.empty else pd.NaT
                    ),
                }
            )

        for month in range(1, 13):
            products_month = product_qc.loc[product_qc["month"].eq(month)]
            dates_month = date_mask.loc[date_mask["date"].dt.month.eq(month)]
            month_rows.append(
                {
                    "rule_id": rule.rule_id,
                    "rule_label": rule.rule_label,
                    "rule_role": rule.role,
                    "calendar_month": month,
                    "n_products": int(len(products_month)),
                    "n_products_passing": int(
                        product_pass.loc[products_month.index].sum()
                    ),
                    "n_candidate_dates": int(len(dates_month)),
                    "n_usable_dates": int(dates_month["s2_date_usable"].sum()),
                    "date_retention_fraction": (
                        float(dates_month["s2_date_usable"].mean())
                        if not dates_month.empty
                        else np.nan
                    ),
                }
            )

    return (
        pd.DataFrame(summaries),
        pd.DataFrame(year_rows),
        pd.DataFrame(month_rows),
        date_masks,
    )


def build_same_day_resolution(
    final_date_mask: pd.DataFrame,
) -> pd.DataFrame:
    """Return provenance and resolution details for multi-product dates only."""

    columns = [
        "date",
        "n_products_on_date",
        "n_products_passing",
        "all_product_ids",
        "product_pass_status",
        "s2_date_usable",
        "selected_product_id",
        "selected_platform",
        "selected_acquisition_datetime",
        "selected_processing_baseline",
        "selected_central_scl",
        "selected_water_fraction_3x3",
        "selected_bad_scl_fraction_3x3",
        "date_rescued_by_alternate_product",
        "qc_rule_id",
        "mask_version",
    ]
    _require_columns(final_date_mask, set(columns), table_name="final date mask")
    return final_date_mask.loc[
        final_date_mask["n_products_on_date"].gt(1), columns
    ].reset_index(drop=True)


def scale_rule_to_window(
    rule: QcRule, *, source_window_size: int, target_window_size: int
) -> QcRule:
    """Scale count cutoffs conservatively by pixel fraction for sensitivity."""

    source_pixels = source_window_size**2
    target_pixels = target_window_size**2
    return replace(
        rule,
        rule_id=f"{rule.rule_id}__{target_window_size}x{target_window_size}",
        maximum_bad_pixels=floor(
            rule.maximum_bad_pixels / source_pixels * target_pixels
        ),
        minimum_water_pixels=ceil(
            rule.minimum_water_pixels / source_pixels * target_pixels
        ),
        maximum_persistent_nonwater_pixels=floor(
            rule.maximum_persistent_nonwater_pixels
            / source_pixels
            * target_pixels
        ),
        maximum_class2_pixels=floor(
            rule.maximum_class2_pixels / source_pixels * target_pixels
        ),
    )


def build_spatial_sensitivity(
    inventory: pd.DataFrame,
    scenes: pd.DataFrame,
    *,
    rules: Sequence[QcRule],
    windows: Sequence[int],
    reference_start: pd.Timestamp,
    reference_end: pd.Timestamp,
    mask_version: str,
) -> pd.DataFrame:
    """Apply fraction-preserving analogues without reopening the ROI decision."""

    rows = []
    for window_size in windows:
        product_qc = build_product_qc(
            inventory,
            scenes,
            window_size=window_size,
            reference_start=reference_start,
            reference_end=reference_end,
        )
        for source_rule in rules:
            rule = scale_rule_to_window(
                source_rule,
                source_window_size=3,
                target_window_size=window_size,
            )
            passes = evaluate_rule(product_qc, rule)
            date_mask = collapse_products_to_dates(
                product_qc, rule, mask_version=mask_version
            )
            rows.append(
                {
                    "source_rule_id_3x3": source_rule.rule_id,
                    "rule_label": source_rule.rule_label,
                    "rule_role": source_rule.role,
                    "window_size": window_size,
                    "window_label": f"{window_size}x{window_size}",
                    "effective_maximum_bad_pixels": rule.maximum_bad_pixels,
                    "effective_minimum_water_pixels": rule.minimum_water_pixels,
                    "effective_center_pixel_rule": rule.center_pixel_rule,
                    "effective_maximum_persistent_nonwater_pixels": rule.maximum_persistent_nonwater_pixels,
                    "effective_maximum_class2_pixels": rule.maximum_class2_pixels,
                    "n_products": len(product_qc),
                    "n_products_passing": int(passes.sum()),
                    "product_pass_fraction": float(passes.mean()),
                    "n_candidate_dates": len(date_mask),
                    "n_usable_dates": int(date_mask["s2_date_usable"].sum()),
                    "date_retention_fraction": float(
                        date_mask["s2_date_usable"].mean()
                    ),
                    **_gap_statistics(date_mask),
                }
            )
    return pd.DataFrame(rows)


def build_stratified_rule_summary(
    product_qc: pd.DataFrame, rules: Sequence[QcRule]
) -> pd.DataFrame:
    """Compare product pass rates by year, platform, and processing baseline."""

    rows = []
    for rule in rules:
        passed = evaluate_rule(product_qc, rule)
        for stratum_type, column in (
            ("year", "year"),
            ("platform", "platform"),
            ("processing_baseline", "processing_baseline"),
        ):
            for value, group in product_qc.groupby(column, sort=True):
                group_pass = passed.loc[group.index]
                rows.append(
                    {
                        "rule_id": rule.rule_id,
                        "rule_label": rule.rule_label,
                        "rule_role": rule.role,
                        "stratum_type": stratum_type,
                        "stratum_value": str(value),
                        "n_products": int(len(group)),
                        "n_products_passing": int(group_pass.sum()),
                        "product_pass_fraction": float(group_pass.mean()),
                    }
                )
    return pd.DataFrame(rows)


def build_input_qc_summary(
    inventory: pd.DataFrame,
    product_qc: pd.DataFrame,
    *,
    reference_start: pd.Timestamp,
    reference_end: pd.Timestamp,
) -> pd.DataFrame:
    """Create a compact audit of primary inputs and retained duplicates."""

    primary = inventory.loc[
        inventory["date"].between(reference_start, reference_end)
    ].copy()
    archive_exact = inventory.duplicated(
        ["acquisition_datetime", "tile_id"], keep=False
    )
    primary_exact = primary.duplicated(
        ["acquisition_datetime", "tile_id"], keep=False
    )
    duplicate_dates = primary.groupby("date").size()
    rows: list[dict[str, Any]] = []

    def add(section: str, metric: str, value: Any, detail: str = "") -> None:
        rows.append(
            {"section": section, "metric": metric, "value": value, "detail": detail}
        )

    add("primary_interval", "reference_start", reference_start.date().isoformat())
    add("primary_interval", "reference_end", reference_end.date().isoformat())
    add("primary_interval", "n_products", len(primary))
    add("primary_interval", "n_unique_calendar_dates", primary["date"].nunique())
    add("primary_interval", "n_dates_with_multiple_products", int(duplicate_dates.gt(1).sum()))
    add("primary_interval", "maximum_products_per_date", int(duplicate_dates.max()))
    add("primary_interval", "n_processing_status_ok_products", int(primary["processing_status"].eq("ok").sum()))
    add("primary_interval", "n_station_inside_raster_products", len(product_qc))
    add("primary_interval", "n_complete_3x3_product_rows", len(product_qc))
    add(
        "exact_datetime_tile_duplicates",
        "archive_duplicate_groups",
        inventory.loc[archive_exact]
        .groupby(["acquisition_datetime", "tile_id"])
        .ngroups,
        "Warning only: all products remain in the inventory.",
    )
    add(
        "exact_datetime_tile_duplicates",
        "archive_products_in_duplicate_groups",
        int(archive_exact.sum()),
    )
    add(
        "exact_datetime_tile_duplicates",
        "primary_duplicate_groups",
        primary.loc[primary_exact]
        .groupby(["acquisition_datetime", "tile_id"])
        .ngroups,
    )
    add(
        "exact_datetime_tile_duplicates",
        "primary_products_in_duplicate_groups",
        int(primary_exact.sum()),
    )
    for column, section in (
        ("processing_status", "primary_processing_status"),
        ("platform", "primary_platform"),
        ("processing_baseline", "primary_processing_baseline"),
    ):
        for value, count in primary[column].value_counts(dropna=False).sort_index().items():
            add(section, str(value), int(count))
    add(
        "scl_consistency",
        "unexpected_scl_values",
        0,
        "Validated before mask construction by the Phase 2A schema checks.",
    )
    add(
        "scl_consistency",
        "class_count_partition_failures",
        0,
        "Every primary 3x3 row has nine classified pixels.",
    )
    return pd.DataFrame(rows)


def _primary_product_qc_output(
    product_qc: pd.DataFrame,
    *,
    final_rule: QcRule,
    mask_version: str,
) -> pd.DataFrame:
    output = product_qc.copy()
    suffix_map = {
        "water_pixel_count": "water_pixel_count_3x3",
        "bad_pixel_count": "bad_pixel_count_3x3",
        "persistent_nonwater_pixel_count": "persistent_nonwater_pixel_count_3x3",
        "class2_pixel_count": "class2_pixel_count_3x3",
        "water_fraction": "water_fraction_3x3",
        "bad_scl_fraction": "bad_scl_fraction_3x3",
        "persistent_nonwater_fraction": "persistent_nonwater_fraction_3x3",
        "class2_fraction": "class2_fraction_3x3",
    }
    output = output.rename(columns=suffix_map)
    output["passes_final_rule"] = evaluate_rule(product_qc, final_rule)
    output["final_rule_failure_reasons"] = rule_failure_reasons(
        product_qc, final_rule
    )
    output["qc_rule_id"] = final_rule.rule_id
    output["mask_version"] = mask_version
    return output[PRIMARY_PRODUCT_QC_COLUMNS]


def build_mask_analysis(
    inventory: pd.DataFrame,
    scenes: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Build every Phase 2A-3 table plus the final one-row-per-date mask."""

    start = config["reference_start"]
    end = config["reference_end"]
    mask_version = str(config["mask_version"])
    final_rule: QcRule = config["final_rule_object"]
    rules: list[QcRule] = list(config["candidate_rule_objects"])
    product_qc = build_product_qc(
        inventory,
        scenes,
        window_size=3,
        reference_start=start,
        reference_end=end,
    )
    sensitivity, years, months, date_masks = summarize_rule_sensitivity(
        product_qc, rules, mask_version=mask_version
    )
    final_mask = date_masks[final_rule.rule_id]
    main_rules = [
        rule
        for rule in rules
        if rule.role in {"strict_sensitivity", "preferred", "relaxed_sensitivity"}
    ]
    spatial_windows = [1, 3, 5]
    tables = {
        "erken_s2_mask_input_qc.csv": build_input_qc_summary(
            inventory,
            product_qc,
            reference_start=start,
            reference_end=end,
        ),
        "erken_s2_scl_product_qc.csv": _primary_product_qc_output(
            product_qc, final_rule=final_rule, mask_version=mask_version
        ),
        "erken_s2_scl_3x3_state_frequency.csv": summarize_state_space(product_qc),
        "erken_s2_scl_qc_rule_sensitivity.csv": sensitivity,
        "erken_s2_scl_qc_rule_year_summary.csv": years,
        "erken_s2_scl_qc_rule_month_summary.csv": months,
        "erken_s2_scl_qc_rule_stratified_summary.csv": build_stratified_rule_summary(
            product_qc, main_rules
        ),
        "erken_s2_same_day_product_resolution.csv": build_same_day_resolution(
            final_mask
        ),
        "erken_s2_scl_spatial_rule_sensitivity.csv": build_spatial_sensitivity(
            inventory,
            scenes,
            rules=main_rules,
            windows=spatial_windows,
            reference_start=start,
            reference_end=end,
            mask_version=mask_version,
        ),
    }
    return tables, final_mask


def _format_dates_for_csv(table: pd.DataFrame) -> pd.DataFrame:
    output = table.copy()
    for column in output.columns:
        if column == "date" or column.endswith("_usable_date"):
            parsed = pd.to_datetime(output[column], errors="coerce")
            output[column] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), "")
    return output


def write_csv_table(table: pd.DataFrame, path: str | Path) -> Path:
    """Write one deterministic portable CSV table."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _format_dates_for_csv(table).to_csv(
        path,
        index=False,
        float_format="%.10g",
        lineterminator="\n",
    )
    return path


def write_mask_outputs(
    tables: Mapping[str, pd.DataFrame],
    final_mask: pd.DataFrame,
    *,
    tables_directory: str | Path,
    mask_path: str | Path,
) -> list[Path]:
    """Write all analysis tables and the final date-level mask."""

    tables_directory = Path(tables_directory)
    outputs = [
        write_csv_table(table, tables_directory / filename)
        for filename, table in tables.items()
    ]
    outputs.append(write_csv_table(final_mask, mask_path))
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
    figure.savefig(pdf, facecolor="white")
    plt.close(figure)
    return [png, pdf]


def generate_mask_figures(
    tables: Mapping[str, pd.DataFrame],
    final_mask: pd.DataFrame,
    output_directory: str | Path,
) -> list[Path]:
    """Generate five SCL-only observation-design diagnostics."""

    output_directory = Path(output_directory)
    sensitivity = tables["erken_s2_scl_qc_rule_sensitivity.csv"]
    years = tables["erken_s2_scl_qc_rule_year_summary.csv"]
    spatial = tables["erken_s2_scl_spatial_rule_sensitivity.csv"]
    colors = plt.get_cmap("tab10").colors
    outputs: list[Path] = []

    with plt.rc_context(_plot_style()):
        plot = sensitivity.iloc[::-1]
        bar_colors = [
            colors[0] if role == "preferred" else "#9ca3af"
            for role in plot["rule_role"]
        ]
        fig, ax = plt.subplots(figsize=(9.2, 5.8), constrained_layout=True)
        bars = ax.barh(plot["rule_label"], plot["n_usable_dates"], color=bar_colors)
        ax.set(
            title="Erken usable calendar dates under pre-specified 3x3 SCL rules",
            xlabel="Unique usable calendar dates",
            ylabel="",
        )
        ax.bar_label(bars, padding=3, fontsize=8)
        ax.text(
            0.99,
            0.01,
            "Blue marks the frozen primary rule; no CHLF information used",
            transform=ax.transAxes,
            ha="right",
            color="#4b5563",
            fontsize=8,
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_11_erken_s2_usable_dates_by_qc_rule"
            )
        )

    with plt.rc_context(_plot_style()):
        main = years.loc[
            years["rule_role"].isin(
                ["strict_sensitivity", "preferred", "relaxed_sensitivity"]
            )
        ]
        fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
        role_colors = {
            "strict_sensitivity": colors[7],
            "preferred": colors[0],
            "relaxed_sensitivity": colors[1],
        }
        role_labels = {
            "strict_sensitivity": "Strict 9/9 water",
            "preferred": "Preferred <=1 bad, >=8 water",
            "relaxed_sensitivity": "Relaxed <=2 bad, >=7 water",
        }
        for role in role_colors:
            group = main.loc[main["rule_role"].eq(role)]
            ax.plot(
                group["year"],
                group["n_usable_dates"],
                marker="o",
                linewidth=1.8,
                color=role_colors[role],
                label=role_labels[role],
            )
        ax.set(
            title="Annual usable Erken Sentinel-2 dates under main SCL rules",
            xlabel="Year",
            ylabel="Unique usable calendar dates",
            xticks=sorted(main["year"].unique()),
        )
        ax.legend(frameon=False, ncol=1)
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_12_erken_s2_annual_usable_dates_by_rule"
            )
        )

    with plt.rc_context(_plot_style()):
        plot = sensitivity.iloc[::-1]
        y = np.arange(len(plot))
        fig, axes = plt.subplots(
            1, 2, figsize=(11.2, 5.8), sharey=True, constrained_layout=True
        )
        axes[0].errorbar(
            plot["median_interval_days"],
            y,
            xerr=np.vstack(
                [
                    plot["median_interval_days"] - plot["q25_interval_days"],
                    plot["q75_interval_days"] - plot["median_interval_days"],
                ]
            ),
            fmt="o",
            color=colors[0],
            capsize=3,
        )
        axes[0].set(
            title="Typical interval (median and IQR)",
            xlabel="Days",
            yticks=y,
            yticklabels=plot["rule_label"],
        )
        axes[1].barh(y, plot["maximum_gap_days"], color="#9ca3af")
        axes[1].set(title="Maximum inter-observation gap", xlabel="Days")
        fig.suptitle("Temporal availability under pre-specified 3x3 SCL rules")
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_13_erken_s2_temporal_gaps_by_qc_rule"
            )
        )

    with plt.rc_context(_plot_style()):
        candidate = final_mask.copy()
        candidate["day_of_year"] = candidate["date"].dt.dayofyear
        fig, ax = plt.subplots(figsize=(10.0, 4.8), constrained_layout=True)
        ax.scatter(
            candidate["day_of_year"],
            candidate["year"],
            color="#d1d5db",
            s=8,
            linewidths=0,
            label="Inventory date rejected by SCL rule",
        )
        usable = candidate.loc[candidate["s2_date_usable"]]
        ax.scatter(
            usable["day_of_year"],
            usable["year"],
            color=colors[0],
            s=13,
            linewidths=0,
            label="Usable unique date",
        )
        month_starts = pd.date_range("2024-01-01", "2024-12-01", freq="MS")
        ax.set_xticks(
            month_starts.dayofyear,
            [date.strftime("%b") for date in month_starts],
        )
        ax.set(
            title="Erken Sentinel-2 observation calendar under the frozen SCL rule",
            xlabel="Calendar month",
            ylabel="Year",
            yticks=sorted(candidate["year"].unique()),
            xlim=(1, 366),
        )
        ax.legend(
            frameon=False,
            ncol=1,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_14_erken_s2_observation_calendar"
            )
        )

    with plt.rc_context(_plot_style()):
        roles = ["strict_sensitivity", "preferred", "relaxed_sensitivity"]
        role_labels = ["Strict", "Preferred", "Relaxed"]
        windows = [1, 3, 5]
        x = np.arange(len(windows))
        width = 0.24
        fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
        for index, (role, label) in enumerate(zip(roles, role_labels, strict=True)):
            group = spatial.loc[spatial["rule_role"].eq(role)].set_index(
                "window_size"
            ).reindex(windows)
            bars = ax.bar(
                x + (index - 1) * width,
                group["n_usable_dates"],
                width,
                label=label,
                color=colors[[7, 0, 1][index]],
            )
            ax.bar_label(bars, padding=2, fontsize=8)
        ax.set(
            title="Spatial sensitivity of SCL-only usable-date counts",
            xlabel="Station-centred SCL window",
            ylabel="Unique usable calendar dates",
            xticks=x,
            xticklabels=[f"{window}x{window}" for window in windows],
        )
        ax.legend(
            frameon=False,
            ncol=1,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
        )
        outputs.extend(
            _save_figure(
                fig, output_directory, "figure_15_erken_s2_spatial_rule_sensitivity"
            )
        )
    return outputs
