#!/usr/bin/env python3
"""Audit the committed Erken reliability synthesis and its provenance."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_contract import canonical_json_payload_sha256, sha256_file  # noqa: E402
from twinwater_timesat.reliability_synthesis import (  # noqa: E402
    ANALYSIS_VERSION,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    INPUT_PATHS,
    OUTPUT_DIRECTORY,
    PRIMARY_METHODS,
    PRIMARY_YEARS,
    STARTING_COMMIT,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    output = ROOT / OUTPUT_DIRECTORY
    manifest_path = output / "erken_reliability_synthesis_manifest_v1.0.json"
    require(manifest_path.exists(), "Reliability synthesis manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["analysis_version"] == ANALYSIS_VERSION, "Analysis version mismatch.")
    require(manifest["starting_commit"] == STARTING_COMMIT, "Starting commit mismatch.")
    require(manifest["bootstrap"]["replicates"] == BOOTSTRAP_REPLICATES, "Bootstrap count mismatch.")
    require(manifest["bootstrap"]["master_seed"] == BOOTSTRAP_SEED, "Bootstrap seed mismatch.")
    require(manifest["analysis_scope"] == "erken_only_saved_results", "Scope is not Erken-only.")
    require(not manifest["vombsjon_data_or_performance_inspected"], "Manifest records forbidden Vomb inspection.")
    require(not manifest["second_freeze_executed"], "Manifest incorrectly records a second freeze.")
    require(all("vomb" not in path.lower() for path in INPUT_PATHS), "Input allowlist contains Vomb.")
    for path, expected in manifest["input_sha256"].items():
        require(sha256_file(ROOT / path) == expected, f"Input checksum mismatch: {path}")
    for path, expected in manifest["implementation_sha256"].items():
        require(sha256_file(ROOT / path) == expected, f"Implementation checksum mismatch: {path}")
    for name, expected in manifest["output_sha256"].items():
        require(sha256_file(output / name) == expected, f"Output checksum mismatch: {name}")
    payload = canonical_json_payload_sha256(
        manifest, excluded_keys=("manifest_payload_sha256",)
    )
    require(payload == manifest["manifest_payload_sha256"], "Manifest payload checksum mismatch.")

    actual = pd.read_csv(output / "erken_reliability_actual_mask_year_method.csv")
    require(tuple(sorted(actual["year"].unique())) == PRIMARY_YEARS, "Actual-mask year set mismatch.")
    require(set(actual["method"].unique()) == set(PRIMARY_METHODS), "Actual-mask method set mismatch.")
    require(len(actual) == 21, "Actual-mask table must contain 21 year-method rows.")
    require(actual["reconstruction_status"].eq("ok").all(), "Actual-mask reconstruction failure found.")

    random_year = pd.read_csv(output / "erken_reliability_random_year_method_deletion.csv")
    require(len(random_year) == 84, "Random year-first table must contain 84 strata rows.")
    require(random_year["n_scenarios"].sum() == 8400, "Random scenario-method denominator mismatch.")
    consecutive_year = pd.read_csv(output / "erken_reliability_consecutive_duration_year_method.csv")
    require(len(consecutive_year) == 84, "Consecutive year-first table must contain 84 duration rows.")
    require(consecutive_year["n_scenarios"].sum() == 17238, "Consecutive scenario-method denominator mismatch.")

    actual_summary = pd.read_csv(output / "erken_reliability_actual_mask_equal_year_summary.csv")
    require(
        actual_summary["n_years_metric_available"].eq(7).all(),
        "An actual-mask summary metric does not contain all seven years.",
    )
    require(
        (actual_summary["cluster_bootstrap_ci_lower"] <= actual_summary["equal_year_estimate"]).all()
        and (actual_summary["equal_year_estimate"] <= actual_summary["cluster_bootstrap_ci_upper"]).all(),
        "An actual-mask estimate lies outside its bootstrap interval.",
    )

    audit = pd.read_csv(output / "erken_reliability_denominator_audit.csv")
    require(audit["n_reconstruction_failures"].sum() == 0, "Unexpected reconstruction failure in audit.")
    require(audit["n_metric_unavailable"].sum() == 0, "Unexpected unavailable metric in audit.")
    activity_cuts = pd.read_csv(output / "erken_reliability_consecutive_activity_tertile_cuts.csv")
    require(set(activity_cuts["duration_days"]) == {10, 20, 30, 45}, "Activity cuts missing a duration.")
    require((activity_cuts["lower_tertile_cut"] <= activity_cuts["upper_tertile_cut"]).all(), "Invalid activity tertiles.")

    report = (output / "erken_reliability_report_v1.0.md").read_text(encoding="utf-8")
    require("简明中文结论" in report, "Chinese conclusion is missing.")
    require("English Results draft" in report and "English Discussion draft" in report, "English draft sections are missing.")
    require("no second freeze executed" in report.lower(), "Second-freeze boundary is not explicit.")
    for index in range(1, 5):
        for suffix in ("png", "pdf"):
            matches = list(output.glob(f"figure_{index:02d}_*.{suffix}"))
            require(len(matches) == 1 and matches[0].stat().st_size > 0, f"Figure {index} {suffix} missing.")

    print("Erken reliability synthesis audit: PASS")
    print(f"Verified {len(manifest['output_sha256'])} hashed outputs and all core denominators.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
