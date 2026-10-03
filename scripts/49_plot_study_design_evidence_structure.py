#!/usr/bin/env python3
"""Render conceptual manuscript Figure 1 from committed study-design evidence.

Run with Python >=3.11 and matplotlib >=3.7:
    python scripts/49_plot_study_design_evidence_structure.py
No reconstruction, metric calculation, fitting, or external inputs are used.
Only the Figure 1 PDF, 600-dpi PNG, and Markdown report are written.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "figure01-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
STEM = ROOT / "manuscript/figures/figure_01_study_design_evidence_structure"
MASTER = "docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md"
CONTRACT = "docs/Reconstruction_Analysis_Contract_v1.0.1.md"
SYNTHESIS = "docs/RSE_Manuscript_Results_Synthesis_v1.0.md"
FREEZE_PROTOCOL = "docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md"
EXECUTION = "docs/Vombsjon_Locked_Transfer_Execution_v1.0.md"
FREEZE = "config/erken_vomb_transfer_freeze_v1.1.json"
RELIABILITY = "results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md"
ERKEN_ANNUAL = "results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv"
VOMB_ROOT = "results/vombsjon/locked_transfer/v1.0/"
MANIFEST = VOMB_ROOT + "vombsjon_transfer_manifest.json"
ELIGIBILITY = VOMB_ROOT + "vombsjon_transfer_year_eligibility.csv"
FIELD = VOMB_ROOT + "vombsjon_transfer_field_consistency.csv"
# Pin the scientific sources, independently of the figure-production commit.
HASHES = {
    MASTER: "bf2e06423ef256380e0446eef1f8a643347da722550906e5dd7732f6adcc7489",
    CONTRACT: "7a111b6e806d1914233481d7cb9bf99459bc74193330b5139c18257bd905046e",
    SYNTHESIS: "68a6269a05aad7979e386edb86bd023ec95f70fd89550e062df6dc4c520ee0cf",
    FREEZE_PROTOCOL: "05295442489cb7775f183c99e58d9ab745e5bd8168d180c920e75e540b166861",
    EXECUTION: "87e9dadb7915b9c2a28e671467c82e5495b91bc2582ebbc17665fdaad59cdc61",
    FREEZE: "477cb4890daa07073cc55c24a66150dd63a9cdf9b9c949756b08c01215dc0983",
    RELIABILITY: "516f80fd0f4666f942af255eb035b7b84b8473d627ff400b054af65b01067b90",
    ERKEN_ANNUAL: "a09cfd20d60e74bfcbb2d90f2389420c0b1f4f6d4176a40e1b252b0c72d2fe9a",
    MANIFEST: "d016221d4a6071536c3b17add5a6414e1f876872734d5cf352c7abb395b33652",
    ELIGIBILITY: "e0ccbb80786e3c9cc35f72d3e6fcb377e1f226b84c4addbab119dcda49ff01ba",
    FIELD: "dce1779ce9d254bfc5c47e6d2a8384062fca04125bcc6f41e91bf6cdf65829c9",
}
PRIMARY = ["linear_interpolation", "timesat_double_logistic", "timesat_smoothing_spline"]
METHODS = [
    ("Linear interpolation", "Untuned baseline", "#0072B2", "o"),
    ("TIMESAT double logistic", "Frozen default benchmark", "#D55E00", "s"),
    ("TIMESAT smoothing spline", "Erken-selected p_smooth = 10", "#009E73", "^"),
]
# Exact scientific text on the canvas. Each entry is mapped to evidence below.
TEXT = {
    "erken_years": "2019-2025",
    "erken_source": "Dense CHLF\nreference",
    "erken_mask": "Actual Sentinel-2\nobservation mask\n\nControlled gaps:\nrandom deletion;\nconsecutive\ncalendar-day\nwindows",
    "erken_target": "Reconstruction vs\nwithheld dense\nCHLF reference",
    "erken_role": "Same-variable\ntemporal evaluation",
    "vomb_years": "2017-2026",
    "vomb_source": "Sentinel-2 MCI",
    "acolite": "ACOLITE: primary\naquatic correction",
    "processor_secondary": "Official L2A: sensitivity\nL1C TOA: diagnostic",
    "vomb_holdout": "Withhold observed\nacquisitions:\nisolated or blocks",
    "vomb_target": "Reconstruction vs\nwithheld observed\nMCI",
    "partial_support": "2026: partial support\nto 3 Aug (ACOLITE)",
    "field": "Sparse field Chl-a\nExact-date proxy\nconsistency only",
    "field_2018": "2018: no valid same-day fixed-polygon field pair",
    "erken_selection": "Erken evaluation\nYear-blocked selection",
    "freeze_heading": "Frozen reconstruction design",
    "freeze_order": "Before Vomb performance",
    "locked_transfer": "Locked transfer: Vombsjön\nNo retuning\nNo field data used for tuning",
    "cv_dl": "CV double logistic: sensitivity only\np_seapar = 0",
    "primary": "Erken actual mask vs\nwithheld CHLF\nVombsjön ACOLITE vs\nwithheld observed MCI",
    "secondary": "Erken controlled gaps\nVombsjön observed-proxy\npeak timing (conditional)",
    "sensitivity": "Official L2A sensitivity\nL1C TOA diagnostic\nCV-DL sensitivity\n±5 / ±15-day peak tolerances",
    "complementary": "Field Chl-a: exact-date\nproxy consistency\nNo daily reconstruction truth",
    "calendars": "Processor calendars\nremain independent",
}
EVIDENCE = {
    "a": [
        (["erken_years", "erken_source"], [MASTER, CONTRACT, ERKEN_ANNUAL], "Erken dense CHLF reference and seven saved actual-mask years, 2019-2025."),
        (["erken_mask", "erken_target", "erken_role"], [MASTER, CONTRACT, SYNTHESIS, RELIABILITY], "Same-variable reconstruction experiment: actual Sentinel-2 timing masks CHLF; additional random deletion and consecutive calendar-day windows are controlled missingness experiments."),
        (["vomb_years", "vomb_source", "vomb_holdout", "vomb_target"], [FREEZE, EXECUTION, ELIGIBILITY, SYNTHESIS], "2017-2026 observed MCI; primary validation withholds isolated or consecutive observed acquisitions (not consecutive calendar days)."),
        (["acolite", "processor_secondary"], [FREEZE, EXECUTION, SYNTHESIS], "ACOLITE primary aquatic atmospheric correction; official L2A separate sensitivity; L1C TOA diagnostic baseline."),
        (["partial_support"], [ELIGIBILITY, SYNTHESIS], "ACOLITE 2026 support ends 3 August; saved observed support is 10 January to 3 August."),
        (["field", "field_2018"], [FREEZE, FIELD, SYNTHESIS], "Sparse field Chl-a provides complementary exact-calendar-date fixed-polygon proxy consistency; no valid 2018 pair for any processor."),
    ],
    "b": [
        (["erken_selection", "freeze_heading", "freeze_order"], [CONTRACT, FREEZE_PROTOCOL, FREEZE], "Erken year-blocked evaluation precedes the final Erken-only freeze and Vombsjön performance inspection."),
        (["locked_transfer"], [FREEZE, EXECUTION, MANIFEST], "Locked Vombsjön transfer used no parameter tuning and no field data for tuning."),
        (["cv_dl"], [FREEZE, FREEZE_PROTOCOL, RELIABILITY], "CV double logistic p_seapar=0 is a separately reported sensitivity, not a replacement for the frozen default primary benchmark."),
    ],
    "c": [
        (["primary"], [SYNTHESIS, CONTRACT, FREEZE], "Primary quantitative targets: withheld dense-reference CHLF under the Erken actual mask, and withheld observed MCI from Vombsjön ACOLITE."),
        (["secondary"], [SYNTHESIS, CONTRACT, FREEZE], "Secondary quantitative evidence: Erken controlled gaps and conditionally identifiable Vombsjön observed-proxy peak timing."),
        (["sensitivity"], [SYNTHESIS, FREEZE], "Separate L2A and CV-DL sensitivities, L1C diagnostic baseline, and ±5/±15-day peak-tolerance sensitivities."),
        (["complementary", "calendars"], [SYNTHESIS, FREEZE, EXECUTION], "Exact-date field Chl-a proxy consistency is complementary/descriptive, not daily reconstruction truth; processors retain their own calendars."),
    ],
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_sources(commit: str) -> dict[str, bytes]:
    sources = {}
    for path, expected in HASHES.items():
        blob = git("show", f"{commit}:{path}")
        require(sha(blob) == expected, f"Committed scientific source changed: {path}")
        require((ROOT / path).read_bytes() == blob, f"Local scientific source differs: {path}")
        sources[path] = blob
    f = json.loads(sources[FREEZE])
    m = json.loads(sources[MANIFEST])
    methods = f["reconstruction_methods"]
    require(methods["primary_order"] == PRIMARY, "Primary method order changed")
    require(methods[PRIMARY[0]]["analysis_role"] == "primary_simple_baseline" and not methods[PRIMARY[0]]["tuned_parameters"], "Linear baseline role changed")
    require(methods[PRIMARY[1]]["analysis_role"] == "primary_frozen_default_benchmark" and methods[PRIMARY[1]]["p_seapar"] == 1 and not methods[PRIMARY[1]]["parameter_override_allowed"], "Default DL role changed")
    require(methods[PRIMARY[2]]["analysis_role"] == "primary_frozen_erken_selected_spline" and methods[PRIMARY[2]]["p_smooth"] == 10 and not methods[PRIMARY[2]]["vomb_performance_used"], "Transfer spline selection changed")
    cv = methods["timesat_double_logistic_cv_sensitivity"]
    require(cv["analysis_role"] == "secondary_sensitivity_not_primary_replacement" and cv["p_seapar"] == 0 and cv["reported_separately"], "CV-DL sensitivity changed")
    obs = f["observation_layer"]
    require(obs["primary_proxy"] == "MCI" and obs["proxy_role"] == "observed_satellite_proxy_not_absolute_chla", "Proxy role changed")
    require(obs["primary_processing_product"]["method"] == "ACOLITE" and obs["primary_processing_product"]["role"] == "primary_aquatic_atmospheric_correction", "ACOLITE role changed")
    require([(r["method"], r["role"]) for r in obs["processing_sensitivities"]] == [("L2A", "separate_official_product_sensitivity"), ("L1C", "separate_transparent_baseline_diagnostic")], "Processor sensitivity/diagnostic roles changed")
    require(f["scope"]["second_freeze_complete"] and not f["scope"]["vombsjon_data_or_performance_used"], "Pre-performance freeze changed")
    require(m["performance_executed"] and not m["parameters_tuned"] and not m["field_used_for_tuning"], "Locked execution tuning status changed")
    require(f["holdout_design"]["isolated"]["block_size_observed_dates"] == 1 and f["holdout_design"]["consecutive"]["block_sizes_observed_dates"] == [2, 3, 4], "Observed-acquisition holdouts changed")
    require(f["validation_roles"]["field_chla"] == "complementary_lake_specific_proxy_validation_and_ecological_consistency_only" and "daily_reconstruction_truth" in f["validation_roles"]["field_chla_not_allowed_for"], "Field role changed")
    peak = f["evaluation"]["proxy_peak_timing"]
    require(peak["role"] == "secondary_conditionally_identifiable_observed_proxy_metric" and peak["primary_tolerance_days"] == 10 and peak["sensitivity_tolerance_days"] == [5, 15], "Peak evidence role changed")
    require(peak["reference"] == "global_maximum_of_full_qc_passed_observed_mci_dates_within_fixed_year_support", "Observed-peak reference changed")
    annual = list(csv.DictReader(io.StringIO(sources[ERKEN_ANNUAL].decode())))
    for method in PRIMARY:
        require(sorted(int(r["year"]) for r in annual if r["method"] == method and r["analysis_role"] == "primary_actual_mask") == list(range(2019, 2026)), "Erken year coverage changed")
    eligibility = list(csv.DictReader(io.StringIO(sources[ELIGIBILITY].decode())))
    ac = [r for r in eligibility if r["processor"] == "ACOLITE"]
    require(sorted({int(r["year"]) for r in ac if r["eligible"] == "True"}) == list(range(2017, 2027)), "Vomb year coverage changed")
    require({(r["support_start"], r["support_end"]) for r in ac if r["year"] == "2026"} == {("2026-01-10", "2026-08-03")}, "2026 ACOLITE partial support changed")
    fields = list(csv.DictReader(io.StringIO(sources[FIELD].decode())))
    fields2018 = [r for r in fields if r["field_year"] == "2018"]
    require(len(fields2018) == 18 and {r["processor"] for r in fields2018} == {"ACOLITE", "L2A", "L1C"} and all(r["pair_available"] == "False" for r in fields2018), "2018 field-pair limitation changed")
    require(all(r["primary_support"] == "fixed_pelagic_convex_hull_polygon" and r["temporal_rule"] == "exact_same_calendar_date" and r["temporal_tolerance_days"] == "0" and r["used_for_tuning"] == "False" for r in fields), "Field evidence support/rule changed")
    for path in (ELIGIBILITY, FIELD):
        require(HASHES[path] == m["output_sha256"][Path(path).name], "Transfer metadata manifest mismatch")
    require(HASHES[FREEZE] == m["input_sha256"][FREEZE] and HASHES[EXECUTION] == m["execution_specification_sha256"], "Execution source manifest mismatch")
    # Human-readable anchors additionally guard the conceptual evidence hierarchy.
    for phrase in ("Erken controlled-gap experiments", "against withheld daily CHLF", "conditionally identifiable observed-MCI peak timing", "does not independently validate satellite retrieval accuracy", "own training/test calendars"):
        require(phrase in sources[SYNTHESIS].decode(), f"Synthesis evidence anchor absent: {phrase}")
    require(set(TEXT) == {key for entries in EVIDENCE.values() for keys, _paths, _claim in entries for key in keys}, "Unmapped scientific canvas text")
    return sources


def draw() -> tuple[plt.Figure, int]:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    width, height = 7.48, 5.60
    fig = plt.figure(figsize=(width, height), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, width), ylim=(0, height))
    ax.set_axis_off()
    text_bounds = []
    text_artists = []
    erken, erken_fill = "#546F78", "#F0F5F6"
    vomb, vomb_fill = "#786478", "#F6F1F5"
    neutral, neutral_fill = "#62666A", "#F4F5F5"

    def label(x, y, text, size=8, ha="center", va="center", weight="normal", color="#25282A", bounds=None):
        artist = ax.text(x, y, text, fontsize=size, ha=ha, va=va, fontweight=weight,
                         color=color, linespacing=1.22)
        text_artists.append(artist)
        if bounds is not None:
            text_bounds.append((artist, bounds))
        return artist

    def box(x, y, w, h, color=neutral, fill="white"):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=color, linewidth=0.65))
        return (x + 0.04, y + 0.04, x + w - 0.04, y + h - 0.04)

    def arrow(x, start, end):
        ax.add_patch(FancyArrowPatch((x, start), (x, end), arrowstyle="-|>",
                                    mutation_scale=7, linewidth=0.7, color=neutral))

    # Panel A: two separate observation and validation chains; field has no arrow.
    label(0.16, 5.39, "(a)  Two-lake observation design", size=8.7, ha="left", va="top", weight="bold")
    for x, name, yearkey, color in ((0.16, "Erken", "erken_years", erken), (1.61, "Vombsjön", "vomb_years", vomb)):
        label(x + 0.63, 5.00, name, size=9, weight="bold", color=color)
        label(x + 0.63, 4.78, TEXT[yearkey])
    b = box(0.16, 3.94, 1.26, 0.66, erken, erken_fill)
    label(0.79, 4.27, TEXT["erken_source"], bounds=b)
    arrow(0.79, 3.91, 3.66)
    b = box(0.16, 2.47, 1.26, 1.16, erken, erken_fill)
    label(0.79, 3.05, TEXT["erken_mask"], size=7.6, bounds=b)
    arrow(0.79, 2.44, 2.27)
    b = box(0.16, 1.55, 1.26, 0.69, erken, erken_fill)
    label(0.79, 1.895, TEXT["erken_target"], size=7.8, bounds=b)
    label(0.79, 1.13, TEXT["erken_role"], size=7.6, color=erken)

    b = box(1.61, 3.45, 1.26, 1.15, vomb, vomb_fill)
    label(2.24, 4.40, TEXT["vomb_source"], size=8, weight="bold", bounds=b)
    label(2.24, 4.10, TEXT["acolite"], size=7.6, bounds=b)
    ax.plot([1.71, 2.77], [3.88, 3.88], color="#D9CDD7", linewidth=0.5)
    label(2.24, 3.67, TEXT["processor_secondary"], size=7.0, bounds=b)
    arrow(2.24, 3.42, 3.21)
    b = box(1.61, 2.45, 1.26, 0.73, vomb, vomb_fill)
    label(2.24, 2.815, TEXT["vomb_holdout"], size=7.8, bounds=b)
    arrow(2.24, 2.42, 2.27)
    b = box(1.61, 1.55, 1.26, 0.69, vomb, vomb_fill)
    label(2.24, 1.895, TEXT["vomb_target"], size=7.8, bounds=b)
    label(2.24, 1.29, TEXT["partial_support"], size=7.0, color=vomb)
    b = box(1.61, 0.40, 1.26, 0.62, vomb)
    label(2.24, 0.71, TEXT["field"], size=7.6, bounds=b)
    label(0.16, 0.16, TEXT["field_2018"], size=7.0, ha="left", color=vomb)

    # Panel B: only the primary temporal workflow has connecting arrows.
    label(3.10, 5.39, "(b)  Frozen reconstruction\nand locked transfer", size=8.7, ha="left", va="top", weight="bold")
    b = box(3.10, 4.28, 2.10, 0.55, neutral, neutral_fill)
    label(4.15, 4.555, TEXT["erken_selection"], size=8, bounds=b)
    arrow(4.15, 4.25, 4.06)
    b = box(3.10, 2.00, 2.10, 2.03, neutral, neutral_fill)
    label(4.15, 3.84, TEXT["freeze_heading"], size=8.1, weight="bold", bounds=b)
    for y, (name, role, color, marker) in zip((3.50, 3.01, 2.52), METHODS, strict=True):
        ax.plot([3.27], [y], linestyle="none", marker=marker, color=color,
                markersize=4.1, markeredgecolor="white", markeredgewidth=0.35)
        label(3.42, y, name, size=7.8, ha="left", bounds=b)
        label(3.42, y - 0.19, role, size=7.2, ha="left", color="#515559", bounds=b)
    label(4.15, 2.13, TEXT["freeze_order"], size=7.2, color=neutral, bounds=b)
    arrow(4.15, 1.97, 1.69)
    b = box(3.10, 1.00, 2.10, 0.66, neutral, neutral_fill)
    label(4.15, 1.33, TEXT["locked_transfer"], size=7.8, bounds=b)
    b = box(3.10, 0.28, 2.10, 0.52, "#A8ABAE")
    label(4.15, 0.54, TEXT["cv_dl"], size=7.1, color=neutral, bounds=b)

    # Panel C: evidence roles, not performance or processor rankings.
    label(5.43, 5.39, "(c)  Evidence hierarchy", size=8.7, ha="left", va="top", weight="bold")
    cards = [
        (3.83, 1.00, "Primary quantitative", "primary", neutral_fill),
        (2.80, 0.87, "Secondary quantitative", "secondary", "#FAFAFA"),
        (1.62, 1.02, "Sensitivity / diagnostic", "sensitivity", "white"),
        (0.53, 0.93, "Complementary /\ndescriptive", "complementary", "white"),
    ]
    for y, h, heading, key, fill in cards:
        b = box(5.43, y, 1.89, h, neutral if key == "primary" else "#A8ABAE", fill)
        label(5.55, y + h - 0.17, heading, size=7.7, ha="left", weight="bold", bounds=b)
        offset = 0.49 if key == "complementary" else 0.36
        label(5.55, y + h - offset, TEXT[key], size=7.6, ha="left", va="top", bounds=b)
    label(6.375, 0.23, TEXT["calendars"], size=7.3, color=neutral)

    # Layout validation operates on rendered text, not on scientific values.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for artist, bounds in text_bounds:
        extent = artist.get_window_extent(renderer).transformed(ax.transData.inverted())
        require(extent.x0 >= bounds[0] and extent.y0 >= bounds[1] and extent.x1 <= bounds[2] and extent.y1 <= bounds[3], f"Text exceeds its box: {artist.get_text()!r}")
    for artist in text_artists:
        extent = artist.get_window_extent(renderer)
        require(fig.bbox.contains(extent.x0, extent.y0) and fig.bbox.contains(extent.x1, extent.y1), "Text clipped at canvas edge")
    for i, left in enumerate(text_artists):
        a = left.get_window_extent(renderer)
        for right in text_artists[i + 1:]:
            require(not a.overlaps(right.get_window_extent(renderer)), f"Text overlap: {left.get_text()!r} / {right.get_text()!r}")
    return fig, len(text_artists)


def write_report(commit: str, n_text: int) -> None:
    caption = (
        "**Figure 1. Study design and evidence structure.** (a) Erken's dense CHLF reference (2019-2025) supports a same-variable temporal reconstruction test under the actual Sentinel-2 observation mask and additional controlled random deletion or consecutive calendar-day deletion windows. This masking experiment does not independently validate satellite retrieval accuracy. Vombsjön (2017-2026) instead uses withheld QC-passed Sentinel-2 MCI observations as its primary quantitative reconstruction target. ACOLITE is the primary aquatic atmospheric-correction product; official L2A is a separate sensitivity and L1C TOA a diagnostic baseline, each on its own observation calendar. ACOLITE support in 2026 ends on 3 August. Sparse field Chl-a provides complementary exact-calendar-date fixed-polygon proxy-consistency evidence only; no valid same-day fixed-polygon pair exists in 2018 for any processor. (b) Erken evaluation precedes the frozen reconstruction design and locked Vombsjön transfer. Linear interpolation is the untuned baseline, default TIMESAT double logistic is the frozen benchmark (p_seapar=1), and TIMESAT smoothing spline uses the final Erken-selected transfer setting p_smooth=10. This final transfer setting is distinct from the spline settings selected within individual Erken outer folds. CV double logistic (p_seapar=0) remains a separate sensitivity. No Vombsjön performance or field data were used to choose the transferred settings, and the transfer execution performed no retuning. (c) Primary quantitative reconstruction evidence is distinguished from secondary controlled-gap and conditionally identifiable observed-proxy peak-timing evidence, separate sensitivity/diagnostic evidence, and complementary/descriptive field consistency. The Vombsjön peak reference is the maximum of the available QC-passed observed MCI series within the fixed year support, not the true ecological bloom peak; ±10 days is the primary tolerance and ±5/±15 days are sensitivities. Field Chl-a is not daily reconstruction truth."
    )
    report = ["# Figure 1 - Study design and evidence structure", "", caption, "",
              "## Reproduction and scope", "",
              "Run `python scripts/49_plot_study_design_evidence_structure.py` with Python >=3.11 and matplotlib >=3.7. The script uses committed blobs and verifies local bytes against eleven pinned source hashes. It performs metadata assertions and renders a conceptual vector schematic; it does not compute performance metrics or run any reconstruction. No CSV is required because the figure contains no quantitative result display.", "",
              f"Evidence-source commit: `{commit}`. Dimensions: 7.48 x 5.60 inches; PNG: 600 dpi; vector PDF with embedded DejaVu Sans. All scientific source files remain unchanged.", "",
              "## Scientific sources inspected", "",
              "| Source | SHA256 |", "| --- | --- |"]
    for path, digest in HASHES.items():
        report.append(f"| [{path}](../../{path}) | `{digest}` |")
    report.extend(["", "## Exact statements and evidence mapping", ""])
    for panel, entries in EVIDENCE.items():
        report.extend([f"### Panel ({panel})", ""])
        for keys, paths, claim in entries:
            exact = "; ".join("‘" + TEXT[key].replace("\n", " / ") + "’" for key in keys)
            links = ", ".join(f"[{Path(path).name}](../../{path})" for path in paths)
            report.append(f"- {exact}. {claim} Sources: {links}.")
        if panel == "b":
            for name, role, _color, _marker in METHODS:
                report.append(f"- ‘{name}’ / ‘{role}’. Sources: [freeze v1.1](../../{FREEZE}), [freeze protocol](../../{FREEZE_PROTOCOL}).")
            report.append("- The freeze is the final transfer design, not a claim that every Erken outer fold used p_smooth=10. The three method markers retain the established blue circle, orange square, and green triangle, in frozen primary order.")
        report.append("")
    report.extend(["## Role and verification details", "",
        "- The hierarchy follows the manuscript synthesis: Erken actual-mask and Vombsjön ACOLITE withheld-MCI comparisons are primary quantitative evidence; Erken controlled gaps and conditionally identifiable observed-MCI peak timing are secondary quantitative evidence.",
        "- Official L2A, CV-DL, and peak tolerances are separately labelled sensitivities. L1C is diagnostic. The shared sensitivity/diagnostic box groups reporting roles without pooling processors or comparing their performance.",
        "- Field Chl-a is complementary/descriptive proxy-consistency evidence at exact calendar dates. Fixed-polygon field support differs from the nominal-station temporal reconstruction target; exact-date matching does not establish the acquisition-minus-sampling time interval or vertical equivalence.",
        "- Assertions verify all seven Erken actual-mask years, all ten eligible ACOLITE transfer years, the primary method order/roles and final spline parameter, processor roles, observed-acquisition holdout units, field rules and tuning flags, and observed-peak role/tolerances.",
        "- All 18 saved 2018 field-date-by-processor records are unavailable pairs (six field dates for each processor). ACOLITE 2026 metadata records support from 2026-01-10 to 2026-08-03. These are availability checks, not new scientific analyses.", "",
        "## Claims intentionally not made", "",
        "- Independent retrieval validation from the Erken masking experiment; a universally best reconstruction method; or independently verified denoising.",
        "- Absolute Chl-a from MCI; daily Vombsjön field truth; field validation of reconstructed daily trajectories, unobserved ecological peaks, onset/end, or integral accuracy.",
        "- ACOLITE superiority, shared/pooled processor calendars, or a matched-calendar Vombsjön processor ranking.",
        "- Equivalence between consecutive observed-acquisition blocks and consecutive calendar-day gaps; full annual ACOLITE coverage in 2026; or valid contemporaneous polygon field validation in 2018.",
        "- New performance estimates, uncertainty intervals, statistical significance, or thresholds.", "",
        "## Visual inspection notes", "",
        f"- Automatic rendering checks passed for {n_text} text objects: all text stays inside the canvas, boxed text stays within its assigned box with inset margins, and text bounding boxes do not overlap.",
        "- The final PNG was visually reviewed at full page width and reduced manuscript size, and the exported PDF was independently rendered for review. Text, markers, and arrowheads are legible, with no clipping or overlap.",
        "- Downward arrows connect only temporal observation/evaluation chains and the Erken-to-freeze-to-transfer sequence. The isolated field and CV-DL boxes have no arrows into method fitting or selection. Lake colors encode lake roles; method colors appear only on explicit method markers. Evidence-box emphasis encodes the planned evidence hierarchy, not processor performance.",
        "- The 2018 limitation and 2026 support note fit in the schematic. Detailed peak-reference, spatial/vertical representativeness, and final-versus-outer-fold spline qualifications are in the caption/report to keep the graphic compact. No requested scientific statement was omitted because it could not be verified.", "",
        "## Output SHA256", "", "| Output | SHA256 |", "| --- | --- |"])
    for suffix in (".pdf", ".png"):
        path = STEM.with_suffix(suffix)
        report.append(f"| [{path.name}]({path.name}) | `{sha(path.read_bytes())}` |")
    report.extend(["", "The report's own hash is not embedded in itself. Only the Figure 1 script and PDF/PNG/Markdown production files are changed.", ""])
    STEM.with_suffix(".md").write_text("\n".join(report), encoding="utf-8")


def main() -> int:
    commit = git("rev-parse", "HEAD").decode().strip()
    sources = validate_sources(commit)
    fig, n_text = draw()
    STEM.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(STEM.with_suffix(".pdf"), metadata={"Title": "Figure 1 - Study design and evidence structure", "CreationDate": None, "ModDate": None})
    fig.savefig(STEM.with_suffix(".png"), dpi=600)
    plt.close(fig)
    for path, blob in sources.items():
        require((ROOT / path).read_bytes() == blob, f"Scientific source modified during plotting: {path}")
    write_report(commit, n_text)
    print("PASS: eleven committed sources unchanged; lake years, method settings/roles, processor roles, field evidence, 2018 limitation, and 2026 support verified.")
    print(f"PASS: {n_text} rendered text objects fit without text overlap or clipping.")
    for suffix in (".pdf", ".png", ".md"):
        path = STEM.with_suffix(suffix)
        print(f"{path.relative_to(ROOT)}  SHA256 {sha(path.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
