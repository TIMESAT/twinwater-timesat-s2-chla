from __future__ import annotations

import numpy as np
import pandas as pd

from twinwater_timesat.reconstruction_metrics import (
    evaluate_pointwise_metrics,
    evaluate_seasonal_metrics,
    global_peak,
)


def support_table(
    dates: list[str],
    reference: list[float],
    *,
    sparse_indices: set[int] | None = None,
    segment_ids: list[str] | None = None,
) -> pd.DataFrame:
    parsed = pd.to_datetime(dates)
    sparse_indices = sparse_indices or set()
    if segment_ids is None:
        segment_ids = ["segment_1"] * len(dates)
    return pd.DataFrame(
        {
            "date": parsed,
            "year": parsed.year,
            "CHLF": reference,
            "open_water": True,
            "reference_value_available": True,
            "common_support": True,
            "common_support_segment_id": segment_ids,
            "s2_openwater_reference_candidate": [
                index in sparse_indices for index in range(len(dates))
            ],
        }
    )


def prediction(dates: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates), "prediction": values})


def test_pointwise_metrics_exclude_sparse_input_dates() -> None:
    dates = [f"2020-01-0{day}" for day in range(1, 6)]
    support = support_table(dates, [1, 2, 3, 4, 5], sparse_indices={0, 4})
    metrics, residuals = evaluate_pointwise_metrics(
        support, prediction(dates, [1, 2.5, 2.5, 4.5, 5])
    )
    assert residuals["date"].dt.day.tolist() == [2, 3, 4]
    assert metrics["n_pointwise_evaluation_dates"] == 3
    assert metrics["bias"] == np.mean([0.5, -0.5, 0.5])
    assert metrics["pointwise_metric_status"] == "ok"


def test_missing_prediction_is_not_silently_dropped() -> None:
    dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
    support = support_table(dates, [1, 2, 3], sparse_indices={0})
    metrics, residuals = evaluate_pointwise_metrics(
        support, prediction(dates[:2], [1, 2])
    )
    assert metrics["pointwise_metric_status"] == "unavailable"
    assert metrics["pointwise_metric_reason"] == "incomplete_prediction_support"
    assert metrics["n_predictions_missing_or_nonfinite"] == 1
    assert len(residuals) == 2
    assert residuals["residual_status"].tolist()[-1] == "missing_or_nonfinite_prediction"


def test_invalid_reference_scale_has_no_epsilon_stabilization() -> None:
    dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
    support = support_table(dates, [2, 2, 2], sparse_indices={0})
    metrics, _ = evaluate_pointwise_metrics(
        support, prediction(dates, [2, 2.5, 1.5])
    )
    assert metrics["rmse"] > 0
    assert np.isnan(metrics["nrmse"])
    assert metrics["nrmse_status"] == "unavailable"
    assert metrics["scale_unavailable_reason"] == "q95_minus_q05_not_positive_finite"


def test_contiguous_equal_maximum_plateau_uses_temporal_midpoint() -> None:
    result = global_peak(
        pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])),
        pd.Series([1.0, 5.0, 5.0]),
    )
    assert result.status == "ok"
    assert result.peak_time == pd.Timestamp("2020-01-02 12:00:00")
    assert result.plateau_days == 2
    assert result.boundary_peak is True


def test_noncontiguous_exact_equal_maxima_are_ambiguous() -> None:
    result = global_peak(
        pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])),
        pd.Series([5.0, 1.0, 5.0]),
    )
    assert result.status == "unavailable"
    assert result.reason == "ambiguous_equal_global_maxima"
    assert result.peak_time is None


def test_integral_does_not_bridge_disconnected_open_water_segments() -> None:
    dates = ["2020-01-01", "2020-01-02", "2020-01-05", "2020-01-06"]
    support = support_table(
        dates,
        [1, 1, 10, 10],
        sparse_indices={0, 3},
        segment_ids=["segment_1", "segment_1", "segment_2", "segment_2"],
    )
    metrics = evaluate_seasonal_metrics(
        support, prediction(dates, [1, 1, 10, 10])
    )
    assert metrics["reference_integral"] == 11
    assert metrics["reconstruction_integral"] == 11
    assert metrics["signed_integral_error"] == 0


def test_negative_reconstruction_values_are_recorded_not_clipped() -> None:
    dates = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]
    support = support_table(dates, [1, 2, 3, 4], sparse_indices={0, 3})
    metrics = evaluate_seasonal_metrics(
        support, prediction(dates, [-1, 2, 3, 4])
    )
    assert metrics["minimum_reconstructed_value"] == -1
    assert metrics["n_negative_reconstructed_days"] == 1
    assert metrics["fraction_negative_reconstructed_days"] == 0.25
    assert metrics["negative_values_clipped"] is False


def test_peak_reliability_uses_only_frozen_5_10_15_day_thresholds() -> None:
    dates = pd.date_range("2020-01-01", periods=20).strftime("%Y-%m-%d").tolist()
    reference = [1.0] * 20
    reconstructed = [1.0] * 20
    reference[4] = 10
    reconstructed[11] = 10
    support = support_table(dates, reference, sparse_indices={0, 19})
    metrics = evaluate_seasonal_metrics(support, prediction(dates, reconstructed))
    assert metrics["absolute_peak_date_error_days"] == 7
    assert metrics["peak_timing_success_5d"] is False
    assert metrics["peak_timing_success_10d"] is True
    assert metrics["peak_timing_success_15d"] is True
