#!/usr/bin/env python3
"""Generate review-only Phase 5 p_seapar comparison figures."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.seapar_review import generate_phase5_review_package  # noqa: E402


def main() -> int:
    paths, manifest = generate_phase5_review_package(
        repository_root=ROOT,
        output_directory=ROOT / "results/phase5/review/trajectories",
    )
    print(f"Wrote {len(paths)} artifacts ({manifest['figure_count']} figures).")
    print("Old methods rerun: False; benchmark outputs modified: False.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
