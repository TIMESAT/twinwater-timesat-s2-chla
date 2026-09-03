"""Deterministic review figures for frozen Erken actual-mask trajectories."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from twinwater_timesat.phase3_contract import (
    PRIMARY_YEARS,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.seasonal_events import EXPECTED_EVENT_TIMES


METHOD_LABELS = {
    "linear_interpolation": "Linear interpolation",
    "timesat_double_logistic": "TIMESAT double logistic",
    "timesat_smoothing_spline": "TIMESAT smoothing spline",
}
METHOD_COLORS = {
    "linear_interpolation": "#0072B2",
    "timesat_double_logistic": "#D55E00",
    "timesat_smoothing_spline": "#009E73",
}
REFERENCE_COLOR = "#202020"
SPARSE_COLOR = "#CC79A7"

SOURCE_PATHS = {
    "daily_trajectories": (
        "results/phase3/actual_mask/"
        "erken_phase3_actual_mask_daily_reconstructions.csv"
    ),
    "actual_mask_manifest": (
        "results/phase3/actual_mask/"
        "erken_phase3_actual_mask_benchmark_manifest.json"
    ),
    "reference_events": (
        "results/phase3/event_preflight/erken_phase3_reference_events.csv"
    ),
    "event_preflight_manifest": (
        "results/phase3/event_preflight/"
        "erken_phase3_event_preperformance_gate.json"
    ),
    "actual_mask_event_metrics": (
        "results/phase3/event_actual_mask/"
        "erken_phase3_actual_mask_event_metrics.csv"
    ),
    "actual_mask_event_manifest": (
        "results/phase3/event_actual_mask/"
        "erken_phase3_actual_mask_event_benchmark_manifest.json"
    ),
}

FIGURE_FILENAMES = (
    "erken_actual_mask_trajectories_overview_2019_2025.png",
    *(f"erken_actual_mask_trajectory_{year}.png" for year in PRIMARY_YEARS),
    *(f"erken_actual_mask_trajectory_events_{year}.png" for year in PRIMARY_YEARS),
    "erken_linear_overview_2019_2025.png",
    "erken_double_logistic_overview_2019_2025.png",
    "erken_smoothing_spline_overview_2019_2025.png",
    "erken_2020_zoom_spring.png",
    "erken_2020_zoom_august.png",
    "erken_2020_zoom_september.png",
    "erken_2025_zoom_spring.png",
    "erken_2025_zoom_summer.png",
    "erken_2025_zoom_october.png",
)

ZOOM_WINDOWS = {
    "erken_2020_zoom_spring.png": (2020, "2020-03-15", "2020-05-20"),
    "erken_2020_zoom_august.png": (2020, "2020-07-20", "2020-08-25"),
    "erken_2020_zoom_september.png": (2020, "2020-08-20", "2020-09-30"),
    "erken_2025_zoom_spring.png": (2025, "2025-03-21", "2025-05-01"),
    "erken_2025_zoom_summer.png": (2025, "2025-06-20", "2025-09-15"),
    "erken_2025_zoom_october.png": (2025, "2025-09-25", "2025-10-31"),
}


def _git_clean_commit(root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("Trajectory figure generation requires a clean worktree.")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_frozen_plot_sources(root: str | Path) -> dict[str, Any]:
    """Load and cross-check only committed frozen actual-mask products."""

    root = Path(root)
    paths = {name: root / relative for name, relative in SOURCE_PATHS.items()}
    before = {name: sha256_file(path) for name, path in paths.items()}
    actual_manifest = json.loads(paths["actual_mask_manifest"].read_text())
    daily_expected = actual_manifest["table_sha256"][paths["daily_trajectories"].name]
    if before["daily_trajectories"] != daily_expected:
        raise RuntimeError("Frozen actual-mask daily trajectory checksum mismatch.")
    event_preflight = json.loads(paths["event_preflight_manifest"].read_text())
    if before["reference_events"] != event_preflight["reference_event_table_sha256"]:
        raise RuntimeError("Frozen reference-event table checksum mismatch.")
    event_manifest = json.loads(paths["actual_mask_event_manifest"].read_text())
    if before["actual_mask_event_metrics"] != event_manifest["table_sha256"][
        paths["actual_mask_event_metrics"].name
    ]:
        raise RuntimeError("Frozen actual-mask event metrics checksum mismatch.")
    daily = pd.read_csv(paths["daily_trajectories"], parse_dates=["date"])
    events = pd.read_csv(paths["reference_events"], parse_dates=["event_time"])
    matches = pd.read_csv(
        paths["actual_mask_event_metrics"],
        parse_dates=["reference_event_time", "reconstructed_event_time"],
    )
    if list(zip(events["event_id"], events["event_date"], strict=True)) != list(
        EXPECTED_EVENT_TIMES
    ):
        raise RuntimeError("Reference event IDs/dates differ from the frozen set.")
    if tuple(sorted(daily["outer_test_year"].unique())) != PRIMARY_YEARS:
        raise RuntimeError("Frozen trajectory years changed.")
    if set(daily["method"]) != set(METHOD_LABELS):
        raise RuntimeError("Frozen trajectory method set changed.")
    key = ["outer_test_year", "date"]
    identity_columns = [
        "CHLF",
        "s2_openwater_reference_candidate",
        "common_support_segment_id",
    ]
    for column in identity_columns:
        pivot = daily.pivot(index=key, columns="method", values=column)
        if not pivot.nunique(axis=1, dropna=False).eq(1).all():
            raise RuntimeError(f"Method rows disagree on frozen {column}.")
    unique = daily.drop_duplicates(key)
    if int(unique["s2_openwater_reference_candidate"].sum()) != 288:
        raise RuntimeError("Frozen actual-mask sparse input count is not 288.")
    return {
        "daily": daily,
        "events": events,
        "matches": matches,
        "source_sha256": before,
        "source_paths": {name: str(path.relative_to(root)) for name, path in paths.items()},
    }


def build_plotting_table(
    daily: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    """Create the sole derived long-format data source used by every figure."""

    keys = ["outer_test_year", "date"]
    base = daily.drop_duplicates(keys).sort_values(keys)
    event_map = events.set_index(["year", "event_time"])["event_id"]
    rows: list[pd.DataFrame] = []
    reference = base[
        [
            "outer_test_year",
            "date",
            "CHLF",
            "s2_openwater_reference_candidate",
            "common_support_segment_id",
        ]
    ].rename(columns={"outer_test_year": "year", "CHLF": "value"})
    reference["series_type"] = "daily_reference"
    reference["method"] = ""
    reference["is_sparse_input"] = False
    rows.append(reference)
    sparse = reference.loc[base["s2_openwater_reference_candidate"].to_numpy()].copy()
    sparse["series_type"] = "actual_sparse_s2_input"
    sparse["is_sparse_input"] = True
    rows.append(sparse)
    for method in METHOD_LABELS:
        method_data = daily.loc[
            daily["method"].eq(method),
            ["outer_test_year", "date", "prediction", "common_support_segment_id"],
        ].rename(
            columns={
                "outer_test_year": "year",
                "prediction": "value",
            }
        )
        method_data["s2_openwater_reference_candidate"] = False
        method_data["series_type"] = "reconstruction"
        method_data["method"] = method
        method_data["is_sparse_input"] = False
        rows.append(method_data)
    output = pd.concat(rows, ignore_index=True)
    output["reference_event_id"] = [
        event_map.get((int(year), pd.Timestamp(date)), "")
        for year, date in zip(output["year"], output["date"], strict=True)
    ]
    output["is_reference_event"] = output["reference_event_id"].ne("")
    output = output.rename(
        columns={"common_support_segment_id": "common_support_segment"}
    )
    return output[
        [
            "year",
            "date",
            "value",
            "series_type",
            "method",
            "is_sparse_input",
            "is_reference_event",
            "reference_event_id",
            "common_support_segment",
        ]
    ].sort_values(["year", "date", "series_type", "method"], kind="mergesort")


def _format_axis(ax: Any, *, title: str, compact: bool = False) -> None:
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel("CHLF (µg L⁻¹)")
    ax.grid(axis="y", alpha=0.2, linewidth=0.6)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2 if compact else 1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.tick_params(axis="x", rotation=0)


def _draw_year(
    ax: Any,
    table: pd.DataFrame,
    year: int,
    *,
    methods: Iterable[str] = tuple(METHOD_LABELS),
    events: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    xlim: tuple[str, str] | None = None,
    compact: bool = False,
) -> None:
    group = table.loc[table["year"].eq(year)]
    if xlim:
        group = group[
            group["date"].between(pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1]))
        ]
    reference = group[group["series_type"].eq("daily_reference")]
    ax.plot(
        reference["date"],
        reference["value"],
        color=REFERENCE_COLOR,
        linewidth=2.1,
        label="Daily reference",
        zorder=3,
    )
    for method in methods:
        curve = group[
            group["series_type"].eq("reconstruction") & group["method"].eq(method)
        ]
        ax.plot(
            curve["date"],
            curve["value"],
            color=METHOD_COLORS[method],
            linewidth=1.45,
            alpha=0.95,
            label=METHOD_LABELS[method],
            zorder=2,
        )
    sparse = group[group["series_type"].eq("actual_sparse_s2_input")]
    ax.scatter(
        sparse["date"],
        sparse["value"],
        s=22 if compact else 30,
        color=SPARSE_COLOR,
        edgecolor="white",
        linewidth=0.55,
        label="Actual sparse S2 inputs",
        zorder=5,
    )
    if events is not None:
        year_events = events[events["year"].eq(year)]
        if xlim:
            year_events = year_events[
                year_events["event_time"].between(
                    pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1])
                )
            ]
        for index, event in enumerate(year_events.itertuples(index=False)):
            ax.axvline(
                event.event_time,
                color="#666666",
                linestyle="--",
                linewidth=0.8,
                alpha=0.7,
                label="Frozen reference event" if index == 0 else None,
            )
            if not compact:
                ax.text(
                    event.event_time,
                    0.97 - 0.08 * (index % 2),
                    event.event_id,
                    transform=ax.get_xaxis_transform(),
                    rotation=90,
                    va="top",
                    ha="right",
                    fontsize=7,
                    color="#555555",
                )
    if matches is not None:
        selected = matches[
            matches["year"].eq(year) & matches["event_status"].eq("matched")
        ]
        if xlim:
            selected = selected[
                selected["reconstructed_event_time"].between(
                    pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1])
                )
            ]
        for method in methods:
            marked = selected[selected["method"].eq(method)]
            if marked.empty:
                continue
            ax.scatter(
                marked["reconstructed_event_time"],
                marked["reconstructed_magnitude"],
                marker="v",
                s=30,
                facecolor=METHOD_COLORS[method],
                edgecolor="white",
                linewidth=0.5,
                label=f"{METHOD_LABELS[method]} matched event",
                zorder=6,
            )
    if xlim:
        ax.set_xlim(pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1]))
    _format_axis(ax, title=str(year), compact=compact)


def _save(fig: Any, path: Path) -> None:
    fig.savefig(
        path,
        dpi=220,
        facecolor="white",
        metadata={"Software": "twinwater-timesat-s2-chla"},
    )
    plt.close(fig)


def _overview(
    table: pd.DataFrame,
    path: Path,
    *,
    methods: Iterable[str],
    title: str,
) -> None:
    fig, axes = plt.subplots(4, 2, figsize=(16, 19), constrained_layout=True)
    for ax, year in zip(axes.flat, PRIMARY_YEARS, strict=False):
        _draw_year(ax, table, year, methods=methods, compact=True)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].axis("off")
    axes.flat[-1].legend(
        handles,
        labels,
        loc="center",
        frameon=False,
        fontsize=11,
    )
    fig.suptitle(title, fontsize=17, fontweight="bold")
    _save(fig, path)


def write_review_figures(
    table: pd.DataFrame,
    events: pd.DataFrame,
    matches: pd.DataFrame,
    output: str | Path,
) -> list[Path]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    overview = output / FIGURE_FILENAMES[0]
    _overview(
        table,
        overview,
        methods=tuple(METHOD_LABELS),
        title="Erken frozen actual-mask trajectories, 2019–2025",
    )
    paths.append(overview)
    for year in PRIMARY_YEARS:
        path = output / f"erken_actual_mask_trajectory_{year}.png"
        fig, ax = plt.subplots(figsize=(15, 7), constrained_layout=True)
        _draw_year(ax, table, year)
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(f"Erken frozen actual-mask trajectory — {year}", fontweight="bold")
        _save(fig, path)
        paths.append(path)

        event_path = output / f"erken_actual_mask_trajectory_events_{year}.png"
        fig, ax = plt.subplots(figsize=(15, 7.5), constrained_layout=True)
        _draw_year(ax, table, year, events=events, matches=matches)
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(
            f"Erken frozen reference and matched seasonal events — {year}",
            fontweight="bold",
        )
        _save(fig, event_path)
        paths.append(event_path)
    for method, filename in (
        ("linear_interpolation", "erken_linear_overview_2019_2025.png"),
        ("timesat_double_logistic", "erken_double_logistic_overview_2019_2025.png"),
        ("timesat_smoothing_spline", "erken_smoothing_spline_overview_2019_2025.png"),
    ):
        path = output / filename
        _overview(
            table,
            path,
            methods=(method,),
            title=f"Erken: {METHOD_LABELS[method]}, 2019–2025",
        )
        paths.append(path)
    for filename, (year, start, end) in ZOOM_WINDOWS.items():
        path = output / filename
        fig, ax = plt.subplots(figsize=(15, 7), constrained_layout=True)
        _draw_year(
            ax,
            table,
            year,
            events=events,
            matches=matches,
            xlim=(start, end),
        )
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(
            f"Erken {year} diagnostic zoom: {pd.Timestamp(start):%d %b}–{pd.Timestamp(end):%d %b}",
            fontweight="bold",
        )
        _save(fig, path)
        paths.append(path)
    generated_names = [path.name for path in paths]
    if len(generated_names) != len(FIGURE_FILENAMES) or set(generated_names) != set(
        FIGURE_FILENAMES
    ):
        raise AssertionError("Generated trajectory figure set differs from specification.")
    return paths


def generate_trajectory_review_package(
    *, repository_root: str | Path, output_directory: str | Path
) -> tuple[list[Path], dict[str, Any]]:
    root = Path(repository_root)
    commit = _git_clean_commit(root)
    sources = load_frozen_plot_sources(root)
    table = build_plotting_table(sources["daily"], sources["events"])
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    table_path = output / "erken_actual_mask_plotting_table.csv"
    write_deterministic_csv(table, table_path)
    figures = write_review_figures(
        table, sources["events"], sources["matches"], output
    )
    after = {
        name: sha256_file(root / relative)
        for name, relative in SOURCE_PATHS.items()
    }
    if after != sources["source_sha256"]:
        raise RuntimeError("A frozen source changed during figure generation.")
    manifest: dict[str, Any] = {
        "schema_version": "erken_actual_mask_trajectory_figure_manifest_v1",
        "repository_commit": commit,
        "scope": "erken_frozen_actual_mask_visual_review_only",
        "source_paths": sources["source_paths"],
        "source_sha256": sources["source_sha256"],
        "plotting_table_path": str(table_path.relative_to(root)),
        "plotting_table_sha256": deterministic_table_sha256(table),
        "figure_paths": [str(path.relative_to(root)) for path in figures],
        "figure_sha256": {
            path.name: sha256_file(path) for path in figures
        },
        "figure_count": len(figures),
        "event_annotations_included": True,
        "matched_reconstructed_event_dates_shown": True,
        "frozen_benchmark_outputs_modified": False,
        "reconstruction_rerun": False,
        "reconstruction_retuned": False,
        "vombsjon_data_or_results_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    manifest_path = output / "erken_trajectory_figure_manifest.json"
    write_deterministic_json(manifest, manifest_path)
    return [table_path, *figures, manifest_path], manifest
