from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from twinwater_timesat.controlled_gaps import (
    RNG_SPECIFICATION,
    frozen_deletion_count,
    frozen_random_seed,
    generate_consecutive_gap_windows,
    generate_random_deletion_masks,
)
from twinwater_timesat.phase3_contract import PRIMARY_YEARS
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)


ROOT = Path(__file__).resolve().parents[1]


def synthetic_contract_support(*, constant: bool = False) -> pd.DataFrame:
    frames = []
    for year in PRIMARY_YEARS:
        dates = pd.date_range(f"{year}-01-01", periods=60, freq="D")
        values = np.full(60, 5.0) if constant else np.arange(60, dtype=float)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "year": year,
                    "CHLF": values,
                    "open_water": True,
                    "reference_value_available": True,
                    "common_support": True,
                    "common_support_segment_id": f"{year}_segment_1",
                    "s2_openwater_reference_candidate": [
                        index in {0, 20, 40, 59} for index in range(60)
                    ],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_frozen_random_rounding_and_seed_formula() -> None:
    assert frozen_deletion_count(1, 0.5) == 1
    assert frozen_deletion_count(3, 0.5) == 2
    assert frozen_deletion_count(10, 0.1) == 1
    assert frozen_random_seed(2019, 1, 1) == 20261902
    assert frozen_random_seed(2025, 4, 100) == 20865001


def test_random_masks_are_deterministic_sorted_and_protect_boundaries() -> None:
    support = synthetic_contract_support()
    first = generate_random_deletion_masks(support)
    second = generate_random_deletion_masks(support)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 2800
    assert first["rng_specification"].eq(RNG_SPECIFICATION).all()
    assert first["frozen_first_sparse_input_date"].eq(
        first["result_first_sparse_input_date"]
    ).all()
    assert first["frozen_last_sparse_input_date"].eq(
        first["result_last_sparse_input_date"]
    ).all()
    assert "a_gap" not in first.columns
    for text in first.loc[first["n_delete"].gt(0), "deleted_dates"].head(20):
        values = text.split(";")
        assert values == sorted(values)
        assert len(values) == len(set(values))


def test_real_authoritative_random_masks_have_frozen_shape() -> None:
    master = read_phase3_master(
        ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv"
    )
    masks = generate_random_deletion_masks(build_common_support(master))
    assert len(masks) == 7 * 4 * 100
    assert masks.groupby(["year", "deletion_fraction"]).size().eq(100).all()


def test_consecutive_windows_are_exhaustive_eligible_and_protect_boundaries() -> None:
    windows = generate_consecutive_gap_windows(synthetic_contract_support())
    assert set(windows["duration_days"]) == {10, 20, 30, 45}
    assert windows["observations_removed"].ge(1).all()
    assert windows["frozen_first_sparse_input_date"].eq(
        windows["result_first_sparse_input_date"]
    ).all()
    assert windows["frozen_last_sparse_input_date"].eq(
        windows["result_last_sparse_input_date"]
    ).all()
    assert windows["window_midpoint_relative_position"].between(0, 1).all()
    for row in windows.itertuples(index=False):
        deleted = row.deleted_dates.split(";")
        assert row.frozen_first_sparse_input_date.strftime("%Y-%m-%d") not in deleted
        assert row.frozen_last_sparse_input_date.strftime("%Y-%m-%d") not in deleted


def test_a_gap_uses_only_transitions_fully_inside_window() -> None:
    support = synthetic_contract_support()
    windows = generate_consecutive_gap_windows(support)
    row = windows.loc[
        windows["year"].eq(2019)
        & windows["duration_days"].eq(10)
        & windows["window_start_date"].eq(pd.Timestamp("2019-01-16"))
    ].iloc[0]
    scale = 56.05 - 2.95
    assert row["within_window_total_variation"] == 9
    assert np.isclose(row["a_gap"], 9 / scale)
    assert row["maximum_absolute_daily_change_inside_window"] == 1
    assert row["net_start_to_end_reference_change"] == 9


def test_invalid_scale_makes_a_gap_explicitly_unavailable() -> None:
    windows = generate_consecutive_gap_windows(synthetic_contract_support(constant=True))
    assert windows["a_gap"].isna().all()
    assert windows["a_gap_status"].eq("unavailable").all()
    assert windows["a_gap_reason"].eq("q95_minus_q05_not_positive_finite").all()


def test_consecutive_windows_never_cross_open_water_discontinuity() -> None:
    support = synthetic_contract_support()
    target = support["year"].eq(2020)
    missing_date = pd.Timestamp("2020-01-31")
    support = support.loc[~(target & support["date"].eq(missing_date))].copy()
    support.loc[
        support["year"].eq(2020) & support["date"].gt(missing_date),
        "common_support_segment_id",
    ] = "2020_segment_2"
    windows = generate_consecutive_gap_windows(support)
    year_windows = windows.loc[windows["year"].eq(2020)]
    assert not (
        year_windows["window_start_date"].lt(missing_date)
        & year_windows["window_end_date"].gt(missing_date)
    ).any()
