#!/usr/bin/env python3
"""Render manuscript Figure 5 from committed frozen values; no analysis runs.

Run from any directory with Python >=3.11 and matplotlib >=3.7:
    python scripts/46_plot_vombsjon_annual_heterogeneity.py
Outputs are confined to manuscript/figures/figure_05_vombsjon_annual_heterogeneity.*
The CSV/report are generated display provenance, not new scientific results.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "figure05-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = "results/vombsjon/locked_transfer/v1.0/"
STEM = ROOT / "manuscript/figures/figure_05_vombsjon_annual_heterogeneity"
HASHES = {
    "vombsjon_transfer_year_summary.csv": "c7d742df66238b046b6adc87b53f4cae578f6ab21e38437f32298948f06084b4",
    "vombsjon_transfer_year_eligibility.csv": "e0ccbb80786e3c9cc35f72d3e6fcb377e1f226b84c4addbab119dcda49ff01ba",
}
# Existing method colors: src/twinwater_timesat/seapar_review.py.
METHODS = {
    "linear_interpolation": ("Linear interpolation", "#0072B2", "o", "primary_simple_baseline"),
    "timesat_double_logistic": ("TIMESAT double logistic (default)", "#D55E00", "s", "primary_frozen_default_benchmark"),
    "timesat_smoothing_spline": ("TIMESAT smoothing spline", "#009E73", "^", "primary_frozen_erken_selected_spline"),
}
PANELS = {
    "a": ("nrmse_training_q95_minus_q05", "Pointwise reconstruction", "Annual nRMSE", (0.1, 0.5)),
    "b": ("trajectory_pearson_r", "Trajectory agreement", "Withheld-date Pearson r", (0.0, 1.05)),
    "c": ("absolute_peak_error_days", "Observed-proxy peak timing", "Mean absolute peak error (days)", (0, 145)),
}
YEARS = list(range(2017, 2027))


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def in_scope(row: dict) -> bool:
    return (row["processor"], row["scenario_kind"], row["block_size_observed_dates"]) == ("ACOLITE", "consecutive", "4")


def main() -> int:
    commit = git("rev-parse", "HEAD").decode().strip()
    manifest = json.loads(git("show", f"{commit}:{SOURCE_ROOT}vombsjon_transfer_manifest.json"))
    sources = {}
    for name, expected in HASHES.items():
        blob = git("show", f"{commit}:{SOURCE_ROOT}{name}")
        require(sha(blob) == expected == manifest["output_sha256"][name], f"Frozen hash mismatch: {name}")
        require((ROOT / SOURCE_ROOT / name).read_bytes() == blob, f"Local source differs: {name}")
        sources[name] = list(csv.DictReader(io.StringIO(blob.decode())))
    eligibility = [r for r in sources["vombsjon_transfer_year_eligibility.csv"] if in_scope(r)]
    require(sorted(int(r["year"]) for r in eligibility) == YEARS, "Eligibility year coverage mismatch")
    support = {int(r["year"]): r for r in eligibility}
    require(all(r["eligible"] == "True" for r in eligibility), "Unexpected ineligible year")
    require(support[2026]["support_start"] == "2026-01-10" and support[2026]["support_end"] == "2026-08-03", "Partial-year support mismatch")
    summary = sources["vombsjon_transfer_year_summary.csv"]
    selected, unavailable = [], []
    for panel, (metric, *_rest) in PANELS.items():
        for year in YEARS:
            for method, (_label, _color, _marker, role) in METHODS.items():
                matches = [r for r in summary if in_scope(r) and int(r["year"]) == year
                           and r["reconstruction_method"] == method and r["metric"] == metric]
                require(len(matches) == 1, "Expected one saved annual row per panel/year/method")
                row = matches[0]
                require(row["analysis_role"] == role and row["processor_role"] == "primary_aquatic_atmospheric_correction", "Role mismatch")
                require(row["n_scenarios_total"] == support[year]["n_scenarios"], "Scenario coverage mismatch")
                available = bool(row["estimate"]) and math.isfinite(float(row["estimate"]))
                require(available == (int(row["n_scenarios_available"]) > 0), "Availability/denominator mismatch")
                if not available:
                    unavailable.append(f"{panel}: {year}, {method}")
                selected.append({"panel": panel, **row,
                    "support_start": support[year]["support_start"], "support_end": support[year]["support_end"]})
    require(len(selected) == 90, "Expected all 90 annual records")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "axes.labelsize": 8, "axes.titlesize": 8.5, "xtick.labelsize": 7,
        "ytick.labelsize": 8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(1, 3, figsize=(7.48, 3.50))
    fig.subplots_adjust(left=0.075, right=0.98, bottom=0.32, top=0.76, wspace=0.43)
    verified = 0
    for ax, (panel, (_metric, title, ylabel, limits)) in zip(axes, PANELS.items(), strict=True):
        for method, (_label, color, marker, _role) in METHODS.items():
            rows = [r for r in selected if r["panel"] == panel and r["reconstruction_method"] == method]
            require([int(r["year"]) for r in rows] == YEARS, "Plot year order mismatch")
            y = [float(r["estimate"]) if r["estimate"] else float("nan") for r in rows]
            line, = ax.plot(YEARS, y, color=color, linewidth=0.75, marker=marker,
                            markersize=3.5, markeredgecolor="white", markeredgewidth=0.35)
            for year, actual, expected in zip(line.get_xdata(), line.get_ydata(), y, strict=True):
                if math.isfinite(expected):
                    require(actual == expected and limits[0] <= actual <= limits[1], "Plotted value mismatch or clipping")
                    verified += 1
                else:
                    require(math.isnan(actual), "Unavailable value imputed")
                    ax.text(year, 0.02, "NA", transform=ax.get_xaxis_transform(), color=color, fontsize=6)
        ax.set(xlim=(2016.6, 2026.4), ylim=limits, ylabel=ylabel)
        # Wrap long headings to retain Figure 4 typography and page width.
        display_title = title.replace(" reconstruction", "\nreconstruction").replace(" agreement", "\nagreement").replace(" peak timing", "\npeak timing")
        ax.set_title(f"({panel})  {display_title}", loc="left", pad=9)
        ax.set_xticks(YEARS, [str(y) + ("*" if y == 2026 else "") for y in YEARS], rotation=60, ha="right")
        ax.tick_params(length=3)
        if panel == "b":
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
        if panel == "c":
            ax.set_yticks([0, 30, 60, 90, 120])
        ax.text(0.02, 0.97, "Higher is better" if panel == "b" else "Lower is better",
                transform=ax.transAxes, va="top", fontsize=7, color="0.4")
    handles = [Line2D([], [], linestyle="none", marker=marker, color=color, markersize=4.5, label=label)
               for label, color, marker, _role in METHODS.values()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.52, 0.985),
               ncol=3, frameon=False, fontsize=7.4, columnspacing=1.0, handletextpad=0.35)
    fig.text(0.5, 0.155, "Year · Four consecutive observed acquisitions withheld", ha="center", fontsize=8)
    fig.text(0.5, 0.087, "*2026: partial observed ACOLITE support, 10 January–3 August. Lines connect annual estimates only.", ha="center", fontsize=7)
    fig.text(0.5, 0.035, "Peak error uses 4 reference-eligible scenarios per method-year;\nreference = maximum of available QC-passed observed MCI, not the true ecological bloom peak.", ha="center", va="center", fontsize=7)
    require(verified + len(unavailable) == 90, "Plot availability count mismatch")
    STEM.parent.mkdir(parents=True, exist_ok=True)
    pdf, png, table, report = (STEM.with_suffix(s) for s in (".pdf", ".png", ".csv", ".md"))
    fig.savefig(pdf, metadata={"Title": "Figure 5 — Vombsjön annual heterogeneity", "CreationDate": None, "ModDate": None})
    fig.savefig(png, dpi=600, metadata={"Title": "Figure 5 — Vombsjön annual heterogeneity"})
    plt.close(fig)
    with table.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(selected[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    with table.open() as stream:
        require(list(csv.DictReader(stream)) == selected, "Export differs from frozen source strings")
    lines = ["# Figure 5 — Vombsjön annual heterogeneity", "",
        "Figure production only; no reconstruction, metric, normalization, aggregation, correlation, confidence interval or statistical test was recomputed.", "",
        f"Source commit: `{commit}`. Script: [46_plot_vombsjon_annual_heterogeneity.py](../../scripts/46_plot_vombsjon_annual_heterogeneity.py).",
        f"Runtime: Python {sys.version.split()[0]}; Matplotlib {matplotlib.__version__}.", "",
        "## Manuscript caption", "",
        "Annual heterogeneity of locked ACOLITE MCI reconstruction under withholding of four consecutive observed acquisitions: (a) annual nRMSE, (b) withheld-date trajectory Pearson r, and (c) mean absolute observed-proxy peak timing error in calendar days. All points are the stored annual estimates for the three primary methods; no new uncertainty intervals are added. Thin lines are visual connections between annual estimates, not continuous temporal trajectories. All eligible years from 2017 through 2026 are retained, including 2018 and 2020. The asterisk marks partial observed ACOLITE support in 2026, from 10 January to 3 August, rather than a complete annual season. Four acquisitions do not represent a fixed four-day gap.", "",
        "Peak error uses 4 reference-eligible scenarios per method-year. Peak timing refers to the maximum of the available QC-passed observed MCI series within annual support, not the true ecological bloom peak. This is satellite-MCI reconstruction evidence, not field validation; it does not imply contemporaneous field–satellite validation in 2018. Default TIMESAT double logistic retains p_seapar=1 and the smoothing spline retains the Erken-selected p_smooth=10. nRMSE and absolute peak error are saved within-year scenario means; correlation uses the saved within-year median-collapsed withheld-date predictions. Annual peak-error availability and support are reported below; unavailable values, if present, remain missing without imputation or connecting across them.", "",
        "## Validation and sources", "",
        f"PASS: {verified} plotted estimates exactly match committed annual-summary values, checked also against Matplotlib coordinates. All 90 expected records are retained. Unavailable annual values: {len(unavailable)}. CSV preserves every selected source decimal string and denominator. Source bytes match both Git and the frozen manifest. Only ACOLITE, consecutive four-acquisition withholding and the three frozen primary methods are selected. Annual scenario totals agree with eligibility; all ten years are eligible. The 2026 support endpoints are explicitly checked. No source table, scientific result, configuration, freeze or execution specification is written by this script.", ""]
    for name, digest in HASHES.items():
        lines.append(f"- [{name}](../../{SOURCE_ROOT}{name}): SHA256 `{digest}`.")
    lines.extend(["", "## Annual availability and support", "",
        "Dates are observed annual support, not assertions of full-year coverage. Scenario counts are per method; overlapping windows remain nested within years. Peak counts below are available annual peak-error scenarios for each of the three methods, in legend order.", "",
        "| Year | Support start | Support end | Eligible dates | Four-acquisition scenarios | Available peak-error scenarios (linear / default DL / spline) |",
        "|---|---|---|---:|---:|---|"])
    for year in YEARS:
        r = support[year]
        counts = [next(s["n_scenarios_available"] for s in selected if s["panel"] == "c" and s["year"] == str(year) and s["reconstruction_method"] == m) for m in METHODS]
        lines.append(f"| {year}{'*' if year == 2026 else ''} | {r['support_start']} | {r['support_end']} | {r['n_eligible_dates']} | {r['n_scenarios']} | {' / '.join(counts)} |")
    lines.extend(["", "*2026 is partial observed support ending on 3 August. Unavailable annual values: " + ("; ".join(unavailable) if unavailable else "none") + ".", "", "## Output SHA256", ""])
    for path in (pdf, png, table):
        lines.append(f"- [{path.name}]({path.name}): `{sha(path.read_bytes())}`")
    lines.extend(["", "## Exact plotted values", "", "Original frozen decimal strings, with no presentation rounding. All rows use ACOLITE and four-consecutive-observed-acquisition withholding.", "",
        "| Panel | Year | Frozen method | Estimate | Available scenarios |", "|---|---:|---|---:|---:|"])
    for r in selected:
        lines.append("| " + " | ".join(r[k] or "unavailable" for k in ("panel", "year", "reconstruction_method", "estimate", "n_scenarios_available")) + " |")
    report.write_text("\n".join(lines) + "\n")
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
