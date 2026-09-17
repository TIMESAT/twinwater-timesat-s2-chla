#!/usr/bin/env python3
"""Run the frozen Erken Sentinel-2 processing-baseline control audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_processing_baseline import (  # noqa: E402
    ProcessingBaselineError,
    default_config_path,
    load_processing_baseline_config,
    run_processing_baseline_audit,
    write_processing_baseline_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit exact Sentinel-2 processing baselines, generation context "
            "and 3x3 B4/B5/B6 reflectance provenance for Erken. Verifies the "
            "existing metadata offset conversion and refuses an empirical "
            "cross-baseline correction without same-acquisition products "
            "processed under distinct baselines. Does not read CHLF, recompute "
            "Phase 6C, rank processors, run TIMESAT, or access Vombsjön."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(ROOT),
        help="Frozen Phase 6D processing-baseline YAML configuration.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_processing_baseline_config(
            args.config, repository_root=ROOT
        )
        result = run_processing_baseline_audit(
            config=config, repository_root=ROOT
        )
        written = write_processing_baseline_outputs(
            result, config=config, repository_root=ROOT
        )
    except ProcessingBaselineError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("Erken Phase 6D Sentinel-2 processing-baseline audit")
    for key, value in result.counts.items():
        print(f"  {key}: {value}")
    print(f"  harmonization_gate: {result.gate_status}")
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    print(
        "STOP: baseline provenance audited; no empirical correction, CHLF "
        "recalculation, reconstruction, or Vombsjön access."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
