#!/usr/bin/env python3
"""Small JSON boundary around the frozen external TIMESAT runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.timesat_adapter import execute_runtime_request  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a machine-readable probe or one-dimensional reconstruction "
            "inside the separately frozen TIMESAT Python environment."
        )
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    result = execute_runtime_request(request)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
