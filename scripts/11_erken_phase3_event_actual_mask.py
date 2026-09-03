#!/usr/bin/env python3
"""Guarded execution of frozen actual-mask seasonal-event performance."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.event_benchmark import (  # noqa: E402
    build_actual_mask_event_products,
    write_actual_mask_event_products,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-performance", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results/phase3/event_actual_mask",
    )
    args = parser.parse_args(argv)
    if not args.execute_performance:
        parser.error("Refusing event performance without --execute-performance")
    tables, manifest = build_actual_mask_event_products(repository_root=ROOT)
    paths = write_actual_mask_event_products(tables, manifest, args.output_dir)
    print(f"Wrote {len(paths)} Phase A products; rows={manifest['n_event_method_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
