from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from twinwater_timesat.event_benchmark import (
    EventBenchmarkGuardError,
    _require_clean_descendant,
    _year_method_summary,
)
from twinwater_timesat.seasonal_events import match_reference_events


ROOT = Path(__file__).resolve().parents[1]


def _matched_and_missed() -> pd.DataFrame:
    references = pd.DataFrame(
        [
            {
                "event_id": "ERK_2020_E01",
                "year": 2020,
                "event_time": pd.Timestamp("2020-01-10"),
                "common_support_segment_id": "s1",
                "reference_magnitude": 10.0,
                "yearly_scale_q95_minus_q05": 10.0,
            },
            {
                "event_id": "ERK_2020_E02",
                "year": 2020,
                "event_time": pd.Timestamp("2020-02-10"),
                "common_support_segment_id": "s1",
                "reference_magnitude": 20.0,
                "yearly_scale_q95_minus_q05": 10.0,
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "REC_2020_P001",
                "year": 2020,
                "event_time": pd.Timestamp("2020-01-15"),
                "common_support_segment_id": "s1",
                "reconstructed_magnitude": 15.0,
            }
        ]
    )
    result = match_reference_events(references, candidates)
    result.insert(2, "method", "linear_interpolation")
    result["reconstruction_status"] = "ok"
    return result


def test_year_method_summary_respects_available_event_denominator() -> None:
    summary = _year_method_summary(_matched_and_missed()).iloc[0]
    assert summary["n_reference_events"] == 2
    assert summary["n_matched_events"] == 1
    assert summary["n_missed_events"] == 1
    assert summary["n_unavailable_events"] == 0
    assert summary["recovery_fraction_5d"] == 0.5
    assert summary["recovery_fraction_10d"] == 0.5
    assert summary["recovery_fraction_15d"] == 0.5
    assert summary["mean_absolute_timing_error_matched_days"] == 5.0


def test_performance_guard_refuses_dirty_worktree(monkeypatch) -> None:
    monkeypatch.setattr(
        "twinwater_timesat.event_benchmark._git",
        lambda root, *args: " M tracked.py",
    )
    with pytest.raises(EventBenchmarkGuardError, match="worktree is dirty"):
        _require_clean_descendant(ROOT)


def test_event_actual_mask_cli_requires_explicit_authorization() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/11_erken_phase3_event_actual_mask.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "Refusing event performance" in completed.stderr
