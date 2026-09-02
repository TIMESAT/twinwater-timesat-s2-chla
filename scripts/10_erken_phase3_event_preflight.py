#!/usr/bin/env python3
"""Freeze Erken reference events without evaluating real reconstructions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.event_preflight import (  # noqa: E402
    build_event_preflight_products,
    write_event_preflight_products,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen reference-only Erken seasonal-event preflight and "
            "synthetic matching gates. No real reconstruction event-level "
            "performance is generated or inspected."
        )
    )
    parser.add_argument(
        "--temporal-master",
        type=Path,
        default=ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "phase3" / "event_preflight",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run all reference-only and synthetic gates without writing products.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tables, manifest = build_event_preflight_products(
        repository_root=ROOT,
        temporal_master_path=args.temporal_master,
    )
    paths = []
    if not args.no_write:
        paths = write_event_preflight_products(tables, manifest, args.output_dir)
    print(
        f"Protocol: {manifest['protocol_version']}; reference events: "
        f"{manifest['reference_event_count']}; pre-performance gates passed: "
        f"{manifest['all_preperformance_gates_passed']}."
    )
    for gate in manifest["gates"]:
        print(f"[{'PASS' if gate['passed'] else 'FAIL'}] {gate['gate']}")
    print("Event-level performance generated: False; inspected: False.")
    if paths:
        print(f"Wrote {len(paths)} reference-only products to {args.output_dir}.")
    return 0 if manifest["all_preperformance_gates_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
