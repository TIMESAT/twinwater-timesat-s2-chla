"""Erken-only reliability synthesis from immutable saved reconstruction results.

The estimators in this module always reduce scenarios within calendar year
before giving years equal weight.  Uncertainty is obtained by resampling whole
years, so methods and masks remain paired inside every sampled year block.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import canonical_json_payload_sha256, sha256_file
from twinwater_timesat.phase3_preflight import write_deterministic_csv, write_deterministic_json


ANALYSIS_VERSION = "Erken_Reliability_Synthesis_v1.0"
STARTING_COMMIT = "53d29783da2dc2899aa9012c40a3744718e2fd84"
CONFIG_PATH = "config/erken_reliability_synthesis_v1.0.json"
OUTPUT_DIRECTORY = "results/reliability_synthesis/v1.0"
BOOTSTRAP_SEED = 20260918
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_ALPHA = 0.05
PRIMARY_YEARS = tuple(range(2019, 2026))

PRIMARY_METHODS = (
    "linear_interpolation",
    "timesat_double_logistic",
    "timesat_smoothing_spline",
)
METHOD_PAIRS = (
    ("linear_interpolation", "timesat_double_logistic"),
    ("linear_interpolation", "timesat_smoothing_spline"),
    ("timesat_smoothing_spline", "timesat_double_logistic"),
)
CV_DEFAULT_METHOD = "timesat_double_logistic_default_seapar1"
CV_METHOD = "timesat_double_logistic_cv_seapar"

METHOD_LABELS = {
    "linear_interpolation": "Linear interpolation",
    "timesat_double_logistic": "TIMESAT double logistic (default)",
    "timesat_smoothing_spline": "TIMESAT smoothing spline",
    CV_DEFAULT_METHOD: "TIMESAT double logistic (default)",
    CV_METHOD: "TIMESAT double logistic (CV p_seapar)",
}
METHOD_COLORS = {
    "linear_interpolation": "#0072B2",
    "timesat_double_logistic": "#D55E00",
    "timesat_smoothing_spline": "#009E73",
    CV_DEFAULT_METHOD: "#D55E00",
    CV_METHOD: "#7A3DC8",
}

INPUT_PATHS = (
    "results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv",
    "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_metrics.csv",
    "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_year_method_summary.csv",
    "results/phase4/synthesis/erken_phase_d_random_deletion_analysis_ready.csv",
    "results/phase4/synthesis/erken_phase_d_consecutive_gap_analysis_ready.csv",
    "results/phase5/synthesis/erken_phase5_actual_mask_year_method.csv",
    "results/phase5/synthesis/erken_phase5_random_year_method_deletion_summary.csv",
    "results/phase5/synthesis/erken_phase5_consecutive_year_method_duration_summary.csv",
)


@dataclass(frozen=True)
class MetricSpec:
    column: str
    label: str
    unit: str
    favorable_direction: str
    binary_peak_success: bool = False


CORE_METRICS = (
    MetricSpec("mae", "point-wise MAE", "ug_L", "lower"),
    MetricSpec("rmse", "point-wise RMSE", "ug_L", "lower"),
    MetricSpec("nrmse", "point-wise nRMSE", "fraction_Q95_minus_Q05", "lower"),
    MetricSpec("absolute_peak_date_error_days", "absolute global-peak date error", "days", "lower"),
    MetricSpec("peak_timing_success_5d", "global-peak timing success <=5 d", "fraction", "higher", True),
    MetricSpec("peak_timing_success_10d", "global-peak timing success <=10 d", "fraction", "higher", True),
    MetricSpec("peak_timing_success_15d", "global-peak timing success <=15 d", "fraction", "higher", True),
    MetricSpec("absolute_peak_magnitude_error", "absolute global-peak magnitude error", "ug_L", "lower"),
    MetricSpec(
        "normalized_absolute_peak_magnitude_error",
        "normalized absolute global-peak magnitude error",
        "fraction_Q95_minus_Q05",
        "lower",
    ),
    MetricSpec("absolute_integral_error", "absolute common-support integral error", "ug_day_L", "lower"),
    MetricSpec("absolute_relative_integral_error", "absolute relative common-support integral error", "fraction", "lower"),
    MetricSpec("pearson_correlation", "daily trajectory Pearson correlation", "correlation", "higher"),
)

CONTROLLED_METRICS = tuple(
    spec
    for spec in CORE_METRICS
    if spec.column
    in {
        "rmse",
        "nrmse",
        "absolute_peak_date_error_days",
        "peak_timing_success_5d",
        "peak_timing_success_10d",
        "peak_timing_success_15d",
        "normalized_absolute_peak_magnitude_error",
        "absolute_integral_error",
        "absolute_relative_integral_error",
        "pearson_correlation",
    }
)

EVENT_METRICS = (
    MetricSpec("recovery_fraction_5d", "major-event recovery <=5 d", "fraction", "higher"),
    MetricSpec("recovery_fraction_10d", "major-event recovery <=10 d", "fraction", "higher"),
    MetricSpec("recovery_fraction_15d", "major-event recovery <=15 d", "fraction", "higher"),
    MetricSpec("mean_absolute_timing_error_matched_days", "matched-event absolute timing error", "days", "lower"),
    MetricSpec(
        "mean_normalized_absolute_magnitude_error_matched",
        "matched-event normalized absolute magnitude error",
        "fraction_Q95_minus_Q05",
        "lower",
    ),
)


def _read_csv(root: Path, relative: str) -> pd.DataFrame:
    return pd.read_csv(root / relative, low_memory=False)


def _as_bool(values: pd.Series) -> pd.Series:
    """Return pandas nullable booleans without turning missing values into True."""

    if str(values.dtype) in {"bool", "boolean"}:
        return values.astype("boolean")
    lowered = values.astype("string").str.lower()
    mapped = lowered.map({"true": True, "false": False, "1": True, "0": False})
    return mapped.astype("boolean")


def _prepare_metrics(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    if "relative_integral_error" in output:
        output["absolute_relative_integral_error"] = pd.to_numeric(
            output["relative_integral_error"], errors="coerce"
        ).abs()
    for days in (5, 10, 15):
        column = f"peak_timing_success_{days}d"
        if column in output:
            output[column] = _as_bool(output[column])
    return output


def _peak_reference_eligible(group: pd.DataFrame) -> pd.Series:
    status = group.get("reference_peak_status", pd.Series("ok", index=group.index))
    boundary = _as_bool(
        group.get("reference_peak_at_boundary", pd.Series(False, index=group.index))
    ).fillna(False)
    return status.eq("ok") & ~boundary.astype(bool)


def _metric_vector(group: pd.DataFrame, spec: MetricSpec) -> tuple[pd.Series, int]:
    """Return estimand values and the number of reference-ineligible rows.

    For an eligible peak-timing case, a failed or missing reconstructed peak is
    explicitly a non-success.  Continuous errors are never imputed.
    """

    if spec.binary_peak_success:
        eligible = _peak_reference_eligible(group)
        values = pd.Series(np.nan, index=group.index, dtype=float)
        observed = _as_bool(group[spec.column])
        values.loc[eligible] = observed.loc[eligible].fillna(False).astype(float)
        return values, int((~eligible).sum())
    return pd.to_numeric(group[spec.column], errors="coerce"), 0


def _stable_seed(key: str) -> int:
    digest = hashlib.sha256(f"{BOOTSTRAP_SEED}|{key}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**63 - 1)


def cluster_bootstrap_mean_ci(values: Iterable[float], *, key: str) -> tuple[float, float, float, int]:
    """Percentile interval after resampling the supplied year-level values."""

    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    n_years = int(array.size)
    if n_years == 0:
        return np.nan, np.nan, np.nan, 0
    estimate = float(np.mean(array))
    rng = np.random.default_rng(_stable_seed(key))
    draws = rng.integers(0, n_years, size=(BOOTSTRAP_REPLICATES, n_years))
    replicates = array[draws].mean(axis=1)
    low, high = np.quantile(
        replicates,
        [BOOTSTRAP_ALPHA / 2, 1 - BOOTSTRAP_ALPHA / 2],
        method="linear",
    )
    return estimate, float(low), float(high), n_years


def _assign_tertiles(
    data: pd.DataFrame,
    *,
    value_column: str,
    group_columns: Sequence[str],
    output_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign deterministic low/medium/high classes and return cut metadata."""

    output = data.copy()
    output[output_column] = pd.Series(pd.NA, index=output.index, dtype="string")
    thresholds: list[dict[str, Any]] = []
    if not group_columns:
        grouped: Iterable[tuple[tuple[Any, ...], pd.DataFrame]] = [((), output)]
    else:
        group_arg: str | list[str] = list(group_columns)
        if len(group_columns) == 1:
            group_arg = group_columns[0]
        grouped = (
            (keys if isinstance(keys, tuple) else (keys,), group)
            for keys, group in output.groupby(group_arg, sort=True, dropna=False)
        )
    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = pd.to_numeric(group[value_column], errors="coerce")
        finite = values[np.isfinite(values)]
        if finite.empty:
            q1 = q2 = np.nan
        else:
            q1, q2 = np.quantile(finite, [1 / 3, 2 / 3], method="linear")
            labels = np.select(
                [values <= q1, values <= q2, values > q2],
                ["low", "medium", "high"],
                default=None,
            )
            output.loc[group.index, output_column] = pd.Series(
                labels, index=group.index, dtype="string"
            )
        row = dict(zip(group_columns, keys, strict=True))
        row.update(
            {
                "stratification_variable": value_column,
                "lower_tertile_cut": float(q1),
                "upper_tertile_cut": float(q2),
                "observed_minimum": float(finite.min()) if not finite.empty else np.nan,
                "observed_maximum": float(finite.max()) if not finite.empty else np.nan,
                "n_unique_scenarios": int(len(group)),
            }
        )
        thresholds.append(row)
    return output, pd.DataFrame(thresholds)


