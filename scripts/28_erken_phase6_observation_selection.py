#!/usr/bin/env python3
"""Apply the frozen 6/9 Erken observation rule to committed QA tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_observation_selection import (  # noqa: E402
    ObservationSelectionError,
    default_config_path,
    load_selection_config,
    run_observation_selection,
    write_selection_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the frozen Erken L1C/L2A/ACOLITE observation-selection "
            "table from committed QA/index tables. Uses >=6 valid pixels in "
            "the primary 3x3 window; does not read CHLF, perform field "
            "matching, rank processors, or run TIMESAT."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(ROOT),
        help="Frozen observation-selection YAML configuration.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_selection_config(args.config, repository_root=ROOT)
        result = run_observation_selection(config=config, repository_root=ROOT)
        written = write_selection_outputs(
            result, config=config, repository_root=ROOT
        )
    except ObservationSelectionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print("Frozen Erken Sentinel-2 observation selection (no CHLF)")
    print(f"  candidate_dates: {result.counts['candidate_dates']}")
    print(f"  methods: {result.counts['methods']}")
    print(f"  unified_rows: {result.counts['rows']}")
    print(
        "  exact_three_method_source_alignment_dates: "
        f"{result.counts['exact_three_method_source_alignment_dates']}"
    )
    for method, counts in result.counts["by_method"].items():
        print(
            f"  {method}: NDCI={counts['ndci_eligible']}, "
            f"MCI={counts['mci_eligible']}, "
            f"common_B456={counts['common_b456_eligible']}"
        )
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    print("STOP: observation selection is frozen; CHLF has not been inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
