from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from pyproj import Transformer

from twinwater_timesat.s2_scl import (
    DEFAULT_BAD_SCL_CLASSES,
    INVENTORY_COLUMNS,
    SCENE_SUMMARY_COLUMNS,
    discover_l2a_products,
    extract_centered_window,
    find_scl_raster,
    parse_product_metadata,
    station_to_pixel,
    summarize_archive,
    summarize_scene,
    summarize_scl_classes,
    transform_station_coordinate,
    write_inventory_summary,
    write_scene_summary,
)


STATION_LAT = 59.84029
STATION_LON = 18.625827
STATION_CRS = "EPSG:4326"
RASTER_CRS = "EPSG:32634"
WINDOW_SIZES = [1, 3, 5, 7, 11]
PRODUCT_NAME = "S2A_MSIL2A_20240101T101021_N0510_R022_T34VCL_20240101T120000.SAFE"


def projected_station() -> tuple[float, float]:
    return Transformer.from_crs(
        STATION_CRS, RASTER_CRS, always_xy=True
    ).transform(STATION_LON, STATION_LAT)


def make_synthetic_safe(
    root: Path,
    *,
    product_name: str = PRODUCT_NAME,
    width: int = 15,
    height: int = 15,
    station_row: int = 7,
    station_col: int = 7,
    shift_x: float = 0.0,
    shift_y: float = 0.0,
    values: np.ndarray | None = None,
) -> tuple[Path, Path, np.ndarray]:
    product = root / product_name
    image_directory = (
        product
        / "GRANULE"
        / "L2A_T34VCL_A000001_20240101T101021"
        / "IMG_DATA"
        / "R20m"
    )
    image_directory.mkdir(parents=True)
    station_x, station_y = projected_station()
    pixel_size = 20.0
    transform = Affine(
        pixel_size,
        0.0,
        station_x - (station_col + 0.5) * pixel_size + shift_x,
        0.0,
        -pixel_size,
        station_y + (station_row + 0.5) * pixel_size + shift_y,
    )
    if values is None:
        values = (np.arange(width * height, dtype=np.uint16) % 12).astype(
            np.uint8
        ).reshape(height, width)
        values[station_row, station_col] = 6
    raster = image_directory / "T34VCL_20240101T101021_SCL_20m.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=RASTER_CRS,
        transform=transform,
    ) as target:
        target.write(values, 1)
    return product, raster, values


def test_safe_discovery_scl_selection_and_compact_metadata(tmp_path: Path) -> None:
    product, raster, _ = make_synthetic_safe(tmp_path / "archive" / "2024")
    (raster.parent / "T34VCL_20240101T101021_B04_20m.tif").write_bytes(b"decoy")
    (raster.parent / "T34VCL_20240101T101021_NDCI_20m.tif").write_bytes(b"decoy")
    (
        tmp_path
        / "archive"
        / "S2A_MSIL1C_20240101T101021_N0510_R022_T34VCL_20240101T120000.SAFE"
    ).mkdir()
    archive = tmp_path / "archive"

    assert discover_l2a_products(archive) == [product]
    assert find_scl_raster(product, tile_id="T34VCL") == raster
    metadata = parse_product_metadata(product, scl_path=raster)
    assert metadata.product_id == PRODUCT_NAME.removesuffix(".SAFE")
    assert metadata.platform == "S2A"
    assert metadata.acquisition_datetime == "2024-01-01T10:10:21Z"
    assert metadata.acquisition_date == "2024-01-01"
    assert metadata.tile_id == "T34VCL"
    assert metadata.processing_baseline == "N0510"


def test_xml_metadata_fallback_for_generic_product_directory(tmp_path: Path) -> None:
    product = tmp_path / "archive" / "generic_product"
    product.mkdir(parents=True)
    (product / "MTD_MSIL2A.xml").write_text(
        """<root>
        <PRODUCT_URI>S2B_MSIL2A_20240202T102019_N0509_R065_T34VCL_20240202T130000.SAFE</PRODUCT_URI>
        <PRODUCT_START_TIME>2024-02-02T10:20:19.000Z</PRODUCT_START_TIME>
        <PROCESSING_BASELINE>05.09</PROCESSING_BASELINE>
        <SPACECRAFT_NAME>Sentinel-2B</SPACECRAFT_NAME>
        </root>""",
        encoding="utf-8",
    )

    assert discover_l2a_products(tmp_path / "archive") == [product]
    metadata = parse_product_metadata(product)
    assert metadata.platform == "S2B"
    assert metadata.acquisition_datetime == "2024-02-02T10:20:19Z"
    assert metadata.processing_baseline == "N0509"


