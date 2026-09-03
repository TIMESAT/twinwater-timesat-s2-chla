from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.phase3_contract import PRIMARY_YEARS
from twinwater_timesat.seapar_actual import (
    COMPARISON_METHODS,
    CV_METHOD,
    DEFAULT_METHOD,
    load_passed_selection,
)
from twinwater_timesat.timesat_adapter import SubprocessTimesatRunner


ROOT = Path(__file__).resolve().parents[1]


def test_passed_selection_is_complete_and_immutable() -> None:
    manifest, selected = load_passed_selection(ROOT)
    assert manifest["audit_status"] == "PASS"
    assert tuple(sorted(selected)) == PRIMARY_YEARS
    assert selected == {year: 0.0 for year in PRIMARY_YEARS}


def test_sensitivity_method_names_keep_default_and_cv_distinct() -> None:
    assert CV_METHOD == "timesat_double_logistic_cv_seapar"
    assert DEFAULT_METHOD == "timesat_double_logistic_default_seapar1"
    assert len(COMPARISON_METHODS) == 4
    assert len(set(COMPARISON_METHODS)) == 4


def test_original_actual_mask_metrics_still_have_frozen_method_set() -> None:
    metrics = pd.read_csv(
        ROOT
        / "results/phase3/actual_mask/"
        "erken_phase3_actual_mask_year_method_metrics.csv"
    )
    assert set(metrics["method"]) == {
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    }
    assert len(metrics) == 21


@pytest.mark.skipif(
    not os.environ.get("TIMESAT_PYTHON"),
    reason="TIMESAT_PYTHON is not set for selected-DL integration.",
)
def test_subprocess_runner_records_explicit_selected_parameter() -> None:
    dates = pd.date_range("2019-01-01", periods=25, freq="15D")
    sparse = pd.DataFrame(
        {
            "date": dates,
            "CHLF": 2 + 8 * np.exp(-((dates.dayofyear - 210) / 60) ** 2),
        }
    )
    runner = SubprocessTimesatRunner(
        python_executable=os.environ["TIMESAT_PYTHON"],
        runtime_script=ROOT / "scripts/07_timesat_runtime.py",
        snapshot_path=(
            ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
        ),
    )
    result = runner.reconstruct_with_seapar(
        year=2019,
        sparse=sparse,
        target_dates=pd.date_range("2019-01-01", "2019-12-31"),
        p_seapar=0.0,
    )
    assert result.status == "ok"
    assert result.method == CV_METHOD
    assert result.diagnostics["requested_p_seapar"] == 0.0
    assert result.diagnostics["effective_p_seapar"] == 0.0
    assert result.diagnostics["p_seapar_exactly_materialized"] is True
