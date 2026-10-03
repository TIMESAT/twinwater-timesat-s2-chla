#!/usr/bin/env python3
"""Build Supplementary Table S5 from the committed field-consistency record; no analysis runs.

Run from any directory:
    python scripts/51_build_supplementary_table_s5.py
Writes manuscript/supplementary/tables/table_s05_vombsjon_field_satellite_proxy_consistency.{csv,md}.
Values are mapped directly from the source; no pixel count, fraction, regression or
correlation is calculated. The script stops if any locked aggregate check fails.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv"
STEM = ROOT / "manuscript/supplementary/tables/table_s05_vombsjon_field_satellite_proxy_consistency"
PROCESSORS = {"ACOLITE": "ACOLITE (primary)", "L2A": "L2A (sensitivity)", "L1C": "L1C (diagnostic)"}
ORDER = {"ACOLITE": 0, "L2A": 1, "L1C": 2}
COORD = {"accepted_measured_gps_qc_ok": "Accepted GPS", "no_measured_gps_recorded": "No GPS",
         "measured_gps_flagged_unresolved": "Unresolved coordinate"}
STATUS = {"date_level_polygon_observation": "Valid polygon observation",
          "no_eligible_polygon_observation_on_field_date": "Below two-thirds validity",
          "no_satellite_product_on_field_date": "No product"}
REASON = {"date_level_polygon_observation": "",
          "no_eligible_polygon_observation_on_field_date": "Polygon valid-pixel fraction below two-thirds on all same-day products",
          "no_satellite_product_on_field_date": "No satellite product on field date"}
COLUMNS = ["Field date", "Year", "Processor", "Field Chl-a (µg L⁻¹)", "Integrated depth (m)",
           "Coordinate status", "Contributes polygon vertex", "Same-day products (n)",
           "Polygon observation status", "Polygon MCI", "Valid pixels (of 615)", "Valid fraction",
           "Valid exact-date pair", "Reason unavailable"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    with SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == 162, f"expected 162 rows, found {len(rows)}")
    require(all(r["used_for_tuning"] == "False" for r in rows), "field values used for tuning")
    require(all(r["field_sampling_time_available"] == "False" for r in rows), "sampling time unexpectedly available")
    require({r["polygon_total_pixel_count"] for r in rows if r["polygon_total_pixel_count"]} == {"615.0"}, "polygon pixel count")
    require({r["primary_support_area_m2"] for r in rows} == {"247766.33349609375"}, "polygon area")
    rows.sort(key=lambda r: (r["field_date"], ORDER[r["method"]]))
    out = []
    for r in rows:
        valid = r["pair_available"] == "True"
        require(valid == (r["matchup_status"] == "date_level_polygon_observation"), "pair/status mismatch")
        out.append({
            "Field date": r["field_date"], "Year": r["field_year"], "Processor": PROCESSORS[r["method"]],
            "Field Chl-a (µg L⁻¹)": r["field_chla_fluorometry_ug_L"],
            "Integrated depth (m)": r["field_source_integrated_sample_depth_m"].replace("-", "–"),
            "Coordinate status": COORD[r["coordinate_status"]],
            "Contributes polygon vertex": "Yes" if r["coordinate_contributed_to_polygon"] == "True" else "No",
            "Same-day products (n)": r["n_products_considered"],
            "Polygon observation status": STATUS[r["matchup_status"]],
            "Polygon MCI": r["MCI_date_median"] if valid else "",
            "Valid pixels (of 615)": r["contributing_mci_valid_pixel_counts"] if valid else "",
            "Valid fraction": r["contributing_mci_valid_pixel_fractions"] if valid else "",
            "Valid exact-date pair": "Yes" if valid else "No",
            "Reason unavailable": REASON[r["matchup_status"]],
        })
    # Locked aggregate checks.
    dates = Counter(o["Field date"] for o in out)
    require(len(dates) == 54 and set(dates.values()) == {3}, "54 dates x 3 processors")
    years = Counter(o["Year"] for o in out if o["Processor"].startswith("ACOLITE"))
    require(years == {"2018": 6, "2019": 22, "2020": 26}, f"year counts {years}")
    expect = {"ACOLITE": ({"2019": 4, "2020": 3}, 29, 18), "L2A": ({"2019": 5, "2020": 4}, 29, 16),
              "L1C": ({"2019": 5, "2020": 4}, 29, 16)}
    for proc, (valid_by_year, no_product, below) in expect.items():
        sub = [o for o in out if o["Processor"].startswith(proc)]
        require(Counter(o["Year"] for o in sub if o["Valid exact-date pair"] == "Yes") == valid_by_year, f"valid pairs {proc}")
        require(sum(o["Polygon observation status"] == "No product" for o in sub) == no_product, f"no product {proc}")
        require(sum(o["Polygon observation status"] == "Below two-thirds validity" for o in sub) == below, f"below {proc}")
        require(Counter(o["Coordinate status"] for o in sub) == {"Accepted GPS": 21, "No GPS": 31, "Unresolved coordinate": 2}, f"coords {proc}")
    STEM.parent.mkdir(parents=True, exist_ok=True)
    with STEM.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(out)

    def fmt(value: str, kind: str) -> str:
        if value == "":
            return "—"
        if kind == "chla":
            return f"{float(value):.3f}"
        if kind == "mci":
            return f"{float(value):.6f}"
        if kind == "int":
            return str(int(float(value)))
        if kind == "frac":
            return f"{float(value):.3f}"
        return value

    lines = ["**Table S5. Complete Vombsjön field–satellite proxy-consistency audit.**", "",
             "All 54 field dates × 3 processors (162 rows). Polygon MCI is the same-day median of valid pixel-level MCI "
             "over the fixed pelagic polygon (615 pixel centres on the 20 m grid), reported only for valid exact-date pairs. "
             "A polygon observation required at least two-thirds valid pixels.", "",
             "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    kinds = ["", "", "", "chla", "", "", "", "int", "", "mci", "int", "frac", "", ""]
    for o in out:
        lines.append("| " + " | ".join(fmt(o[c], k) for c, k in zip(COLUMNS, kinds)) + " |")
    lines += ["", "Valid exact-date pairs: ACOLITE 7 (2018/2019/2020: 0/4/3), L2A 9 (0/5/4), L1C 9 (0/5/4). "
              "No processor had a valid 2018 pair.", "",
              "Field values entered no fitting, tuning or method selection. Sampling clock times are unavailable. "
              "Integrated-water-column Chl-a is not treated as satellite-surface Chl-a.", ""]
    STEM.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
