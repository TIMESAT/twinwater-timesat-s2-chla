#!/usr/bin/env python3
"""Run one frozen controlled-gap family from a clean committed worktree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.controlled_benchmark import (  # noqa: E402
    run_controlled_family,
    write_controlled_family,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-performance", action="store_true")
    parser.add_argument(
        "--family",
        required=True,
        choices=["random_deletion", "consecutive_internal_gap"],
    )
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get("TIMESAT_PYTHON", sys.executable),
    )
    args = parser.parse_args()
    if not args.execute_performance:
        parser.error("Refusing controlled-gap performance without explicit authorization")
    directory = (
        ROOT / "results/phase4/random_deletion"
        if args.family == "random_deletion"
        else ROOT / "results/phase4/consecutive_gaps"
    )
    tables, manifest = run_controlled_family(
        repository_root=ROOT,
        timesat_python=args.timesat_python,
        family=args.family,
    )
    paths = write_controlled_family(tables, manifest, directory)
    print(f"Wrote {len(paths)} files; scenarios={manifest['n_scenarios']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
