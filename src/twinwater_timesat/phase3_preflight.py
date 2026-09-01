"""Phase 3 pre-performance gates and deterministic manifest products."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.controlled_gaps import (
    generate_consecutive_gap_windows,
    generate_random_deletion_masks,
)
from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    EXPECTED_SPARSE_DATES,
    PRIMARY_YEARS,
    SPLINE_GRID,
    build_outer_folds,
    canonical_json_payload_sha256,
    load_contract_config,
    load_timesat_defaults_snapshot,
    sha256_file,
)
from twinwater_timesat.reconstruction_benchmark import sparse_input_checksum
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    build_common_support_summary,
    build_sparse_inputs,
    folds_to_table,
    read_phase3_master,
)
from twinwater_timesat.spline_selection import (
    select_spline_for_all_outer_folds,
    select_spline_for_outer_fold,
)
from twinwater_timesat.timesat_adapter import (
    ReconstructionResult,
    SubprocessTimesatRunner,
)


PHASE3_IMPLEMENTATION_PATHS = (
    "pyproject.toml",
    "config/reconstruction_analysis_contract_v1.0.1.json",
    "config/timesat_double_logistic_defaults_v4.4.1.json",
    "docs/Reconstruction_Analysis_Contract_v1.0.1.md",
    "docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md",
    "scripts/07_timesat_runtime.py",
    "scripts/08_erken_phase3_preflight.py",
    "scripts/09_erken_phase3_benchmark.py",
    "src/twinwater_timesat/controlled_gaps.py",
    "src/twinwater_timesat/phase3_benchmark.py",
    "src/twinwater_timesat/phase3_contract.py",
    "src/twinwater_timesat/phase3_preflight.py",
    "src/twinwater_timesat/reconstruction_benchmark.py",
    "src/twinwater_timesat/reconstruction_metrics.py",
    "src/twinwater_timesat/reconstruction_support.py",
    "src/twinwater_timesat/spline_selection.py",
    "src/twinwater_timesat/timesat_adapter.py",
)


def _portable_frame(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            has_time = (
                output[column].dropna().dt.normalize()
                != output[column].dropna()
            ).any()
            format_string = "%Y-%m-%dT%H:%M:%S" if has_time else "%Y-%m-%d"
            output[column] = output[column].dt.strftime(format_string).where(
                output[column].notna(), ""
            )
        elif pd.api.types.is_object_dtype(output[column]):
            output[column] = output[column].map(
                lambda value: (
                    pd.Timestamp(value).isoformat()
                    if isinstance(value, pd.Timestamp)
                    else value
                )
            )
    return output


def deterministic_csv_bytes(data: pd.DataFrame) -> bytes:
    """Serialize a table with round-trip float precision and stable dates."""

    buffer = io.StringIO()
    _portable_frame(data).to_csv(
        buffer,
        index=False,
        float_format="%.17g",
        lineterminator="\n",
    )
    return buffer.getvalue().encode("utf-8")


def deterministic_table_sha256(data: pd.DataFrame) -> str:
    return hashlib.sha256(deterministic_csv_bytes(data)).hexdigest()


def write_deterministic_csv(data: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(deterministic_csv_bytes(data))
    return path


def write_deterministic_json(value: Mapping[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _implementation_provenance(root: Path) -> dict[str, Any]:
    """Identify the latest code commit and checksum the exact runtime bundle."""

    paths = [root / relative for relative in PHASE3_IMPLEMENTATION_PATHS]
    missing = [
        relative
        for relative, path in zip(PHASE3_IMPLEMENTATION_PATHS, paths, strict=True)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Phase 3 implementation bundle is incomplete: " + ", ".join(missing)
        )
    digest = hashlib.sha256()
    for relative, path in zip(PHASE3_IMPLEMENTATION_PATHS, paths, strict=True):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")

    commit = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            *PHASE3_IMPLEMENTATION_PATHS,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not commit:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            *PHASE3_IMPLEMENTATION_PATHS,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "repository_code_commit": commit,
        "implementation_bundle_sha256": digest.hexdigest(),
        "tracked_implementation_files_dirty": bool(dirty),
        "implementation_paths": list(PHASE3_IMPLEMENTATION_PATHS),
    }


class _SyntheticSplineRunner:
    """Deterministic no-TIMESAT runner used only for leakage/determinism gates."""

    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series | pd.DatetimeIndex,
        smoothing: int | None = None,
    ) -> ReconstructionResult:
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates))
        return ReconstructionResult(
            method=method,
            year=year,
            status="ok",
            failure_reason="",
            prediction=pd.DataFrame(
                {
                    "date": targets,
                    "prediction": np.arange(1, len(targets) + 1, dtype=float),
                }
            ),
            diagnostics={"synthetic_preperformance_gate": True},
        )


def _synthetic_selection_checks() -> dict[str, bool]:
    """Exercise selection twice and mutate the excluded outer reference."""

    rows: list[dict[str, Any]] = []
    for year in PRIMARY_YEARS:
        for offset, date in enumerate(pd.date_range(f"{year}-06-01", periods=10)):
            rows.append(
                {
                    "date": date,
                    "year": year,
                    "CHLF": float(offset + 1),
                    "open_water": True,
                    "reference_value_available": True,
                    "common_support": True,
                    "common_support_segment_id": f"{year}_segment_1",
                    "s2_openwater_reference_candidate": offset in {0, 4, 9},
                }
            )
    support = pd.DataFrame(rows)
    first = select_spline_for_all_outer_folds(
        support, runner=_SyntheticSplineRunner()
    )
    second = select_spline_for_all_outer_folds(
        support, runner=_SyntheticSplineRunner()
    )
    deterministic = all(
        deterministic_table_sha256(left) == deterministic_table_sha256(right)
        for left, right in zip(first, second, strict=True)
    )
    selected_grid_only = bool(
        first[0]["selection_status"].eq("ok").all()
        and first[0]["selected_smoothing"].isin(SPLINE_GRID).all()
    )

    baseline = select_spline_for_outer_fold(
        support, outer_test_year=2025, runner=_SyntheticSplineRunner()
    )
    mutated = support.copy()
    mutated.loc[mutated["year"].eq(2025), "CHLF"] = np.linspace(
        -1e12, 1e12, 10
    )
    changed = select_spline_for_outer_fold(
        mutated, outer_test_year=2025, runner=_SyntheticSplineRunner()
    )
    leakage_safe = bool(
        baseline.selected_smoothing == changed.selected_smoothing
        and deterministic_table_sha256(baseline.candidate_summary)
        == deterministic_table_sha256(changed.candidate_summary)
        and deterministic_table_sha256(baseline.candidate_year_results)
        == deterministic_table_sha256(changed.candidate_year_results)
    )
    return {
        "synthetic_spline_selection_deterministic": deterministic,
        "synthetic_spline_selection_grid_only": selected_grid_only,
        "outer_reference_mutation_cannot_change_selection": leakage_safe,
    }


def _invariant_checks(
    *,
    sparse: pd.DataFrame,
    support: pd.DataFrame,
    folds: pd.DataFrame,
    random_masks: pd.DataFrame,
    consecutive_windows: pd.DataFrame,
) -> dict[str, bool]:
    support_summary = build_common_support_summary(support)
    sparse_boundaries = sparse.groupby("year")["date"].agg(["min", "max"])
    boundaries_match = all(
        support_summary.set_index("year").loc[year, "first_sparse_input_date"]
        == sparse_boundaries.loc[year, "min"]
        and support_summary.set_index("year").loc[year, "last_sparse_input_date"]
        == sparse_boundaries.loc[year, "max"]
        for year in PRIMARY_YEARS
    )
    random_protected = bool(
        random_masks["frozen_first_sparse_input_date"].eq(
            random_masks["result_first_sparse_input_date"]
        ).all()
        and random_masks["frozen_last_sparse_input_date"].eq(
            random_masks["result_last_sparse_input_date"]
        ).all()
    )
    consecutive_protected = bool(
        consecutive_windows["frozen_first_sparse_input_date"].eq(
            consecutive_windows["result_first_sparse_input_date"]
        ).all()
        and consecutive_windows["frozen_last_sparse_input_date"].eq(
            consecutive_windows["result_last_sparse_input_date"]
        ).all()
    )
    fold_ok = bool(
        len(folds) == 7
        and folds["n_inner_training_years"].eq(6).all()
        and all(
            str(row.outer_test_year)
            not in row.inner_training_years.split(";")
            for row in folds.itertuples(index=False)
        )
    )
    return {
        "sparse_count_exact": len(sparse) == EXPECTED_SPARSE_DATES,
        "seven_outer_folds_six_training_years": fold_ok,
        "method_independent_support_boundaries": boundaries_match,
        "random_masks_preserve_boundaries": random_protected,
        "consecutive_windows_preserve_boundaries": consecutive_protected,
        "random_masks_have_no_a_gap": "a_gap" not in random_masks.columns,
        "consecutive_windows_have_a_gap": "a_gap" in consecutive_windows.columns,
        "no_performance_columns_generated": not any(
            column in consecutive_windows.columns or column in random_masks.columns
            for column in (
                "bias",
                "mae",
                "rmse",
                "nrmse",
                "peak_date_error",
                "method_rank",
            )
        ),
    }


def build_preperformance_products(
    *,
    repository_root: str | Path,
    temporal_master_path: str | Path,
    timesat_python: str | Path,
    runtime_script: str | Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build and verify all implementation-only gate products in memory."""

    root = Path(repository_root)
    implementation = _implementation_provenance(root)
    contract = load_contract_config(root)
    snapshot_path = root / contract["timesat_defaults_snapshot"]
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    master = read_phase3_master(temporal_master_path)
    sparse = build_sparse_inputs(master)
    support = build_common_support(master)
    support_summary = build_common_support_summary(support)
    folds = folds_to_table(build_outer_folds())
    random_masks = generate_random_deletion_masks(support)
    consecutive_windows = generate_consecutive_gap_windows(support)

    # A second independent in-memory generation is the deterministic rerun gate.
    random_second = generate_random_deletion_masks(support)
    consecutive_second = generate_consecutive_gap_windows(support)
    deterministic_masks = deterministic_table_sha256(
        random_masks
    ) == deterministic_table_sha256(random_second)
    deterministic_windows = deterministic_table_sha256(
        consecutive_windows
    ) == deterministic_table_sha256(consecutive_second)
    selection_checks = _synthetic_selection_checks()

    runner = SubprocessTimesatRunner(
        python_executable=timesat_python,
        runtime_script=runtime_script,
        snapshot_path=snapshot_path,
    )
    runtime = runner.verify_runtime(smoke_test=True)
    invariants = _invariant_checks(
        sparse=sparse,
        support=support,
        folds=folds,
        random_masks=random_masks,
        consecutive_windows=consecutive_windows,
    )
    invariants.update(selection_checks)

    support_export = support.loc[
        support["common_support"],
        [
            "date",
            "year",
            "doy",
            "open_water",
            "reference_value_available",
            "s2_openwater_reference_candidate",
            "first_sparse_input_date",
            "last_sparse_input_date",
            "common_support_segment_id",
        ],
    ].reset_index(drop=True)
    tables = {
        "erken_phase3_sparse_inputs.csv": sparse,
        "erken_phase3_common_support.csv": support_export,
        "erken_phase3_common_support_summary.csv": support_summary,
        "erken_phase3_loyo_folds.csv": folds,
        "erken_phase3_random_deletion_masks.csv": random_masks,
        "erken_phase3_consecutive_gap_windows.csv": consecutive_windows,
    }
    table_hashes = {
        filename: deterministic_table_sha256(table)
        for filename, table in tables.items()
    }
    gates = [
        {
            "gate": "governing_contract_detected",
            "passed": contract["contract_version"] == CONTRACT_VERSION,
            "detail": CONTRACT_VERSION,
        },
        {
            "gate": "observation_join_structural_validation",
            "passed": True,
            "detail": f"{len(master)} unique daily rows",
        },
        {
            "gate": "actual_mask_sparse_dates",
            "passed": len(sparse) == EXPECTED_SPARSE_DATES,
            "detail": str(len(sparse)),
        },
        {
            "gate": "seven_loyo_folds",
            "passed": invariants["seven_outer_folds_six_training_years"],
            "detail": "7 outer folds; 6 inner years each",
        },
        {
            "gate": "common_support_rules",
            "passed": invariants["method_independent_support_boundaries"],
            "detail": "open water inside frozen first/last sparse dates",
        },
        {
            "gate": "timesat_defaults_snapshot",
            "passed": bool(snapshot["snapshot_payload_sha256"]),
            "detail": snapshot["snapshot_payload_sha256"],
        },
        {
            "gate": "timesat_runtime_defaults_match",
            "passed": runtime["runtime_defaults_match_snapshot"],
            "detail": (
                f"timesat={runtime['timesat_core_version']}; "
                f"timesat-cli={runtime['timesat_cli_version']}"
            ),
        },
        {
            "gate": "spline_candidate_grid",
            "passed": contract["spline"]["candidate_grid"] == list(SPLINE_GRID),
            "detail": ";".join(str(value) for value in SPLINE_GRID),
        },
        {
            "gate": "random_mask_reproducibility",
            "passed": deterministic_masks
            and invariants["random_masks_preserve_boundaries"],
            "detail": f"{len(random_masks)} manifests",
        },
        {
            "gate": "consecutive_window_generation",
            "passed": deterministic_windows
            and invariants["consecutive_windows_preserve_boundaries"],
            "detail": f"{len(consecutive_windows)} exhaustive eligible windows",
        },
        {
            "gate": "leakage_prevention_tests",
            "passed": invariants["seven_outer_folds_six_training_years"]
            and invariants["method_independent_support_boundaries"]
            and invariants["outer_reference_mutation_cannot_change_selection"],
            "detail": (
                "outer year excluded; synthetic outer-reference mutation leaves "
                "selection unchanged"
            ),
        },
        {
            "gate": "deterministic_rerun",
            "passed": deterministic_masks
            and deterministic_windows
            and invariants["synthetic_spline_selection_deterministic"],
            "detail": (
                "random, consecutive, and synthetic selected-parameter tables "
                "reproduced"
            ),
        },
    ]
    all_passed = all(bool(item["passed"]) for item in gates) and all(
        invariants.values()
    )
    manifest: dict[str, Any] = {
        "schema_version": "phase3_preperformance_gate_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "scientific_master_version": contract["scientific_master_version"],
        "all_preperformance_gates_passed": all_passed,
        "scientific_reconstruction_performance_generated": False,
        "scientific_reconstruction_performance_inspected": False,
        "implementation_provenance": implementation,
        "timesat": {
            "core_version": runtime["timesat_core_version"],
            "core_source_git_commit": snapshot["timesat_core"][
                "source_git_commit"
            ],
            "core_runtime_binary_filename": runtime[
                "timesat_core_binary_filename"
            ],
            "core_runtime_binary_sha256": runtime["timesat_core_binary_sha256"],
            "cli_version": runtime["timesat_cli_version"],
            "cli_source_git_commit": snapshot["timesat_cli"]["source_git_commit"],
            "defaults_snapshot_payload_sha256": snapshot[
                "snapshot_payload_sha256"
            ],
            "runtime_defaults_match_snapshot": runtime[
                "runtime_defaults_match_snapshot"
            ],
            "synthetic_smoke_test": runtime["smoke_test"],
        },
        "input_provenance": {
            "temporal_master_path": str(
                Path(temporal_master_path).resolve().relative_to(root.resolve())
            ),
            "temporal_master_sha256": sha256_file(temporal_master_path),
            "sparse_input_checksum": sparse_input_checksum(sparse),
            "n_sparse_inputs": len(sparse),
        },
        "table_sha256": table_hashes,
        "invariants": invariants,
        "gates": gates,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest


def write_preperformance_products(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / filename)
        for filename, table in tables.items()
    ]
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase3_preperformance_gate.json"
        )
    )
    return paths
