#!/usr/bin/env python3
"""Run the isolated Erken actual-mask TIMESAT mechanism diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.mechanism_diagnostic import (  # noqa: E402
    COARSE_SMOOTHING_GRID,
    DIAGNOSTIC_VERSION,
    PART_A_METHODS,
    P_SEAPAR_GRID,
    MechanismRuntime,
    build_interval_geometry_table,
    classify_mechanism_case,
    equal_year_summary,
    evaluate_curve,
    evaluate_event_curve,
    nearest_peak_diagnostic,
    p_seapar_to_internal_smoothing,
    runtime_request,
    summarize_event_recovery,
)
from twinwater_timesat.phase3_contract import (  # noqa: E402
    canonical_json_payload_sha256,
    load_timesat_defaults_snapshot,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (  # noqa: E402
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_support import (  # noqa: E402
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.timesat_adapter import SubprocessTimesatRunner  # noqa: E402


OUTPUT_ROOT = ROOT / "results/diagnostics/erken_timesat_mechanism_v1"
FROZEN_PARENT_FILES = (
    ROOT / "results/phase3/actual_mask/erken_phase3_actual_mask_benchmark_manifest.json",
    ROOT / "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv",
    ROOT / "results/phase3/actual_mask/erken_phase3_spline_selection.csv",
    ROOT / "results/phase3/event_preflight/erken_phase3_event_preperformance_gate.json",
    ROOT / "results/phase3/event_preflight/erken_phase3_reference_events.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get(
            "TIMESAT_PYTHON", "/Users/zzcai/.venvs/twinwater-timesat-4.4.1/bin/python"
        ),
    )
    parser.add_argument(
        "--diagnostic-site-packages",
        type=Path,
        default=Path(
            "/private/tmp/timesat-diagnostic-install/lib/python3.12/site-packages"
        ),
    )
    parser.add_argument(
        "--diagnostic-library-path",
        type=Path,
        default=Path("/private/tmp/timesat-diag-toolchain/lib"),
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _sha256_bytes(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype=np.float64).tobytes()).hexdigest()


def _hash_frozen_results() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in FROZEN_PARENT_FILES
    }


def _assert_all_frozen_results_unmodified() -> None:
    changed = _git(
        "diff",
        "--name-only",
        "add063e89a47b31605c354d3c4cdb87b01412056",
        "--",
        "results/phase3",
        "results/phase4",
        "results/phase5",
    )
    if changed:
        raise RuntimeError(f"Frozen Phase 3/4/5 outputs differ from main:\n{changed}")


def _reference_events() -> pd.DataFrame:
    return pd.read_csv(
        ROOT / "results/phase3/event_preflight/erken_phase3_reference_events.csv",
        parse_dates=[
            "event_time",
            "event_date",
            "plateau_start_time",
            "plateau_end_time",
        ],
    )


def _selection() -> dict[int, int]:
    table = pd.read_csv(
        ROOT / "results/phase3/actual_mask/erken_phase3_spline_selection.csv"
    )
    return dict(
        zip(
            table["outer_test_year"].astype(int),
            table["selected_smoothing"].astype(int),
            strict=True,
        )
    )


def _frozen_curve(daily: pd.DataFrame, year: int, method: str) -> pd.DataFrame:
    curve = daily.loc[
        daily["outer_test_year"].eq(year) & daily["method"].eq(method),
        ["date", "prediction"],
    ].copy()
    curve["date"] = pd.to_datetime(curve["date"])
    return curve.sort_values("date").reset_index(drop=True)


def _plot_part_a(
    output: Path,
    support: pd.DataFrame,
    curves: pd.DataFrame,
    intervals: pd.DataFrame,
    selected: dict[int, int],
) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    colors = {
        "linear_interpolation": "#6c757d",
        "timesat_smoothing_spline_0": "#d55e00",
        "timesat_smoothing_spline_selected": "#0072b2",
    }
    labels = {
        "linear_interpolation": "Linear",
        "timesat_smoothing_spline_0": "TIMESAT spline, p_smooth=0",
        "timesat_smoothing_spline_selected": "Frozen selected TIMESAT spline",
    }

    def draw(ax: plt.Axes, year: int) -> None:
        ysupport = support.loc[support["year"].eq(year) & support["common_support"]]
        ycurves = curves.loc[curves["year"].eq(year)]
        ax.plot(ysupport["date"], ysupport["CHLF"], color="black", lw=1.1, label="Daily reference")
        sparse = ysupport.loc[ysupport["s2_openwater_reference_candidate"]]
        ax.scatter(sparse["date"], sparse["CHLF"], color="black", s=15, zorder=5, label="Sparse input")
        for method in PART_A_METHODS:
            curve = ycurves.loc[ycurves["method"].eq(method)]
            ax.plot(curve["date"], curve["prediction"], color=colors[method], lw=1.2, label=labels[method])
        ax.set_title(f"{year} (selected spline={selected[year]})", loc="left", fontsize=10)
        ax.set_ylabel("CHLF")
        ax.grid(alpha=0.2)

    paths: list[Path] = []
    figure, axes = plt.subplots(7, 1, figsize=(15, 21), constrained_layout=True)
    for ax, year in zip(axes, range(2019, 2026), strict=True):
        draw(ax, year)
    axes[0].legend(ncol=4, fontsize=8, loc="upper right")
    figure.suptitle("A1 — Erken spline-0 versus linear and frozen selected spline")
    path = output / "A1_spline0_vs_linear_overview_2019_2025.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    paths.append(path)

    for year in range(2019, 2026):
        figure, ax = plt.subplots(figsize=(14, 5), constrained_layout=True)
        draw(ax, year)
        ax.legend(ncol=4, fontsize=8)
        path = output / f"A2_spline0_vs_linear_{year}.png"
        figure.savefig(path, dpi=180)
        plt.close(figure)
        paths.append(path)

    eligible = intervals.loc[intervals["interval_status"].eq("ok")]
    zoom_specs = {
        "normalized_overshoot": eligible.loc[
            eligible["normalized_max_absolute_overshoot"].idxmax()
        ],
        "rmse_disadvantage": eligible.loc[
            eligible["spline0_minus_linear_withheld_rmse"].idxmax()
        ],
    }
    for name, row in zoom_specs.items():
        year = int(row["year"])
        start = pd.Timestamp(row["interval_start_date"]) - pd.Timedelta(days=7)
        end = pd.Timestamp(row["interval_end_date"]) + pd.Timedelta(days=7)
        figure, ax = plt.subplots(figsize=(12, 5), constrained_layout=True)
        draw(ax, year)
        ax.set_xlim(start, end)
        ax.axvspan(row["interval_start_date"], row["interval_end_date"], color="#f0e442", alpha=0.18)
        ax.legend(ncol=2, fontsize=8)
        ax.set_title(
            f"A3 — {name.replace('_', ' ')}: {year}, "
            f"{pd.Timestamp(row['interval_start_date']):%Y-%m-%d} to "
            f"{pd.Timestamp(row['interval_end_date']):%Y-%m-%d}"
        )
        path = output / f"A3_worst_{name}.png"
        figure.savefig(path, dpi=180)
        plt.close(figure)
        paths.append(path)

    figure, ax = plt.subplots(figsize=(9, 6), constrained_layout=True)
    for year, group in eligible.groupby("year"):
        ax.scatter(group["gap_length_days"], group["spline0_minus_linear_withheld_rmse"], s=22, alpha=0.75, label=str(year))
    ax.axhline(0, color="black", lw=0.8)
    ax.set(xlabel="Gap length (calendar days)", ylabel="Withheld RMSE: spline-0 minus linear", title="A4 — Interval RMSE difference versus gap length")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(alpha=0.2)
    path = output / "A4_interval_rmse_difference_vs_gap_length.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    paths.append(path)

    figure, ax = plt.subplots(figsize=(9, 6), constrained_layout=True)
    for year, group in eligible.groupby("year"):
        ax.scatter(group["gap_length_days"], group["normalized_max_absolute_overshoot"], s=22, alpha=0.75, label=str(year))
    ax.set(xlabel="Gap length (calendar days)", ylabel="Normalized maximum endpoint-range overshoot", title="A5 — Spline-0 overshoot versus gap length")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(alpha=0.2)
    path = output / "A5_normalized_overshoot_vs_gap_length.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    paths.append(path)
    return paths


def _part_a(
    output: Path,
    support: pd.DataFrame,
    references: pd.DataFrame,
    selected: dict[int, int],
    runner: SubprocessTimesatRunner,
) -> tuple[dict[str, pd.DataFrame], list[Path]]:
    frozen = pd.read_csv(
        ROOT / "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv",
        parse_dates=["date"],
    )
    curve_rows: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    event_rows: list[pd.DataFrame] = []
    for year in range(2019, 2026):
        ysupport = support.loc[support["year"].eq(year)].copy()
        common = ysupport.loc[ysupport["common_support"]]
        sparse = ysupport.loc[ysupport["s2_openwater_reference_candidate"], ["date", "CHLF"]]
        spline0_result = runner.reconstruct(
            method="timesat_smoothing_spline",
            year=year,
            sparse=sparse,
            target_dates=common["date"],
            smoothing=0,
        )
        if spline0_result.status != "ok":
            raise RuntimeError(f"Spline-0 failed for {year}: {spline0_result.failure_reason}")
        method_curves = {
            "linear_interpolation": _frozen_curve(frozen, year, "linear_interpolation"),
            "timesat_smoothing_spline_0": spline0_result.prediction,
            "timesat_smoothing_spline_selected": _frozen_curve(
                frozen, year, "timesat_smoothing_spline"
            ),
        }
        yreferences = references.loc[references["year"].eq(year)].copy()
        for method, curve in method_curves.items():
            curve = common[
                [
                    "date",
                    "year",
                    "CHLF",
                    "s2_openwater_reference_candidate",
                    "common_support_segment_id",
                ]
            ].merge(curve, on="date", validate="one_to_one")
            curve.insert(1, "method", method)
            curve["selected_spline_smoothing"] = selected[year] if method.endswith("selected") else np.nan
            curve_rows.append(curve)
            metric_rows.append(evaluate_curve(ysupport, curve[["date", "prediction"]], method=method))
            event_rows.append(
                evaluate_event_curve(
                    ysupport,
                    yreferences,
                    curve[["date", "prediction"]],
                    method=method,
                )
            )
    curves = pd.concat(curve_rows, ignore_index=True)
    events = pd.concat(event_rows, ignore_index=True)
    recovery = summarize_event_recovery(events)
    metrics = pd.DataFrame(metric_rows).merge(recovery, on=["year", "method"], validate="one_to_one")
    intervals = build_interval_geometry_table(support, curves, selected)
    tables = {
        "erken_spline0_vs_linear_daily_curves.csv": curves,
        "erken_spline0_vs_linear_year_metrics.csv": metrics,
        "erken_spline0_vs_linear_equal_year_summary.csv": equal_year_summary(metrics),
        "erken_spline0_vs_linear_event_metrics.csv": events,
        "erken_spline0_vs_linear_interval_geometry.csv": intervals,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        write_deterministic_csv(table, output / name)
    figures = _plot_part_a(output, support, curves, intervals, selected)
    return tables, figures


def _peaks_table(
    result: dict[str, Any], year_support: pd.DataFrame, scenario: dict[str, Any]
) -> pd.DataFrame:
    records = result["mechanism_diagnostic"]["filtered_peaks_central_year"]
    peaks = pd.DataFrame(records)
    if peaks.empty:
        peaks = pd.DataFrame(columns=["full_extended_index", "central_year_index", "peak_time"])
    peaks["peak_time"] = pd.to_datetime(peaks["peak_time"])
    mapping = year_support.loc[
        year_support["common_support"], ["date", "common_support_segment_id"]
    ]
    peaks = peaks.merge(mapping, left_on="peak_time", right_on="date", how="left")
    peaks.drop(columns="date", inplace=True)
    for key, value in reversed(list(scenario.items())):
        peaks.insert(0, key, value)
    peaks["inside_frozen_common_support"] = peaks["common_support_segment_id"].notna()
    return peaks


def _runtime_curve(
    result: dict[str, Any], year_support: pd.DataFrame, scenario: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    final = pd.DataFrame({"date": pd.to_datetime(result["dates"]), "prediction": result["prediction"]})
    coarse = pd.DataFrame(
        {
            "date": pd.to_datetime(result["mechanism_diagnostic"]["coarse_dates"]),
            "coarse_prediction": result["mechanism_diagnostic"]["coarse_curve"],
        }
    )
    support_columns = [
        "date",
        "year",
        "CHLF",
        "common_support",
        "s2_openwater_reference_candidate",
        "common_support_segment_id",
    ]
    final = year_support[support_columns].merge(final, on="date", how="left", validate="one_to_one")
    coarse = year_support[support_columns].merge(coarse, on="date", how="left", validate="one_to_one")
    for key, value in reversed(list(scenario.items())):
        if key in final.columns:
            if not final[key].eq(value).all() or not coarse[key].eq(value).all():
                raise RuntimeError(f"Scenario field {key!r} conflicts with support data.")
            continue
        final.insert(0, key, value)
        coarse.insert(0, key, value)
    return final, coarse


def _scenario_summary(
    result: dict[str, Any],
    year_support: pd.DataFrame,
    final: pd.DataFrame,
    peaks: pd.DataFrame,
    event_rows: pd.DataFrame,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    common_curve = final.loc[final["common_support"], ["date", "prediction"]]
    metric = evaluate_curve(year_support, common_curve, method=str(scenario["scenario_id"]))
    from twinwater_timesat.reconstruction_metrics import evaluate_seasonal_metrics

    seasonal = evaluate_seasonal_metrics(year_support, common_curve)
    available = event_rows["event_status"].ne("unavailable")
    diagnostic = result["mechanism_diagnostic"]
    row: dict[str, Any] = {
        **scenario,
        **{key: value for key, value in metric.items() if key not in {"year", "method"}},
        "reconstruction_failure_reason": result["failure_reason"],
        "actual_internal_coarse_smoothing": diagnostic["actual_internal_coarse_smoothing"],
        "base_value": diagnostic["base_value"],
        "coarse_error_flag": diagnostic["coarse_error_flag"],
        "raw_peak_count_full_extended": diagnostic["raw_peak_count_full_extended"],
        "filtered_peak_count_full_extended": diagnostic["filtered_peak_count_full_extended"],
        "initialized_season_count_full_extended": diagnostic["initialized_season_count_full_extended"],
        "filtered_peak_count_central_year": int(len(peaks)),
        "filtered_peak_count_common_support": int(peaks["inside_frozen_common_support"].sum()),
        "filtered_peak_dates_common_support": ";".join(
            peaks.loc[peaks["inside_frozen_common_support"], "peak_time"].dt.strftime("%Y-%m-%d")
        ),
        "final_numseason_output": ";".join(map(str, result["diagnostics"]["nseason"])),
        "reference_integral": seasonal.get("reference_integral"),
        "reconstruction_integral": seasonal.get("reconstruction_integral"),
        "signed_integral_error": seasonal.get("signed_integral_error"),
        "absolute_integral_error": seasonal.get("absolute_integral_error"),
        "relative_integral_error": seasonal.get("relative_integral_error"),
        "n_reference_events": int(len(event_rows)),
        "n_matched_events": int(event_rows["event_status"].eq("matched").sum()),
    }
    for days in (5, 10, 15):
        row[f"event_recovery_{days}d"] = float(
            event_rows.loc[available, f"success_{days}d"].astype(bool).mean()
        )
    return row


def _plot_part_b(
    output: Path,
    support: pd.DataFrame,
    final: pd.DataFrame,
    coarse: pd.DataFrame,
    peaks: pd.DataFrame,
    summary: pd.DataFrame,
) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    selected_grid = [1000.0, 100.0, 10.0, 0.0]
    colors = {1000.0: "#0072b2", 100.0: "#009e73", 10.0: "#e69f00", 0.0: "#d55e00"}
    paths: list[Path] = []
    for year in range(2019, 2026):
        ys = support.loc[support["year"].eq(year) & support["common_support"]]
        figure, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, constrained_layout=True)
        for ax in axes:
            ax.plot(ys["date"], ys["CHLF"], color="black", lw=1.1, label="Daily reference")
            sparse = ys.loc[ys["s2_openwater_reference_candidate"]]
            ax.scatter(sparse["date"], sparse["CHLF"], color="black", s=14, zorder=5, label="Sparse input")
        for smoothing in selected_grid:
            c = coarse.loc[(coarse["year"].eq(year)) & (coarse["coarse_smoothing"].eq(smoothing)) & coarse["common_support"]]
            axes[0].plot(c["date"], c["coarse_prediction"], color=colors[smoothing], lw=1.2, label=f"coarse={smoothing:g}")
            p = peaks.loc[(peaks["year"].eq(year)) & (peaks["coarse_smoothing"].eq(smoothing)) & peaks["inside_frozen_common_support"]]
            if not p.empty:
                heights = c.set_index("date")["coarse_prediction"].reindex(p["peak_time"]).to_numpy()
                axes[0].scatter(p["peak_time"], heights, color=colors[smoothing], marker="v", s=25)
            f = final.loc[(final["year"].eq(year)) & (final["coarse_smoothing"].eq(smoothing)) & final["common_support"]]
            axes[1].plot(f["date"], f["prediction"], color=colors[smoothing], lw=1.2, label=f"final DL, coarse={smoothing:g}")
        axes[0].set_title(f"B2 — {year}: internal coarse seasonal curves and filtered peaks")
        axes[1].set_title("Corresponding final double-logistic curves")
        for ax in axes:
            ax.set_ylabel("CHLF")
            ax.grid(alpha=0.2)
            ax.legend(ncol=3, fontsize=8)
        path = output / f"B2_coarse_and_final_double_logistic_{year}.png"
        figure.savefig(path, dpi=180)
        plt.close(figure)
        paths.append(path)

    for year in (2020, 2025):
        ys = support.loc[support["year"].eq(year) & support["common_support"]]
        figure, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True, constrained_layout=True)
        for smoothing in selected_grid:
            c = coarse.loc[(coarse["year"].eq(year)) & (coarse["coarse_smoothing"].eq(smoothing)) & coarse["common_support"]]
            f = final.loc[(final["year"].eq(year)) & (final["coarse_smoothing"].eq(smoothing)) & final["common_support"]]
            axes[0].plot(c["date"], c["coarse_prediction"], color=colors[smoothing], lw=1.4, label=f"coarse={smoothing:g}")
            axes[1].plot(f["date"], f["prediction"], color=colors[smoothing], lw=1.4, label=f"coarse={smoothing:g}")
        for ax in axes:
            ax.plot(ys["date"], ys["CHLF"], color="black", lw=0.9, alpha=0.65, label="Daily reference")
            ax.scatter(ys.loc[ys["s2_openwater_reference_candidate"], "date"], ys.loc[ys["s2_openwater_reference_candidate"], "CHLF"], color="black", s=18, zorder=5)
            ax.grid(alpha=0.2)
            ax.legend(ncol=3, fontsize=8)
            ax.set_ylabel("CHLF")
        axes[0].set_title(f"Detailed internal coarse-season mechanism — {year}")
        axes[1].set_title("Detailed final double-logistic response")
        path = output / f"B2_detailed_mechanism_{year}.png"
        figure.savefig(path, dpi=200)
        plt.close(figure)
        paths.append(path)

    labels = [f"{value:g}" for value in COARSE_SMOOTHING_GRID]
    x = np.arange(len(labels))
    fields = [
        ("filtered_peak_count_common_support", "Filtered coarse peaks"),
        ("nrmse", "Withheld nRMSE"),
        ("event_recovery_10d", "Event recovery ≤10 d"),
        ("absolute_integral_error", "Absolute integral error"),
    ]
    figure, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    for ax, (field, title) in zip(axes.ravel(), fields, strict=True):
        for year, group in summary.groupby("year"):
            ordered = group.set_index("coarse_smoothing").reindex(COARSE_SMOOTHING_GRID)
            ax.plot(x, ordered[field], marker="o", ms=3, lw=1, label=str(year))
        ax.set_xticks(x, labels)
        ax.set_xlabel("Direct coarse smoothing")
        ax.set_title(title)
        ax.grid(alpha=0.2)
    axes[0, 0].legend(ncol=2, fontsize=8)
    figure.suptitle("B2 — Per-year response across the direct coarse-smoothing grid")
    path = output / "B2_coarse_smoothing_response_summary.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    paths.append(path)
    return paths


def _default_equivalence(
    runtime: MechanismRuntime,
    production: SubprocessTimesatRunner,
    support: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    frozen_daily = pd.read_csv(
        ROOT / "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv",
        parse_dates=["date"],
    )
    for year in range(2019, 2026):
        ys = support.loc[support["year"].eq(year)].copy()
        sparse = ys.loc[ys["s2_openwater_reference_candidate"], ["date", "CHLF"]]
        full_dates = pd.date_range(f"{year}-01-01", periods=365, freq="D")
        prod = production.reconstruct(
            method="timesat_double_logistic",
            year=year,
            sparse=sparse,
            target_dates=full_dates,
        )
        diag = runtime.run(runtime_request(ys, p_seapar=1.0, coarse_smoothing_override=None))
        a = prod.prediction["prediction"].to_numpy(float)
        b = np.asarray(diag["prediction"], dtype=float)
        frozen = _frozen_curve(frozen_daily, year, "timesat_double_logistic")
        diagnostic_by_date = pd.Series(b, index=pd.to_datetime(diag["dates"]))
        diagnostic_frozen_support = diagnostic_by_date.reindex(frozen["date"]).to_numpy(float)
        frozen_values = frozen["prediction"].to_numpy(float)
        rows.append(
            {
                "year": year,
                "production_final_curve_sha256": _sha256_bytes(a),
                "diagnostic_final_curve_sha256": _sha256_bytes(b),
                "final_curve_byte_equal": bool(a.tobytes() == b.tobytes()),
                "maximum_absolute_final_curve_difference": float(np.max(np.abs(a - b))),
                "frozen_saved_common_support_curve_sha256": _sha256_bytes(frozen_values),
                "diagnostic_common_support_curve_sha256": _sha256_bytes(diagnostic_frozen_support),
                "frozen_saved_common_support_curve_byte_equal": bool(
                    frozen_values.tobytes() == diagnostic_frozen_support.tobytes()
                ),
                "maximum_absolute_frozen_saved_curve_difference": float(
                    np.max(np.abs(frozen_values - diagnostic_frozen_support))
                ),
                "production_numseason_output": ";".join(map(str, prod.diagnostics["nseason"])),
                "diagnostic_numseason_output": ";".join(map(str, diag["diagnostics"]["nseason"])),
                "auxiliary_numseason_equal": prod.diagnostics["nseason"] == diag["diagnostics"]["nseason"],
                "actual_internal_coarse_smoothing": diag["mechanism_diagnostic"]["actual_internal_coarse_smoothing"],
            }
        )
    table = pd.DataFrame(rows)
    if not (
        table["final_curve_byte_equal"].all()
        and table["frozen_saved_common_support_curve_byte_equal"].all()
    ):
        raise RuntimeError(
            "Diagnostic build does not reproduce production and frozen saved final "
            "daily curves byte-for-byte."
        )
    return table


def _part_b(
    output: Path,
    support: pd.DataFrame,
    references: pd.DataFrame,
    runtime: MechanismRuntime,
    production: SubprocessTimesatRunner,
) -> tuple[dict[str, pd.DataFrame], list[Path]]:
    equivalence = _default_equivalence(runtime, production, support)
    all_tables: dict[str, pd.DataFrame] = {"default_build_equivalence.csv": equivalence}

    for family, grid in (("p_seapar", P_SEAPAR_GRID), ("coarse_smoothing", COARSE_SMOOTHING_GRID)):
        final_rows: list[pd.DataFrame] = []
        coarse_rows: list[pd.DataFrame] = []
        peak_rows: list[pd.DataFrame] = []
        event_rows: list[pd.DataFrame] = []
        summaries: list[dict[str, Any]] = []
        for year in range(2019, 2026):
            ys = support.loc[support["year"].eq(year)].copy()
            yrefs = references.loc[references["year"].eq(year)].copy()
            for value in grid:
                if family == "p_seapar":
                    p_seapar = float(value)
                    override = None
                    scenario = {
                        "year": year,
                        "scenario_id": f"B1_{year}_p_seapar_{value:.1f}",
                        "p_seapar": p_seapar,
                        "mapped_coarse_smoothing": p_seapar_to_internal_smoothing(p_seapar),
                    }
                else:
                    p_seapar = 1.0
                    override = float(value)
                    scenario = {
                        "year": year,
                        "scenario_id": f"B2_{year}_coarse_{value:g}",
                        "p_seapar": p_seapar,
                        "coarse_smoothing": float(value),
                    }
                result = runtime.run(
                    runtime_request(
                        ys,
                        p_seapar=p_seapar,
                        coarse_smoothing_override=override,
                    )
                )
                final, coarse = _runtime_curve(result, ys, scenario)
                peaks = _peaks_table(result, ys, scenario)
                common_final = final.loc[final["common_support"], ["date", "prediction"]]
                events = evaluate_event_curve(
                    ys, yrefs, common_final, method=scenario["scenario_id"]
                )
                for key, item in reversed(list(scenario.items())):
                    if key not in {"year", "scenario_id"}:
                        events.insert(3, key, item)
                events["scenario_id"] = scenario["scenario_id"]
                summaries.append(_scenario_summary(result, ys, final, peaks, events, scenario))
                final_rows.append(final)
                coarse_rows.append(coarse)
                peak_rows.append(peaks)
                event_rows.append(events)
        prefix = "B1_p_seapar" if family == "p_seapar" else "B2_direct_coarse_smoothing"
        family_tables = {
            f"{prefix}_summary.csv": pd.DataFrame(summaries),
            f"{prefix}_final_daily_curves.csv": pd.concat(final_rows, ignore_index=True),
            f"{prefix}_coarse_daily_curves.csv": pd.concat(coarse_rows, ignore_index=True),
            f"{prefix}_filtered_peaks.csv": pd.concat(peak_rows, ignore_index=True),
            f"{prefix}_event_metrics.csv": pd.concat(event_rows, ignore_index=True),
        }
        all_tables.update(family_tables)

    b2_summary = all_tables["B2_direct_coarse_smoothing_summary.csv"]
    b2_final = all_tables["B2_direct_coarse_smoothing_final_daily_curves.csv"]
    b2_coarse = all_tables["B2_direct_coarse_smoothing_coarse_daily_curves.csv"]
    b2_peaks = all_tables["B2_direct_coarse_smoothing_filtered_peaks.csv"]
    b2_events = all_tables["B2_direct_coarse_smoothing_event_metrics.csv"]
    key_rows: list[dict[str, Any]] = []
    for summary_row in b2_summary.itertuples(index=False):
        year = int(summary_row.year)
        smoothing = float(summary_row.coarse_smoothing)
        scenario_id = str(summary_row.scenario_id)
        scenario_peaks = b2_peaks.loc[
            b2_peaks["scenario_id"].eq(scenario_id)
            & b2_peaks["inside_frozen_common_support"]
        ]
        scenario_events = b2_events.loc[b2_events["scenario_id"].eq(scenario_id)].set_index("event_id")
        for reference in references.loc[references["year"].eq(year)].itertuples(index=False):
            nearest = nearest_peak_diagnostic(
                pd.Timestamp(reference.event_time),
                str(reference.common_support_segment_id),
                scenario_peaks,
            )
            final_event = scenario_events.loc[reference.event_id]
            key_rows.append(
                {
                    "year": year,
                    "scenario_id": scenario_id,
                    "coarse_smoothing": smoothing,
                    "event_id": reference.event_id,
                    "reference_event_time": reference.event_time,
                    **nearest,
                    "final_event_status": final_event["event_status"],
                    "final_double_logistic_matched": final_event["event_status"] == "matched",
                    "final_double_logistic_event_time": final_event["reconstructed_event_time"],
                    "final_double_logistic_signed_timing_error_days": final_event["signed_timing_error_days"],
                    "final_double_logistic_absolute_timing_error_days": final_event["absolute_timing_error_days"],
                    "mechanism_case": classify_mechanism_case(
                        nearest["coarse_peak_exists_within_15d"],
                        str(final_event["event_status"]),
                    ),
                }
            )
    all_tables["B2_event_coarse_to_final_mechanism_table.csv"] = pd.DataFrame(key_rows)

    output.mkdir(parents=True, exist_ok=True)
    for name, table in all_tables.items():
        write_deterministic_csv(table, output / name)
    figures = _plot_part_b(output, support, b2_final, b2_coarse, b2_peaks, b2_summary)
    return all_tables, figures


def _write_source_trace(path: Path) -> None:
    path.write_text(
        """# TIMESAT 4.4.1 double-logistic coarse-season source trace

