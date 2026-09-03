#!/usr/bin/env python3
"""Independent saved-output audits for both Phase S4 families."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.phase3_preflight import write_deterministic_json  # noqa: E402
from twinwater_timesat.seapar_controlled import (  # noqa: E402
    CONTROLLED_ROOT,
    FAMILY_SPECS,
    audit_saved_seapar_controlled_family,
)


def main() -> int:
    status = 0
    for family, spec in FAMILY_SPECS.items():
        audit = audit_saved_seapar_controlled_family(
            repository_root=ROOT, family=family
        )
        output = ROOT / CONTROLLED_ROOT / spec["output_directory"]
        write_deterministic_json(
            audit, output / "erken_phase5_seapar_controlled_gap_audit.json"
        )
        print(f"Phase S4 {family}: {audit['audit_status']}")
        if audit["audit_status"] != "PASS":
            status = 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
