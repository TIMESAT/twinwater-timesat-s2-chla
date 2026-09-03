"""Year-aware, non-tuning Phase D synthesis of frozen Erken results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.seasonal_events import PROTOCOL_VERSION


INPUT_PATHS = (
    "results/phase3/actual_mask/erken_phase3_actual_mask_benchmark_manifest.json",
    "results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv",
    "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_benchmark_manifest.json",
    "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_metrics.csv",
    "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_year_method_summary.csv",
    "results/phase4/random_deletion/erken_phase4_controlled_gap_manifest.json",
    "results/phase4/random_deletion/erken_phase4_controlled_gap_audit.json",
    "results/phase4/random_deletion/erken_phase4_random_deletion_scenario_method_metrics.csv",
    "results/phase4/random_deletion/erken_phase4_random_deletion_event_metrics.csv",
    "results/phase4/consecutive_gaps/erken_phase4_controlled_gap_manifest.json",
    "results/phase4/consecutive_gaps/erken_phase4_controlled_gap_audit.json",
    "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_scenario_method_metrics.csv",
    "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_event_metrics.csv",
    "results/phase3/preflight/erken_phase3_random_deletion_masks.csv",
    "results/phase3/preflight/erken_phase3_consecutive_gap_windows.csv",
)


def _require_clean(root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if status:
        raise RuntimeError("Phase D synthesis requires a clean committed worktree.")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _read_csv(root: Path, relative: str) -> pd.DataFrame:
    return pd.read_csv(root / relative, low_memory=False)


def _event_scenario_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (mask_id, method), group in events.groupby(["mask_id", "method"], sort=True):
        available = group["event_status"].ne("unavailable")
        row: dict[str, Any] = {
            "mask_id": mask_id,
            "method": method,
            "event_reference_count": len(group),
            "event_matched_count": int(group["event_status"].eq("matched").sum()),
            "event_missed_count": int(
                group["event_status"].eq("missed_no_peak_within_15d").sum()
            ),
            "event_unavailable_count": int(group["event_status"].eq("unavailable").sum()),
        }
        for days in (5, 10, 15):
            row[f"event_recovery_fraction_{days}d"] = (
                float(group.loc[available, f"success_{days}d"].astype(bool).mean())
                if available.any()
                else np.nan
            )
        matched = group["event_status"].eq("matched")
        row["event_median_absolute_timing_error_matched_days"] = float(
            group.loc[matched, "absolute_timing_error_days"].median()
        )
        row["event_median_normalized_absolute_magnitude_error_matched"] = float(
            group.loc[matched, "normalized_absolute_magnitude_error"].median()
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _summary(data: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in data.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys, strict=True))
        row.update(
            {
                "n_scenarios": len(group),
                "n_reconstruction_failures": int(
                    group["reconstruction_status"].ne("ok").sum()
                ),
                "mean_nrmse": float(group["nrmse"].mean()),
                "median_nrmse": float(group["nrmse"].median()),
                "mean_absolute_global_peak_timing_error_days": float(
                    group["absolute_peak_date_error_days"].mean()
                ),
                "median_absolute_global_peak_timing_error_days": float(
                    group["absolute_peak_date_error_days"].median()
                ),
                "global_peak_success_fraction_10d": float(
                    group["peak_timing_success_10d"].dropna().astype(bool).mean()
                ),
                "mean_event_recovery_fraction_10d": float(
                    group["event_recovery_fraction_10d"].mean()
                ),
                "median_event_recovery_fraction_10d": float(
                    group["event_recovery_fraction_10d"].median()
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
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


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
                "n_scenarios": len(group),
                "spearman_nrmse_vs_a_gap": group["nrmse"].corr(
                    group["a_gap"], method="spearman"
                ),
                "spearman_nrmse_vs_midpoint_relative_position": group["nrmse"].corr(
                    group["window_midpoint_relative_position"], method="spearman"
                ),
                "spearman_global_peak_abs_error_vs_a_gap": group[
                    "absolute_peak_date_error_days"
                ].corr(group["a_gap"], method="spearman"),
                "spearman_event_recovery_10d_vs_a_gap": group[
                    "event_recovery_fraction_10d"
                ].corr(group["a_gap"], method="spearman"),
            }
        )
    return pd.DataFrame(rows)


def build_synthesis_products(
    *, repository_root: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str]:
    root = Path(repository_root)
    commit = _require_clean(root)
    for family in ("random_deletion", "consecutive_gaps"):
        audit = json.loads(
            (root / f"results/phase4/{family}/erken_phase4_controlled_gap_audit.json").read_text()
        )
        if audit["audit_status"] != "PASS":
            raise RuntimeError(f"Phase D blocked by {family} audit HOLD.")
    actual = _read_csv(
        root,
        "results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv",
    )
    actual_events = _read_csv(
        root,
        "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_year_method_summary.csv",
    )
    random_metrics = _read_csv(
        root,
        "results/phase4/random_deletion/erken_phase4_random_deletion_scenario_method_metrics.csv",
    )
    random_events = _read_csv(
        root,
        "results/phase4/random_deletion/erken_phase4_random_deletion_event_metrics.csv",
    )
    random_masks = _read_csv(
        root, "results/phase3/preflight/erken_phase3_random_deletion_masks.csv"
    )
    consecutive_metrics = _read_csv(
        root,
        "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_scenario_method_metrics.csv",
    )
    consecutive_events = _read_csv(
        root,
        "results/phase4/consecutive_gaps/erken_phase4_consecutive_gaps_event_metrics.csv",
    )
    consecutive_masks = _read_csv(
        root, "results/phase3/preflight/erken_phase3_consecutive_gap_windows.csv"
    )
    random = random_metrics.merge(random_masks, on=["mask_id", "scenario_family", "year"], validate="many_to_one")
    random = random.merge(_event_scenario_summary(random_events), on=["mask_id", "method"], validate="one_to_one")
    consecutive = consecutive_metrics.merge(
        consecutive_masks, on=["mask_id", "scenario_family", "year"], validate="many_to_one"
    )
    consecutive = consecutive.merge(
        _event_scenario_summary(consecutive_events), on=["mask_id", "method"], validate="one_to_one"
    )
    actual_columns = [
        "year", "method", "reconstruction_status", "nrmse", "mae", "rmse",
        "absolute_peak_date_error_days", "peak_timing_success_5d",
        "peak_timing_success_10d", "peak_timing_success_15d",
        "normalized_absolute_peak_magnitude_error", "absolute_integral_error",
        "pearson_correlation", "n_negative_reconstructed_days",
        "fraction_negative_reconstructed_days", "selected_smoothing",
    ]
    tables = {
        "erken_phase_d_actual_mask_year_method.csv": actual[actual_columns],
        "erken_phase_d_actual_mask_event_year_method.csv": actual_events,
        "erken_phase_d_random_deletion_analysis_ready.csv": random,
        "erken_phase_d_consecutive_gap_analysis_ready.csv": consecutive,
        "erken_phase_d_random_year_method_deletion_summary.csv": _summary(
            random, ["year", "method", "deletion_fraction"]
        ),
        "erken_phase_d_consecutive_year_method_duration_summary.csv": _summary(
            consecutive, ["year", "method", "duration_days"]
        ),
        "erken_phase_d_consecutive_peak_containment_summary.csv": _summary(
            consecutive,
            ["year", "method", "duration_days", "contains_reference_global_peak"],
        ),
        "erken_phase_d_consecutive_continuous_associations.csv": _continuous_associations(
            consecutive
        ),
    }
    failure_rows = []
    for family, data in (
        ("actual_mask", actual),
        ("random_deletion", random),
        ("consecutive_internal_gap", consecutive),
    ):
        for (year, method), group in data.groupby(["year", "method"], sort=True):
            failure_rows.append(
                {
                    "scenario_family": family,
                    "year": int(year),
                    "method": method,
                    "n_rows": len(group),
                    "n_reconstruction_failures": int(group["reconstruction_status"].ne("ok").sum()),
                    "fraction_reconstruction_failures": float(group["reconstruction_status"].ne("ok").mean()),
                    "n_with_negative_reconstruction": int(group["n_negative_reconstructed_days"].gt(0).sum()),
                    "fraction_with_negative_reconstruction": float(group["n_negative_reconstructed_days"].gt(0).mean()),
                }
            )
    tables["erken_phase_d_failure_negative_summary.csv"] = pd.DataFrame(failure_rows)
    report = _markdown_report(actual, actual_events, random, consecutive)
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase_d_synthesis_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "event_protocol_version": PROTOCOL_VERSION,
        "repository_code_commit": commit,
        "repository_worktree_dirty": False,
        "analysis_scope": "erken_only",
        "statistical_model_selected": False,
        "universal_failure_threshold_defined": False,
        "method_winner_generated": False,
        "vombsjon_data_or_performance_inspected": False,
        "input_sha256": {path: sha256_file(root / path) for path in INPUT_PATHS},
        "table_sha256": {name: deterministic_table_sha256(table) for name, table in tables.items()},
        "scenario_counts": {"actual_mask_year_method": 21, "random_deletion": 2800, "consecutive_internal_gap": 5746},
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest, report


def _markdown_report(actual, actual_events, random, consecutive) -> str:
    lines = [
        "# Frozen Erken Phase D descriptive synthesis",
        "",
        "**Scope:** Erken only. Factual/descriptive; no final inferential model, method winner, or universal failure threshold.",
        "",
        "## Actual-mask evidence",
        "",
    ]
    for method in sorted(actual["method"].unique()):
        metrics = actual[actual["method"].eq(method)]
        events = actual_events[actual_events["method"].eq(method)]
        lines.append(
            f"- `{method}`: median year-level nRMSE {metrics['nrmse'].median():.3f}; "
            f"events matched {int(events['n_matched_events'].sum())}/18; "
            f"≤10 d recoveries {events['recovery_fraction_10d'].mul(events['n_available_reference_events']).sum():.0f}/18."
        )
    lines.extend(["", "## Controlled-gap evidence", ""])
    for label, data in (("random deletion", random), ("consecutive gaps", consecutive)):
        lines.append(
            f"- {label}: {data['mask_id'].nunique():,} scenarios; "
            f"{len(data):,} scenario-method rows; "
            f"{int(data['reconstruction_status'].ne('ok').sum())} reconstruction failures."
        )
    lines.extend(
        [
            "",
            "All scenario-level outcomes remain nested within seven years. Analysis-ready tables retain continuous gap activity/position and the frozen mask descriptors.",
            "",
            "## Governance boundary",
            "",
            "No Vombsjön data or performance were read. No method was retuned, no final statistical model was selected, and no universal reliability threshold or method winner was produced.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_synthesis_products(tables: Mapping[str, pd.DataFrame], manifest: Mapping[str, Any], report: str, output: str | Path) -> list[Path]:
    output = Path(output)
    paths = [write_deterministic_csv(table, output / name) for name, table in tables.items()]
    report_path = output / "erken_phase_d_synthesis.md"
    report_path.write_text(report, encoding="utf-8")
    paths.append(report_path)
    figure_path = output / "erken_phase_d_descriptive_summary.png"
    _write_figure(tables, figure_path)
    paths.append(figure_path)
    final_manifest = dict(manifest)
    final_manifest["report_sha256"] = sha256_file(report_path)
    final_manifest["figure_sha256"] = sha256_file(figure_path)
    final_manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(
        final_manifest, excluded_keys=("manifest_payload_sha256",)
    )
    manifest_path = output / "erken_phase_d_synthesis_manifest.json"
    write_deterministic_json(final_manifest, manifest_path)
    paths.append(manifest_path)
    return paths


def _write_figure(tables: Mapping[str, pd.DataFrame], path: Path) -> None:
    actual = tables["erken_phase_d_actual_mask_year_method.csv"]
    event = tables["erken_phase_d_actual_mask_event_year_method.csv"]
    random = tables["erken_phase_d_random_year_method_deletion_summary.csv"]
    consecutive = tables["erken_phase_d_consecutive_year_method_duration_summary.csv"]
    containment = tables["erken_phase_d_consecutive_peak_containment_summary.csv"]
    association = tables["erken_phase_d_consecutive_continuous_associations.csv"]
    failure = tables["erken_phase_d_failure_negative_summary.csv"]
    methods = sorted(actual["method"].unique())
    colors = dict(zip(methods, ("#3366cc", "#dc3912", "#109618"), strict=True))
    fig, axes = plt.subplots(3, 3, figsize=(15, 12), constrained_layout=True)
    for method in methods:
        a = actual[actual["method"].eq(method)]
        axes[0, 0].plot(a["year"], a["nrmse"], marker="o", label=method, color=colors[method])
        axes[0, 1].plot(a["year"], a["absolute_peak_date_error_days"], marker="o", color=colors[method])
        e = event[event["method"].eq(method)]
        axes[0, 2].plot(e["year"], e["recovery_fraction_10d"], marker="o", color=colors[method])
        r = random[random["method"].eq(method)].groupby("deletion_fraction", as_index=False)["median_nrmse"].median()
        axes[1, 0].plot(r["deletion_fraction"], r["median_nrmse"], marker="o", color=colors[method])
        c = consecutive[consecutive["method"].eq(method)].groupby("duration_days", as_index=False)["median_nrmse"].median()
        axes[1, 1].plot(c["duration_days"], c["median_nrmse"], marker="o", color=colors[method])
        co = containment[containment["method"].eq(method)].groupby("contains_reference_global_peak", as_index=False)["median_nrmse"].median()
        axes[1, 2].plot(co["contains_reference_global_peak"].astype(int), co["median_nrmse"], marker="o", color=colors[method])
        aa = association[association["method"].eq(method)].groupby("duration_days", as_index=False)["spearman_nrmse_vs_a_gap"].median()
        axes[2, 0].plot(aa["duration_days"], aa["spearman_nrmse_vs_a_gap"], marker="o", color=colors[method])
        pp = association[association["method"].eq(method)].groupby("duration_days", as_index=False)["spearman_nrmse_vs_midpoint_relative_position"].median()
        axes[2, 1].plot(pp["duration_days"], pp["spearman_nrmse_vs_midpoint_relative_position"], marker="o", color=colors[method])
        ff = failure[failure["method"].eq(method)].groupby("scenario_family", as_index=False)["fraction_with_negative_reconstruction"].median()
        axes[2, 2].plot(range(len(ff)), ff["fraction_with_negative_reconstruction"], marker="o", color=colors[method])
    titles = ["Actual-mask nRMSE", "Global peak absolute timing error", "Seasonal-event recovery ≤10 d", "Random deletion: year-first median nRMSE", "Consecutive duration: year-first median nRMSE", "Gap contains global peak", "nRMSE vs continuous A_gap (Spearman)", "nRMSE vs relative position (Spearman)", "Negative-reconstruction fraction"]
    for ax, title in zip(axes.flat, titles, strict=True):
        ax.set_title(title)
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    axes[2, 2].set_xticks(range(3), ["actual", "consecutive", "random"], rotation=20)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)
