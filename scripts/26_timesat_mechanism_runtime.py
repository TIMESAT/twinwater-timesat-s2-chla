#!/usr/bin/env python3
"""JSON-lines bridge for the isolated diagnostic TIMESAT build."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_contract import load_timesat_defaults_snapshot  # noqa: E402
from twinwater_timesat.timesat_adapter import _run_timesat_core  # noqa: E402


def _date_for_index(year: int, index: int, ignored_day: int) -> str:
    from timesat_cli.dateutils import date_with_ignored_day

    return pd.Timestamp(date_with_ignored_day(year, index, ignored_day)).strftime(
        "%Y-%m-%d"
    )


def execute(request: dict[str, object]) -> dict[str, object]:
    import timesat

    snapshot = load_timesat_defaults_snapshot(
        ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
    )
    parameters = {
        **snapshot["effective_runtime_parameters"],
        "p_seapar": float(request["p_seapar"]),
    }
    override = request.get("coarse_smoothing_override")
    timesat.configure_erken_mechanism_diagnostic(
        0 if override is None else 1,
        1000.0 if override is None else float(override),
    )
    result = _run_timesat_core(
        year=int(request["year"]),
        dates=[pd.Timestamp(value) for value in request["dates"]],
        values=[float(value) for value in request["values"]],
        method="timesat_double_logistic",
        smoothing=None,
        parameters=parameters,
    )
    diagnostic = timesat.get_erken_mechanism_diagnostic()
    actual_smoothing = float(diagnostic[0])
    ybase = float(diagnostic[1])
    curve_length = int(diagnostic[2])
    error_flag = int(diagnostic[3])
    raw_peak_count = int(diagnostic[4])
    filtered_peak_count = int(diagnostic[5])
    initialized_season_count = int(diagnostic[6])
    full_curve = np.asarray(diagnostic[7], dtype=float)[:curve_length]
    raw_peaks = np.asarray(diagnostic[8], dtype=int)[:raw_peak_count]
    filtered_peaks = np.asarray(diagnostic[9], dtype=int)[:filtered_peak_count]
    if curve_length != 1095:
        raise RuntimeError(
            f"Expected one-year extended coarse curve length 1095; found {curve_length}."
        )
    central_curve = full_curve[365:730]
    ignored_day = int(parameters["p_ignoreday"])

    def central_peak_records(peaks: np.ndarray) -> list[dict[str, object]]:
        records = []
        for full_index in peaks.tolist():
            if 366 <= full_index <= 730:
                central_index = int(full_index - 365)
                records.append(
                    {
                        "full_extended_index": int(full_index),
                        "central_year_index": central_index,
                        "peak_time": _date_for_index(
                            int(request["year"]), central_index, ignored_day
                        ),
                    }
                )
        return records

    result["mechanism_diagnostic"] = {
        "override_enabled": override is not None,
        "requested_coarse_smoothing_override": (
            None if override is None else float(override)
        ),
        "actual_internal_coarse_smoothing": actual_smoothing,
        "base_value": ybase,
        "coarse_curve_length_full_extended": curve_length,
        "coarse_error_flag": error_flag,
        "raw_peak_count_full_extended": raw_peak_count,
        "filtered_peak_count_full_extended": filtered_peak_count,
        "initialized_season_count_full_extended": initialized_season_count,
        "coarse_dates": [
            _date_for_index(int(request["year"]), index, ignored_day)
            for index in range(1, 366)
        ],
        "coarse_curve": central_curve.tolist(),
        "raw_peaks_central_year": central_peak_records(raw_peaks),
        "filtered_peaks_central_year": central_peak_records(filtered_peaks),
    }
    return result


def main() -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = {"ok": True, "result": execute(request)}
        except Exception as exc:
            response = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        print(json.dumps(response, separators=(",", ":"), allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
