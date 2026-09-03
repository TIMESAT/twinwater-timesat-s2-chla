#!/usr/bin/env python3
"""Generate Erken-only Phase D descriptive synthesis products."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.erken_synthesis import build_synthesis_products, write_synthesis_products  # noqa: E402


def main() -> int:
    tables, manifest, report = build_synthesis_products(repository_root=ROOT)
    paths = write_synthesis_products(
        tables, manifest, report, ROOT / "results/phase4/synthesis"
    )
    print(f"Wrote {len(paths)} Erken-only Phase D products.")
    print("No final model, method winner, universal threshold, or Vomb inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
