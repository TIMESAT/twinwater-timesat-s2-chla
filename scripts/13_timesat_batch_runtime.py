#!/usr/bin/env python3
"""Persistent JSON-lines transport for the already frozen TIMESAT runtime."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_contract import load_timesat_defaults_snapshot  # noqa: E402
from twinwater_timesat.timesat_adapter import (  # noqa: E402
    _parameter_array,
    _run_timesat_core,
    _validated_p_seapar,
    probe_runtime,
)


def main() -> int:
    snapshot_path = Path(sys.argv[1])
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    probe_runtime(snapshot_path, smoke_test=False)
    parameters = snapshot["effective_runtime_parameters"]
    for line in sys.stdin:
        request = json.loads(line)
        try:
            request_parameters = parameters
            sensitivity_parameter = None
            if "p_seapar" in request:
                if request["method"] != "timesat_double_logistic":
                    raise ValueError("p_seapar sensitivity is double-logistic only.")
                sensitivity_parameter = _validated_p_seapar(request["p_seapar"])
                request_parameters = {
                    **parameters,
                    "p_seapar": sensitivity_parameter,
                }
            result = _run_timesat_core(
                year=int(request["year"]),
                dates=request["dates"],
                values=request["values"],
                method=request["method"],
                smoothing=request.get("smoothing"),
                parameters=request_parameters,
            )
            if sensitivity_parameter is not None:
                materialized = _parameter_array(sensitivity_parameter, float)
                result["diagnostics"].update(
                    {
                        "requested_p_seapar": sensitivity_parameter,
                        "requested_p_seapar_float64_hex": sensitivity_parameter.hex(),
                        "effective_p_seapar": float(materialized[0]),
                        "effective_p_seapar_float64_hex": float(materialized[0]).hex(),
                        "p_seapar_array_dtype": str(materialized.dtype),
                        "p_seapar_array_unique_count": int(
                            len(set(materialized.tolist()))
                        ),
                        "p_seapar_exactly_materialized": bool(
                            all(value == sensitivity_parameter for value in materialized)
                        ),
                    }
                )
            response = {"ok": True, "result": result}
        except Exception as exc:  # preserve a per-scenario method failure
            response = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
