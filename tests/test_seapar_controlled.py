from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from twinwater_timesat.phase3_contract import sha256_file
from twinwater_timesat.seapar_controlled import (
    CV_METHOD,
    FAMILY_SPECS,
    _audit_tables,
    _validate_frozen_controlled_inputs,
)
from twinwater_timesat.seapar_sensitivity import load_passed_seapar_preflight


ROOT = Path(__file__).resolve().parents[1]
SELECTED = {year: 0.0 for year in range(2019, 2026)}


def test_phase_s4_cli_requires_explicit_authorization() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/23_erken_phase5_seapar_controlled_gaps.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "Refusing Phase S4 performance" in completed.stderr


def test_frozen_controlled_mask_raw_hashes_and_invariants() -> None:
    preflight = load_passed_seapar_preflight(ROOT)
    expected = {
        "random_deletion": "6f37404c2fc98bc4be58de944154e035b29842cd369607259a8831b060eafb06",
        "consecutive_internal_gap": "74d386692544dca9854ac818b3a723e41a7da907379f857e54f4808007acb58d",
    }
    for family, expected_sha in expected.items():
        frozen = _validate_frozen_controlled_inputs(
            ROOT, family=family, preflight=preflight
        )
        assert frozen["mask_sha256"] == expected_sha
        assert sha256_file(ROOT / frozen["mask_path"]) == expected_sha
        assert len(frozen["scenarios"]) == FAMILY_SPECS[family]["expected_scenarios"]
        assert frozen["endpoint_protection_unchanged"] is True


def test_controlled_audit_enforces_fixed_parameter_and_same_sparse_input() -> None:
    scenarios = pd.DataFrame(
        {
            "mask_id": ["m1", "m2"],
            "year": [2019, 2020],
        }
    )
    metrics = pd.DataFrame(
        {
            "mask_id": ["m1", "m2"],
            "year": [2019, 2020],
            "method": [CV_METHOD, CV_METHOD],
            "selected_p_seapar": [0.0, 0.0],
            "diagnostic_selected_p_seapar": [0.0, 0.0],
            "diagnostic_requested_p_seapar": [0.0, 0.0],
            "diagnostic_effective_p_seapar": [0.0, 0.0],
            "diagnostic_p_seapar_exactly_materialized": [True, True],
            "p_seapar_reselected_within_scenario": [False, False],
            "diagnostic_p_seapar_reselected_within_scenario": [False, False],
            "old_methods_reused_not_rerun": [True, True],
            "diagnostic_sparse_input_checksum": ["a", "b"],
            "reconstruction_status": ["ok", "ok"],
        }
    )
    events = pd.DataFrame(
        {
            "mask_id": ["m1", "m1", "m2", "m2", "m2"],
            "year": [2019, 2019, 2020, 2020, 2020],
            "event_id": ["a", "b", "c", "d", "e"],
            "event_status": ["matched", "missed_no_peak_within_15d", "matched", "matched", "matched"],
            "matched_candidate_id": ["p1", None, "p1", "p2", "p3"],
            "absolute_timing_error_days": [5.0, None, 1.0, 10.0, 15.0],
            "magnitude_used_for_matching": [False] * 5,
            "selected_p_seapar": [0.0] * 5,
            "p_seapar_reselected_within_scenario": [False] * 5,
        }
    )
    phase4 = pd.DataFrame(
        {
            "mask_id": ["m1", "m1", "m1", "m2", "m2", "m2"],
            "diagnostic_sparse_input_checksum": ["a", "a", "a", "b", "b", "b"],
        }
    )
    checks = _audit_tables(
        family="random_deletion",
        scenarios=scenarios,
        metrics=metrics,
        events=events,
        selected=SELECTED,
        phase4_metrics=phase4,
    )
    # The tiny fixture intentionally does not have the real scenario count, but
    # every scientific-identity and no-retuning check must pass.
    assert checks["expected_scenario_count"] is False
    for name in (
        "same_mask_scientific_identity_as_phase4",
        "selected_p_seapar_exactly_applied_by_year",
        "runtime_parameter_evidence_exact",
        "no_p_seapar_retuning",
        "old_methods_reused_not_rerun",
        "matching_within_15_days",
        "one_to_one_event_matching",
        "magnitude_not_used_for_matching",
        "failures_preserved_as_unavailable",
    ):
        assert checks[name] is True

    changed = metrics.copy()
    changed.loc[1, "selected_p_seapar"] = 0.1
    failed = _audit_tables(
        family="random_deletion",
        scenarios=scenarios,
        metrics=changed,
        events=events,
        selected=SELECTED,
        phase4_metrics=phase4,
    )
    assert failed["selected_p_seapar_exactly_applied_by_year"] is False


def test_failed_reconstruction_requires_all_events_unavailable() -> None:
    scenarios = pd.DataFrame({"mask_id": ["m1"], "year": [2019]})
    metrics = pd.DataFrame(
        {
            "mask_id": ["m1"],
            "year": [2019],
            "method": [CV_METHOD],
            "selected_p_seapar": [0.0],
            "diagnostic_selected_p_seapar": [0.0],
            "diagnostic_requested_p_seapar": [0.0],
            "diagnostic_effective_p_seapar": [0.0],
            "diagnostic_p_seapar_exactly_materialized": [True],
            "p_seapar_reselected_within_scenario": [False],
            "diagnostic_p_seapar_reselected_within_scenario": [False],
            "old_methods_reused_not_rerun": [True],
            "diagnostic_sparse_input_checksum": ["a"],
            "reconstruction_status": ["failed"],
        }
    )
    events = pd.DataFrame(
        {
            "mask_id": ["m1", "m1"],
            "year": [2019, 2019],
            "event_id": ["a", "b"],
            "event_status": ["unavailable", "unavailable"],
            "matched_candidate_id": [None, None],
            "absolute_timing_error_days": [None, None],
            "magnitude_used_for_matching": [False, False],
            "selected_p_seapar": [0.0, 0.0],
            "p_seapar_reselected_within_scenario": [False, False],
        }
    )
    phase4 = pd.DataFrame(
        {"mask_id": ["m1"], "diagnostic_sparse_input_checksum": ["a"]}
    )
    checks = _audit_tables(
        family="random_deletion",
        scenarios=scenarios,
        metrics=metrics,
        events=events,
        selected=SELECTED,
        phase4_metrics=phase4,
    )
    assert checks["failures_preserved_as_unavailable"] is True
