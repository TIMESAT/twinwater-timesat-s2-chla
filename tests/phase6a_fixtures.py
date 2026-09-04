"""Minimal controlled SAFE fixtures for Phase 6A tests.

These are deliberately tiny synthetic products used only to exercise the
pipeline's logic. They are never scientific outputs and are never written into
the repository; every fixture lives in a pytest temporary directory.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer


STATION_LAT = 59.84029
STATION_LON = 18.625827
STATION_CRS = "EPSG:4326"
RASTER_CRS = "EPSG:32634"

TILE = "T34VCM"
SENSING_COMPACT = "20190417T102031"
SENSING_ISO = "2019-04-17T10:20:31.024Z"
GENERATION_COMPACT = "20221023T092125"
BASELINE_DECIMAL = "05.00"

# Frozen 20 m analysis grid used by the fixtures: 12x12 cells with the station
# placed at row/col 5 so the 3x3 window is complete and interior.
TARGET_SIZE = 12
STATION_ROW = 5
STATION_COL = 5

CANONICAL_BAND_IDS = {"B4": 3, "B5": 4, "B6": 5}
CENTRAL_WAVELENGTHS = {"B4": 664.6, "B5": 704.1, "B6": 740.5}

MSK_QUALIT_BAND_COUNT = 8
MSK_CLASSI_BAND_COUNT = 3


def projected_station() -> tuple[float, float]:
    """Return the Erken station in the fixture raster CRS."""

    transformer = Transformer.from_crs(STATION_CRS, RASTER_CRS, always_xy=True)
    return transformer.transform(STATION_LON, STATION_LAT)


def grid_origin() -> tuple[float, float]:
    """Return a tile origin that places the station at the fixture pixel."""

    station_x, station_y = projected_station()
    # Snap to a 60 m multiple so the 10 m, 20 m and 60 m grids nest exactly.
    origin_x = np.floor((station_x - STATION_COL * 20.0) / 60.0) * 60.0
    origin_y = np.ceil((station_y + STATION_ROW * 20.0) / 60.0) * 60.0
    return float(origin_x), float(origin_y)


def transform_for(resolution_m: float) -> Affine:
    """Return the affine transform of one fixture resolution level."""

    origin_x, origin_y = grid_origin()
    return Affine(resolution_m, 0.0, origin_x, 0.0, -resolution_m, origin_y)


def station_pixel(resolution_m: float) -> tuple[int, int]:
    """Return the station's row/col at one fixture resolution."""

    station_x, station_y = projected_station()
    transform = transform_for(resolution_m)
    col = int(np.floor((station_x - transform.c) / resolution_m))
    row = int(np.floor((transform.f - station_y) / resolution_m))
    return row, col


def _write_raster(
    path: Path, array: np.ndarray, resolution_m: float, dtype: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(array)
    if data.ndim == 2:
        data = data[np.newaxis, :, :]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=dtype,
        crs=RASTER_CRS,
        transform=transform_for(resolution_m),
    ) as dataset:
        dataset.write(data.astype(dtype))


def _spectral_information_xml() -> str:
    entries = []
    for band, band_id in CANONICAL_BAND_IDS.items():
        entries.append(
            f'<Spectral_Information bandId="{band_id}" physicalBand="{band}">'
            f"<Wavelength><CENTRAL unit=\"nm\">{CENTRAL_WAVELENGTHS[band]}</CENTRAL>"
            "</Wavelength></Spectral_Information>"
        )
    return "".join(entries)


def _offset_xml(tag: str, list_tag: str, offset: float, bands: dict[str, int]) -> str:
    entries = "".join(
        f'<{tag} band_id="{band_id}">{offset:g}</{tag}>'
        for band_id in sorted(bands.values())
    )
    return f"<{list_tag}>{entries}</{list_tag}>"


