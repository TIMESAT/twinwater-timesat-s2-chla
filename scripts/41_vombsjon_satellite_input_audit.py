#!/usr/bin/env python3
"""Vombsjon raw Sentinel-2 / ACOLITE product audit and matchup materialization.

Governed by ``docs/Vombsjon_Satellite_Input_Audit_Protocol_v1.0.md`` and
``config/vombsjon_satellite_input_audit_v1.0.yaml``. Every scientific rule is
read from the frozen ``config/erken_vomb_transfer_freeze_v1.0.json`` and
cross-checked against it before any product is opened.

The real Sentinel-2 SAFE and ACOLITE archives live on the Linux/HPC server, so
the archive roots are runtime inputs and are never committed. When a root is
not supplied the run reports what it could not do rather than guessing a path
or synthesising output.

This command stops after the input audit. It does not run TIMESAT, build a
daily reconstructed curve, withhold observations, compute reconstruction
metrics, tune any rule from Vombsjon, or choose a processor from Vombsjon
performance.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.vombsjon_satellite_audit import (  # noqa: E402
    VombsjonAuditConfigError,
    VombsjonAuditError,
    VombsjonScopeError,
    default_config_path,
    load_audit_config,
    run_audit,
    write_audit_outputs,
)

L1C_ROOT_ENVIRONMENT_VARIABLE = "VOMBSJON_S2_L1C_ROOT"
L2A_ROOT_ENVIRONMENT_VARIABLE = "VOMBSJON_S2_L2A_ROOT"
ACOLITE_ROOT_ENVIRONMENT_VARIABLE = "VOMBSJON_ACOLITE_ROOT"
DEFAULT_OUTPUT_ROOT = Path("results") / "vombsjon" / "satellite_input_audit" / "v1.0"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory the Vombsjon Sentinel-2 L1C, official ESA L2A and "
            "ACOLITE products, audit L1C/L2A pairing and the actual ACOLITE "
            "layout, extract the frozen fixed-station 3x3 20 m target and the "
            "field-location target, apply the frozen 6-of-9 QC, deduplicate "
            "same-day observations per method, and materialize the derived "
            "field-satellite matchup table under "
            "results/vombsjon/satellite_input_audit/v1.0/."
        )
    )
    parser.add_argument(
        "--l1c-root",
        type=Path,
        default=None,
        help=(
            "Runtime path to the Vombsjon Sentinel-2 L1C SAFE archive. Falls "
            f"back to ${L1C_ROOT_ENVIRONMENT_VARIABLE}."
        ),
    )
    parser.add_argument(
        "--l2a-root",
        type=Path,
        default=None,
        help=(
            "Runtime path to the Vombsjon official ESA L2A SAFE archive. Falls "
            f"back to ${L2A_ROOT_ENVIRONMENT_VARIABLE}."
        ),
    )
    parser.add_argument(
        "--acolite-root",
        type=Path,
        default=None,
        help=(
            "Runtime path to the Vombsjon ACOLITE output archive. The layout is "
            "discovered from the files that are actually there, not assumed to "
            f"match the Erken layout. Falls back to ${ACOLITE_ROOT_ENVIRONMENT_VARIABLE}."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / DEFAULT_OUTPUT_ROOT,
        help=(
            "Versioned Vombsjon audit output namespace (default: "
            f"{DEFAULT_OUTPUT_ROOT.as_posix()})."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(ROOT),
        help="Vombsjon satellite input audit configuration YAML.",
    )
    parser.add_argument(
        "--require-real-archive",
        action="store_true",
        help=(
            "Fail instead of reporting a clean stop when an archive root is "
            "missing. Use on the Linux server."
        ),
    )
    parser.add_argument(
        "--record-absolute-roots",
        action="store_true",
        help=(
            "Write the literal runtime archive paths into the manifest. Off by "
            "default; the manifest always records their SHA256 identity."
        ),
    )
    return parser.parse_args(argv)


def _resolve_root(explicit: Path | None, variable: str) -> Path | None:
    if explicit is not None:
        return explicit
    value = os.environ.get(variable, "").strip()
    return Path(value) if value else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_audit_config(args.config, repository_root=ROOT)
    except VombsjonAuditConfigError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    roots = {
        "L1C": _resolve_root(args.l1c_root, L1C_ROOT_ENVIRONMENT_VARIABLE),
        "L2A": _resolve_root(args.l2a_root, L2A_ROOT_ENVIRONMENT_VARIABLE),
        "ACOLITE": _resolve_root(args.acolite_root, ACOLITE_ROOT_ENVIRONMENT_VARIABLE),
    }
    for label, root in roots.items():
        if root is not None and not root.is_dir():
            print(
                f"ERROR: {label} archive root is not a directory: {root}",
                file=sys.stderr,
            )
            return 2

    missing = [label for label, root in roots.items() if root is None]
    if missing:
        message = (
            f"No real archive root was supplied for {missing}.\n"
            "This audit does not guess archive paths and does not generate "
            "synthetic scientific outputs.\n"
            "Run on the Linux server with the real roots; see "
            "docs/Vombsjon_Satellite_Input_Audit_Protocol_v1.0.md."
        )
        if args.require_real_archive:
            print(f"ERROR: {message}", file=sys.stderr)
            return 2
        print(f"STOP: {message}")
        return 0

    try:
        result = run_audit(
            config=config,
            repository_root=ROOT,
            l1c_root=roots["L1C"],
            l2a_root=roots["L2A"],
            acolite_root=roots["ACOLITE"],
        )
        written = write_audit_outputs(
            result,
            config=config,
            repository_root=ROOT,
            output_root=args.output_root,
            record_absolute_roots=args.record_absolute_roots,
        )
    except (VombsjonAuditConfigError, VombsjonAuditError, VombsjonScopeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print(
        "Vombsjon raw satellite/product and matchup audit "
        "(no TIMESAT, no reconstruction, no performance)"
    )
    for key in (
        "l1c_products",
        "l2a_products",
        "acolite_scenes",
        "exact_unique_l1c_l2a_pairs",
        "extraction_rows",
        "fixed_target_observation_rows",
        "field_location_observation_rows",
        "same_day_rows",
        "field_matchup_rows",
        "failure_rows",
    ):
        print(f"  {key}: {result.counts.get(key)}")
    for key in (
        "fixed_target_products_by_method",
        "fixed_target_mci_eligible_by_method",
        "same_day_mci_available_dates_by_method",
    ):
        print(f"  {key}: {result.counts.get(key)}")

    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")

    if result.unresolved_items:
        print("Unresolved items recorded in the manifest:")
        for item in result.unresolved_items:
            affected = item.get("affected") or []
            suffix = f" ({len(affected)} affected)" if affected else ""
            print(f"  - {item['item']}: {item['status']}{suffix}")

    print(
        "STOP: this is the authorized input audit only. Vombsjon reconstruction "
        "performance, withheld-observation experiments and processor selection "
        "remain out of scope."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
