#!/usr/bin/env python3
"""Run the frozen Erken Phase 6C exact-date index–CHLF analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_chlf_matchup import (  # noqa: E402
    ChlfMatchupError,
    default_config_path,
    load_chlf_matchup_config,
    run_chlf_matchup_analysis,
    write_chlf_matchup_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen Erken exact-same-date L1C/L2A/ACOLITE NDCI/MCI "
            "versus daily CHLF analysis on metric-specific common support. "
            "Does not retune observation rules, run reconstruction/TIMESAT, "
            "select a processor winner, or inspect Vombsjön."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=Path, default=default_config_path(ROOT),
        help="Frozen Phase 6C YAML configuration.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_chlf_matchup_config(args.config, repository_root=ROOT)
        result = run_chlf_matchup_analysis(config=config, repository_root=ROOT)
        written = write_chlf_matchup_outputs(result, config=config, repository_root=ROOT)
    except ChlfMatchupError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("Erken Phase 6C exact-date Sentinel-2 index–CHLF analysis")
    for key, value in result.counts.items():
        print(f"  {key}: {value}")
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    print("STOP: observation-layer analysis complete; no reconstruction or Vombsjön access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
