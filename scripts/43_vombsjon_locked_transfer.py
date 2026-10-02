#!/usr/bin/env python3
"""Preflight by default. Real transfer requires explicit --run-performance."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from twinwater_timesat.vombsjon_locked_transfer import preflight, run_performance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-performance', action='store_true')
    args = parser.parse_args(argv)
    if args.run_performance:
        result = run_performance(ROOT)
    else:
        result = preflight(ROOT)[0]
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