def l1c_metadata_xml(
    *,
    product_uri: str,
    quantification: float | None = 10000.0,
    offset: float | None = -1000.0,
    include_bands: dict[str, int] | None = None,
    spectral_information: bool = True,
    baseline: str | None = BASELINE_DECIMAL,
) -> str:
    """Build a minimal but structurally faithful L1C product metadata document."""

    bands = include_bands if include_bands is not None else CANONICAL_BAND_IDS
    quantification_xml = (
        f'<QUANTIFICATION_VALUE unit="none">{quantification:g}</QUANTIFICATION_VALUE>'
        if quantification is not None
        else ""
    )
    offset_xml = (
        _offset_xml("RADIO_ADD_OFFSET", "Radiometric_Offset_List", offset, bands)
        if offset is not None
        else ""
    )
    spectral_xml = (
        f"<Spectral_Information_List>{_spectral_information_xml()}"
        "</Spectral_Information_List>"
        if spectral_information
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Level-1C_User_Product><General_Info>"
        f"<Product_Info><PRODUCT_URI>{product_uri}</PRODUCT_URI>"
        f"<GENERATION_TIME>2022-10-23T09:21:25.000Z</GENERATION_TIME>"
        "<Datatake><SPACECRAFT_NAME>Sentinel-2A</SPACECRAFT_NAME>"
        f"<DATATAKE_SENSING_START>{SENSING_ISO}</DATATAKE_SENSING_START>"
        "<SENSING_ORBIT_NUMBER>65</SENSING_ORBIT_NUMBER></Datatake>"
        + (
            f"<PROCESSING_BASELINE>{baseline}</PROCESSING_BASELINE>"
            if baseline is not None
            else ""
        )
        + "</Product_Info>"
        f"<Product_Image_Characteristics>{quantification_xml}{offset_xml}"
        f"{spectral_xml}</Product_Image_Characteristics>"
        "</General_Info></Level-1C_User_Product>"
    )


def l2a_metadata_xml(
    *,
    product_uri: str,
    quantification: float | None = 10000.0,
    offset: float | None = -1000.0,
    include_bands: dict[str, int] | None = None,
    spectral_information: bool = True,
    baseline: str | None = BASELINE_DECIMAL,
) -> str:
    """Build a minimal but structurally faithful L2A product metadata document."""

    bands = include_bands if include_bands is not None else CANONICAL_BAND_IDS
    quantification_xml = (
        "<QUANTIFICATION_VALUES_LIST>"
        f'<BOA_QUANTIFICATION_VALUE unit="none">{quantification:g}'
        "</BOA_QUANTIFICATION_VALUE></QUANTIFICATION_VALUES_LIST>"
        if quantification is not None
        else ""
    )
    offset_xml = (
        _offset_xml("BOA_ADD_OFFSET", "BOA_ADD_OFFSET_VALUES_LIST", offset, bands)
        if offset is not None
        else ""
    )
    spectral_xml = (
        f"<Spectral_Information_List>{_spectral_information_xml()}"
        "</Spectral_Information_List>"
        if spectral_information
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Level-2A_User_Product><General_Info>"
        f"<Product_Info><PRODUCT_URI>{product_uri}</PRODUCT_URI>"
        f"<GENERATION_TIME>2022-10-23T09:21:25.000Z</GENERATION_TIME>"
        "<Datatake><SPACECRAFT_NAME>Sentinel-2A</SPACECRAFT_NAME>"
        f"<DATATAKE_SENSING_START>{SENSING_ISO}</DATATAKE_SENSING_START>"
        "<SENSING_ORBIT_NUMBER>65</SENSING_ORBIT_NUMBER></Datatake>"
        + (
            f"<PROCESSING_BASELINE>{baseline}</PROCESSING_BASELINE>"
            if baseline is not None
            else ""
        )
        + "</Product_Info>"
        f"<Product_Image_Characteristics>{quantification_xml}{offset_xml}"
        f"{spectral_xml}</Product_Image_Characteristics>"
        "</General_Info></Level-2A_User_Product>"
    )


def product_name(level: str, *, platform: str = "S2A", tile: str = TILE) -> str:
    """Return a compact SAFE product name for one processing level."""

    return (
        f"{platform}_MSI{level}_{SENSING_COMPACT}_N0500_R065_{tile}_"
        f"{GENERATION_COMPACT}"
    )


