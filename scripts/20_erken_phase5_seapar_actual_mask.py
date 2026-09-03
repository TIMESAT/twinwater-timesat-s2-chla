#!/usr/bin/env python3
"""Run isolated actual-mask performance for CV-selected p_seapar."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_actual import (  # noqa: E402
    run_seapar_actual_mask,
    write_seapar_actual_mask,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-performance", action="store_true")
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get("TIMESAT_PYTHON", sys.executable),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "results/phase5/double_logistic_seapar_actual_mask",
    )
    args = parser.parse_args()
    if not args.execute_performance:
        parser.error("Refusing Phase S2 performance without --execute-performance")
    tables, manifest, audit = run_seapar_actual_mask(
        repository_root=ROOT, timesat_python=args.timesat_python
    )
    paths = write_seapar_actual_mask(
        tables, manifest, audit, args.output_directory
    )
    print(f"Phase S2 {audit['audit_status']}; wrote {len(paths)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
