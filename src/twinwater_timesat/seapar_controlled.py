"""Controlled-gap sensitivity for the LOYO-selected double-logistic p_seapar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.controlled_benchmark import (
    FAMILIES as PHASE4_FAMILIES,
    PersistentTimesatRunner,
    _scenario_support,
)
from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    PRIMARY_YEARS,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_benchmark import (
    evaluate_method_result,
    sparse_input_checksum,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seapar_actual import (
    CV_METHOD,
    _implementation_provenance,
    _json_manifest,
    load_passed_selection,
)
from twinwater_timesat.seapar_sensitivity import (
    CLASSIFICATION,
    PROTOCOL_VERSION,
    SeaparSensitivityGuardError,
    load_passed_seapar_preflight,
    load_seapar_sensitivity_config,
    require_clean_descendant,
    validate_parent_output_inventory,
)
from twinwater_timesat.seasonal_events import (
    PROTOCOL_VERSION as EVENT_PROTOCOL_VERSION,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    match_detected_reconstruction_events,
)
from twinwater_timesat.timesat_adapter import ReconstructionResult


CONTROLLED_ROOT = "results/phase5/double_logistic_seapar_controlled_gaps"
SELECTION_PATH = (
    "results/phase5/double_logistic_seapar_selection/"
    "erken_phase5_seapar_selection.csv"
)
S4_IMPLEMENTATION_PATHS = (
    "scripts/13_timesat_batch_runtime.py",
    "scripts/23_erken_phase5_seapar_controlled_gaps.py",
    "scripts/24_erken_phase5_seapar_controlled_audit.py",
    "src/twinwater_timesat/controlled_benchmark.py",
    "src/twinwater_timesat/reconstruction_benchmark.py",
    "src/twinwater_timesat/reconstruction_metrics.py",
    "src/twinwater_timesat/reconstruction_support.py",
    "src/twinwater_timesat/seapar_actual.py",
    "src/twinwater_timesat/seapar_controlled.py",
    "src/twinwater_timesat/seapar_sensitivity.py",
    "src/twinwater_timesat/seasonal_events.py",
    "src/twinwater_timesat/timesat_adapter.py",
    "tests/test_seapar_controlled.py",
)
FAMILY_SPECS: dict[str, dict[str, Any]] = {
    "random_deletion": {
        "prefix": "random_deletion",
        "output_directory": "random_deletion",
        "expected_scenarios": 2800,
        "phase4_directory": "results/phase4/random_deletion",
        "phase4_metrics": (
            "erken_phase4_random_deletion_scenario_method_metrics.csv"
        ),
        "phase4_events": "erken_phase4_random_deletion_event_metrics.csv",
    },
    "consecutive_internal_gap": {
        "prefix": "consecutive_gaps",
        "output_directory": "consecutive_gaps",
        "expected_scenarios": 5746,
        "phase4_directory": "results/phase4/consecutive_gaps",
        "phase4_metrics": (
            "erken_phase4_consecutive_gaps_scenario_method_metrics.csv"
        ),
        "phase4_events": "erken_phase4_consecutive_gaps_event_metrics.csv",
    },
}


def _payload_manifest(path: Path, checksum_key: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = value.get(checksum_key)
    actual = canonical_json_payload_sha256(value, excluded_keys=(checksum_key,))
    if expected != actual:
        raise SeaparSensitivityGuardError(f"Manifest checksum failed: {path}")
    return value


def _output_names(family: str) -> tuple[str, str]:
    prefix = FAMILY_SPECS[family]["prefix"]
    return (
        f"erken_phase5_seapar_{prefix}_scenario_method_metrics.csv",
        f"erken_phase5_seapar_{prefix}_event_metrics.csv",
    )


def _output_directory(root: Path, family: str) -> Path:
    return root / CONTROLLED_ROOT / FAMILY_SPECS[family]["output_directory"]


def _validate_phase5_parent(
    root: Path, relative_directory: str, filename: str
) -> dict[str, Any]:
    directory = root / relative_directory
    manifest = _json_manifest(directory / filename)
    if manifest.get("audit_status") != "PASS":
        raise SeaparSensitivityGuardError(f"Required Phase 5 parent is not PASS: {filename}")
    for name, expected in manifest.get("table_sha256", {}).items():
        if sha256_file(directory / name) != expected:
            raise SeaparSensitivityGuardError(f"Phase 5 parent table changed: {name}")
    return manifest


def _validate_frozen_controlled_inputs(
    root: Path,
    *,
    family: str,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate raw frozen masks and the saved Phase 4 results without rewriting them."""

    spec = FAMILY_SPECS[family]
    phase3_path = root / "results/phase3/preflight/erken_phase3_preperformance_gate.json"
    phase3 = _payload_manifest(phase3_path, "manifest_payload_sha256")
    mask_name = PHASE4_FAMILIES[family]
    mask_path = phase3_path.parent / mask_name
    raw_mask_sha = sha256_file(mask_path)
    expected_phase3_sha = phase3["table_sha256"][mask_name]
    expected_s0_sha = preflight["parent_output_sha256"][str(mask_path.relative_to(root))]

    phase4_directory = root / spec["phase4_directory"]
    phase4_manifest_path = phase4_directory / "erken_phase4_controlled_gap_manifest.json"
    phase4_manifest = _payload_manifest(
        phase4_manifest_path, "manifest_payload_sha256"
    )
    phase4_audit = _payload_manifest(
        phase4_directory / "erken_phase4_controlled_gap_audit.json",
        "audit_payload_sha256",
    )
    if phase4_audit.get("audit_status") != "PASS":
        raise SeaparSensitivityGuardError(
            f"Original Phase 4 {family} audit is not PASS."
        )
    expected_phase4_sha = phase4_manifest["mask_manifest_sha256"]
    hashes = {raw_mask_sha, expected_phase3_sha, expected_phase4_sha, expected_s0_sha}
    if len(hashes) != 1:
        raise SeaparSensitivityGuardError(
            f"Frozen {family} mask SHA256 mismatch: "
            f"raw={raw_mask_sha}, phase3={expected_phase3_sha}, "
            f"phase4={expected_phase4_sha}, s0={expected_s0_sha}."
        )
    for name, expected in phase4_manifest["table_sha256"].items():
        if sha256_file(phase4_directory / name) != expected:
            raise SeaparSensitivityGuardError(
                f"Original Phase 4 controlled output changed: {name}"
            )

    scenarios = pd.read_csv(mask_path)
    if len(scenarios) != spec["expected_scenarios"]:
        raise SeaparSensitivityGuardError(
            f"Frozen {family} scenario count changed: {len(scenarios)}."
        )
    if not scenarios["mask_id"].is_unique:
        raise SeaparSensitivityGuardError(f"Frozen {family} mask IDs are not unique.")
    endpoints_ok = bool(
        scenarios["frozen_first_sparse_input_date"].eq(
            scenarios["result_first_sparse_input_date"]
        ).all()
        and scenarios["frozen_last_sparse_input_date"].eq(
            scenarios["result_last_sparse_input_date"]
        ).all()
    )
    if not endpoints_ok:
        raise SeaparSensitivityGuardError(f"Frozen {family} endpoint guard failed.")
    if family == "consecutive_internal_gap":
        if not scenarios["common_support_segment_id"].notna().all():
            raise SeaparSensitivityGuardError("A consecutive window crosses a segment.")
        if not scenarios["a_gap_status"].eq("ok").all():
            raise SeaparSensitivityGuardError("Frozen consecutive A_gap changed.")
    elif "a_gap" in scenarios.columns:
        raise SeaparSensitivityGuardError("Random masks unexpectedly contain A_gap.")

    return {
        "scenarios": scenarios,
        "mask_path": str(mask_path.relative_to(root)),
        "mask_sha256": raw_mask_sha,
        "phase3_preperformance_manifest_payload_sha256": phase3[
            "manifest_payload_sha256"
        ],
        "phase4_manifest": phase4_manifest,
        "phase4_manifest_file_sha256": sha256_file(phase4_manifest_path),
        "phase4_audit_payload_sha256": phase4_audit["audit_payload_sha256"],
        "phase4_source_sha256": {
            name: sha256_file(phase4_directory / name)
            for name in (spec["phase4_metrics"], spec["phase4_events"])
        },
        "endpoint_protection_unchanged": endpoints_ok,
    }


