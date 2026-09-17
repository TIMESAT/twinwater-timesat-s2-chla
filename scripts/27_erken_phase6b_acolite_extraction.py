#!/usr/bin/env python3
"""Extract Erken ACOLITE rhos, QA flags, NDCI and MCI without running ACOLITE."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_acolite import (  # noqa: E402
    AcoliteConfigError,
    AcoliteExtractionError,
    default_acolite_config_path,
    load_acolite_config,
    run_acolite_extraction,
    write_acolite_outputs,
)


ACOLITE_ROOT_ENVIRONMENT_VARIABLE = "ERKEN_ACOLITE_ROOT"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract already-generated Erken ACOLITE L2R rhos and L2W "
            "l2_flags on the Phase 6A-compatible 20 m 1/3/5/7/11 windows, "
            "then calculate QA-only NDCI/MCI tables. This command does not "
            "run atmospheric correction, inspect CHLF, or run TIMESAT."
        )
    )
    parser.add_argument(
        "--acolite-root",
        type=Path,
        default=None,
        help=(
            "Root containing <L1C product>/acolite directories. Falls back "
            f"to ${ACOLITE_ROOT_ENVIRONMENT_VARIABLE}; never stored in outputs."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results" / "phase6b" / "acolite",
        help=(
            "Isolated output namespace (default: results/phase6b/acolite)."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_acolite_config_path(ROOT),
        help="ACOLITE extraction configuration YAML.",
    )
    parser.add_argument(
        "--require-real-archive",
        action="store_true",
        help="Fail instead of stopping cleanly when no ACOLITE root is supplied.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    archive = args.acolite_root
    if archive is None:
        value = os.environ.get(ACOLITE_ROOT_ENVIRONMENT_VARIABLE, "").strip()
        archive = Path(value) if value else None

    if archive is None:
        message = (
            "No ACOLITE archive root was supplied (--acolite-root or "
            f"${ACOLITE_ROOT_ENVIRONMENT_VARIABLE}). No output was written."
        )
        if args.require_real_archive:
            print(f"ERROR: {message}", file=sys.stderr)
            return 2
        print(f"STOP: {message}")
        return 0
    if not archive.is_dir():
        print(f"ERROR: ACOLITE archive root is not a directory: {archive}", file=sys.stderr)
        return 2

    try:
        config = load_acolite_config(args.config, repository_root=ROOT)
        result = run_acolite_extraction(
            config=config,
            repository_root=ROOT,
            acolite_root=archive,
        )
        written = write_acolite_outputs(
            result,
            config=config,
            repository_root=ROOT,
            output_root=args.output_root,
        )
    except (AcoliteConfigError, AcoliteExtractionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print("Erken ACOLITE QA-only extraction (no CHLF, no performance, no TIMESAT)")
    for key, value in result.counts.items():
        print(f"  {key}: {value}")
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    print(
        "STOP: ACOLITE extraction is complete, but the final minimum valid-pixel "
        "threshold remains NOT_SELECTED_REQUIRES_HUMAN_FREEZE."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
