from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.phase3_benchmark import (
    require_clean_performance_worktree,
    load_passed_preperformance_manifest,
    run_actual_mask_benchmark,
)
from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    PRIMARY_METHODS,
    PRIMARY_YEARS,
    canonical_json_payload_sha256,
)
from twinwater_timesat.reconstruction_benchmark import evaluate_method_result
from twinwater_timesat.timesat_adapter import ReconstructionResult


def _synthetic_support() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
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
                    "common_support_segment_id": 1,
                    "s2_openwater_reference_candidate": offset in {0, 4, 9},
                }
            )
    return pd.DataFrame(rows)


class DeterministicSyntheticRunner:
    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series,
        smoothing: int | None = None,
    ) -> ReconstructionResult:
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates))
        values = np.arange(1, len(targets) + 1, dtype=float)
        return ReconstructionResult(
            method=method,
            year=year,
            status="ok",
            failure_reason="",
            prediction=pd.DataFrame({"date": targets, "prediction": values}),
            diagnostics={"synthetic_test_runner": True},
        )


def test_actual_mask_executor_retains_all_folds_methods_and_provenance() -> None:
    tables = run_actual_mask_benchmark(
        _synthetic_support(),
        runner=DeterministicSyntheticRunner(),
        provenance={"repository_code_commit": "synthetic"},
    )
    selection = tables["erken_phase3_spline_selection.csv"]
    metrics = tables["erken_phase3_actual_mask_year_method_metrics.csv"]
    curves = tables["erken_phase3_actual_mask_daily_reconstructions.csv"]
    assert len(selection) == 7
    assert selection["selected_smoothing"].eq(0).all()
    assert len(metrics) == 21
    assert set(metrics["method"]) == set(PRIMARY_METHODS)
    assert metrics.groupby("outer_test_year")["method"].nunique().eq(3).all()
    assert metrics["repository_code_commit"].eq("synthetic").all()
    assert len(curves) == 210
    assert curves["reconstruction_failure_reason"].eq("").all()

    repeated = run_actual_mask_benchmark(
        _synthetic_support(),
        runner=DeterministicSyntheticRunner(),
        provenance={"repository_code_commit": "synthetic"},
    )
    for name, table in tables.items():
        pd.testing.assert_frame_equal(table, repeated[name])


def test_failed_method_remains_as_explicit_metric_and_residual_rows() -> None:
    support = _synthetic_support().loc[lambda frame: frame["year"].eq(2019)]
    failed = ReconstructionResult(
        method="timesat_double_logistic",
        year=2019,
        status="failed",
        failure_reason="synthetic_nonconvergence",
        prediction=pd.DataFrame(columns=["date", "prediction"]),
        diagnostics={"timesat_failure_code": 99},
    )
    metrics, residuals = evaluate_method_result(support, failed)
    assert metrics["reconstruction_status"] == "failed"
    assert metrics["reconstruction_failure_reason"] == "synthetic_nonconvergence"
    assert metrics["diagnostic_timesat_failure_code"] == 99
    assert metrics["pointwise_metric_reason"] == "reconstruction_failed"
    assert len(residuals) == 7
    assert residuals["residual_status"].eq("reconstruction_failed").all()


def test_benchmark_gate_manifest_is_self_checking(tmp_path) -> None:
    manifest = {
        "schema_version": "phase3_preperformance_gate_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "all_preperformance_gates_passed": True,
        "scientific_reconstruction_performance_generated": False,
        "scientific_reconstruction_performance_inspected": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert load_passed_preperformance_manifest(path)[
        "all_preperformance_gates_passed"
    ] is True
    manifest["all_preperformance_gates_passed"] = False
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        load_passed_preperformance_manifest(path)


def test_benchmark_guard_refuses_a_dirty_git_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    commands = (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Phase 3 test"],
        ["git", "config", "user.email", "phase3-test@example.invalid"],
    )
    for command in commands:
        subprocess.run(command, cwd=repository, check=True, capture_output=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=repository, check=True
    )
    clean = require_clean_performance_worktree(repository)
    assert clean.repository_worktree_dirty is False

    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Git worktree is dirty"):
        require_clean_performance_worktree(repository)
