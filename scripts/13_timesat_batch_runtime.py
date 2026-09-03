#!/usr/bin/env python3
"""Persistent JSON-lines transport for the already frozen TIMESAT runtime."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_contract import load_timesat_defaults_snapshot  # noqa: E402
from twinwater_timesat.timesat_adapter import _run_timesat_core, probe_runtime  # noqa: E402


def main() -> int:
    snapshot_path = Path(sys.argv[1])
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    probe_runtime(snapshot_path, smoke_test=False)
    parameters = snapshot["effective_runtime_parameters"]
    for line in sys.stdin:
        request = json.loads(line)
        try:
            result = _run_timesat_core(
                year=int(request["year"]),
                dates=request["dates"],
                values=request["values"],
                method=request["method"],
                smoothing=request.get("smoothing"),
                parameters=parameters,
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
