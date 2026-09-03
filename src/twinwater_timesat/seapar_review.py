"""Deterministic Phase 5 trajectory review for selected p_seapar."""

from __future__ import annotations

import json
from pathlib import Path
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
from twinwater_timesat.seapar_actual import (
    ACTUAL_DIRECTORY,
    CV_METHOD,
    DEFAULT_METHOD,
    EVENT_DIRECTORY,
    load_passed_selection,
)
from twinwater_timesat.seapar_sensitivity import (
    CLASSIFICATION,
    PROTOCOL_VERSION,
    load_passed_seapar_preflight,
    require_clean_descendant,
    validate_parent_output_inventory,
)
from twinwater_timesat.seasonal_events import EXPECTED_EVENT_TIMES


METHOD_LABELS = {
    "linear_interpolation": "Linear interpolation",
    "timesat_smoothing_spline": "Frozen smoothing spline",
    DEFAULT_METHOD: "DL default p_seapar=1",
    CV_METHOD: "DL CV-selected p_seapar",
}
METHOD_COLORS = {
    "linear_interpolation": "#0072B2",
    "timesat_smoothing_spline": "#009E73",
    DEFAULT_METHOD: "#D55E00",
    CV_METHOD: "#7B2CBF",
}
METHOD_STYLES = {
    "linear_interpolation": "-",
    "timesat_smoothing_spline": "-",
    DEFAULT_METHOD: "--",
    CV_METHOD: "-",
}
REFERENCE_COLOR = "#202020"
SPARSE_COLOR = "#CC79A7"
SOURCE_PATHS = {
    "frozen_primary_daily": (
        "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv"
    ),
    "frozen_reference_events": (
        "results/phase3/event_preflight/erken_phase3_reference_events.csv"
    ),
    "selected_daily": (
        f"{ACTUAL_DIRECTORY}/erken_phase5_seapar_actual_mask_daily_reconstructions.csv"
    ),
    "actual_manifest": (
        f"{ACTUAL_DIRECTORY}/erken_phase5_seapar_actual_mask_manifest.json"
    ),
    "event_comparison": (
        f"{EVENT_DIRECTORY}/erken_phase5_seapar_actual_mask_event_comparison.csv"
    ),
    "event_manifest": f"{EVENT_DIRECTORY}/erken_phase5_seapar_event_manifest.json",
}
ZOOM_WINDOWS = {
    "erken_phase5_2020_zoom_spring.png": (2020, "2020-03-15", "2020-05-20"),
    "erken_phase5_2020_zoom_august.png": (2020, "2020-07-20", "2020-08-25"),
    "erken_phase5_2020_zoom_september.png": (2020, "2020-08-20", "2020-09-30"),
    "erken_phase5_2025_zoom_spring.png": (2025, "2025-03-21", "2025-05-01"),
    "erken_phase5_2025_zoom_summer.png": (2025, "2025-06-20", "2025-09-15"),
    "erken_phase5_2025_zoom_october.png": (2025, "2025-09-25", "2025-10-31"),
}
FIGURE_FILENAMES = (
    "erken_phase5_seapar_trajectories_overview_2019_2025.png",
    *(f"erken_phase5_seapar_trajectory_{year}.png" for year in PRIMARY_YEARS),
    *(f"erken_phase5_seapar_trajectory_events_{year}.png" for year in PRIMARY_YEARS),
    "erken_phase5_cv_double_logistic_overview_2019_2025.png",
    "erken_phase5_default_vs_cv_double_logistic_overview_2019_2025.png",
    *(f"erken_phase5_default_vs_cv_double_logistic_{year}.png" for year in PRIMARY_YEARS),
    *ZOOM_WINDOWS,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("manifest_payload_sha256") != canonical_json_payload_sha256(
        value, excluded_keys=("manifest_payload_sha256",)
    ):
        raise RuntimeError(f"Manifest checksum mismatch: {path}")
    return value


def load_phase5_review_sources(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    preflight = load_passed_seapar_preflight(root)
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    _, selected = load_passed_selection(root)
    paths = {name: root / relative for name, relative in SOURCE_PATHS.items()}
    before = {name: sha256_file(path) for name, path in paths.items()}
    actual_manifest = _load_json(paths["actual_manifest"])
    event_manifest = _load_json(paths["event_manifest"])
    if before["selected_daily"] != actual_manifest["table_sha256"][
        paths["selected_daily"].name
    ]:
        raise RuntimeError("Selected daily trajectory checksum mismatch.")
    if before["event_comparison"] != event_manifest["table_sha256"][
        paths["event_comparison"].name
    ]:
        raise RuntimeError("Event comparison checksum mismatch.")
    if before["frozen_primary_daily"] != preflight["parent_output_sha256"][
        SOURCE_PATHS["frozen_primary_daily"]
    ]:
        raise RuntimeError("Frozen primary daily trajectories changed.")
    if before["frozen_reference_events"] != preflight["parent_output_sha256"][
        SOURCE_PATHS["frozen_reference_events"]
    ]:
        raise RuntimeError("Frozen reference event table changed.")
    old = pd.read_csv(paths["frozen_primary_daily"], parse_dates=["date"])
    new = pd.read_csv(paths["selected_daily"], parse_dates=["date"])
    events = pd.read_csv(paths["frozen_reference_events"], parse_dates=["event_time"])
    matches = pd.read_csv(
        paths["event_comparison"],
        parse_dates=["reference_event_time", "reconstructed_event_time"],
    )
    if list(zip(events["event_id"], events["event_date"], strict=True)) != list(
        EXPECTED_EVENT_TIMES
    ):
        raise RuntimeError("Frozen 18-event set changed.")
    unique = old.drop_duplicates(["outer_test_year", "date"])
    if int(unique["s2_openwater_reference_candidate"].sum()) != 288:
        raise RuntimeError("Frozen actual-mask sparse input count changed.")
    if new["reconstruction_status"].ne("ok").any():
        raise RuntimeError("Selected trajectory contains a failed reconstruction.")
    observed_selected = (
        new.groupby("outer_test_year")["selected_p_seapar"].first().to_dict()
    )
    if observed_selected != selected:
        raise RuntimeError("Selected trajectory parameters differ from Phase S1.")
    return {
        "old": old,
        "new": new,
        "events": events,
        "matches": matches,
        "selected": selected,
        "source_paths": {name: str(path.relative_to(root)) for name, path in paths.items()},
        "source_sha256": before,
        "parent_output_sha256": preflight["parent_output_sha256"],
    }


def build_phase5_plotting_table(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    keys = ["outer_test_year", "date"]
    base = old.drop_duplicates(keys).sort_values(keys)
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
    reference["selected_p_seapar"] = pd.NA
    reference["is_sparse_input"] = False
    rows.append(reference)
    sparse = reference.loc[base["s2_openwater_reference_candidate"].to_numpy()].copy()
    sparse["series_type"] = "actual_sparse_s2_input"
    sparse["is_sparse_input"] = True
    rows.append(sparse)
    old_methods = old[
        [
            "outer_test_year",
            "date",
            "prediction",
            "method",
            "common_support_segment_id",
        ]
    ].rename(columns={"outer_test_year": "year", "prediction": "value"})
    old_methods["method"] = old_methods["method"].replace(
        {"timesat_double_logistic": DEFAULT_METHOD}
    )
    old_methods["s2_openwater_reference_candidate"] = False
    old_methods["series_type"] = "reconstruction"
    old_methods["selected_p_seapar"] = old_methods["method"].map(
        {DEFAULT_METHOD: 1.0}
    )
    old_methods["is_sparse_input"] = False
    rows.append(old_methods)
    selected = new[
        [
            "outer_test_year",
            "date",
            "prediction",
            "method",
            "common_support_segment_id",
            "selected_p_seapar",
        ]
    ].rename(columns={"outer_test_year": "year", "prediction": "value"})
    selected["s2_openwater_reference_candidate"] = False
    selected["series_type"] = "reconstruction"
    selected["is_sparse_input"] = False
    rows.append(selected)
    output = pd.concat(rows, ignore_index=True)
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
            "selected_p_seapar",
            "is_sparse_input",
            "common_support_segment",
        ]
    ].sort_values(["year", "date", "series_type", "method"], kind="mergesort")


def _format_axis(ax: Any, *, year: int, selected: float, compact: bool) -> None:
    ax.set_title(str(year), fontweight="bold")
    ax.text(
        0.99,
        0.97,
        f"CV p_seapar={selected:.1f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8 if compact else 10,
        bbox={"facecolor": "white", "edgecolor": "#bbbbbb", "alpha": 0.8},
    )
    ax.set_ylabel("CHLF (µg L⁻¹)")
    ax.grid(axis="y", alpha=0.2, linewidth=0.6)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2 if compact else 1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


def _draw_year(
    ax: Any,
    table: pd.DataFrame,
    year: int,
    *,
    selected: float,
    methods: Iterable[str] = tuple(METHOD_LABELS),
    events: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    xlim: tuple[str, str] | None = None,
    compact: bool = False,
) -> None:
    group = table[table["year"].eq(year)]
    if xlim:
        group = group[group["date"].between(pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1]))]
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
            linestyle=METHOD_STYLES[method],
            linewidth=1.55,
            label=METHOD_LABELS[method],
            zorder=2,
        )
    sparse = group[group["series_type"].eq("actual_sparse_s2_input")]
    ax.scatter(
        sparse["date"],
        sparse["value"],
        color=SPARSE_COLOR,
        edgecolor="white",
        linewidth=0.55,
        s=22 if compact else 30,
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
                linestyle=":",
                linewidth=0.9,
                label="Frozen reference event" if index == 0 else None,
            )
            if not compact:
                ax.text(
                    event.event_time,
                    0.04 + 0.08 * (index % 2),
                    event.event_id,
                    transform=ax.get_xaxis_transform(),
                    rotation=90,
                    va="bottom",
                    ha="left",
                    fontsize=7,
                    color="#555555",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65},
                )
    if matches is not None:
        marked = matches[
            matches["year"].eq(year)
            & matches["event_status"].eq("matched")
            & matches["method"].isin([DEFAULT_METHOD, CV_METHOD])
        ]
        if xlim:
            marked = marked[
                marked["reconstructed_event_time"].between(
                    pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1])
                )
            ]
        for method in (DEFAULT_METHOD, CV_METHOD):
            subset = marked[marked["method"].eq(method)]
            if subset.empty or method not in methods:
                continue
            ax.scatter(
                subset["reconstructed_event_time"],
                subset["reconstructed_magnitude"],
                marker="v",
                s=35,
                color=METHOD_COLORS[method],
                edgecolor="white",
                linewidth=0.5,
                label=f"{METHOD_LABELS[method]} matched event",
                zorder=6,
            )
    if xlim:
        ax.set_xlim(pd.Timestamp(xlim[0]), pd.Timestamp(xlim[1]))
    _format_axis(ax, year=year, selected=selected, compact=compact)


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
    selected: dict[int, float],
    path: Path,
    *,
    methods: tuple[str, ...],
    title: str,
) -> None:
    fig, axes = plt.subplots(4, 2, figsize=(16, 19), constrained_layout=True)
    for ax, year in zip(axes.flat, PRIMARY_YEARS, strict=False):
        _draw_year(
            ax,
            table,
            year,
            selected=selected[year],
            methods=methods,
            compact=True,
        )
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].axis("off")
    axes.flat[-1].legend(handles, labels, loc="center", frameon=False, fontsize=10)
    fig.suptitle(title, fontsize=17, fontweight="bold")
    _save(fig, path)


