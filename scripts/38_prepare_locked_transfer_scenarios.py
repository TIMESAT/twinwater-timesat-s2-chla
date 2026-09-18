#!/usr/bin/env python3
"""Prepare locked date-level holdout scenarios from a passed observation audit.

This utility does not reconstruct or evaluate performance. It is intended for
the post-freeze Vomb input-audit stage, after the caller has materialized the
three standardized columns requested below.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.transfer_freeze import (  # noqa: E402
    enumerate_holdout_scenarios,
    load_transfer_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize the frozen isolated and consecutive date holdouts."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--value-column", default="MCI_median")
    parser.add_argument("--eligible-column", default="mci_observation_eligible")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_transfer_config(ROOT)
    table = pd.read_csv(args.input)
    required = [args.date_column, args.value_column, args.eligible_column]
    missing = [column for column in required if column not in table.columns]
    if missing:
        raise ValueError(f"Input observation audit is missing columns: {missing}")
    standardized = table[required].rename(
        columns={
            args.date_column: "date",
            args.value_column: "value",
            args.eligible_column: "eligible",
        }
    )
    holdout = config["holdout_design"]
    scenarios = enumerate_holdout_scenarios(
        standardized,
        minimum_full_year_dates=int(holdout["minimum_full_year_eligible_dates"]),
        minimum_training_dates=int(holdout["minimum_retained_training_dates"]),
        block_sizes=tuple(holdout["consecutive"]["block_sizes_observed_dates"]),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scenarios.to_csv(args.output, index=False, lineterminator="\n")
    print(f"Wrote {len(scenarios)} frozen date-level holdout scenarios to {args.output}.")
    print("No reconstruction or performance evaluation was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
