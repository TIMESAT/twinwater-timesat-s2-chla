import json

import pytest

from twinwater_timesat.provenance import (
    assert_portable_metadata,
    build_run_metadata,
)


def test_portable_run_metadata_contains_no_user_home_path() -> None:
    metadata = build_run_metadata(
        processing_timestamp_utc="2026-01-01T00:00:00+00:00",
        input_source_filename="erken.csv",
        raw_input_relative_path="data/raw/erken.csv",
        source_sha256="abc123",
        source_size_bytes=10,
        detected_header_line_number=2,
        duplicate_audit={"candidate_copy_count": 3, "byte_identical": True},
        python_version="3.13.0",
        package_versions={"pandas": "3.0.0"},
        git_commit_at_run_time="deadbeef",
        project_config={"phase": 1.1},
        erken_config={"dataset": {"raw_relative_path": "data/raw/erken.csv"}},
        peak_detection_config={"analysis_scope": "open_water"},
    )

    assert "/" + "Users/" not in json.dumps(metadata)
    assert metadata["raw_input_relative_path"] == "data/raw/erken.csv"


def test_portable_metadata_validation_rejects_absolute_user_path() -> None:
    with pytest.raises(ValueError, match="machine-specific"):
        assert_portable_metadata(
            {"bad_path": "/" + "Users/example/Downloads/erken.csv"}
        )
