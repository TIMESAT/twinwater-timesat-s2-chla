from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from twinwater_timesat.s2_acolite import (
    AcoliteConfig,
    AcoliteExtractionError,
    AcoliteProduct,
    decode_l2_flags,
    default_acolite_config_path,
    discover_acolite_products,
    extract_acolite_product,
    load_acolite_config,
    run_acolite_extraction,
    select_flags_asset,
    select_rhos_assets,
    write_acolite_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ID = "S2A_MSIL1C_20190417T102031_N0500_R065_T34VCM_20221023T062324"
OUTPUT_PREFIX = "S2A_MSI_2019_04_17_10_20_31_T34VCM"


@pytest.fixture()
def config() -> AcoliteConfig:
    return load_acolite_config(
        default_acolite_config_path(ROOT), repository_root=ROOT
    )


def _write_geotiff(
    path: Path,
    values: np.ndarray,
    *,
    resolution_m: int,
    dtype: str,
) -> None:
    station = Transformer.from_crs("EPSG:4326", "EPSG:32634", always_xy=True).transform(
        18.625827, 59.84029
    )
    side_m = values.shape[1] * resolution_m
    transform = from_origin(
        station[0] - side_m / 2,
        station[1] + side_m / 2,
        resolution_m,
        resolution_m,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=dtype,
        crs="EPSG:32634",
        transform=transform,
    ) as dataset:
        dataset.write(values.astype(dtype), 1)


def _build_product(
    root: Path,
    *,
    resolution_m: int = 20,
    product_id: str = PRODUCT_ID,
    flag_value: int = 1,
) -> AcoliteProduct:
    product_root = root / product_id
    output = product_root / "acolite"
    output.mkdir(parents=True)
    target_pixels = 11
    native_pixels = target_pixels * (20 // resolution_m)
    values = {
        665: np.full((native_pixels, native_pixels), 0.01),
        704: np.full((native_pixels, native_pixels), 0.02),
        740: np.full((native_pixels, native_pixels), 0.015),
    }
    for wavelength, array in values.items():
        _write_geotiff(
            output / f"{OUTPUT_PREFIX}_L2R_rhos_{wavelength}.tif",
            array,
            resolution_m=resolution_m,
            dtype="float32",
        )
    flags = np.zeros((native_pixels, native_pixels), dtype="uint16")
    centre = native_pixels // 2
    flags[centre, centre] = flag_value
    _write_geotiff(
        output / f"{OUTPUT_PREFIX}_L2W_l2_flags.tif",
        flags,
        resolution_m=resolution_m,
        dtype="uint16",
    )
    (output / "run.json").write_text('{"run": "fixture"}\n', encoding="utf-8")
    (output / "acolite-settings.txt").write_text(
        "l2w_mask=True\n", encoding="utf-8"
    )
    return AcoliteProduct(
        product_id=product_id,
        product_root=product_root,
        output_dir=output,
    )


def _base_row() -> dict[str, object]:
    return {
        "date": "2019-04-17",
        "year": 2019,
        "scl_gate_pass": True,
        "l2a_representative_status": "frozen_representative",
        "l1c_pairing_status": "exact_unique",
        "source_l1c_product_id": PRODUCT_ID,
    }


def _write_pairing_audit(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "year",
        "l2a_representative_status",
        "scl_gate_pass",
        "l2a_product_id",
        "l1c_pairing_status",
        "l1c_product_id",
        "l1c_platform",
        "l1c_sensing_datetime",
        "l1c_tile",
        "l1c_relative_orbit",
        "l1c_processing_baseline",
    ]
    rows = [
        {
            "date": "2019-04-17",
            "year": "2019",
            "l2a_representative_status": "frozen_representative",
            "scl_gate_pass": "True",
            "l2a_product_id": "S2A_MSIL2A_fixture",
            "l1c_pairing_status": "exact_unique",
            "l1c_product_id": PRODUCT_ID,
            "l1c_platform": "S2A",
            "l1c_sensing_datetime": "2019-04-17T10:20:31Z",
            "l1c_tile": "T34VCM",
            "l1c_relative_orbit": "65",
            "l1c_processing_baseline": "N0500",
        },
        {
            "date": "2019-04-19",
            "year": "2019",
            "l2a_representative_status": "no_representative_frozen_scl_gate_failed",
            "scl_gate_pass": "False",
            "l2a_product_id": "",
            "l1c_pairing_status": "no_l2a_representative_for_date",
            "l1c_product_id": "",
        },
        {
            "date": "2019-06-06",
            "year": "2019",
            "l2a_representative_status": "frozen_representative",
            "scl_gate_pass": "True",
            "l2a_product_id": "S2A_MSIL2A_ambiguous",
            "l1c_pairing_status": "ambiguous_multiple_candidates",
            "l1c_product_id": "",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _temp_config(config: AcoliteConfig, repository: Path) -> AcoliteConfig:
    values = copy.deepcopy(config.values)
    values["inputs"]["phase6a_pairing_audit"] = (
        "results/phase6a/erken_l1c_l2a_pairing_audit.csv"
    )
    return AcoliteConfig(
        values=values,
        source_relative_path=config.source_relative_path,
        sha256=config.sha256,
    )


def test_config_freezes_rhos_flags_grid_and_windows(config: AcoliteConfig) -> None:
    assert config.section("inputs")["extraction_scope"] == (
        "all_discovered_acolite_products"
    )
    assert config.section("reflectance")["quantity"] == "rhos"
    assert config.section("grid")["target_resolution_m"] == 20
    assert config.section("spatial_summary")["window_sizes"] == [1, 3, 5, 7, 11]
    assert config.section("spatial_summary")["primary_window_size"] == 3
    assert config.section("qa")["unknown_bits_policy"] == "hard_invalid"


def test_discovery_matches_server_directory_layout(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    _build_product(tmp_path)
    products = discover_acolite_products(tmp_path, config=config)
    assert [product.product_id for product in products] == [PRODUCT_ID]
    assert products[0].output_dir.name == "acolite"


def test_rhos_and_flags_selection_uses_matching_output_prefix(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    product = _build_product(tmp_path)
    selected = select_rhos_assets(product, config=config)
    assert {band: wave for band, (wave, _) in selected.items()} == {
        "B4": 665.0,
        "B5": 704.0,
        "B6": 740.0,
    }
    assert select_flags_asset(
        product, config=config, rhos_asset=selected["B4"][1]
    ).name.endswith("_L2W_l2_flags.tif")


def test_equal_distance_wavelength_tie_is_refused(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    product = _build_product(tmp_path)
    original = product.output_dir / f"{OUTPUT_PREFIX}_L2R_rhos_704.tif"
    duplicate = product.output_dir / f"{OUTPUT_PREFIX}_L2R_rhos_706.tif"
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(AcoliteExtractionError, match="ambiguous_nearest.*B5"):
        select_rhos_assets(product, config=config)


def test_l2_flags_decode_keeps_negative_diagnostic_and_unknown_hard(
    config: AcoliteConfig,
) -> None:
    values = np.array([[0, 1, 8, 128]], dtype="uint16")
    layers, hard, integer = decode_l2_flags(values, config=config)
    assert integer.tolist() == [[0, 1, 8, 128]]
    assert layers["non_water_swir"].tolist() == [[False, True, False, False]]
    assert layers["negative_surface_reflectance"].tolist() == [
        [False, False, True, False]
    ]
    assert layers["unknown_bits"].tolist() == [[False, False, False, True]]
    assert hard.tolist() == [[False, True, False, True]]


@pytest.mark.parametrize("resolution_m", [20, 10])
def test_product_extraction_matches_phase6a_windows_and_indices(
    tmp_path: Path,
    config: AcoliteConfig,
    resolution_m: int,
) -> None:
    product = _build_product(tmp_path, resolution_m=resolution_m)
    outcome = extract_acolite_product(
        product,
        archive_root=tmp_path,
        config=config,
        base_row=_base_row(),
    )
    assert outcome.failure_reason is None
    assert outcome.row["reflectance_quantity"] == "rhos"
    assert outcome.row["native_to_target_reduction_factor"] == 20 // resolution_m
    assert outcome.row["NDCI_valid_pixel_count"] == 8
    assert outcome.row["NDCI_median"] == pytest.approx(1 / 3)
    assert outcome.row["MCI_valid_pixel_count"] == 8
    assert outcome.row["qa_acolite_non_water_swir_count"] == 1
    assert [row["window_size"] for row in outcome.window_rows] == [1, 3, 5, 7, 11]
    assert outcome.window_rows[0]["NDCI_valid_pixel_count"] == 0
    assert outcome.window_rows[-1]["NDCI_valid_pixel_count"] == 120


def test_negative_rhos_is_retained_but_diagnosed(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    product = _build_product(tmp_path, flag_value=8)
    outcome = extract_acolite_product(
        product,
        archive_root=tmp_path,
        config=config,
        base_row=_base_row(),
    )
    assert outcome.failure_reason is None
    assert outcome.row["qa_acolite_negative_surface_reflectance_count"] == 1
    assert outcome.row["qa_acolite_hard_invalid_count"] == 0
    assert outcome.row["NDCI_valid_pixel_count"] == 9


def test_custom_flag_exponent_mismatch_is_refused(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    product = _build_product(tmp_path)
    (product.output_dir / "acolite-settings.txt").write_text(
        "flag_exponent_swir=7\n", encoding="utf-8"
    )
    outcome = extract_acolite_product(
        product,
        archive_root=tmp_path,
        config=config,
        base_row=_base_row(),
    )
    assert "flag_exponent_swir=7 differs" in str(outcome.failure_reason)


def test_full_run_extracts_products_and_retains_phase6a_alignment(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    repository = tmp_path / "repository"
    archive = tmp_path / "ACOLITE_ERKEN"
    _build_product(archive)
    pairing = repository / "results/phase6a/erken_l1c_l2a_pairing_audit.csv"
    _write_pairing_audit(pairing)
    test_config = _temp_config(config, repository)

    result = run_acolite_extraction(
        config=test_config,
        repository_root=repository,
        acolite_root=archive,
    )
    assert result.counts == {
        "phase6a_candidate_dates": 3,
        "phase6a_frozen_representative_l2a_dates": 2,
        "phase6a_exact_l1c_pairs": 1,
        "acolite_product_directories_discovered": 1,
        "eligible_acolite_products_found": 1,
        "successful_primary_extractions": 1,
        "extraction_rows": 1,
        "date_observation_rows": 1,
        "spatial_sensitivity_rows": 5,
        "failure_rows": 0,
    }
    statuses = {
        row["acolite_phase6a_alignment_status"]
        for row in result.phase6a_alignment_rows
    }
    assert "not_eligible_no_frozen_l2a_representative" in statuses
    assert "not_eligible_l1c_pairing_ambiguous_multiple_candidates" in statuses
    assert "eligible_exact_l1c_product_found" in statuses

    output_root = repository / "results/phase6b/acolite"
    written = write_acolite_outputs(
        result,
        config=test_config,
        repository_root=repository,
        output_root=output_root,
    )
    assert set(written) == {
        "inventory",
        "phase6a_alignment_audit",
        "extraction_master",
        "date_observation_master",
        "product_window_indices",
        "attrition_table",
        "failure_audit",
        "provenance_manifest",
    }
    manifest = json.loads(written["provenance_manifest"].read_text(encoding="utf-8"))
    assert manifest["chlf_inspected"] is False
    assert manifest["processor_performance_generated"] is False
    for path in written.values():
        assert path.is_relative_to(output_root)
        assert str(archive) not in path.read_text(encoding="utf-8")


def test_product_outside_phase6a_interval_is_still_extracted(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    repository = tmp_path / "repository"
    archive = tmp_path / "ACOLITE_ERKEN"
    product_id = "S2A_MSIL1C_20170114T101351_N0500_R022_T34VCM_20230918T102847"
    _build_product(archive, product_id=product_id)
    pairing = repository / "results/phase6a/erken_l1c_l2a_pairing_audit.csv"
    _write_pairing_audit(pairing)
    result = run_acolite_extraction(
        config=_temp_config(config, repository),
        repository_root=repository,
        acolite_root=archive,
    )
    assert len(result.extraction_rows) == 1
    row = result.extraction_rows[0]
    assert row["date"] == "2017-01-14"
    assert row["phase6a_date_in_pairing_audit"] is False
    assert row["phase6a_subset_status"] == "outside_phase6a_pairing_audit"
    assert row["NDCI_median"] == pytest.approx(1 / 3)


def test_output_outside_phase6b_acolite_is_refused(
    tmp_path: Path, config: AcoliteConfig
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "ACOLITE_ERKEN"
    archive.mkdir()
    pairing = repository / "results/phase6a/erken_l1c_l2a_pairing_audit.csv"
    _write_pairing_audit(pairing)
    test_config = _temp_config(config, repository)
    with pytest.raises(AcoliteExtractionError, match="must remain under"):
        write_acolite_outputs(
            run_acolite_extraction(
                config=test_config,
                repository_root=repository,
                acolite_root=archive,
            ),
            config=test_config,
            repository_root=repository,
            output_root=repository / "results/elsewhere",
        )


def test_cli_help_and_no_archive_stop() -> None:
    script = ROOT / "scripts/27_erken_phase6b_acolite_extraction.py"
    help_result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "already-generated Erken ACOLITE" in help_result.stdout
    stop_result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={key: value for key, value in __import__("os").environ.items() if key != "ERKEN_ACOLITE_ROOT"},
    )
    assert "STOP:" in stop_result.stdout
    assert "No output was written" in stop_result.stdout
