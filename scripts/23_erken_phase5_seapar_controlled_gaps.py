#!/usr/bin/env python3
"""Run the frozen Phase S4 controlled-gap sensitivity from a clean commit."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_controlled import (  # noqa: E402
    CONTROLLED_ROOT,
    FAMILY_SPECS,
    run_seapar_controlled_family,
    write_seapar_controlled_family,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-performance", action="store_true")
    parser.add_argument(
        "--family",
        choices=["all", *FAMILY_SPECS],
        default="all",
    )
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get("TIMESAT_PYTHON", sys.executable),
    )
    args = parser.parse_args()
    if not args.execute_performance:
        parser.error("Refusing Phase S4 performance without --execute-performance")
    families = tuple(FAMILY_SPECS) if args.family == "all" else (args.family,)

    # Do not write either family until every requested run and deterministic rerun
    # has passed from the same clean committed state.
    completed = []
    for family in families:
        completed.append(
            (
                family,
                run_seapar_controlled_family(
                    repository_root=ROOT,
                    timesat_python=args.timesat_python,
                    family=family,
                ),
            )
        )
    for family, (tables, manifest, audit) in completed:
        directory = (
            ROOT
            / CONTROLLED_ROOT
            / FAMILY_SPECS[family]["output_directory"]
        )
        paths = write_seapar_controlled_family(
            tables, manifest, audit, directory
        )
        print(
            f"Phase S4 {family} {audit['audit_status']}; "
            f"scenarios={manifest['n_scenarios']}; wrote {len(paths)} files."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
