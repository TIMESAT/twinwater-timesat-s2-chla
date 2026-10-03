#!/usr/bin/env python3
"""Render manuscript Figure 2 from committed frozen values; no analysis runs.

Run from any directory with Python >=3.11 and matplotlib >=3.7:
    python scripts/48_plot_erken_metric_tradeoffs.py
Outputs are confined to manuscript/figures/figure_02_erken_metric_tradeoffs.*
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

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "figure02-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = "results/reliability_synthesis/v1.0/"
STEM = ROOT / "manuscript/figures/figure_02_erken_metric_tradeoffs"
HASHES = {
    "erken_reliability_actual_mask_year_method.csv": "a09cfd20d60e74bfcbb2d90f2389420c0b1f4f6d4176a40e1b252b0c72d2fe9a",
    "erken_reliability_actual_mask_equal_year_summary.csv": "b390777bcd4fc746ba7294a9131537bedb5ab7afcb363618606b654f9440ea2e",
}
# Existing method colors: src/twinwater_timesat/seapar_review.py.
METHODS = {
    "linear_interpolation": ("Linear interpolation", "#0072B2", "o", "primary_simple_baseline"),
    "timesat_double_logistic": ("TIMESAT double logistic (default)", "#D55E00", "s", "primary_frozen_default_benchmark"),
    "timesat_smoothing_spline": ("TIMESAT smoothing spline", "#009E73", "^", "primary_erken_loyo_selected_spline"),
}
PANELS = {
    "a": ("nrmse", "Pointwise reconstruction", "Annual nRMSE", (0, 0.40)),
    "b": ("absolute_peak_date_error_days", "Global-peak timing", "Absolute peak error (days)", (0, 230)),
    "c": ("absolute_integral_error", "Common-support integral", "Absolute integral error\n(µg d L⁻¹)", (0, 620)),
}
YEARS = list(range(2019, 2026))
ANNUAL_FILE = "erken_reliability_actual_mask_year_method.csv"
SUMMARY_FILE = "erken_reliability_actual_mask_equal_year_summary.csv"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    commit = git("rev-parse", "HEAD").decode().strip()
    manifest = json.loads(git("show", f"{commit}:{SOURCE_ROOT}erken_reliability_synthesis_manifest_v1.0.json"))
    sources = {}
    for name, expected in HASHES.items():
        blob = git("show", f"{commit}:{SOURCE_ROOT}{name}")
        require(sha(blob) == expected == manifest["output_sha256"][name], f"Frozen hash mismatch: {name}")
        require((ROOT / SOURCE_ROOT / name).read_bytes() == blob, f"Local source differs: {name}")
        sources[name] = list(csv.DictReader(io.StringIO(blob.decode())))
    annual = [r for r in sources[ANNUAL_FILE] if r["analysis_role"] == "primary_actual_mask" and r["method"] in METHODS]
    require(len(annual) == 21, "Expected 21 saved primary annual reconstruction records")
    boundaries = set()
    for method in METHODS:
        rows = [r for r in annual if r["method"] == method]
        require(sorted(int(r["year"]) for r in rows) == YEARS, "Annual year coverage mismatch")
        for r in rows:
            year = int(r["year"])
            expected_status = "boundary_truncated_common_support" if year in (2019, 2025) else "complete_calendar_year_source_coverage"
            require(r["calendar_coverage_status"] == expected_status, "Stored boundary status mismatch")
            if r["calendar_coverage_status"] == "boundary_truncated_common_support":
                boundaries.add(year)
            require(r["reconstruction_status"] == "ok" and not r["reconstruction_failure_reason"], "Reconstruction unavailable")
            require(r["peak_timing_metric_status"] == "ok", "Peak metric unavailable")
            require(int(r["n_pointwise_evaluation_dates"]) > 0 and int(r["n_common_support_dates"]) > 0, "No evaluation support")
    require(boundaries == {2019, 2025}, "Boundary cue coverage mismatch")
    selected = []
    for panel, (metric, _title, _ylabel, limits) in PANELS.items():
        for year in YEARS:
            for method in METHODS:
                row = next(r for r in annual if r["year"] == str(year) and r["method"] == method)
                require(row[metric] and math.isfinite(float(row[metric])), "Annual metric unavailable")
                require(limits[0] <= float(row[metric]) <= limits[1], "Annual value would be clipped")
                selected.append({"panel": panel, "record_type": "annual", "source_file": ANNUAL_FILE,
                                 "metric": metric, "plotted_estimate": row[metric], **row})
        for method in METHODS:
            matches = [r for r in sources[SUMMARY_FILE] if r["method"] == method
                       and r["analysis_role"] == "primary_actual_mask" and r["metric"] == metric]
            require(len(matches) == 1, "Expected one saved aggregate per method/metric")
            row = matches[0]
            require(row["favorable_direction"] == "lower", "Unexpected metric direction")
            require(row["n_years_in_stratum"] == row["n_years_metric_available"] == "7", "Aggregate year availability mismatch")
            require(row["n_scenarios_total"] == row["n_metric_available_total"] == "7", "Aggregate denominator mismatch")
            require(row["n_reconstruction_failures_total"] == row["n_metric_unavailable_total"] == "0", "Saved aggregate has missing outcomes")
            values = [float(row[k]) for k in ("cluster_bootstrap_ci_lower", "equal_year_estimate", "cluster_bootstrap_ci_upper")]
            require(all(math.isfinite(v) for v in values) and values == sorted(values), "Invalid saved aggregate/interval")
            require(limits[0] <= values[0] <= values[2] <= limits[1], "Aggregate interval would be clipped")
            selected.append({"panel": panel, "record_type": "equal_year", "source_file": SUMMARY_FILE,
                             "plotted_estimate": row["equal_year_estimate"], **row})
    require(len(selected) == 72, "Expected 63 annual values plus 9 aggregates")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "axes.labelsize": 8, "axes.titlesize": 8.5, "xtick.labelsize": 7,
        "ytick.labelsize": 8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(1, 3, figsize=(7.48, 3.50))
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.32, top=0.76, wspace=0.46)
    annual_verified = aggregate_verified = endpoint_verified = 0
    for ax, (panel, (_metric, title, ylabel, limits)) in zip(axes, PANELS.items(), strict=True):
        for index, (method, (_label, color, marker, _role)) in enumerate(METHODS.items()):
            rows = [r for r in selected if r["panel"] == panel and r["method"] == method and r["record_type"] == "annual"]
            require([int(r["year"]) for r in rows] == YEARS, "Annual plot order mismatch")
            y = [float(r["plotted_estimate"]) for r in rows]
            line, = ax.plot(range(7), y, color=color, linewidth=0.75, marker=marker,
                            markersize=3.5, markeredgecolor="white", markeredgewidth=0.35)
            require(list(line.get_ydata()) == y, "Annual rendered-value mismatch")
            annual_verified += len(y)
            summary = next(r for r in selected if r["panel"] == panel and r["method"] == method and r["record_type"] == "equal_year")
            x = 8.1 + (index-1)*0.22
            value, lower, upper = (float(summary[k]) for k in ("equal_year_estimate", "cluster_bootstrap_ci_lower", "cluster_bootstrap_ci_upper"))
            bars = ax.vlines(x, lower, upper, color=color, linewidth=0.85, alpha=0.70)
            ax.hlines([lower, upper], x-0.05, x+0.05, color=color, linewidth=0.85, alpha=0.70)
            point, = ax.plot([x], [value], linestyle="none", marker=marker, color=color,
                             markersize=4.2, markeredgecolor="white", markeredgewidth=0.4)
            require(point.get_ydata()[0] == value, "Aggregate rendered-value mismatch")
            segment = bars.get_segments()[0]
            require(segment[0, 1] == lower and segment[1, 1] == upper, "Rendered interval mismatch")
            aggregate_verified += 1
            endpoint_verified += 2
        ax.axvline(7.0, color="0.80", linewidth=0.6, linestyle=(0, (2, 3)))
        ax.set(xlim=(-0.45, 8.8), ylim=limits, ylabel=ylabel)
        labels = [str(y) + ("*" if y in boundaries else "") for y in YEARS] + ["Equal-\nyear"]
        ax.set_xticks([*range(7), 8.1], labels, rotation=60, ha="right")
        ax.get_xticklabels()[-1].set_rotation(0)
        ax.get_xticklabels()[-1].set_ha("center")
        display_title = title.replace(" reconstruction", "\nreconstruction").replace(" timing", "\ntiming").replace(" integral", "\nintegral")
        ax.set_title(f"({panel})  {display_title}", loc="left", pad=9)
        ax.tick_params(length=3)
        ax.text(0.02, 0.97, "Lower is better", transform=ax.transAxes, va="top", fontsize=7, color="0.4")
        if panel == "b":
            ax.set_yticks([0, 50, 100, 150, 200])
        if panel == "c":
            ax.set_yticks([0, 150, 300, 450, 600])
    handles = [Line2D([], [], linestyle="none", marker=marker, color=color, markersize=4.5, label=label)
               for label, color, marker, _role in METHODS.values()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.52, 0.985),
               ncol=3, frameon=False, fontsize=7.4, columnspacing=1.0, handletextpad=0.35)
    fig.text(0.5, 0.16, "Year · Actual observation mask · Equal-year summaries shown separately", ha="center", fontsize=7.5)
    fig.text(0.5, 0.098, "* boundary-truncated common support · Lines only aid year-to-year reading", ha="center", fontsize=7)
    fig.text(0.5, 0.037, "Summary bars: saved 95% whole-year cluster-bootstrap intervals · Peak-error means are strongly year-sensitive", ha="center", fontsize=7)
    require((annual_verified, aggregate_verified, endpoint_verified) == (63, 9, 18), "Rendered count mismatch")
    STEM.parent.mkdir(parents=True, exist_ok=True)
    pdf, png, table, report = (STEM.with_suffix(s) for s in (".pdf", ".png", ".csv", ".md"))
    fig.savefig(pdf, metadata={"Title": "Figure 2 — Erken metric trade-offs", "CreationDate": None, "ModDate": None})
    fig.savefig(png, dpi=600, metadata={"Title": "Figure 2 — Erken metric trade-offs"})
    plt.close(fig)
    fields = list(dict.fromkeys(k for r in selected for k in r))
    with table.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    with table.open() as stream:
        require(list(csv.DictReader(stream)) == [{k:r.get(k, "") for k in fields} for r in selected], "Export differs from source decimal strings")
    lines = ["# Figure 2 — Erken metric trade-offs under the actual observation mask", "",
        "Figure production only; no reconstruction, normalization, metric, aggregation, confidence interval, statistical test or new cross-metric score was computed.", "",
        f"Source commit: `{commit}`. Script: [48_plot_erken_metric_tradeoffs.py](../../scripts/48_plot_erken_metric_tradeoffs.py).",
        f"Runtime: Python {sys.version.split()[0]}; Matplotlib {matplotlib.__version__}.", "",
        "## Manuscript-ready caption", "",
        "Metric-specific behavior of primary Erken reconstruction under the actual observation mask: (a) annual nRMSE, (b) absolute common-support global-peak date error in calendar days, and (c) absolute common-support seasonal integral error. Annual estimates for 2019–2025 are copied from the frozen primary_actual_mask table. The separated rightmost Equal-year category shows the saved equal-year estimate and 95% whole-year cluster-bootstrap interval for each method, based on seven equally weighted years and 10,000 whole-year resamples. Connecting lines only aid year-to-year reading; they do not represent a fitted temporal trend and do not connect to the aggregate category. Small horizontal offsets in the summary category distinguish methods without scientific meaning.", "",
        "Asterisks mark 2019 and 2025 as boundary-truncated common support, directly from calendar_coverage_status. These years remain eligible and retained in the frozen summaries. The dense-reference Erken common-support global maximum is not asserted to be the full-calendar-year ecological maximum in those years. The integral is evaluated only over the frozen common support; this is neither a Vombsjön metric nor satellite-retrieval validation. The full 2020 and 2025 peak errors are shown on a linear axis, with no clipping, transformation, broken axis or omission.", "",
        "Peak-error means are strongly influenced by particular years, especially 2025; this figure does not establish universal peak-timing superiority. The corrected v1.0.1 interpretation distinguishes ties from reversals in existing supporting omission summaries, but no leave-one-year-out results are plotted here. Linear interpolation has the lowest saved equal-year nRMSE, while default double logistic has the lowest descriptive equal-year absolute integral error. These metric-specific patterns do not establish a universal method ranking. Individual interval overlap or separation is not a significance test. No direct numerical comparison to Vombsjön is made.", "",
        "All three methods preserve their primary roles: linear interpolation is the untuned baseline; TIMESAT double logistic retains frozen effective defaults; and TIMESAT smoothing spline uses the saved Erken outer-fold selected setting. No CV-DL result is included.", "",
        "## Validation and sources", "",
        "PASS: 63 annual plotted values, 9 equal-year estimates and 18 CI endpoints exactly match committed frozen source tables, including direct Matplotlib coordinate checks. All selected rows are primary_actual_mask and use only the three primary methods, with annual coverage exactly 2019–2025. All 21 annual reconstructions have reconstruction_status=ok and peak_timing_metric_status=ok; all 63 selected annual metrics are finite. Every aggregate reports 7/7 available years and 7/7 available outcomes, zero reconstruction failures and zero metric-unavailable outcomes. The CSV preserves every source decimal string and relevant support/status fields. The 2019/2025 boundary statuses are checked explicitly; all values and intervals fit within linear axes. No result, config, protocol, freeze or source table is written by this script.", ""]
    for name, digest in HASHES.items():
        lines.append(f"- [{name}](../../{SOURCE_ROOT}{name}): SHA256 `{digest}`; committed, local and frozen-manifest bytes agree.")
    lines.extend(["- [Corrected Erken synthesis v1.0.1](../../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md): interpretation authority.",
        "- [RSE manuscript results synthesis v1.0](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md): manuscript synthesis authority.",
        "", "## Annual availability and support", "",
        "Counts and statuses below are identical across the three methods for each year. Sparse-input endpoints bound the frozen common support; n_common_support_dates counts the eligible support dates rather than asserting an uninterrupted calendar interval. All displayed metrics are available; unavailable annual values and aggregate values: none.", "",
        "| Year | First sparse input | Last sparse input | Sparse inputs | Pointwise evaluation dates | Common-support dates | Calendar coverage status |",
        "|---|---|---|---:|---:|---:|---|"])
    for year in YEARS:
        rows = [r for r in annual if r["year"] == str(year)]
        keys = ("first_sparse_input_date", "last_sparse_input_date", "diagnostic_n_sparse_inputs", "n_pointwise_evaluation_dates", "n_common_support_dates", "calendar_coverage_status")
        require(len({tuple(r[k] for k in keys) for r in rows}) == 1, "Support differs across primary methods")
        lines.append("| " + " | ".join([str(year)+("*" if year in boundaries else ""), *[rows[0][k] for k in keys]]) + " |")
    lines.extend(["", "## Output SHA256", ""])
    for path in (pdf, png, table):
        lines.append(f"- [{path.name}]({path.name}): `{sha(path.read_bytes())}`")
    lines.extend(["", "## Exact annual plotted values", "", "Original source decimal strings, without presentation rounding.", "",
        "| Panel | Year | Frozen method | Estimate |", "|---|---:|---|---:|"])
    for r in selected:
        if r["record_type"] == "annual":
            lines.append("| " + " | ".join(r[k] for k in ("panel", "year", "method", "plotted_estimate")) + " |")
    lines.extend(["", "## Exact equal-year summaries and intervals", "", "All rows have 7/7 available years and 7/7 available outcomes; zero unavailable outcomes.", "",
        "| Panel | Frozen method | Estimate | Lower 95% | Upper 95% |", "|---|---|---:|---:|---:|"])
    for r in selected:
        if r["record_type"] == "equal_year":
            lines.append("| " + " | ".join(r[k] for k in ("panel", "method", "equal_year_estimate", "cluster_bootstrap_ci_lower", "cluster_bootstrap_ci_upper")) + " |")
    report.write_text("\n".join(lines)+"\n")
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