Diagnostic scope: frozen core source commit `b20844140bf38543349552341212609fa18b24b1`.
No production source or configuration was changed.

## `p_seapar` mapping and coarse curve

In `fortran/season.f90`, subroutine `season` starts at line 4. Lines 46–56 map
`seasonpar` to the smoothing-spline control and build the preliminary daily curve:

```fortran
pval = 1000.d0 + (50000.d0 - 1000.d0) * seasonpar
if (pval < 1000.d0) pval = 1000.d0
if (pval > 50000.d0) pval = 50000.d0
call smoothingspline(...,pval,yfit(...),...)
```

Thus `p_seapar=0` maps exactly to `1000`, and `p_seapar=1` maps to `50000`.
Lines 57–70 extend the ends and clamp the preliminary curve to the base.

## Peak detection and filtering

`season.f90:95` calls `findallpeaks(yfit,...)`. The state machine is implemented in
`fortran/findallpeaks.f90:29–79`. `season.f90:107–130` then rejects unsupported
lobes and peaks below 1% of the largest preliminary peak; lines 132–147 remove
peaks separated by fewer than five internal days. Lines 158–160 call the internal
`initialdlpar`, which derives 20/50/80% transition positions and can reject seasons
without observation support (`season.f90:166–263`).

## Control of the final double logistic

