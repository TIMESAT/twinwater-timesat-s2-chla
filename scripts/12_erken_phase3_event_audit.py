#!/usr/bin/env python3
"""Independent mechanical audit of Phase A seasonal-event outputs."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.event_benchmark import audit_actual_mask_event_products  # noqa: E402
from twinwater_timesat.phase3_preflight import write_deterministic_json  # noqa: E402


def main() -> int:
    output = ROOT / "results/phase3/event_actual_mask"
    audit = audit_actual_mask_event_products(
        repository_root=ROOT, output_directory=output
    )
    write_deterministic_json(audit, output / "erken_phase3_actual_mask_event_audit.json")
    print(f"Phase B audit: {audit['audit_status']}")
    return 0 if audit["audit_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