def _scenario_year_summary(
    data: pd.DataFrame,
    *,
    strata: Sequence[str],
    metrics: Sequence[MetricSpec],
    coverage_columns: Sequence[str],
) -> pd.DataFrame:
    """First-stage scenario aggregation within year and method."""

    rows: list[dict[str, Any]] = []
    group_columns = ["year", "method", *strata]
    for keys, group in data.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row: dict[str, Any] = dict(zip(group_columns, keys, strict=True))
        row["n_scenarios"] = int(len(group))
        row["n_reconstruction_failures"] = int(
            group["reconstruction_status"].ne("ok").sum()
        )
        row["n_scenarios_with_negative_values"] = int(
            pd.to_numeric(group["n_negative_reconstructed_days"], errors="coerce")
            .fillna(0)
            .gt(0)
            .sum()
        )
        for column in coverage_columns:
            values = pd.to_numeric(group[column], errors="coerce")
            row[f"{column}_minimum"] = float(values.min())
            row[f"{column}_maximum"] = float(values.max())
        for spec in metrics:
            values, n_reference_ineligible = _metric_vector(group, spec)
            available = values[np.isfinite(values)]
            row[spec.column] = float(available.mean()) if not available.empty else np.nan
            row[f"n_{spec.column}_available"] = int(len(available))
            row[f"n_{spec.column}_unavailable"] = int(len(group) - len(available))
            if spec.binary_peak_success:
                row[f"n_{spec.column}_reference_ineligible"] = n_reference_ineligible
        rows.append(row)
    return pd.DataFrame(rows).sort_values(group_columns, kind="mergesort").reset_index(drop=True)


def _equal_year_summary(
    year_data: pd.DataFrame,
    *,
    strata: Sequence[str],
    metrics: Sequence[MetricSpec],
    coverage_columns: Sequence[str],
    key_prefix: str,
    analysis_role: str,
) -> pd.DataFrame:
    """Second-stage equal-year means with whole-year bootstrap intervals."""

    rows: list[dict[str, Any]] = []
    group_columns = ["method", *strata]
    for keys, group in year_data.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        identity = dict(zip(group_columns, keys, strict=True))
        key_bits = "|".join(f"{column}={identity[column]}" for column in group_columns)
        for spec in metrics:
            estimate, low, high, n_years = cluster_bootstrap_mean_ci(
                group[spec.column], key=f"{key_prefix}|{key_bits}|{spec.column}"
            )
            row = dict(identity)
            row.update(
                {
                    "analysis_role": analysis_role,
                    "metric": spec.column,
                    "metric_label": spec.label,
                    "unit": spec.unit,
                    "favorable_direction": spec.favorable_direction,
                    "equal_year_estimate": estimate,
                    "cluster_bootstrap_ci_lower": low,
                    "cluster_bootstrap_ci_upper": high,
                    "n_years_in_stratum": int(group["year"].nunique()),
                    "n_years_metric_available": n_years,
                    "n_scenarios_total": int(group["n_scenarios"].sum()),
                    "n_reconstruction_failures_total": int(
                        group["n_reconstruction_failures"].sum()
                    ),
                    "n_metric_available_total": int(
                        group[f"n_{spec.column}_available"].sum()
                    ),
                    "n_metric_unavailable_total": int(
                        group[f"n_{spec.column}_unavailable"].sum()
                    ),
                }
            )
            for column in coverage_columns:
                row[f"{column}_observed_minimum"] = float(
                    group[f"{column}_minimum"].min()
                )
                row[f"{column}_observed_maximum"] = float(
                    group[f"{column}_maximum"].max()
                )
            rows.append(row)
    sort_columns = [*group_columns, "metric"]
    return pd.DataFrame(rows).sort_values(sort_columns, kind="mergesort").reset_index(drop=True)


def _paired_year_differences(
    year_data: pd.DataFrame,
    *,
    strata: Sequence[str],
    metrics: Sequence[MetricSpec],
    method_pairs: Sequence[tuple[str, str]],
) -> pd.DataFrame:
    """Paired method contrasts; positive advantage always favors method A."""

    rows: list[dict[str, Any]] = []
    keys = ["year", *strata]
    for method_a, method_b in method_pairs:
        left = year_data.loc[year_data["method"].eq(method_a), [*keys, *[m.column for m in metrics]]]
        right = year_data.loc[year_data["method"].eq(method_b), [*keys, *[m.column for m in metrics]]]
        merged = left.merge(right, on=keys, suffixes=("_a", "_b"), validate="one_to_one")
        for _, record in merged.iterrows():
            base = {column: record[column] for column in keys}
            for spec in metrics:
                a = float(record[f"{spec.column}_a"])
                b = float(record[f"{spec.column}_b"])
                raw = a - b
                advantage = raw if spec.favorable_direction == "higher" else -raw
                rows.append(
                    {
                        **base,
                        "method_a": method_a,
                        "method_b": method_b,
                        "metric": spec.column,
                        "metric_label": spec.label,
                        "unit": spec.unit,
                        "favorable_direction": spec.favorable_direction,
                        "method_a_value": a,
                        "method_b_value": b,
                        "raw_difference_a_minus_b": raw,
                        "advantage_for_method_a": advantage,
                    }
                )
    sort_columns = [*strata, "method_a", "method_b", "metric", "year"]
    return pd.DataFrame(rows).sort_values(sort_columns, kind="mergesort").reset_index(drop=True)


