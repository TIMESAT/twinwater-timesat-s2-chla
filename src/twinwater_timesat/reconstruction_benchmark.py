"""Phase 3 method dispatch and explicit per-year evaluation products."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.reconstruction_metrics import (
    evaluate_pointwise_metrics,
    evaluate_seasonal_metrics,
)
from twinwater_timesat.timesat_adapter import (
    ReconstructionResult,
    SubprocessTimesatRunner,
    linear_reconstruct,
)


def sparse_input_checksum(sparse: pd.DataFrame) -> str:
    """Hash ordered sparse dates and float64 values for cross-method identity."""

    ordered = sparse[["date", "CHLF"]].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    ordered["CHLF"] = pd.to_numeric(ordered["CHLF"], errors="raise").astype(float)
    ordered = ordered.sort_values("date")
    payload = [
        {"date": row.date, "CHLF_float64_hex": float(row.CHLF).hex()}
        for row in ordered.itertuples(index=False)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def reconstruct_all_methods_for_year(
    year_support: pd.DataFrame,
    *,
    selected_smoothing: int | None,
    timesat_runner: SubprocessTimesatRunner,
) -> dict[str, ReconstructionResult]:
    """Give all three methods an identical frozen sparse series and support."""

    years = year_support["year"].unique()
    if len(years) != 1:
        raise ValueError("Exactly one year is required for method dispatch.")
    year = int(years[0])
    sparse = year_support.loc[
        year_support["s2_openwater_reference_candidate"], ["date", "CHLF"]
    ].copy()
    target_dates = year_support.loc[year_support["common_support"], "date"].copy()
    checksum = sparse_input_checksum(sparse)
    results: dict[str, ReconstructionResult] = {
        "linear_interpolation": linear_reconstruct(
            year=year, sparse=sparse.copy(), target_dates=target_dates
        ),
        "timesat_double_logistic": timesat_runner.reconstruct(
            method="timesat_double_logistic",
            year=year,
            sparse=sparse.copy(),
            target_dates=target_dates,
        ),
    }
    if selected_smoothing is None:
        results["timesat_smoothing_spline"] = ReconstructionResult(
            method="timesat_smoothing_spline",
            year=year,
            status="failed",
            failure_reason="outer_fold_spline_selection_failed",
            prediction=pd.DataFrame(
                {"date": pd.to_datetime(target_dates), "prediction": np.nan}
            ),
            diagnostics={"selected_smoothing": None},
        )
    else:
        results["timesat_smoothing_spline"] = timesat_runner.reconstruct(
            method="timesat_smoothing_spline",
            year=year,
            sparse=sparse.copy(),
            target_dates=target_dates,
            smoothing=selected_smoothing,
        )
    output: dict[str, ReconstructionResult] = {}
    for method, result in results.items():
        diagnostics = dict(result.diagnostics)
        diagnostics["sparse_input_checksum"] = checksum
        diagnostics["identical_sparse_input_enforced"] = True
        output[method] = ReconstructionResult(
            result.method,
            result.year,
            result.status,
            result.failure_reason,
            result.prediction,
            diagnostics,
        )
    if len({item.diagnostics["sparse_input_checksum"] for item in output.values()}) != 1:
        raise AssertionError("Methods did not receive identical sparse inputs.")
    return output


def evaluate_method_result(
    year_support: pd.DataFrame,
    reconstruction: ReconstructionResult,
    *,
    provenance: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Evaluate an explicit success/failure without silently dropping failures."""

    base: dict[str, Any] = {
        "year": reconstruction.year,
        "method": reconstruction.method,
        "reconstruction_status": reconstruction.status,
        "reconstruction_failure_reason": reconstruction.failure_reason,
        **dict(provenance or {}),
    }
    for key, value in reconstruction.diagnostics.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            base[f"diagnostic_{key}"] = value
    if reconstruction.status != "ok":
        base.update(
            {
                "pointwise_metric_status": "unavailable",
                "pointwise_metric_reason": "reconstruction_failed",
                "seasonal_metric_status": "unavailable",
                "seasonal_metric_reason": "reconstruction_failed",
            }
        )
        residual_dates = year_support.loc[
            year_support["common_support"]
            & year_support["reference_value_available"]
            & ~year_support["s2_openwater_reference_candidate"],
            ["date", "year", "CHLF"],
        ].copy()
        residual_dates["prediction"] = np.nan
        residual_dates["prediction_available"] = False
        residual_dates["residual"] = np.nan
        residual_dates["absolute_error"] = np.nan
        residual_dates["squared_error"] = np.nan
        residual_dates["residual_status"] = "reconstruction_failed"
        residual_dates["method"] = reconstruction.method
        return base, residual_dates

    pointwise, residuals = evaluate_pointwise_metrics(
        year_support, reconstruction.prediction
    )
    seasonal = evaluate_seasonal_metrics(year_support, reconstruction.prediction)
    base.update(pointwise)
    base.update(seasonal)
    residuals["method"] = reconstruction.method
    return base, residuals
