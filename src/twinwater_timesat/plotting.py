"""Publication-oriented diagnostic figures for Phase 1."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


COLORS = plt.get_cmap("tab10").colors


def _style() -> dict[str, object]:
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


def _save(fig: plt.Figure, output_directory: Path, stem: str) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    png = output_directory / f"{stem}.png"
    pdf = output_directory / f"{stem}.pdf"
    fig.savefig(png, dpi=300, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    plt.close(fig)
    return [png, pdf]


def _shade_ice_periods(ax: plt.Axes, data: pd.DataFrame, *, label: bool = False) -> None:
    ice = data.loc[data["ice_flag"].eq(1), "date"].sort_values()
    if ice.empty:
        return
    groups = ice.diff().dt.days.ne(1).cumsum()
    for index, (_, dates) in enumerate(ice.groupby(groups)):
        ax.axvspan(
            dates.min() - pd.Timedelta(hours=12),
            dates.max() + pd.Timedelta(hours=12),
            color="#6b7280",
            alpha=0.14,
            linewidth=0,
            label="Ice flagged" if label and index == 0 else None,
        )


def plot_complete_time_series(data: pd.DataFrame, output_directory: str | Path) -> list[Path]:
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(11.2, 4.0), constrained_layout=True)
        ax.plot(data["date"], data["CHLF"], color="#176b87", linewidth=0.85, label="CHLF")
        _shade_ice_periods(ax, data, label=True)
        ax.set(
            title="Lake Erken daily chlorophyll fluorescence: complete observed record",
            xlabel="Date",
            ylabel="CHLF (µg L$^{-1}$)",
        )
        ax.legend(frameon=False, ncol=2, loc="upper left")
        ax.text(
            0.995,
            0.98,
            "Daily 00:00 reference; no interpolation or smoothing",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color="#4b5563",
            fontsize=8,
        )
        return _save(fig, Path(output_directory), "figure_01_erken_complete_time_series")


def plot_annual_common_scale(data: pd.DataFrame, output_directory: str | Path) -> list[Path]:
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(10.0, 5.0), constrained_layout=True)
        for index, (year, group) in enumerate(data.groupby("year", sort=True)):
            ax.plot(group["doy"], group["CHLF"], linewidth=0.9, color=COLORS[index], label=str(year))
        ax.set(
            title="Annual Erken CHLF trajectories aligned by day of year (common scale)",
            xlabel="Day of year",
            ylabel="CHLF (µg L$^{-1}$)",
            xlim=(1, 366),
        )
        ax.legend(frameon=False, ncol=4, loc="upper left")
        return _save(fig, Path(output_directory), "figure_02_erken_annual_common_scale")


def plot_annual_local_scaling(data: pd.DataFrame, output_directory: str | Path) -> list[Path]:
    years = sorted(data["year"].unique())
    with plt.rc_context(_style()):
        fig, axes = plt.subplots(4, 2, figsize=(10.0, 10.8), sharex=True, constrained_layout=True)
        flat = axes.ravel()
        record_start = data["date"].min()
        record_end = data["date"].max()
        for index, year in enumerate(years):
            ax = flat[index]
            group = data.loc[data["year"].eq(year)]
            ax.plot(group["doy"], group["CHLF"], linewidth=0.85, color=COLORS[index])
            partial = record_start.year == year and record_start.dayofyear > 1 or record_end.year == year and record_end.dayofyear < (366 if record_end.is_leap_year else 365)
            ax.set_title(f"{year}{' — partial record' if partial else ''}", loc="left")
            ax.set_xlim(1, 366)
            ax.set_ylabel("CHLF (µg L$^{-1}$)")
        for ax in flat[len(years) :]:
            ax.set_visible(False)
        for ax in flat[-2:]:
            if ax.get_visible():
                ax.set_xlabel("Day of year")
        fig.suptitle(
            "Annual Erken CHLF trajectories with local y-scaling\n"
            "Compare within-year shape only; panel magnitudes are not visually comparable",
            fontsize=12,
        )
        return _save(fig, Path(output_directory), "figure_03_erken_annual_local_scaling")


def plot_normalized_shape(data: pd.DataFrame, output_directory: str | Path) -> list[Path]:
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(10.0, 5.0), constrained_layout=True)
        for index, (year, group) in enumerate(data.groupby("year", sort=True)):
            values = group["CHLF"].to_numpy(dtype=float)
            finite = np.isfinite(values)
            minimum = np.min(values[finite])
            maximum = np.max(values[finite])
            normalized = (
                (values - minimum) / (maximum - minimum)
                if maximum > minimum
                else np.full_like(values, np.nan)
            )
            ax.plot(group["doy"], normalized, linewidth=0.9, color=COLORS[index], label=str(year))
        ax.set(
            title="Normalized annual Erken CHLF shape comparison (visualization only)",
            xlabel="Day of year",
            ylabel="Within-year min–max normalized CHLF",
            xlim=(1, 366),
            ylim=(-0.02, 1.02),
        )
        ax.legend(frameon=False, ncol=4, loc="upper left")
        ax.text(
            0.995,
            0.985,
            r"Normalization: $(CHLF-yearly\ min)/(yearly\ max-yearly\ min)$; not an accuracy metric",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color="#4b5563",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "none", "alpha": 0.82},
        )
        return _save(fig, Path(output_directory), "figure_04_erken_normalized_shape")


def plot_interannual_metrics(
    annual: pd.DataFrame, output_directory: str | Path
) -> list[Path]:
    summary = annual.loc[annual["scope"].eq("open_water")].sort_values("year")
    complete = (
        annual.loc[annual["scope"].eq("complete_reference")]
        .sort_values("year")
        .set_index("year")
    )
    metrics = [
        ("global_max_doy", "Open-water peak timing", "Peak date (DOY)"),
        ("max_chlf_ug_l", "Open-water peak magnitude", "Peak CHLF (µg L$^{-1}$)"),
        ("amplitude_chlf_ug_l", "Open-water annual amplitude", "Amplitude (µg L$^{-1}$)"),
    ]
    with plt.rc_context(_style()):
        fig, axes = plt.subplots(3, 1, figsize=(8.5, 8.3), sharex=True, constrained_layout=True)
        for ax, (column, title, ylabel) in zip(axes, metrics, strict=True):
            ax.plot(summary["year"], summary[column], color="#176b87", linewidth=1.2, zorder=1)
            for row in summary.itertuples(index=False):
                partial = row.record_partial_calendar_year
                ax.scatter(
                    row.year,
                    getattr(row, column),
                    s=42,
                    facecolor="white" if partial else "#176b87",
                    edgecolor="#176b87",
                    linewidth=1.2,
                    zorder=2,
                )
                if column in {"global_max_doy", "max_chlf_ug_l"}:
                    complete_value = complete.loc[row.year, column]
                    open_water_value = getattr(row, column)
                    if not np.isclose(complete_value, open_water_value):
                        ax.scatter(
                            row.year,
                            complete_value,
                            marker="x",
                            s=52,
                            color="#6b7280",
                            linewidth=1.4,
                            zorder=3,
                        )
            ax.set_title(title, loc="left")
            ax.set_ylabel(ylabel)
        axes[-1].set_xlabel("Year")
        axes[-1].set_xticks(summary["year"])
        legend_handles = [
            Line2D(
                [0],
                [0],
                color="#176b87",
                marker="o",
                linewidth=1.2,
                label="Open-water metric",
            ),
            Line2D(
                [0],
                [0],
                color="#176b87",
                marker="o",
                markerfacecolor="white",
                linewidth=0,
                label="Partial calendar year",
            ),
            Line2D(
                [0],
                [0],
                color="#6b7280",
                marker="x",
                linewidth=0,
                label="Differing complete-reference peak",
            ),
        ]
        axes[0].legend(
            handles=legend_handles,
            frameon=False,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.03),
            ncol=3,
        )
        fig.suptitle(
            "Interannual Erken open-water seasonal metrics (separate axes; no dual axis)\n"
            "Open-water metrics exclude dates flagged as ice covered; this is the preliminary observable domain.\n"
            "It is not actual Sentinel-2 acquisition availability.",
            fontsize=12,
        )
        return _save(fig, Path(output_directory), "figure_05_erken_interannual_metrics")


def generate_all_figures(
    data: pd.DataFrame, annual: pd.DataFrame, output_directory: str | Path
) -> list[Path]:
    """Generate every required Phase 1 figure in PNG and PDF formats."""

    outputs: list[Path] = []
    outputs.extend(plot_complete_time_series(data, output_directory))
    outputs.extend(plot_annual_common_scale(data, output_directory))
    outputs.extend(plot_annual_local_scaling(data, output_directory))
    outputs.extend(plot_normalized_shape(data, output_directory))
    outputs.extend(plot_interannual_metrics(annual, output_directory))
    return outputs
