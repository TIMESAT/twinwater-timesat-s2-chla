#!/usr/bin/env python3
"""Audit the committed Erken-only second freeze and reliability correction."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_contract import (  # noqa: E402
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.transfer_freeze import (  # noqa: E402
    CONFIG_PATH,
    CORRECTED_REPORT_NAME,
    CORRECTION_DIRECTORY,
    CORRIGENDUM_MANIFEST_NAME,
    FREEZE_MANIFEST_NAME,
    FREEZE_VERSION,
    OUTPUT_DIRECTORY,
    SOURCE_RELIABILITY_MANIFEST,
    load_transfer_config,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    config = load_transfer_config(ROOT)
    output = ROOT / OUTPUT_DIRECTORY
    correction = ROOT / CORRECTION_DIRECTORY
    manifest = json.loads((output / FREEZE_MANIFEST_NAME).read_text(encoding="utf-8"))
    require(manifest["freeze_version"] == FREEZE_VERSION, "Freeze version mismatch.")
    require(
        manifest["status"] == "FROZEN_COMPLETE_ERKEN_ONLY_VOMB_PERFORMANCE_NOT_RUN",
        "Freeze status is not complete and Erken-only.",
    )
    require(
        manifest["starting_commit"] == config["starting_commit"],
        "Starting commit mismatch.",
    )
    require(
        manifest["repository"]["worktree_dirty_at_materialization_start"] is False,
        "Final freeze manifest was not materialized from a clean implementation commit.",
    )
    guards = manifest["scientific_guards"]
    require(guards["erken_only_selection"], "Freeze is not recorded as Erken-only.")
    require(not guards["vombsjon_input_read"], "Manifest records Vomb input access.")
    require(not guards["vombsjon_performance_run"], "Manifest records Vomb performance.")
    require(guards["second_freeze_complete"], "Second freeze is not complete.")
    require(manifest["final_spline"]["p_smooth"] == 10, "Final spline is not 10.")
    require(not manifest["final_spline"]["outer_fold_mode_used"], "Outer-fold mode was used.")
    require(
        np.isclose(manifest["final_spline"]["selected_score"], 0.212145438496667),
        "Final spline score changed.",
    )
    require(
        manifest["primary_methods"]
        == [
            "linear_interpolation",
            "timesat_double_logistic",
            "timesat_smoothing_spline",
        ],
        "Primary method set changed.",
    )
    require(
        manifest["cv_double_logistic_role"]
        == "secondary_sensitivity_not_primary_replacement",
        "CV double logistic role changed.",
    )
    require(
        manifest["synthetic_validation"]["all_passed"],
        "Synthetic holdout validation did not pass.",
    )
    require(
        manifest["synthetic_validation"]["timesat_runtime_affine_equivariance"]
        == "pass",
        "TIMESAT affine-equivariance validation did not pass.",
    )

    for relative, expected in manifest["input_sha256"].items():
        require(sha256_file(ROOT / relative) == expected, f"Input hash mismatch: {relative}")
    for relative, expected in manifest["implementation_sha256"].items():
        require(
            sha256_file(ROOT / relative) == expected,
            f"Implementation hash mismatch: {relative}",
        )
    for relative, expected in manifest["output_sha256"].items():
        require(sha256_file(ROOT / relative) == expected, f"Output hash mismatch: {relative}")
    require(
        canonical_json_payload_sha256(
            manifest, excluded_keys=("manifest_payload_sha256",)
        )
        == manifest["manifest_payload_sha256"],
        "Freeze-manifest payload hash mismatch.",
    )

    scores = pd.read_csv(output / config["outputs"]["spline_candidate_summary"])
    require(len(scores) == 8, "Spline summary must contain eight candidates.")
    selected = scores.loc[scores["selected_for_transfer"].astype(bool)]
    require(len(selected) == 1 and int(selected.iloc[0]["smoothing"]) == 10, "Spline selection mismatch.")
    require(selected.iloc[0]["rank"] == 1, "Selected spline is not rank 1.")
    require(scores["n_years"].eq(7).all(), "A candidate does not use seven equal-weight years.")
    require(
        scores["repetitions_per_candidate_year"].eq(6).all(),
        "Saved outer-fold repetitions were not audited.",
    )

    methods = pd.read_csv(output / config["outputs"]["method_parameter_basis"])
    require(len(methods) == 4, "Method table must contain three primaries and one sensitivity.")
    require(
        (methods["primary_or_sensitivity"] == "primary").sum() == 3,
        "Method table does not contain exactly three primary methods.",
    )
    sensitivity = methods.loc[
        methods["method"].eq("timesat_double_logistic_cv_sensitivity")
    ].iloc[0]
    require(
        sensitivity["primary_or_sensitivity"] == "secondary_sensitivity",
        "CV double logistic is not a secondary sensitivity.",
    )

    synthetic = pd.read_csv(output / config["outputs"]["synthetic_holdout_validation"])
    require(len(synthetic) >= 10 and synthetic["passed"].astype(bool).all(), "Synthetic audit failure.")
    runtime = json.loads(
        (output / config["outputs"]["timesat_runtime_validation"]).read_text(
            encoding="utf-8"
        )
    )
    require(runtime["all_passed"], "TIMESAT runtime validation failed.")
    require(
        not runtime["scientific_performance_evaluated"]
        and not runtime["vombsjon_data_or_performance_accessed"],
        "Runtime validation exceeded its synthetic-only scope.",
    )
    require(
        runtime["configuration"]["sha256"] == sha256_file(ROOT / CONFIG_PATH),
        "Runtime validation used a different transfer configuration.",
    )

    source_manifest = json.loads(
        (ROOT / SOURCE_RELIABILITY_MANIFEST).read_text(encoding="utf-8")
    )
    source_root = ROOT / "results/reliability_synthesis/v1.0"
    for name, expected in source_manifest["output_sha256"].items():
        require(sha256_file(source_root / name) == expected, f"Frozen v1.0 changed: {name}")
    corrected = (correction / CORRECTED_REPORT_NAME).read_text(encoding="utf-8")
    require("v1.0.1 — interpretive correction" in corrected, "Corrected report header missing.")
    require("It reduced noise" not in corrected, "Unsupported denoising wording remains.")
    require(
        corrected.count("some leave-one-year-out summaries tied, and none reversed") == 2,
        "Linear peak-timing tie/no-reversal correction is incomplete.",
    )
    require(
        "the contrast took both signs" in corrected,
        "Spline versus double-logistic sign change is not explained.",
    )
    require(
        "not a known operational input inside a hidden Vomb gap" in corrected,
        "A_gap operational limitation is missing.",
    )
    corrigendum = json.loads(
        (correction / CORRIGENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    require(not corrigendum["numeric_tables_recomputed"], "Corrigendum reran numeric tables.")
    require(not corrigendum["reconstruction_rerun"], "Corrigendum reran reconstruction.")
    require(
        canonical_json_payload_sha256(
            corrigendum, excluded_keys=("manifest_payload_sha256",)
        )
        == corrigendum["manifest_payload_sha256"],
        "Corrigendum-manifest payload hash mismatch.",
    )

    print("Erken-only second transfer freeze audit: PASS")
    print(
        f"Verified {len(manifest['input_sha256'])} inputs, "
        f"{len(manifest['implementation_sha256'])} implementation files, and "
        f"{len(manifest['output_sha256'])} outputs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
