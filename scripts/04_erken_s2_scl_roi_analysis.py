#!/usr/bin/env python3
"""Analyse real Erken Sentinel-2 SCL windows without freezing QC thresholds."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_roi import (  # noqa: E402
    build_analysis_tables,
    generate_roi_figures,
    read_and_validate_diagnostics,
    write_analysis_tables,
)


DEFAULT_INVENTORY = ROOT / "data" / "processed" / "erken_s2_l2a_inventory.csv"
DEFAULT_SCENES = ROOT / "data" / "processed" / "erken_s2_scl_scene_summary.csv"
DEFAULT_TABLES = ROOT / "results" / "tables"
DEFAULT_FIGURES = ROOT / "results" / "figures"
DEFAULT_REFERENCE_START = "2019-04-17"
DEFAULT_REFERENCE_END = "2025-11-30"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the committed real Erken Sentinel-2 L2A SCL diagnostics, "
            "compare station-centred 1x1 through 11x11 windows, and write "
            "science-ready tables and figures. This analysis does not select a "
            "final water/bad-SCL usability threshold."
        )
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help=f"Product inventory CSV (default: {DEFAULT_INVENTORY.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--scenes",
        type=Path,
        default=DEFAULT_SCENES,
        help=f"Long scene/window CSV (default: {DEFAULT_SCENES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=DEFAULT_TABLES,
        help=f"CSV output directory (default: {DEFAULT_TABLES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES,
        help=f"Figure output directory (default: {DEFAULT_FIGURES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--reference-start",
        default=DEFAULT_REFERENCE_START,
        help=f"Inclusive primary-overlap start date (default: {DEFAULT_REFERENCE_START}).",
    )
    parser.add_argument(
        "--reference-end",
        default=DEFAULT_REFERENCE_END,
        help=f"Inclusive primary-overlap end date (default: {DEFAULT_REFERENCE_END}).",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Write and validate tables only; useful for lightweight automated checks.",
    )
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inventory, scenes = read_and_validate_diagnostics(args.inventory, args.scenes)
    tables, primary = build_analysis_tables(
        inventory,
        scenes,
        reference_start=args.reference_start,
        reference_end=args.reference_end,
    )
    table_paths = write_analysis_tables(tables, args.tables_dir)
    figure_paths: list[Path] = []
    if not args.skip_figures:
        figure_paths = generate_roi_figures(
            primary,
            tables["erken_s2_scl_window_year_summary.csv"],
            tables["erken_s2_scl_central_pixel_class_frequency.csv"],
            args.figures_dir,
        )

    valid_products = scenes.loc[scenes["analysis_valid"], "product_id"].nunique()
    primary_products = primary["product_id"].nunique()
    invalid_products = inventory["product_id"].nunique() - valid_products
    print(
        f"Validated {len(inventory)} products: valid={valid_products}, "
        f"missing/invalid={invalid_products}."
    )
    print(
        f"Primary overlap {args.reference_start} through {args.reference_end}: "
        f"{primary_products} acquisitions, {len(primary)} window rows."
    )
    print(f"Wrote {len(table_paths)} table(s) to {_display_path(args.tables_dir)}.")
    if args.skip_figures:
        print("Skipped figures by request.")
    else:
        print(
            f"Wrote {len(figure_paths)} figure file(s) "
            f"to {_display_path(args.figures_dir)}."
        )
    print("No final water-fraction or bad-SCL usability threshold was applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
