from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from twinwater_timesat.s2_roi import (
    WINDOW_SIZES,
    build_analysis_tables,
    read_and_validate_diagnostics,
    write_analysis_tables,
)


ROOT = Path(__file__).resolve().parents[1]


def make_diagnostics() -> tuple[pd.DataFrame, pd.DataFrame]:
    products = [
        {
            "product_id": "product_water",
            "platform": "S2A",
            "acquisition_datetime": "2020-06-01T10:00:00Z",
            "acquisition_date": "2020-06-01",
            "tile_id": "T34VCM",
            "processing_baseline": "N0500",
            "scl_raster_relative_path": "water.tif",
            "scl_candidate_count": 2,
            "scl_found": True,
            "processing_status": "ok",
            "processing_note": "",
        },
        {
            "product_id": "product_cloud",
            "platform": "S2B",
            "acquisition_datetime": "2020-06-02T10:00:00Z",
            "acquisition_date": "2020-06-02",
            "tile_id": "T34VCM",
            "processing_baseline": "N0510",
            "scl_raster_relative_path": "cloud.tif",
            "scl_candidate_count": 2,
            "scl_found": True,
            "processing_status": "ok",
            "processing_note": "",
        },
    ]
    scene_rows = []
    for product in products:
        water = product["product_id"] == "product_water"
        for window_size in WINDOW_SIZES:
            pixel_count = window_size**2
            row = {
                **{
                    key: product[key]
                    for key in (
                        "product_id",
                        "platform",
                        "acquisition_datetime",
                        "acquisition_date",
                        "tile_id",
                        "processing_baseline",
                    )
                },
                "scl_crs": "EPSG:32634",
                "raster_transform_a": 20.0,
                "raster_transform_b": 0.0,
                "raster_transform_c": 300000.0,
                "raster_transform_d": 0.0,
                "raster_transform_e": -20.0,
                "raster_transform_f": 6700020.0,
                "pixel_size_x": 20.0,
                "pixel_size_y": 20.0,
                "raster_width": 5490,
                "raster_height": 5490,
                "station_lat": 59.84029,
                "station_lon": 18.625827,
                "station_crs": "EPSG:4326",
                "station_x": 367000.0,
                "station_y": 6636000.0,
                "central_row": 3200,
                "central_col": 3347,
                "station_inside_raster": True,
                "central_scl": 6 if water else 9,
                "window_size": window_size,
                "requested_pixel_count": pixel_count,
                "actual_pixel_count": pixel_count,
                "window_complete": True,
                "unexpected_scl_count": 0,
                "water_fraction": 1.0 if water else 0.0,
                "bad_scl_fraction": 0.0 if water else 1.0,
                "processing_status": "ok",
            }
            for code in range(12):
                count = pixel_count if code == (6 if water else 9) else 0
                row[f"scl_{code}_count"] = count
                row[f"scl_{code}_fraction"] = count / pixel_count
            scene_rows.append(row)
    return pd.DataFrame(products), pd.DataFrame(scene_rows)


def write_inputs(
    tmp_path: Path, inventory: pd.DataFrame, scenes: pd.DataFrame
) -> tuple[Path, Path]:
    inventory_path = tmp_path / "inventory.csv"
    scene_path = tmp_path / "scenes.csv"
    inventory.to_csv(inventory_path, index=False)
    scenes.to_csv(scene_path, index=False)
    return inventory_path, scene_path


def test_realistic_inputs_produce_expected_window_and_frequency_summaries(
    tmp_path: Path,
) -> None:
    inventory, scenes = make_diagnostics()
    inventory_path, scene_path = write_inputs(tmp_path, inventory, scenes)
    loaded_inventory, loaded_scenes = read_and_validate_diagnostics(
        inventory_path, scene_path
    )
    tables, primary = build_analysis_tables(
        loaded_inventory,
        loaded_scenes,
        reference_start="2019-04-17",
        reference_end="2025-11-30",
    )

    summary = tables["erken_s2_scl_window_summary.csv"]
    assert summary["window_size"].tolist() == list(WINDOW_SIZES)
    assert summary["n_scenes"].eq(2).all()
    assert summary["water_fraction_median"].eq(0.5).all()
    assert summary["fraction_water_ge_0_95"].eq(0.5).all()
    assert summary["fraction_water_eq_1_00"].eq(0.5).all()
    assert summary["fraction_any_bad_scl"].eq(0.5).all()
    assert summary["fraction_dominated_by_nonwater"].eq(0.5).all()
    assert summary["fraction_any_persistent_nonwater"].eq(0).all()
    assert len(primary) == 10

    frequency = tables["erken_s2_scl_central_pixel_class_frequency.csv"].set_index(
        "scl_code"
    )
    assert frequency.loc[6, "fraction"] == pytest.approx(0.5)
    assert frequency.loc[9, "fraction"] == pytest.approx(0.5)
    assert frequency.drop(index=[6, 9])["count"].eq(0).all()


def test_table_writes_are_deterministic(tmp_path: Path) -> None:
    inventory, scenes = make_diagnostics()
    inventory_path, scene_path = write_inputs(tmp_path, inventory, scenes)
    loaded_inventory, loaded_scenes = read_and_validate_diagnostics(
        inventory_path, scene_path
    )
    tables, _ = build_analysis_tables(
        loaded_inventory,
        loaded_scenes,
        reference_start="2019-04-17",
        reference_end="2025-11-30",
    )
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_paths = write_analysis_tables(tables, first_directory)
    write_analysis_tables(tables, second_directory)

    for first_path in first_paths:
        assert first_path.read_bytes() == (second_directory / first_path.name).read_bytes()


def test_validation_rejects_missing_candidate_window(tmp_path: Path) -> None:
    inventory, scenes = make_diagnostics()
    scenes = scenes.loc[
        ~(
            scenes["product_id"].eq("product_water")
            & scenes["window_size"].eq(11)
        )
    ]
    inventory_path, scene_path = write_inputs(tmp_path, inventory, scenes)

    with pytest.raises(ValueError, match="exactly one row for each candidate window"):
        read_and_validate_diagnostics(inventory_path, scene_path)


def test_roi_analysis_cli_help() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/04_erken_s2_scl_roi_analysis.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "final water/bad-SCL usability" in completed.stdout
    assert "--reference-start" in completed.stdout
