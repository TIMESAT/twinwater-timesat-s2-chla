from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.phase3_contract import PRIMARY_YEARS, SPLINE_GRID
from twinwater_timesat.spline_selection import select_spline_for_outer_fold
from twinwater_timesat.timesat_adapter import ReconstructionResult


def selection_support() -> pd.DataFrame:
    frames = []
    for year in PRIMARY_YEARS:
        dates = pd.date_range(f"{year}-06-01", periods=10, freq="D")
        reference = np.linspace(0, 9, 10)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "year": year,
                    "CHLF": reference,
                    "open_water": True,
                    "reference_value_available": True,
                    "common_support": True,
                    "common_support_segment_id": f"{year}_segment_1",
                    "s2_openwater_reference_candidate": [
                        index in {0, 9} for index in range(10)
                    ],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@dataclass
class FakeSplineRunner:
    errors: dict[int, float]
    failed: set[tuple[int, int]] = field(default_factory=set)
    called_years: list[int] = field(default_factory=list)

    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series,
        smoothing: int | None = None,
    ) -> ReconstructionResult:
        assert method == "timesat_smoothing_spline"
        assert smoothing in SPLINE_GRID
        self.called_years.append(year)
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates))
        if (year, int(smoothing)) in self.failed:
            return ReconstructionResult(
                method,
                year,
                "failed",
                "synthetic_failure",
                pd.DataFrame({"date": targets, "prediction": np.nan}),
                {},
            )
        reference = np.arange(len(targets), dtype=float)
        values = reference + self.errors[int(smoothing)]
        return ReconstructionResult(
            method,
            year,
            "ok",
            "",
            pd.DataFrame({"date": targets, "prediction": values}),
            {},
        )


def test_selection_uses_only_six_outer_training_years_and_equal_year_scores() -> None:
    runner = FakeSplineRunner(
        errors={value: abs(value - 10) + 1 for value in SPLINE_GRID}
    )
    result = select_spline_for_outer_fold(
        selection_support(), outer_test_year=2023, runner=runner
    )
    assert result.status == "ok"
    assert result.selected_smoothing == 10
    assert set(runner.called_years) == set(PRIMARY_YEARS) - {2023}
    assert len(runner.called_years) == 8 * 6
    assert result.candidate_summary["n_valid_training_years"].eq(6).all()
    assert result.candidate_summary["equal_year_weighting"].all()
    assert not result.candidate_year_results["outer_test_reference_used"].any()
    assert not result.candidate_year_results["seasonal_metric_used_for_tuning"].any()


def test_exact_score_tie_chooses_smaller_smoothing_parameter() -> None:
    errors = {value: 5.0 for value in SPLINE_GRID}
    errors[1] = 1.0
    errors[3] = 1.0
    result = select_spline_for_outer_fold(
        selection_support(),
        outer_test_year=2019,
        runner=FakeSplineRunner(errors=errors),
    )
    assert result.selected_smoothing == 1


def test_one_failed_training_year_makes_whole_candidate_ineligible() -> None:
    errors = {value: float(value + 1) for value in SPLINE_GRID}
    errors[1] = 0.1
    errors[3] = 0.2
    runner = FakeSplineRunner(errors=errors, failed={(2020, 1)})
    result = select_spline_for_outer_fold(
        selection_support(), outer_test_year=2019, runner=runner
    )
    row = result.candidate_summary.set_index("smoothing").loc[1]
    assert row["candidate_status"] == "ineligible"
    assert row["n_valid_training_years"] == 5
    assert result.selected_smoothing == 3


def test_all_failed_candidates_record_selection_failure() -> None:
    failures = {
        (year, smoothing)
        for year in PRIMARY_YEARS
        if year != 2025
        for smoothing in SPLINE_GRID
    }
    result = select_spline_for_outer_fold(
        selection_support(),
        outer_test_year=2025,
        runner=FakeSplineRunner(
            errors={value: 1.0 for value in SPLINE_GRID}, failed=failures
        ),
    )
    assert result.status == "failed"
    assert result.failure_reason == "all_spline_candidates_ineligible"
    assert result.selected_smoothing is None
    assert result.candidate_summary["candidate_status"].eq("ineligible").all()


def test_outer_reference_mutation_cannot_change_inner_selection_evidence() -> None:
    original = selection_support()
    mutated = original.copy()
    mutated.loc[mutated["year"].eq(2024), "CHLF"] = 1_000_000
    errors = {value: abs(value - 30) + 1 for value in SPLINE_GRID}
    first = select_spline_for_outer_fold(
        original,
        outer_test_year=2024,
        runner=FakeSplineRunner(errors=errors),
    )
    second = select_spline_for_outer_fold(
        mutated,
        outer_test_year=2024,
        runner=FakeSplineRunner(errors=errors),
    )
    pd.testing.assert_frame_equal(first.candidate_summary, second.candidate_summary)
    pd.testing.assert_frame_equal(
        first.candidate_year_results, second.candidate_year_results
    )


def test_unlisted_smoothing_grid_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be exactly"):
        select_spline_for_outer_fold(
            selection_support(),
            outer_test_year=2020,
            runner=FakeSplineRunner(errors={value: 1 for value in SPLINE_GRID}),
            candidate_grid=(0, 1, 2),
        )
