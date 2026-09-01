#!/usr/bin/env python3
"""Join and audit frozen Erken Sentinel-2 dates against the daily reference."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.temporal_sampling import (  # noqa: E402
    REFERENCE_END,
    REFERENCE_START,
    build_temporal_sampling_analysis,
    generate_temporal_sampling_figures,
    read_and_validate_temporal_inputs,
    write_temporal_sampling_outputs,
)


DEFAULT_DAILY = ROOT / "data" / "processed" / "erken_daily_clean.csv"
DEFAULT_MASK = ROOT / "data" / "processed" / "erken_s2_observation_mask.csv"
DEFAULT_OUTPUT = (
    ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv"
)
DEFAULT_TABLES = ROOT / "results" / "tables"
DEFAULT_FIGURES = ROOT / "results" / "figures"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and deterministically join the canonical daily Erken CHLF "
            "reference to the frozen date-level Sentinel-2 SCL mask, then write "
            "descriptive reconciliation, annual, interval, and boundary audits. "
            "This does not define final reconstruction input or run reconstruction."
        )
    )
    parser.add_argument(
        "--daily-reference",
        type=Path,
        default=DEFAULT_DAILY,
        help=f"Canonical daily CSV (default: {DEFAULT_DAILY.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--s2-mask",
        type=Path,
        default=DEFAULT_MASK,
        help=f"Frozen S2 mask CSV (default: {DEFAULT_MASK.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Joined daily master CSV (default: {DEFAULT_OUTPUT.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=DEFAULT_TABLES,
        help=f"Audit table directory (default: {DEFAULT_TABLES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES,
        help=f"Diagnostic figure directory (default: {DEFAULT_FIGURES.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--reference-start",
        default=REFERENCE_START.date().isoformat(),
        help=f"Expected inclusive daily start (default: {REFERENCE_START.date()}).",
    )
    parser.add_argument(
        "--reference-end",
        default=REFERENCE_END.date().isoformat(),
        help=f"Expected inclusive daily end (default: {REFERENCE_END.date()}).",
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
    daily, mask = read_and_validate_temporal_inputs(
        args.daily_reference,
        args.s2_mask,
        reference_start=args.reference_start,
        reference_end=args.reference_end,
    )
    tables, master = build_temporal_sampling_analysis(daily, mask)
    csv_paths = write_temporal_sampling_outputs(
        tables,
        master,
        tables_directory=args.tables_dir,
        master_path=args.output,
    )
    figure_paths: list[Path] = []
    if not args.skip_figures:
        figure_paths = generate_temporal_sampling_figures(
            master,
            tables["erken_temporal_sampling_year_summary.csv"],
            args.figures_dir,
        )

    qc = tables["erken_temporal_sampling_join_qc.csv"].set_index("metric")
    print(
        f"Validated daily reference: {len(daily)} unique rows, "
        f"{daily['date'].min().date()} through {daily['date'].max().date()}."
    )
    print(
        f"Validated frozen mask: {len(mask)} inventory dates, "
        f"{int(mask['s2_date_usable'].sum())} S2-usable dates."
    )
    print(
        "Daily reconciliation: usable matched="
        f"{qc.loc['s2_usable_dates_matching_daily_reference', 'value']}, "
        "not open water="
        f"{qc.loc['s2_usable_dates_not_openwater', 'value']}, "
        "reference missing="
        f"{qc.loc['s2_usable_dates_with_reference_missing', 'value']}, "
        "preliminary candidates="
        f"{qc.loc['preliminary_sparse_candidates', 'value']}."
    )
    print(
        f"Wrote {len(csv_paths)} CSV file(s), including {_display_path(args.output)}."
    )
    if args.skip_figures:
        print("Skipped figures by request.")
    else:
        print(
            f"Wrote {len(figure_paths)} figure file(s) to "
            f"{_display_path(args.figures_dir)}."
        )
    print(
        "Stopped at the preliminary sampling audit; no final season, year "
        "eligibility, reconstruction, or performance rule was defined."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