# Native QA masks follow official Sentinel-2 geometry rather than one uniform
# resolution: MSK_QUALIT is distributed at the spatial resolution of its
# spectral band (B4 -> 10 m, B5/B6 -> 20 m) while MSK_CLASSI is 60 m.
QUALIT_RESOLUTION_M: dict[str, float] = {"B04": 10.0, "B05": 20.0, "B06": 20.0}
CLASSI_RESOLUTION_M = 60.0

# Reference cells for tests, expressed on each mask's own native grid.
#
# The frozen 3x3 window covers 20 m rows/cols 4-6. On the 10 m grid that is
# rows/cols 8-13; on the 60 m grid it is cells (1,1)-(2,2).
WINDOW_20M_ORIGIN = (4, 4)
# One single 10 m subpixel inside 20 m window pixel (4, 4).
B04_SINGLE_FINE_CELL = (8, 8)
# 60 m cell (1,1) covers 20 m rows/cols 3-5 -> four window pixels.
OPAQUE_COARSE_CELL = (1, 1)
OPAQUE_WINDOW_PIXELS = 4
# 60 m cell (2,2) covers 20 m rows/cols 6-8 -> one window pixel.
OPAQUE_COARSE_CELL_SINGLE = (2, 2)
OPAQUE_WINDOW_PIXELS_SINGLE = 1

MSK_QUALIT_CONDITION_INDEX: dict[str, int] = {
    "ancillary_lost": 0,
    "ancillary_degraded": 1,
    "msi_lost": 2,
    "msi_degraded": 3,
    "defective": 4,
    "nodata": 5,
    "partially_corrected": 6,
    "saturated": 7,
}
MSK_CLASSI_CONDITION_INDEX: dict[str, int] = {
    "opaque_cloud": 0,
    "cirrus": 1,
    "snow_ice": 2,
}


def _grid_size(resolution_m: float) -> int:
    """Return the fixture raster size at one resolution, preserving nesting."""

    return int(round(TARGET_SIZE * 20.0 / resolution_m))


def _quality_masks(
    root: Path,
    bands: tuple[str, ...],
    *,
    qualit_flags: dict[str, list[tuple[str, tuple[int, int]]]] | None = None,
    classi_flags: list[tuple[str, tuple[int, int]]] | None = None,
) -> None:
    """Write per-band MSK_QUALIT and product-level MSK_CLASSI rasters.

    ``qualit_flags`` maps a band to ``(condition, (row, col))`` entries on that
    band's own native mask grid; ``classi_flags`` uses the 60 m grid.
    """

    qualit_flags = qualit_flags or {}
    for band in bands:
        resolution = QUALIT_RESOLUTION_M[band]
        size = _grid_size(resolution)
        values = np.zeros((MSK_QUALIT_BAND_COUNT, size, size), dtype="uint8")
        for condition, (row, col) in qualit_flags.get(band, []):
            values[MSK_QUALIT_CONDITION_INDEX[condition], row, col] = 1
        _write_raster(root / f"MSK_QUALIT_{band}.tif", values, resolution, "uint8")

    classi_size = _grid_size(CLASSI_RESOLUTION_M)
    classi = np.zeros((MSK_CLASSI_BAND_COUNT, classi_size, classi_size), dtype="uint8")
    for condition, (row, col) in classi_flags or []:
        classi[MSK_CLASSI_CONDITION_INDEX[condition], row, col] = 1
    _write_raster(root / "MSK_CLASSI_B00.tif", classi, CLASSI_RESOLUTION_M, "uint8")

    # Detector footprint is inventoried but not part of canonical validity.
    _write_raster(
        root / "MSK_DETFOO_B04.tif",
        np.ones((_grid_size(10.0), _grid_size(10.0)), dtype="uint8"),
        10.0,
        "uint8",
    )


