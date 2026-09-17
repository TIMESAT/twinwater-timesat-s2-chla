from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from twinwater_timesat.s2_observation_selection import (
    EXPECTED_METHODS,
    ObservationSelectionError,
    _read_governed_csv,
    classify_metric,
    default_config_path,
    load_selection_config,
    run_observation_selection,
    write_selection_outputs,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def config():
    return load_selection_config(default_config_path(ROOT), repository_root=ROOT)


@pytest.fixture(scope="module")
def result(config):
    return run_observation_selection(config=config, repository_root=ROOT)


def test_frozen_config_is_exact(config) -> None:
    assert config.minimum_valid_pixels == 6
    assert config.rule_id == "erken_s2_primary3x3_min6_v1"
    assert tuple(config.values["scope"]["methods"]) == EXPECTED_METHODS
    assert config.values["scope"]["primary_window_size"] == 3
    assert config.values["scope"]["grid_resolution_m"] == 20
    assert config.values["indices"]["nominal_central_wavelength_nm"] == {
        "B4": 665.0,
        "B5": 705.0,
        "B6": 740.0,
    }


@pytest.mark.parametrize(
    ("count", "expected_eligible", "expected_status"),
    [
        (5, False, "ineligible_below_6_valid_pixels"),
        (6, True, "eligible_at_least_6_of_9_valid_pixels"),
        (9, True, "eligible_at_least_6_of_9_valid_pixels"),
    ],
)
def test_frozen_threshold_boundary(count, expected_eligible, expected_status) -> None:
    eligible, status = classify_metric(
        count=count,
        source_available=True,
        required_qa_complete=True,
        unavailable_reason="",
    )
    assert eligible is expected_eligible
    assert status == expected_status


def test_missing_required_qa_is_unavailable_even_with_nine_pixels() -> None:
    eligible, status = classify_metric(
        count=9,
        source_available=True,
        required_qa_complete=False,
        unavailable_reason="required_qa_incomplete",
    )
    assert eligible is None
    assert status == "unavailable_required_qa_incomplete"


def test_governed_reader_refuses_chlf_and_ice(tmp_path: Path) -> None:
    for column in ("CHLF", "PRESENCE_ICE"):
        path = tmp_path / f"forbidden_{column}.csv"
        path.write_text(f"date,{column}\n2020-01-01,1\n", encoding="utf-8")
        with pytest.raises(ObservationSelectionError, match="prohibited field"):
            _read_governed_csv(path)


def test_real_inputs_produce_complete_three_method_audit(result) -> None:
    assert result.counts["candidate_dates"] == 926
    assert result.counts["methods"] == 3
    assert result.counts["rows"] == 2778
    assert result.counts["exact_three_method_source_alignment_dates"] == 306
    by_date: dict[str, set[str]] = {}
    for row in result.rows:
        by_date.setdefault(row["date"], set()).add(row["observation_method"])
    assert len(by_date) == 926
    assert all(methods == set(EXPECTED_METHODS) for methods in by_date.values())


def test_real_eligibility_counts_are_frozen(result) -> None:
    assert result.counts["by_method"] == {
        "L1C": {
            "rows": 926,
            "product_available": 306,
            "required_qa_complete": 306,
            "ndci_eligible": 286,
            "mci_eligible": 286,
            "common_b456_eligible": 286,
        },
        "L2A": {
            "rows": 926,
            "product_available": 307,
            "required_qa_complete": 307,
            "ndci_eligible": 283,
            "mci_eligible": 287,
            "common_b456_eligible": 287,
        },
        "ACOLITE": {
            "rows": 926,
            "product_available": 306,
            "required_qa_complete": 306,
            "ndci_eligible": 233,
            "mci_eligible": 234,
            "common_b456_eligible": 234,
        },
    }


def test_metric_specific_counts_control_metric_specific_eligibility(result) -> None:
    row = next(
        row
        for row in result.rows
        if row["date"] == "2022-09-30" and row["observation_method"] == "L2A"
    )
    assert row["NDCI_valid_pixel_count"] == 1
    assert row["MCI_valid_pixel_count"] == 9
    assert row["ndci_observation_eligible"] is False
    assert row["mci_observation_eligible"] is True
    assert row["diagnostic_flags_exclusionary"] is False


def test_ambiguous_l1c_is_explicit_and_does_not_remove_l2a(result) -> None:
    rows = {
        row["observation_method"]: row
        for row in result.rows
        if row["date"] == "2019-06-06"
    }
    assert rows["L2A"]["ndci_observation_eligible"] is True
    assert rows["L1C"]["ndci_observation_eligible"] is None
    assert rows["ACOLITE"]["ndci_observation_eligible"] is None
    assert "ambiguous" in rows["L1C"]["ndci_selection_status"]
    assert all(not row["exact_three_method_source_alignment"] for row in rows.values())


def test_unified_rows_never_expose_chlf_or_ice(result) -> None:
    assert result.rows
    assert "CHLF" not in result.rows[0]
    assert "PRESENCE_ICE" not in result.rows[0]
    assert all(row["chlf_used"] is False for row in result.rows)


def test_writer_records_hashes_and_scientific_guards(
    result, config, tmp_path: Path
) -> None:
    values = dict(config.values)
    # Keep the real frozen output namespace but redirect through a temporary
    # repository-shaped root so this test cannot overwrite committed products.
    fake_root = tmp_path / "repository"
    values["outputs"] = {
        "root": "results/phase6b/observation_selection",
        "selection_table": "results/phase6b/observation_selection/test_selection.csv",
        "manifest": "results/phase6b/observation_selection/test_manifest.json",
    }
    test_config = type(config)(values, config.source_relative_path, config.sha256)
    copied_inputs = {}
    for name, source in result.input_paths.items():
        destination = fake_root / "inputs" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied_inputs[name] = destination
    test_result = type(result)(result.rows, copied_inputs, result.counts)
    written = write_selection_outputs(
        test_result, config=test_config, repository_root=fake_root
    )
    manifest = json.loads(written["manifest"].read_text(encoding="utf-8"))
    assert written["selection_table"].is_file()
    assert manifest["counts"]["rows"] == 2778
    assert manifest["scientific_guards"] == {
        "chlf_read": False,
        "presence_ice_read": False,
        "field_matchup_generated": False,
        "processor_ranking_generated": False,
        "timesat_run": False,
    }
    assert len(manifest["output"]["selection_table_sha256"]) == 64
    assert len(manifest["configuration"]["sha256"]) == 64


def test_cli_help_states_frozen_boundary() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/28_erken_phase6_observation_selection.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert ">=6 valid pixels" in completed.stdout
    assert "does not read CHLF" in completed.stdout
