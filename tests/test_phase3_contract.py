from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    PRIMARY_YEARS,
    SPLINE_GRID,
    build_outer_folds,
    load_contract_config,
    load_timesat_defaults_snapshot,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    build_common_support_summary,
    build_sparse_inputs,
    read_phase3_master,
    validate_phase3_master,
)


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv"


def test_authoritative_governing_documents_and_contract_hashes_validate() -> None:
    config = load_contract_config(ROOT)
    assert config["contract_version"] == CONTRACT_VERSION
    assert config["years"] == list(PRIMARY_YEARS)
    assert config["spline"]["candidate_grid"] == list(SPLINE_GRID)


def test_timesat_defaults_snapshot_is_self_checking_and_frozen() -> None:
    snapshot = load_timesat_defaults_snapshot(
        ROOT / "config" / "timesat_double_logistic_defaults_v4.4.1.json"
    )
    assert snapshot["timesat_core"]["version"] == "4.4.1"
    assert snapshot["timesat_cli"]["version"] == "1.9.2"
    assert snapshot["effective_runtime_parameters"]["p_fitmethod"] == 1
    assert snapshot["frozen_before_performance"] is True
    assert snapshot["effective_runtime_parameters"]["landuse"] == 1
    assert snapshot["effective_runtime_parameters"]["p_st_timestep"] == 1


def test_exact_seven_outer_folds_each_have_only_six_other_years() -> None:
    folds = build_outer_folds()
    assert len(folds) == 7
    assert {fold.outer_test_year for fold in folds} == set(PRIMARY_YEARS)
    for fold in folds:
        assert len(fold.inner_training_years) == 6
        assert fold.outer_test_year not in fold.inner_training_years
        assert set(fold.inner_training_years) == set(PRIMARY_YEARS) - {
            fold.outer_test_year
        }


def test_authoritative_master_produces_exactly_288_sparse_inputs() -> None:
    master = read_phase3_master(MASTER)
    sparse = build_sparse_inputs(master)
    assert len(sparse) == 288
    assert sparse["date"].is_unique
    assert sparse["sparse_input_source_flag"].eq(
        "s2_openwater_reference_candidate"
    ).all()
    assert sparse.groupby("year").size().tolist() == [35, 56, 46, 36, 27, 40, 48]


def test_sparse_input_flag_is_audited_not_silently_regenerated() -> None:
    master = read_phase3_master(MASTER)
    candidate_index = master.index[master["s2_openwater_reference_candidate"]][0]
    master.loc[candidate_index, "s2_openwater_reference_candidate"] = False
    with pytest.raises(ValueError, match="will not be silently regenerated"):
        validate_phase3_master(master)


def test_common_support_is_method_independent_and_has_frozen_boundaries() -> None:
    support = build_common_support(read_phase3_master(MASTER))
    summary = build_common_support_summary(support).set_index("year")
    expected = {
        2019: ("2019-04-17", "2019-12-05", 233, 1),
        2020: ("2020-01-19", "2020-11-22", 303, 2),
        2021: ("2021-03-19", "2021-12-04", 261, 1),
        2022: ("2022-04-18", "2022-12-09", 236, 1),
        2023: ("2023-04-21", "2023-11-29", 223, 1),
        2024: ("2024-04-17", "2024-11-28", 226, 1),
        2025: ("2025-03-21", "2025-11-26", 251, 1),
    }
    for year, (first, last, days, segments) in expected.items():
        row = summary.loc[year]
        assert row["first_sparse_input_date"] == pd.Timestamp(first)
        assert row["last_sparse_input_date"] == pd.Timestamp(last)
        assert row["n_common_support_days"] == days
        assert row["n_common_support_segments"] == segments
    outside = support.loc[~support["inside_frozen_sparse_boundaries"]]
    assert not outside["common_support"].any()
    non_open = support.loc[~support["open_water"]]
    assert not non_open["common_support"].any()
