from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.controlled_benchmark import PersistentTimesatRunner
from twinwater_timesat.phase3_contract import PRIMARY_YEARS
from twinwater_timesat.seapar_selection import (
    S1_IMPLEMENTATION_PATHS,
    _candidate_effectiveness,
    _equal_year_means_match_exactly,
    select_seapar_for_all_outer_folds,
    select_seapar_for_outer_fold,
)
from twinwater_timesat.timesat_adapter import ReconstructionResult


ROOT = Path(__file__).resolve().parents[1]


def test_s1_implementation_bundle_is_explicit_and_erken_only() -> None:
    assert S1_IMPLEMENTATION_PATHS
    assert all((ROOT / path).is_file() for path in S1_IMPLEMENTATION_PATHS)
    assert all("vomb" not in path.lower() for path in S1_IMPLEMENTATION_PATHS)


def _support() -> pd.DataFrame:
    rows = []
    for year in PRIMARY_YEARS:
        for offset, date in enumerate(pd.date_range(f"{year}-06-01", periods=6)):
            rows.append(
                {
                    "date": date,
                    "year": year,
                    "CHLF": float(offset + year - 2018),
                    "open_water": True,
                    "reference_value_available": True,
                    "common_support": True,
                    "common_support_segment_id": f"{year}_segment_1",
                    "s2_openwater_reference_candidate": offset in {0, 5},
                }
            )
    return pd.DataFrame(rows)


class _Runner:
    def __init__(self, *, failed_candidate: float | None = None):
        self.failed_candidate = failed_candidate

    def reconstruct(
        self,
        *,
        method,
        year,
        sparse,
        target_dates,
        smoothing=None,
        p_seapar=None,
    ):
        targets = pd.DatetimeIndex(target_dates)
        failed = p_seapar == self.failed_candidate and year == 2020
        return ReconstructionResult(
            method,
            year,
            "failed" if failed else "ok",
            "synthetic_failure" if failed else "",
            pd.DataFrame(
                {
                    "date": targets,
                    "prediction": np.arange(len(targets), dtype=float),
                }
            ),
            {
                "requested_p_seapar": p_seapar,
                "requested_p_seapar_float64_hex": float(p_seapar).hex(),
                "effective_p_seapar": p_seapar,
                "effective_p_seapar_float64_hex": float(p_seapar).hex(),
                "p_seapar_array_dtype": "float64",
                "p_seapar_exactly_materialized": True,
            },
        )


def test_exact_tie_selects_larger_p_seapar() -> None:
    result = select_seapar_for_outer_fold(
        _support(), outer_test_year=2019, runner=_Runner()
    )
    assert result.status == "ok"
    assert result.selected_p_seapar == 1.0
    assert result.tie_status == "exact_tie_larger_p_seapar_selected"


def test_failure_in_one_training_year_makes_candidate_ineligible() -> None:
    result = select_seapar_for_outer_fold(
        _support(), outer_test_year=2019, runner=_Runner(failed_candidate=0.5)
    )
    row = result.candidate_summary.set_index("candidate_p_seapar").loc[0.5]
    assert row["candidate_status"] == "ineligible"
    assert row["failure_count"] == 1
    assert result.selected_p_seapar == 1.0


def test_held_out_reference_mutation_cannot_change_selection() -> None:
    support = _support()
    baseline = select_seapar_for_outer_fold(
        support, outer_test_year=2025, runner=_Runner()
    )
    mutated = support.copy()
    mutated.loc[mutated["year"].eq(2025), "CHLF"] = 1e12
    changed = select_seapar_for_outer_fold(
        mutated, outer_test_year=2025, runner=_Runner()
    )
    pd.testing.assert_frame_equal(
        baseline.candidate_summary, changed.candidate_summary
    )
    pd.testing.assert_frame_equal(
        baseline.candidate_year_results, changed.candidate_year_results
    )


def test_all_fold_candidate_inventory_is_exact() -> None:
    selection, summary, candidate_years = select_seapar_for_all_outer_folds(
        _support(), runner=_Runner()
    )
    assert len(selection) == 7
    assert len(summary) == 77
    assert len(candidate_years) == 462
    assert candidate_years.groupby(
        ["outer_test_year", "candidate_p_seapar"]
    )["training_year"].nunique().eq(6).all()


def test_equal_year_mean_audit_uses_selection_arithmetic_path() -> None:
    values = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], dtype=np.float64)
    years = pd.DataFrame(
        {
            "outer_test_year": 2019,
            "training_year": [2020, 2021, 2022, 2023, 2024, 2025],
            "candidate_p_seapar": 0.3,
            "nrmse": values,
        }
    )
    summary = pd.DataFrame(
        {
            "outer_test_year": [2019],
            "candidate_p_seapar": [0.3],
            "candidate_status": ["eligible"],
            "mean_equal_year_nrmse": [float(np.mean(values))],
        }
    )
    assert _equal_year_means_match_exactly(years, summary)
    summary.loc[0, "mean_equal_year_nrmse"] = np.nextafter(
        summary.loc[0, "mean_equal_year_nrmse"], np.inf
    )
    assert not _equal_year_means_match_exactly(years, summary)


def test_candidate_effectiveness_requires_real_nrmse_change() -> None:
    base = pd.DataFrame(
        {
            "outer_test_year": [2019, 2019],
            "training_year": [2020, 2020],
            "candidate_p_seapar": [0.0, 1.0],
            "nrmse": [0.2, 0.2],
        }
    )
    assert not _candidate_effectiveness(base)["candidate_parameter_effect_observed"]
    base.loc[1, "nrmse"] = 0.21
    assert _candidate_effectiveness(base)["candidate_parameter_effect_observed"]


@pytest.mark.skipif(
    not os.environ.get("TIMESAT_PYTHON"),
    reason="TIMESAT_PYTHON is not set for persistent p_seapar integration.",
)
def test_persistent_runtime_materializes_selected_parameter() -> None:
    dates = pd.date_range("2019-01-01", periods=25, freq="15D")
    sparse = pd.DataFrame(
        {
            "date": dates,
            "CHLF": 2 + 8 * np.exp(-((dates.dayofyear - 210) / 60) ** 2),
        }
    )
    with PersistentTimesatRunner(
        Path(os.environ["TIMESAT_PYTHON"]),
        ROOT / "scripts/13_timesat_batch_runtime.py",
        ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json",
    ) as runner:
        result = runner.reconstruct(
            method="timesat_double_logistic",
            year=2019,
            sparse=sparse,
            target_dates=pd.date_range("2019-01-01", "2019-12-31"),
            p_seapar=0.3,
        )
    assert result.status == "ok"
    assert result.diagnostics["requested_p_seapar"] == 0.3
    assert result.diagnostics["effective_p_seapar"] == 0.3
    assert result.diagnostics["p_seapar_exactly_materialized"] is True
