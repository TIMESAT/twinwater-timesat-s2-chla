#!/usr/bin/env python3
"""Build the Erken-only Phase S5 sensitivity review packet and stop."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_synthesis import (  # noqa: E402
    SYNTHESIS_DIRECTORY,
    build_seapar_synthesis,
    write_seapar_synthesis,
)


def main() -> int:
    tables, manifest, report = build_seapar_synthesis(repository_root=ROOT)
    paths, audit = write_seapar_synthesis(
        tables, manifest, report, ROOT / SYNTHESIS_DIRECTORY
    )
    print(f"Phase S5 {audit['audit_status']}; wrote {len(paths)} files.")
    print("HARD HUMAN REVIEW GATE reached. Stop before Vombsjön.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
