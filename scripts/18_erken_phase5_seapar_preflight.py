#!/usr/bin/env python3
"""Freeze and verify p_seapar sensitivity gates without real performance."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_sensitivity import (  # noqa: E402
    build_seapar_preperformance_products,
    write_seapar_preperformance_products,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run synthetic-only Phase S0 p_seapar pre-performance gates."
    )
    parser.add_argument(
        "--timesat-python",
        default=os.environ.get("TIMESAT_PYTHON", sys.executable),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=(
            ROOT / "results/phase5/double_logistic_seapar_preflight"
        ),
    )
    args = parser.parse_args(argv)
    tables, manifest = build_seapar_preperformance_products(
        repository_root=ROOT,
        timesat_python=args.timesat_python,
        runtime_script=ROOT / "scripts/07_timesat_runtime.py",
    )
    paths = write_seapar_preperformance_products(
        tables, manifest, args.output_directory
    )
    print(
        f"Phase S0 PASS: {len(manifest['candidate_grid'])} candidates accepted; "
        "real sensitivity performance generated: False; Vombsjön accessed: False."
    )
    print(f"Wrote {len(paths)} files; manifest={manifest['manifest_payload_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
