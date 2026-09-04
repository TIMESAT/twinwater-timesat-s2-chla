#!/usr/bin/env python3
"""Phase 6A — Erken real Sentinel-2 L1C / official ESA L2A observation pilot.

DRAFT pipeline, pending human review and freeze. Governed by
``docs/Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md`` and
``config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml``.

The real Sentinel-2 SAFE archive lives on the Linux/HPC server, so archive roots
are runtime inputs and are never committed. When a root is not supplied the run
reports what it could not do rather than guessing a path or synthesising output.

This script stops after the QA/availability outputs. It does not inspect CHLF,
compute index-versus-field performance, rank L1C against L2A, or run TIMESAT.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.s2_pilot import (  # noqa: E402
    PilotExecutionError,
    run_pilot,
    write_outputs,
)
from twinwater_timesat.s2_pilot_config import (  # noqa: E402
    PilotScopeError,
    assert_no_prohibited_site,
    default_pilot_config_path,
    load_pilot_config,
)

L1C_ROOT_ENVIRONMENT_VARIABLE = "ERKEN_S2_L1C_ROOT"
L2A_ROOT_ENVIRONMENT_VARIABLE = "ERKEN_S2_L2A_ROOT"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Erken real Sentinel-2 L1C/L2A reflectance, native QA and "
            "NDCI/MCI on the frozen station-centred 3x3 20 m support, and write "
            "QA-only availability audits under results/phase6a/."
        )
    )
    parser.add_argument(
        "--l1c-root",
        type=Path,
        default=None,
        help=(
            "Runtime path to the Erken Sentinel-2 L1C SAFE archive. Never "
            f"written to outputs. Falls back to ${L1C_ROOT_ENVIRONMENT_VARIABLE}."
        ),
    )
    parser.add_argument(
        "--l2a-root",
        type=Path,
        default=None,
        help=(
            "Runtime path to the Erken official ESA L2A SAFE archive. Never "
            f"written to outputs. Falls back to ${L2A_ROOT_ENVIRONMENT_VARIABLE}."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results" / "phase6a",
        help="Isolated Phase 6A output namespace (default: results/phase6a).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_pilot_config_path(ROOT),
        help="DRAFT pilot configuration YAML.",
    )
    parser.add_argument(
        "--require-real-archive",
        action="store_true",
        help=(
            "Fail instead of reporting a stop when no real archive root is "
            "available. Use on the Linux server."
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
    config = load_pilot_config(args.config, repository_root=ROOT)

    l1c_root = _resolve_root(args.l1c_root, L1C_ROOT_ENVIRONMENT_VARIABLE)
    l2a_root = _resolve_root(args.l2a_root, L2A_ROOT_ENVIRONMENT_VARIABLE)

    for label, root in (("L1C", l1c_root), ("L2A", l2a_root)):
        if root is None:
            continue
        assert_no_prohibited_site(root, config, context=f"{label} archive root")
        if not root.is_dir():
            print(
                f"ERROR: {label} archive root is not a directory: {root}",
                file=sys.stderr,
            )
            return 2

    if l2a_root is None:
        message = (
            "No real Sentinel-2 L2A archive root was supplied "
            f"(--l2a-root or ${L2A_ROOT_ENVIRONMENT_VARIABLE}).\n"
            "Phase 6A does not guess archive paths and does not generate "
            "synthetic scientific outputs.\n"
            "Run on the Linux server with the real roots; see the README and "
            "docs/Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md."
        )
        if args.require_real_archive:
            print(f"ERROR: {message}", file=sys.stderr)
            return 2
        print(f"STOP: {message}")
        return 0

    try:
        result = run_pilot(
            config=config,
            repository_root=ROOT,
            l2a_root=l2a_root,
            l1c_root=l1c_root,
        )
        written = write_outputs(
            result,
            config=config,
            repository_root=ROOT,
            output_root=args.output_root,
            l1c_root_provided=l1c_root is not None,
            l2a_root_provided=l2a_root is not None,
        )
    except (PilotExecutionError, PilotScopeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    counts = result.counts
    print("Phase 6A QA-only observation audit (no CHLF, no performance, no TIMESAT)")
    for key in (
        "candidate_dates",
        "frozen_representative_l2a_dates",
        "exact_l1c_l2a_pairs",
        "unmatched_or_ambiguous_dates",
        "extraction_rows",
        "failure_rows",
        "qa_inventory_rows",
    ):
        print(f"  {key}: {counts.get(key)}")
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    print(
        "STOP: the final minimum valid-pixel threshold is NOT selected here and "
        "requires human freeze before any field-matchup analysis."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
