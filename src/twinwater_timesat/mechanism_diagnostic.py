"""Diagnostic-only helpers for the Erken TIMESAT mechanism investigation.

This module is intentionally outside the governed Phase 3/4/5 pipelines.  It
reads their frozen products, writes only under ``results/diagnostics``, and
never selects or recommends a production parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.reconstruction_metrics import (
    evaluate_pointwise_metrics,
    evaluate_seasonal_metrics,
)
from twinwater_timesat.seasonal_events import (
    detect_reconstruction_peak_candidates,
    match_detected_reconstruction_events,
)


DIAGNOSTIC_VERSION = "erken_timesat_mechanism_v1"
P_SEAPAR_GRID = tuple(round(value / 10, 1) for value in range(11))
COARSE_SMOOTHING_GRID = (1000.0, 300.0, 100.0, 30.0, 10.0, 3.0, 1.0, 0.0)
PART_A_METHODS = (
    "linear_interpolation",
    "timesat_smoothing_spline_0",
    "timesat_smoothing_spline_selected",
)


def p_seapar_to_internal_smoothing(p_seapar: float) -> float:
    """Return the exact frozen ``season.f90`` linear mapping."""

    value = float(p_seapar)
    if not np.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("p_seapar must be finite and in [0, 1].")
    return 1000.0 + (50000.0 - 1000.0) * value


def nonzero_derivative_sign_changes(values: Iterable[float]) -> int:
    """Count direction reversals after ignoring exactly flat increments."""

    array = np.asarray(tuple(values), dtype=float)
    if len(array) < 3 or not np.isfinite(array).all():
        return 0
    signs = np.sign(np.diff(array))
    signs = signs[signs != 0]
    return int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0


def interval_geometry(
    values: Iterable[float], *, lower_endpoint: float, upper_endpoint: float, scale: float
) -> dict[str, Any]:
    """Describe containing-endpoint overshoot for one interval."""

    array = np.asarray(tuple(values), dtype=float)
    finite = array[np.isfinite(array)]
    lower = min(float(lower_endpoint), float(upper_endpoint))
    upper = max(float(lower_endpoint), float(upper_endpoint))
    if finite.size == 0:
        return {
            "n_interior_points": 0,
            "spline0_exceeds_endpoint_range": False,
            "n_outside_endpoint_range": 0,
            "fraction_outside_endpoint_range": np.nan,
            "max_positive_overshoot": np.nan,
            "max_negative_overshoot": np.nan,
            "max_negative_overshoot_magnitude": np.nan,
            "max_absolute_overshoot": np.nan,
            "normalized_max_absolute_overshoot": np.nan,
        }
    positive = max(0.0, float(finite.max() - upper))
    negative = min(0.0, float(finite.min() - lower))
    outside = (finite < lower) | (finite > upper)
    maximum = max(positive, abs(negative))
    return {
        "n_interior_points": int(finite.size),
        "spline0_exceeds_endpoint_range": bool(outside.any()),
        "n_outside_endpoint_range": int(outside.sum()),
        "fraction_outside_endpoint_range": float(outside.mean()),
        "max_positive_overshoot": positive,
        "max_negative_overshoot": negative,
        "max_negative_overshoot_magnitude": abs(negative),
        "max_absolute_overshoot": maximum,
        "normalized_max_absolute_overshoot": (
            float(maximum / scale) if np.isfinite(scale) and scale > 0 else np.nan
        ),
    }


def _rmse(reference: pd.Series, prediction: pd.Series) -> float:
    valid = reference.notna() & prediction.notna()
    if not valid.any():
        return np.nan
    difference = prediction.loc[valid].to_numpy(float) - reference.loc[valid].to_numpy(
        float
    )
    return float(np.sqrt(np.mean(np.square(difference))))


def build_interval_geometry_table(
    support: pd.DataFrame,
    curves: pd.DataFrame,
    selected_smoothing: Mapping[int, int],
) -> pd.DataFrame:
    """Build the Part A interval table without crossing open-water segments."""

    pivot = curves.pivot(index="date", columns="method", values="prediction")
    rows: list[dict[str, Any]] = []
    for year, year_support in support.groupby("year", sort=True):
        scale = float(
            year_support.loc[year_support["common_support"], "CHLF"].quantile(0.95)
            - year_support.loc[year_support["common_support"], "CHLF"].quantile(0.05)
        )
        sparse = year_support.loc[
            year_support["s2_openwater_reference_candidate"],
            ["date", "CHLF", "common_support_segment_id"],
        ].sort_values("date")
        for interval_number, (left, right) in enumerate(
            zip(sparse.iloc[:-1].itertuples(), sparse.iloc[1:].itertuples(), strict=True),
            start=1,
        ):
            same_segment = left.common_support_segment_id == right.common_support_segment_id
            base: dict[str, Any] = {
                "year": int(year),
                "interval_number": interval_number,
                "interval_start_date": pd.Timestamp(left.date),
                "interval_end_date": pd.Timestamp(right.date),
                "gap_length_days": int((right.date - left.date).days),
                "left_endpoint_value": float(left.CHLF),
                "right_endpoint_value": float(right.CHLF),
                "common_support_segment_id": left.common_support_segment_id,
                "same_open_water_segment": bool(same_segment),
                "selected_spline_smoothing": int(selected_smoothing[int(year)]),
            }
            if not same_segment:
                base.update(
                    {
                        "interval_status": "unavailable_cross_segment",
                        "interval_reason": "consecutive_sparse_endpoints_cross_open_water_segment",
                    }
                )
                base.update(
                    interval_geometry(
                        [],
                        lower_endpoint=left.CHLF,
                        upper_endpoint=right.CHLF,
                        scale=scale,
                    )
                )
                base.update(
                    {
                        "n_internal_extrema": np.nan,
                        "n_derivative_sign_changes": np.nan,
                        "spline0_changes_derivative_sign_inside_interval": np.nan,
                        "linear_withheld_rmse": np.nan,
                        "spline0_withheld_rmse": np.nan,
                        "selected_spline_withheld_rmse": np.nan,
                        "spline0_minus_linear_withheld_rmse": np.nan,
                    }
                )
                rows.append(base)
                continue

            between = year_support.loc[
                year_support["date"].between(left.date, right.date, inclusive="both")
                & year_support["common_support"]
                & year_support["common_support_segment_id"].eq(
                    left.common_support_segment_id
                )
            ].copy()
            between = between.merge(
                pivot.reset_index(), on="date", how="left", validate="one_to_one"
            )
            interior = between.loc[
                between["date"].gt(left.date) & between["date"].lt(right.date)
            ].copy()
            withheld = interior.loc[
                interior["reference_value_available"]
                & ~interior["s2_openwater_reference_candidate"]
            ]
            geometry = interval_geometry(
                interior["timesat_smoothing_spline_0"],
                lower_endpoint=left.CHLF,
                upper_endpoint=right.CHLF,
                scale=scale,
            )
            changes = nonzero_derivative_sign_changes(
                between["timesat_smoothing_spline_0"]
            )
            linear_rmse = _rmse(withheld["CHLF"], withheld["linear_interpolation"])
            spline0_rmse = _rmse(
                withheld["CHLF"], withheld["timesat_smoothing_spline_0"]
            )
            selected_rmse = _rmse(
                withheld["CHLF"],
                withheld["timesat_smoothing_spline_selected"],
            )
            base.update(
                {
                    "interval_status": "ok",
                    "interval_reason": "",
                    **geometry,
                    "n_internal_extrema": changes,
                    "n_derivative_sign_changes": changes,
                    "spline0_changes_derivative_sign_inside_interval": bool(changes > 0),
                    "linear_withheld_rmse": linear_rmse,
                    "spline0_withheld_rmse": spline0_rmse,
                    "selected_spline_withheld_rmse": selected_rmse,
                    "spline0_minus_linear_withheld_rmse": spline0_rmse
                    - linear_rmse,
                    "n_withheld_evaluation_dates": int(len(withheld)),
                }
            )
            rows.append(base)
    return pd.DataFrame(rows)


def evaluate_curve(
    year_support: pd.DataFrame, curve: pd.DataFrame, *, method: str
) -> dict[str, Any]:
    """Compute the requested Part A metrics on the frozen support."""

    pointwise, _ = evaluate_pointwise_metrics(year_support, curve)
    seasonal = evaluate_seasonal_metrics(year_support, curve)
    values = pd.to_numeric(curve["prediction"], errors="coerce")
    row = {
        "year": int(year_support["year"].iloc[0]),
        "method": method,
        "reconstruction_status": "ok" if values.notna().all() else "failed",
        "mae": pointwise.get("mae"),
        "rmse": pointwise.get("rmse"),
        "nrmse": pointwise.get("nrmse"),
        "pearson_correlation": seasonal.get("pearson_correlation"),
        "n_pointwise_evaluation_dates": pointwise.get(
            "n_pointwise_evaluation_dates"
        ),
        "minimum_reconstructed_value": seasonal.get(
            "minimum_reconstructed_value"
        ),
        "n_negative_reconstructed_days": seasonal.get(
            "n_negative_reconstructed_days"
        ),
        "fraction_negative_reconstructed_days": seasonal.get(
            "fraction_negative_reconstructed_days"
        ),
    }
    return row


def evaluate_event_curve(
    year_support: pd.DataFrame,
    reference_events: pd.DataFrame,
    curve: pd.DataFrame,
    *,
    method: str,
) -> pd.DataFrame:
    """Apply the frozen secondary event protocol to one diagnostic curve."""

    detection = detect_reconstruction_peak_candidates(
        year_support,
        curve[["date", "prediction"]],
        reconstruction_status="ok",
        failure_reason="",
    )
    matched = match_detected_reconstruction_events(reference_events, detection)
    matched.insert(2, "method", method)
    return matched


def summarize_event_recovery(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize event recovery without ranking methods."""

    rows: list[dict[str, Any]] = []
    for keys, group in events.groupby(["year", "method"], sort=True):
        year, method = keys
        available = group["event_status"].ne("unavailable")
        row: dict[str, Any] = {
            "year": int(year),
            "method": method,
            "n_reference_events": int(len(group)),
            "n_matched_events": int(group["event_status"].eq("matched").sum()),
            "n_missed_events": int(
                group["event_status"].eq("missed_no_peak_within_15d").sum()
            ),
        }
        for days in (5, 10, 15):
            row[f"event_recovery_{days}d"] = (
                float(group.loc[available, f"success_{days}d"].astype(bool).mean())
                if available.any()
                else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def equal_year_summary(year_metrics: pd.DataFrame) -> pd.DataFrame:
    """Average each method's seven yearly estimates with equal year weight."""

    metrics = [
        "mae",
        "rmse",
        "nrmse",
        "pearson_correlation",
        "event_recovery_5d",
        "event_recovery_10d",
        "event_recovery_15d",
        "fraction_negative_reconstructed_days",
    ]
    rows = []
    for method, group in year_metrics.groupby("method", sort=False):
        row: dict[str, Any] = {
            "method": method,
            "n_years": int(group["year"].nunique()),
            "total_negative_reconstructed_days": int(
                group["n_negative_reconstructed_days"].sum()
            ),
        }
        for metric in metrics:
            row[f"equal_year_mean_{metric}"] = float(group[metric].mean())
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass
class MechanismRuntime:
    """Persistent JSON-lines client for the diagnostic TIMESAT build."""

    python_executable: Path
    runtime_script: Path
    repository_root: Path
    diagnostic_site_packages: Path
    diagnostic_library_path: Path
    process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "MechanismRuntime":
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [
                str(self.diagnostic_site_packages),
                str(self.repository_root / "src"),
            ]
        )
        environment["DYLD_FALLBACK_LIBRARY_PATH"] = str(
            self.diagnostic_library_path
        )
        environment["OMP_NUM_THREADS"] = "1"
        self.process = subprocess.Popen(
            [str(self.python_executable), str(self.runtime_script)],
            cwd=self.repository_root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self

    def run(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Diagnostic runtime is not active.")
        self.process.stdin.write(json.dumps(dict(request), separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            error = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"Diagnostic TIMESAT runtime stopped: {error}")
        response = json.loads(line)
        if not response.get("ok"):
            raise RuntimeError(
                f"Diagnostic TIMESAT runtime failed: {response.get('error_type')}: "
                f"{response.get('error')}"
            )
        return response["result"]

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process is None:
            return
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)


def runtime_request(
    year_support: pd.DataFrame,
    *,
    p_seapar: float,
    coarse_smoothing_override: float | None,
) -> dict[str, Any]:
    """Make one canonical real-Erken request for the diagnostic runtime."""

    sparse = year_support.loc[
        year_support["s2_openwater_reference_candidate"], ["date", "CHLF"]
    ].sort_values("date")
    return {
        "year": int(year_support["year"].iloc[0]),
        "dates": sparse["date"].dt.strftime("%Y-%m-%d").tolist(),
        "values": sparse["CHLF"].astype(float).tolist(),
        "p_seapar": float(p_seapar),
        "coarse_smoothing_override": coarse_smoothing_override,
    }


def nearest_peak_diagnostic(
    reference_time: pd.Timestamp,
    segment_id: str,
    peaks: pd.DataFrame,
) -> dict[str, Any]:
    """Return same-segment nearest-coarse-peak facts for one reference event."""

    candidates = peaks.loc[peaks["common_support_segment_id"].eq(segment_id)].copy()
    if candidates.empty:
        return {
            "coarse_peak_exists_within_15d": False,
            "nearest_coarse_peak_time": pd.NaT,
            "nearest_coarse_peak_absolute_distance_days": np.nan,
        }
    candidates["distance"] = (
        pd.to_datetime(candidates["peak_time"]) - pd.Timestamp(reference_time)
    ).abs().dt.days
    candidates = candidates.sort_values(["distance", "peak_time"], kind="mergesort")
    nearest = candidates.iloc[0]
    return {
        "coarse_peak_exists_within_15d": bool(nearest["distance"] <= 15),
        "nearest_coarse_peak_time": pd.Timestamp(nearest["peak_time"]),
        "nearest_coarse_peak_absolute_distance_days": int(nearest["distance"]),
    }


def classify_mechanism_case(
    coarse_peak_within_15d: bool, final_event_status: str
) -> str:
    """Classify only the observed coarse-to-final event transition."""

    final_matched = final_event_status == "matched"
    if not coarse_peak_within_15d and not final_matched:
        return "coarse_season_detection_bottleneck"
    if coarse_peak_within_15d and not final_matched:
        return "final_double_logistic_fitting_bottleneck"
    if not coarse_peak_within_15d and final_matched:
        return "final_fit_peak_without_nearby_filtered_coarse_peak"
    return "coarse_and_final_peak_within_15d"
