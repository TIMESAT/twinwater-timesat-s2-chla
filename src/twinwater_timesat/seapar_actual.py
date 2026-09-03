"""Actual-mask and event sensitivity for the LOYO-selected p_seapar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd
import scipy

from twinwater_timesat.event_benchmark import _year_method_summary
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
    EXPECTED_EVENT_TIMES,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    match_detected_reconstruction_events,
)
from twinwater_timesat.timesat_adapter import (
    ReconstructionResult,
    SubprocessTimesatRunner,
)


CV_METHOD = "timesat_double_logistic_cv_seapar"
DEFAULT_METHOD = "timesat_double_logistic_default_seapar1"
COMPARISON_METHODS = (
    "linear_interpolation",
    "timesat_smoothing_spline",
    DEFAULT_METHOD,
    CV_METHOD,
)
SELECTION_DIRECTORY = "results/phase5/double_logistic_seapar_selection"
ACTUAL_DIRECTORY = "results/phase5/double_logistic_seapar_actual_mask"
EVENT_DIRECTORY = "results/phase5/double_logistic_seapar_event_actual_mask"
S2_IMPLEMENTATION_PATHS = (
    "scripts/07_timesat_runtime.py",
    "scripts/20_erken_phase5_seapar_actual_mask.py",
    "src/twinwater_timesat/reconstruction_benchmark.py",
    "src/twinwater_timesat/reconstruction_metrics.py",
    "src/twinwater_timesat/reconstruction_support.py",
    "src/twinwater_timesat/seapar_actual.py",
    "src/twinwater_timesat/seapar_sensitivity.py",
    "src/twinwater_timesat/timesat_adapter.py",
)
S3_IMPLEMENTATION_PATHS = (
    "scripts/21_erken_phase5_seapar_events.py",
    "src/twinwater_timesat/event_benchmark.py",
    "src/twinwater_timesat/seapar_actual.py",
    "src/twinwater_timesat/seasonal_events.py",
)


def _json_manifest(path: Path, checksum_key: str = "manifest_payload_sha256") -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get(checksum_key) != canonical_json_payload_sha256(
        value, excluded_keys=(checksum_key,)
    ):
        raise SeaparSensitivityGuardError(f"Manifest checksum failed: {path}")
    return value


def load_passed_selection(root: str | Path) -> tuple[dict[str, Any], dict[int, float]]:
    root = Path(root)
    directory = root / SELECTION_DIRECTORY
    manifest = _json_manifest(directory / "erken_phase5_seapar_selection_manifest.json")
    if manifest.get("audit_status") != "PASS":
        raise SeaparSensitivityGuardError("Phase S1 selection audit is not PASS.")
    for name, expected in manifest["table_sha256"].items():
        if sha256_file(directory / name) != expected:
            raise SeaparSensitivityGuardError(f"Phase S1 table changed: {name}")
    selected = {
        int(year): float(value)
        for year, value in manifest["selected_p_seapar"].items()
    }
    if tuple(sorted(selected)) != PRIMARY_YEARS:
        raise SeaparSensitivityGuardError("Phase S1 selections do not cover 2019–2025.")
    return manifest, selected


def _implementation_provenance(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    hashes = {relative: sha256_file(root / relative) for relative in paths}
    digest = hashlib.sha256()
    for relative, value in hashes.items():
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(value.encode())
        digest.update(b"\n")
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "implementation_commit": commit,
        "implementation_bundle_sha256": digest.hexdigest(),
        "implementation_file_sha256": hashes,
    }


def _selected_reconstruction(
    year_support: pd.DataFrame,
    *,
    selected_p_seapar: float,
    runner: SubprocessTimesatRunner,
) -> ReconstructionResult:
    year = int(year_support["year"].iloc[0])
    sparse = year_support.loc[
        year_support["s2_openwater_reference_candidate"], ["date", "CHLF"]
    ].copy()
    targets = year_support.loc[year_support["common_support"], "date"]
    result = runner.reconstruct_with_seapar(
        year=year,
        sparse=sparse,
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
            "identical_actual_mask_sparse_input_enforced": True,
        },
    )


def _build_actual_tables(
    support: pd.DataFrame,
    *,
    selected: Mapping[int, float],
    runner: SubprocessTimesatRunner,
    root: Path,
) -> dict[str, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    residuals: list[pd.DataFrame] = []
    daily_rows: list[pd.DataFrame] = []
    for year in PRIMARY_YEARS:
        year_support = support.loc[support["year"].eq(year)].copy()
        result = _selected_reconstruction(
            year_support,
            selected_p_seapar=selected[year],
            runner=runner,
        )
        provenance = {
            "contract_version": CONTRACT_VERSION,
            "analysis_classification": CLASSIFICATION,
            "selected_p_seapar": selected[year],
            "p_seapar_selection_source": (
                f"{SELECTION_DIRECTORY}/erken_phase5_seapar_selection.csv"
            ),
        }
        metrics, residual = evaluate_method_result(
            year_support, result, provenance=provenance
        )
        metric_rows.append(metrics)
        residual["selected_p_seapar"] = selected[year]
        residuals.append(residual)
        curve = year_support.loc[
            year_support["common_support"],
            [
                "date",
                "year",
                "CHLF",
                "s2_openwater_reference_candidate",
                "common_support_segment_id",
            ],
        ].merge(result.prediction, on="date", how="left", validate="one_to_one")
        curve.insert(0, "analysis_classification", CLASSIFICATION)
        curve.insert(1, "outer_test_year", year)
        curve.insert(2, "method", CV_METHOD)
        curve["selected_p_seapar"] = selected[year]
        curve["reconstruction_status"] = result.status
        curve["reconstruction_failure_reason"] = result.failure_reason
        daily_rows.append(curve)
    new_metrics = pd.DataFrame(metric_rows).sort_values("year").reset_index(drop=True)
    old_path = (
        root / "results/phase3/actual_mask/erken_phase3_actual_mask_year_method_metrics.csv"
    )
    old_metrics = pd.read_csv(old_path)
    old_metrics["analysis_role"] = "frozen_primary_reused"
    old_metrics["source_result_path"] = str(old_path.relative_to(root))
    old_metrics["original_method"] = old_metrics["method"]
    old_metrics.loc[
        old_metrics["method"].eq("timesat_double_logistic"), "method"
    ] = DEFAULT_METHOD
    old_metrics["selected_p_seapar"] = np.where(
        old_metrics["method"].eq(DEFAULT_METHOD), 1.0, np.nan
    )
    new_comparison = new_metrics.copy()
    new_comparison["analysis_role"] = "secondary_sensitivity_new"
    new_comparison["source_result_path"] = (
        f"{ACTUAL_DIRECTORY}/erken_phase5_seapar_actual_mask_year_metrics.csv"
    )
    new_comparison["original_method"] = CV_METHOD
    comparison = pd.concat([old_metrics, new_comparison], ignore_index=True, sort=False)
    order = {method: index for index, method in enumerate(COMPARISON_METHODS)}
    comparison["method_display_order"] = comparison["method"].map(order)
    comparison = comparison.sort_values(
        ["year", "method_display_order"], kind="mergesort"
    ).reset_index(drop=True)
    return {
        "erken_phase5_seapar_actual_mask_daily_reconstructions.csv": pd.concat(
            daily_rows, ignore_index=True
        ),
        "erken_phase5_seapar_actual_mask_withheld_residuals.csv": pd.concat(
            residuals, ignore_index=True
        ),
        "erken_phase5_seapar_actual_mask_year_metrics.csv": new_metrics,
        "erken_phase5_seapar_actual_mask_comparison.csv": comparison,
    }


def run_seapar_actual_mask(
    *, repository_root: str | Path, timesat_python: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]]:
    root = Path(repository_root)
    repository_commit = require_clean_descendant(root)
    preflight = load_passed_seapar_preflight(root)
    selection_manifest, selected = load_passed_selection(root)
    config = load_seapar_sensitivity_config(root)
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    support = build_common_support(
        read_phase3_master(root / "data/processed/erken_temporal_sampling_master.csv")
    )
    runner = SubprocessTimesatRunner(
        python_executable=timesat_python,
        runtime_script=root / "scripts/07_timesat_runtime.py",
        snapshot_path=root / config["timesat"]["defaults_snapshot_path"],
    )
    runner.verify_seapar_grid(tuple(config["timesat"]["candidate_grid"]))
    first = _build_actual_tables(
        support, selected=selected, runner=runner, root=root
    )
    second = _build_actual_tables(
        support, selected=selected, runner=runner, root=root
    )
    daily = first["erken_phase5_seapar_actual_mask_daily_reconstructions.csv"]
    metrics = first["erken_phase5_seapar_actual_mask_year_metrics.csv"]
    comparison = first["erken_phase5_seapar_actual_mask_comparison.csv"]
    deterministic = all(
        deterministic_table_sha256(first[name])
        == deterministic_table_sha256(second[name])
        for name in first
    )
    expected_dates = support.loc[support["common_support"]].groupby("year").size()
    observed_dates = daily.groupby("outer_test_year").size()
    checks = {
        "seven_selected_reconstructions": len(metrics) == 7,
        "selection_exactly_applied": bool(
            metrics.set_index("year")["selected_p_seapar"].to_dict() == selected
        ),
        "runtime_parameter_evidence_exact": bool(
            metrics["diagnostic_p_seapar_exactly_materialized"].all()
            and metrics.set_index("year")["diagnostic_effective_p_seapar"].to_dict()
            == selected
        ),
        "all_reconstructions_valid": bool(
            metrics["reconstruction_status"].eq("ok").all()
        ),
        "complete_common_support_daily_output": bool(
            observed_dates.to_dict() == expected_dates.to_dict()
            and daily["prediction"].notna().all()
        ),
        "comparison_has_four_methods_per_year": bool(
            comparison.groupby("year")["method"].nunique().eq(4).all()
            and set(comparison["method"]) == set(COMPARISON_METHODS)
        ),
        "old_methods_reused_not_rerun": True,
        "deterministic_rerun": deterministic,
        "selection_manifest_unchanged": bool(
            selection_manifest["audit_status"] == "PASS"
        ),
        "original_parent_outputs_unchanged": True,
        "event_performance_not_used_or_generated": True,
    }
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SeaparSensitivityGuardError("Phase S2 audit HOLD: " + ", ".join(failed))
    implementation = _implementation_provenance(root, S2_IMPLEMENTATION_PATHS)
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_actual_mask_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_code_commit": repository_commit,
        "repository_worktree_dirty": False,
        **implementation,
        "selection_manifest_payload_sha256": selection_manifest[
            "manifest_payload_sha256"
        ],
        "selected_p_seapar": {str(year): value for year, value in selected.items()},
        "new_method": CV_METHOD,
        "comparison_methods": list(COMPARISON_METHODS),
        "old_methods_reused_not_rerun": True,
        "method_ranking_generated": False,
        "event_performance_generated": False,
        "audit_status": "PASS",
        "audit_checks": checks,
        "parent_output_sha256": preflight["parent_output_sha256"],
        "table_sha256": {
            name: deterministic_table_sha256(table)
            for name, table in first.items()
        },
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    audit: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_actual_mask_audit_v1",
        "audit_status": "PASS",
        "checks": checks,
        "selected_p_seapar": manifest["selected_p_seapar"],
        "benchmark_manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return first, manifest, audit


def write_seapar_actual_mask(
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
            audit, output / "erken_phase5_seapar_actual_mask_audit.json"
        )
    )
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase5_seapar_actual_mask_manifest.json"
        )
    )
    return paths


def _build_event_tables(root: Path) -> dict[str, pd.DataFrame]:
    support = build_common_support(
        read_phase3_master(root / "data/processed/erken_temporal_sampling_master.csv")
    )
    references = detect_reference_major_events(support)
    if list(zip(references["event_id"], references["event_date"], strict=True)) != list(
        EXPECTED_EVENT_TIMES
    ):
        raise SeaparSensitivityGuardError("Frozen 18-event reference set changed.")
    daily = pd.read_csv(
        root / ACTUAL_DIRECTORY / "erken_phase5_seapar_actual_mask_daily_reconstructions.csv",
        parse_dates=["date"],
    )
    rows: list[pd.DataFrame] = []
    for year in PRIMARY_YEARS:
        year_support = support.loc[support["year"].eq(year)].copy()
        curve = daily.loc[daily["outer_test_year"].eq(year)].copy()
        status_values = curve["reconstruction_status"].unique()
        status = status_values[0] if len(status_values) == 1 else "failed"
        reasons = curve["reconstruction_failure_reason"].dropna().astype(str)
        reason = ";".join(sorted(set(reasons)))
        detection = detect_reconstruction_peak_candidates(
            year_support,
            curve[["date", "prediction"]],
            reconstruction_status=status,
            failure_reason=reason,
        )
        matched = match_detected_reconstruction_events(
            references.loc[references["year"].eq(year)], detection
        )
        matched.insert(2, "method", CV_METHOD)
        matched["selected_p_seapar"] = float(curve["selected_p_seapar"].iloc[0])
        matched["reconstruction_status"] = status
        matched["reconstruction_failure_code"] = reason or detection.failure_reason
        matched["reconstructed_prominence_diagnostic"] = np.nan
        rows.append(matched)
    events = pd.concat(rows, ignore_index=True).sort_values(
        ["year", "reference_event_time"], kind="mergesort"
    ).reset_index(drop=True)
    cv_summary = _year_method_summary(events)
    old_path = (
        root / "results/phase3/event_actual_mask/erken_phase3_actual_mask_event_metrics.csv"
    )
    old = pd.read_csv(
        old_path,
        parse_dates=["reference_event_time", "reconstructed_event_time"],
    )
    old["original_method"] = old["method"]
    old.loc[old["method"].eq("timesat_double_logistic"), "method"] = DEFAULT_METHOD
    old["selected_p_seapar"] = np.where(old["method"].eq(DEFAULT_METHOD), 1.0, np.nan)
    old["analysis_role"] = "frozen_primary_reused"
    event_comparison = events.copy()
    event_comparison["original_method"] = CV_METHOD
    event_comparison["analysis_role"] = "secondary_sensitivity_new"
    comparison = pd.concat([old, event_comparison], ignore_index=True, sort=False)
    order = {method: index for index, method in enumerate(COMPARISON_METHODS)}
    comparison["method_display_order"] = comparison["method"].map(order)
    comparison = comparison.sort_values(
        ["year", "method_display_order", "reference_event_time"], kind="mergesort"
    ).reset_index(drop=True)
    comparison_summary = _year_method_summary(comparison)
    return {
        "erken_phase5_seapar_actual_mask_event_metrics.csv": events,
        "erken_phase5_seapar_actual_mask_event_year_summary.csv": cv_summary,
        "erken_phase5_seapar_actual_mask_event_comparison.csv": comparison,
        "erken_phase5_seapar_actual_mask_event_comparison_summary.csv": (
            comparison_summary
        ),
    }


def run_seapar_events(
    *, repository_root: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]]:
    root = Path(repository_root)
    repository_commit = require_clean_descendant(root)
    preflight = load_passed_seapar_preflight(root)
    selection_manifest, selected = load_passed_selection(root)
    actual_manifest = _json_manifest(
        root / ACTUAL_DIRECTORY / "erken_phase5_seapar_actual_mask_manifest.json"
    )
    if actual_manifest.get("audit_status") != "PASS":
        raise SeaparSensitivityGuardError("Phase S2 audit is not PASS.")
    actual_dir = root / ACTUAL_DIRECTORY
    for name, expected in actual_manifest["table_sha256"].items():
        if sha256_file(actual_dir / name) != expected:
            raise SeaparSensitivityGuardError(f"Phase S2 table changed: {name}")
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    first = _build_event_tables(root)
    second = _build_event_tables(root)
    events = first["erken_phase5_seapar_actual_mask_event_metrics.csv"]
    comparison = first["erken_phase5_seapar_actual_mask_event_comparison.csv"]
    matched = events["event_status"].eq("matched")
    flags_exact = all(
        bool(
            events.loc[matched, f"success_{days}d"].astype(bool).eq(
                events.loc[matched, "absolute_timing_error_days"].le(days)
            ).all()
        )
        for days in (5, 10, 15)
    )
    checks = {
        "frozen_18_events_represented": bool(
            len(events) == 18 and events["event_id"].nunique() == 18
        ),
        "all_reconstructions_valid": bool(
            events["reconstruction_status"].eq("ok").all()
        ),
        "no_match_beyond_15_days": bool(
            events.loc[matched, "absolute_timing_error_days"].le(15).all()
        ),
        "one_to_one_matching": bool(
            not events.loc[matched].duplicated(
                ["year", "method", "matched_candidate_id"]
            ).any()
        ),
        "magnitude_not_used_for_matching": bool(
            events["magnitude_used_for_matching"].eq(False).all()  # noqa: E712
        ),
        "timing_threshold_flags_exact": flags_exact,
        "selected_p_seapar_matches_phase_s1": bool(
            events.groupby("year")["selected_p_seapar"].first().to_dict()
            == selected
        ),
        "comparison_has_four_methods_and_18_events_each": bool(
            comparison.groupby("method")["event_id"].nunique().eq(18).all()
            and set(comparison["method"]) == set(COMPARISON_METHODS)
        ),
        "event_metrics_not_used_for_tuning": True,
        "original_event_outputs_reused_unchanged": True,
        "deterministic_regeneration": all(
            deterministic_table_sha256(first[name])
            == deterministic_table_sha256(second[name])
            for name in first
        ),
        "original_parent_outputs_unchanged": True,
    }
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SeaparSensitivityGuardError("Phase S3 audit HOLD: " + ", ".join(failed))
    implementation = _implementation_provenance(root, S3_IMPLEMENTATION_PATHS)
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_event_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_code_commit": repository_commit,
        **implementation,
        "selection_manifest_payload_sha256": selection_manifest[
            "manifest_payload_sha256"
        ],
        "actual_mask_manifest_payload_sha256": actual_manifest[
            "manifest_payload_sha256"
        ],
        "selected_p_seapar": {str(year): value for year, value in selected.items()},
        "scipy_version": scipy.__version__,
        "frozen_reference_event_count": 18,
        "new_method": CV_METHOD,
        "comparison_methods": list(COMPARISON_METHODS),
        "old_event_methods_reused_not_rerun": True,
        "event_metrics_used_for_tuning": False,
        "method_ranking_generated": False,
        "audit_status": "PASS",
        "audit_checks": checks,
        "parent_output_sha256": preflight["parent_output_sha256"],
        "table_sha256": {
            name: deterministic_table_sha256(table)
            for name, table in first.items()
        },
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    audit: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_event_audit_v1",
        "audit_status": "PASS",
        "checks": checks,
        "event_manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return first, manifest, audit


def write_seapar_events(
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
            audit, output / "erken_phase5_seapar_event_audit.json"
        )
    )
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase5_seapar_event_manifest.json"
        )
    )
    return paths
