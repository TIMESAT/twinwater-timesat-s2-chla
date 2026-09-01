"""Leakage-safe nested year-blocked TIMESAT spline selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    PRIMARY_YEARS,
    SPLINE_GRID,
    build_outer_folds,
)
from twinwater_timesat.reconstruction_metrics import evaluate_pointwise_metrics
from twinwater_timesat.timesat_adapter import ReconstructionResult


class SplineRunner(Protocol):
    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series | pd.DatetimeIndex,
        smoothing: int | None = None,
    ) -> ReconstructionResult: ...


@dataclass(frozen=True)
class SplineSelectionResult:
    """One outer fold's selection outcome and complete candidate evidence."""

    outer_test_year: int
    status: str
    failure_reason: str
    selected_smoothing: int | None
    candidate_summary: pd.DataFrame
    candidate_year_results: pd.DataFrame


def select_spline_for_outer_fold(
    common_support: pd.DataFrame,
    *,
    outer_test_year: int,
    runner: SplineRunner,
    candidate_grid: tuple[int, ...] = SPLINE_GRID,
) -> SplineSelectionResult:
    """Select one global smoothing control from only six outer-training years."""

    if tuple(candidate_grid) != SPLINE_GRID:
        raise ValueError(f"Spline grid must be exactly {SPLINE_GRID}.")
    folds = {fold.outer_test_year: fold for fold in build_outer_folds()}
    if outer_test_year not in folds:
        raise ValueError(f"outer_test_year must be in {PRIMARY_YEARS}.")
    fold = folds[outer_test_year]

    # This is the leakage boundary: the outer-test rows are discarded before
    # any sparse value, daily reference value, reconstruction, or metric call.
    training = common_support.loc[
        common_support["year"].isin(fold.inner_training_years)
    ].copy()
    if set(training["year"].unique()) != set(fold.inner_training_years):
        raise ValueError("Not all six outer-training years are available.")

    year_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    for smoothing in candidate_grid:
        year_scores: list[float] = []
        candidate_eligible = True
        failure_reasons: list[str] = []
        for year in fold.inner_training_years:
            year_data = training.loc[training["year"].eq(year)].copy()
            sparse = year_data.loc[
                year_data["s2_openwater_reference_candidate"], ["date", "CHLF"]
            ].copy()
            target_dates = year_data.loc[year_data["common_support"], "date"]
            reconstruction = runner.reconstruct(
                method="timesat_smoothing_spline",
                year=year,
                sparse=sparse,
                target_dates=target_dates,
                smoothing=smoothing,
            )
            if reconstruction.status == "ok":
                metric, _ = evaluate_pointwise_metrics(
                    year_data, reconstruction.prediction
                )
                nrmse = metric["nrmse"]
                valid = bool(
                    metric["nrmse_status"] == "ok" and np.isfinite(nrmse)
                )
                reason = "" if valid else str(metric["nrmse_reason"])
            else:
                nrmse = np.nan
                valid = False
                reason = reconstruction.failure_reason or "reconstruction_failed"
            if valid:
                year_scores.append(float(nrmse))
            else:
                candidate_eligible = False
                failure_reasons.append(f"{year}:{reason}")
            year_rows.append(
                {
                    "outer_test_year": outer_test_year,
                    "smoothing": smoothing,
                    "inner_training_year": year,
                    "nrmse": float(nrmse) if np.isfinite(nrmse) else np.nan,
                    "candidate_year_status": "ok" if valid else "ineligible",
                    "candidate_year_failure_reason": reason,
                    "reconstruction_status": reconstruction.status,
                    "reconstruction_failure_reason": reconstruction.failure_reason,
                    "outer_test_reference_used": False,
                    "tuning_metric": "withheld_day_nrmse",
                    "seasonal_metric_used_for_tuning": False,
                }
            )
        if candidate_eligible and len(year_scores) == 6:
            mean_score = float(np.mean(np.asarray(year_scores, dtype=np.float64)))
            status = "eligible"
            reason = ""
        else:
            mean_score = np.nan
            status = "ineligible"
            reason = ";".join(failure_reasons)
        candidate_rows.append(
            {
                "outer_test_year": outer_test_year,
                "smoothing": smoothing,
                "candidate_status": status,
                "candidate_failure_reason": reason,
                "n_required_training_years": 6,
                "n_valid_training_years": len(year_scores),
                "mean_equal_year_nrmse": mean_score,
                "equal_year_weighting": True,
            }
        )

    candidate_summary = pd.DataFrame(candidate_rows)
    eligible = candidate_summary.loc[
        candidate_summary["candidate_status"].eq("eligible")
    ].copy()
    if eligible.empty:
        return SplineSelectionResult(
            outer_test_year,
            "failed",
            "all_spline_candidates_ineligible",
            None,
            candidate_summary,
            pd.DataFrame(year_rows),
        )
    # Python's stable sort plus the explicit second key implements the frozen
    # exact-float tie rule: an exactly equal stored score selects smaller s.
    winner = eligible.sort_values(
        ["mean_equal_year_nrmse", "smoothing"], kind="mergesort"
    ).iloc[0]
    selected = int(winner["smoothing"])
    candidate_summary["selected_for_outer_fold"] = candidate_summary[
        "smoothing"
    ].eq(selected) & candidate_summary["candidate_status"].eq("eligible")
    return SplineSelectionResult(
        outer_test_year,
        "ok",
        "",
        selected,
        candidate_summary,
        pd.DataFrame(year_rows),
    )


def select_spline_for_all_outer_folds(
    common_support: pd.DataFrame,
    *,
    runner: SplineRunner,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Execute the frozen selection procedure for all seven folds.

    This function is intentionally not called by the pre-performance CLI.
    """

    selections: list[dict[str, Any]] = []
    summaries: list[pd.DataFrame] = []
    year_results: list[pd.DataFrame] = []
    for year in PRIMARY_YEARS:
        result = select_spline_for_outer_fold(
            common_support, outer_test_year=year, runner=runner
        )
        selections.append(
            {
                "outer_test_year": year,
                "selection_status": result.status,
                "selection_failure_reason": result.failure_reason,
                "selected_smoothing": result.selected_smoothing,
            }
        )
        summaries.append(result.candidate_summary)
        year_results.append(result.candidate_year_results)
    return (
        pd.DataFrame(selections),
        pd.concat(summaries, ignore_index=True),
        pd.concat(year_results, ignore_index=True),
    )
