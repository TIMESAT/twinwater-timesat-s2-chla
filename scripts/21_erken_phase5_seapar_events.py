#!/usr/bin/env python3
"""Run frozen 18-event sensitivity from saved Phase S2 trajectories."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_actual import (  # noqa: E402
    run_seapar_events,
    write_seapar_events,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-performance", action="store_true")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=(
            ROOT / "results/phase5/double_logistic_seapar_event_actual_mask"
        ),
    )
    args = parser.parse_args()
    if not args.execute_performance:
        parser.error("Refusing Phase S3 event performance without --execute-performance")
    tables, manifest, audit = run_seapar_events(repository_root=ROOT)
    paths = write_seapar_events(tables, manifest, audit, args.output_directory)
    print(f"Phase S3 {audit['audit_status']}; wrote {len(paths)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
