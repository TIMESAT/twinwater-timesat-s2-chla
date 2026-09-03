#!/usr/bin/env python3
"""Mechanical audits for both frozen controlled-gap families."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.controlled_benchmark import audit_controlled_family  # noqa: E402
from twinwater_timesat.phase3_preflight import write_deterministic_json  # noqa: E402


def main() -> int:
    status = 0
    for family, directory in (
        ("random_deletion", ROOT / "results/phase4/random_deletion"),
        ("consecutive_internal_gap", ROOT / "results/phase4/consecutive_gaps"),
    ):
        audit = audit_controlled_family(repository_root=ROOT, family=family)
        write_deterministic_json(
            audit, directory / "erken_phase4_controlled_gap_audit.json"
        )
        print(f"{family}: {audit['audit_status']}")
        if audit["audit_status"] != "PASS":
            status = 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
