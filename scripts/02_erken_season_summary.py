#!/usr/bin/env python3
"""Summarize annual Erken CHLF and generate exploratory peak/figure outputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))

from twinwater_timesat.io import read_clean_csv  # noqa: E402
from twinwater_timesat.plotting import generate_all_figures  # noqa: E402
from twinwater_timesat.seasonal import (  # noqa: E402
    annual_summary,
    complete_vs_open_water_peak_summary,
    measurement_regime_summary,
    peak_sensitivity_summary,
)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def main() -> None:
    erkennen = load_yaml(ROOT / "config" / "erken.yaml")
    project = load_yaml(ROOT / "config" / "project.yaml")
    peak_config = load_yaml(ROOT / "config" / "peak_detection_exploratory.yaml")
    outputs = erkennen["outputs"]
    years = project["years"]

    data = read_clean_csv(ROOT / outputs["clean_daily"])
    annual = annual_summary(data, years=years)
    year_path = ROOT / outputs["year_summary"]
    year_path.parent.mkdir(parents=True, exist_ok=True)
    annual.to_csv(year_path, index=False, float_format="%.10g")

    sensitivity = peak_sensitivity_summary(
        data,
        years=years,
        minimum_separation_days=int(peak_config["minimum_separation_days"]),
        prominence_fractions=peak_config["prominence_sensitivity_fractions"],
    )
    peak_path = ROOT / outputs["peak_sensitivity"]
    sensitivity.to_csv(peak_path, index=False, float_format="%.10g")

    peak_comparison = complete_vs_open_water_peak_summary(data, years=years)
    peak_comparison_path = ROOT / outputs["complete_vs_open_water_peak"]
    peak_comparison.to_csv(
        peak_comparison_path, index=False, float_format="%.10g"
    )

    regime = measurement_regime_summary(
        annual,
        sensitivity,
        primary_prominence_fraction=float(
            peak_config["primary_prominence_fraction_of_within_year_amplitude"]
        ),
    )
    regime_path = ROOT / outputs["measurement_regime_summary"]
    regime.to_csv(regime_path, index=False, float_format="%.10g")

    figures = generate_all_figures(data, annual, ROOT / outputs["figures_directory"])
    print(f"Wrote {year_path.relative_to(ROOT)} ({len(annual)} scope-year rows)")
    print(f"Wrote {peak_path.relative_to(ROOT)} ({len(sensitivity)} sensitivity rows)")
    print(
        f"Wrote {peak_comparison_path.relative_to(ROOT)} "
        f"({len(peak_comparison)} annual comparison rows)"
    )
    print(f"Wrote {regime_path.relative_to(ROOT)} ({len(regime)} regime-metric rows)")
    for figure in figures:
        print(f"Wrote {figure.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
