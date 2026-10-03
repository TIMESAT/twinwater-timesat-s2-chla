#!/usr/bin/env python3
"""Render manuscript Figure 4 from committed frozen values; no analysis runs.

Run from any directory with Python >=3.11 and matplotlib >=3.7:
    python scripts/45_plot_vombsjon_primary_transfer.py
Outputs are confined to manuscript/figures/figure_04_vombsjon_primary_transfer.*
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

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "figure04-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = "results/vombsjon/locked_transfer/v1.0/"
STEM = ROOT / "manuscript/figures/figure_04_vombsjon_primary_transfer"
HASHES = {
    "vombsjon_transfer_equal_year_summary.csv": "af3efcd45da4f01f74a90ff1d16483f1b4374188d3b6e60bc5338409035ae2a1",
    "vombsjon_transfer_peak_metrics.csv": "92a5b93ecc3e1ad9def88afa421567b80e0b46616008f61a6ed879c75f75b00a",
}
# Existing method colors: src/twinwater_timesat/seapar_review.py.
METHODS = {
    "linear_interpolation": ("Linear interpolation", "#0072B2", "o", "primary_simple_baseline"),
    "timesat_double_logistic": ("TIMESAT double logistic (default)", "#D55E00", "s", "primary_frozen_default_benchmark"),
    "timesat_smoothing_spline": ("TIMESAT smoothing spline", "#009E73", "^", "primary_frozen_erken_selected_spline"),
}
PANELS = {
    "a": ("nrmse_training_q95_minus_q05", "Pointwise reconstruction", "Equal-year nRMSE", (0.10, 0.40)),
    "b": ("trajectory_pearson_r", "Trajectory agreement", "Withheld-date Pearson r", (0.50, 0.90)),
    "c": ("peak_success_10d", "Observed-proxy peak", "Proportion within ±10 days", (-0.025, 1.0)),
}
DESIGNS = (("isolated", 1), ("consecutive", 2), ("consecutive", 3), ("consecutive", 4))


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    commit = git("rev-parse", "HEAD").decode().strip()
    manifest = json.loads(git("show", f"{commit}:{SOURCE_ROOT}vombsjon_transfer_manifest.json"))
    sources = {}
    for name, expected in HASHES.items():
        blob = git("show", f"{commit}:{SOURCE_ROOT}{name}")
        require(sha(blob) == expected == manifest["output_sha256"][name], f"Frozen hash mismatch: {name}")
        require((ROOT / SOURCE_ROOT / name).read_bytes() == blob, f"Local source differs: {name}")
        sources[name] = list(csv.DictReader(io.StringIO(blob.decode())))

    summary = sources["vombsjon_transfer_equal_year_summary.csv"]
    peaks = sources["vombsjon_transfer_peak_metrics.csv"]
    selected = []
    for panel, (metric, *_rest) in PANELS.items():
        for kind, block in DESIGNS:
            for method, (_label, _color, _marker, role) in METHODS.items():
                matches = [r for r in summary if (r["processor"], r["scenario_kind"],
                    int(r["block_size_observed_dates"]), r["reconstruction_method"], r["metric"])
                    == ("ACOLITE", kind, block, method, metric)]
                require(len(matches) == 1, "Expected exactly one frozen row per plotted point")
                row = matches[0]
                require(row["analysis_role"] == role and row["processor_role"] == "primary_aquatic_atmospheric_correction", "Frozen role mismatch")
                require(row["n_years_total"] == row["n_years_available"] == "10", "Year coverage changed")
                require(row["n_bootstrap_finite"] == "10000", "Bootstrap coverage changed")
                require(int(row["n_scenarios_total"]) == 325 - 10 * block, "Scenario count changed")
                denominator = 10 * block if panel == "c" else 325 - 10 * block
                require(int(row["n_scenarios_available"]) == denominator, "Metric denominator changed")
                if panel == "c":
                    eligible = [r for r in peaks if r["processor"] == "ACOLITE"
                        and r["scenario_kind"] == kind and int(r["block_size_observed_dates"]) == block
                        and r["reconstruction_method"] == method and r["reference_eligible"] == "True"]
                    require(len(eligible) == denominator, "Peak reference-eligibility count mismatch")
                values = [float(row[k]) for k in ("ci_lower", "estimate", "ci_upper")]
                require(all(math.isfinite(v) for v in values) and values == sorted(values), "Invalid saved estimate/interval")
                selected.append({"panel": panel, **row})

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "axes.labelsize": 8, "axes.titlesize": 8.5, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(1, 3, figsize=(7.48, 3.50))
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.32, top=0.79, wspace=0.43)
    verified = 0
    for ax, (panel, (_metric, title, ylabel, limits)) in zip(axes, PANELS.items(), strict=True):
        for method_index, (method, (_label, color, marker, _role)) in enumerate(METHODS.items()):
            rows = [r for r in selected if r["panel"] == panel and r["reconstruction_method"] == method]
            x = [i + (method_index - 1) * 0.19 for i in range(4)]
            y = [float(r["estimate"]) for r in rows]
            lo = [float(r["ci_lower"]) for r in rows]
            hi = [float(r["ci_upper"]) for r in rows]
            bars = ax.vlines(x, lo, hi, color=color, linewidth=0.85, alpha=0.70)
            ax.hlines(lo, [v-0.035 for v in x], [v+0.035 for v in x], color=color, linewidth=0.85, alpha=0.70)
            ax.hlines(hi, [v-0.035 for v in x], [v+0.035 for v in x], color=color, linewidth=0.85, alpha=0.70)
            points, = ax.plot(x, y, linestyle="none", marker=marker, color=color,
                              markersize=4.2, markeredgecolor="white", markeredgewidth=0.4)
            require(list(points.get_ydata()) == y, "Rendered estimate mismatch")
            for segment, lower, upper in zip(bars.get_segments(), lo, hi, strict=True):
                require(segment[0, 1] == lower and segment[1, 1] == upper, "Rendered interval mismatch")
                verified += 1
        ax.set(xlim=(-0.5, 3.5), ylim=limits, ylabel=ylabel)
        ax.set_title(f"({panel})  {title}", loc="left", pad=9)
        ax.set_xticks(range(4), ["Isolated", "2", "3", "4"])
        ax.tick_params(length=3)
        ax.text(0.02, 0.96, "Lower is better" if panel == "a" else "Higher is better",
                transform=ax.transAxes, va="top", fontsize=7, color="0.4")
        if panel == "c":
            for i in range(4):
                ax.text(i, -0.20, f"n = {10*(i+1)}", transform=ax.get_xaxis_transform(),
                        ha="center", va="top", fontsize=7)
            ax.text(0.5, -0.30, "Reference-eligible scenarios\nper method",
                    transform=ax.transAxes, ha="center", va="top", fontsize=7)
    handles = [Line2D([], [], linestyle="none", marker=marker, color=color, markersize=4.5, label=label)
               for label, color, marker, _role in METHODS.values()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.52, 0.985),
               ncol=3, frameon=False, fontsize=7.4, columnspacing=1.0, handletextpad=0.35)
    fig.text(0.5, 0.125, "Observed acquisitions withheld (isolated or 2–4 consecutive)", ha="center", fontsize=8)
    fig.text(0.5, 0.062, "ACOLITE MCI · 10 years (2017–2026) · Equal-year estimates and saved 95% whole-year bootstrap intervals",
             ha="center", fontsize=7)
    fig.text(0.5, 0.015, "Peak reference: maximum of available QC-passed observed MCI, not the true ecological bloom peak.", ha="center", fontsize=7)
    require(verified == 36, "Expected 36 verified plotted estimates and intervals")
    STEM.parent.mkdir(parents=True, exist_ok=True)
    pdf, png, table, report = (STEM.with_suffix(s) for s in (".pdf", ".png", ".csv", ".md"))
    fig.savefig(pdf, metadata={"Title": "Figure 4 — Primary Vombsjön locked transfer", "CreationDate": None, "ModDate": None})
    fig.savefig(png, dpi=600, metadata={"Title": "Figure 4 — Primary Vombsjön locked transfer"})
    plt.close(fig)
    with table.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    require(list(csv.DictReader(table.open())) == selected, "Full-precision export differs from source strings")
    lines = ["# Figure 4 — Primary Vombsjön locked transfer", "",
        "Production figure only; no reconstruction, performance metric, aggregation, correlation, confidence interval, or statistical test was computed.", "",
        f"Source commit: `{commit}`. Script: [45_plot_vombsjon_primary_transfer.py](../../scripts/45_plot_vombsjon_primary_transfer.py).",
        f"Runtime: Python {sys.version.split()[0]}; Matplotlib {matplotlib.__version__}.", "",
        "## Caption", "",
        "ACOLITE MCI locked transfer: (a) equal-year nRMSE, (b) equal-year withheld-date trajectory Pearson correlation, and (c) equal-year proportion of reference-eligible scenarios with reconstructed observed-proxy peak within ±10 calendar days. Points and intervals are copied from the frozen summary; intervals are the saved 95% percentile intervals from 10,000 whole-year bootstrap draws. All plotted metrics have 10/10 available years (2017–2026); 2026 has partial observed support. Horizontal offsets separate methods within each design and have no numerical meaning. Two, three and four refer to consecutive observed acquisitions withheld, not calendar-day gap lengths.", "",
        "Pointwise scenario counts per method are 315/305/295/285. Peak reference-eligible counts per method are only 10/20/30/40; overlapping scenarios remain nested within years. Peak success uses all reference-eligible scenarios, with unavailable reconstruction peaks or failed fits counted as non-success under the frozen rule. The peak reference is the maximum of the available QC-passed observed MCI series, not the true ecological bloom maximum. Default double logistic retains p_seapar=1; the transferred spline retains the Erken-selected p_smooth=10. Correlation is the saved arithmetic equal-year summary of within-year, median-collapsed withheld-date predictions. Individual interval overlap or separation is not a significance test.", "",
        "## Validation and provenance", "",
        "PASS: all 36 plotted estimates and 72 interval endpoints match committed source values, including direct checks of Matplotlib point and interval coordinates. Exported CSV preserves source decimal strings exactly. Peak denominators independently match counts of saved reference_eligible=True records; no peak statistic was recalculated.", ""]
    for name, digest in HASHES.items():
        lines.append(f"- [{name}](../../{SOURCE_ROOT}{name}): SHA256 `{digest}`; committed bytes, local bytes, and frozen manifest agree.")
    lines.extend(["", "## Output SHA256", ""])
    for path in (pdf, png, table):
        lines.append(f"- [{path.name}]({path.name}): `{sha(path.read_bytes())}`")
    lines.extend(["", "## Exact plotted values", "", "Original CSV decimal strings; no presentation rounding. Design 1 is isolated; designs 2–4 are consecutive acquisitions.", "",
        "| Panel | Acquisitions | Frozen method | Estimate | Lower 95% | Upper 95% | Available scenarios |", "|---|---:|---|---:|---:|---:|---:|"])
    for r in selected:
        lines.append("| " + " | ".join(r[k] for k in ("panel", "block_size_observed_dates", "reconstruction_method", "estimate", "ci_lower", "ci_upper", "n_scenarios_available")) + " |")
    report.write_text("\n".join(lines) + "\n")
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
