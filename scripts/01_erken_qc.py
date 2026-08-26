#!/usr/bin/env python3
"""Ingest the raw Erken CSV, preserve daily values, and write QC outputs."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.io import read_erken_csv, write_clean_csv  # noqa: E402
from twinwater_timesat.provenance import build_run_metadata  # noqa: E402
from twinwater_timesat.qc import (  # noqa: E402
    build_qc_summary,
    render_qc_report,
    sha256_file,
)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def git_commit() -> str | None:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return process.stdout.strip() if process.returncode == 0 else None


def package_versions() -> dict[str, str]:
    distributions = {
        "pandas": "pandas",
        "numpy": "numpy",
        "scipy": "scipy",
        "matplotlib": "matplotlib",
        "pyyaml": "PyYAML",
        "pytest": "pytest",
    }
    versions: dict[str, str] = {}
    for label, distribution in distributions.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = "not installed"
    return versions


def main() -> None:
    erkennen = load_yaml(ROOT / "config" / "erken.yaml")
    project = load_yaml(ROOT / "config" / "project.yaml")
    dataset_config = erkennen["dataset"]
    outputs = erkennen["outputs"]
    raw_path = ROOT / dataset_config["raw_relative_path"]
    copied_hash = sha256_file(raw_path)
    if copied_hash != dataset_config["expected_sha256"]:
        raise RuntimeError(
            f"Raw-file SHA256 mismatch: expected {dataset_config['expected_sha256']}, got {copied_hash}."
        )

    ingestion = read_erken_csv(raw_path)
    clean_path = ROOT / outputs["clean_daily"]
    write_clean_csv(ingestion.data, clean_path)

    qc = build_qc_summary(
        ingestion.data,
        raw_input_relative_path=dataset_config["raw_relative_path"],
        source_sha256=copied_hash,
        header_line_number=ingestion.header_line_number,
        duplicate_candidate_count=dataset_config["duplicate_source_audit"][
            "candidate_copy_count"
        ],
        duplicate_candidates_byte_identical=dataset_config[
            "duplicate_source_audit"
        ]["byte_identical"],
    )
    qc_path = ROOT / outputs["qc_summary"]
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    qc.to_csv(qc_path, index=False)
    report = render_qc_report(ingestion.data, qc)
    report_path = ROOT / outputs["qc_report"]
    report_path.write_text(report, encoding="utf-8")

    peak_config = load_yaml(ROOT / "config" / "peak_detection_exploratory.yaml")
    metadata = build_run_metadata(
        processing_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        input_source_filename=dataset_config["raw_filename"],
        raw_input_relative_path=dataset_config["raw_relative_path"],
        source_sha256=copied_hash,
        source_size_bytes=raw_path.stat().st_size,
        detected_header_line_number=ingestion.header_line_number,
        duplicate_audit=dataset_config["duplicate_source_audit"],
        python_version=platform.python_version(),
        package_versions=package_versions(),
        git_commit_at_run_time=git_commit(),
        project_config=project,
        erken_config=erkennen,
        peak_detection_config=peak_config,
    )
    metadata_path = ROOT / outputs["run_metadata"]
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Wrote {clean_path.relative_to(ROOT)} ({len(ingestion.data)} rows)")
    print(f"Wrote {qc_path.relative_to(ROOT)}")
    print(f"Wrote {report_path.relative_to(ROOT)}")
    print(f"Wrote {metadata_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
