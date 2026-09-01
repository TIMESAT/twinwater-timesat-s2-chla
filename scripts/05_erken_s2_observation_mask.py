#!/usr/bin/env python3
"""Build the frozen Erken date-level Sentinel-2 SCL observation mask."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_mask import (  # noqa: E402
    build_mask_analysis,
    generate_mask_figures,
    load_mask_config,
    write_mask_outputs,
)
from twinwater_timesat.s2_roi import read_and_validate_diagnostics  # noqa: E402


DEFAULT_CONFIG = ROOT / "config" / "erken_s2_observation_mask.yaml"
DEFAULT_INVENTORY = ROOT / "data" / "processed" / "erken_s2_l2a_inventory.csv"
DEFAULT_SCENES = ROOT / "data" / "processed" / "erken_s2_scl_scene_summary.csv"
DEFAULT_MASK = ROOT / "data" / "processed" / "erken_s2_observation_mask.csv"
DEFAULT_TABLES = ROOT / "results" / "tables"
DEFAULT_FIGURES = ROOT / "results" / "figures"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate committed Erken Sentinel-2 SCL summaries, compare a compact "
            "set of SCL-only integer-pixel QC rules, collapse products to unique "
            "calendar dates, and write the frozen date-level observation mask."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Versioned mask config (default: {DEFAULT_CONFIG.relative_to(ROOT)}).",
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
        help=f"Long SCL scene/window CSV (default: {DEFAULT_SCENES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--mask-output",
        type=Path,
        default=DEFAULT_MASK,
        help=f"Final date-level mask CSV (default: {DEFAULT_MASK.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=DEFAULT_TABLES,
        help=f"Diagnostic CSV directory (default: {DEFAULT_TABLES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES,
        help=f"Diagnostic figure directory (default: {DEFAULT_FIGURES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Write and validate CSV outputs only.",
    )
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_mask_config(args.config)
    inventory, scenes = read_and_validate_diagnostics(args.inventory, args.scenes)
    tables, final_mask = build_mask_analysis(inventory, scenes, config)
    csv_paths = write_mask_outputs(
        tables,
        final_mask,
        tables_directory=args.tables_dir,
        mask_path=args.mask_output,
    )
    figure_paths: list[Path] = []
    if not args.skip_figures:
        figure_paths = generate_mask_figures(tables, final_mask, args.figures_dir)

    preferred = tables["erken_s2_scl_qc_rule_sensitivity.csv"].loc[
        lambda data: data["rule_role"].eq("preferred")
    ].iloc[0]
    input_qc = tables["erken_s2_mask_input_qc.csv"].set_index("metric")
    print(
        f"Validated primary interval {config['reference_start'].date()} through "
        f"{config['reference_end'].date()}: {int(preferred['n_products'])} products, "
        f"{int(preferred['n_candidate_dates'])} unique calendar dates."
    )
    print(
        f"Duplicate dates={int(preferred['n_dates_with_multiple_products'])}; "
        "maximum products/date="
        f"{input_qc.loc['maximum_products_per_date', 'value']}; all products retained."
    )
    print(
        f"Frozen rule {preferred['rule_id']}: "
        f"{int(preferred['n_products_passing'])} products pass and "
        f"{int(preferred['n_usable_dates'])} unique dates are usable."
    )
    print(
        "Same-day alternate products rescue "
        f"{int(preferred['n_dates_rescued_by_alternate_product'])} date(s)."
    )
    print(
        f"Wrote {len(csv_paths)} CSV file(s), including "
        f"{_display_path(args.mask_output)}."
    )
    if args.skip_figures:
        print("Skipped figures by request.")
    else:
        print(
            f"Wrote {len(figure_paths)} figure file(s) to "
            f"{_display_path(args.figures_dir)}."
        )
    print("No CHLF, reflectance, spectral index, or reconstruction result was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
