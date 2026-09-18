#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.vombsjon_field_audit import validate_written_audit


if __name__ == "__main__":
    manifest = validate_written_audit(ROOT)
    core = manifest["core_audit"]
    print("Vomb field-input audit: PASS")
    print(
        f"Verified {core['row_count']} field observations, "
        f"{core['metadata_records']} XLSX metadata dates, four source checksums, "
        "and all versioned audit outputs."
    )
