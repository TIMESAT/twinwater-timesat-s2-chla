from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.phase3_preflight import (
    deterministic_csv_bytes,
    deterministic_table_sha256,
)
from twinwater_timesat.phase3_contract import canonical_json_payload_sha256
from twinwater_timesat.reconstruction_benchmark import (
    reconstruct_all_methods_for_year,
)
from twinwater_timesat.timesat_adapter import (
    ReconstructionResult,
    SubprocessTimesatRunner,
    linear_reconstruct,
)


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "config" / "timesat_double_logistic_defaults_v4.4.1.json"
RUNTIME_SCRIPT = ROOT / "scripts" / "07_timesat_runtime.py"


def test_linear_interpolation_is_fixed_and_has_no_extrapolation() -> None:
    sparse = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-03"]),
            "CHLF": [1.0, 5.0],
        }
    )
    result = linear_reconstruct(
        year=2020,
        sparse=sparse,
        target_dates=pd.date_range("2020-01-01", "2020-01-03"),
    )
    assert result.status == "ok"
    assert result.prediction["prediction"].tolist() == [1.0, 3.0, 5.0]
    outside = linear_reconstruct(
        year=2020,
        sparse=sparse,
        target_dates=pd.date_range("2019-12-31", "2020-01-03"),
    )
    assert outside.status == "failed"
    assert outside.failure_reason == "target_dates_outside_sparse_boundaries"


class RecordingTimesatRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series,
        smoothing: int | None = None,
    ) -> ReconstructionResult:
        signature = ";".join(
            f"{date.strftime('%Y-%m-%d')}={float(value).hex()}"
            for date, value in zip(
                pd.to_datetime(sparse["date"]), sparse["CHLF"].astype(float)
            )
        )
        self.calls.append((method, signature))
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates))
        return ReconstructionResult(
            method,
            year,
            "ok",
            "",
            pd.DataFrame(
                {"date": targets, "prediction": np.linspace(1, 2, len(targets))}
            ),
            {},
        )


def test_all_three_methods_receive_identical_sparse_dates_and_values() -> None:
    dates = pd.date_range("2020-01-01", periods=5)
    support = pd.DataFrame(
        {
            "date": dates,
            "year": 2020,
            "CHLF": [1, 2, 3, 4, 5],
            "common_support": True,
            "s2_openwater_reference_candidate": [True, False, True, False, True],
        }
    )
    runner = RecordingTimesatRunner()
    results = reconstruct_all_methods_for_year(
        support, selected_smoothing=10, timesat_runner=runner
    )
    assert set(results) == {
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    }
    assert runner.calls[0][1] == runner.calls[1][1]
    checksums = {
        result.diagnostics["sparse_input_checksum"] for result in results.values()
    }
    assert len(checksums) == 1


def test_complete_daily_reference_cannot_change_timesat_sparse_request() -> None:
    dates = pd.date_range("2020-01-01", periods=5)
    support = pd.DataFrame(
        {
            "date": dates,
            "year": 2020,
            "CHLF": [1.0, 200.0, 3.0, -100.0, 5.0],
            "common_support": True,
            "s2_openwater_reference_candidate": [True, False, True, False, True],
        }
    )
    first = RecordingTimesatRunner()
    reconstruct_all_methods_for_year(
        support, selected_smoothing=10, timesat_runner=first
    )
    mutated = support.copy()
    mutated.loc[~mutated["s2_openwater_reference_candidate"], "CHLF"] = [9e8, -9e8]
    second = RecordingTimesatRunner()
    reconstruct_all_methods_for_year(
        mutated, selected_smoothing=10, timesat_runner=second
    )
    assert first.calls == second.calls


def test_deterministic_csv_preserves_float64_and_dates() -> None:
    table = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "value": [np.nextafter(1.0, 2.0), np.pi],
        }
    )
    first = deterministic_csv_bytes(table)
    second = deterministic_csv_bytes(table)
    assert first == second
    assert deterministic_table_sha256(table) == deterministic_table_sha256(table.copy())
    loaded = pd.read_csv(io.BytesIO(first))
    assert np.array_equal(loaded["value"].to_numpy(), table["value"].to_numpy())


def test_phase3_cli_help_is_explicitly_preperformance() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/08_erken_phase3_preflight.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "No Erken reconstruction performance is run" in completed.stdout
    assert "--timesat-python" in completed.stdout
    assert "--no-write" in completed.stdout


def test_benchmark_cli_requires_explicit_performance_authorization() -> None:
    help_result = subprocess.run(
        [sys.executable, "scripts/09_erken_phase3_benchmark.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--execute-performance" in help_result.stdout
    refused = subprocess.run(
        [sys.executable, "scripts/09_erken_phase3_benchmark.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "Refusing to generate scientific reconstruction performance" in (
        refused.stdout + refused.stderr
    )


def _external_timesat_python() -> Path:
    value = os.environ.get("TIMESAT_PYTHON")
    if not value:
        pytest.skip("TIMESAT_PYTHON is not set for external integration tests.")
    path = Path(value)
    if not path.is_file():
        pytest.skip(f"TIMESAT_PYTHON does not exist: {path}")
    return path


def test_external_frozen_timesat_runtime_and_both_algorithms() -> None:
    runner = SubprocessTimesatRunner(
        python_executable=_external_timesat_python(),
        runtime_script=RUNTIME_SCRIPT,
        snapshot_path=SNAPSHOT,
    )
    probe = runner.verify_runtime(smoke_test=True)
    assert probe["runtime_defaults_match_snapshot"] is True
    assert probe["timesat_core_version"] == "4.4.1"
    assert probe["timesat_cli_version"] == "1.9.2"
    assert probe["smoke_test"]["passed"] is True


def test_external_runtime_default_mismatch_fails_loudly(tmp_path: Path) -> None:
    changed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    changed["effective_runtime_parameters"]["p_davailwin"] = 44
    changed["snapshot_payload_sha256"] = canonical_json_payload_sha256(
        changed, excluded_keys=("snapshot_payload_sha256",)
    )
    changed_path = tmp_path / "changed_defaults.json"
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    runner = SubprocessTimesatRunner(
        python_executable=_external_timesat_python(),
        runtime_script=RUNTIME_SCRIPT,
        snapshot_path=changed_path,
    )
    with pytest.raises(RuntimeError, match="effective_runtime_parameters"):
        runner.verify_runtime(smoke_test=False)


def test_external_full_preperformance_cli_gate() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/08_erken_phase3_preflight.py",
            "--timesat-python",
            str(_external_timesat_python()),
            "--no-write",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "pre-performance gates passed: True" in completed.stdout
    assert "Scientific reconstruction performance generated: False" in completed.stdout
