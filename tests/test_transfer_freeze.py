"""Erken-only transfer-freeze selection, holdout, and correction tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.transfer_freeze import (
    SOURCE_REPORT,
    TransferFreezeError,
    collapse_same_day_observations,
    common_evaluation_dates,
    corrected_reliability_report,
    derive_final_spline_scores,
    enumerate_holdout_scenarios,
    fit_training_affine_scale,
    load_transfer_config,
    synthetic_holdout_audit,
)


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_config_is_complete_and_retains_primary_methods() -> None:
    config = load_transfer_config(ROOT)
    assert config["scope"]["second_freeze_complete"] is True
    assert config["scope"]["vombsjon_data_or_performance_used"] is False
    assert config["reconstruction_methods"]["primary_order"] == [
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    ]
    assert config["reconstruction_methods"]["timesat_smoothing_spline"]["p_smooth"] == 10
    assert (
        config["reconstruction_methods"]["timesat_double_logistic_cv_sensitivity"][
            "analysis_role"
        ]
        == "secondary_sensitivity_not_primary_replacement"
    )


def test_final_spline_uses_seven_year_equal_weight_scores_not_outer_mode() -> None:
    rows = pd.read_csv(
        ROOT / "results/phase3/actual_mask/erken_phase3_spline_candidate_year_nrmse.csv"
    )
    summary, selected = derive_final_spline_scores(rows)
    assert selected == 10
    assert summary["n_years"].eq(7).all()
    assert summary["repetitions_per_candidate_year"].eq(6).all()
    row = summary.set_index("smoothing").loc[10]
    assert row["rank"] == 1
    assert np.isclose(row["mean_equal_year_nrmse"], 0.212145438496667)
    assert row["mean_equal_year_nrmse"] < summary.set_index("smoothing").loc[30, "mean_equal_year_nrmse"]


def test_disagreeing_saved_candidate_repetition_fails() -> None:
    rows = pd.read_csv(
        ROOT / "results/phase3/actual_mask/erken_phase3_spline_candidate_year_nrmse.csv"
    )
    rows.loc[0, "nrmse"] += 0.01
    with pytest.raises(TransferFreezeError, match="repetitions disagree"):
        derive_final_spline_scores(rows)


def test_holdouts_are_exhaustive_internal_and_date_level() -> None:
    dates = pd.date_range("2021-03-01", periods=10, freq="10D")
    observations = pd.DataFrame(
        {"date": dates, "value": np.arange(10, dtype=float), "eligible": True}
    )
    observations = pd.concat(
        [
            observations,
            pd.DataFrame({"date": [dates[4]], "value": [6.0], "eligible": [True]}),
        ],
        ignore_index=True,
    )
    collapsed = collapse_same_day_observations(observations)
    assert len(collapsed) == 10
    assert collapsed.loc[collapsed["date"].eq(dates[4]), "value"].iloc[0] == 5.0
    scenarios = enumerate_holdout_scenarios(observations)
    assert (scenarios["scenario_kind"] == "isolated").sum() == 8
    assert (
        scenarios.loc[scenarios["scenario_kind"].eq("consecutive")]
        .groupby("block_size_observed_dates")
        .size()
        .to_dict()
        == {2: 7, 3: 6, 4: 5}
    )
    assert scenarios["first_date_protected"].all()
    assert scenarios["last_date_protected"].all()
    assert not scenarios["randomly_subsampled"].any()


def test_training_only_scale_is_invertible_and_heldout_mutation_independent() -> None:
    training = np.array([-0.02, -0.01, 0.0, 0.03])
    scale = fit_training_affine_scale(training)
    transformed = scale.transform(training)
    assert np.isclose(transformed.min(), 1000.0)
    assert np.isclose(transformed.max(), 9000.0)
    assert np.allclose(scale.inverse(transformed), training, rtol=0, atol=1e-12)
    heldout_a = np.array([0.01])
    heldout_b = np.array([1000.0])
    assert fit_training_affine_scale(training) == fit_training_affine_scale(training)
    assert not np.array_equal(heldout_a, heldout_b)
    with pytest.raises(TransferFreezeError, match="range must be positive"):
        fit_training_affine_scale([0.1, 0.1])


def test_common_evaluation_dates_require_all_primary_predictions() -> None:
    dates = pd.to_datetime(["2021-06-01", "2021-06-11", "2021-06-21"])
    predictions = {
        "linear_interpolation": pd.DataFrame({"date": dates, "prediction": [1, 2, 3]}),
        "timesat_double_logistic": pd.DataFrame({"date": dates, "prediction": [1, np.nan, 3]}),
        "timesat_smoothing_spline": pd.DataFrame({"date": dates, "prediction": [1, 2, 3]}),
    }
    common = common_evaluation_dates(dates, predictions)
    assert common.tolist() == [dates[0], dates[2]]


def test_synthetic_holdout_audit_passes_every_check() -> None:
    audit = synthetic_holdout_audit()
    assert len(audit) >= 10
    assert audit["passed"].all()


def test_report_correction_is_interpretive_only_and_precise() -> None:
    source = (ROOT / SOURCE_REPORT).read_text(encoding="utf-8")
    corrected, replacements = corrected_reliability_report(source)
    assert len(replacements) == 10
    assert "It reduced noise" not in corrected
    assert corrected.count("some leave-one-year-out summaries tied, and none reversed") == 2
    assert "the contrast took both signs" in corrected
    assert "not a known operational input inside a hidden Vomb gap" in corrected
    assert "不能作为 Vomb 隐藏缺口内已知的运行输入" in corrected
    assert "v1.0 numerical tables, figures, manifest and all frozen analysis outputs are unchanged" in corrected
