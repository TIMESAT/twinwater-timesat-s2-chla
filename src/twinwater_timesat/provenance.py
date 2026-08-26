"""Portable reproducibility metadata for public Phase 1.1 outputs."""

from __future__ import annotations

import json
from typing import Any, Mapping


PROHIBITED_PATH_MARKERS = (
    "/" + "Users/",
    "/" + "home/",
    "\\" + "Users\\",
)


def assert_portable_metadata(metadata: Mapping[str, Any]) -> None:
    """Fail if serialized public metadata contains a common absolute home path."""

    serialized = json.dumps(metadata, ensure_ascii=False)
    detected = [marker for marker in PROHIBITED_PATH_MARKERS if marker in serialized]
    if detected:
        raise ValueError(
            "Run metadata contains machine-specific absolute path marker(s): "
            f"{detected}."
        )


def build_run_metadata(
    *,
    processing_timestamp_utc: str,
    input_source_filename: str,
    raw_input_relative_path: str,
    source_sha256: str,
    source_size_bytes: int,
    detected_header_line_number: int,
    duplicate_audit: Mapping[str, Any],
    python_version: str,
    package_versions: Mapping[str, str],
    git_commit_at_run_time: str | None,
    project_config: Mapping[str, Any],
    erken_config: Mapping[str, Any],
    peak_detection_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build public, repository-portable run metadata and validate it."""

    metadata: dict[str, Any] = {
        "processing_timestamp_utc": processing_timestamp_utc,
        "input_source_filename": input_source_filename,
        "raw_input_relative_path": raw_input_relative_path,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size_bytes,
        "detected_header_line_number": detected_header_line_number,
        "duplicate_source_audit": dict(duplicate_audit),
        "python_version": python_version,
        "package_versions": dict(package_versions),
        "git_commit_at_run_time": git_commit_at_run_time,
        "project_config": dict(project_config),
        "erken_config": dict(erken_config),
        "peak_detection_config": dict(peak_detection_config),
    }
    assert_portable_metadata(metadata)
    return metadata
