#!/usr/bin/env python3
"""Run training-only LOYO selection for the p_seapar sensitivity."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_selection import (  # noqa: E402
    run_seapar_selection,
    write_seapar_selection,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-selection", action="store_true")
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get("TIMESAT_PYTHON", sys.executable),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "results/phase5/double_logistic_seapar_selection",
    )
    args = parser.parse_args()
    if not args.execute_selection:
        parser.error("Refusing real LOYO candidate evaluation without --execute-selection")
    tables, manifest, audit = run_seapar_selection(
        repository_root=ROOT, timesat_python=args.timesat_python
    )
    paths = write_seapar_selection(tables, manifest, audit, args.output_directory)
    print(f"Phase S1 {manifest['audit_status']}; wrote {len(paths)} files.")
    for year, value in manifest["selected_p_seapar"].items():
        print(f"{year}: p_seapar={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