def write_phase5_review_figures(
    table: pd.DataFrame,
    events: pd.DataFrame,
    matches: pd.DataFrame,
    selected: dict[int, float],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    path = output / "erken_phase5_seapar_trajectories_overview_2019_2025.png"
    _overview(
        table,
        selected,
        path,
        methods=tuple(METHOD_LABELS),
        title="Erken p_seapar sensitivity trajectories, 2019–2025",
    )
    paths.append(path)
    for year in PRIMARY_YEARS:
        path = output / f"erken_phase5_seapar_trajectory_{year}.png"
        fig, ax = plt.subplots(figsize=(15, 7), constrained_layout=True)
        _draw_year(ax, table, year, selected=selected[year])
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(f"Erken p_seapar sensitivity — {year}", fontweight="bold")
        _save(fig, path)
        paths.append(path)
        path = output / f"erken_phase5_seapar_trajectory_events_{year}.png"
        fig, ax = plt.subplots(figsize=(15, 7.5), constrained_layout=True)
        _draw_year(
            ax,
            table,
            year,
            selected=selected[year],
            events=events,
            matches=matches,
        )
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(
            f"Erken p_seapar sensitivity with frozen events — {year}",
            fontweight="bold",
        )
        _save(fig, path)
        paths.append(path)
    path = output / "erken_phase5_cv_double_logistic_overview_2019_2025.png"
    _overview(
        table,
        selected,
        path,
        methods=(CV_METHOD,),
        title="Erken CV-selected double logistic, 2019–2025",
    )
    paths.append(path)
    path = output / "erken_phase5_default_vs_cv_double_logistic_overview_2019_2025.png"
    _overview(
        table,
        selected,
        path,
        methods=(DEFAULT_METHOD, CV_METHOD),
        title="Erken double logistic: default versus CV-selected p_seapar",
    )
    paths.append(path)
    for year in PRIMARY_YEARS:
        path = output / f"erken_phase5_default_vs_cv_double_logistic_{year}.png"
        fig, ax = plt.subplots(figsize=(15, 7), constrained_layout=True)
        _draw_year(
            ax,
            table,
            year,
            selected=selected[year],
            methods=(DEFAULT_METHOD, CV_METHOD),
            events=events,
            matches=matches,
        )
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(f"Erken DL default versus CV-selected — {year}", fontweight="bold")
        _save(fig, path)
        paths.append(path)
    for filename, (year, start, end) in ZOOM_WINDOWS.items():
        path = output / filename
        fig, ax = plt.subplots(figsize=(15, 7), constrained_layout=True)
        _draw_year(
            ax,
            table,
            year,
            selected=selected[year],
            events=events,
            matches=matches,
            xlim=(start, end),
        )
        ax.set_xlabel("Date")
        ax.legend(loc="upper left", ncol=2, frameon=False)
        fig.suptitle(
            f"Erken p_seapar sensitivity zoom: {pd.Timestamp(start):%d %b}–"
            f"{pd.Timestamp(end):%d %b %Y}",
            fontweight="bold",
        )
        _save(fig, path)
        paths.append(path)
    names = [path.name for path in paths]
    if len(names) != len(FIGURE_FILENAMES) or set(names) != set(FIGURE_FILENAMES):
        raise AssertionError("Generated Phase 5 figure inventory differs from specification.")
    return paths


def generate_phase5_review_package(
    *, repository_root: str | Path, output_directory: str | Path
) -> tuple[list[Path], dict[str, Any]]:
    root = Path(repository_root)
    commit = require_clean_descendant(root)
    sources = load_phase5_review_sources(root)
    table = build_phase5_plotting_table(sources["old"], sources["new"])
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    table_path = output / "erken_phase5_seapar_plotting_table.csv"
    write_deterministic_csv(table, table_path)
    figures = write_phase5_review_figures(
        table,
        sources["events"],
        sources["matches"],
        sources["selected"],
        output,
    )
    after = {
        name: sha256_file(root / relative) for name, relative in SOURCE_PATHS.items()
    }
    if after != sources["source_sha256"]:
        raise RuntimeError("A frozen source changed during Phase 5 figure generation.")
    validate_parent_output_inventory(root, sources["parent_output_sha256"])
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_trajectory_review_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_commit": commit,
        "source_paths": sources["source_paths"],
        "source_sha256": sources["source_sha256"],
        "selected_p_seapar": {
            str(year): value for year, value in sources["selected"].items()
        },
        "plotting_table_path": str(table_path.relative_to(root)),
        "plotting_table_sha256": deterministic_table_sha256(table),
        "figure_count": len(figures),
        "figure_paths": [str(path.relative_to(root)) for path in figures],
        "figure_sha256": {path.name: sha256_file(path) for path in figures},
        "event_annotations_included": True,
        "default_and_cv_matched_event_dates_shown": True,
        "old_methods_reused_not_rerun": True,
        "benchmark_outputs_modified": False,
        "reconstruction_rerun": False,
        "method_ranking_generated": False,
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    manifest_path = output / "erken_phase5_seapar_trajectory_review_manifest.json"
    write_deterministic_json(manifest, manifest_path)
    return [table_path, *figures, manifest_path], manifest
