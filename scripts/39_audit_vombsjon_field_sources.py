#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.vombsjon_field_audit import write_audit_outputs


if __name__ == "__main__":
    outputs = write_audit_outputs(ROOT)
    print("Vomb field-input audit outputs written:")
    for output in outputs.values():
        print(output.relative_to(ROOT))
