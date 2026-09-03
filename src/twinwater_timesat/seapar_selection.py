"""Leakage-safe LOYO selection of double-logistic p_seapar."""

from __future__ import annotations

from dataclasses import dataclass
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import numpy as np
import pandas as pd

from twinwater_timesat.controlled_benchmark import PersistentTimesatRunner
from twinwater_timesat.phase3_contract import (
    PRIMARY_YEARS,
    build_outer_folds,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_benchmark import sparse_input_checksum
from twinwater_timesat.reconstruction_metrics import (
    evaluate_pointwise_metrics,
    robust_reference_scale,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seapar_sensitivity import (
    CLASSIFICATION,
    CONFIG_PATH,
    PROTOCOL_VERSION,
    SEAPAR_GRID,
    SeaparSensitivityGuardError,
    load_passed_seapar_preflight,
    load_seapar_sensitivity_config,
    require_clean_descendant,
    validate_parent_output_inventory,
)
from twinwater_timesat.timesat_adapter import ReconstructionResult, SubprocessTimesatRunner


S1_IMPLEMENTATION_PATHS = (
    "config/double_logistic_seapar_sensitivity_v1.0.json",
    "config/timesat_double_logistic_defaults_v4.4.1.json",
    "scripts/07_timesat_runtime.py",
    "scripts/13_timesat_batch_runtime.py",
    "scripts/19_erken_phase5_seapar_selection.py",
    "src/twinwater_timesat/phase3_contract.py",
    "src/twinwater_timesat/reconstruction_benchmark.py",
    "src/twinwater_timesat/reconstruction_metrics.py",
    "src/twinwater_timesat/reconstruction_support.py",
    "src/twinwater_timesat/seapar_sensitivity.py",
    "src/twinwater_timesat/seapar_selection.py",
    "src/twinwater_timesat/timesat_adapter.py",
)
SELECTION_TEST_EVIDENCE_PATH = (
    "results/phase5/double_logistic_seapar_selection/"
    "erken_phase5_seapar_preexecution_tests.json"
)


class SeaparRunner(Protocol):
    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series | pd.DatetimeIndex,
        smoothing: int | None = None,
        p_seapar: float | None = None,
    ) -> ReconstructionResult: ...


@dataclass(frozen=True)
class SeaparSelectionResult:
    outer_test_year: int
    status: str
    failure_reason: str
    selected_p_seapar: float | None
    selected_mean_training_nrmse: float | None
    tie_status: str
    candidate_summary: pd.DataFrame
    candidate_year_results: pd.DataFrame


def _parameter_evidence(result: ReconstructionResult, candidate: float) -> bool:
    diagnostics = result.diagnostics
    return bool(
        diagnostics.get("p_seapar_exactly_materialized") is True
        and diagnostics.get("effective_p_seapar") == candidate
        and diagnostics.get("requested_p_seapar") == candidate
        and diagnostics.get("p_seapar_array_dtype") == "float64"
    )


def select_seapar_for_outer_fold(
    common_support: pd.DataFrame,
    *,
    outer_test_year: int,
    runner: SeaparRunner,
    candidate_grid: tuple[float, ...] = SEAPAR_GRID,
) -> SeaparSelectionResult:
    """Select p_seapar using only the six training years of one outer fold."""

    if tuple(candidate_grid) != SEAPAR_GRID:
        raise ValueError(f"p_seapar grid must be exactly {SEAPAR_GRID}.")
    folds = {fold.outer_test_year: fold for fold in build_outer_folds()}
    if outer_test_year not in folds:
        raise ValueError(f"outer_test_year must be in {PRIMARY_YEARS}.")
    fold = folds[outer_test_year]
    training = common_support.loc[
        common_support["year"].isin(fold.inner_training_years)
    ].copy()
    if set(training["year"].unique()) != set(fold.inner_training_years):
        raise ValueError("Not all six outer-training years are available.")

    year_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for candidate in candidate_grid:
        scores: dict[int, float] = {}
        failures: list[str] = []
        for year in fold.inner_training_years:
            year_data = training.loc[training["year"].eq(year)].copy()
            sparse = year_data.loc[
                year_data["s2_openwater_reference_candidate"], ["date", "CHLF"]
            ].copy()
            targets = year_data.loc[year_data["common_support"], "date"]
            scale = robust_reference_scale(
                year_data.loc[
                    year_data["common_support"]
                    & year_data["reference_value_available"],
                    "CHLF",
                ]
            )
            reconstruction = runner.reconstruct(
                method="timesat_double_logistic",
                year=year,
                sparse=sparse,
                target_dates=targets,
                p_seapar=candidate,
            )
            parameter_ok = _parameter_evidence(reconstruction, candidate)
            if reconstruction.status == "ok":
                pointwise, _ = evaluate_pointwise_metrics(
                    year_data, reconstruction.prediction
                )
            else:
                pointwise = {
                    "pointwise_metric_status": "unavailable",
                    "pointwise_metric_reason": "reconstruction_failed",
                    "nrmse_status": "unavailable",
                    "nrmse_reason": "reconstruction_failed",
                    "rmse": np.nan,
                    "nrmse": np.nan,
                    "n_pointwise_evaluation_dates": int(
                        (
                            year_data["common_support"]
                            & year_data["reference_value_available"]
                            & ~year_data["s2_openwater_reference_candidate"]
                        ).sum()
                    ),
                }
            nrmse = pointwise["nrmse"]
            valid = bool(
                reconstruction.status == "ok"
                and parameter_ok
                and pointwise["nrmse_status"] == "ok"
                and np.isfinite(nrmse)
            )
            if valid:
                scores[year] = float(nrmse)
                reason = ""
            else:
                reason = (
                    reconstruction.failure_reason
                    or ("runtime_parameter_evidence_failed" if not parameter_ok else "")
                    or str(pointwise["nrmse_reason"])
                )
                failures.append(f"{year}:{reason}")
            diagnostics = reconstruction.diagnostics
            year_rows.append(
                {
                    "outer_test_year": outer_test_year,
                    "training_year": year,
                    "candidate_p_seapar": candidate,
                    "candidate_year_status": "ok" if valid else "ineligible",
                    "candidate_year_failure_reason": reason,
                    "reconstruction_status": reconstruction.status,
                    "reconstruction_failure_reason": reconstruction.failure_reason,
                    "rmse": pointwise["rmse"],
                    "q05_reference": scale["q05"],
                    "q95_reference": scale["q95"],
                    "q95_minus_q05": scale["scale"],
                    "nrmse": nrmse,
                    "n_pointwise_evaluation_dates": pointwise[
                        "n_pointwise_evaluation_dates"
                    ],
                    "sparse_input_checksum": sparse_input_checksum(sparse),
                    "requested_p_seapar": diagnostics.get("requested_p_seapar"),
                    "requested_p_seapar_float64_hex": diagnostics.get(
                        "requested_p_seapar_float64_hex"
                    ),
                    "effective_p_seapar": diagnostics.get("effective_p_seapar"),
                    "effective_p_seapar_float64_hex": diagnostics.get(
                        "effective_p_seapar_float64_hex"
                    ),
                    "p_seapar_array_dtype": diagnostics.get(
                        "p_seapar_array_dtype"
                    ),
                    "p_seapar_exactly_materialized": parameter_ok,
                    "outer_test_reference_used": False,
                    "tuning_metric": "withheld_day_nrmse",
                    "equal_year_weighting": True,
                    "event_metrics_used_for_tuning": False,
                    "global_peak_metrics_used_for_tuning": False,
                    "controlled_gap_results_used_for_tuning": False,
                }
            )
        eligible = len(scores) == 6
        mean_score = (
            float(np.mean(np.asarray(list(scores.values()), dtype=np.float64)))
            if eligible
            else np.nan
        )
        summary_rows.append(
            {
                "outer_test_year": outer_test_year,
                "candidate_p_seapar": candidate,
                "candidate_status": "eligible" if eligible else "ineligible",
                "candidate_failure_reason": ";".join(failures),
                "n_required_training_years": 6,
                "n_valid_training_years": len(scores),
                "failure_count": 6 - len(scores),
                "training_year_nrmse_json": json.dumps(
                    {str(year): scores.get(year) for year in fold.inner_training_years},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "mean_equal_year_nrmse": mean_score,
                "equal_year_weighting": True,
            }
        )

    candidate_summary = pd.DataFrame(summary_rows)
    eligible_rows = candidate_summary.loc[
        candidate_summary["candidate_status"].eq("eligible")
    ].copy()
    if eligible_rows.empty:
        return SeaparSelectionResult(
            outer_test_year,
            "failed",
            "all_p_seapar_candidates_ineligible",
            None,
            None,
            "unavailable",
            candidate_summary,
            pd.DataFrame(year_rows),
        )
    minimum = eligible_rows["mean_equal_year_nrmse"].min()
    tied = eligible_rows[eligible_rows["mean_equal_year_nrmse"].eq(minimum)]
    winner = tied.sort_values(
        "candidate_p_seapar", ascending=False, kind="mergesort"
    ).iloc[0]
    selected = float(winner["candidate_p_seapar"])
    candidate_summary["selected_for_outer_fold"] = (
        candidate_summary["candidate_status"].eq("eligible")
        & candidate_summary["candidate_p_seapar"].eq(selected)
    )
    return SeaparSelectionResult(
        outer_test_year,
        "ok",
        "",
        selected,
        float(winner["mean_equal_year_nrmse"]),
        (
            "exact_tie_larger_p_seapar_selected"
            if len(tied) > 1
            else "unique_minimum"
        ),
        candidate_summary,
        pd.DataFrame(year_rows),
    )


def select_seapar_for_all_outer_folds(
    common_support: pd.DataFrame, *, runner: SeaparRunner
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selections: list[dict[str, Any]] = []
    summaries: list[pd.DataFrame] = []
    year_results: list[pd.DataFrame] = []
    for year in PRIMARY_YEARS:
        result = select_seapar_for_outer_fold(
            common_support, outer_test_year=year, runner=runner
        )
        selections.append(
            {
                "outer_test_year": year,
                "selected_p_seapar": result.selected_p_seapar,
                "selected_mean_training_nrmse": (
                    result.selected_mean_training_nrmse
                ),
                "tie_status": result.tie_status,
                "selection_status": result.status,
                "selection_failure_reason": result.failure_reason,
            }
        )
        summaries.append(result.candidate_summary)
        year_results.append(result.candidate_year_results)
    return (
        pd.DataFrame(selections),
        pd.concat(summaries, ignore_index=True),
        pd.concat(year_results, ignore_index=True),
    )


def _selection_code_excludes_event_modules() -> bool:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = ("seasonal_events", "event_benchmark")
    return not any(token in module for module in imported for token in forbidden)


def _implementation_provenance(root: Path) -> dict[str, Any]:
    file_hashes = {
        relative: sha256_file(root / relative) for relative in S1_IMPLEMENTATION_PATHS
    }
    digest = hashlib.sha256()
    for relative, file_hash in file_hashes.items():
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    implementation_commit = _git_log_for_paths(root, S1_IMPLEMENTATION_PATHS)
    return {
        "selection_implementation_commit": implementation_commit,
        "selection_implementation_bundle_sha256": digest.hexdigest(),
        "selection_implementation_file_sha256": file_hashes,
    }


def _git_log_for_paths(root: Path, paths: tuple[str, ...]) -> str:
    import subprocess

    return subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _load_preexecution_test_evidence(
    root: Path, implementation_commit: str
) -> dict[str, Any]:
    path = root / SELECTION_TEST_EVIDENCE_PATH
    if not path.is_file():
        raise SeaparSensitivityGuardError(
            "S1 pre-execution test evidence is missing; run the full relevant suite first."
        )
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("evidence_payload_sha256") != canonical_json_payload_sha256(
        evidence, excluded_keys=("evidence_payload_sha256",)
    ):
        raise SeaparSensitivityGuardError("S1 test-evidence checksum mismatch.")
    required = {
        "implementation_commit": implementation_commit,
        "exit_code": 0,
        "failed": 0,
    }
    for key, expected in required.items():
        if evidence.get(key) != expected:
            raise SeaparSensitivityGuardError(
                f"S1 test evidence {key} must equal {expected!r}."
            )
    if evidence.get("run") != evidence.get("passed") + evidence.get("skipped"):
        raise SeaparSensitivityGuardError("S1 test counts do not reconcile.")
    return evidence


def _equal_year_means_match_exactly(
    candidate_years: pd.DataFrame, summary: pd.DataFrame
) -> bool:
    """Recompute with the exact ordered NumPy path used during selection."""

    for row in summary.itertuples(index=False):
        group = candidate_years.loc[
            candidate_years["outer_test_year"].eq(row.outer_test_year)
            & candidate_years["candidate_p_seapar"].eq(row.candidate_p_seapar)
        ].sort_values("training_year", kind="mergesort")
        values = group["nrmse"].to_numpy(dtype=np.float64)
        if row.candidate_status == "eligible":
            recomputed = float(np.mean(values))
            if recomputed != float(row.mean_equal_year_nrmse):
                return False
        elif not pd.isna(row.mean_equal_year_nrmse):
            return False
    return True


def _candidate_effectiveness(candidate_years: pd.DataFrame) -> dict[str, Any]:
    """Require a real numerical response to at least one candidate change."""

    ranges: list[float] = []
    for _, group in candidate_years.groupby(
        ["outer_test_year", "training_year"], sort=True
    ):
        values = group.sort_values("candidate_p_seapar")["nrmse"].to_numpy(float)
        finite = values[np.isfinite(values)]
        ranges.append(float(np.max(finite) - np.min(finite)) if len(finite) else np.nan)
    materially_different = [
        value for value in ranges if np.isfinite(value) and value > 1e-12
    ]
    return {
        "n_outer_training_year_groups": len(ranges),
        "n_groups_with_candidate_nrmse_range_gt_1e_minus_12": len(
            materially_different
        ),
        "maximum_candidate_nrmse_range": (
            float(np.nanmax(ranges)) if ranges else np.nan
        ),
        "candidate_parameter_effect_observed": bool(materially_different),
        "effectiveness_threshold_absolute_nrmse": 1e-12,
    }


def _with_provenance(
    table: pd.DataFrame, *, commit: str, preflight_sha256: str
) -> pd.DataFrame:
    output = table.copy()
    output.insert(0, "analysis_classification", CLASSIFICATION)
    output.insert(1, "protocol_version", PROTOCOL_VERSION)
    output.insert(2, "repository_code_commit", commit)
    output.insert(3, "preperformance_manifest_payload_sha256", preflight_sha256)
    return output


def run_seapar_selection(
    *, repository_root: str | Path, timesat_python: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]]:
    """Execute and mechanically audit the real training-only Phase S1 selection."""

    root = Path(repository_root)
    commit = require_clean_descendant(root)
    preflight = load_passed_seapar_preflight(root)
    config = load_seapar_sensitivity_config(root)
    implementation = _implementation_provenance(root)
    test_evidence = _load_preexecution_test_evidence(
        root, implementation["selection_implementation_commit"]
    )
    temporal_master = root / "data/processed/erken_temporal_sampling_master.csv"
    support = build_common_support(read_phase3_master(temporal_master))
    snapshot = root / config["timesat"]["defaults_snapshot_path"]
    subprocess_runner = SubprocessTimesatRunner(
        python_executable=timesat_python,
        runtime_script=root / "scripts/07_timesat_runtime.py",
        snapshot_path=snapshot,
    )
    runtime = subprocess_runner.verify_seapar_grid(SEAPAR_GRID)
    with PersistentTimesatRunner(
        Path(timesat_python), root / "scripts/13_timesat_batch_runtime.py", snapshot
    ) as runner:
        selection, summary, candidate_years = select_seapar_for_all_outer_folds(
            support, runner=runner
        )
        second = select_seapar_for_all_outer_folds(support, runner=runner)
        mutation_checks: dict[str, bool] = {}
        for outer_year in PRIMARY_YEARS:
            mutated = support.copy()
            outer = mutated["year"].eq(outer_year)
            mutated.loc[outer, "CHLF"] = np.linspace(-1e12, 1e12, int(outer.sum()))
            changed = select_seapar_for_outer_fold(
                mutated, outer_test_year=outer_year, runner=runner
            )
            baseline_summary = summary.loc[
                summary["outer_test_year"].eq(outer_year)
            ].reset_index(drop=True)
            baseline_years = candidate_years.loc[
                candidate_years["outer_test_year"].eq(outer_year)
            ].reset_index(drop=True)
            mutation_checks[str(outer_year)] = bool(
                changed.selected_p_seapar
                == selection.set_index("outer_test_year").loc[
                    outer_year, "selected_p_seapar"
                ]
                and deterministic_table_sha256(changed.candidate_summary)
                == deterministic_table_sha256(baseline_summary)
                and deterministic_table_sha256(changed.candidate_year_results)
                == deterministic_table_sha256(baseline_years)
            )

    deterministic = all(
        deterministic_table_sha256(left) == deterministic_table_sha256(right)
        for left, right in zip(
            (selection, summary, candidate_years), second, strict=True
        )
    )
    mean_exact = _equal_year_means_match_exactly(candidate_years, summary)
    effectiveness = _candidate_effectiveness(candidate_years)
    checks = {
        "outer_year_absent_from_training_rows": bool(
            candidate_years["outer_test_year"].ne(
                candidate_years["training_year"]
            ).all()
        ),
        "exactly_six_training_years_per_fold_candidate": bool(
            candidate_years.groupby(
                ["outer_test_year", "candidate_p_seapar"]
            )["training_year"].nunique().eq(6).all()
        ),
        "exactly_11_candidates_attempted_per_fold": bool(
            summary.groupby("outer_test_year")["candidate_p_seapar"]
            .nunique()
            .eq(11)
            .all()
        ),
        "candidate_year_row_count_462": len(candidate_years) == 462,
        "equal_year_mean_exact": mean_exact,
        "all_runtime_parameters_exactly_materialized": bool(
            candidate_years["p_seapar_exactly_materialized"].all()
        ),
        "event_modules_absent_from_selection_code": (
            _selection_code_excludes_event_modules()
        ),
        "event_metrics_not_used_for_tuning": bool(
            candidate_years["event_metrics_used_for_tuning"].eq(False).all()  # noqa: E712
        ),
        "held_out_reference_mutation_cannot_change_selection": all(
            mutation_checks.values()
        ),
        "deterministic_rerun": deterministic,
        "all_folds_selected": bool(selection["selection_status"].eq("ok").all()),
        "runtime_grid_still_passed": bool(runtime["candidate_grid_accepted"]),
        "candidate_parameter_effect_observed": effectiveness[
            "candidate_parameter_effect_observed"
        ],
        "preexecution_test_suite_passed": bool(
            test_evidence["exit_code"] == 0 and test_evidence["failed"] == 0
        ),
        "original_parent_outputs_unchanged": True,
    }
    validate_parent_output_inventory(root, preflight["parent_output_sha256"])
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SeaparSensitivityGuardError(
            "Phase S1 audit HOLD: " + ", ".join(failed)
        )
    preflight_sha = preflight["manifest_payload_sha256"]
    tables = {
        "erken_phase5_seapar_candidate_year_nrmse.csv": _with_provenance(
            candidate_years, commit=commit, preflight_sha256=preflight_sha
        ),
        "erken_phase5_seapar_candidate_summary.csv": _with_provenance(
            summary, commit=commit, preflight_sha256=preflight_sha
        ),
        "erken_phase5_seapar_selection.csv": _with_provenance(
            selection, commit=commit, preflight_sha256=preflight_sha
        ),
    }
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_selection_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_code_commit": commit,
        "repository_worktree_dirty": False,
        **implementation,
        "preexecution_test_evidence_path": SELECTION_TEST_EVIDENCE_PATH,
        "preexecution_test_evidence_file_sha256": sha256_file(
            root / SELECTION_TEST_EVIDENCE_PATH
        ),
        "preexecution_test_counts": {
            key: test_evidence[key]
            for key in ("run", "passed", "failed", "skipped", "exit_code")
        },
        "preperformance_manifest_payload_sha256": preflight_sha,
        "parent_output_sha256": preflight["parent_output_sha256"],
        "config_path": CONFIG_PATH,
        "temporal_master_path": str(temporal_master.relative_to(root)),
        "temporal_master_sha256": sha256_file(temporal_master),
        "candidate_grid": list(SEAPAR_GRID),
        "outer_years": list(PRIMARY_YEARS),
        "selection_objective": "minimum_equal_year_mean_withheld_day_nrmse",
        "exact_tie_rule": "larger_p_seapar",
        "selected_p_seapar": {
            str(int(row.outer_test_year)): float(row.selected_p_seapar)
            for row in selection.itertuples(index=False)
        },
        "held_out_reference_mutation_checks": mutation_checks,
        "candidate_parameter_effectiveness": effectiveness,
        "audit_status": "PASS",
        "audit_path": (
            "results/phase5/double_logistic_seapar_selection/"
            "erken_phase5_seapar_selection_audit.json"
        ),
        "audit_checks": checks,
        "table_sha256": {
            name: deterministic_table_sha256(table)
            for name, table in tables.items()
        },
        "held_out_year_performance_generated": False,
        "event_metrics_used_for_tuning": False,
        "controlled_gap_results_used_for_tuning": False,
        "original_parent_outputs_unchanged": True,
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    audit: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_selection_audit_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": CLASSIFICATION,
        "audit_status": "PASS",
        "checks": checks,
        "held_out_reference_mutation_checks": mutation_checks,
        "candidate_parameter_effectiveness": effectiveness,
        "selection_implementation_commit": implementation[
            "selection_implementation_commit"
        ],
        "selection_implementation_bundle_sha256": implementation[
            "selection_implementation_bundle_sha256"
        ],
        "preexecution_test_counts": manifest["preexecution_test_counts"],
        "selection_manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "vombsjon_accessed": False,
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return tables, manifest, audit


def write_seapar_selection(
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
            audit, output / "erken_phase5_seapar_selection_audit.json"
        )
    )
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase5_seapar_selection_manifest.json"
        )
    )
    return paths
