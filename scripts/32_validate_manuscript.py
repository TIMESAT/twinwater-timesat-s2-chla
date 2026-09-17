#!/usr/bin/env python3
"""Validate that manuscript headline values match committed result products.

This checker is read-only. It does not rerun scientific analyses or alter any
frozen result. Its purpose is to keep the narrative artifact synchronized with
the repository evidence from which it was written.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANUSCRIPT = ROOT / "manuscript" / "manuscript.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the repository-derived manuscript.")
    parser.add_argument("--manuscript", type=Path, default=DEFAULT_MANUSCRIPT)
    return parser.parse_args()


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def keyed(path: str, key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows(path)}


def close(actual: str | float, expected: float, *, tolerance: float = 1e-6) -> None:
    value = float(actual)
    if not math.isclose(value, expected, rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"Expected {expected}, found {value}")


def require_text(text: str, snippets: list[str]) -> None:
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        raise AssertionError(f"Manuscript is missing expected evidence: {missing}")


def validate(manuscript: Path) -> dict[str, int]:
    text = manuscript.read_text(encoding="utf-8")
    lowered = text.lower()
    for marker in ("todo", "tbd", "insert citation", "lorem ipsum"):
        if marker in lowered:
            raise AssertionError(f"Unresolved manuscript placeholder: {marker}")

    figures = re.findall(r"!\[[^]]+]\(([^)]+)\)", text)
    if len(figures) != 5:
        raise AssertionError(f"Expected five manuscript figures, found {len(figures)}")
    for relative in figures:
        if not (manuscript.parent / relative).resolve().is_file():
            raise AssertionError(f"Missing figure: {relative}")

    actual = keyed(
        "results/phase5/synthesis/erken_phase5_actual_mask_equal_year_summary.csv",
        "method",
    )
    expected_actual = {
        "linear_interpolation": (0.20346328824253312, 0.8638929950675112, 157.45983889359035),
        "timesat_smoothing_spline": (0.22292936847424422, 0.8302380174949224, 187.0741745586739),
        "timesat_double_logistic_default_seapar1": (
            0.25045631794676765,
            0.7417982635896657,
            125.95976563919242,
        ),
        "timesat_double_logistic_cv_seapar": (
            0.23889271264377612,
            0.7756142146280499,
            139.4638196106074,
        ),
    }
    for method, expected in expected_actual.items():
        row = actual[method]
        close(row["equal_year_mean_nrmse"], expected[0])
        close(row["equal_year_mean_pearson_correlation"], expected[1])
        close(row["equal_year_mean_absolute_integral_error"], expected[2])

    events = rows(
        "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_metrics.csv"
    )
    expected_events = {
        "linear_interpolation": (18, 17),
        "timesat_smoothing_spline": (15, 15),
        "timesat_double_logistic": (8, 5),
    }
    for method, (matched, success_10d) in expected_events.items():
        selected = [row for row in events if row["method"] == method]
        if len(selected) != 18:
            raise AssertionError(f"Expected 18 event rows for {method}, found {len(selected)}")
        actual_matched = sum(row["event_status"] == "matched" for row in selected)
        actual_success = sum(row["success_10d"].lower() == "true" for row in selected)
        if (actual_matched, actual_success) != (matched, success_10d):
            raise AssertionError(
                f"Unexpected event result for {method}: {(actual_matched, actual_success)}"
            )

    selections = rows(
        "results/phase5/synthesis/erken_phase5_selection_by_outer_year.csv"
    )
    if [int(float(row["outer_test_year"])) for row in selections] != list(range(2019, 2026)):
        raise AssertionError("Double-logistic selection years are incomplete or unordered")
    if any(float(row["selected_p_seapar"]) != 0.0 for row in selections):
        raise AssertionError("Manuscript no longer matches the selected p_seapar values")

    association = rows("results/phase6c/erken_s2_chlf_association_summary.csv")
    primary = {
        (row["metric"], row["observation_method"]): row
        for row in association
        if row["support"] == "primary_common" and row["stratum_type"] == "overall"
    }
    expected_rho = {
        ("NDCI", "L1C"): (215, 0.162291),
        ("NDCI", "L2A"): (215, 0.200106),
        ("NDCI", "ACOLITE"): (215, 0.213973),
        ("MCI", "L1C"): (220, 0.412558),
        ("MCI", "L2A"): (220, 0.509588),
        ("MCI", "ACOLITE"): (220, 0.458043),
    }
    for key, (count, rho) in expected_rho.items():
        row = primary[key]
        if int(row["n_pairs_raw_CHLF"]) != count:
            raise AssertionError(f"Unexpected common-support count for {key}")
        close(row["spearman_rho"], rho, tolerance=5e-7)

    matchup_rows = rows("results/phase6c/erken_s2_chlf_matchup_audit.csv")
    if len(matchup_rows) != 2778:
        raise AssertionError(f"Expected 2778 observation-audit rows, found {len(matchup_rows)}")

    require_text(
        text,
        [
            "2,420 unique calendar dates",
            "1,950 dates were classified as open water",
            "307 of 926 acquisition dates",
            "288 reconstruction inputs",
            "2,800 random-deletion masks",
            "5,746 exhaustive internal gap windows",
            "Linear interpolation | 0.203 | 0.864 | 157.5 | 18/18 | 17/18",
            "TIMESAT double logistic default | 0.250 | 0.742 | 126.0 | 8/18 | 5/18",
            "Vombsjön data and results were not accessed",
        ],
    )

    word_count = len(re.findall(r"\b[\w'-]+\b", text))
    return {"figures": len(figures), "headline_checks": 34, "word_count": word_count}


def main() -> int:
    args = parse_args()
    summary = validate(args.manuscript.resolve())
    print(
        "Manuscript audit PASS: "
        f"{summary['headline_checks']} headline checks, "
        f"{summary['figures']} figures, {summary['word_count']} source words"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
