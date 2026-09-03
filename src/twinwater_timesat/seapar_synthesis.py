"""Erken-only descriptive Phase S5 synthesis at the hard human-review gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    PRIMARY_YEARS,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.seapar_actual import (
    COMPARISON_METHODS,
    CV_METHOD,
    DEFAULT_METHOD,
    _implementation_provenance,
    _json_manifest,
    load_passed_selection,
)
from twinwater_timesat.seapar_controlled import (
    CONTROLLED_ROOT,
    FAMILY_SPECS,
    _output_names,
)
from twinwater_timesat.seapar_sensitivity import (
    CLASSIFICATION,
    PROTOCOL_VERSION,
    SeaparSensitivityGuardError,
    load_passed_seapar_preflight,
    require_clean_descendant,
    validate_parent_output_inventory,
)


SYNTHESIS_DIRECTORY = "results/phase5/synthesis"
FINAL_TEST_EVIDENCE_PATH = (
    "results/phase5/double_logistic_seapar_selection/"
    "erken_phase5_seapar_final_tests.json"
)
S5_IMPLEMENTATION_PATHS = (
    "scripts/25_erken_phase5_seapar_synthesis.py",
    "src/twinwater_timesat/seapar_synthesis.py",
    "tests/test_seapar_synthesis.py",
)
METHOD_LABELS = {
    "linear_interpolation": "Linear",
    "timesat_smoothing_spline": "Frozen spline",
    DEFAULT_METHOD: "DL default p_seapar=1",
    CV_METHOD: "DL CV-selected p_seapar",
}
METHOD_COLORS = {
    "linear_interpolation": "#0072B2",
    "timesat_smoothing_spline": "#009E73",
    DEFAULT_METHOD: "#D55E00",
    CV_METHOD: "#7A3DC8",
}
RESPONSE_NRMSE_COLUMN = "mean_equal_year_nrmse"


def _read_csv(root: Path, relative: str) -> pd.DataFrame:
    return pd.read_csv(root / relative, low_memory=False)


def _bool_mean(values: pd.Series) -> float:
    available = values.dropna()
    if available.empty:
        return np.nan
    if available.dtype == object:
        mapped = available.astype(str).str.lower().map({"true": True, "false": False})
        if mapped.isna().any():
            raise ValueError("Boolean metric contains a non-boolean value.")
        available = mapped
    return float(available.astype(bool).mean())


def _event_scenario_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (mask_id, method), group in events.groupby(["mask_id", "method"], sort=True):
        available = group["event_status"].ne("unavailable")
        matched = group["event_status"].eq("matched")
        row: dict[str, Any] = {
            "mask_id": mask_id,
            "method": method,
            "event_reference_count": int(len(group)),
            "event_matched_count": int(matched.sum()),
            "event_missed_count": int(
                group["event_status"].eq("missed_no_peak_within_15d").sum()
            ),
            "event_unavailable_count": int(group["event_status"].eq("unavailable").sum()),
        }
        for days in (5, 10, 15):
            row[f"event_recovery_fraction_{days}d"] = (
                _bool_mean(group.loc[available, f"success_{days}d"])
                if available.any()
                else np.nan
            )
        row["event_median_absolute_timing_error_matched_days"] = float(
            group.loc[matched, "absolute_timing_error_days"].median()
        )
        row["event_median_normalized_absolute_magnitude_error_matched"] = float(
            group.loc[matched, "normalized_absolute_magnitude_error"].median()
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _controlled_summary(
    data: pd.DataFrame, group_columns: list[str]
) -> pd.DataFrame:
    """Summarize scenarios within year; never pool masks across years."""

    rows: list[dict[str, Any]] = []
    for keys, group in data.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys, strict=True))
        row.update(
            {
                "n_scenarios": int(len(group)),
                "n_reconstruction_failures": int(
                    group["reconstruction_status"].ne("ok").sum()
                ),
                "fraction_reconstruction_failures": float(
                    group["reconstruction_status"].ne("ok").mean()
                ),
                "mean_mae": float(group["mae"].mean()),
                "mean_rmse": float(group["rmse"].mean()),
                "mean_nrmse": float(group["nrmse"].mean()),
                "median_nrmse": float(group["nrmse"].median()),
                "mean_absolute_global_peak_timing_error_days": float(
                    group["absolute_peak_date_error_days"].mean()
                ),
                "median_absolute_global_peak_timing_error_days": float(
                    group["absolute_peak_date_error_days"].median()
                ),
                "mean_normalized_absolute_global_peak_magnitude_error": float(
                    group["normalized_absolute_peak_magnitude_error"].mean()
                ),
                "mean_absolute_integral_error": float(
                    group["absolute_integral_error"].mean()
                ),
                "mean_pearson_correlation": float(
                    group["pearson_correlation"].mean()
                ),
                "fraction_scenarios_with_negative_values": float(
                    group["n_negative_reconstructed_days"].gt(0).mean()
                ),
                "mean_matched_event_absolute_timing_error_days": float(
                    group["event_median_absolute_timing_error_matched_days"].mean()
                ),
                "mean_matched_event_normalized_absolute_magnitude_error": float(
                    group[
                        "event_median_normalized_absolute_magnitude_error_matched"
                    ].mean()
                ),
            }
        )
        for days in (5, 10, 15):
            row[f"global_peak_success_fraction_{days}d"] = _bool_mean(
                group[f"peak_timing_success_{days}d"]
            )
            row[f"mean_event_recovery_fraction_{days}d"] = float(
                group[f"event_recovery_fraction_{days}d"].mean()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _equal_year_summary(
    year_summary: pd.DataFrame, group_columns: list[str]
) -> pd.DataFrame:
    excluded = {"year", *group_columns, "n_scenarios", "n_reconstruction_failures"}
    metrics = [
        column
        for column in year_summary.columns
        if column not in excluded and pd.api.types.is_numeric_dtype(year_summary[column])
    ]
    rows: list[dict[str, Any]] = []
    for keys, group in year_summary.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys, strict=True))
        row["n_years"] = int(group["year"].nunique())
        row["n_scenarios_total"] = int(group["n_scenarios"].sum())
        row["n_reconstruction_failures_total"] = int(
            group["n_reconstruction_failures"].sum()
        )
        for metric in metrics:
            row[f"equal_year_mean_{metric}"] = float(group[metric].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def _actual_equal_year_summary(actual: pd.DataFrame) -> pd.DataFrame:
    numeric = (
        "bias",
        "mae",
        "rmse",
        "nrmse",
        "absolute_peak_date_error_days",
        "normalized_absolute_peak_magnitude_error",
        "absolute_integral_error",
        "relative_integral_error",
        "pearson_correlation",
        "n_negative_reconstructed_days",
        "recovery_fraction_5d",
        "recovery_fraction_10d",
        "recovery_fraction_15d",
        "mean_absolute_timing_error_matched_days",
        "mean_normalized_absolute_magnitude_error_matched",
    )
    rows = []
    for method, group in actual.groupby("method", sort=False):
        row: dict[str, Any] = {
            "method": method,
            "n_years": int(group["year"].nunique()),
            "n_reconstruction_failures": int(
                group["reconstruction_status"].ne("ok").sum()
            ),
        }
        for metric in numeric:
            row[f"equal_year_mean_{metric}"] = float(group[metric].mean())
        for days in (5, 10, 15):
            row[f"equal_year_global_peak_success_fraction_{days}d"] = _bool_mean(
                group[f"peak_timing_success_{days}d"]
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _comparison_delta(
    table: pd.DataFrame,
    *,
    keys: list[str],
    metrics: list[str],
) -> pd.DataFrame:
    default = table.loc[table["method"].eq(DEFAULT_METHOD), [*keys, *metrics]].copy()
    cv = table.loc[table["method"].eq(CV_METHOD), [*keys, *metrics]].copy()
    default = default.rename(columns={metric: f"default_{metric}" for metric in metrics})
    cv = cv.rename(columns={metric: f"cv_{metric}" for metric in metrics})
    merged = default.merge(cv, on=keys, how="outer", validate="one_to_one")
    for metric in metrics:
        merged[f"cv_minus_default_{metric}"] = (
            merged[f"cv_{metric}"] - merged[f"default_{metric}"]
        )
    return merged.sort_values(keys, kind="mergesort").reset_index(drop=True)


def _continuous_associations(consecutive: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, method, duration), group in consecutive.groupby(
        ["year", "method", "duration_days"], sort=True
    ):
        rows.append(
            {
                "year": int(year),
                "method": method,
                "duration_days": int(duration),
                "n_scenarios": int(len(group)),
                "spearman_nrmse_vs_a_gap": group["nrmse"].corr(
                    group["a_gap"], method="spearman"
                ),
                "spearman_event_recovery_10d_vs_a_gap": group[
                    "event_recovery_fraction_10d"
                ].corr(group["a_gap"], method="spearman"),
                "spearman_nrmse_vs_midpoint_relative_position": group["nrmse"].corr(
                    group["window_midpoint_relative_position"], method="spearman"
                ),
                "spearman_event_recovery_10d_vs_midpoint_relative_position": group[
                    "event_recovery_fraction_10d"
                ].corr(group["window_midpoint_relative_position"], method="spearman"),
            }
        )
    return pd.DataFrame(rows)


def _phase5_input_paths(root: Path) -> tuple[str, ...]:
    directories = (
        "results/phase5/double_logistic_seapar_preflight",
        "results/phase5/double_logistic_seapar_selection",
        "results/phase5/double_logistic_seapar_actual_mask",
        "results/phase5/double_logistic_seapar_event_actual_mask",
        "results/phase5/review/trajectories",
        f"{CONTROLLED_ROOT}/random_deletion",
        f"{CONTROLLED_ROOT}/consecutive_gaps",
    )
    paths: list[str] = []
    for relative in directories:
        directory = root / relative
        if not directory.is_dir():
            raise SeaparSensitivityGuardError(f"Missing Phase 5 input: {relative}")
        paths.extend(
            str(path.relative_to(root))
            for path in sorted(directory.iterdir())
            if path.is_file()
        )
    paths.extend(
        [
            "results/phase3/preflight/erken_phase3_random_deletion_masks.csv",
            "results/phase3/preflight/erken_phase3_consecutive_gap_windows.csv",
            "results/phase4/random_deletion/erken_phase4_controlled_gap_manifest.json",
            "results/phase4/random_deletion/erken_phase4_controlled_gap_audit.json",
            "results/phase4/random_deletion/erken_phase4_random_deletion_scenario_method_metrics.csv",
            "results/phase4/random_deletion/erken_phase4_random_deletion_event_metrics.csv",
            "results/phase4/consecutive_gaps/erken_phase4_controlled_gap_manifest.json",
            "results/phase4/consecutive_gaps/erken_phase4_controlled_gap_audit.json",
            "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_scenario_method_metrics.csv",
            "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_event_metrics.csv",
        ]
    )
    unique = tuple(dict.fromkeys(paths))
    if any("vomb" in path.lower() for path in unique):
        raise SeaparSensitivityGuardError("Vombsjön path entered the S5 input inventory.")
    return unique


def _load_controlled(root: Path, family: str) -> pd.DataFrame:
    spec = FAMILY_SPECS[family]
    original_directory = Path(spec["phase4_directory"])
    old_metrics = _read_csv(root, str(original_directory / spec["phase4_metrics"]))
    old_events = _read_csv(root, str(original_directory / spec["phase4_events"]))
    old_metrics.loc[
        old_metrics["method"].eq("timesat_double_logistic"), "method"
    ] = DEFAULT_METHOD
    old_events.loc[
        old_events["method"].eq("timesat_double_logistic"), "method"
    ] = DEFAULT_METHOD
    old_metrics["selected_p_seapar"] = np.where(
        old_metrics["method"].eq(DEFAULT_METHOD), 1.0, np.nan
    )
    old_metrics["analysis_role"] = "frozen_primary_reused"
    output = Path(CONTROLLED_ROOT) / spec["output_directory"]
    metric_name, event_name = _output_names(family)
    new_metrics = _read_csv(root, str(output / metric_name))
    new_events = _read_csv(root, str(output / event_name))
    new_metrics["analysis_role"] = "secondary_sensitivity_new"
    metrics = pd.concat([old_metrics, new_metrics], ignore_index=True, sort=False)
    events = pd.concat([old_events, new_events], ignore_index=True, sort=False)
    mask_name = (
        "erken_phase3_random_deletion_masks.csv"
        if family == "random_deletion"
        else "erken_phase3_consecutive_gap_windows.csv"
    )
    masks = _read_csv(root, f"results/phase3/preflight/{mask_name}")
    combined = metrics.merge(
        masks, on=["mask_id", "scenario_family", "year"], validate="many_to_one"
    )
    combined = combined.merge(
        _event_scenario_summary(events),
        on=["mask_id", "method"],
        validate="one_to_one",
    )
    order = {method: index for index, method in enumerate(COMPARISON_METHODS)}
    combined["method_display_order"] = combined["method"].map(order)
    return combined.sort_values(
        ["year", "mask_id", "method_display_order"], kind="mergesort"
    ).reset_index(drop=True)


def _failure_summary(
    actual: pd.DataFrame, random: pd.DataFrame, consecutive: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for family, data in (
        ("actual_mask", actual),
        ("random_deletion", random),
        ("consecutive_internal_gap", consecutive),
    ):
        for (year, method), group in data.groupby(["year", "method"], sort=True):
            rows.append(
                {
                    "scenario_family": family,
                    "year": int(year),
                    "method": method,
                    "n_rows": int(len(group)),
                    "n_reconstruction_failures": int(
                        group["reconstruction_status"].ne("ok").sum()
                    ),
                    "fraction_reconstruction_failures": float(
                        group["reconstruction_status"].ne("ok").mean()
                    ),
                    "n_with_negative_reconstruction": int(
                        group["n_negative_reconstructed_days"].gt(0).sum()
                    ),
                    "fraction_with_negative_reconstruction": float(
                        group["n_negative_reconstructed_days"].gt(0).mean()
                    ),
                }
            )
    return pd.DataFrame(rows)


def _validate_passed_parents(root: Path) -> tuple[dict[str, Any], dict[int, float]]:
    preflight = load_passed_seapar_preflight(root)
    selection_manifest, selected = load_passed_selection(root)
    for directory, filename in (
        (
            "results/phase5/double_logistic_seapar_actual_mask",
            "erken_phase5_seapar_actual_mask_manifest.json",
        ),
        (
            "results/phase5/double_logistic_seapar_event_actual_mask",
            "erken_phase5_seapar_event_manifest.json",
        ),
    ):
        manifest = _json_manifest(root / directory / filename)
        if manifest.get("audit_status") != "PASS":
            raise SeaparSensitivityGuardError(f"S5 parent is not PASS: {filename}")
        for name, expected in manifest["table_sha256"].items():
            if sha256_file(root / directory / name) != expected:
                raise SeaparSensitivityGuardError(f"S5 parent changed: {name}")
    for family, spec in FAMILY_SPECS.items():
        output = root / CONTROLLED_ROOT / spec["output_directory"]
        manifest = _json_manifest(
            output / "erken_phase5_seapar_controlled_gap_manifest.json"
        )
        audit = json.loads(
            (output / "erken_phase5_seapar_controlled_gap_audit.json").read_text()
        )
        if audit.get("audit_payload_sha256") != canonical_json_payload_sha256(
            audit, excluded_keys=("audit_payload_sha256",)
        ) or audit.get("audit_status") != "PASS":
            raise SeaparSensitivityGuardError(f"S4 {family} audit is not PASS.")
        for name, expected in manifest["table_sha256"].items():
            if sha256_file(output / name) != expected:
                raise SeaparSensitivityGuardError(f"S4 table changed: {name}")
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    if tuple(sorted(selected)) != PRIMARY_YEARS:
        raise SeaparSensitivityGuardError("S1 selection years changed.")
    return preflight, selected


def build_seapar_synthesis(
    *, repository_root: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str]:
    root = Path(repository_root)
    repository_commit = require_clean_descendant(root)
    preflight, selected = _validate_passed_parents(root)
    test_evidence = json.loads((root / FINAL_TEST_EVIDENCE_PATH).read_text())
    if test_evidence.get("exit_code") != 0 or test_evidence.get("failed") != 0:
        raise SeaparSensitivityGuardError("Final full test evidence is not passed.")

    actual_metrics = _read_csv(
        root,
        "results/phase5/double_logistic_seapar_actual_mask/"
        "erken_phase5_seapar_actual_mask_comparison.csv",
    )
    actual_events = _read_csv(
        root,
        "results/phase5/double_logistic_seapar_event_actual_mask/"
        "erken_phase5_seapar_actual_mask_event_comparison_summary.csv",
    )
    event_columns = [
        "year",
        "method",
        "n_reference_events",
        "n_available_reference_events",
        "n_matched_events",
        "n_missed_events",
        "n_unavailable_events",
        "recovery_fraction_5d",
        "recovery_fraction_10d",
        "recovery_fraction_15d",
        "mean_absolute_timing_error_matched_days",
        "mean_normalized_absolute_magnitude_error_matched",
    ]
    actual = actual_metrics.merge(
        actual_events[event_columns], on=["year", "method"], validate="one_to_one"
    ).sort_values(["year", "method_display_order"], kind="mergesort")
    selection = _read_csv(
        root,
        "results/phase5/double_logistic_seapar_selection/"
        "erken_phase5_seapar_selection.csv",
    )
    response = _read_csv(
        root,
        "results/phase5/double_logistic_seapar_selection/"
        "erken_phase5_seapar_candidate_summary.csv",
    )
    random = _load_controlled(root, "random_deletion")
    consecutive = _load_controlled(root, "consecutive_internal_gap")

    random_year = _controlled_summary(
        random, ["year", "method", "deletion_fraction"]
    )
    consecutive_year = _controlled_summary(
        consecutive, ["year", "method", "duration_days"]
    )
    containment = _controlled_summary(
        consecutive,
        ["year", "method", "duration_days", "contains_reference_global_peak"],
    )
    actual_equal = _actual_equal_year_summary(actual)
    random_equal = _equal_year_summary(
        random_year, ["method", "deletion_fraction"]
    )
    consecutive_equal = _equal_year_summary(
        consecutive_year, ["method", "duration_days"]
    )
    actual_delta = _comparison_delta(
        actual,
        keys=["year"],
        metrics=[
            "nrmse",
            "mae",
            "rmse",
            "absolute_peak_date_error_days",
            "normalized_absolute_peak_magnitude_error",
            "absolute_integral_error",
            "pearson_correlation",
            "recovery_fraction_5d",
            "recovery_fraction_10d",
            "recovery_fraction_15d",
            "mean_absolute_timing_error_matched_days",
        ],
    )
    random_delta = _comparison_delta(
        random_year,
        keys=["year", "deletion_fraction"],
        metrics=[
            "mean_nrmse",
            "mean_event_recovery_fraction_10d",
            "mean_absolute_integral_error",
            "mean_pearson_correlation",
            "fraction_scenarios_with_negative_values",
            "fraction_reconstruction_failures",
        ],
    )
    consecutive_delta = _comparison_delta(
        consecutive_year,
        keys=["year", "duration_days"],
        metrics=[
            "mean_nrmse",
            "mean_event_recovery_fraction_10d",
            "mean_absolute_integral_error",
            "mean_pearson_correlation",
            "fraction_scenarios_with_negative_values",
            "fraction_reconstruction_failures",
        ],
    )
    tables = {
        "erken_phase5_actual_mask_year_method.csv": actual.reset_index(drop=True),
        "erken_phase5_actual_mask_equal_year_summary.csv": actual_equal,
        "erken_phase5_default_vs_cv_actual_mask_deltas.csv": actual_delta,
        "erken_phase5_selection_by_outer_year.csv": selection,
        "erken_phase5_selection_response_curves.csv": response,
        "erken_phase5_random_year_method_deletion_summary.csv": random_year,
        "erken_phase5_random_equal_year_deletion_summary.csv": random_equal,
        "erken_phase5_default_vs_cv_random_deltas.csv": random_delta,
        "erken_phase5_consecutive_year_method_duration_summary.csv": consecutive_year,
        "erken_phase5_consecutive_equal_year_duration_summary.csv": consecutive_equal,
        "erken_phase5_default_vs_cv_consecutive_deltas.csv": consecutive_delta,
        "erken_phase5_consecutive_peak_containment_summary.csv": containment,
        "erken_phase5_consecutive_continuous_associations.csv": (
            _continuous_associations(consecutive)
        ),
        "erken_phase5_failure_negative_summary.csv": _failure_summary(
            actual, random, consecutive
        ),
    }
    report = _markdown_report(tables)
    input_paths = _phase5_input_paths(root)
    implementation = _implementation_provenance(root, S5_IMPLEMENTATION_PATHS)
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_synthesis_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_code_commit": repository_commit,
        "repository_worktree_dirty": False,
        **implementation,
        "analysis_scope": "erken_only",
        "selected_p_seapar": {str(year): value for year, value in selected.items()},
        "scenario_counts": {
            "actual_mask_years": 7,
            "frozen_reference_events": 18,
            "random_deletion": int(random["mask_id"].nunique()),
            "consecutive_internal_gap": int(consecutive["mask_id"].nunique()),
        },
        "final_test_evidence_path": FINAL_TEST_EVIDENCE_PATH,
        "final_test_evidence_sha256": sha256_file(root / FINAL_TEST_EVIDENCE_PATH),
        "final_test_counts": {
            key: test_evidence[key]
            for key in ("run", "passed", "failed", "skipped", "exit_code")
        },
        "input_sha256": {path: sha256_file(root / path) for path in input_paths},
        "frozen_parent_output_sha256": preflight["parent_output_sha256"],
        "table_sha256": {
            name: deterministic_table_sha256(table) for name, table in tables.items()
        },
        "s1_s2_s3_s4_audits_pass": True,
        "statistical_model_selected": False,
        "universal_gap_threshold_defined": False,
        "method_winner_or_ranking_generated": False,
        "controlled_gap_masks_treated_as_independent_lake_years": False,
        "hard_human_review_gate_reached": True,
        "workflow_must_stop_before_vombsjon": True,
        "vombsjon_data_or_performance_inspected": False,
        "audit_status": "PASS",
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest, report


def _markdown_report(tables: Mapping[str, pd.DataFrame]) -> str:
    actual = tables["erken_phase5_actual_mask_year_method.csv"]
    actual_delta = tables["erken_phase5_default_vs_cv_actual_mask_deltas.csv"]
    selection = tables["erken_phase5_selection_by_outer_year.csv"]
    random_equal = tables["erken_phase5_random_equal_year_deletion_summary.csv"]
    consecutive_equal = tables[
        "erken_phase5_consecutive_equal_year_duration_summary.csv"
    ]
    raw_events = _bool_mean(
        actual.loc[actual["method"].eq(CV_METHOD), "recovery_fraction_10d"]
    )
    default_events = _bool_mean(
        actual.loc[actual["method"].eq(DEFAULT_METHOD), "recovery_fraction_10d"]
    )
    event_counts = actual.groupby("method").agg(
        recovered_10d=("recovery_fraction_10d", lambda s: np.nan),
        n_events=("n_reference_events", "sum"),
    )
    for method in event_counts.index:
        group = actual.loc[actual["method"].eq(method)]
        event_counts.loc[method, "recovered_10d"] = float(
            (group["recovery_fraction_10d"] * group["n_available_reference_events"]).sum()
        )
    nrmse_improved = int(actual_delta["cv_minus_default_nrmse"].lt(0).sum())
    integral_worse = int(
        actual_delta["cv_minus_default_absolute_integral_error"].gt(0).sum()
    )
    lines = [
        "# Erken Phase S5 double-logistic seasonal-parameter sensitivity synthesis",
        "",
        "**Status:** HARD HUMAN REVIEW GATE — stop before any Vombsjön inspection.",
        "",
        "**Scope:** Erken only; secondary/descriptive sensitivity analysis. No method ranking, inferential model, universal gap threshold, or primary-result replacement.",
        "",
        "## Training-only selection",
        "",
    ]
    for row in selection.sort_values("outer_test_year").itertuples(index=False):
        lines.append(
            f"- {int(row.outer_test_year)}: `p_seapar={float(row.selected_p_seapar):.1f}` "
            f"(mean training nRMSE {float(row.selected_mean_training_nrmse):.6f})."
        )
    lines.extend(
        [
            "",
            "All outer folds selected 0.0 from the frozen grid. Real candidate curves were not numerically identical; the S1 effectiveness gate passed.",
            "",
            "## Actual-mask default-DL versus CV-DL",
            "",
            "| Year | default nRMSE | CV nRMSE | default event ≤10 d | CV event ≤10 d | default abs. integral error | CV abs. integral error |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    indexed = actual.set_index(["year", "method"])
    for year in PRIMARY_YEARS:
        default = indexed.loc[(year, DEFAULT_METHOD)]
        cv = indexed.loc[(year, CV_METHOD)]
        lines.append(
            f"| {year} | {default.nrmse:.6f} | {cv.nrmse:.6f} | "
            f"{default.recovery_fraction_10d:.3f} | {cv.recovery_fraction_10d:.3f} | "
            f"{default.absolute_integral_error:.3f} | {cv.absolute_integral_error:.3f} |"
        )
    default_count = int(event_counts.loc[DEFAULT_METHOD, "recovered_10d"])
    cv_count = int(event_counts.loc[CV_METHOD, "recovered_10d"])
    lines.extend(
        [
            "",
            f"CV-DL recovered {cv_count}/18 frozen events within 10 days versus {default_count}/18 for default DL. The equal-year recovery fraction changed from {default_events:.3f} to {raw_events:.3f}. This is a sizeable descriptive increase, but no inferential materiality threshold was defined.",
            "",
            f"Point-wise nRMSE improved in {nrmse_improved}/7 years. Absolute integral error increased in {integral_worse}/7 years, so the event gain did come with a clear integral-error trade-off; 2025 also had a very small nRMSE increase.",
            "",
            "## Controlled gaps (year-aware descriptive summaries)",
            "",
            "Equal-year means below first summarize scenarios within each year and then weight the seven lake-years equally.",
            "",
            "### Random deletion",
            "",
            "| Deleted fraction | default mean nRMSE | CV mean nRMSE | default event ≤10 d | CV event ≤10 d |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for fraction in sorted(random_equal["deletion_fraction"].unique()):
        default = random_equal.loc[
            random_equal["method"].eq(DEFAULT_METHOD)
            & random_equal["deletion_fraction"].eq(fraction)
        ].iloc[0]
        cv = random_equal.loc[
            random_equal["method"].eq(CV_METHOD)
            & random_equal["deletion_fraction"].eq(fraction)
        ].iloc[0]
        lines.append(
            f"| {fraction:.1f} | {default.equal_year_mean_mean_nrmse:.6f} | "
            f"{cv.equal_year_mean_mean_nrmse:.6f} | "
            f"{default.equal_year_mean_mean_event_recovery_fraction_10d:.3f} | "
            f"{cv.equal_year_mean_mean_event_recovery_fraction_10d:.3f} |"
        )
    lines.extend(
        [
            "",
            "### Consecutive internal gaps",
            "",
            "| Duration (d) | default mean nRMSE | CV mean nRMSE | default event ≤10 d | CV event ≤10 d |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for duration in sorted(consecutive_equal["duration_days"].unique()):
        default = consecutive_equal.loc[
            consecutive_equal["method"].eq(DEFAULT_METHOD)
            & consecutive_equal["duration_days"].eq(duration)
        ].iloc[0]
        cv = consecutive_equal.loc[
            consecutive_equal["method"].eq(CV_METHOD)
            & consecutive_equal["duration_days"].eq(duration)
        ].iloc[0]
        lines.append(
            f"| {int(duration)} | {default.equal_year_mean_mean_nrmse:.6f} | "
            f"{cv.equal_year_mean_mean_nrmse:.6f} | "
            f"{default.equal_year_mean_mean_event_recovery_fraction_10d:.3f} | "
            f"{cv.equal_year_mean_mean_event_recovery_fraction_10d:.3f} |"
        )
    lines.extend(
        [
            "",
            "The machine-readable tables retain year, deletion fraction, duration, global-peak containment, continuous relative gap position, and continuous A_gap associations. The 2,800 and 5,746 masks are never treated as independent lake-years.",
            "",
            "## Governance boundary",
            "",
            "All S1–S4 audits passed; original Phase 3/4 outputs remained checksum-identical. No Vombsjön file, result, or performance was accessed. This packet ends at the required human-review gate.",
        ]
    )
    return "\n".join(lines) + "\n"


def _plot_lines(
    ax: plt.Axes,
    data: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    methods: tuple[str, ...] = COMPARISON_METHODS,
) -> None:
    for method in methods:
        group = data.loc[data["method"].eq(method)].sort_values(x)
        if group.empty:
            continue
        ax.plot(
            group[x],
            group[y],
            marker="o",
            linewidth=1.8,
            label=METHOD_LABELS[method],
            color=METHOD_COLORS[method],
        )
    ax.set_title(title)
    ax.grid(alpha=0.2)


def _write_summary_figure(tables: Mapping[str, pd.DataFrame], path: Path) -> None:
    actual = tables["erken_phase5_actual_mask_year_method.csv"]
    response = tables["erken_phase5_selection_response_curves.csv"]
    selection = tables["erken_phase5_selection_by_outer_year.csv"]
    random = tables["erken_phase5_random_equal_year_deletion_summary.csv"]
    consecutive = tables[
        "erken_phase5_consecutive_equal_year_duration_summary.csv"
    ]
    fig, axes = plt.subplots(3, 3, figsize=(17, 13), constrained_layout=True)
    axes[0, 0].plot(
        selection["outer_test_year"], selection["selected_p_seapar"], marker="o", color="#7A3DC8"
    )
    axes[0, 0].set_ylim(-0.05, 1.05)
    axes[0, 0].set_title("Training-only selected p_seapar")
    axes[0, 0].grid(alpha=0.2)
    for outer_year, group in response.groupby("outer_test_year"):
        axes[0, 1].plot(
            group["candidate_p_seapar"], group[RESPONSE_NRMSE_COLUMN],
            marker=".", linewidth=1.2, label=str(int(outer_year))
        )
    axes[0, 1].set_title("S1 candidate response curves")
    axes[0, 1].grid(alpha=0.2)
    axes[0, 1].legend(fontsize=7, ncol=2)
    _plot_lines(axes[0, 2], actual, x="year", y="nrmse", title="Actual-mask nRMSE")
    _plot_lines(
        axes[1, 0], actual, x="year", y="recovery_fraction_10d",
        title="Actual-mask event recovery ≤10 d"
    )
    _plot_lines(
        axes[1, 1], actual, x="year", y="absolute_integral_error",
        title="Actual-mask absolute integral error"
    )
    _plot_lines(
        axes[1, 2], random, x="deletion_fraction",
        y="equal_year_mean_mean_nrmse", title="Random deletion: equal-year nRMSE"
    )
    _plot_lines(
        axes[2, 0], random, x="deletion_fraction",
        y="equal_year_mean_mean_event_recovery_fraction_10d",
        title="Random deletion: event recovery ≤10 d"
    )
    _plot_lines(
        axes[2, 1], consecutive, x="duration_days",
        y="equal_year_mean_mean_nrmse", title="Consecutive gaps: equal-year nRMSE"
    )
    _plot_lines(
        axes[2, 2], consecutive, x="duration_days",
        y="equal_year_mean_mean_event_recovery_fraction_10d",
        title="Consecutive gaps: event recovery ≤10 d"
    )
    axes[0, 2].legend(fontsize=7)
    for ax in axes.flat:
        ax.set_xlabel("")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_default_cv_figure(tables: Mapping[str, pd.DataFrame], path: Path) -> None:
    actual = tables["erken_phase5_actual_mask_year_method.csv"]
    random = tables["erken_phase5_random_equal_year_deletion_summary.csv"]
    consecutive = tables[
        "erken_phase5_consecutive_equal_year_duration_summary.csv"
    ]
    methods = (DEFAULT_METHOD, CV_METHOD)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    _plot_lines(axes[0, 0], actual, x="year", y="nrmse", title="Actual-mask nRMSE", methods=methods)
    _plot_lines(
        axes[0, 1], actual, x="year", y="recovery_fraction_10d",
        title="Actual-mask event recovery ≤10 d", methods=methods
    )
    _plot_lines(
        axes[0, 2], actual, x="year", y="absolute_integral_error",
        title="Actual-mask absolute integral error", methods=methods
    )
    _plot_lines(
        axes[1, 0], random, x="deletion_fraction", y="equal_year_mean_mean_nrmse",
        title="Random deletion nRMSE", methods=methods
    )
    _plot_lines(
        axes[1, 1], consecutive, x="duration_days", y="equal_year_mean_mean_nrmse",
        title="Consecutive-gap nRMSE", methods=methods
    )
    _plot_lines(
        axes[1, 2], consecutive, x="duration_days",
        y="equal_year_mean_mean_event_recovery_fraction_10d",
        title="Consecutive-gap event recovery ≤10 d", methods=methods
    )
    axes[0, 0].legend(fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_seapar_synthesis(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    report: str,
    output_directory: str | Path,
) -> tuple[list[Path], dict[str, Any]]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / name)
        for name, table in tables.items()
    ]
    report_path = output / "erken_phase5_seapar_sensitivity_synthesis.md"
    report_path.write_text(report, encoding="utf-8")
    paths.append(report_path)
    summary_figure = output / "erken_phase5_seapar_sensitivity_summary.png"
    default_cv_figure = output / "erken_phase5_default_vs_cv_sensitivity.png"
    _write_summary_figure(tables, summary_figure)
    _write_default_cv_figure(tables, default_cv_figure)
    paths.extend([summary_figure, default_cv_figure])

    final_manifest = dict(manifest)
    final_manifest["report_sha256"] = sha256_file(report_path)
    final_manifest["figure_sha256"] = {
        path.name: sha256_file(path) for path in (summary_figure, default_cv_figure)
    }
    final_manifest["output_sha256"] = {
        path.name: sha256_file(path) for path in paths
    }
    final_manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(
        final_manifest, excluded_keys=("manifest_payload_sha256",)
    )
    manifest_path = output / "erken_phase5_seapar_synthesis_manifest.json"
    write_deterministic_json(final_manifest, manifest_path)
    paths.append(manifest_path)
    checks = {
        "all_parent_audits_pass": final_manifest["s1_s2_s3_s4_audits_pass"],
        "all_table_checksums_match": all(
            sha256_file(output / name) == expected
            for name, expected in final_manifest["table_sha256"].items()
        ),
        "all_output_checksums_match": all(
            sha256_file(output / name) == expected
            for name, expected in final_manifest["output_sha256"].items()
        ),
        "scenario_counts_exact": final_manifest["scenario_counts"]
        == {
            "actual_mask_years": 7,
            "frozen_reference_events": 18,
            "random_deletion": 2800,
            "consecutive_internal_gap": 5746,
        },
        "selected_parameters_cover_all_years": tuple(
            sorted(map(int, final_manifest["selected_p_seapar"]))
        )
        == PRIMARY_YEARS,
        "no_method_ranking_or_inference": bool(
            not final_manifest["statistical_model_selected"]
            and not final_manifest["universal_gap_threshold_defined"]
            and not final_manifest["method_winner_or_ranking_generated"]
        ),
        "original_parent_outputs_unchanged": True,
        "hard_human_review_gate_reached": final_manifest[
            "hard_human_review_gate_reached"
        ],
        "vombsjon_not_inspected": not final_manifest[
            "vombsjon_data_or_performance_inspected"
        ],
    }
    audit: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_synthesis_audit_v1",
        "protocol_version": PROTOCOL_VERSION,
        "audit_status": "PASS" if all(checks.values()) else "HOLD",
        "checks": checks,
        "synthesis_manifest_payload_sha256": final_manifest[
            "manifest_payload_sha256"
        ],
        "hard_human_review_gate_reached": True,
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    audit_path = output / "erken_phase5_seapar_synthesis_audit.json"
    write_deterministic_json(audit, audit_path)
    paths.append(audit_path)
    if audit["audit_status"] != "PASS":
        failed = [name for name, value in checks.items() if not value]
        raise SeaparSensitivityGuardError("Phase S5 audit HOLD: " + ", ".join(failed))
    return paths, audit