def _selected_result(
    year_support: pd.DataFrame,
    *,
    runner: PersistentTimesatRunner,
    selected_p_seapar: float,
) -> ReconstructionResult:
    year = int(year_support["year"].iloc[0])
    sparse = year_support.loc[
        year_support["s2_openwater_reference_candidate"], ["date", "CHLF"]
    ].copy()
    targets = year_support.loc[year_support["common_support"], "date"]
    result = runner.reconstruct(
        method="timesat_double_logistic",
        year=year,
        sparse=sparse.copy(),
        target_dates=targets,
        p_seapar=selected_p_seapar,
    )
    return ReconstructionResult(
        method=CV_METHOD,
        year=year,
        status=result.status,
        failure_reason=result.failure_reason,
        prediction=result.prediction,
        diagnostics={
            **result.diagnostics,
            "sparse_input_checksum": sparse_input_checksum(sparse),
            "identical_sparse_input_enforced": True,
            "selected_p_seapar": selected_p_seapar,
            "p_seapar_reselected_within_scenario": False,
        },
    )


def _build_controlled_tables(
    support: pd.DataFrame,
    references: pd.DataFrame,
    scenarios: pd.DataFrame,
    *,
    family: str,
    selected: Mapping[int, float],
    runner: PersistentTimesatRunner,
) -> dict[str, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    event_tables: list[pd.DataFrame] = []
    for index, scenario in enumerate(scenarios.itertuples(index=False), start=1):
        year = int(scenario.year)
        year_support = _scenario_support(support, scenario)
        result = _selected_result(
            year_support,
            runner=runner,
            selected_p_seapar=selected[year],
        )
        metrics, _ = evaluate_method_result(
            year_support,
            result,
            provenance={
                "contract_version": CONTRACT_VERSION,
                "analysis_classification": CLASSIFICATION,
                "mask_id": scenario.mask_id,
                "scenario_family": family,
                "selected_p_seapar": selected[year],
                "p_seapar_selection_source": SELECTION_PATH,
                "p_seapar_reselected_within_scenario": False,
                "old_methods_reused_not_rerun": True,
            },
        )
        metric_rows.append(metrics)
        detection = detect_reconstruction_peak_candidates(
            year_support,
            result.prediction,
            reconstruction_status=result.status,
            failure_reason=result.failure_reason,
        )
        events = match_detected_reconstruction_events(
            references.loc[references["year"].eq(year)], detection
        )
        events.insert(2, "method", CV_METHOD)
        events.insert(3, "mask_id", scenario.mask_id)
        events.insert(4, "scenario_family", family)
        events["selected_p_seapar"] = selected[year]
        events["p_seapar_selection_source"] = SELECTION_PATH
        events["p_seapar_reselected_within_scenario"] = False
        events["reconstruction_status"] = result.status
        events["reconstruction_failure_code"] = result.failure_reason
        event_tables.append(events)
        if index % 100 == 0 or index == len(scenarios):
            print(
                f"Phase S4 {family}: {index}/{len(scenarios)} scenarios",
                flush=True,
            )
    metrics = pd.DataFrame(metric_rows).sort_values(
        ["year", "mask_id", "method"], kind="mergesort"
    ).reset_index(drop=True)
    events = pd.concat(event_tables, ignore_index=True).sort_values(
        ["year", "mask_id", "method", "reference_event_time"],
        kind="mergesort",
    ).reset_index(drop=True)
    metric_name, event_name = _output_names(family)
    return {metric_name: metrics, event_name: events}


def _audit_tables(
    *,
    family: str,
    scenarios: pd.DataFrame,
    metrics: pd.DataFrame,
    events: pd.DataFrame,
    selected: Mapping[int, float],
    phase4_metrics: pd.DataFrame,
) -> dict[str, bool]:
    expected_count = int(FAMILY_SPECS[family]["expected_scenarios"])
    reference_counts = {2019: 2, 2020: 3, 2021: 2, 2022: 2, 2023: 3, 2024: 2, 2025: 4}
    expected_event_rows = int(scenarios["year"].map(reference_counts).sum())
    expected_parameters = metrics["year"].map(selected).astype(float)
    original_checksums = (
        phase4_metrics.groupby("mask_id")["diagnostic_sparse_input_checksum"]
        .agg(lambda values: set(values.dropna().astype(str)))
        .to_dict()
    )
    same_sparse = all(
        {str(row.diagnostic_sparse_input_checksum)} == original_checksums[row.mask_id]
        for row in metrics.itertuples(index=False)
    )
    failed = set(metrics.loc[metrics["reconstruction_status"].ne("ok"), "mask_id"])
    unavailable = set(
        events.loc[events["event_status"].eq("unavailable"), "mask_id"].unique()
    )
    unavailable_complete = all(
        events.loc[events["mask_id"].eq(mask_id), "event_status"]
        .eq("unavailable")
        .all()
        for mask_id in failed
    )
    matched = events["event_status"].eq("matched")
    event_counts = events.groupby("mask_id")["event_id"].nunique()
    expected_by_mask = scenarios.set_index("mask_id")["year"].map(reference_counts)
    return {
        "expected_scenario_count": len(scenarios) == expected_count,
        "one_new_method_row_per_scenario": bool(
            len(metrics) == expected_count
            and metrics["mask_id"].is_unique
            and metrics["method"].eq(CV_METHOD).all()
        ),
        "expected_event_row_count": len(events) == expected_event_rows,
        "frozen_reference_events_per_scenario": bool(
            event_counts.to_dict() == expected_by_mask.to_dict()
        ),
        "same_mask_scientific_identity_as_phase4": same_sparse,
        "selected_p_seapar_exactly_applied_by_year": bool(
            metrics["selected_p_seapar"].astype(float).eq(expected_parameters).all()
            and metrics["diagnostic_selected_p_seapar"]
            .astype(float)
            .eq(expected_parameters)
            .all()
            and events["selected_p_seapar"]
            .astype(float)
            .eq(events["year"].map(selected).astype(float))
            .all()
        ),
        "runtime_parameter_evidence_exact": bool(
            metrics["diagnostic_requested_p_seapar"]
            .astype(float)
            .eq(expected_parameters)
            .all()
            and metrics["diagnostic_effective_p_seapar"]
            .astype(float)
            .eq(expected_parameters)
            .all()
            and metrics["diagnostic_p_seapar_exactly_materialized"].eq(True).all()  # noqa: E712
        ),
        "no_p_seapar_retuning": bool(
            metrics["p_seapar_reselected_within_scenario"].eq(False).all()  # noqa: E712
            and metrics["diagnostic_p_seapar_reselected_within_scenario"]
            .eq(False)
            .all()  # noqa: E712
            and events["p_seapar_reselected_within_scenario"].eq(False).all()  # noqa: E712
        ),
        "old_methods_reused_not_rerun": bool(
            metrics["old_methods_reused_not_rerun"].eq(True).all()  # noqa: E712
        ),
        "matching_within_15_days": bool(
            events.loc[matched, "absolute_timing_error_days"].le(15).all()
        ),
        "one_to_one_event_matching": bool(
            not events.loc[matched].duplicated(
                ["mask_id", "matched_candidate_id"]
            ).any()
        ),
        "magnitude_not_used_for_matching": bool(
            events["magnitude_used_for_matching"].eq(False).all()  # noqa: E712
        ),
        "failures_preserved_as_unavailable": bool(
            failed == unavailable and unavailable_complete
        ),
    }


def run_seapar_controlled_family(
    *,
    repository_root: str | Path,
    timesat_python: str | Path,
    family: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]]:
    """Execute one S4 family twice before writing and mechanically audit it."""

    if family not in FAMILY_SPECS:
        raise ValueError(f"Unknown controlled family: {family}")
    root = Path(repository_root)
    repository_commit = require_clean_descendant(root)
    preflight = load_passed_seapar_preflight(root)
    selection_manifest, selected = load_passed_selection(root)
    actual_manifest = _validate_phase5_parent(
        root,
        "results/phase5/double_logistic_seapar_actual_mask",
        "erken_phase5_seapar_actual_mask_manifest.json",
    )
    event_manifest = _validate_phase5_parent(
        root,
        "results/phase5/double_logistic_seapar_event_actual_mask",
        "erken_phase5_seapar_event_manifest.json",
    )
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    frozen = _validate_frozen_controlled_inputs(
        root, family=family, preflight=preflight
    )
    config = load_seapar_sensitivity_config(root)
    support = build_common_support(
        read_phase3_master(root / "data/processed/erken_temporal_sampling_master.csv")
    )
    references = detect_reference_major_events(support)
    snapshot = root / config["timesat"]["defaults_snapshot_path"]
    builds: list[dict[str, pd.DataFrame]] = []
    for run_index in (1, 2):
        print(f"Phase S4 {family}: deterministic run {run_index}/2", flush=True)
        with PersistentTimesatRunner(
            Path(timesat_python), root / "scripts/13_timesat_batch_runtime.py", snapshot
        ) as runner:
            builds.append(
                _build_controlled_tables(
                    support,
                    references,
                    frozen["scenarios"],
                    family=family,
                    selected=selected,
                    runner=runner,
                )
            )
    first, second = builds
    deterministic = all(
        deterministic_table_sha256(first[name])
        == deterministic_table_sha256(second[name])
        for name in first
    )
    metric_name, event_name = _output_names(family)
    phase4_directory = root / FAMILY_SPECS[family]["phase4_directory"]
    phase4_metrics = pd.read_csv(
        phase4_directory / FAMILY_SPECS[family]["phase4_metrics"]
    )
    checks = _audit_tables(
        family=family,
        scenarios=frozen["scenarios"],
        metrics=first[metric_name],
        events=first[event_name],
        selected=selected,
        phase4_metrics=phase4_metrics,
    )
    checks.update(
        {
            "raw_mask_sha_matches_phase3_phase4_and_s0": True,
            "endpoint_protection_unchanged": frozen[
                "endpoint_protection_unchanged"
            ],
            "no_cross_segment_windows": bool(
                family == "random_deletion"
                or frozen["scenarios"]["common_support_segment_id"].notna().all()
            ),
            "no_scenario_deduplication": bool(
                frozen["scenarios"]["mask_id"].is_unique
                and len(frozen["scenarios"])
                == FAMILY_SPECS[family]["expected_scenarios"]
            ),
            "a_gap_unchanged": bool(
                family == "random_deletion"
                and "a_gap" not in frozen["scenarios"].columns
                or family == "consecutive_internal_gap"
                and frozen["scenarios"]["a_gap_status"].eq("ok").all()
            ),
            "no_spline_retuning": True,
            "deterministic_output_regeneration": deterministic,
            "phase_s1_s2_s3_pass": True,
            "original_parent_outputs_unchanged": True,
        }
    )
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SeaparSensitivityGuardError(
            f"Phase S4 {family} audit HOLD: " + ", ".join(failed)
        )
    implementation = _implementation_provenance(root, S4_IMPLEMENTATION_PATHS)
    spec = FAMILY_SPECS[family]
    manifest: dict[str, Any] = {
        "schema_version": f"erken_phase5_seapar_{spec['prefix']}_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "event_protocol_version": EVENT_PROTOCOL_VERSION,
        "analysis_classification": CLASSIFICATION,
        "scenario_family": family,
        "repository_code_commit": repository_commit,
        "repository_worktree_dirty": False,
        **implementation,
        "selection_manifest_payload_sha256": selection_manifest[
            "manifest_payload_sha256"
        ],
        "actual_mask_manifest_payload_sha256": actual_manifest[
            "manifest_payload_sha256"
        ],
        "event_manifest_payload_sha256": event_manifest[
            "manifest_payload_sha256"
        ],
        "phase3_preperformance_manifest_payload_sha256": frozen[
            "phase3_preperformance_manifest_payload_sha256"
        ],
        "original_phase4_manifest_payload_sha256": frozen["phase4_manifest"][
            "manifest_payload_sha256"
        ],
        "original_phase4_manifest_file_sha256": frozen[
            "phase4_manifest_file_sha256"
        ],
        "original_phase4_audit_payload_sha256": frozen[
            "phase4_audit_payload_sha256"
        ],
        "original_phase4_source_sha256": frozen["phase4_source_sha256"],
        "mask_manifest_path": frozen["mask_path"],
        "mask_manifest_sha256": frozen["mask_sha256"],
        "n_scenarios": len(frozen["scenarios"]),
        "n_scenario_method_rows": len(first[metric_name]),
        "n_event_rows": len(first[event_name]),
        "new_method": CV_METHOD,
        "selected_p_seapar": {
            str(year): value for year, value in selected.items()
        },
        "p_seapar_reselected_within_scenario": False,
        "linear_spline_default_dl_reused_not_rerun": True,
        "frozen_spline_selections_unchanged": True,
        "controlled_gap_results_used_for_tuning": False,
        "method_ranking_generated": False,
        "audit_status": "PASS",
        "audit_checks": checks,
        "table_sha256": {
            name: deterministic_table_sha256(table)
            for name, table in first.items()
        },
        "method_status_counts": {
            str(key): int(value)
            for key, value in first[metric_name]["reconstruction_status"]
            .value_counts()
            .items()
        },
        "parent_output_sha256": preflight["parent_output_sha256"],
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    audit: dict[str, Any] = {
        "schema_version": f"erken_phase5_seapar_{spec['prefix']}_audit_v1",
        "protocol_version": PROTOCOL_VERSION,
        "family": family,
        "audit_status": "PASS",
        "checks": checks,
        "scenario_count": len(frozen["scenarios"]),
        "scenario_method_count": len(first[metric_name]),
        "event_row_count": len(first[event_name]),
        "mask_manifest_sha256": frozen["mask_sha256"],
        "selected_p_seapar": manifest["selected_p_seapar"],
        "benchmark_manifest_payload_sha256": manifest[
            "manifest_payload_sha256"
        ],
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return first, manifest, audit


def write_seapar_controlled_family(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    audit: Mapping[str, Any],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / name)
        for name, table in tables.items()
    ]
    paths.append(
        write_deterministic_json(
            audit, output / "erken_phase5_seapar_controlled_gap_audit.json"
        )
    )
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase5_seapar_controlled_gap_manifest.json"
        )
    )
    return paths


