#!/usr/bin/env python3
"""Generate the versioned Erken reliability synthesis from saved results."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.reliability_synthesis import write_reliability_products  # noqa: E402


def main() -> int:
    paths = write_reliability_products(repository_root=ROOT)
    print(f"Wrote {len(paths)} Erken reliability-synthesis products.")
    print("Saved-result derivation only; no reconstruction, satellite extraction, Vomb inspection, or second freeze.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
