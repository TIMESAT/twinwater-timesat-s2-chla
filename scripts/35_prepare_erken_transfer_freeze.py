#!/usr/bin/env python3
"""Materialize the Erken-only second freeze from saved Erken evidence."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.transfer_freeze import write_transfer_freeze_products  # noqa: E402


def main() -> int:
    paths = write_transfer_freeze_products(ROOT)
    print(f"Wrote and hashed {len(paths)} Erken-only transfer-freeze products.")
    print("No reconstruction was rerun and no Vombsjön input or performance was accessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
