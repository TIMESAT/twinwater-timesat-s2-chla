#!/usr/bin/env python3
"""Build portable Lake Erken Sentinel-2 L2A SCL diagnostic CSVs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_scl import (  # noqa: E402
    summarize_archive,
    write_inventory_summary,
    write_scene_summary,
)


DEFAULT_CONFIG = ROOT / "config" / "erken_s2_mask.yaml"
DEFAULT_SCENE_OUTPUT = ROOT / "data" / "processed" / "erken_s2_scl_scene_summary.csv"
DEFAULT_INVENTORY_OUTPUT = ROOT / "data" / "processed" / "erken_s2_l2a_inventory.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Sentinel-2 L2A products, locate the Erken station in each "
            "SCL raster, and write diagnostic class summaries."
        )
    )
    parser.add_argument(
        "--input-root",
        required=True,
        type=Path,
        help="Runtime path to the Sentinel-2 L2A archive; never written to outputs.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Diagnostic YAML configuration (default: {DEFAULT_CONFIG.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SCENE_OUTPUT,
        help=(
            "Long-format scene/window CSV "
            f"(default: {DEFAULT_SCENE_OUTPUT.relative_to(ROOT)})."
        ),
    )
    parser.add_argument(
        "--inventory-output",
        type=Path,
        default=DEFAULT_INVENTORY_OUTPUT,
        help=(
            "Product inventory CSV "
            f"(default: {DEFAULT_INVENTORY_OUTPUT.relative_to(ROOT)})."
        ),
    )
    return parser.parse_args(argv)


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"SCL diagnostic config not found: {path}")
    with path.open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    if not isinstance(config, dict):
        raise ValueError("SCL diagnostic config must be a YAML mapping.")
    return config


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    station = config["station"]
    inventory_rows, scene_rows = summarize_archive(
        args.input_root,
        station_lat=float(station["latitude"]),
        station_lon=float(station["longitude"]),
        station_crs=str(station["crs"]),
        window_sizes=[int(size) for size in config["candidate_windows"]],
        bad_scl_classes=[
            int(code) for code in config["diagnostic_bad_scl_classes"]
        ],
    )
    write_scene_summary(scene_rows, args.output)
    write_inventory_summary(inventory_rows, args.inventory_output)

    status_counts: dict[str, int] = {}
    for row in inventory_rows:
        status = str(row["processing_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    status_text = ", ".join(
        f"{status}={count}" for status, count in sorted(status_counts.items())
    ) or "none"
    print(f"Discovered {len(inventory_rows)} L2A product(s); statuses: {status_text}")
    print(f"Wrote {args.inventory_output} ({len(inventory_rows)} product rows)")
    print(f"Wrote {args.output} ({len(scene_rows)} product-window rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