def test_wgs84_transform_row_col_and_exact_central_pixel(tmp_path: Path) -> None:
    _, raster, values = make_synthetic_safe(tmp_path)
    expected_x, expected_y = projected_station()
    station_x, station_y = transform_station_coordinate(
        station_lon=STATION_LON,
        station_lat=STATION_LAT,
        station_crs=STATION_CRS,
        raster_crs=RASTER_CRS,
    )
    assert station_x == pytest.approx(expected_x)
    assert station_y == pytest.approx(expected_y)

    with rasterio.open(raster) as dataset:
        location = station_to_pixel(
            dataset.transform,
            raster_width=dataset.width,
            raster_height=dataset.height,
            station_x=station_x,
            station_y=station_y,
        )
        central = extract_centered_window(
            dataset, central_row=location.row, central_col=location.col, window_size=1
        )
    assert location.inside
    assert (location.row, location.col) == (7, 7)
    assert central.values.tolist() == [[int(values[7, 7])]] == [[6]]


def test_all_candidate_centered_windows_have_exact_sizes(tmp_path: Path) -> None:
    _, raster, values = make_synthetic_safe(tmp_path)
    with rasterio.open(raster) as dataset:
        for size in WINDOW_SIZES:
            extracted = extract_centered_window(
                dataset, central_row=7, central_col=7, window_size=size
            )
            half = size // 2
            expected = values[7 - half : 7 + half + 1, 7 - half : 7 + half + 1]
            np.testing.assert_array_equal(extracted.values, expected)
            assert extracted.requested_pixel_count == size * size
            assert extracted.actual_pixel_count == size * size
            assert extracted.complete


def test_class_counts_fractions_and_diagnostic_aggregates() -> None:
    values = np.array(
        [[0, 1, 3], [6, 6, 6], [8, 10, 11]], dtype=np.uint8
    )
    summary = summarize_scl_classes(
        values, bad_scl_classes=DEFAULT_BAD_SCL_CLASSES
    )

    assert summary["scl_0_count"] == 1
    assert summary["scl_6_count"] == 3
    assert summary["scl_11_count"] == 1
    assert summary["scl_6_fraction"] == pytest.approx(3 / 9)
    assert summary["water_fraction"] == pytest.approx(3 / 9)
    assert summary["bad_scl_fraction"] == pytest.approx(6 / 9)
    assert summary["unexpected_scl_count"] == 0
    assert summary["unexpected_scl_values"] == ""


def test_raster_edge_window_is_clipped_without_padding(tmp_path: Path) -> None:
    _, raster, values = make_synthetic_safe(
        tmp_path, station_row=0, station_col=0
    )
    with rasterio.open(raster) as dataset:
        station_x, station_y = projected_station()
        location = station_to_pixel(
            dataset.transform,
            raster_width=dataset.width,
            raster_height=dataset.height,
            station_x=station_x,
            station_y=station_y,
        )
        extracted = extract_centered_window(
            dataset, central_row=location.row, central_col=location.col, window_size=11
        )

    assert (location.row, location.col) == (0, 0)
    assert extracted.requested_pixel_count == 121
    assert extracted.actual_pixel_count == 36
    assert not extracted.complete
    np.testing.assert_array_equal(extracted.values, values[:6, :6])


def test_station_outside_raster_is_recorded_without_crashing(tmp_path: Path) -> None:
    product, _, _ = make_synthetic_safe(tmp_path, shift_x=100_000.0)
    inventory, scenes = summarize_scene(
        product,
        input_root=tmp_path,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )

    assert inventory["processing_status"] == "station_outside_raster"
    assert inventory["scl_found"]
    assert len(scenes) == 5
    assert {row["processing_status"] for row in scenes} == {
        "station_outside_raster"
    }
    assert all(row["station_inside_raster"] is False for row in scenes)
    assert all(row["actual_pixel_count"] == 0 for row in scenes)


def test_missing_scl_raster_is_inventory_and_scene_status(tmp_path: Path) -> None:
    product = tmp_path / PRODUCT_NAME
    product.mkdir()
    inventory, scenes = summarize_scene(
        product,
        input_root=tmp_path,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )

    assert inventory["scl_found"] is False
    assert inventory["scl_candidate_count"] == 0
    assert inventory["processing_status"] == "missing_scl"
    assert len(scenes) == 5
    assert all(row["processing_status"] == "missing_scl" for row in scenes)


