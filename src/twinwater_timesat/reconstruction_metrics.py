"""Method-independent Phase 3 reconstruction metrics and failure flags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from twinwater_timesat.reconstruction_support import pointwise_evaluation_mask


@dataclass(frozen=True)
class PeakResult:
    """A common-support global-maximum result."""

    status: str
    reason: str
    peak_time: pd.Timestamp | None
    peak_value: float | None
    plateau_start: pd.Timestamp | None
    plateau_end: pd.Timestamp | None
    plateau_days: int | None
    boundary_peak: bool | None
    distance_to_nearest_boundary_days: float | None


def robust_reference_scale(values: pd.Series) -> dict[str, Any]:
    """Compute the frozen Q95-Q05 scale with explicit validity."""

    array = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {
            "q05": np.nan,
            "q95": np.nan,
            "scale": np.nan,
            "scale_available": False,
            "scale_unavailable_reason": "no_finite_common_support_reference",
        }
    q05, q95 = np.quantile(array, [0.05, 0.95], method="linear")
    scale = float(q95 - q05)
    valid = bool(np.isfinite(scale) and scale > 0)
    return {
        "q05": float(q05),
        "q95": float(q95),
        "scale": scale,
        "scale_available": valid,
        "scale_unavailable_reason": "" if valid else "q95_minus_q05_not_positive_finite",
    }


def _prediction_series(prediction: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(prediction, pd.Series):
        result = prediction.copy()
        if not isinstance(result.index, pd.DatetimeIndex):
            raise ValueError("Prediction Series must use a DatetimeIndex.")
        result.index = result.index.normalize()
    else:
        required = {"date", "prediction"}
        missing = sorted(required - set(prediction.columns))
        if missing:
            raise ValueError(f"Prediction table lacks columns: {missing}")
        dates = pd.to_datetime(prediction["date"], errors="coerce")
        if dates.isna().any():
            raise ValueError("Prediction table contains invalid dates.")
        result = pd.Series(
            pd.to_numeric(prediction["prediction"], errors="coerce").to_numpy(),
            index=dates.dt.normalize(),
            name="prediction",
        )
    if result.index.duplicated().any():
        raise ValueError("Prediction dates must be unique.")
    return result.sort_index()


def evaluate_pointwise_metrics(
    year_support: pd.DataFrame,
    prediction: pd.DataFrame | pd.Series,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Evaluate only genuinely withheld dates; never drop missing predictions."""

    eligible = year_support.loc[pointwise_evaluation_mask(year_support)].copy()
    pred = _prediction_series(prediction)
    eligible["prediction"] = eligible["date"].map(pred)
    eligible["prediction_available"] = eligible["prediction"].notna() & np.isfinite(
        eligible["prediction"].to_numpy(dtype=float)
    )
    eligible["residual"] = eligible["prediction"] - eligible["CHLF"]
    eligible["absolute_error"] = eligible["residual"].abs()
    eligible["squared_error"] = eligible["residual"] ** 2
    eligible["residual_status"] = np.where(
        eligible["prediction_available"], "ok", "missing_or_nonfinite_prediction"
    )

    reference_domain = year_support.loc[
        year_support["common_support"] & year_support["reference_value_available"],
        "CHLF",
    ]
    scale = robust_reference_scale(reference_domain)
    missing_count = int((~eligible["prediction_available"]).sum())
    summary: dict[str, Any] = {
        "n_pointwise_evaluation_dates": int(len(eligible)),
        "n_predictions_available": int(eligible["prediction_available"].sum()),
        "n_predictions_missing_or_nonfinite": missing_count,
        "q05_reference": scale["q05"],
        "q95_reference": scale["q95"],
        "q95_minus_q05": scale["scale"],
        "scale_available": scale["scale_available"],
        "scale_unavailable_reason": scale["scale_unavailable_reason"],
    }
    if eligible.empty:
        summary.update(
            {
                "pointwise_metric_status": "unavailable",
                "pointwise_metric_reason": "no_eligible_withheld_dates",
                "bias": np.nan,
                "mae": np.nan,
                "rmse": np.nan,
                "nrmse": np.nan,
                "nrmse_status": "unavailable",
                "nrmse_reason": "no_eligible_withheld_dates",
            }
        )
    elif missing_count:
        summary.update(
            {
                "pointwise_metric_status": "unavailable",
                "pointwise_metric_reason": "incomplete_prediction_support",
                "bias": np.nan,
                "mae": np.nan,
                "rmse": np.nan,
                "nrmse": np.nan,
                "nrmse_status": "unavailable",
                "nrmse_reason": "incomplete_prediction_support",
            }
        )
    else:
        residual = eligible["residual"].to_numpy(dtype=float)
        rmse = float(np.sqrt(np.mean(residual**2)))
        nrmse = rmse / scale["scale"] if scale["scale_available"] else np.nan
        summary.update(
            {
                "pointwise_metric_status": "ok",
                "pointwise_metric_reason": "",
                "bias": float(np.mean(residual)),
                "mae": float(np.mean(np.abs(residual))),
                "rmse": rmse,
                "nrmse": float(nrmse) if np.isfinite(nrmse) else np.nan,
                "nrmse_status": "ok" if scale["scale_available"] else "unavailable",
                "nrmse_reason": scale["scale_unavailable_reason"],
            }
        )
    residual_columns = [
        "date",
        "year",
        "CHLF",
        "prediction",
        "prediction_available",
        "residual",
        "absolute_error",
        "squared_error",
        "residual_status",
    ]
    return summary, eligible[residual_columns].reset_index(drop=True)