def audit_saved_seapar_controlled_family(
    *, repository_root: str | Path, family: str
) -> dict[str, Any]:
    """Independently re-audit saved S4 tables and their frozen parents."""

    if family not in FAMILY_SPECS:
        raise ValueError(f"Unknown controlled family: {family}")
    root = Path(repository_root)
    preflight = load_passed_seapar_preflight(root)
    _, selected = load_passed_selection(root)
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    frozen = _validate_frozen_controlled_inputs(
        root, family=family, preflight=preflight
    )
    output = _output_directory(root, family)
    manifest = _payload_manifest(
        output / "erken_phase5_seapar_controlled_gap_manifest.json",
        "manifest_payload_sha256",
    )
    metric_name, event_name = _output_names(family)
    metrics = pd.read_csv(output / metric_name)
    events = pd.read_csv(output / event_name)
    phase4_metrics = pd.read_csv(
        root
        / FAMILY_SPECS[family]["phase4_directory"]
        / FAMILY_SPECS[family]["phase4_metrics"]
    )
    checks = _audit_tables(
        family=family,
        scenarios=frozen["scenarios"],
        metrics=metrics,
        events=events,
        selected=selected,
        phase4_metrics=phase4_metrics,
    )
    checks.update(
        {
            "raw_mask_sha_matches_phase3_phase4_and_s0": (
                manifest["mask_manifest_sha256"] == frozen["mask_sha256"]
            ),
            "endpoint_protection_unchanged": frozen[
                "endpoint_protection_unchanged"
            ],
            "no_cross_segment_windows": bool(
                family == "random_deletion"
                or frozen["scenarios"]["common_support_segment_id"].notna().all()
            ),
            "no_scenario_deduplication": bool(
                frozen["scenarios"]["mask_id"].is_unique
                and len(frozen["scenarios"])
                == FAMILY_SPECS[family]["expected_scenarios"]
            ),
            "a_gap_unchanged": bool(
                family == "random_deletion"
                and "a_gap" not in frozen["scenarios"].columns
                or family == "consecutive_internal_gap"
                and frozen["scenarios"]["a_gap_status"].eq("ok").all()
            ),
            "no_spline_retuning": bool(
                manifest["frozen_spline_selections_unchanged"]
                and manifest["linear_spline_default_dl_reused_not_rerun"]
            ),
            "deterministic_output_regeneration": bool(
                manifest["audit_checks"]["deterministic_output_regeneration"]
            ),
            "output_checksums": all(
                sha256_file(output / name) == expected
                for name, expected in manifest["table_sha256"].items()
            ),
            "manifest_parent_hashes_current": bool(
                manifest["original_phase4_manifest_file_sha256"]
                == frozen["phase4_manifest_file_sha256"]
                and manifest["original_phase4_source_sha256"]
                == frozen["phase4_source_sha256"]
            ),
            "original_parent_outputs_unchanged": True,
        }
    )
    status = "PASS" if all(checks.values()) else "HOLD"
    audit: dict[str, Any] = {
        "schema_version": (
            f"erken_phase5_seapar_{FAMILY_SPECS[family]['prefix']}_audit_v1"
        ),
        "protocol_version": PROTOCOL_VERSION,
        "family": family,
        "audit_status": status,
        "checks": checks,
        "scenario_count": len(frozen["scenarios"]),
        "scenario_method_count": len(metrics),
        "event_row_count": len(events),
        "mask_manifest_sha256": frozen["mask_sha256"],
        "selected_p_seapar": manifest["selected_p_seapar"],
        "benchmark_manifest_payload_sha256": manifest[
            "manifest_payload_sha256"
        ],
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return audit
