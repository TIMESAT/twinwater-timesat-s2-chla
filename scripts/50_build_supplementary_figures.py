#!/usr/bin/env python3
"""Render Supplementary Figures S1-S3 from committed result tables; no analysis runs.

Run from any directory with Python >=3.11 and matplotlib >=3.7:
    python scripts/50_build_supplementary_figures.py
Outputs are confined to manuscript/supplementary/figures/figure_s0[1-3]_*.{png,pdf}.
Every plotted value is read directly from a committed table. No model is fitted,
no metric is recomputed and no new inferential quantity is derived.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "supp-figures-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "manuscript/supplementary/figures"
REL = ROOT / "results/reliability_synthesis/v1.0"
SPATIAL = ROOT / "results/tables/erken_s2_scl_spatial_rule_sensitivity.csv"
DAILY = ROOT / "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv"

# Method colors and markers follow the main manuscript figures.
METHODS = {
    "linear_interpolation": ("Linear interpolation", "#0072B2", "o"),
    "timesat_double_logistic": ("TIMESAT double logistic (default)", "#D55E00", "s"),
    "timesat_smoothing_spline": ("TIMESAT smoothing spline", "#009E73", "^"),
}
RULES = {
    "bad2_water9_centernotbad_p0_class2zero": ("Strict", "#BBBBBB"),
    "scl3x3_b1_w8_centernotbad_p0_class2zero_v1": ("Preferred", "#555555"),
    "bad2_water7_centernotbad_p0_class2zero": ("Relaxed", "#999999"),
}
BOUNDARY_YEARS = {2019, 2025}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def style() -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.7, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42})


def save(fig, stem: str, title: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.pdf", metadata={"Title": title, "CreationDate": None, "ModDate": None})
    fig.savefig(OUT / f"{stem}.png", dpi=600, metadata={"Title": title})
    plt.close(fig)


def method_handles() -> list[Line2D]:
    return [Line2D([], [], color=c, marker=m, linestyle="-", markersize=4, linewidth=1.0, label=l)
            for l, c, m in METHODS.values()]


def figure_s1() -> None:
    rows = read(SPATIAL)
    table = {(r["source_rule_id_3x3"], int(r["window_size"])): r for r in rows}
    windows = (1, 3, 5)
    for rule in RULES:
        for w in windows:
            require((rule, w) in table, f"missing spatial rule {rule} {w}")
    fig, axes = plt.subplots(1, 2, figsize=(7.48, 3.0))
    ax = axes[0]
    width = 0.26
    for i, (rule, (label, color)) in enumerate(RULES.items()):
        xs = [k + (i - 1) * width for k in range(len(windows))]
        ys = [int(table[(rule, w)]["n_usable_dates"]) for w in windows]
        bars = ax.bar(xs, ys, width=width, color=color, edgecolor="black", linewidth=0.4, label=label)
        for x, y in zip(xs, ys):
            ax.text(x, y + 2, str(y), ha="center", va="bottom", fontsize=6.3)
    ax.set_xticks(range(len(windows)), [f"{w}×{w}" for w in windows])
    ax.set_ylim(250, 330)
    ax.set_ylabel("Usable observation dates, 2019–2025")
    ax.set_xlabel("Station-centred SCL window")
    ax.set_title("(a)  Usable dates by window and rule", loc="left")
    ax.legend(loc="upper right", fontsize=7, ncol=3, handlelength=1.0, columnspacing=0.8)
    ax = axes[1]
    thresholds = (("n_gaps_gt_10_days", ">10 d"), ("n_gaps_gt_20_days", ">20 d"),
                  ("n_gaps_gt_30_days", ">30 d"), ("n_gaps_gt_45_days", ">45 d"))
    shades = {1: "#DDDDDD", 3: "#555555", 5: "#999999"}
    preferred = "scl3x3_b1_w8_centernotbad_p0_class2zero_v1"
    for i, w in enumerate(windows):
        xs = [k + (i - 1) * width for k in range(len(thresholds))]
        ys = [int(table[(preferred, w)][col]) for col, _ in thresholds]
        ax.bar(xs, ys, width=width, color=shades[w], edgecolor="black", linewidth=0.4, label=f"{w}×{w}")
        for x, y in zip(xs, ys):
            ax.text(x, y + 0.8, str(y), ha="center", va="bottom", fontsize=6.3)
    ax.set_xticks(range(len(thresholds)), [lab for _, lab in thresholds])
    ax.set_ylabel("Inter-observation gaps (n)")
    ax.set_xlabel("Gap length (preferred rule, scaled to window)")
    ax.set_title("(b)  Gaps by window", loc="left")
    ax.legend(loc="upper right", fontsize=7, ncol=3, handlelength=1.0, columnspacing=0.8)
    fig.text(0.5, 0.015, "3×3 is the frozen primary window; 1×1 and 5×5 are diagnostics and were not used for reconstruction.",
             ha="center", fontsize=7)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "figure_s01_observation_mask_stability", "Figure S1 — Erken observation-mask window-size stability")


def figure_s2() -> None:
    rows = read(DAILY)
    by_year: dict[int, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        require(r["outer_test_year"] == r["year"], "outer test year mismatch")
        require(r["reconstruction_status"] == "ok", "reconstruction failure present")
        by_year[int(r["year"])].append(r)
    years = sorted(by_year)
    require(years == list(range(2019, 2026)), f"unexpected years {years}")
    fig, axes = plt.subplots(4, 2, figsize=(7.48, 9.2))
    axes = axes.ravel()
    for ax, year in zip(axes, years):
        yr = by_year[year]
        ref = {}
        for r in yr:
            if r["method"] == "linear_interpolation":
                ref[(r["common_support_segment_id"], r["date"])] = (float(r["CHLF"]), r["s2_openwater_reference_candidate"] == "True")
        segments = sorted({seg for seg, _ in ref})
        for seg in segments:
            pts = sorted((date.fromisoformat(d), v) for (s, d), v in ref.items() if s == seg)
            ax.plot([p[0] for p in pts], [p[1][0] for p in pts], color="black", linewidth=0.9, zorder=2)
            inputs = [p for p in pts if p[1][1]]
            ax.scatter([p[0] for p in inputs], [p[1][0] for p in inputs], s=7, facecolor="white",
                       edgecolor="black", linewidth=0.6, zorder=5)
        smoothing = ""
        for method, (_label, color, _m) in METHODS.items():
            mrows = [r for r in yr if r["method"] == method]
            if method == "timesat_smoothing_spline":
                values = {r["selected_smoothing"] for r in mrows}
                require(len(values) == 1, "multiple stored smoothing values")
                smoothing = values.pop()
            for seg in segments:
                pts = sorted((date.fromisoformat(r["date"]), float(r["prediction"]))
                             for r in mrows if r["common_support_segment_id"] == seg and r["prediction"] != "")
                ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, linewidth=0.9, alpha=0.9, zorder=3)
        all_dates = [date.fromisoformat(d) for _, d in ref]
        for edge in (min(all_dates), max(all_dates)):
            ax.axvline(edge, color="0.6", linewidth=0.5, linestyle=":", zorder=1)
        flag = "*" if year in BOUNDARY_YEARS else ""
        ax.set_title(f"{year}{flag}  (spline p_smooth = {smoothing})", loc="left")
        ax.set_ylabel("CHLF (µg L⁻¹)")
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b"))
        ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(3, 5, 7, 9, 11)))
    legend_ax = axes[-1]
    legend_ax.axis("off")
    handles = [Line2D([], [], color="black", linewidth=1.0, label="Dense CHLF reference"),
               Line2D([], [], color="black", marker="o", markerfacecolor="white", linestyle="none",
                      markersize=4, label="Actual-mask input date")]
    handles += [Line2D([], [], color=c, linewidth=1.2, label=l) for l, c, _m in METHODS.values()]
    handles += [Line2D([], [], color="0.6", linestyle=":", linewidth=0.8, label="Common-support boundary")]
    legend_ax.legend(handles=handles, loc="center left", fontsize=7.5)
    legend_ax.text(0.0, 0.05, "* Boundary-truncated common support;\n  support maxima are not full-year maxima.",
                   transform=legend_ax.transAxes, fontsize=7)
    fig.tight_layout()
    save(fig, "figure_s02_erken_annual_trajectories", "Figure S2 — Erken annual trajectories and actual-mask reconstructions")


def summary_rows(name: str) -> list[dict[str, str]]:
    return read(REL / name)


def interval_plot(ax, xs_labels, getter, offsets=(-0.2, 0.0, 0.2)) -> None:
    for (method, (_label, color, marker)), off in zip(METHODS.items(), offsets):
        for k, key in enumerate(xs_labels):
            est, lo, hi = getter(method, key)
            ax.errorbar(k + off, est, yerr=[[est - lo], [hi - est]], fmt=marker, color=color,
                        markersize=3.8, elinewidth=0.8, capsize=1.6)


def figure_s3() -> None:
    random_rows = summary_rows("erken_reliability_random_equal_year_deletion.csv")
    contain_rows = summary_rows("erken_reliability_consecutive_peak_containment_summary.csv")
    assoc_rows = summary_rows("erken_reliability_consecutive_continuous_associations_summary.csv")
    levels = sorted({r["deletion_fraction"] for r in random_rows}, key=float)
    require(len(levels) == 4, "expected four deletion levels")

    def rnd(metric):
        def get(method, level):
            m = [r for r in random_rows if r["method"] == method and r["deletion_fraction"] == level and r["metric"] == metric]
            require(len(m) == 1, f"random lookup {method} {level} {metric}")
            r = m[0]
            return float(r["equal_year_estimate"]), float(r["cluster_bootstrap_ci_lower"]), float(r["cluster_bootstrap_ci_upper"])
        return get

    fig, axes = plt.subplots(2, 2, figsize=(7.48, 5.6))
    level_labels = [f"{round(float(v) * 100)}%" for v in levels]
    ax = axes[0, 0]
    interval_plot(ax, levels, rnd("nrmse"))
    ax.set_xticks(range(4), level_labels)
    ax.set_xlabel("Interior inputs randomly deleted")
    ax.set_ylabel("Equal-year nRMSE")
    ax.set_title("(a)  Random deletion: pointwise error", loc="left")
    ax = axes[0, 1]
    interval_plot(ax, levels, rnd("peak_timing_success_10d"))
    ax.set_xticks(range(4), level_labels)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Interior inputs randomly deleted")
    ax.set_ylabel("Peak timing success within ±10 d")
    ax.set_title("(b)  Random deletion: global-peak timing", loc="left")

    ax = axes[1, 0]
    durations = ("10", "20", "30", "45")
    for (method, (_label, color, marker)), off in zip(METHODS.items(), (-0.24, 0.0, 0.24)):
        for k, dur in enumerate(durations):
            vals = {}
            for inside in ("False", "True"):
                m = [r for r in contain_rows if r["method"] == method and r["duration_days"] == dur
                     and r["contains_reference_global_peak"] == inside and r["metric"] == "peak_timing_success_10d"]
                require(len(m) == 1, f"containment lookup {method} {dur} {inside}")
                vals[inside] = float(m[0]["equal_year_estimate"])
            x = k + off
            ax.plot([x - 0.07, x + 0.07], [vals["False"], vals["True"]], color=color, linewidth=0.8)
            ax.plot(x - 0.07, vals["False"], marker=marker, color=color, markersize=3.8, markerfacecolor="white")
            ax.plot(x + 0.07, vals["True"], marker=marker, color=color, markersize=3.8)
    ax.set_xticks(range(4), [f"{d} d" for d in durations])
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Consecutive calendar-day deletion window")
    ax.set_ylabel("Peak timing success within ±10 d")
    ax.set_title("(c)  Peak outside (open) vs inside (filled) window", loc="left")

    ax = axes[1, 1]

    def assoc(method, dur):
        m = [r for r in assoc_rows if r["method"] == method and r["duration_days"] == dur
             and r["covariate"] == "a_gap" and r["outcome"] == "nrmse"]
        require(len(m) == 1, f"association lookup {method} {dur}")
        r = m[0]
        return float(r["equal_year_mean_spearman"]), float(r["cluster_bootstrap_ci_lower"]), float(r["cluster_bootstrap_ci_upper"])

    interval_plot(ax, durations, assoc)
    ax.axhline(0, color="0.6", linewidth=0.6, linestyle=":")
    ax.set_xticks(range(4), [f"{d} d" for d in durations])
    ax.set_xlabel("Consecutive calendar-day deletion window")
    ax.set_ylabel("Within-year Spearman ρ (A_gap, nRMSE)")
    ax.set_title("(d)  Retrospective hidden-gap activity", loc="left")

    fig.legend(handles=[Line2D([], [], color=c, marker=m, linestyle="none", markersize=4, label=l)
                        for l, c, m in METHODS.values()],
               loc="upper center", ncol=3, fontsize=7.4, bbox_to_anchor=(0.5, 0.995))
    fig.text(0.5, 0.012, "Equal-year estimates; bars are 95% whole-year bootstrap intervals. "
             "A_gap is retrospective and unavailable inside a real observation gap.", ha="center", fontsize=7)
    fig.tight_layout(rect=(0, 0.035, 1, 0.95))
    save(fig, "figure_s03_controlled_missingness_extended", "Figure S3 — Extended Erken controlled missingness")


def main() -> int:
    style()
    figure_s1()
    figure_s2()
    figure_s3()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
