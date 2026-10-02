#!/usr/bin/env python3
"""Validate saved locked-transfer outputs without reconstructing observations."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from twinwater_timesat.vombsjon_locked_transfer import preflight, validate_outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', help='Check inputs and synthetic runtime only; no performance outputs required.')
    args = parser.parse_args(argv)
    result = preflight(ROOT)[0] if args.preflight else validate_outputs(ROOT)
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