def build_l1c_product(
    base: Path,
    *,
    digital_numbers: dict[str, int] | None = None,
    metadata_xml: str | None = None,
    qualit_flags: dict[str, list[tuple[str, tuple[int, int]]]] | None = None,
    classi_flags: list[tuple[str, tuple[int, int]]] | None = None,
    platform: str = "S2A",
    tile: str = TILE,
) -> Path:
    """Create a minimal L1C SAFE product with flat IMG_DATA band rasters."""

    name = product_name("L1C", platform=platform, tile=tile)
    root = base / f"{name}.SAFE"
    granule = root / "GRANULE" / f"L1C_{tile}_A020000_{SENSING_COMPACT}"
    image = granule / "IMG_DATA"
    quality = granule / "QI_DATA"

    values = digital_numbers or {"B4": 1400, "B5": 1600, "B6": 1500}
    # B4 is native 10 m in L1C; B5 and B6 define the 20 m target grid.
    _write_raster(
        image / f"{tile}_{SENSING_COMPACT}_B04.tif",
        np.full((TARGET_SIZE * 2, TARGET_SIZE * 2), values["B4"], dtype="uint16"),
        10.0,
        "uint16",
    )
    for band, key in (("B05", "B5"), ("B06", "B6")):
        _write_raster(
            image / f"{tile}_{SENSING_COMPACT}_{band}.tif",
            np.full((TARGET_SIZE, TARGET_SIZE), values[key], dtype="uint16"),
            20.0,
            "uint16",
        )

    _quality_masks(
        quality,
        ("B04", "B05", "B06"),
        qualit_flags=qualit_flags,
        classi_flags=classi_flags,
    )
    (root / "MTD_MSIL1C.xml").write_text(
        metadata_xml or l1c_metadata_xml(product_uri=f"{name}.SAFE"),
        encoding="utf-8",
    )
    return root


def build_l2a_product(
    base: Path,
    *,
    digital_numbers: dict[str, int] | None = None,
    metadata_xml: str | None = None,
    scl_values: np.ndarray | None = None,
    qualit_flags: dict[str, list[tuple[str, tuple[int, int]]]] | None = None,
    classi_flags: list[tuple[str, tuple[int, int]]] | None = None,
    platform: str = "S2A",
    tile: str = TILE,
) -> Path:
    """Create a minimal official-L2A SAFE product with R10m/R20m IMG_DATA.

    Quality masks are inherited from L1C at their spectral band's native
    resolution, so this fixture exercises both the target-resolution case
    (B5/B6 at 20 m) and the finer-than-target case (B4 at 10 m) that the
    categorical parser claims to support.
    """

    name = product_name("L2A", platform=platform, tile=tile)
    root = base / f"{name}.SAFE"
    granule = root / "GRANULE" / f"L2A_{tile}_A020000_{SENSING_COMPACT}"
    quality = granule / "QI_DATA"

    values = digital_numbers or {"B4": 1200, "B5": 1500, "B6": 1300}
    _write_raster(
        granule / "IMG_DATA" / "R10m" / f"{tile}_{SENSING_COMPACT}_B04_10m.tif",
        np.full((TARGET_SIZE * 2, TARGET_SIZE * 2), values["B4"], dtype="uint16"),
        10.0,
        "uint16",
    )
    for band, key in (("B04", "B4"), ("B05", "B5"), ("B06", "B6")):
        _write_raster(
            granule / "IMG_DATA" / "R20m" / f"{tile}_{SENSING_COMPACT}_{band}_20m.tif",
            np.full((TARGET_SIZE, TARGET_SIZE), values[key], dtype="uint16"),
            20.0,
            "uint16",
        )

    scl = (
        scl_values
        if scl_values is not None
        else np.full((TARGET_SIZE, TARGET_SIZE), 6, dtype="uint8")
    )
    _write_raster(
        granule / "IMG_DATA" / "R20m" / f"{tile}_{SENSING_COMPACT}_SCL_20m.tif",
        scl,
        20.0,
        "uint8",
    )

    _quality_masks(
        quality,
        ("B04", "B05", "B06"),
        qualit_flags=qualit_flags,
        classi_flags=classi_flags,
    )
    (root / "MTD_MSIL2A.xml").write_text(
        metadata_xml or l2a_metadata_xml(product_uri=f"{name}.SAFE"),
        encoding="utf-8",
    )
    return root


def write_frozen_mask_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a minimal stand-in for the frozen date-level observation mask."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "date",
        "year",
        "s2_date_usable",
        "selected_product_id",
        "qc_rule_id",
        "mask_version",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