def test_empty_archive_creates_no_synthetic_acquisition_rows(tmp_path: Path) -> None:
    inventory, scenes = summarize_archive(
        tmp_path,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )
    inventory_path = tmp_path / "inventory.csv"
    scene_path = tmp_path / "scenes.csv"
    write_inventory_summary(inventory, inventory_path)
    write_scene_summary(scenes, scene_path)

    assert inventory == []
    assert scenes == []
    assert len(inventory_path.read_text(encoding="utf-8").splitlines()) == 1
    assert len(scene_path.read_text(encoding="utf-8").splitlines()) == 1


def test_same_date_products_remain_separate(tmp_path: Path) -> None:
    make_synthetic_safe(tmp_path, product_name=PRODUCT_NAME)
    make_synthetic_safe(
        tmp_path,
        product_name="S2B_MSIL2A_20240101T101021_N0510_R022_T34VCL_20240101T120500.SAFE",
    )
    inventory, scenes = summarize_archive(
        tmp_path,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )

    assert len(inventory) == 2
    assert len(scenes) == 10
    assert {row["platform"] for row in inventory} == {"S2A", "S2B"}
    assert {row["acquisition_date"] for row in inventory} == {"2024-01-01"}


def test_deterministic_portable_csvs_and_non_reflectance_schema(tmp_path: Path) -> None:
    make_synthetic_safe(tmp_path / "archive")
    archive = tmp_path / "archive"
    first_inventory, first_scenes = summarize_archive(
        archive,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )
    second_inventory, second_scenes = summarize_archive(
        archive,
        station_lat=STATION_LAT,
        station_lon=STATION_LON,
        station_crs=STATION_CRS,
        window_sizes=WINDOW_SIZES,
    )
    assert first_inventory == second_inventory
    assert first_scenes == second_scenes

    first_scene_path = tmp_path / "scene_first.csv"
    second_scene_path = tmp_path / "scene_second.csv"
    first_inventory_path = tmp_path / "inventory_first.csv"
    second_inventory_path = tmp_path / "inventory_second.csv"
    write_scene_summary(first_scenes, first_scene_path)
    write_scene_summary(second_scenes, second_scene_path)
    write_inventory_summary(first_inventory, first_inventory_path)
    write_inventory_summary(second_inventory, second_inventory_path)

    assert first_scene_path.read_bytes() == second_scene_path.read_bytes()
    assert first_inventory_path.read_bytes() == second_inventory_path.read_bytes()
    output_text = first_scene_path.read_text(encoding="utf-8")
    assert str(archive) not in output_text
    assert "/" + "Users/" not in output_text
    assert "GRANULE/" in output_text
    forbidden_science_inputs = {"chlf", "ndci", "mci", "reflectance"}
    output_columns = {column.lower() for column in SCENE_SUMMARY_COLUMNS}
    assert all(
        not any(term in column for term in forbidden_science_inputs)
        for column in output_columns
    )

    with first_scene_path.open(encoding="utf-8", newline="") as source:
        assert tuple(csv.DictReader(source).fieldnames or ()) == SCENE_SUMMARY_COLUMNS
    with first_inventory_path.open(encoding="utf-8", newline="") as source:
        assert tuple(csv.DictReader(source).fieldnames or ()) == INVENTORY_COLUMNS


def test_cli_writes_scene_and_inventory_outputs(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    make_synthetic_safe(archive)
    scene_output = tmp_path / "outputs" / "scene.csv"
    inventory_output = tmp_path / "outputs" / "inventory.csv"
    script = Path(__file__).resolve().parents[1] / "scripts" / "03_erken_s2_scl_diagnostics.py"
    process = subprocess.run(
        [
            sys.executable,
            str(script),
            "--input-root",
            str(archive),
            "--output",
            str(scene_output),
            "--inventory-output",
            str(inventory_output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert "Discovered 1 L2A product(s)" in process.stdout
    with scene_output.open(encoding="utf-8", newline="") as source:
        scene_rows = list(csv.DictReader(source))
    with inventory_output.open(encoding="utf-8", newline="") as source:
        inventory_rows = list(csv.DictReader(source))
    assert len(scene_rows) == 5
    assert len(inventory_rows) == 1
    assert inventory_rows[0]["processing_status"] == "ok"
