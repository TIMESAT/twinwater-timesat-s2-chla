"""Phase 6A scope guards: Vomb protection, frozen namespaces, portability."""

from __future__ import annotations

from pathlib import Path

import pytest

from twinwater_timesat.s2_pilot_config import (
    PilotConfigError,
    PilotScopeError,
    assert_no_prohibited_processor,
    assert_no_prohibited_site,
    assert_output_path_allowed,
    assert_permitted_product_level,
    assert_portable_rows,
    assert_portable_value,
    default_pilot_config_path,
    load_pilot_config,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def config():
    return load_pilot_config(default_pilot_config_path(ROOT), repository_root=ROOT)


def test_draft_config_loads_and_reports_its_own_identity(config):
    assert config.pilot_version == "erken_real_s2_l1c_l2a_observation_pilot_v1.0"
    assert config.status == "DRAFT_PENDING_HUMAN_FREEZE"
    assert config.source_relative_path.startswith("config/")
    assert len(config.sha256) == 64


def test_config_rejects_unknown_schema_version(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: something_else\n", encoding="utf-8")
    with pytest.raises(PilotConfigError, match="schema_version"):
        load_pilot_config(path)


@pytest.mark.parametrize(
    "value",
    [
        "/archive/Vombsjon/L2A",
        "results/phase6a/vomb_summary.csv",
        "S2A_MSIL2A_20190417T102031_N0500_R065_T33VWF_vombsjön.SAFE",
    ],
)
def test_prohibited_site_access_is_refused(config, value):
    with pytest.raises(PilotScopeError, match="Lake Erken"):
        assert_no_prohibited_site(value, config)


def test_erken_paths_are_accepted(config):
    assert_no_prohibited_site("/archive/Erken/L1C", config)


@pytest.mark.parametrize("level", ["L1C", "L2A", "l1c"])
def test_permitted_product_levels(config, level):
    assert_permitted_product_level(level, config)


@pytest.mark.parametrize("level", ["ACOLITE", "L2R", "POLYMER"])
def test_out_of_scope_product_levels_are_refused(config, level):
    with pytest.raises(PilotScopeError):
        assert_permitted_product_level(level, config)


@pytest.mark.parametrize(
    "value", ["run_acolite.py", "C2RCC output", "oc-smart_l2", "POLYMER_v4"]
)
def test_atmospheric_correction_processors_are_refused(config, value):
    with pytest.raises(PilotScopeError, match="s2-inlandwater-ac"):
        assert_no_prohibited_processor(value, config)


@pytest.mark.parametrize(
    "path",
    [
        "results/phase3/anything.csv",
        "results/phase4/anything.csv",
        "results/phase5/anything.csv",
        "results/tables/erken_s2_scl_product_qc.csv",
        "data/processed/erken_s2_observation_mask.csv",
        "config/erken_s2_observation_mask.yaml",
        "docs/decisions.md",
    ],
)
def test_writes_into_frozen_namespaces_are_refused(config, path):
    with pytest.raises(PilotScopeError):
        assert_output_path_allowed(path, config, repository_root=ROOT)


def test_only_phase6a_namespace_is_writable(config):
    resolved = assert_output_path_allowed(
        "results/phase6a/qa/x.csv", config, repository_root=ROOT
    )
    assert resolved.is_relative_to(ROOT / "results" / "phase6a")


def test_paths_escaping_the_repository_are_refused(config):
    with pytest.raises(PilotScopeError):
        assert_output_path_allowed(
            "results/phase6a/../../elsewhere.csv", config, repository_root=ROOT
        )


def test_absolute_machine_paths_are_refused_in_outputs():
    with pytest.raises(PilotScopeError, match="runtime inputs"):
        assert_portable_value("/Users/someone/archive/L1C")
    with pytest.raises(PilotScopeError):
        assert_portable_rows([{"path": "/home/someone/archive/L2A"}])


def test_portable_rows_accept_product_relative_paths():
    assert_portable_rows(
        [{"path": "GRANULE/L2A_T34VCM/IMG_DATA/R20m/B04_20m.jp2", "value": None}]
    )
