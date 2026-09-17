from __future__ import annotations

import copy
import math
import subprocess
import sys
from pathlib import Path

import pytest

from twinwater_timesat.s2_chlf_matchup import (
    build_association_tables,
    build_loyo_tables,
    build_matchup_audit,
    default_config_path,
    load_chlf_matchup_config,
    write_csv,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def config():
    original = load_chlf_matchup_config(
        default_config_path(ROOT), repository_root=ROOT
    )
    values = copy.deepcopy(original.values)
    values["association"]["year_cluster_bootstrap"]["replicates"] = 30
    return type(original)(values, original.source_relative_path, original.sha256)


def _selection_row(
    date: str,
    year: int,
    method: str,
    *,
    ndci: float,
    mci: float,
    ndci_eligible: bool = True,
    mci_eligible: bool = True,
    exact: bool = True,
) -> dict[str, str]:
    return {
        "date": date,
        "year": str(year),
        "observation_method": method,
        "chlf_used": "False",
        "exact_three_method_source_alignment": str(exact),
        "ndci_observation_eligible": str(ndci_eligible),
        "mci_observation_eligible": str(mci_eligible),
        "NDCI_median": str(ndci),
        "MCI_median": str(mci),
        "NDCI_valid_pixel_count": "9",
        "MCI_valid_pixel_count": "9",
        "source_product_id": f"{method}_{date}",
    }


def _reference_row(
    date: str, year: int, chlf: float, *, open_water: bool = True
) -> dict[str, str]:
    return {
        "date": date,
        "year": str(year),
        "CHLF": str(chlf),
        "PRESENCE_ICE": "0" if open_water else "1",
        "open_water": str(open_water),
        "measurement_regime": "pre_2023" if year < 2023 else "2023_onward",
    }


def _perfect_fixture():
    selection = []
    reference = []
    counter = 1
    for year in (2020, 2021, 2022):
        for day in (1, 2, 3):
            date = f"{year}-06-{day:02d}"
            chlf = float(counter)
            index = math.log10(chlf)
            reference.append(_reference_row(date, year, chlf))
            for method in ("L1C", "L2A", "ACOLITE"):
                selection.append(
                    _selection_row(
                        date, year, method, ndci=index, mci=index * 0.001
                    )
                )
            counter += 1
    return selection, reference


def test_config_freezes_exact_date_common_support_and_metrics() -> None:
    config = load_chlf_matchup_config(
        default_config_path(ROOT), repository_root=ROOT
    )
    assert config.values["matchup"]["temporal_tolerance_days"] == 0
    assert config.values["matchup"]["nearest_date_matching_allowed"] is False
    assert config.values["matchup"]["interpolation_allowed"] is False
    assert config.values["supports"]["primary"]["id"] == (
        "exact_three_method_metric_common_support"
    )
    assert config.values["association"]["primary_metric"] == (
        "spearman_rho_raw_CHLF_vs_index"
    )
    assert config.values["predictive_validation"]["design"] == (
        "leave_one_calendar_year_out"
    )


def test_exact_date_join_never_uses_nearest_reference(config) -> None:
    selection = [
        _selection_row("2020-06-02", 2020, method, ndci=0.1, mci=0.001)
        for method in ("L1C", "L2A", "ACOLITE")
    ]
    reference = [_reference_row("2020-06-01", 2020, 4.0)]
    audit, pairs = build_matchup_audit(selection, reference, config)
    assert len(audit) == 3
    assert not pairs
    assert all(row["reference_date_match"] is False for row in audit)
    assert all(
        row["ndci_matchup_status"] == "unavailable_no_exact_date_reference"
        for row in audit
    )


def test_common_support_is_metric_specific_and_requires_all_methods(config) -> None:
    date = "2020-06-01"
    selection = [
        _selection_row(
            date,
            2020,
            method,
            ndci=0.1,
            mci=0.001,
            mci_eligible=method != "ACOLITE",
        )
        for method in ("L1C", "L2A", "ACOLITE")
    ]
    audit, pairs = build_matchup_audit(
        selection, [_reference_row(date, 2020, 4.0)], config
    )
    assert all(row["ndci_primary_common_support"] is True for row in audit)
    assert all(row["mci_primary_common_support"] is False for row in audit)
    ndci = [row for row in pairs if row["metric"] == "NDCI"]
    mci = [row for row in pairs if row["metric"] == "MCI"]
    assert len(ndci) == 3
    assert all(row["primary_common_support"] for row in ndci)
    assert len(mci) == 2
    assert not any(row["primary_common_support"] for row in mci)


def test_ice_date_is_retained_but_not_an_analysis_pair(config) -> None:
    date = "2020-01-15"
    selection = [
        _selection_row(date, 2020, method, ndci=0.1, mci=0.001)
        for method in ("L1C", "L2A", "ACOLITE")
    ]
    audit, pairs = build_matchup_audit(
        selection, [_reference_row(date, 2020, 4.0, open_water=False)], config
    )
    assert len(audit) == 3
    assert not pairs
    assert all(row["ndci_matchup_status"] == "ineligible_not_open_water" for row in audit)


def test_perfect_monotonic_fixture_has_exact_association(config) -> None:
    selection, reference = _perfect_fixture()
    _, pairs = build_matchup_audit(selection, reference, config)
    summary, annual = build_association_tables(pairs, config)
    overall = [
        row
        for row in summary
        if row["support"] == "primary_common"
        and row["stratum_type"] == "overall"
    ]
    assert len(overall) == 6
    assert all(row["n_pairs_raw_CHLF"] == 9 for row in overall)
    assert all(row["spearman_rho"] == pytest.approx(1.0) for row in overall)
    assert all(row["pearson_r_log10_CHLF"] == pytest.approx(1.0) for row in overall)
    assert len(annual) == 36


def test_loyo_predictions_use_only_other_years(config) -> None:
    selection, reference = _perfect_fixture()
    _, pairs = build_matchup_audit(selection, reference, config)
    predictions, summary = build_loyo_tables(pairs, config)
    assert len(predictions) == 54
    assert all(row["training_n"] == 6 for row in predictions)
    assert all(row["test_n"] == 3 for row in predictions)
    assert all(row["fold_status"] == "ok" for row in predictions)
    assert all(
        row["predicted_log10_CHLF"] == pytest.approx(row["observed_log10_CHLF"])
        for row in predictions
    )
    pooled = [row for row in summary if row["evaluation_scope"] == "pooled_all_heldout"]
    assert len(pooled) == 6
    assert all(row["RMSE_log10_CHLF"] == pytest.approx(0.0, abs=1e-14) for row in pooled)
    assert all(row["R2_log10_CHLF"] == pytest.approx(1.0) for row in pooled)


def test_csv_writer_is_deterministic_lf(config, tmp_path: Path) -> None:
    selection, reference = _perfect_fixture()
    audit, _ = build_matchup_audit(selection, reference, config)
    first = write_csv(audit, tmp_path / "first.csv")
    second = write_csv(audit, tmp_path / "second.csv")
    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()


def test_cli_help_states_scientific_boundary() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/29_erken_phase6c_chlf_matchup.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "exact-same-date" in completed.stdout
    assert "Does not retune observation rules" in completed.stdout
    assert "Vombsjön" in completed.stdout
