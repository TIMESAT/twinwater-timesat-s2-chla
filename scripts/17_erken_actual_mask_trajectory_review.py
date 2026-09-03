#!/usr/bin/env python3
"""Create frozen Erken actual-mask trajectory review figures."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.trajectory_review import generate_trajectory_review_package  # noqa: E402


def main() -> int:
    paths, manifest = generate_trajectory_review_package(
        repository_root=ROOT,
        output_directory=ROOT / "results/phase4/review/trajectories",
    )
    print(f"Wrote {len(paths)} review artifacts ({manifest['figure_count']} figures).")
    print("Frozen benchmark outputs modified: False; reconstruction rerun: False.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
