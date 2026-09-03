from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from twinwater_timesat.seapar_sensitivity import (
    CLASSIFICATION,
    PARENT_OUTPUT_DIRECTORIES,
    PROTOCOL_VERSION,
    SEAPAR_GRID,
    load_seapar_sensitivity_config,
    parent_output_inventory,
)
from twinwater_timesat.timesat_adapter import (
    SubprocessTimesatRunner,
    _validated_p_seapar,
)


ROOT = Path(__file__).resolve().parents[1]


def test_sensitivity_config_freezes_exact_scientific_rules() -> None:
    config = load_seapar_sensitivity_config(ROOT)
    assert config["protocol_version"] == PROTOCOL_VERSION
    assert config["analysis_classification"] == CLASSIFICATION
    assert tuple(config["timesat"]["candidate_grid"]) == SEAPAR_GRID
    assert config["selection"]["year_weighting"] == "equal"
    assert config["selection"]["exact_stored_precision_tie_rule"] == (
        "larger_p_seapar"
    )
    assert config["event_metrics_never_used_for_tuning"] is True
    assert config["original_outputs_remain_untouched"] is True
    assert config["vombsjon_forbidden"] is True


def test_candidate_validation_never_rounds_or_clips() -> None:
    for candidate in SEAPAR_GRID:
        assert _validated_p_seapar(candidate).hex() == float(candidate).hex()
    for invalid in (-0.1, 1.1, np.nan, True, "0.5"):
        with pytest.raises(ValueError):
            _validated_p_seapar(invalid)


def test_parent_inventory_uses_only_explicit_erken_directories() -> None:
    assert PARENT_OUTPUT_DIRECTORIES
    assert all("vomb" not in path.lower() for path in PARENT_OUTPUT_DIRECTORIES)
    inventory = parent_output_inventory(ROOT)
    assert inventory
    assert all("vomb" not in path.lower() for path in inventory)
    assert (
        "results/phase3/actual_mask/"
        "erken_phase3_actual_mask_daily_reconstructions.csv"
    ) in inventory


@pytest.mark.skipif(
    not os.environ.get("TIMESAT_PYTHON"),
    reason="TIMESAT_PYTHON is not set for p_seapar runtime integration.",
)
def test_frozen_runtime_accepts_exact_candidate_grid() -> None:
    runner = SubprocessTimesatRunner(
        python_executable=os.environ["TIMESAT_PYTHON"],
        runtime_script=ROOT / "scripts/07_timesat_runtime.py",
        snapshot_path=(
            ROOT / "config/timesat_double_logistic_defaults_v4.4.1.json"
        ),
    )
    result = runner.verify_seapar_grid(SEAPAR_GRID)
    assert result["candidate_grid_accepted"] is True
    assert [item["requested_p_seapar"] for item in result["candidate_checks"]] == list(
        SEAPAR_GRID
    )
    assert all(
        item["effective_equals_requested"]
        and item["reconstruction_status"] == "ok"
        for item in result["candidate_checks"]
    )