def global_peak(dates: pd.Series, values: pd.Series) -> PeakResult:
    """Resolve the frozen global-maximum plateau and ambiguity rules."""

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates).dt.normalize(),
            "value": pd.to_numeric(values, errors="coerce"),
        }
    ).sort_values("date")
    if frame.empty:
        return PeakResult(
            "unavailable", "empty_common_support", None, None, None, None, None, None, None
        )
    if frame["date"].duplicated().any():
        raise ValueError("Peak input dates must be unique.")
    finite = np.isfinite(frame["value"].to_numpy(dtype=float))
    if not finite.all():
        return PeakResult(
            "unavailable",
            "missing_or_nonfinite_common_support_values",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    maximum = float(frame["value"].max())
    maxima = frame.loc[frame["value"].eq(maximum), "date"].reset_index(drop=True)
    groups = maxima.diff().dt.days.ne(1).cumsum()
    if groups.nunique() > 1:
        return PeakResult(
            "unavailable",
            "ambiguous_equal_global_maxima",
            None,
            maximum,
            None,
            None,
            None,
            None,
            None,
        )
    plateau_start = maxima.iloc[0]
    plateau_end = maxima.iloc[-1]
    midpoint = plateau_start + (plateau_end - plateau_start) / 2
    support_start = frame["date"].iloc[0]
    support_end = frame["date"].iloc[-1]
    boundary = bool(plateau_start == support_start or plateau_end == support_end)
    boundary_distance = min(
        (midpoint - support_start).total_seconds() / 86400,
        (support_end - midpoint).total_seconds() / 86400,
    )
    return PeakResult(
        "ok",
        "",
        midpoint,
        maximum,
        plateau_start,
        plateau_end,
        int((plateau_end - plateau_start).days + 1),
        boundary,
        float(boundary_distance),
    )


def _integral_by_segments(frame: pd.DataFrame, value_column: str) -> float:
    total = 0.0
    for _, segment in frame.groupby("common_support_segment_id", sort=False):
        ordered = segment.sort_values("date")
        values = ordered[value_column].to_numpy(dtype=float)
        dates = ordered["date"].to_numpy(dtype="datetime64[ns]")
        if len(values) <= 1:
            continue
        elapsed = np.diff(dates).astype("timedelta64[s]").astype(float) / 86400.0
        total += float(np.sum((values[:-1] + values[1:]) * 0.5 * elapsed))
    return total


def _peak_fields(prefix: str, result: PeakResult) -> dict[str, Any]:
    return {
        f"{prefix}_peak_status": result.status,
        f"{prefix}_peak_reason": result.reason,
        f"{prefix}_peak_time": result.peak_time,
        f"{prefix}_peak_value": result.peak_value,
        f"{prefix}_peak_plateau_start": result.plateau_start,
        f"{prefix}_peak_plateau_end": result.plateau_end,
        f"{prefix}_peak_plateau_days": result.plateau_days,
        f"{prefix}_peak_at_boundary": result.boundary_peak,
        f"{prefix}_peak_distance_to_nearest_boundary_days": (
            result.distance_to_nearest_boundary_days
        ),
    }


def evaluate_seasonal_metrics(
    year_support: pd.DataFrame,
    prediction: pd.DataFrame | pd.Series,
) -> dict[str, Any]:
    """Apply identical external seasonal definitions over identical support."""

    support = year_support.loc[
        year_support["common_support"] & year_support["reference_value_available"]
    ].copy()
    pred = _prediction_series(prediction)
    support["prediction"] = support["date"].map(pred)
    prediction_finite = support["prediction"].notna() & np.isfinite(
        support["prediction"].to_numpy(dtype=float)
    )
    scale = robust_reference_scale(support["CHLF"])
    result: dict[str, Any] = {
        "n_common_support_dates": int(len(support)),
        "n_common_support_predictions": int(prediction_finite.sum()),
        "n_missing_common_support_predictions": int((~prediction_finite).sum()),
        "q95_minus_q05": scale["scale"],
        "scale_available": scale["scale_available"],
        "scale_unavailable_reason": scale["scale_unavailable_reason"],
    }
    present = support.loc[prediction_finite, "prediction"].to_numpy(dtype=float)
    result.update(
        {
            "minimum_reconstructed_value": float(np.min(present)) if present.size else np.nan,
            "n_negative_reconstructed_days": int((present < 0).sum()),
            "fraction_negative_reconstructed_days": (
                float((present < 0).mean()) if present.size else np.nan
            ),
            "negative_values_clipped": False,
        }
    )
    reference_peak = global_peak(support["date"], support["CHLF"])
    result.update(_peak_fields("reference", reference_peak))
    if support.empty or not prediction_finite.all():
        reconstruction_peak = PeakResult(
            "unavailable",
            "incomplete_prediction_support",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        result.update(_peak_fields("reconstruction", reconstruction_peak))
        result.update(
            {
                "seasonal_metric_status": "unavailable",
                "seasonal_metric_reason": "incomplete_prediction_support",
                "peak_timing_metric_status": "unavailable",
                "peak_timing_metric_reason": "incomplete_prediction_support",
                "signed_peak_date_error_days": np.nan,
                "absolute_peak_date_error_days": np.nan,
                "peak_timing_success_5d": pd.NA,
                "peak_timing_success_10d": pd.NA,
                "peak_timing_success_15d": pd.NA,
                "signed_peak_magnitude_error": np.nan,
                "absolute_peak_magnitude_error": np.nan,
                "normalized_absolute_peak_magnitude_error": np.nan,
                "reference_integral": np.nan,
                "reconstruction_integral": np.nan,
                "signed_integral_error": np.nan,
                "absolute_integral_error": np.nan,
                "relative_integral_error": np.nan,
                "relative_integral_status": "unavailable",
                "relative_integral_reason": "incomplete_prediction_support",
                "pearson_correlation": np.nan,
                "correlation_status": "unavailable",
                "correlation_reason": "incomplete_prediction_support",
            }
        )
        return result

    reconstruction_peak = global_peak(support["date"], support["prediction"])
    result.update(_peak_fields("reconstruction", reconstruction_peak))
    if reference_peak.status == "ok" and reconstruction_peak.status == "ok":
        signed_days = (
            reconstruction_peak.peak_time - reference_peak.peak_time
        ).total_seconds() / 86400
        absolute_days = abs(signed_days)
        magnitude_error = reconstruction_peak.peak_value - reference_peak.peak_value
        normalized_magnitude = (
            abs(magnitude_error) / scale["scale"]
            if scale["scale_available"]
            else np.nan
        )
    else:
        signed_days = absolute_days = magnitude_error = normalized_magnitude = np.nan
    if reference_peak.status != "ok":
        peak_timing_status = "unavailable"
        peak_timing_reason = reference_peak.reason
    elif reference_peak.boundary_peak:
        peak_timing_status = "unavailable"
        peak_timing_reason = "reference_peak_at_boundary"
    elif reconstruction_peak.status != "ok":
        peak_timing_status = "unavailable"
        peak_timing_reason = reconstruction_peak.reason
    else:
        peak_timing_status = "ok"
        peak_timing_reason = ""
    reference_integral = _integral_by_segments(support, "CHLF")
    reconstruction_integral = _integral_by_segments(support, "prediction")
    integral_error = reconstruction_integral - reference_integral
    relative_ok = bool(np.isfinite(reference_integral) and reference_integral != 0)

    reference_values = support["CHLF"].to_numpy(dtype=float)
    reconstruction_values = support["prediction"].to_numpy(dtype=float)
    correlation_ok = bool(
        len(support) >= 2
        and np.std(reference_values) > 0
        and np.std(reconstruction_values) > 0
    )
    correlation = (
        float(np.corrcoef(reference_values, reconstruction_values)[0, 1])
        if correlation_ok
        else np.nan
    )
    result.update(
        {
            "seasonal_metric_status": "ok",
            "seasonal_metric_reason": "",
            "peak_timing_metric_status": peak_timing_status,
            "peak_timing_metric_reason": peak_timing_reason,
            "signed_peak_date_error_days": float(signed_days) if np.isfinite(signed_days) else np.nan,
            "absolute_peak_date_error_days": float(absolute_days) if np.isfinite(absolute_days) else np.nan,
            "peak_timing_success_5d": (
                bool(absolute_days <= 5) if peak_timing_status == "ok" else pd.NA
            ),
            "peak_timing_success_10d": (
                bool(absolute_days <= 10) if peak_timing_status == "ok" else pd.NA
            ),
            "peak_timing_success_15d": (
                bool(absolute_days <= 15) if peak_timing_status == "ok" else pd.NA
            ),
            "signed_peak_magnitude_error": float(magnitude_error) if np.isfinite(magnitude_error) else np.nan,
            "absolute_peak_magnitude_error": float(abs(magnitude_error)) if np.isfinite(magnitude_error) else np.nan,
            "normalized_absolute_peak_magnitude_error": (
                float(normalized_magnitude) if np.isfinite(normalized_magnitude) else np.nan
            ),
            "reference_integral": reference_integral,
            "reconstruction_integral": reconstruction_integral,
            "signed_integral_error": integral_error,
            "absolute_integral_error": abs(integral_error),
            "relative_integral_error": (
                float(integral_error / reference_integral) if relative_ok else np.nan
            ),
            "relative_integral_status": "ok" if relative_ok else "unavailable",
            "relative_integral_reason": "" if relative_ok else "reference_integral_zero_or_nonfinite",
            "pearson_correlation": correlation,
            "correlation_status": "ok" if correlation_ok else "unavailable",
            "correlation_reason": "" if correlation_ok else "constant_or_insufficient_trajectory",
        }
    )
    return result
