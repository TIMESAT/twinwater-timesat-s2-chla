from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from twinwater_timesat.s2_processing_baseline import (
    ProcessingBaselineError,
    build_acquisition_inventory,
    build_observation_audit,
    default_config_path,
    generation_context,
    load_processing_baseline_config,
    official_product_context,
    parse_product_identity,
    run_processing_baseline_audit,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def config():
    return load_processing_baseline_config(
        default_config_path(ROOT), repository_root=ROOT
    )


def _product_id(
    level: str,
    *,
    sensing: str = "20200102T102031",
    baseline: str = "N0500",
    generation: str = "20230901T120000",
) -> str:
    return (
        f"S2A_MSI{level}_{sensing}_{baseline}_R065_T34VCM_{generation}"
    )


def _selection_row(method: str, product_id: str) -> dict[str, str]:
    return {
        "date": "2020-01-02",
        "year": "2020",
        "observation_method": method,
        "product_level": {"L1C": "L1C", "L2A": "L2A", "ACOLITE": "L2R"}[
            method
        ],
        "source_product_id": product_id,
        "method_product_available": "True",
        "exact_three_method_source_alignment": "True",
        "source_failure_reason": "",
        "ndci_observation_eligible": "True",
        "mci_observation_eligible": "True",
        "common_b456_observation_eligible": "True",
    }


def _reflectance_row(product_id: str, level: str) -> dict[str, str]:
    identity = parse_product_identity(product_id)
    row = {
        "window_size": "3",
        "product_id": product_id,
        "product_level": level,
        "processing_baseline": identity.processing_baseline,
        "sensing_datetime": identity.sensing_datetime,
        "generation_time": identity.generation_time,
        "radiometry_processing_baseline": identity.processing_baseline,
        "radiometry_offset_expected_for_baseline": "True",
    }
    for index, band in enumerate(("B4", "B5", "B6"), start=1):
        row.update(
            {
                f"{band}_offset_source": "product_offset_list",
                f"{band}_add_offset": "-1000",
                f"{band}_conversion_rule": "(DN + -1000) / 10000",
                f"{band}_reflectance_valid_pixel_count": "9",
                f"{band}_reflectance_valid_pixel_fraction": "1",
                f"{band}_reflectance_median": str(index / 100),
                f"{band}_reflectance_mean": str(index / 100),
                f"{band}_reflectance_SD": "0.001",
                f"{band}_reflectance_IQR": "0.001",
                f"{band}_reflectance_min": str(index / 100 - 0.001),
                f"{band}_reflectance_max": str(index / 100 + 0.001),
            }
        )
    return row


def _acolite_row(product_id: str) -> dict[str, str]:
    identity = parse_product_identity(product_id)
    row = {
        "window_size": "3",
        "source_l1c_product_id": product_id,
        "processing_baseline": identity.processing_baseline,
        "sensing_datetime": identity.sensing_datetime,
        "generation_time": identity.generation_time,
    }
    for index, band in enumerate(("B4", "B5", "B6"), start=1):
        row.update(
            {
                f"{band}_geotiff_scale": "1",
                f"{band}_geotiff_offset": "0",
                f"{band}_reflectance_valid_pixel_count": "9",
                f"{band}_reflectance_valid_pixel_fraction": "1",
                f"{band}_reflectance_median": str(index / 100),
                f"{band}_reflectance_mean": str(index / 100),
                f"{band}_reflectance_SD": "0.001",
                f"{band}_reflectance_IQR": "0.001",
                f"{band}_reflectance_min": str(index / 100 - 0.001),
                f"{band}_reflectance_max": str(index / 100 + 0.001),
            }
        )
    return row


def test_config_freezes_baseline_as_measurement_factor(config) -> None:
    assert config.values["processing_baseline"][
        "exact_l1c_l2a_pair_must_share_baseline"
    ] is True
    assert config.values["harmonization_gate"][
        "same_acquisition_cross_baseline_pairs_required"
    ] is True
    assert config.values["harmonization_gate"][
        "response_or_chlf_may_define_correction"
    ] is False
    assert config.values["scientific_guards"]["phase6c_outputs_must_remain_byte_identical"] is True


def test_product_identity_and_generation_context_are_independent(config) -> None:
    identity = parse_product_identity(_product_id("L1C"))
    assert identity.processing_baseline == "N0500"
    assert identity.acquisition_identity == (
        "S2A|2020-01-02T10:20:31Z|R065|T34VCM"
    )
    assert generation_context(2.0, config) == "near_sensing_generation"
    assert generation_context(1000.0, config) == "delayed_generation"


def test_official_product_context_uses_baseline_and_generation(config) -> None:
    assert official_product_context(
        processing_baseline="N0500",
        sensing_datetime="2020-01-02T10:20:31Z",
        generation_context_label="delayed_generation",
        config=config,
    ) == "collection1_historical_reprocessed"
    assert official_product_context(
        processing_baseline="N0510",
        sensing_datetime="2024-04-01T10:20:31Z",
        generation_context_label="near_sensing_generation",
        config=config,
    ) == "nominal_operational"


def test_inventory_distinguishes_same_and_cross_baseline_duplicates(config) -> None:
    same_acquisition = "20200102T102031"
    rows = [
        {
            "source_l1c_product_id": _product_id(
                "L1C",
                sensing=same_acquisition,
                baseline="N0500",
                generation="20230901T120000",
            ),
            "phase6a_exact_pair_eligible": "True",
            "rhos_geotiff_count": "3",
        },
        {
            "source_l1c_product_id": _product_id(
                "L1C",
                sensing=same_acquisition,
                baseline="N0510",
                generation="20230902T120000",
            ),
            "phase6a_exact_pair_eligible": "True",
            "rhos_geotiff_count": "3",
        },
    ]
    inventory = build_acquisition_inventory(rows, config)
    assert all(row["acquisition_distinct_baseline_count"] == 2 for row in inventory)
    assert all(row["acquisition_duplicate_status"] == "cross_baseline_duplicate" for row in inventory)


def test_observation_audit_retains_band_reflectance_and_offset_status(config) -> None:
    l1c = _product_id("L1C")
    l2a = _product_id("L2A")
    selection = [
        _selection_row("L1C", l1c),
        _selection_row("L2A", l2a),
        _selection_row("ACOLITE", l1c),
    ]
    audit = build_observation_audit(
        selection,
        [_reflectance_row(l1c, "L1C"), _reflectance_row(l2a, "L2A")],
        [_acolite_row(l1c)],
        config,
    )
    assert len(audit) == 3
    assert {row["processing_baseline"] for row in audit} == {"N0500"}
    assert all(
        row["l1c_l2a_baseline_pair_status"]
        == "exact_pair_same_processing_baseline"
        for row in audit
    )
    l1c_row = next(row for row in audit if row["observation_method"] == "L1C")
    assert l1c_row["B4_reflectance_median"] == pytest.approx(0.01)
    assert l1c_row["radiometric_conversion_status"] == (
        "metadata_derived_offset_and_quantification_applied"
    )
    assert all(
        row["empirical_cross_baseline_correction_applied"] is False
        for row in audit
    )


def test_exact_l1c_l2a_baseline_mismatch_fails(config) -> None:
    l1c = _product_id("L1C", baseline="N0500")
    l2a = _product_id("L2A", baseline="N0510")
    selection = [
        _selection_row("L1C", l1c),
        _selection_row("L2A", l2a),
        _selection_row("ACOLITE", l1c),
    ]
    with pytest.raises(ProcessingBaselineError, match="baseline mismatch"):
        build_observation_audit(
            selection,
            [_reflectance_row(l1c, "L1C"), _reflectance_row(l2a, "L2A")],
            [_acolite_row(l1c)],
            config,
        )


def test_real_committed_inputs_hold_empirical_harmonization(config) -> None:
    result = run_processing_baseline_audit(config=config, repository_root=ROOT)
    assert result.counts["observation_rows"] == 2778
    assert result.counts["exact_three_method_alignment_dates"] == 306
    assert result.counts["inventory_products"] == 1358
    assert result.counts["same_baseline_duplicate_acquisition_identities"] == 1
    assert result.counts["cross_baseline_duplicate_acquisition_identities"] == 0
    assert result.counts["l1c_l2a_metadata_radiometry_verified_products"] == 613
    assert result.gate_status == "HOLD_EMPIRICAL_HARMONIZATION_NOT_IDENTIFIABLE"
    assert result.phase6c_hash_check["all_outputs_unchanged"] is True


def test_cli_help_states_harmonization_boundary() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/30_erken_phase6d_processing_baseline_audit.py",
            "--help",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "processing baselines" in completed.stdout
    assert "refuses an empirical" in completed.stdout
    assert "Does not read" in completed.stdout
    assert "CHLF" in completed.stdout
