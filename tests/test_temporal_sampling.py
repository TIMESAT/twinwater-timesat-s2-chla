from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.temporal_sampling import (
    FROZEN_MASK_VERSION,
    FROZEN_QC_RULE_ID,
    build_boundary_audit,
    build_candidate_gaps,
    build_join_qc,
    build_year_summary,
    join_daily_reference_and_s2_mask,
    validate_daily_reference,
    validate_s2_mask,
    write_csv_table,
)


ROOT = Path(__file__).resolve().parents[1]


def make_daily(
    dates: list[str],
    *,
    chlf: list[float] | None = None,
    ice: list[int] | None = None,
) -> pd.DataFrame:
    parsed = pd.to_datetime(dates)
    if chlf is None:
        chlf = [float(index + 1) for index in range(len(dates))]
    if ice is None:
        ice = [0] * len(dates)
    years = parsed.year
    return pd.DataFrame(
        {
            "date": parsed,
            "year": years,
            "doy": parsed.dayofyear,
            "CHLF": chlf,
            "PRESENCE_ICE": ice,
            "ice_flag": ice,
            "open_water": [value == 0 for value in ice],
            "measurement_regime": [
                "pre_2023" if year <= 2022 else "2023_onward" for year in years
            ],
        }
    )


def make_mask(
    rows: list[tuple[str, bool]],
) -> pd.DataFrame:
    output = []
    for index, (date, usable) in enumerate(rows):
        product_id = f"product_{index}" if usable else pd.NA
        output.append(
            {
                "date": date,
                "year": pd.Timestamp(date).year,
                "n_products_on_date": 1,
                "n_products_passing": int(usable),
                "s2_date_usable": usable,
                "selected_product_id": product_id,
                "selected_platform": "S2A" if usable else pd.NA,
                "selected_acquisition_datetime": (
                    f"{date}T10:00:00Z" if usable else pd.NA
                ),
                "selected_processing_baseline": "N0500" if usable else pd.NA,
                "selected_central_scl": 6 if usable else np.nan,
                "selected_water_pixel_count_3x3": 9 if usable else np.nan,
                "selected_bad_pixel_count_3x3": 0 if usable else np.nan,
                "selected_persistent_nonwater_pixel_count_3x3": (
                    0 if usable else np.nan
                ),
                "selected_class2_pixel_count_3x3": 0 if usable else np.nan,
                "selected_water_fraction_3x3": 1.0 if usable else np.nan,
                "selected_bad_scl_fraction_3x3": 0.0 if usable else np.nan,
                "qc_rule_id": FROZEN_QC_RULE_ID,
                "mask_version": FROZEN_MASK_VERSION,
            }
        )
    return pd.DataFrame(output)


def test_exact_date_join_preserves_daily_key_space_and_separate_flags() -> None:
    daily = make_daily(
        [
            "2019-04-17",
            "2019-04-18",
            "2019-04-19",
            "2019-04-20",
            "2019-04-21",
        ],
        chlf=[1.0, 2.0, 3.0, np.nan, 5.0],
        ice=[0, 0, 1, 0, 0],
    )
    mask = make_mask(
        [
            ("2019-04-17", True),
            ("2019-04-18", False),
            ("2019-04-19", True),
            ("2019-04-20", True),
        ]
    )

    joined = join_daily_reference_and_s2_mask(daily, mask).set_index("date")

    assert len(joined) == len(daily)
    assert joined.index.is_unique
    assert bool(joined.loc[pd.Timestamp("2019-04-17"), "s2_openwater_reference_candidate"])
    assert not bool(joined.loc[pd.Timestamp("2019-04-18"), "s2_openwater_reference_candidate"])
    assert not bool(joined.loc[pd.Timestamp("2019-04-19"), "s2_openwater_reference_candidate"])
    assert not bool(joined.loc[pd.Timestamp("2019-04-20"), "s2_openwater_reference_candidate"])
    non_s2 = joined.loc[pd.Timestamp("2019-04-21")]
    assert not bool(non_s2["s2_inventory_date"])
    assert not bool(non_s2["s2_date_usable"])
    assert pd.isna(non_s2["selected_product_id"])


def test_missing_reference_is_explicitly_reconciled() -> None:
    daily = make_daily(
        ["2019-04-17", "2019-04-18", "2019-04-19"],
        chlf=[1.0, np.nan, 3.0],
        ice=[0, 0, 1],
    )
    mask = make_mask(
        [
            ("2019-04-17", True),
            ("2019-04-18", True),
            ("2019-04-19", True),
        ]
    )
    daily = validate_daily_reference(daily)
    mask = validate_s2_mask(mask)
    master = join_daily_reference_and_s2_mask(daily, mask)
    gaps = build_candidate_gaps(master)
    qc = build_join_qc(daily, mask, master, gaps).set_index("metric")["value"]

    assert int(qc["n_s2_usable_lhs"]) == 3
    assert int(qc["n_preliminary_candidates"]) == 1
    assert int(qc["n_s2_usable_but_not_openwater"]) == 1
    assert int(qc["n_s2_usable_but_reference_missing"]) == 1
    assert int(qc["n_s2_usable_without_daily_row"]) == 0
    assert int(qc["identity_difference"]) == 0
    assert bool(qc["identity_passed"])


