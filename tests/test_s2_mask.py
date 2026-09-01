from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from twinwater_timesat.s2_mask import (
    QcRule,
    collapse_products_to_dates,
    evaluate_rule,
    load_mask_config,
    write_csv_table,
)


ROOT = Path(__file__).resolve().parents[1]
FINAL_RULE = QcRule(
    rule_id="test_rule",
    rule_label="test",
    role="preferred",
    maximum_bad_pixels=1,
    minimum_water_pixels=8,
    center_pixel_rule="not_obvious_bad",
    maximum_persistent_nonwater_pixels=0,
    maximum_class2_pixels=0,
)


def make_product_qc(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults: dict[str, object] = {
        "platform": "S2A",
        "processing_baseline": "N0500",
        "central_scl": 6,
        "window_size": 3,
        "water_pixel_count": 9,
        "bad_pixel_count": 0,
        "persistent_nonwater_pixel_count": 0,
        "class2_pixel_count": 0,
        "water_fraction": 1.0,
        "bad_scl_fraction": 0.0,
        "persistent_nonwater_fraction": 0.0,
        "class2_fraction": 0.0,
        "central_is_water": True,
        "central_is_obvious_bad": False,
        "central_is_persistent_nonwater": False,
        "central_is_class2": False,
    }
    table = pd.DataFrame([{**defaults, **row} for row in rows])
    table["date"] = pd.to_datetime(table["date"]).dt.normalize()
    table["year"] = table["date"].dt.year
    table["month"] = table["date"].dt.month
    table["_acquisition_sort"] = pd.to_datetime(
        table["acquisition_datetime"], utc=True
    )
    return table


def test_integer_pixel_threshold_logic() -> None:
    product_qc = make_product_qc(
        [
            {
                "product_id": "eight_water_one_bad",
                "date": "2025-01-01",
                "acquisition_datetime": "2025-01-01T10:00:00Z",
                "water_pixel_count": 8,
                "bad_pixel_count": 1,
                "water_fraction": 8 / 9,
                "bad_scl_fraction": 1 / 9,
            },
            {
                "product_id": "seven_water_two_bad",
                "date": "2025-01-02",
                "acquisition_datetime": "2025-01-02T10:00:00Z",
                "water_pixel_count": 7,
                "bad_pixel_count": 2,
                "water_fraction": 7 / 9,
                "bad_scl_fraction": 2 / 9,
            },
            {
                "product_id": "persistent_pixel",
                "date": "2025-01-03",
                "acquisition_datetime": "2025-01-03T10:00:00Z",
                "water_pixel_count": 8,
                "persistent_nonwater_pixel_count": 1,
                "water_fraction": 8 / 9,
                "persistent_nonwater_fraction": 1 / 9,
            },
            {
                "product_id": "class2_pixel",
                "date": "2025-01-04",
                "acquisition_datetime": "2025-01-04T10:00:00Z",
                "water_pixel_count": 8,
                "class2_pixel_count": 1,
                "water_fraction": 8 / 9,
                "class2_fraction": 1 / 9,
            },
        ]
    )

    assert evaluate_rule(product_qc, FINAL_RULE).tolist() == [True, False, False, False]


def test_center_water_and_center_not_bad_are_distinct_rule_choices() -> None:
    product_qc = make_product_qc(
        [
            {
                "product_id": "center_persistent",
                "date": "2025-02-01",
                "acquisition_datetime": "2025-02-01T10:00:00Z",
                "central_scl": 4,
                "central_is_water": False,
                "central_is_persistent_nonwater": True,
                "water_pixel_count": 8,
                "persistent_nonwater_pixel_count": 1,
                "water_fraction": 8 / 9,
                "persistent_nonwater_fraction": 1 / 9,
            }
        ]
    )
    allow_persistent = QcRule(
        **{
            **FINAL_RULE.__dict__,
            "maximum_persistent_nonwater_pixels": 1,
        }
    )
    require_water = QcRule(
        **{
            **allow_persistent.__dict__,
            "center_pixel_rule": "water",
        }
    )

    assert evaluate_rule(product_qc, allow_persistent).item() is True
    assert evaluate_rule(product_qc, require_water).item() is False


def test_same_day_collapse_handles_pass_fail_both_and_neither() -> None:
    product_qc = make_product_qc(
        [
            {
                "product_id": "fail_first",
                "date": "2025-03-01",
                "acquisition_datetime": "2025-03-01T10:00:00Z",
                "central_scl": 9,
                "central_is_water": False,
                "central_is_obvious_bad": True,
                "water_pixel_count": 0,
                "bad_pixel_count": 9,
                "water_fraction": 0.0,
                "bad_scl_fraction": 1.0,
            },
            {
                "product_id": "pass_second",
                "date": "2025-03-01",
                "acquisition_datetime": "2025-03-01T10:05:00Z",
            },
            {
                "product_id": "pass_early",
                "date": "2025-03-02",
                "acquisition_datetime": "2025-03-02T10:00:00Z",
            },
            {
                "product_id": "pass_late",
                "date": "2025-03-02",
                "acquisition_datetime": "2025-03-02T10:05:00Z",
            },
            {
                "product_id": "fail_a",
                "date": "2025-03-03",
                "acquisition_datetime": "2025-03-03T10:00:00Z",
                "central_scl": 9,
                "central_is_water": False,
                "central_is_obvious_bad": True,
                "water_pixel_count": 0,
                "bad_pixel_count": 9,
                "water_fraction": 0.0,
                "bad_scl_fraction": 1.0,
            },
            {
                "product_id": "fail_b",
                "date": "2025-03-03",
                "acquisition_datetime": "2025-03-03T10:05:00Z",
                "central_scl": 8,
                "central_is_water": False,
                "central_is_obvious_bad": True,
                "water_pixel_count": 0,
                "bad_pixel_count": 9,
                "water_fraction": 0.0,
                "bad_scl_fraction": 1.0,
            },
        ]
    )

    collapsed = collapse_products_to_dates(
        product_qc, FINAL_RULE, mask_version="test_v1"
    ).set_index("date")

    rescued = collapsed.loc[pd.Timestamp("2025-03-01")]
    assert bool(rescued["s2_date_usable"])
    assert rescued["n_products_passing"] == 1
    assert rescued["selected_product_id"] == "pass_second"
    assert bool(rescued["date_rescued_by_alternate_product"])

    both = collapsed.loc[pd.Timestamp("2025-03-02")]
    assert bool(both["s2_date_usable"])
    assert both["n_products_passing"] == 2
    assert both["selected_product_id"] == "pass_early"

    neither = collapsed.loc[pd.Timestamp("2025-03-03")]
    assert not bool(neither["s2_date_usable"])
    assert neither["n_products_passing"] == 0
    assert pd.isna(neither["selected_product_id"])
    assert neither["reason_if_unusable"] == (
        "no_product_on_date_passed_scene_quality_rule"
    )


def test_representative_ranking_and_exact_acquisition_duplicates_are_deterministic() -> None:
    product_qc = make_product_qc(
        [
            {
                "product_id": "lexical_b",
                "date": "2025-04-01",
                "acquisition_datetime": "2025-04-01T10:00:00Z",
            },
            {
                "product_id": "lexical_a",
                "date": "2025-04-01",
                "acquisition_datetime": "2025-04-01T10:00:00Z",
            },
            {
                "product_id": "one_bad_earlier",
                "date": "2025-04-01",
                "acquisition_datetime": "2025-04-01T09:55:00Z",
                "water_pixel_count": 8,
                "bad_pixel_count": 1,
                "water_fraction": 8 / 9,
                "bad_scl_fraction": 1 / 9,
            },
        ]
    )

    first = collapse_products_to_dates(product_qc, FINAL_RULE, mask_version="test")
    second = collapse_products_to_dates(
        product_qc.sample(frac=1, random_state=42).reset_index(drop=True),
        FINAL_RULE,
        mask_version="test",
    )
    assert len(first) == 1
    assert first.loc[0, "n_products_on_date"] == 3
    assert first.loc[0, "selected_product_id"] == "lexical_a"
    assert second.loc[0, "selected_product_id"] == "lexical_a"
    assert first.loc[0, "all_product_ids"] == second.loc[0, "all_product_ids"]


def test_csv_writes_are_deterministic(tmp_path: Path) -> None:
    table = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "usable": [True, False],
            "fraction": [8 / 9, float("nan")],
        }
    )
    first = write_csv_table(table, tmp_path / "first.csv")
    second = write_csv_table(table, tmp_path / "second.csv")
    assert first.read_bytes() == second.read_bytes()


def test_malformed_config_fails_clearly(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("mask_version: test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Mask config is missing field"):
        load_mask_config(config_path)


def test_observation_mask_cli_help() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/05_erken_s2_observation_mask.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "unique calendar dates" in completed.stdout
    assert "--mask-output" in completed.stdout
    assert "--skip-figures" in completed.stdout


def test_committed_final_mask_has_unique_dates() -> None:
    mask_path = ROOT / "data" / "processed" / "erken_s2_observation_mask.csv"
    mask = pd.read_csv(mask_path)
    assert len(mask) == 926
    assert mask["date"].nunique() == len(mask)
    assert mask["s2_date_usable"].sum() == 307
    assert not any("chlf" in column.lower() for column in mask.columns)