def _paired_summary(
    paired_year: pd.DataFrame,
    *,
    strata: Sequence[str],
    key_prefix: str,
    analysis_role: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_columns = [*strata, "method_a", "method_b", "metric"]
    for keys, group in paired_year.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        identity = dict(zip(group_columns, keys, strict=True))
        key_bits = "|".join(f"{column}={identity[column]}" for column in group_columns)
        raw_estimate, raw_low, raw_high, n_years = cluster_bootstrap_mean_ci(
            group["raw_difference_a_minus_b"], key=f"{key_prefix}|raw|{key_bits}"
        )
        advantage, advantage_low, advantage_high, _ = cluster_bootstrap_mean_ci(
            group["advantage_for_method_a"], key=f"{key_prefix}|advantage|{key_bits}"
        )
        row = dict(identity)
        first = group.iloc[0]
        row.update(
            {
                "analysis_role": analysis_role,
                "metric_label": first["metric_label"],
                "unit": first["unit"],
                "favorable_direction": first["favorable_direction"],
                "mean_raw_difference_a_minus_b": raw_estimate,
                "raw_difference_ci_lower": raw_low,
                "raw_difference_ci_upper": raw_high,
                "mean_advantage_for_method_a": advantage,
                "advantage_ci_lower": advantage_low,
                "advantage_ci_upper": advantage_high,
                "n_paired_years": n_years,
                "n_years_method_a_favored": int(group["advantage_for_method_a"].gt(0).sum()),
                "n_years_method_b_favored": int(group["advantage_for_method_a"].lt(0).sum()),
                "n_year_ties": int(group["advantage_for_method_a"].eq(0).sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(group_columns, kind="mergesort").reset_index(drop=True)


def _actual_year_table(actual: pd.DataFrame) -> pd.DataFrame:
    actual = _prepare_metrics(actual)
    if set(actual["method"].unique()) != set(PRIMARY_METHODS):
        raise ValueError("Primary actual-mask method set differs from the frozen contract.")
    if tuple(sorted(actual["year"].unique())) != PRIMARY_YEARS:
        raise ValueError("Primary actual-mask years differ from 2019-2025.")
    keep = [
        "year",
        "method",
        "reconstruction_status",
        "reconstruction_failure_reason",
        "first_sparse_input_date",
        "last_sparse_input_date",
        "diagnostic_n_sparse_inputs",
        "n_pointwise_evaluation_dates",
        "n_common_support_dates",
        "q95_minus_q05",
        "reference_peak_time",
        "reconstruction_peak_time",
        "signed_peak_date_error_days",
        "reference_peak_at_boundary",
        "peak_timing_metric_status",
        "n_negative_reconstructed_days",
        "selected_smoothing",
        *[spec.column for spec in CORE_METRICS],
    ]
    output = actual.loc[:, list(dict.fromkeys(keep))].copy()
    output["calendar_coverage_status"] = np.where(
        output["year"].isin([2019, 2025]),
        "boundary_truncated_common_support",
        "complete_calendar_year_source_coverage",
    )
    output["analysis_role"] = "primary_actual_mask"
    return output.sort_values(["year", "method"], kind="mergesort").reset_index(drop=True)


def _actual_as_year_summary(actual_year: pd.DataFrame) -> pd.DataFrame:
    """Add the denominator fields expected by the generic year-first summarizer."""

    output = actual_year.copy()
    output["n_scenarios"] = 1
    output["n_reconstruction_failures"] = output["reconstruction_status"].ne("ok").astype(int)
    output["n_scenarios_with_negative_values"] = output["n_negative_reconstructed_days"].gt(0).astype(int)
    for spec in CORE_METRICS:
        values, n_reference_ineligible = _metric_vector(output, spec)
        output[spec.column] = values
        output[f"n_{spec.column}_available"] = values.notna().astype(int)
        output[f"n_{spec.column}_unavailable"] = values.isna().astype(int)
        if spec.binary_peak_success:
            output[f"n_{spec.column}_reference_ineligible"] = n_reference_ineligible
    return output


def _leave_one_year_out_tables(
    actual_year_summary: pd.DataFrame,
    paired_year: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    method_rows: list[dict[str, Any]] = []
    for omitted in PRIMARY_YEARS:
        retained = actual_year_summary.loc[actual_year_summary["year"].ne(omitted)]
        for method, group in retained.groupby("method", sort=True):
            for spec in CORE_METRICS:
                values = pd.to_numeric(group[spec.column], errors="coerce")
                method_rows.append(
                    {
                        "omitted_year": omitted,
                        "method": method,
                        "metric": spec.column,
                        "metric_label": spec.label,
                        "unit": spec.unit,
                        "favorable_direction": spec.favorable_direction,
                        "equal_year_estimate_after_omission": float(values.mean()),
                        "n_years_retained": int(values.notna().sum()),
                    }
                )
    method_table = pd.DataFrame(method_rows).sort_values(
        ["method", "metric", "omitted_year"], kind="mergesort"
    )

    pair_rows: list[dict[str, Any]] = []
    for omitted in PRIMARY_YEARS:
        retained = paired_year.loc[paired_year["year"].ne(omitted)]
        for keys, group in retained.groupby(["method_a", "method_b", "metric"], sort=True):
            pair_rows.append(
                {
                    "omitted_year": omitted,
                    "method_a": keys[0],
                    "method_b": keys[1],
                    "metric": keys[2],
                    "metric_label": group.iloc[0]["metric_label"],
                    "unit": group.iloc[0]["unit"],
                    "favorable_direction": group.iloc[0]["favorable_direction"],
                    "mean_advantage_for_method_a_after_omission": float(
                        group["advantage_for_method_a"].mean()
                    ),
                    "n_paired_years_retained": int(
                        group["advantage_for_method_a"].notna().sum()
                    ),
                }
            )
    pair_table = pd.DataFrame(pair_rows).sort_values(
        ["method_a", "method_b", "metric", "omitted_year"], kind="mergesort"
    )

    stability_rows: list[dict[str, Any]] = []
    full_groups = paired_year.groupby(["method_a", "method_b", "metric"], sort=True)
    for keys, full in full_groups:
        subset = pair_table.loc[
            pair_table["method_a"].eq(keys[0])
            & pair_table["method_b"].eq(keys[1])
            & pair_table["metric"].eq(keys[2])
        ]
        full_advantage = float(full["advantage_for_method_a"].mean())
        loo = subset["mean_advantage_for_method_a_after_omission"]
        full_sign = np.sign(full_advantage)
        same_sign = bool((np.sign(loo) == full_sign).all()) if full_sign != 0 else bool((loo == 0).all())
        stability_rows.append(
            {
                "method_a": keys[0],
                "method_b": keys[1],
                "metric": keys[2],
                "metric_label": full.iloc[0]["metric_label"],
                "unit": full.iloc[0]["unit"],
                "favorable_direction": full.iloc[0]["favorable_direction"],
                "full_equal_year_mean_advantage_for_method_a": full_advantage,
                "minimum_loo_advantage_for_method_a": float(loo.min()),
                "maximum_loo_advantage_for_method_a": float(loo.max()),
                "n_loo_method_a_favored": int(loo.gt(0).sum()),
                "n_loo_method_b_favored": int(loo.lt(0).sum()),
                "n_loo_ties": int(loo.eq(0).sum()),
                "all_leave_one_year_out_estimates_keep_full_direction": same_sign,
            }
        )
    stability = pd.DataFrame(stability_rows).sort_values(
        ["method_a", "method_b", "metric"], kind="mergesort"
    )
    return method_table.reset_index(drop=True), pair_table.reset_index(drop=True), stability.reset_index(drop=True)


def _event_tables(event_year: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_year = event_year.copy()
    event_year["analysis_role"] = "secondary_exploratory_event_recovery"
    rows: list[dict[str, Any]] = []
    for method, group in event_year.groupby("method", sort=True):
        for spec in EVENT_METRICS:
            estimate, low, high, n_years = cluster_bootstrap_mean_ci(
                pd.to_numeric(group[spec.column], errors="coerce"),
                key=f"event|{method}|{spec.column}",
            )
            rows.append(
                {
                    "method": method,
                    "analysis_role": "secondary_exploratory_event_recovery",
                    "metric": spec.column,
                    "metric_label": spec.label,
                    "unit": spec.unit,
                    "favorable_direction": spec.favorable_direction,
                    "equal_year_estimate": estimate,
                    "cluster_bootstrap_ci_lower": low,
                    "cluster_bootstrap_ci_upper": high,
                    "n_years_metric_available": n_years,
                    "n_reference_events_total": int(group["n_reference_events"].sum()),
                    "n_available_reference_events_total": int(
                        group["n_available_reference_events"].sum()
                    ),
                    "n_matched_events_total": int(group["n_matched_events"].sum()),
                    "n_missed_events_total": int(group["n_missed_events"].sum()),
                    "n_unavailable_events_total": int(group["n_unavailable_events"].sum()),
                    "n_method_failures_total": int(group["n_method_failures"].sum()),
                    "n_success_5d_total": int(
                        np.rint(
                            (
                                group["recovery_fraction_5d"]
                                * group["n_available_reference_events"]
                            ).sum()
                        )
                    ),
                    "n_success_10d_total": int(
                        np.rint(
                            (
                                group["recovery_fraction_10d"]
                                * group["n_available_reference_events"]
                            ).sum()
                        )
                    ),
                    "n_success_15d_total": int(
                        np.rint(
                            (
                                group["recovery_fraction_15d"]
                                * group["n_available_reference_events"]
                            ).sum()
                        )
                    ),
                }
            )
    summary = pd.DataFrame(rows).sort_values(["method", "metric"], kind="mergesort")
    return event_year.sort_values(["year", "method"], kind="mergesort"), summary.reset_index(drop=True)


def _continuous_associations(
    data: pd.DataFrame,
    *,
    family: str,
    group_columns: Sequence[str],
    covariates: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcomes = ("nrmse", "absolute_peak_date_error_days", "peak_timing_success_10d")
    rows: list[dict[str, Any]] = []
    for keys, group in data.groupby(["year", "method", *group_columns], sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        identity = dict(zip(["year", "method", *group_columns], keys, strict=True))
        for covariate in covariates:
            x = pd.to_numeric(group[covariate], errors="coerce")
            for outcome in outcomes:
                y = _as_bool(group[outcome]).astype(float) if outcome.startswith("peak_timing_success") else pd.to_numeric(group[outcome], errors="coerce")
                valid = x.notna() & y.notna()
                correlation = (
                    float(x.loc[valid].corr(y.loc[valid], method="spearman"))
                    if valid.sum() >= 3 and x.loc[valid].nunique() > 1 and y.loc[valid].nunique() > 1
                    else np.nan
                )
                rows.append(
                    {
                        **identity,
                        "scenario_family": family,
                        "covariate": covariate,
                        "outcome": outcome,
                        "association": "within_year_spearman",
                        "spearman_correlation": correlation,
                        "n_scenarios_available": int(valid.sum()),
                        "covariate_minimum": float(x.loc[valid].min()) if valid.any() else np.nan,
                        "covariate_maximum": float(x.loc[valid].max()) if valid.any() else np.nan,
                    }
                )
    year_table = pd.DataFrame(rows)
    equal_rows: list[dict[str, Any]] = []
    summary_groups = ["method", *group_columns, "covariate", "outcome"]
    for keys, group in year_table.groupby(summary_groups, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        identity = dict(zip(summary_groups, keys, strict=True))
        key_bits = "|".join(f"{column}={identity[column]}" for column in summary_groups)
        estimate, low, high, n_years = cluster_bootstrap_mean_ci(
            group["spearman_correlation"], key=f"association|{family}|{key_bits}"
        )
        equal_rows.append(
            {
                **identity,
                "scenario_family": family,
                "equal_year_mean_spearman": estimate,
                "cluster_bootstrap_ci_lower": low,
                "cluster_bootstrap_ci_upper": high,
                "n_years_metric_available": n_years,
                "n_scenarios_available_total": int(group["n_scenarios_available"].sum()),
                "covariate_observed_minimum": float(group["covariate_minimum"].min()),
                "covariate_observed_maximum": float(group["covariate_maximum"].max()),
            }
        )
    return (
        year_table.sort_values(["method", *group_columns, "covariate", "outcome", "year"], kind="mergesort").reset_index(drop=True),
        pd.DataFrame(equal_rows).sort_values(summary_groups, kind="mergesort").reset_index(drop=True),
    )


def _cv_actual_tables(cv_actual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cv_actual = _prepare_metrics(cv_actual)
    selected = cv_actual.loc[cv_actual["method"].isin([CV_DEFAULT_METHOD, CV_METHOD])].copy()
    selected["analysis_role"] = "secondary_double_logistic_parameter_sensitivity"
    selected["n_scenarios"] = 1
    selected["n_reconstruction_failures"] = selected["reconstruction_status"].ne("ok").astype(int)
    selected["n_scenarios_with_negative_values"] = selected["n_negative_reconstructed_days"].gt(0).astype(int)
    sensitivity_metrics = (
        *CORE_METRICS,
        MetricSpec("recovery_fraction_10d", "major-event recovery <=10 d", "fraction", "higher"),
    )
    for spec in sensitivity_metrics:
        values = (
            pd.to_numeric(selected[spec.column], errors="coerce")
            if spec.column == "recovery_fraction_10d"
            else _metric_vector(selected, spec)[0]
        )
        selected[spec.column] = values
        selected[f"n_{spec.column}_available"] = values.notna().astype(int)
        selected[f"n_{spec.column}_unavailable"] = values.isna().astype(int)
    summary = _equal_year_summary(
        selected,
        strata=(),
        metrics=sensitivity_metrics,
        coverage_columns=(),
        key_prefix="cv_actual",
        analysis_role="secondary_double_logistic_parameter_sensitivity",
    )
    paired_year = _paired_year_differences(
        selected,
        strata=(),
        metrics=sensitivity_metrics,
        method_pairs=((CV_METHOD, CV_DEFAULT_METHOD),),
    )
    paired = _paired_summary(
        paired_year,
        strata=(),
        key_prefix="cv_actual_pair",
        analysis_role="secondary_double_logistic_parameter_sensitivity",
    )
    keep = [
        "year",
        "method",
        "analysis_role",
        "selected_p_seapar",
        "reconstruction_status",
        *[spec.column for spec in sensitivity_metrics],
    ]
    return (
        selected.loc[:, list(dict.fromkeys(keep))].sort_values(["year", "method"], kind="mergesort").reset_index(drop=True),
        summary,
        paired,
    )


def _cv_controlled_summary(random: pd.DataFrame, consecutive: pd.DataFrame) -> pd.DataFrame:
    specs = (
        ("mean_nrmse", "point-wise nRMSE", "fraction_Q95_minus_Q05", "lower"),
        ("mean_absolute_global_peak_timing_error_days", "absolute global-peak date error", "days", "lower"),
        ("global_peak_success_fraction_10d", "global-peak timing success <=10 d", "fraction", "higher"),
        ("mean_absolute_integral_error", "absolute common-support integral error", "ug_day_L", "lower"),
        ("mean_pearson_correlation", "daily trajectory Pearson correlation", "correlation", "higher"),
        ("mean_event_recovery_fraction_10d", "major-event recovery <=10 d", "fraction", "higher"),
    )
    frames = []
    for family, table, level_column in (
        ("random_deletion", random, "deletion_fraction"),
        ("consecutive_internal_gap", consecutive, "duration_days"),
    ):
        subset = table.loc[table["method"].isin([CV_DEFAULT_METHOD, CV_METHOD])].copy()
        subset["scenario_family"] = family
        subset["level_name"] = level_column
        subset["level_value"] = subset[level_column]
        frames.append(subset)
    combined = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, Any]] = []
    for keys, group in combined.groupby(
        ["scenario_family", "level_name", "level_value", "method"], sort=True
    ):
        family, level_name, level_value, method = keys
        for column, label, unit, direction in specs:
            estimate, low, high, n_years = cluster_bootstrap_mean_ci(
                group[column],
                key=f"cv_controlled|{family}|{level_value}|{method}|{column}",
            )
            rows.append(
                {
                    "scenario_family": family,
                    "level_name": level_name,
                    "level_value": level_value,
                    "method": method,
                    "analysis_role": "secondary_double_logistic_parameter_sensitivity",
                    "metric": column,
                    "metric_label": label,
                    "unit": unit,
                    "favorable_direction": direction,
                    "equal_year_estimate": estimate,
                    "cluster_bootstrap_ci_lower": low,
                    "cluster_bootstrap_ci_upper": high,
                    "n_years_metric_available": n_years,
                    "n_scenarios_total": int(group["n_scenarios"].sum()),
                    "n_reconstruction_failures_total": int(
                        group["n_reconstruction_failures"].sum()
                    ),
                }
            )
    summary = pd.DataFrame(rows)

    paired_rows: list[dict[str, Any]] = []
    for keys, group in combined.groupby(
        ["scenario_family", "level_name", "level_value"], sort=True
    ):
        family, level_name, level_value = keys
        default = group.loc[group["method"].eq(CV_DEFAULT_METHOD)].set_index("year")
        cv = group.loc[group["method"].eq(CV_METHOD)].set_index("year")
        years = default.index.intersection(cv.index)
        for column, label, unit, direction in specs:
            raw = cv.loc[years, column].astype(float) - default.loc[years, column].astype(float)
            advantage = raw if direction == "higher" else -raw
            estimate, low, high, n_years = cluster_bootstrap_mean_ci(
                advantage,
                key=f"cv_controlled_pair|{family}|{level_value}|{column}",
            )
            paired_rows.append(
                {
                    "scenario_family": family,
                    "level_name": level_name,
                    "level_value": level_value,
                    "method": "cv_minus_default_paired_advantage",
                    "analysis_role": "secondary_double_logistic_parameter_sensitivity",
                    "metric": column,
                    "metric_label": label,
                    "unit": unit,
                    "favorable_direction": direction,
                    "equal_year_estimate": estimate,
                    "cluster_bootstrap_ci_lower": low,
                    "cluster_bootstrap_ci_upper": high,
                    "n_years_metric_available": n_years,
                    "n_scenarios_total": int(group.loc[group["method"].eq(CV_METHOD), "n_scenarios"].sum()),
                    "n_reconstruction_failures_total": int(
                        group.loc[group["method"].eq(CV_METHOD), "n_reconstruction_failures"].sum()
                    ),
                }
            )
    return pd.concat([summary, pd.DataFrame(paired_rows)], ignore_index=True).sort_values(
        ["scenario_family", "level_value", "method", "metric"], kind="mergesort"
    ).reset_index(drop=True)


def _denominator_audit(
    actual: pd.DataFrame,
    random: pd.DataFrame,
    consecutive: pd.DataFrame,
    event_metrics: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family, data in (
        ("actual_mask", actual),
        ("random_deletion", random),
        ("consecutive_internal_gap", consecutive),
    ):
        for method, group in data.groupby("method", sort=True):
            for spec in CORE_METRICS:
                values, n_reference_ineligible = _metric_vector(group, spec)
                rows.append(
                    {
                        "scenario_family": family,
                        "analysis_role": "primary",
                        "method": method,
                        "metric": spec.column,
                        "n_rows_or_reference_events": int(len(group)),
                        "n_reconstruction_failures": int(
                            group["reconstruction_status"].ne("ok").sum()
                        ),
                        "n_metric_available": int(values.notna().sum()),
                        "n_metric_unavailable": int(values.isna().sum()),
                        "n_reference_ineligible": n_reference_ineligible,
                        "missing_policy": (
                            "eligible failure/missing peak counts as non-success"
                            if spec.binary_peak_success
                            else "continuous metric unavailable; no imputation"
                        ),
                    }
                )
    for method, group in event_metrics.groupby("method", sort=True):
        rows.append(
            {
                "scenario_family": "actual_mask_event_recovery",
                "analysis_role": "secondary_exploratory_event_recovery",
                "method": method,
                "metric": "event_recovery_10d",
                "n_rows_or_reference_events": int(len(group)),
                "n_reconstruction_failures": int(
                    group["reconstruction_status"].ne("ok").sum()
                ),
                "n_metric_available": int(group["event_status"].ne("unavailable").sum()),
                "n_metric_unavailable": int(group["event_status"].eq("unavailable").sum()),
                "n_reference_ineligible": 0,
                "missing_policy": "missed events remain failures; unavailable events reported separately",
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["scenario_family", "method", "metric"], kind="mergesort"
    ).reset_index(drop=True)


def build_reliability_tables(repository_root: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(repository_root)
    if any("vomb" in path.lower() for path in INPUT_PATHS):
        raise RuntimeError("Erken synthesis input allowlist contains a forbidden Vomb path.")
    actual_raw = _prepare_metrics(_read_csv(root, INPUT_PATHS[0]))
    event_metrics = _read_csv(root, INPUT_PATHS[1])
    event_year_raw = _read_csv(root, INPUT_PATHS[2])
    random_raw = _prepare_metrics(_read_csv(root, INPUT_PATHS[3]))
    consecutive_raw = _prepare_metrics(_read_csv(root, INPUT_PATHS[4]))
    cv_actual_raw = _read_csv(root, INPUT_PATHS[5])
    cv_random_year = _read_csv(root, INPUT_PATHS[6])
    cv_consecutive_year = _read_csv(root, INPUT_PATHS[7])

    actual_year = _actual_year_table(actual_raw)
    actual_year_summary = _actual_as_year_summary(actual_year)
    actual_equal = _equal_year_summary(
        actual_year_summary,
        strata=(),
        metrics=CORE_METRICS,
        coverage_columns=(),
        key_prefix="actual",
        analysis_role="primary_actual_mask",
    )
    actual_paired_year = _paired_year_differences(
        actual_year_summary,
        strata=(),
        metrics=CORE_METRICS,
        method_pairs=METHOD_PAIRS,
    )
    actual_paired = _paired_summary(
        actual_paired_year,
        strata=(),
        key_prefix="actual_pair",
        analysis_role="primary_actual_mask",
    )
    loo_method, loo_pair, loo_stability = _leave_one_year_out_tables(
        actual_year_summary, actual_paired_year
    )
    event_year, event_equal = _event_tables(event_year_raw)

    random_coverage = (
        "observations_remaining",
        "resulting_observation_density",
        "resulting_maximum_internal_gap_days",
        "n_delete",
    )
    random_year = _scenario_year_summary(
        random_raw,
        strata=("deletion_fraction",),
        metrics=CONTROLLED_METRICS,
        coverage_columns=random_coverage,
    )
    random_equal = _equal_year_summary(
        random_year,
        strata=("deletion_fraction",),
        metrics=CONTROLLED_METRICS,
        coverage_columns=random_coverage,
        key_prefix="random_fraction",
        analysis_role="primary_controlled_random_deletion",
    )
    random_pair_year = _paired_year_differences(
        random_year,
        strata=("deletion_fraction",),
        metrics=CONTROLLED_METRICS,
        method_pairs=METHOD_PAIRS,
    )
    random_pair = _paired_summary(
        random_pair_year,
        strata=("deletion_fraction",),
        key_prefix="random_pair",
        analysis_role="primary_controlled_random_deletion",
    )

    unique_random = random_raw.drop_duplicates(["year", "mask_id"]).copy()
    random_strata_frames: list[pd.DataFrame] = []
    random_strata_cuts: list[pd.DataFrame] = []
    random_covariate_year_frames: list[pd.DataFrame] = []
    random_covariate_equal_frames: list[pd.DataFrame] = []
    for covariate in (
        "resulting_observation_density",
        "resulting_maximum_internal_gap_days",
    ):
        assigned_masks, cuts = _assign_tertiles(
            unique_random[["year", "mask_id", covariate]],
            value_column=covariate,
            group_columns=(),
            output_column="covariate_class",
        )
        cuts["analysis_role"] = "exploratory_post_hoc_visual_stratification"
        random_strata_cuts.append(cuts)
        assigned = random_raw.merge(
            assigned_masks[["year", "mask_id", "covariate_class"]],
            on=["year", "mask_id"],
            validate="many_to_one",
        )
        assigned["stratification_variable"] = covariate
        year_table = _scenario_year_summary(
            assigned,
            strata=("stratification_variable", "covariate_class"),
            metrics=CONTROLLED_METRICS,
            coverage_columns=random_coverage,
        )
        equal_table = _equal_year_summary(
            year_table,
            strata=("stratification_variable", "covariate_class"),
            metrics=CONTROLLED_METRICS,
            coverage_columns=random_coverage,
            key_prefix=f"random_covariate|{covariate}",
            analysis_role="exploratory_post_hoc_visual_stratification",
        )
        random_covariate_year_frames.append(year_table)
        random_covariate_equal_frames.append(equal_table)
        random_strata_frames.append(assigned_masks)

    random_assoc_year, random_assoc_equal = _continuous_associations(
        random_raw,
        family="random_deletion",
        group_columns=(),
        covariates=("resulting_observation_density", "resulting_maximum_internal_gap_days"),
    )

    unique_consecutive = consecutive_raw.drop_duplicates(["year", "mask_id"]).copy()
    activity_masks, activity_cuts = _assign_tertiles(
        unique_consecutive[["year", "mask_id", "duration_days", "a_gap"]],
        value_column="a_gap",
        group_columns=("duration_days",),
        output_column="activity_class",
    )
    activity_cuts["analysis_role"] = "protocol_visualization_stratum_continuous_a_gap_primary"
    consecutive = consecutive_raw.merge(
        activity_masks[["year", "mask_id", "activity_class"]],
        on=["year", "mask_id"],
        validate="many_to_one",
    )
    consecutive_coverage = (
        "a_gap",
        "window_midpoint_relative_position",
        "observations_removed",
        "resulting_maximum_internal_gap_days",
    )
    consecutive_duration_year = _scenario_year_summary(
        consecutive,
        strata=("duration_days",),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
    )
    consecutive_duration_equal = _equal_year_summary(
        consecutive_duration_year,
        strata=("duration_days",),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
        key_prefix="consecutive_duration",
        analysis_role="primary_controlled_consecutive_gap",
    )
    consecutive_activity_year = _scenario_year_summary(
        consecutive,
        strata=("duration_days", "activity_class"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
    )
    consecutive_activity_equal = _equal_year_summary(
        consecutive_activity_year,
        strata=("duration_days", "activity_class"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
        key_prefix="consecutive_activity",
        analysis_role="protocol_visualization_stratum_continuous_a_gap_primary",
    )
    consecutive_peak_year = _scenario_year_summary(
        consecutive,
        strata=("duration_days", "contains_reference_global_peak"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
    )
    consecutive_peak_equal = _equal_year_summary(
        consecutive_peak_year,
        strata=("duration_days", "contains_reference_global_peak"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
        key_prefix="consecutive_peak",
        analysis_role="primary_controlled_consecutive_gap",
    )
    consecutive_removed_year = _scenario_year_summary(
        consecutive,
        strata=("duration_days", "observations_removed"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
    )
    consecutive_removed_equal = _equal_year_summary(
        consecutive_removed_year,
        strata=("duration_days", "observations_removed"),
        metrics=CONTROLLED_METRICS,
        coverage_columns=consecutive_coverage,
        key_prefix="consecutive_removed",
        analysis_role="primary_controlled_consecutive_gap",
    )
    consecutive_pair_year = _paired_year_differences(
        consecutive_duration_year,
        strata=("duration_days",),
        metrics=CONTROLLED_METRICS,
        method_pairs=METHOD_PAIRS,
    )
    consecutive_pair = _paired_summary(
        consecutive_pair_year,
        strata=("duration_days",),
        key_prefix="consecutive_pair",
        analysis_role="primary_controlled_consecutive_gap",
    )
    consecutive_assoc_year, consecutive_assoc_equal = _continuous_associations(
        consecutive,
        family="consecutive_internal_gap",
        group_columns=("duration_days",),
        covariates=("a_gap", "window_midpoint_relative_position", "observations_removed"),
    )

    cv_actual_year, cv_actual_equal, cv_actual_pair = _cv_actual_tables(cv_actual_raw)
    cv_controlled = _cv_controlled_summary(cv_random_year, cv_consecutive_year)
    denominator_audit = _denominator_audit(
        actual_raw, random_raw, consecutive_raw, event_metrics
    )

    return {
        "erken_reliability_actual_mask_year_method.csv": actual_year,
        "erken_reliability_actual_mask_equal_year_summary.csv": actual_equal,
        "erken_reliability_actual_mask_paired_year_differences.csv": actual_paired_year,
        "erken_reliability_actual_mask_paired_summary.csv": actual_paired,
        "erken_reliability_actual_mask_leave_one_year_out.csv": loo_method,
        "erken_reliability_actual_mask_leave_one_year_out_paired.csv": loo_pair,
        "erken_reliability_actual_mask_leave_one_year_out_stability.csv": loo_stability,
        "erken_reliability_event_year_method.csv": event_year,
        "erken_reliability_event_equal_year_summary.csv": event_equal,
        "erken_reliability_random_year_method_deletion.csv": random_year,
        "erken_reliability_random_equal_year_deletion.csv": random_equal,
        "erken_reliability_random_paired_summary.csv": random_pair,
        "erken_reliability_random_covariate_strata_year.csv": pd.concat(random_covariate_year_frames, ignore_index=True),
        "erken_reliability_random_covariate_strata_summary.csv": pd.concat(random_covariate_equal_frames, ignore_index=True),
        "erken_reliability_random_covariate_strata_cuts.csv": pd.concat(random_strata_cuts, ignore_index=True),
        "erken_reliability_random_continuous_associations_year.csv": random_assoc_year,
        "erken_reliability_random_continuous_associations_summary.csv": random_assoc_equal,
        "erken_reliability_consecutive_duration_year_method.csv": consecutive_duration_year,
        "erken_reliability_consecutive_duration_summary.csv": consecutive_duration_equal,
        "erken_reliability_consecutive_activity_year_method.csv": consecutive_activity_year,
        "erken_reliability_consecutive_activity_summary.csv": consecutive_activity_equal,
        "erken_reliability_consecutive_peak_containment_summary.csv": consecutive_peak_equal,
        "erken_reliability_consecutive_observations_removed_summary.csv": consecutive_removed_equal,
        "erken_reliability_consecutive_paired_summary.csv": consecutive_pair,
        "erken_reliability_consecutive_continuous_associations_year.csv": consecutive_assoc_year,
        "erken_reliability_consecutive_continuous_associations_summary.csv": consecutive_assoc_equal,
        "erken_reliability_consecutive_activity_tertile_cuts.csv": activity_cuts,
        "erken_reliability_double_logistic_cv_actual_mask_year.csv": cv_actual_year,
        "erken_reliability_double_logistic_cv_actual_mask_summary.csv": cv_actual_equal,
        "erken_reliability_double_logistic_cv_actual_mask_paired_summary.csv": cv_actual_pair,
        "erken_reliability_double_logistic_cv_controlled_summary.csv": cv_controlled,
        "erken_reliability_denominator_audit.csv": denominator_audit,
    }


def _summary_record(
    table: pd.DataFrame,
    *,
    method: str,
    metric: str,
    **filters: Any,
) -> pd.Series:
    selection = table["method"].eq(method) & table["metric"].eq(metric)
    for column, value in filters.items():
        selection &= table[column].eq(value)
    matches = table.loc[selection]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one summary row for {method}/{metric}/{filters}, found {len(matches)}."
        )
    return matches.iloc[0]


def _estimate_text(row: pd.Series, digits: int = 3) -> str:
    return (
        f"{row['equal_year_estimate']:.{digits}f} "
        f"(95% year-cluster bootstrap CI "
        f"{row['cluster_bootstrap_ci_lower']:.{digits}f} to "
        f"{row['cluster_bootstrap_ci_upper']:.{digits}f})"
    )


def build_report(tables: Mapping[str, pd.DataFrame]) -> str:
    actual = tables["erken_reliability_actual_mask_equal_year_summary.csv"]
    actual_year = tables["erken_reliability_actual_mask_year_method.csv"]
    paired = tables["erken_reliability_actual_mask_paired_summary.csv"]
    loo = tables["erken_reliability_actual_mask_leave_one_year_out_stability.csv"]
    events = tables["erken_reliability_event_equal_year_summary.csv"]
    random = tables["erken_reliability_random_equal_year_deletion.csv"]
    random_assoc = tables["erken_reliability_random_continuous_associations_summary.csv"]
    consecutive = tables["erken_reliability_consecutive_duration_summary.csv"]
    activity = tables["erken_reliability_consecutive_activity_summary.csv"]
    containment = tables["erken_reliability_consecutive_peak_containment_summary.csv"]
    consecutive_assoc = tables[
        "erken_reliability_consecutive_continuous_associations_summary.csv"
    ]
    cv = tables["erken_reliability_double_logistic_cv_actual_mask_summary.csv"]
    audit = tables["erken_reliability_denominator_audit.csv"]

    def a(method: str, metric: str) -> pd.Series:
        return _summary_record(actual, method=method, metric=metric)

    method_order = list(PRIMARY_METHODS)
    method_short = {
        "linear_interpolation": "线性插值",
        "timesat_double_logistic": "默认双逻辑",
        "timesat_smoothing_spline": "平滑样条",
    }

    def pair_record(method_a: str, method_b: str, metric: str) -> pd.Series:
        return paired.loc[
            paired["method_a"].eq(method_a)
            & paired["method_b"].eq(method_b)
            & paired["metric"].eq(metric)
        ].iloc[0]

    linear_dl_nrmse = pair_record(
        "linear_interpolation", "timesat_double_logistic", "nrmse"
    )
    linear_spline_nrmse = pair_record(
        "linear_interpolation", "timesat_smoothing_spline", "nrmse"
    )
    linear_dl_integral = pair_record(
        "linear_interpolation", "timesat_double_logistic", "absolute_integral_error"
    )
    spline_dl_integral = pair_record(
        "timesat_smoothing_spline", "timesat_double_logistic", "absolute_integral_error"
    )
    nrmse_text = "；".join(
        f"{method_short[m]} {_estimate_text(a(m, 'nrmse'))}" for m in method_order
    )
    peak_text = "；".join(
        f"{method_short[m]} {_estimate_text(a(m, 'peak_timing_success_10d'))}" for m in method_order
    )
    integral_text = "；".join(
        f"{method_short[m]} {_estimate_text(a(m, 'absolute_integral_error'), 1)}"
        for m in method_order
    )

    typical_rows: list[str] = []
    for method in method_order:
        subset = actual_year.loc[actual_year["method"].eq(method)]
        peak_worst = subset.nlargest(2, "absolute_peak_date_error_days")
        peak_cases = ", ".join(
            f"{int(record.year)} ({record.absolute_peak_date_error_days:.1f} d)"
            for record in peak_worst.itertuples()
        )
        nrmse_worst = subset.loc[subset["nrmse"].idxmax()]
        typical_rows.append(
            f"- {METHOD_LABELS[method]}: two largest peak-date errors occurred in {peak_cases}; "
            f"nRMSE was highest in "
            f"{int(nrmse_worst['year'])} ({nrmse_worst['nrmse']:.3f})."
        )

    loo_lines: list[str] = []
    for method_a, method_b in METHOD_PAIRS:
        for metric in ("nrmse", "absolute_integral_error", "peak_timing_success_10d"):
            row = loo.loc[
                loo["method_a"].eq(method_a)
                & loo["method_b"].eq(method_b)
                & loo["metric"].eq(metric)
            ].iloc[0]
            direction = "kept" if row["all_leave_one_year_out_estimates_keep_full_direction"] else "changed"
            loo_lines.append(
                f"- {METHOD_LABELS[method_a]} vs {METHOD_LABELS[method_b]}, `{metric}`: "
                f"full advantage for method A {row['full_equal_year_mean_advantage_for_method_a']:.3f}; "
                f"leave-one-year-out range {row['minimum_loo_advantage_for_method_a']:.3f} to "
                f"{row['maximum_loo_advantage_for_method_a']:.3f}; direction {direction}."
            )

    random_lines: list[str] = []
    for method in method_order:
        low = _summary_record(random, method=method, metric="nrmse", deletion_fraction=0.1)
        high = _summary_record(random, method=method, metric="nrmse", deletion_fraction=0.5)
        high_success = _summary_record(
            random, method=method, metric="peak_timing_success_10d", deletion_fraction=0.5
        )
        random_lines.append(
            f"- {METHOD_LABELS[method]}: nRMSE {_estimate_text(low)} at 10% deletion and "
            f"{_estimate_text(high)} at 50%; 50% deletion peak-date <=10 d rate "
            f"{_estimate_text(high_success)}. Coverage at 50% spanned density "
            f"{high['resulting_observation_density_observed_minimum']:.3f}-"
            f"{high['resulting_observation_density_observed_maximum']:.3f} and maximum internal gap "
            f"{high['resulting_maximum_internal_gap_days_observed_minimum']:.0f}-"
            f"{high['resulting_maximum_internal_gap_days_observed_maximum']:.0f} d."
        )

    random_association_lines: list[str] = []
    for method in method_order:
        density = random_assoc.loc[
            random_assoc["method"].eq(method)
            & random_assoc["covariate"].eq("resulting_observation_density")
            & random_assoc["outcome"].eq("nrmse")
        ].iloc[0]
        max_gap = random_assoc.loc[
            random_assoc["method"].eq(method)
            & random_assoc["covariate"].eq("resulting_maximum_internal_gap_days")
            & random_assoc["outcome"].eq("nrmse")
        ].iloc[0]
        random_association_lines.append(
            f"- {METHOD_LABELS[method]}: equal-year mean within-year Spearman nRMSE association "
            f"was {density['equal_year_mean_spearman']:.3f} "
            f"({density['cluster_bootstrap_ci_lower']:.3f} to {density['cluster_bootstrap_ci_upper']:.3f}) "
            f"with remaining density and {max_gap['equal_year_mean_spearman']:.3f} "
            f"({max_gap['cluster_bootstrap_ci_lower']:.3f} to {max_gap['cluster_bootstrap_ci_upper']:.3f}) "
            f"with realized maximum internal gap; all 7 years contributed."
        )

    consecutive_lines: list[str] = []
    for method in method_order:
        short = _summary_record(consecutive, method=method, metric="nrmse", duration_days=10)
        long = _summary_record(consecutive, method=method, metric="nrmse", duration_days=45)
        long_success = _summary_record(
            consecutive,
            method=method,
            metric="peak_timing_success_10d",
            duration_days=45,
        )
        low_activity = _summary_record(
            activity,
            method=method,
            metric="nrmse",
            duration_days=45,
            activity_class="low",
        )
        high_activity = _summary_record(
            activity,
            method=method,
            metric="nrmse",
            duration_days=45,
            activity_class="high",
        )
        consecutive_lines.append(
            f"- {METHOD_LABELS[method]}: nRMSE {_estimate_text(short)} for 10-d windows and "
            f"{_estimate_text(long)} for 45-d windows; 45-d peak-date <=10 d rate "
            f"{_estimate_text(long_success)}. Within 45-d windows, low-activity nRMSE was "
            f"{_estimate_text(low_activity)} and high-activity nRMSE was {_estimate_text(high_activity)}."
        )

    containment_lines: list[str] = []
    for method in method_order:
        outside = _summary_record(
            containment,
            method=method,
            metric="peak_timing_success_10d",
            duration_days=45,
            contains_reference_global_peak=False,
        )
        inside = _summary_record(
            containment,
            method=method,
            metric="peak_timing_success_10d",
            duration_days=45,
            contains_reference_global_peak=True,
        )
        containment_lines.append(
            f"- {METHOD_LABELS[method]}: 45-d windows not containing/containing the reference global peak "
            f"had <=10 d rates {_estimate_text(outside)} / {_estimate_text(inside)}; "
            f"the peak-containing stratum included {int(inside['n_years_in_stratum'])} years and "
            f"{int(inside['n_scenarios_total'])} scenario-method rows."
        )

    consecutive_association_lines: list[str] = []
    for method in method_order:
        associations: dict[str, pd.Series] = {}
        for covariate in (
            "a_gap",
            "window_midpoint_relative_position",
            "observations_removed",
        ):
            associations[covariate] = consecutive_assoc.loc[
                consecutive_assoc["method"].eq(method)
                & consecutive_assoc["duration_days"].eq(45)
                & consecutive_assoc["covariate"].eq(covariate)
                & consecutive_assoc["outcome"].eq("nrmse")
            ].iloc[0]
        consecutive_association_lines.append(
            f"- {METHOD_LABELS[method]} (45-d windows): equal-year mean within-year Spearman "
            f"nRMSE association was {associations['a_gap']['equal_year_mean_spearman']:.3f} with A_gap, "
            f"{associations['window_midpoint_relative_position']['equal_year_mean_spearman']:.3f} with "
            f"relative midpoint position, and {associations['observations_removed']['equal_year_mean_spearman']:.3f} "
            f"with observations removed; 7 years contributed to each nRMSE association."
        )

    cv_default = _summary_record(cv, method=CV_DEFAULT_METHOD, metric="nrmse")
    cv_selected = _summary_record(cv, method=CV_METHOD, metric="nrmse")
    cv_integral_default = _summary_record(cv, method=CV_DEFAULT_METHOD, metric="absolute_integral_error")
    cv_integral_selected = _summary_record(cv, method=CV_METHOD, metric="absolute_integral_error")
    failures_total = int(audit["n_reconstruction_failures"].sum())
    unavailable_total = int(audit["n_metric_unavailable"].sum())

    lines = [
        "# Erken reliability synthesis v1.0",
        "",
        f"**Analysis date:** 2026-09-18  ",
        f"**Starting commit:** `{STARTING_COMMIT}`  ",
        "**Scope:** saved Erken outputs only; no reconstruction or satellite extraction rerun; no Vombsjön data or performance inspected; no second freeze executed.",
        "",
        "## 简明中文结论",
        "",
        f"1. 在实际 Sentinel-2 采样掩膜下，点位误差以年为单位等权汇总后为：{nrmse_text}。线性插值 nRMSE 对默认双逻辑在 7/7 年较低、对平滑样条在 6/7 年较低；这是点位误差上的稳定优势，但不等于它每个科学指标都最好。来源：`erken_reliability_actual_mask_equal_year_summary.csv` 与 `erken_reliability_actual_mask_paired_summary.csv`。",
        f"2. 全局峰值日期 <=10 天的年份等权达标率为：{peak_text}。峰值日期与峰值幅度分开统计；多事件年份中全局最大值身份切换会造成很大的日期误差。来源：`erken_reliability_actual_mask_year_method.csv` 与 `erken_reliability_actual_mask_equal_year_summary.csv`。",
        f"3. 共同支持区间的绝对积分误差为：{integral_text} ug day L^-1。默认双逻辑在积分上平均最好，却在 nRMSE、相关性和事件恢复上较弱；积分准确不能替代短期事件恢复充分。来源：`erken_reliability_actual_mask_equal_year_summary.csv`。",
        "4. 18 个主要事件的恢复结果仍是后验冻结的次要/探索性分析，不能替代主分析的全局峰值指标。来源：`erken_reliability_event_year_method.csv` 与 `erken_reliability_event_equal_year_summary.csv`。",
        "5. 随机删除与连续缺口都没有产生重建失败，但可靠性随缺测增强而总体下降，并受年份、方法、A_gap、峰值是否落在缺口内和实际移除观测数共同影响；不存在由这 7 个年份支持的通用缺口阈值。",
        "6. 逐次剔除一年表明，一些平均优势方向稳定，另一些会随被剔除年份改变；因此报告同时给出平均优势、逐年胜负与 leave-one-year-out 范围，不能把平均较低误差写成每年均优。",
        "7. 所有主结果来自 7 个 Erken 年份。bootstrap 以整年为 cluster，区间只能反映这 7 年内部的年际不确定性，不能外推为通用湖泊可靠性界限。",
        "",
        "## Analysis identity and statistical method",
        "",
        f"All scenario metrics were first averaged within year and stratum; years then received equal weight. Uncertainty used {BOOTSTRAP_REPLICATES:,} whole-year bootstrap resamples with master seed `{BOOTSTRAP_SEED}` and two-sided percentile intervals at 95%. A SHA256-derived sub-seed was used per estimand. Resampling the year-level vector is algebraically equivalent to resampling complete year blocks after the prescribed within-year reduction, and therefore preserves all method and scenario pairing inside a year.",
        "",
        "Continuous metrics were not imputed when unavailable. Eligible peak-timing failures or missing reconstructed peaks would count as non-success, while reference-ineligible cases would be excluded and reported. In the saved inputs used here, every primary actual-mask, random-deletion and consecutive-gap reconstruction and every requested primary metric was available. The denominator audit nevertheless records every denominator explicitly.",
        "",
        "## Primary actual-mask comparison",
        "",
        "### Metric-specific strengths and limitations",
        "",
        f"- Linear interpolation had the lowest mean nRMSE ({_estimate_text(a('linear_interpolation', 'nrmse'))}), the highest mean trajectory correlation ({_estimate_text(a('linear_interpolation', 'pearson_correlation'))}), and the lowest normalized peak-magnitude error ({_estimate_text(a('linear_interpolation', 'normalized_absolute_peak_magnitude_error'))}). It had lower nRMSE than default double logistic in {int(linear_dl_nrmse['n_years_method_a_favored'])}/7 years and than the smoothing spline in {int(linear_spline_nrmse['n_years_method_a_favored'])}/7 years. Its limitation is that local responsiveness does not guarantee correct annual-maximum identity or the lowest cumulative integral error.",
        f"- The smoothing spline was intermediate in mean nRMSE ({_estimate_text(a('timesat_smoothing_spline', 'nrmse'))}) and correlation ({_estimate_text(a('timesat_smoothing_spline', 'pearson_correlation'))}). It reduced noise with more flexibility than the default double logistic, but still attenuated or reordered peaks and had the largest mean absolute integral error ({_estimate_text(a('timesat_smoothing_spline', 'absolute_integral_error'), 1)} ug day L^-1).",
        f"- Default double logistic had the smallest descriptive mean absolute integral error ({_estimate_text(a('timesat_double_logistic', 'absolute_integral_error'), 1)} ug day L^-1), outperforming linear interpolation on this metric in {int(linear_dl_integral['n_years_method_b_favored'])}/7 years and the smoothing spline in {int(spline_dl_integral['n_years_method_b_favored'])}/7 years. However, its mean nRMSE ({_estimate_text(a('timesat_double_logistic', 'nrmse'))}), correlation ({_estimate_text(a('timesat_double_logistic', 'pearson_correlation'))}), and normalized peak-magnitude error ({_estimate_text(a('timesat_double_logistic', 'normalized_absolute_peak_magnitude_error'))}) were least favorable. Pairwise bootstrap intervals for integral advantages included zero against linear interpolation and the spline, so the lower descriptive mean is not a universal or formal superiority claim.",
        "",
        "### Cross-year stability and typical difficult years",
        "",
        *typical_rows,
        "",
        "A lower equal-year mean is not evidence of year-by-year dominance. Paired year differences and their bootstrap intervals are in `erken_reliability_actual_mask_paired_summary.csv`; the complete year-level contrasts are in `erken_reliability_actual_mask_paired_year_differences.csv`.",
        "",
        "### Leave-one-year-out re-summaries",
        "",
        *loo_lines,
        "",
        "These are re-summaries only: no method was refit and no parameter was retuned. Full results are in `erken_reliability_actual_mask_leave_one_year_out*.csv`.",
        "",
        "### Supplementary event recovery",
        "",
    ]
    for method in method_order:
        row = _summary_record(events, method=method, metric="recovery_fraction_10d")
        lines.append(
            f"- {METHOD_LABELS[method]}: equal-year event recovery <=10 d {_estimate_text(row)}; "
            f"pooled descriptive <=10 d count {int(row['n_success_10d_total'])}/"
            f"{int(row['n_available_reference_events_total'])}; "
            f"pooled descriptive count {int(row['n_matched_events_total'])} matched, "
            f"{int(row['n_missed_events_total'])} missed, {int(row['n_unavailable_events_total'])} unavailable "
            f"among {int(row['n_reference_events_total'])} reference-event rows."
        )
    lines.extend(
        [
            "",
            "## Missingness response",
            "",
            "### Random deletion",
            "",
            *random_lines,
            "",
            "Deletion-fraction curves are confirmatory controlled-gap summaries. Additional tertile displays for remaining density and realized maximum internal gap are explicitly labelled `exploratory_post_hoc_visual_stratification`; they do not redefine the frozen primary analysis. See `erken_reliability_random_covariate_strata_summary.csv` and the continuous within-year associations.",
            "",
            *random_association_lines,
            "",
            "### Consecutive internal gaps",
            "",
            *consecutive_lines,
            "",
            "A_gap remains continuous in the primary association table. Low/medium/high labels are used only for visualization and were formed from tertiles inside each frozen duration, as required by the contract. Relative midpoint position and observations removed are retained continuously in `erken_reliability_consecutive_continuous_associations*.csv`; exact observations-removed strata are in `erken_reliability_consecutive_observations_removed_summary.csv`.",
            "",
            *consecutive_association_lines,
            "",
            "### Peak containment",
            "",
            *containment_lines,
            "",
            "Sparse peak-containing strata have wide, discrete seven-year bootstrap intervals. They are evidence about the observed Erken scenarios, not universal operational thresholds.",
            "",
            "## Double-logistic CV sensitivity (separate from the primary comparison)",
            "",
            f"The training-only CV sensitivity changed actual-mask nRMSE from {_estimate_text(cv_default)} under the frozen default to {_estimate_text(cv_selected)}. Absolute common-support integral error changed from {_estimate_text(cv_integral_default, 1)} to {_estimate_text(cv_integral_selected, 1)} ug day L^-1. This remains a secondary sensitivity and does not replace the default double-logistic primary result. Controlled-gap sensitivity summaries are in `erken_reliability_double_logistic_cv_controlled_summary.csv`.",
            "",
            "## Failures, missingness and support limits",
            "",
            f"Across the primary tables audited here, the summed method-family failure count was {failures_total} and the summed metric-unavailable count was {unavailable_total}. These zero counts are empirical outcomes, not proof that a successful curve is scientifically reliable. The complete audit is `erken_reliability_denominator_audit.csv`.",
            "",
            "The 2019 and 2025 records are boundary-truncated. They remain eligible only for frozen common-support metrics; neither their common-support maximum nor integral is claimed to represent the full calendar year. Controlled-gap coverage ranges and contributing-year counts appear on every long-format summary row.",
            "",
            "## Implications for the future second freeze",
            "",
            "This synthesis provides evidence for, but does not execute, the second Erken-only freeze. The freeze decision still needs to record: (i) whether the workflow prioritizes point-wise/trajectory fidelity, global-peak timing, cumulative integral, or an explicit hierarchy among them; (ii) whether the primary transfer workflow carries the frozen default double logistic only or also a clearly labelled CV sensitivity; (iii) how reconstructed values will be represented at unsupported or high-activity gaps; and (iv) the exact transfer manifest, quality rules and reporting language. No setting should be chosen from a single pooled metric.",
            "",
            "## English Results draft",
            "",
            f"Under the actual Sentinel-2 sampling mask, equal-year mean nRMSE was {_estimate_text(a('linear_interpolation', 'nrmse'))} for linear interpolation, {_estimate_text(a('timesat_smoothing_spline', 'nrmse'))} for the smoothing spline, and {_estimate_text(a('timesat_double_logistic', 'nrmse'))} for the default double-logistic reconstruction. The corresponding mean trajectory correlations were {_estimate_text(a('linear_interpolation', 'pearson_correlation'))}, {_estimate_text(a('timesat_smoothing_spline', 'pearson_correlation'))}, and {_estimate_text(a('timesat_double_logistic', 'pearson_correlation'))}. Rankings differed by outcome: the default double logistic had the smallest equal-year absolute common-support integral error ({_estimate_text(a('timesat_double_logistic', 'absolute_integral_error'), 1)} ug day L^-1), whereas linear interpolation and the smoothing spline had errors of {_estimate_text(a('linear_interpolation', 'absolute_integral_error'), 1)} and {_estimate_text(a('timesat_smoothing_spline', 'absolute_integral_error'), 1)} ug day L^-1, respectively. Global-peak timing success within 10 d was {_estimate_text(a('linear_interpolation', 'peak_timing_success_10d'))}, {_estimate_text(a('timesat_smoothing_spline', 'peak_timing_success_10d'))}, and {_estimate_text(a('timesat_double_logistic', 'peak_timing_success_10d'))}. Thus, point-wise fidelity, peak timing, peak magnitude, trajectory agreement, and seasonal integral did not identify a uniformly best method.",
            "",
            "Additional missingness degraded reliability without defining a universal gap-duration threshold. Random-deletion and consecutive-gap responses were summarized within each year before years were equally weighted. For consecutive windows, higher A_gap strata generally had larger nRMSE than lower-activity windows of the same duration, while windows containing the reference global peak showed lower peak-timing success. Remaining observation density, realized maximum internal gap, relative gap position, and the number of removed observations showed method- and year-dependent associations. All primary reconstructions completed, but completion alone did not imply reliable seasonal metrics.",
            "",
            "## English Discussion draft",
            "",
            "The Erken results support a metric-specific interpretation of temporal reconstruction. Linear interpolation was most responsive to observed local variation and had the lowest average point-wise error, but its advantage was not universal across years or outcomes. The default double-logistic representation better preserved the common-support integral on average while more often altering the identity, timing, or magnitude of the dominant seasonal peak. The smoothing spline occupied an intermediate position for several outcomes but could still attenuate or reorder peaks. These contrasts separate four claims that are often conflated: a low average error does not imply year-by-year superiority; an accurate peak date does not ensure accurate peak magnitude; an accurate integral does not demonstrate short-event recovery; and a numerically complete reconstructed curve is not evidence that its scientific metrics are reliable.",
            "",
            "The controlled experiments further show why gap length is insufficient as an operational rule. Reliability depended on realized observation density and maximum internal gap for scattered deletion, and on duration, relative position, global-peak containment, removed-observation count, and hidden reference activity for consecutive gaps. Because only seven Erken years contribute independent clusters, the intervals are necessarily coarse and cannot justify a general lake-wide threshold. The future transfer freeze should therefore encode a metric-priority hierarchy and uncertainty-reporting rule rather than designate one universally superior reconstruction method.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/33_erken_reliability_synthesis.py",
            "pytest -q",
            "python scripts/34_validate_erken_reliability_synthesis.py",
            "```",
            "",
            "The synthesis script reads only the eight allowlisted saved Erken result files recorded in `config/erken_reliability_synthesis_v1.0.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _save_figure(fig: plt.Figure, output_stem: Path) -> list[Path]:
    paths = []
    for suffix, dpi in ((".png", 220), (".pdf", 300)):
        path = output_stem.with_suffix(suffix)
        metadata = None
        if suffix == ".pdf":
            fixed_time = datetime(2026, 9, 18, tzinfo=timezone.utc)
            metadata = {
                "Title": output_stem.name,
                "Author": "TIMESAT twinwater Erken reliability synthesis",
                "Creator": ANALYSIS_VERSION,
                "Producer": "Matplotlib",
                "CreationDate": fixed_time,
                "ModDate": fixed_time,
            }
        fig.savefig(path, dpi=dpi, bbox_inches="tight", metadata=metadata)
        paths.append(path)
    plt.close(fig)
    return paths


def _plot_cross_year(tables: Mapping[str, pd.DataFrame], output: Path) -> list[Path]:
    data = tables["erken_reliability_actual_mask_year_method.csv"]
    panels = (
        ("nrmse", "Point-wise nRMSE"),
        ("absolute_peak_date_error_days", "Global-peak date error (d)"),
        ("normalized_absolute_peak_magnitude_error", "Normalized peak-magnitude error"),
        ("absolute_integral_error", "Common-support integral error"),
        ("pearson_correlation", "Trajectory Pearson r"),
        ("peak_timing_success_10d", "Global peak within 10 d"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, constrained_layout=True)
    for ax, (column, title) in zip(axes.flat, panels, strict=True):
        for method in PRIMARY_METHODS:
            subset = data.loc[data["method"].eq(method)].sort_values("year")
            values = _as_bool(subset[column]).astype(float) if column.startswith("peak_timing_success") else subset[column].astype(float)
            ax.plot(
                subset["year"],
                values,
                marker="o",
                linewidth=1.8,
                color=METHOD_COLORS[method],
                label=METHOD_LABELS[method],
            )
        if column == "absolute_peak_date_error_days":
            ax.axhline(10, color="0.35", linestyle="--", linewidth=1, label="10-d criterion")
        if column == "peak_timing_success_10d":
            ax.set_ylim(-0.05, 1.05)
        ax.set_title(title)
        ax.grid(alpha=0.25)
        ax.set_xticks(PRIMARY_YEARS, ["2019†", "2020", "2021", "2022", "2023", "2024", "2025†"], rotation=35)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Erken actual-mask reliability by year († boundary-truncated)", fontsize=14)
    return _save_figure(fig, output / "figure_01_cross_year_method_comparison")


def _plot_summary_lines(
    ax: plt.Axes,
    table: pd.DataFrame,
    *,
    x_column: str,
    metric: str,
    title: str,
) -> None:
    for method in PRIMARY_METHODS:
        subset = table.loc[table["method"].eq(method) & table["metric"].eq(metric)].sort_values(x_column)
        x = subset[x_column].astype(float).to_numpy()
        y = subset["equal_year_estimate"].astype(float).to_numpy()
        low = subset["cluster_bootstrap_ci_lower"].astype(float).to_numpy()
        high = subset["cluster_bootstrap_ci_upper"].astype(float).to_numpy()
        ax.plot(x, y, marker="o", color=METHOD_COLORS[method], label=METHOD_LABELS[method])
        ax.fill_between(x, low, high, color=METHOD_COLORS[method], alpha=0.12)
    ax.set_title(title)
    ax.grid(alpha=0.25)


def _plot_missingness_response(tables: Mapping[str, pd.DataFrame], output: Path) -> list[Path]:
    random = tables["erken_reliability_random_equal_year_deletion.csv"]
    consecutive = tables["erken_reliability_consecutive_duration_summary.csv"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    _plot_summary_lines(
        axes[0, 0], random, x_column="deletion_fraction", metric="nrmse", title="Random deletion: nRMSE"
    )
    _plot_summary_lines(
        axes[0, 1], random, x_column="deletion_fraction", metric="peak_timing_success_10d", title="Random deletion: global peak within 10 d"
    )
    _plot_summary_lines(
        axes[1, 0], consecutive, x_column="duration_days", metric="nrmse", title="Consecutive gaps: nRMSE"
    )
    _plot_summary_lines(
        axes[1, 1], consecutive, x_column="duration_days", metric="peak_timing_success_10d", title="Consecutive gaps: global peak within 10 d"
    )
    axes[0, 0].set_xlabel("Interior observations deleted (fraction)")
    axes[0, 1].set_xlabel("Interior observations deleted (fraction)")
    axes[1, 0].set_xlabel("Calendar-window duration (d)")
    axes[1, 1].set_xlabel("Calendar-window duration (d)")
    axes[0, 1].set_ylim(-0.05, 1.05)
    axes[1, 1].set_ylim(-0.05, 1.05)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Empirical missingness response; bands are 95% whole-year bootstrap intervals", fontsize=14)
    return _save_figure(fig, output / "figure_02_missingness_response_curves")


def _plot_activity_strata(tables: Mapping[str, pd.DataFrame], output: Path) -> list[Path]:
    data = tables["erken_reliability_consecutive_activity_summary.csv"]
    activity_order = ("low", "medium", "high")
    activity_colors = {"low": "#56B4E9", "medium": "#E69F00", "high": "#CC79A7"}
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, constrained_layout=True)
    for column, method in enumerate(PRIMARY_METHODS):
        for row, metric in enumerate(("nrmse", "peak_timing_success_10d")):
            ax = axes[row, column]
            for activity_class in activity_order:
                subset = data.loc[
                    data["method"].eq(method)
                    & data["metric"].eq(metric)
                    & data["activity_class"].eq(activity_class)
                ].sort_values("duration_days")
                x = subset["duration_days"].astype(float).to_numpy()
                y = subset["equal_year_estimate"].astype(float).to_numpy()
                low = subset["cluster_bootstrap_ci_lower"].astype(float).to_numpy()
                high = subset["cluster_bootstrap_ci_upper"].astype(float).to_numpy()
                ax.plot(x, y, marker="o", color=activity_colors[activity_class], label=activity_class)
                ax.fill_between(x, low, high, color=activity_colors[activity_class], alpha=0.12)
            ax.grid(alpha=0.25)
            ax.set_xlabel("Gap duration (d)")
            if row == 0:
                ax.set_title(METHOD_LABELS[method])
            if row == 1:
                ax.set_ylim(-0.05, 1.05)
    axes[0, 0].set_ylabel("Point-wise nRMSE")
    axes[1, 0].set_ylabel("Global peak within 10 d")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, title="A_gap tertile within duration", loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Reliability stratified by hidden within-gap activity", fontsize=14)
    return _save_figure(fig, output / "figure_03_reliability_activity_strata")


def _plot_loo_stability(tables: Mapping[str, pd.DataFrame], output: Path) -> list[Path]:
    data = tables["erken_reliability_actual_mask_leave_one_year_out_paired.csv"]
    metrics = ("nrmse", "absolute_peak_date_error_days", "absolute_integral_error", "pearson_correlation")
    metric_labels = {
        "nrmse": "nRMSE advantage",
        "absolute_peak_date_error_days": "Peak-date error advantage (d)",
        "absolute_integral_error": "Integral-error advantage",
        "pearson_correlation": "Correlation advantage",
    }
    pairs = list(METHOD_PAIRS)
    fig, axes = plt.subplots(len(metrics), len(pairs), figsize=(14, 11), sharex=True, constrained_layout=True)
    for row, metric in enumerate(metrics):
        for column, (method_a, method_b) in enumerate(pairs):
            ax = axes[row, column]
            subset = data.loc[
                data["metric"].eq(metric)
                & data["method_a"].eq(method_a)
                & data["method_b"].eq(method_b)
            ].sort_values("omitted_year")
            ax.bar(
                subset["omitted_year"].astype(str),
                subset["mean_advantage_for_method_a_after_omission"],
                color=np.where(subset["mean_advantage_for_method_a_after_omission"].ge(0), "#0072B2", "#D55E00"),
            )
            ax.axhline(0, color="0.25", linewidth=0.8)
            ax.grid(axis="y", alpha=0.2)
            if row == 0:
                ax.set_title(f"{METHOD_LABELS[method_a]}\nvs {METHOD_LABELS[method_b]}", fontsize=9)
            if column == 0:
                ax.set_ylabel(metric_labels[metric])
            if row == len(metrics) - 1:
                ax.tick_params(axis="x", rotation=35)
    fig.suptitle("Leave-one-year-out paired advantage (positive favors first method)", fontsize=14)
    return _save_figure(fig, output / "figure_04_leave_one_year_out_stability")


def write_reliability_products(
    *, repository_root: str | Path, output_directory: str | Path | None = None
) -> list[Path]:
    root = Path(repository_root)
    config = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    if config["starting_commit"] != STARTING_COMMIT:
        raise RuntimeError("Reliability synthesis starting commit does not match the recorded value.")
    if tuple(config["inputs"]) != INPUT_PATHS:
        raise RuntimeError("Reliability synthesis input allowlist differs from the versioned config.")
    if config["estimation"]["bootstrap_replicates"] != BOOTSTRAP_REPLICATES:
        raise RuntimeError("Bootstrap replicate count differs from the versioned config.")
    if config["estimation"]["bootstrap_master_seed"] != BOOTSTRAP_SEED:
        raise RuntimeError("Bootstrap seed differs from the versioned config.")
    output = root / (output_directory or config["output_directory"])
    output.mkdir(parents=True, exist_ok=True)

    tables = build_reliability_tables(root)
    written: list[Path] = []
    for name, table in tables.items():
        written.append(write_deterministic_csv(table, output / name))

    written.extend(_plot_cross_year(tables, output))
    written.extend(_plot_missingness_response(tables, output))
    written.extend(_plot_activity_strata(tables, output))
    written.extend(_plot_loo_stability(tables, output))

    report_path = output / "erken_reliability_report_v1.0.md"
    report_path.write_text(build_report(tables), encoding="utf-8")
    written.append(report_path)

    manifest: dict[str, Any] = {
        "schema_version": "erken_reliability_synthesis_manifest_v1",
        "analysis_version": ANALYSIS_VERSION,
        "analysis_date": "2026-09-18",
        "starting_commit": STARTING_COMMIT,
        "analysis_scope": "erken_only_saved_results",
        "reconstruction_rerun": False,
        "satellite_extraction_rerun": False,
        "vombsjon_data_or_performance_inspected": False,
        "second_freeze_executed": False,
        "year_weighting": "within_year_first_then_equal_year",
        "bootstrap": {
            "cluster_unit": "calendar_year",
            "replicates": BOOTSTRAP_REPLICATES,
            "master_seed": BOOTSTRAP_SEED,
            "subseed_derivation": "sha256(master_seed|analysis_key), first 16 hex digits modulo 2^63-1",
            "confidence_level": 0.95,
            "interval_algorithm": "two_sided_percentile_numpy_linear_quantiles",
            "paired_year_resampling": True,
        },
        "input_sha256": {path: sha256_file(root / path) for path in INPUT_PATHS},
        "implementation_sha256": {
            CONFIG_PATH: sha256_file(root / CONFIG_PATH),
            "src/twinwater_timesat/reliability_synthesis.py": sha256_file(
                root / "src/twinwater_timesat/reliability_synthesis.py"
            ),
            "scripts/33_erken_reliability_synthesis.py": sha256_file(
                root / "scripts/33_erken_reliability_synthesis.py"
            ),
            "scripts/34_validate_erken_reliability_synthesis.py": sha256_file(
                root / "scripts/34_validate_erken_reliability_synthesis.py"
            ),
        },
        "output_sha256": {
            path.name: sha256_file(path) for path in sorted(written, key=lambda item: item.name)
        },
        "output_counts": {
            "csv_tables": len(tables),
            "figures_png": 4,
            "figures_pdf": 4,
            "reports": 1,
        },
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(
        manifest, excluded_keys=("manifest_payload_sha256",)
    )
    manifest_path = output / "erken_reliability_synthesis_manifest_v1.0.json"
    write_deterministic_json(manifest, manifest_path)
    written.append(manifest_path)
    return written