def test_year_summary_uses_within_year_candidate_intervals() -> None:
    daily = make_daily(
        ["2020-01-01", "2020-01-06", "2020-01-16"],
    )
    mask = make_mask([(date, True) for date in daily["date"].dt.strftime("%Y-%m-%d")])
    master = join_daily_reference_and_s2_mask(daily, mask)
    summary = build_year_summary(master).iloc[0]

    assert summary["n_preliminary_sparse_candidates"] == 3
    assert summary["n_intervals"] == 2
    assert summary["median_interval_days"] == 7.5
    assert summary["maximum_interval_days"] == 10


def test_gap_table_flags_year_boundary_and_ice_days() -> None:
    daily = make_daily(
        ["2019-12-31", "2020-01-01", "2020-01-02"],
        ice=[0, 1, 0],
    )
    mask = make_mask([("2019-12-31", True), ("2020-01-02", True)])
    master = join_daily_reference_and_s2_mask(daily, mask)
    gaps = build_candidate_gaps(master)

    assert len(gaps) == 1
    assert gaps.loc[0, "gap_days"] == 2
    assert bool(gaps.loc[0, "crosses_year_boundary"])
    assert gaps.loc[0, "number_of_daily_reference_days_between"] == 1
    assert gaps.loc[0, "number_of_open_water_days_between"] == 0
    assert bool(gaps.loc[0, "contains_ice_day"])


def test_boundary_audit_keeps_2019_and_2025_eligibility_unresolved() -> None:
    daily = make_daily(
        [
            "2019-04-17",
            "2019-04-18",
            "2019-04-19",
            "2019-12-31",
            "2025-01-01",
            "2025-11-28",
            "2025-11-29",
            "2025-11-30",
        ],
        chlf=[5.0, 3.0, 2.0, 1.0, 1.0, 2.0, 4.0, 8.0],
    )
    mask = make_mask([("2019-04-17", True), ("2025-11-30", True)])
    master = join_daily_reference_and_s2_mask(daily, mask)
    audit = build_boundary_audit(master, adjacent_days=3).set_index("year")

    assert audit.loc[2019, "partial_year_boundary_side"] == "left"
    assert audit.loc[2019, "open_water_season_boundary_status"] == "left_truncated"
    assert bool(audit.loc[2019, "boundary_chlf_elevated_relative_to_observed_context"])
    assert audit.loc[2025, "partial_year_boundary_side"] == "right"
    assert audit.loc[2025, "open_water_season_boundary_status"] == "right_truncated"
    assert bool(audit.loc[2025, "boundary_chlf_elevated_relative_to_observed_context"])
    assert audit["requires_later_year_eligibility_decision"].all()


def test_duplicate_daily_dates_fail_clearly() -> None:
    daily = make_daily(["2020-01-01", "2020-01-01"])
    with pytest.raises(ValueError, match="daily reference date keys must be unique"):
        validate_daily_reference(daily)


def test_duplicate_mask_dates_fail_clearly() -> None:
    mask = make_mask([("2020-01-01", True), ("2020-01-01", False)])
    with pytest.raises(ValueError, match="mask date keys must be unique"):
        validate_s2_mask(mask)


def test_csv_output_is_deterministic_and_preserves_date_named_nondate_fields(
    tmp_path: Path,
) -> None:
    table = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "s2_inventory_date": [True, False],
            "n_products_on_date": [1, np.nan],
        }
    )
    first = write_csv_table(table, tmp_path / "first.csv")
    second = write_csv_table(table, tmp_path / "second.csv")
    loaded = pd.read_csv(first)

    assert first.read_bytes() == second.read_bytes()
    assert loaded["date"].tolist() == ["2020-01-01", "2020-01-02"]
    assert loaded["s2_inventory_date"].tolist() == [True, False]
    assert loaded.loc[0, "n_products_on_date"] == 1


def test_temporal_sampling_cli_help() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/06_erken_temporal_sampling_join.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "deterministically join" in completed.stdout
    assert "--daily-reference" in completed.stdout
    assert "--skip-figures" in completed.stdout


def test_committed_temporal_sampling_master_is_unique_and_preliminary() -> None:
    path = ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv"
    master = pd.read_csv(path)
    assert len(master) == 2420
    assert master["date"].nunique() == len(master)
    assert master["s2_inventory_date"].sum() == 926
    assert master["s2_date_usable"].sum() == 307
    assert master["s2_openwater_reference_candidate"].sum() == 288
    assert "analysis_eligible" not in master.columns
    assert "is_sparse_input" not in master.columns
