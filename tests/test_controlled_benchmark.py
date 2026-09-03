from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat.controlled_benchmark import (
    PersistentTimesatRunner,
    _methods_for_scenario,
    _scenario_support,
    canonical_mask_identity,
)
from twinwater_timesat.controlled_gaps import (
    generate_consecutive_gap_windows,
    generate_random_deletion_masks,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.timesat_adapter import ReconstructionResult


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
MASTER = ROOT / "data/processed/erken_temporal_sampling_master.csv"


def _support() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=10)
    return pd.DataFrame(
        {
            "date": dates,
            "year": 2020,
            "CHLF": np.arange(10, dtype=float),
            "common_support": True,
            "reference_value_available": True,
            "common_support_segment_id": "s1",
            "s2_openwater_reference_candidate": True,
        }
    )


def test_scenario_support_deletes_only_named_sparse_dates() -> None:
    scenario = type(
        "Scenario",
        (),
        {"year": 2020, "deleted_dates": "2020-01-03;2020-01-08"},
    )()
    result = _scenario_support(_support(), scenario)
    retained = result.loc[result["s2_openwater_reference_candidate"], "date"]
    assert pd.Timestamp("2020-01-03") not in set(retained)
    assert pd.Timestamp("2020-01-08") not in set(retained)
    assert retained.iloc[0] == pd.Timestamp("2020-01-01")
    assert retained.iloc[-1] == pd.Timestamp("2020-01-10")


class _FakeRunner:
    def reconstruct(self, *, method, year, sparse, target_dates, smoothing=None):
        return ReconstructionResult(
            method,
            year,
            "ok",
            "",
            pd.DataFrame(
                {"date": pd.to_datetime(target_dates), "prediction": 1.0}
            ),
            {"smoothing": smoothing},
        )


def test_all_methods_receive_identical_scenario_sparse_input() -> None:
    results = _methods_for_scenario(_support(), runner=_FakeRunner(), smoothing=100)
    assert set(results) == {
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    }
    assert len(
        {result.diagnostics["sparse_input_checksum"] for result in results.values()}
    ) == 1
    assert all(
        result.diagnostics["identical_sparse_input_enforced"]
        for result in results.values()
    )


def test_controlled_cli_requires_explicit_authorization() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/14_erken_phase4_controlled_gaps.py",
            "--family",
            "random_deletion",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "Refusing controlled-gap performance" in completed.stderr


def test_persistent_transport_runs_frozen_timesat() -> None:
    value = os.environ.get("TIMESAT_PYTHON")
    if not value or not Path(value).is_file():
        pytest.skip("TIMESAT_PYTHON is not set")
    dates = pd.date_range("2020-01-01", periods=25, freq="15D")
    sparse = pd.DataFrame(
        {
            "date": dates,
            "CHLF": 2 + 8 * np.exp(-((dates.dayofyear - 210) / 60) ** 2),
        }
    )
    with PersistentTimesatRunner(
        Path(value), ROOT / "scripts/13_timesat_batch_runtime.py", SNAPSHOT
    ) as runner:
        result = runner.reconstruct(
            method="timesat_smoothing_spline",
            year=2020,
            sparse=sparse,
            target_dates=pd.date_range("2020-01-01", "2020-12-30"),
            smoothing=10,
        )
    assert result.status == "ok"
    assert result.prediction["prediction"].notna().all()
    assert result.diagnostics["persistent_batch_transport"] is True


@pytest.mark.parametrize(
    ("family", "filename", "expected_sha256"),
    [
        (
            "random_deletion",
            "erken_phase3_random_deletion_masks.csv",
            "6f37404c2fc98bc4be58de944154e035b29842cd369607259a8831b060eafb06",
        ),
        (
            "consecutive_internal_gap",
            "erken_phase3_consecutive_gap_windows.csv",
            "74d386692544dca9854ac818b3a723e41a7da907379f857e54f4808007acb58d",
        ),
    ],
)
def test_regenerated_canonical_mask_bytes_equal_raw_file_and_both_manifests(
    family: str, filename: str, expected_sha256: str
) -> None:
    support = build_common_support(read_phase3_master(MASTER))
    regenerated = (
        generate_random_deletion_masks(support)
        if family == "random_deletion"
        else generate_consecutive_gap_windows(support)
    )
    phase3 = json.loads(
        (
            ROOT
            / "results/phase3/preflight/erken_phase3_preperformance_gate.json"
        ).read_text()
    )
    controlled_dir = (
        ROOT / "results/phase4/random_deletion"
        if family == "random_deletion"
        else ROOT / "results/phase4/consecutive_gaps"
    )
    controlled = json.loads(
        (controlled_dir / "erken_phase4_controlled_gap_manifest.json").read_text()
    )
    identity = canonical_mask_identity(
        regenerated,
        frozen_path=ROOT / "results/phase3/preflight" / filename,
        phase3_manifest_sha256=phase3["table_sha256"][filename],
        controlled_manifest_sha256=controlled["mask_manifest_sha256"],
    )
    assert identity["passed"] is True
    assert set(identity.values()) == {True, expected_sha256}
