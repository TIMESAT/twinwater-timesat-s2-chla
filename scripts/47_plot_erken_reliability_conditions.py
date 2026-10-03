#!/usr/bin/env python3
"""Render manuscript Figure 3 from committed frozen values; no analysis runs.

Run from any directory with Python >=3.11 and matplotlib >=3.7:
    python scripts/47_plot_erken_reliability_conditions.py
Outputs are confined to manuscript/figures/figure_03_erken_reliability_conditions.*
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

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "figure03-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = "results/reliability_synthesis/v1.0/"
STEM = ROOT / "manuscript/figures/figure_03_erken_reliability_conditions"
HASHES = {
    "erken_reliability_consecutive_duration_summary.csv": "acf112f1e687f63a7b842d19a6f15904f69e7f2fd8742d4639c0e4c1d286c4f5",
    "erken_reliability_consecutive_activity_summary.csv": "4cb72c969137ad38371fcfda2227f51358b157bb295c64de0212ff9107abb2c5",
    "erken_reliability_consecutive_peak_containment_summary.csv": "af9d1526674d553b3d9bed003662c05ba7d634409dc0808a5d6e563ac6bb813d",
}
# Existing method colors: src/twinwater_timesat/seapar_review.py.
METHODS = {
    "linear_interpolation": ("Linear interpolation", "#0072B2", "o", "primary_simple_baseline"),
    "timesat_double_logistic": ("TIMESAT double logistic (default)", "#D55E00", "s", "primary_frozen_default_benchmark"),
    "timesat_smoothing_spline": ("TIMESAT smoothing spline", "#009E73", "^", "primary_erken_loyo_selected_spline"),
}
PANELS = {
    "a": ("duration", "nrmse", "duration_days", ("10", "20", "30", "45"),
          "Gap-duration dependence", "Equal-year nRMSE", "Consecutive deletion-window\nduration (days)",
          "primary_controlled_consecutive_gap"),
    "b": ("activity", "nrmse", "activity_class", ("low", "medium", "high"),
          "Hidden-gap activity", "Equal-year nRMSE", "Hidden-gap activity",
          "protocol_visualization_stratum_continuous_a_gap_primary"),
    "c": ("peak_containment", "peak_timing_success_10d", "contains_reference_global_peak", ("False", "True"),
          "Global-peak containment", "Peak timing success\nwithin ±10 days", "",
          "primary_controlled_consecutive_gap"),
}


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
    selected = []
    for panel, (suffix, metric, stratum, categories, _title, _ylabel, _xlabel, role) in PANELS.items():
        name = f"erken_reliability_consecutive_{suffix}_summary.csv"
        for category in categories:
            for method in METHODS:
                matches = [r for r in sources[name] if r["method"] == method and r["metric"] == metric
                           and r[stratum] == category and (panel == "a" or r["duration_days"] == "45")]
                require(len(matches) == 1, "Expected one source row per panel/stratum/method")
                row = matches[0]
                require(row["analysis_role"] == role, "Frozen analysis role mismatch")
                require(row["favorable_direction"] == ("higher" if panel == "c" else "lower"), "Metric direction mismatch")
                require(row["n_years_in_stratum"] == row["n_years_metric_available"] == "7", "Year availability changed")
                require(row["n_metric_unavailable_total"] == row["n_reconstruction_failures_total"] == "0", "Unavailable/failure count changed")
                require(row["n_metric_available_total"] == row["n_scenarios_total"], "Scenario availability changed")
                numbers = [float(row[k]) for k in ("cluster_bootstrap_ci_lower", "equal_year_estimate", "cluster_bootstrap_ci_upper")]
                require(all(math.isfinite(v) for v in numbers) and numbers == sorted(numbers), "Invalid saved value or interval")
                selected.append({"panel": panel, "source_file": name, **row})
    require(len(selected) == 27, "Expected exactly 27 saved estimates")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "axes.labelsize": 8, "axes.titlesize": 8.5, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(1, 3, figsize=(7.48, 3.50))
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.32, top=0.76, wspace=0.46)
    verified = 0
    for ax, (panel, (_suffix, _metric, _stratum, categories, title, ylabel, xlabel, _role)) in zip(axes, PANELS.items(), strict=True):
        limits = (0.10, 0.40) if panel != "c" else (0, 1.10)
        for method_index, (method, (_label, color, marker, _method_role)) in enumerate(METHODS.items()):
            rows = [r for r in selected if r["panel"] == panel and r["method"] == method]
            # Discrete grouped positions; offsets only distinguish methods.
            x = [i + (method_index - 1) * 0.18 for i in range(len(categories))]
            y = [float(r["equal_year_estimate"]) for r in rows]
            lo = [float(r["cluster_bootstrap_ci_lower"]) for r in rows]
            hi = [float(r["cluster_bootstrap_ci_upper"]) for r in rows]
            bars = ax.vlines(x, lo, hi, color=color, linewidth=0.85, alpha=0.70)
            ax.hlines(lo, [v-0.035 for v in x], [v+0.035 for v in x], color=color, linewidth=0.85, alpha=0.70)
            ax.hlines(hi, [v-0.035 for v in x], [v+0.035 for v in x], color=color, linewidth=0.85, alpha=0.70)
            line, = ax.plot(x, y, linestyle="-" if panel == "a" else "none", linewidth=0.75,
                            marker=marker, color=color, markersize=4.2, markeredgecolor="white", markeredgewidth=0.4)
            require(list(line.get_ydata()) == y, "Rendered estimate mismatch")
            for segment, lower, upper in zip(bars.get_segments(), lo, hi, strict=True):
                require(segment[0, 1] == lower and segment[1, 1] == upper, "Rendered interval mismatch")
                require(limits[0] <= lower <= upper <= limits[1], "Interval clipped by axis")
                verified += 1
        labels = list(categories) if panel == "a" else [v.title() for v in categories] if panel == "b" else ["Peak outside\ngap", "Peak inside\ngap"]
        ax.set(xlim=(-0.5, len(categories)-0.5), ylim=limits, ylabel=ylabel, xlabel=xlabel)
        ax.set_xticks(range(len(categories)), labels)
        display_title = title.replace(" dependence", "\ndependence").replace(" activity", "\nactivity").replace(" containment", "\ncontainment")
        ax.set_title(f"({panel})  {display_title}", loc="left", pad=9)
        ax.tick_params(length=3)
        ax.text(0.02, 0.97, "Higher is better" if panel == "c" else "Lower is better",
                transform=ax.transAxes, va="top", fontsize=7, color="0.4")
        if panel == "c":
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    handles = [Line2D([], [], linestyle="none", marker=marker, color=color, markersize=4.5, label=label)
               for label, color, marker, _role in METHODS.values()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.52, 0.985),
               ncol=3, frameon=False, fontsize=7.4, columnspacing=1.0, handletextpad=0.35)
    fig.text(0.5, 0.14, "Panels (b) and (c): 45-day windows · Seven Erken years (2019–2025)", ha="center", fontsize=7)
    fig.text(0.5, 0.082, "Equal-year estimates and saved 95% whole-year cluster-bootstrap intervals", ha="center", fontsize=7)
    fig.text(0.5, 0.025, "Hidden-gap activity is retrospective, derived from the complete Erken reference; it is unknown inside a real gap.", ha="center", fontsize=7)
    require(verified == 27, "Expected 27 plotted estimates and 54 interval endpoints")
    STEM.parent.mkdir(parents=True, exist_ok=True)
    pdf, png, table, report = (STEM.with_suffix(s) for s in (".pdf", ".png", ".csv", ".md"))
    fig.savefig(pdf, metadata={"Title": "Figure 3 — Erken reliability conditions", "CreationDate": None, "ModDate": None})
    fig.savefig(png, dpi=600, metadata={"Title": "Figure 3 — Erken reliability conditions"})
    plt.close(fig)
    fields = list(dict.fromkeys(k for r in selected for k in r))
    with table.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    with table.open() as stream:
        exported = list(csv.DictReader(stream))
    require(exported == [{k: r.get(k, "") for k in fields} for r in selected], "Export changed source decimal strings")
    lines = ["# Figure 3 — Erken reliability conditions", "",
        "Figure production only; no reconstruction, reliability experiment, metric, aggregation, confidence interval or inferential comparison was recomputed.", "",
        f"Source commit: `{commit}`. Script: [47_plot_erken_reliability_conditions.py](../../scripts/47_plot_erken_reliability_conditions.py).",
        f"Runtime: Python {sys.version.split()[0]}; Matplotlib {matplotlib.__version__}.", "",
        "## Manuscript caption", "",
        "Erken reconstruction reliability under controlled consecutive deletion windows. (a) Equal-year nRMSE for 10-, 20-, 30- and 45-calendar-day windows. (b) Equal-year nRMSE within the existing low, medium and high hidden-gap activity classes for 45-day windows. (c) Equal-year global-peak timing success within ±10 calendar days for 45-day windows with the dense-reference global peak outside or inside the deletion window. Points and 95% whole-year cluster-bootstrap intervals are copied exactly from the frozen summary tables. Scenario metrics were summarized within year and stratum before equal weighting across seven Erken years (2019–2025); the saved intervals use 10,000 whole-year resamples. Method offsets distinguish overlapping symbols, not different durations or strata. Panel (a) uses discrete ordered duration groups and connecting lines only as visual guides, not a fitted response or threshold.", "",
        "The activity classes are the frozen duration-specific tertiles of continuous A_gap, a retrospective descriptor calculated from the hidden complete Erken reference. A_gap is the within-window total absolute daily change divided by the yearly common-support Q95−Q05 scale; it is not observed inside an unknown operational gap. No thresholds or bins were recalculated. Peak containment concerns the Erken dense-reference global annual peak under the frozen common-support rules, not Vombsjön observed-proxy validation. In boundary-truncated 2019 and 2025, this common-support maximum is not asserted to be the full-calendar-year maximum.", "",
        "All three primary methods retain their frozen roles: linear interpolation is the untuned baseline, TIMESAT double logistic uses frozen effective defaults, and TIMESAT smoothing spline uses the Erken outer-fold selected setting inherited by the controlled-gap experiments, without scenario retuning. Per-method scenario counts in (a) are 1379/1525/1475/1367 in duration order; in (b), 456/455/456 for low/medium/high; in (c), 1122/245 for peak outside/inside. All selected metrics are available, with seven contributing years in every stratum. Overlapping windows are nested within years and are not independent seasonal replicates.", "",
        "These descriptive conditions retain metric-specific method behavior. Interval overlap or separation is not a significance test; no universal gap-duration threshold or operational A_gap predictor is claimed. Erken nRMSE must not be compared directly with Vombsjön nRMSE because their normalization and estimands differ.", "",
        "## Validation and provenance", "",
        "PASS: all 27 plotted estimates and 54 interval endpoints match the committed source rows, including Matplotlib point/interval coordinates. CSV preserves exact source decimal strings and all source denominator fields. Panel (a) selects only nrmse and 10/20/30/45-day windows; panel (b) selects only 45-day nrmse and existing low/medium/high classes; panel (c) selects only 45-day peak_timing_success_10d and False/True peak-containment strata. Only the three primary methods are included, in manuscript order; saved analysis roles and favorable directions are checked. All selected rows have 7/7 metric-available years, zero reconstruction failures and zero unavailable metrics. No source result, config, protocol or freeze is written by this script.", ""]
    for name, digest in HASHES.items():
        lines.append(f"- [{name}](../../{SOURCE_ROOT}{name}): SHA256 `{digest}`; Git, local bytes and frozen manifest agree.")
    lines.extend(["", "## Output SHA256", ""])
    for path in (pdf, png, table):
        lines.append(f"- [{path.name}]({path.name}): `{sha(path.read_bytes())}`")
    lines.extend(["", "## Exact plotted values and availability", "",
        "All values below retain the source decimal strings. Years are metric-available / in-stratum. Scenarios are metric-available / total; unavailable metrics and reconstruction failures are zero in every row. Full source fields, including analysis_role and coverage, are preserved in the CSV.", "",
        "| Panel | Stratum | Method | Estimate | Lower 95% | Upper 95% | Years | Scenarios |",
        "|---|---|---|---:|---:|---:|---|---|"])
    for r in selected:
        stratum = r[PANELS[r["panel"]][2]]
        cells = [r["panel"], stratum, r["method"], r["equal_year_estimate"], r["cluster_bootstrap_ci_lower"], r["cluster_bootstrap_ci_upper"],
                 f"{r['n_years_metric_available']}/{r['n_years_in_stratum']}", f"{r['n_metric_available_total']}/{r['n_scenarios_total']}"]
        lines.append("| " + " | ".join(cells) + " |")
    report.write_text("\n".join(lines) + "\n")
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
