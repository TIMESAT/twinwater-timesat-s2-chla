#!/usr/bin/env python3
"""Validate the frozen Phase 3 contract without generating performance."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_preflight import (  # noqa: E402
    build_preperformance_products,
    write_preperformance_products,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_timesat_python = os.environ.get("TIMESAT_PYTHON", sys.executable)
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 3 implementation/pre-performance gates, freeze and "
            "verify TIMESAT defaults, and generate deterministic sparse/support/"
            "controlled-mask manifests. No Erken reconstruction performance is run."
        )
    )
    parser.add_argument(
        "--temporal-master",
        type=Path,
        default=ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv",
    )
    parser.add_argument(
        "--timesat-python",
        type=Path,
        default=Path(default_timesat_python),
        help=(
            "Python executable containing timesat==4.4.1 and timesat-cli==1.9.2. "
            "Defaults to TIMESAT_PYTHON or the current interpreter."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "phase3" / "preflight",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Validate all gates in memory without writing deterministic products.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tables, manifest = build_preperformance_products(
        repository_root=ROOT,
        temporal_master_path=args.temporal_master,
        timesat_python=args.timesat_python,
        runtime_script=ROOT / "scripts" / "07_timesat_runtime.py",
    )
    paths = []
    if not args.no_write:
        paths = write_preperformance_products(tables, manifest, args.output_dir)
    print(
        f"Contract: {manifest['contract_version']}; sparse inputs: "
        f"{manifest['input_provenance']['n_sparse_inputs']}; "
        f"pre-performance gates passed: "
        f"{manifest['all_preperformance_gates_passed']}."
    )
    for gate in manifest["gates"]:
        print(f"[{ 'PASS' if gate['passed'] else 'FAIL' }] {gate['gate']}: {gate['detail']}")
    print(
        "Scientific reconstruction performance generated: False; inspected: False."
    )
    if paths:
        print(f"Wrote {len(paths)} deterministic preflight products to {args.output_dir}.")
    if not manifest["all_preperformance_gates_passed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
