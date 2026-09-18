#!/usr/bin/env python3
"""Validate the frozen TIMESAT runtime and affine MCI scaling on synthetic data."""

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
    load_timesat_defaults_snapshot,
    sha256_file,
)
from twinwater_timesat.timesat_adapter import _run_timesat_core, probe_runtime  # noqa: E402
from twinwater_timesat.transfer_freeze import (  # noqa: E402
    CONFIG_PATH,
    OUTPUT_DIRECTORY,
    fit_training_affine_scale,
    load_transfer_config,
)


def main() -> int:
    config = load_transfer_config(ROOT)
    snapshot_path = ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    runtime = probe_runtime(snapshot_path, smoke_test=True)

    doys = np.arange(1, 366, 15, dtype=int)
    native = (
        -0.018
        + 0.018 * np.exp(-((doys - 105) / 42) ** 2)
        + 0.041 * np.exp(-((doys - 235) / 52) ** 2)
    )
    dates = [
        pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(day - 1))
        for day in doys
    ]
    low_scale = fit_training_affine_scale(native, scaled_minimum=100.0, scaled_maximum=900.0)
    frozen_scale = fit_training_affine_scale(
        native,
        scaled_minimum=float(config["scale_handling"]["scaled_training_minimum"]),
        scaled_maximum=float(config["scale_handling"]["scaled_training_maximum"]),
    )
    checks = []
    tolerance = 1e-8
    for method, smoothing in (
        ("timesat_double_logistic", None),
        ("timesat_smoothing_spline", 10),
    ):
        low = _run_timesat_core(
            year=2019,
            dates=dates,
            values=low_scale.transform(native).tolist(),
            method=method,
            smoothing=smoothing,
            parameters=snapshot["effective_runtime_parameters"],
        )
        frozen = _run_timesat_core(
            year=2019,
            dates=dates,
            values=frozen_scale.transform(native).tolist(),
            method=method,
            smoothing=smoothing,
            parameters=snapshot["effective_runtime_parameters"],
        )
        low_native = low_scale.inverse(np.asarray(low["prediction"], dtype=float))
        frozen_native = frozen_scale.inverse(np.asarray(frozen["prediction"], dtype=float))
        difference = np.abs(low_native - frozen_native)
        max_difference = float(np.nanmax(difference))
        passed = bool(
            low["status"] == "ok"
            and frozen["status"] == "ok"
            and np.isfinite(difference).all()
            and max_difference <= tolerance
        )
        checks.append(
            {
                "method": method,
                "smoothing": smoothing,
                "lower_scale_status": low["status"],
                "frozen_scale_status": frozen["status"],
                "maximum_native_unit_absolute_difference": max_difference,
                "absolute_tolerance": tolerance,
                "passed": passed,
            }
        )

    all_passed = bool(runtime["runtime_defaults_match_snapshot"] and runtime["smoke_test"]["passed"] and all(item["passed"] for item in checks))
    result = {
        "schema_version": "erken_transfer_timesat_runtime_validation_v1",
        "validation_date": config["freeze_date"],
        "configuration": {
            "relative_path": CONFIG_PATH.as_posix(),
            "sha256": sha256_file(ROOT / CONFIG_PATH),
        },
        "timesat_snapshot": {
            "relative_path": "config/timesat_double_logistic_defaults_v4.4.1.json",
            "sha256": sha256_file(snapshot_path),
        },
        "runtime": runtime,
        "affine_equivariance_checks": checks,
        "all_passed": all_passed,
        "scientific_performance_evaluated": False,
        "vombsjon_data_or_performance_accessed": False,
    }
    result["payload_sha256"] = canonical_json_payload_sha256(
        result, excluded_keys=("payload_sha256",)
    )
    output = ROOT / OUTPUT_DIRECTORY / config["outputs"]["timesat_runtime_validation"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not all_passed:
        failed = [item["method"] for item in checks if not item["passed"]]
        raise RuntimeError(f"TIMESAT transfer runtime validation failed: {failed}")
    print("Transfer TIMESAT runtime and affine-equivariance validation: PASS")
    for item in checks:
        print(
            f"{item['method']}: max native-unit difference "
            f"{item['maximum_native_unit_absolute_difference']:.3e}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