`fortran/processtimeseries.f90:195–197` passes `p_seapar` to `season`, receiving
the preliminary curve, initial double-logistic parameters and season count. For
`fitmethod=1`, lines 207–214 call `processdl` with those initial parameters.
`fortran/processdl.f90:40–55` calls `findoddpoints` and `fitlogistic2`, then applies
the final range clamp. The preliminary curve therefore controls detected seasons
and initialization, while `processdl` controls the final nonlinear fit.

## One-pixel instrumentation

The diagnostic patch records the absolute preliminary curve immediately after the
base clamp, raw and filtered peak indices, actual `pval`, and initialized-season
count. An explicit override is applied only after the frozen mapping/clamp and only
in the isolated diagnostic build. With the override disabled, all seven final
365-day Erken curves are byte-identical to the frozen production binary.
""",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if _git("rev-parse", "--abbrev-ref", "HEAD") != "diagnostic/erken-timesat-mechanism":
        raise RuntimeError("This diagnostic may run only on diagnostic/erken-timesat-mechanism.")
    _assert_all_frozen_results_unmodified()
    before = _hash_frozen_results()
    output = args.output_root
    part_a_output = output / "spline0_vs_linear"
    part_b_output = output / "double_logistic_coarse_season"
    support = build_common_support(
        read_phase3_master(ROOT / "data/processed/erken_temporal_sampling_master.csv")
    )
    references = _reference_events()
    selected = _selection()
    snapshot_path = ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    production = SubprocessTimesatRunner(
        python_executable=args.timesat_python,
        runtime_script=ROOT / "scripts/07_timesat_runtime.py",
        snapshot_path=snapshot_path,
    )
    production_runtime = production.verify_runtime(smoke_test=True)
    part_a_tables, part_a_figures = _part_a(
        part_a_output, support, references, selected, production
    )
    with MechanismRuntime(
        Path(args.timesat_python),
        ROOT / "scripts/26_timesat_mechanism_runtime.py",
        ROOT,
        args.diagnostic_site_packages,
        args.diagnostic_library_path,
    ) as diagnostic:
        part_b_tables, part_b_figures = _part_b(
            part_b_output, support, references, diagnostic, production
        )
    source_trace = output / "double_logistic_coarse_season_source_trace.md"
    output.mkdir(parents=True, exist_ok=True)
    _write_source_trace(source_trace)
    after = _hash_frozen_results()
    if before != after:
        raise RuntimeError("A frozen Phase 3/4/5 result changed during the diagnostic.")
    _assert_all_frozen_results_unmodified()

    patch_path = ROOT / "diagnostics/timesat_mechanism_v1/timesat_v4.4.1_instrumentation.patch"
    binary_path = args.diagnostic_site_packages / "timesat/_timesat.cpython-312-darwin.so"
    manifest_path = output / "erken_timesat_mechanism_diagnostic_manifest.json"
    generated = sorted(
        path for path in output.rglob("*")
        if path.is_file() and path != manifest_path
    )
    manifest: dict[str, Any] = {
        "schema_version": "erken_timesat_mechanism_diagnostic_manifest_v1",
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "analysis_classification": "diagnostic_only_no_production_selection",
        "repository_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "repository_code_commit": _git("rev-parse", "HEAD"),
        "canonical_main_base_commit": "add063e89a47b31605c354d3c4cdb87b01412056",
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "matplotlib_version": matplotlib.__version__,
        "frozen_timesat_source_commit": snapshot["timesat_core"]["source_git_commit"],
        "frozen_timesat_version": snapshot["timesat_core"]["version"],
        "frozen_timesat_cli_version": snapshot["timesat_cli"]["version"],
        "frozen_production_binary_sha256": snapshot["timesat_core"]["observed_build_artifacts"][0]["sha256"],
        "diagnostic_binary_sha256": sha256_file(binary_path),
        "instrumentation_patch_sha256": sha256_file(patch_path),
        "production_runtime_probe": production_runtime,
        "part_a_methods": list(PART_A_METHODS),
        "p_seapar_grid": list(P_SEAPAR_GRID),
        "direct_coarse_smoothing_grid": list(COARSE_SMOOTHING_GRID),
        "actual_mask_years": list(range(2019, 2026)),
        "frozen_sparse_input_count": int(support["s2_openwater_reference_candidate"].sum()),
        "frozen_reference_event_count": int(len(references)),
        "default_final_curve_byte_equivalence_all_years": bool(
            part_b_tables["default_build_equivalence.csv"]["final_curve_byte_equal"].all()
        ),
        "default_frozen_saved_curve_byte_equivalence_all_years": bool(
            part_b_tables["default_build_equivalence.csv"][
                "frozen_saved_common_support_curve_byte_equal"
            ].all()
        ),
        "frozen_parent_results_unchanged": before == after,
        "frozen_relevant_parent_file_count": len(before),
        "frozen_relevant_parent_file_sha256": before,
        "all_phase3_phase4_phase5_paths_equal_to_main_base": True,
        "production_parameter_selected": False,
        "production_parameter_recommended": False,
        "controlled_gap_outputs_read_or_generated": False,
        "vombsjon_read_or_generated": False,
        "generated_file_sha256": {
            str(path.relative_to(output)): sha256_file(path) for path in generated
        },
        "part_a_table_rows": {name: len(table) for name, table in part_a_tables.items()},
        "part_b_table_rows": {name: len(table) for name, table in part_b_tables.items()},
        "part_a_figure_count": len(part_a_figures),
        "part_b_figure_count": len(part_b_figures),
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    write_deterministic_json(manifest, manifest_path)
    print(json.dumps({"manifest": str(manifest_path), "generated_files": len(generated) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
