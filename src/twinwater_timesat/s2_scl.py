"""Portable Sentinel-2 L2A SCL discovery and spatial diagnostics.

This module deliberately reads only the Scene Classification Layer (SCL). It
does not read reflectance bands, derive spectral indices, or decide whether an
acquisition is usable for temporal reconstruction.
"""

from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import rowcol
from rasterio.windows import Window

from .provenance import PROHIBITED_PATH_MARKERS


SCL_CLASS_NAMES: dict[int, str] = {
    0: "No data",
    1: "Saturated or defective",
    2: "Topographic cast shadow / dark area (baseline dependent)",
    3: "Cloud shadow",
    4: "Vegetation",
    5: "Not vegetated",
    6: "Water",
    7: "Unclassified",
    8: "Cloud medium probability",
    9: "Cloud high probability",
    10: "Thin cirrus",
    11: "Snow or ice",
}
SCL_CLASS_CODES: tuple[int, ...] = tuple(SCL_CLASS_NAMES)
DEFAULT_BAD_SCL_CLASSES: frozenset[int] = frozenset({0, 1, 3, 8, 9, 10, 11})
SCL_RASTER_SUFFIXES: frozenset[str] = frozenset({".jp2", ".tif", ".tiff"})

PRODUCT_NAME_RE = re.compile(
    r"(?P<platform>S2[A-Z0-9])_MSIL2A_"
    r"(?P<acquisition>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_R\d{3}_"
    r"(?P<tile>T\d{2}[A-Z]{3})_\d{8}T\d{6}",
    re.IGNORECASE,
)
TILE_RE = re.compile(r"(?:^|_)(T\d{2}[A-Z]{3})(?:_|$)", re.IGNORECASE)
SCL_NAME_RE = re.compile(r"(?:^|_)SCL(?:_|$)", re.IGNORECASE)


class SCLDiscoveryError(ValueError):
    """Raised when an L2A product does not identify one unambiguous SCL raster."""


@dataclass(frozen=True)
class ProductMetadata:
    """Portable product-level metadata extracted from name and optional XML."""

    product_id: str
    platform: str | None
    acquisition_datetime: str | None
    acquisition_date: str | None
    tile_id: str | None
    processing_baseline: str | None


@dataclass(frozen=True)
class PixelLocation:
    """Pixel indices calculated from a raster's actual affine transform."""

    row: int
    col: int
    inside: bool


@dataclass(frozen=True)
class WindowExtraction:
    """An unpadded, raster-clipped centered window."""

    values: np.ndarray
    requested_pixel_count: int
    actual_pixel_count: int
    complete: bool


METADATA_COLUMNS: tuple[str, ...] = (
    "product_id",
    "platform",
    "acquisition_datetime",
    "acquisition_date",
    "tile_id",
    "processing_baseline",
)
RASTER_COLUMNS: tuple[str, ...] = (
    "scl_raster_relative_path",
    "scl_crs",
    "raster_transform_a",
    "raster_transform_b",
    "raster_transform_c",
    "raster_transform_d",
    "raster_transform_e",
    "raster_transform_f",
    "raster_bounds_left",
    "raster_bounds_bottom",
    "raster_bounds_right",
    "raster_bounds_top",
    "pixel_size_x",
    "pixel_size_y",
    "raster_width",
    "raster_height",
)
STATION_COLUMNS: tuple[str, ...] = (
    "station_lat",
    "station_lon",
    "station_crs",
    "station_x",
    "station_y",
    "central_row",
    "central_col",
    "central_scl",
    "station_inside_raster",
)
CLASS_COLUMNS: tuple[str, ...] = tuple(
    [f"scl_{code}_count" for code in SCL_CLASS_CODES]
    + [f"scl_{code}_fraction" for code in SCL_CLASS_CODES]
    + [
        "unexpected_scl_count",
        "unexpected_scl_values",
        "water_fraction",
        "bad_scl_fraction",
    ]
)
SCENE_SUMMARY_COLUMNS: tuple[str, ...] = (
    *METADATA_COLUMNS,
    *RASTER_COLUMNS,
    *STATION_COLUMNS,
    "window_size",
    "requested_pixel_count",
    "actual_pixel_count",
    "window_complete",
    *CLASS_COLUMNS,
    "processing_status",
    "processing_note",
)
INVENTORY_COLUMNS: tuple[str, ...] = (
    *METADATA_COLUMNS,
    "scl_raster_relative_path",
    "scl_candidate_count",
    "scl_found",
    "processing_status",
    "processing_note",
)


def _product_name(path: Path) -> str:
    name = path.name
    return name[:-5] if name.upper().endswith(".SAFE") else name


def _looks_like_product_directory(path: Path, filenames: Sequence[str]) -> bool:
    name = path.name.upper()
    return (
        (name.endswith(".SAFE") and "_MSIL2A_" in name)
        or "MTD_MSIL2A.XML" in {filename.upper() for filename in filenames}
        or bool(PRODUCT_NAME_RE.search(name))
    )


def discover_l2a_products(input_root: str | Path) -> list[Path]:
    """Discover deterministic SAFE-style or compact-name L2A product roots."""

    root = Path(input_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Sentinel-2 L2A input root is not a directory: {root}")

    root_files = [path.name for path in root.iterdir() if path.is_file()]
    if _looks_like_product_directory(root, root_files):
        return [root]

    products: set[Path] = set()
    for current, directory_names, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path != root and _looks_like_product_directory(
            current_path, filenames
        ):
            products.add(current_path)
            directory_names[:] = []
            continue

        product_directories: list[str] = []
        for directory_name in directory_names:
            candidate = current_path / directory_name
            if _looks_like_product_directory(candidate, []):
                products.add(candidate)
                product_directories.append(directory_name)
        if product_directories:
            directory_names[:] = [
                name for name in directory_names if name not in product_directories
            ]

    return sorted(products, key=lambda path: path.relative_to(root).as_posix())


def _is_scl_raster(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in SCL_RASTER_SUFFIXES
        and bool(SCL_NAME_RE.search(path.stem))
    )


def find_scl_rasters(product_path: str | Path) -> list[Path]:
    """Return all SCL-like JP2/GeoTIFF rasters below a product root."""

    product = Path(product_path)
    if not product.is_dir():
        return []
    return sorted(
        (path for path in product.rglob("*") if _is_scl_raster(path)),
        key=lambda path: path.relative_to(product).as_posix(),
    )


def _scl_preference(path: Path) -> tuple[int, int]:
    text = path.as_posix().upper()
    named_20m = "_SCL_20M" in path.stem.upper()
    in_r20m_directory = "/R20M/" in text
    extension_rank = {".jp2": 0, ".tif": 1, ".tiff": 2}.get(
        path.suffix.lower(), 3
    )
    resolution_rank = (
        0 if named_20m and in_r20m_directory else 1 if named_20m else 2
    )
    return (resolution_rank, extension_rank)


def find_scl_raster(
    product_path: str | Path, *, tile_id: str | None = None
) -> Path | None:
    """Select the preferred SCL raster or fail on unresolved ambiguity."""

    candidates = find_scl_rasters(product_path)
    if not candidates:
        return None
    if tile_id:
        tile_matches = [
            path for path in candidates if tile_id.upper() in path.as_posix().upper()
        ]
        if tile_matches:
            candidates = tile_matches
    best_preference = min(_scl_preference(path) for path in candidates)
    preferred = [
        path for path in candidates if _scl_preference(path) == best_preference
    ]
    if len(preferred) != 1:
        relative = [
            path.relative_to(Path(product_path)).as_posix() for path in preferred
        ]
        raise SCLDiscoveryError(
            "Multiple equally preferred SCL rasters remain after native-20 m "
            f"and tile selection: {relative}"
        )
    return preferred[0]


def _xml_values(metadata_path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(metadata_path).getroot()
    except (ElementTree.ParseError, OSError):
        return {}
    values: dict[str, str] = {}
    wanted = {
        "PRODUCT_URI",
        "PRODUCT_START_TIME",
        "DATATAKE_SENSING_START",
        "SENSING_TIME",
        "PROCESSING_BASELINE",
        "SPACECRAFT_NAME",
        "TILE_ID",
    }
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1].upper()
        text = (element.text or "").strip()
        if local_name in wanted and text and local_name not in values:
            values[local_name] = text
    return values


def _first_product_xml(product_path: Path) -> Path | None:
    direct = product_path / "MTD_MSIL2A.xml"
    if direct.is_file():
        return direct
    matches = sorted(
        (
            path
            for path in product_path.glob("MTD_MSIL2A.*")
            if path.is_file() and path.suffix.lower() == ".xml"
        ),
        key=lambda path: path.name,
    )
    return matches[0] if matches else None


def _normalise_datetime(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    text = value.strip()
    parsed: datetime | None = None
    if re.fullmatch(r"\d{8}T\d{6}", text):
        parsed = datetime.strptime(text, "%Y%m%dT%H%M%S").replace(
            tzinfo=timezone.utc
        )
    else:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
        except ValueError:
            date = (
                text[:10]
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text)
                else None
            )
            return text, date
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ"), parsed.date().isoformat()


def _normalise_platform(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper().strip()
    sentinel_match = re.search(r"SENTINEL[-_ ]?2[-_ ]?([A-Z0-9])", upper)
    if sentinel_match:
        return f"S2{sentinel_match.group(1)}"
    compact_match = re.search(r"S2[A-Z0-9]", upper)
    return compact_match.group(0) if compact_match else value


def _normalise_baseline(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.strip().upper()
    if re.fullmatch(r"N\d{4}", upper):
        return upper
    decimal = re.fullmatch(r"(\d{2})\.(\d{2})", upper)
    return f"N{decimal.group(1)}{decimal.group(2)}" if decimal else upper


def _normalise_tile_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"T\d{2}[A-Z]{3}", value.upper())
    return match.group(0) if match else value.upper()


def parse_product_metadata(
    product_path: str | Path, *, scl_path: str | Path | None = None
) -> ProductMetadata:
    """Parse compact SAFE naming first and use product XML as a fallback."""

    product = Path(product_path)
    product_id = _product_name(product)
    xml_path = _first_product_xml(product)
    xml = _xml_values(xml_path) if xml_path else {}
    xml_product_id = xml.get("PRODUCT_URI")
    if xml_product_id:
        product_id = _product_name(Path(xml_product_id))

    match = PRODUCT_NAME_RE.search(product_id)
    platform = match.group("platform").upper() if match else None
    acquisition = match.group("acquisition") if match else None
    baseline = match.group("baseline").upper() if match else None
    tile_id = match.group("tile").upper() if match else None

    platform = platform or _normalise_platform(xml.get("SPACECRAFT_NAME"))
    acquisition = acquisition or xml.get("PRODUCT_START_TIME") or xml.get(
        "DATATAKE_SENSING_START"
    ) or xml.get("SENSING_TIME")
    baseline = baseline or xml.get("PROCESSING_BASELINE")
    tile_id = tile_id or xml.get("TILE_ID")
    if not tile_id and scl_path is not None:
        tile_match = TILE_RE.search(Path(scl_path).as_posix())
        tile_id = tile_match.group(1).upper() if tile_match else None

    acquisition_datetime, acquisition_date = _normalise_datetime(acquisition)
    return ProductMetadata(
        product_id=product_id,
        platform=_normalise_platform(platform),
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date,
        tile_id=_normalise_tile_id(tile_id),
        processing_baseline=_normalise_baseline(baseline),
    )


def transform_station_coordinate(
    *,
    station_lon: float,
    station_lat: float,
    station_crs: str | CRS,
    raster_crs: str | CRS,
) -> tuple[float, float]:
    """Transform a longitude/latitude coordinate with explicit x/y ordering."""

    transformer = Transformer.from_crs(
        CRS.from_user_input(station_crs),
        CRS.from_user_input(raster_crs),
        always_xy=True,
    )
    station_x, station_y = transformer.transform(station_lon, station_lat)
    if not (math.isfinite(station_x) and math.isfinite(station_y)):
        raise ValueError("Station coordinate transformation produced non-finite values.")
    return float(station_x), float(station_y)


def station_to_pixel(
    transform: rasterio.Affine,
    *,
    raster_width: int,
    raster_height: int,
    station_x: float,
    station_y: float,
) -> PixelLocation:
    """Calculate the containing pixel using the inverse affine transform."""

    row_value, col_value = rowcol(
        transform,
        station_x,
        station_y,
        op=np.floor,
    )
    row = int(row_value)
    col = int(col_value)
    inside = 0 <= row < raster_height and 0 <= col < raster_width
    return PixelLocation(row=row, col=col, inside=inside)


def extract_centered_window(
    dataset: rasterio.io.DatasetReader,
    *,
    central_row: int,
    central_col: int,
    window_size: int,
) -> WindowExtraction:
    """Read an odd centered window, clipped to raster bounds without padding."""

    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("window_size must be a positive odd integer.")
    if not (0 <= central_row < dataset.height and 0 <= central_col < dataset.width):
        raise ValueError("Central pixel lies outside the raster.")

    half = window_size // 2
    row_start = max(0, central_row - half)
    row_stop = min(dataset.height, central_row + half + 1)
    col_start = max(0, central_col - half)
    col_stop = min(dataset.width, central_col + half + 1)
    window = Window(
        col_off=col_start,
        row_off=row_start,
        width=col_stop - col_start,
        height=row_stop - row_start,
    )
    values = dataset.read(1, window=window, boundless=False)
    requested = window_size * window_size
    actual = int(values.size)
    return WindowExtraction(
        values=values,
        requested_pixel_count=requested,
        actual_pixel_count=actual,
        complete=actual == requested,
    )


def summarize_scl_classes(
    values: np.ndarray,
    *,
    bad_scl_classes: Iterable[int] = DEFAULT_BAD_SCL_CLASSES,
) -> dict[str, Any]:
    """Summarize every standard SCL class plus diagnostic aggregate fractions."""

    flat = np.asarray(values).reshape(-1)
    pixel_count = int(flat.size)
    bad_classes = frozenset(int(code) for code in bad_scl_classes)
    result: dict[str, Any] = {}
    for code in SCL_CLASS_CODES:
        count = int(np.count_nonzero(flat == code))
        result[f"scl_{code}_count"] = count
        result[f"scl_{code}_fraction"] = count / pixel_count if pixel_count else None
    standard = np.isin(flat, SCL_CLASS_CODES)
    unexpected_values: list[str] = []
    for value in np.unique(flat[~standard]):
        numeric = float(value)
        unexpected_values.append(
            str(int(numeric))
            if math.isfinite(numeric) and numeric.is_integer()
            else str(value)
        )
    result["unexpected_scl_count"] = int(np.count_nonzero(~standard))
    result["unexpected_scl_values"] = ";".join(unexpected_values)
    result["water_fraction"] = (
        int(np.count_nonzero(flat == 6)) / pixel_count if pixel_count else None
    )
    result["bad_scl_fraction"] = (
        int(np.count_nonzero(np.isin(flat, tuple(bad_classes)))) / pixel_count
        if pixel_count
        else None
    )
    return result


def _metadata_values(metadata: ProductMetadata) -> dict[str, Any]:
    return {column: getattr(metadata, column) for column in METADATA_COLUMNS}


def _relative_path(path: Path, input_root: Path) -> str:
    return path.relative_to(input_root).as_posix()


def _empty_raster_values() -> dict[str, Any]:
    return {column: None for column in RASTER_COLUMNS}


def _empty_station_values(
    *, station_lat: float, station_lon: float, station_crs: str
) -> dict[str, Any]:
    return {
        "station_lat": station_lat,
        "station_lon": station_lon,
        "station_crs": station_crs,
        "station_x": None,
        "station_y": None,
        "central_row": None,
        "central_col": None,
        "central_scl": None,
        "station_inside_raster": None,
    }


def _failure_scene_rows(
    *,
    metadata: ProductMetadata,
    window_sizes: Sequence[int],
    raster_values: Mapping[str, Any],
    station_values: Mapping[str, Any],
    status: str,
    note: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window_size in window_sizes:
        row = {
            **_metadata_values(metadata),
            **raster_values,
            **station_values,
            "window_size": window_size,
            "requested_pixel_count": window_size * window_size,
            "actual_pixel_count": 0,
            "window_complete": False,
            **{column: None for column in CLASS_COLUMNS},
            "processing_status": status,
            "processing_note": note,
        }
        rows.append(row)
    return rows


def summarize_scene(
    product_path: str | Path,
    *,
    input_root: str | Path,
    station_lat: float,
    station_lon: float,
    station_crs: str,
    window_sizes: Sequence[int],
    bad_scl_classes: Iterable[int] = DEFAULT_BAD_SCL_CLASSES,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create one inventory row and one scene row per requested window size."""

    product = Path(product_path)
    root = Path(input_root)
    metadata = parse_product_metadata(product)
    candidate_count = len(find_scl_rasters(product))
    inventory = {
        **_metadata_values(metadata),
        "scl_raster_relative_path": None,
        "scl_candidate_count": candidate_count,
        "scl_found": candidate_count > 0,
        "processing_status": None,
        "processing_note": "",
    }
    base_station = _empty_station_values(
        station_lat=station_lat,
        station_lon=station_lon,
        station_crs=station_crs,
    )

    try:
        scl_path = find_scl_raster(product, tile_id=metadata.tile_id)
    except SCLDiscoveryError:
        inventory.update(
            processing_status="ambiguous_scl",
            processing_note="Multiple equally preferred SCL rasters; no implicit selection was made.",
        )
        return inventory, _failure_scene_rows(
            metadata=metadata,
            window_sizes=window_sizes,
            raster_values=_empty_raster_values(),
            station_values=base_station,
            status="ambiguous_scl",
            note=inventory["processing_note"],
        )

    if scl_path is None:
        inventory.update(
            processing_status="missing_scl",
            processing_note="No SCL JP2/GeoTIFF raster was found below the product root.",
        )
        return inventory, _failure_scene_rows(
            metadata=metadata,
            window_sizes=window_sizes,
            raster_values=_empty_raster_values(),
            station_values=base_station,
            status="missing_scl",
            note=inventory["processing_note"],
        )

    metadata = parse_product_metadata(product, scl_path=scl_path)
    inventory.update(_metadata_values(metadata))
    relative_scl = _relative_path(scl_path, root)
    inventory["scl_raster_relative_path"] = relative_scl
    try:
        dataset_context = rasterio.open(scl_path)
    except (OSError, rasterio.errors.RasterioError):
        inventory.update(
            processing_status="raster_open_error",
            processing_note="The selected SCL raster could not be opened by rasterio.",
        )
        raster_values = _empty_raster_values()
        raster_values["scl_raster_relative_path"] = relative_scl
        return inventory, _failure_scene_rows(
            metadata=metadata,
            window_sizes=window_sizes,
            raster_values=raster_values,
            station_values=base_station,
            status="raster_open_error",
            note=inventory["processing_note"],
        )

    with dataset_context as dataset:
        transform = dataset.transform
        bounds = dataset.bounds
        raster_values = {
            "scl_raster_relative_path": relative_scl,
            "scl_crs": dataset.crs.to_string() if dataset.crs else None,
            "raster_transform_a": transform.a,
            "raster_transform_b": transform.b,
            "raster_transform_c": transform.c,
            "raster_transform_d": transform.d,
            "raster_transform_e": transform.e,
            "raster_transform_f": transform.f,
            "raster_bounds_left": bounds.left,
            "raster_bounds_bottom": bounds.bottom,
            "raster_bounds_right": bounds.right,
            "raster_bounds_top": bounds.top,
            "pixel_size_x": dataset.res[0],
            "pixel_size_y": dataset.res[1],
            "raster_width": dataset.width,
            "raster_height": dataset.height,
        }
        if dataset.crs is None:
            inventory.update(
                processing_status="missing_raster_crs",
                processing_note="The SCL raster has no declared CRS.",
            )
            return inventory, _failure_scene_rows(
                metadata=metadata,
                window_sizes=window_sizes,
                raster_values=raster_values,
                station_values=base_station,
                status="missing_raster_crs",
                note=inventory["processing_note"],
            )

        try:
            station_x, station_y = transform_station_coordinate(
                station_lon=station_lon,
                station_lat=station_lat,
                station_crs=station_crs,
                raster_crs=dataset.crs,
            )
        except (ValueError, TypeError):
            inventory.update(
                processing_status="coordinate_transform_error",
                processing_note="The station coordinate could not be transformed into the raster CRS.",
            )
            return inventory, _failure_scene_rows(
                metadata=metadata,
                window_sizes=window_sizes,
                raster_values=raster_values,
                station_values=base_station,
                status="coordinate_transform_error",
                note=inventory["processing_note"],
            )

        location = station_to_pixel(
            transform,
            raster_width=dataset.width,
            raster_height=dataset.height,
            station_x=station_x,
            station_y=station_y,
        )
        station_values = {
            **base_station,
            "station_x": station_x,
            "station_y": station_y,
            "central_row": location.row,
            "central_col": location.col,
            "station_inside_raster": location.inside,
        }
        if not location.inside:
            inventory.update(
                processing_status="station_outside_raster",
                processing_note="The transformed station coordinate lies outside this SCL raster.",
            )
            return inventory, _failure_scene_rows(
                metadata=metadata,
                window_sizes=window_sizes,
                raster_values=raster_values,
                station_values=station_values,
                status="station_outside_raster",
                note=inventory["processing_note"],
            )

        try:
            central = dataset.read(
                1,
                window=Window(location.col, location.row, 1, 1),
                boundless=False,
            )
        except (OSError, rasterio.errors.RasterioError):
            inventory.update(
                processing_status="raster_read_error",
                processing_note="The SCL raster opened but the central pixel could not be read.",
            )
            return inventory, _failure_scene_rows(
                metadata=metadata,
                window_sizes=window_sizes,
                raster_values=raster_values,
                station_values=station_values,
                status="raster_read_error",
                note=inventory["processing_note"],
            )
        central_scl = int(central[0, 0])
        station_values["central_scl"] = central_scl
        rows: list[dict[str, Any]] = []
        window_read_failed = False
        for window_size in window_sizes:
            try:
                extracted = extract_centered_window(
                    dataset,
                    central_row=location.row,
                    central_col=location.col,
                    window_size=window_size,
                )
            except (OSError, rasterio.errors.RasterioError):
                window_read_failed = True
                rows.extend(
                    _failure_scene_rows(
                        metadata=metadata,
                        window_sizes=[window_size],
                        raster_values=raster_values,
                        station_values=station_values,
                        status="window_read_error",
                        note="The centered SCL window could not be read.",
                    )
                )
                continue
            status = "ok" if extracted.complete else "window_clipped"
            note = (
                ""
                if extracted.complete
                else "Requested centered window reached the raster boundary; no padding was added."
            )
            rows.append(
                {
                    **_metadata_values(metadata),
                    **raster_values,
                    **station_values,
                    "window_size": window_size,
                    "requested_pixel_count": extracted.requested_pixel_count,
                    "actual_pixel_count": extracted.actual_pixel_count,
                    "window_complete": extracted.complete,
                    **summarize_scl_classes(
                        extracted.values, bad_scl_classes=bad_scl_classes
                    ),
                    "processing_status": status,
                    "processing_note": note,
                }
            )
        inventory.update(
            processing_status="window_read_error" if window_read_failed else "ok",
            processing_note=(
                "At least one requested centered SCL window could not be read."
                if window_read_failed
                else ""
            ),
        )
        return inventory, rows


def summarize_archive(
    input_root: str | Path,
    *,
    station_lat: float,
    station_lon: float,
    station_crs: str,
    window_sizes: Sequence[int],
    bad_scl_classes: Iterable[int] = DEFAULT_BAD_SCL_CLASSES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Summarize every discovered product without collapsing same-date products."""

    validated_windows = tuple(int(size) for size in window_sizes)
    if not validated_windows or len(validated_windows) != len(set(validated_windows)):
        raise ValueError("window_sizes must be a non-empty sequence of unique values.")
    if any(size < 1 or size % 2 == 0 for size in validated_windows):
        raise ValueError("Every candidate window size must be a positive odd integer.")
    bad_classes = frozenset(int(code) for code in bad_scl_classes)
    if not bad_classes.issubset(SCL_CLASS_CODES):
        raise ValueError("diagnostic bad SCL classes must be standard codes 0 through 11.")

    root = Path(input_root)
    inventory_rows: list[dict[str, Any]] = []
    scene_rows: list[dict[str, Any]] = []
    for product in discover_l2a_products(root):
        inventory, scenes = summarize_scene(
            product,
            input_root=root,
            station_lat=station_lat,
            station_lon=station_lon,
            station_crs=station_crs,
            window_sizes=validated_windows,
            bad_scl_classes=bad_classes,
        )
        inventory_rows.append(inventory)
        scene_rows.extend(scenes)
    inventory_rows.sort(
        key=lambda row: (
            str(row.get("acquisition_datetime") or ""),
            str(row.get("product_id") or ""),
        )
    )
    scene_rows.sort(
        key=lambda row: (
            str(row.get("acquisition_datetime") or ""),
            str(row.get("product_id") or ""),
            int(row.get("window_size") or 0),
        )
    )
    return inventory_rows, scene_rows


def assert_portable_output_rows(rows: Iterable[Mapping[str, Any]]) -> None:
    """Reject normal output values that contain absolute or home-directory paths."""

    for row_number, row in enumerate(rows, start=1):
        for column, value in row.items():
            if not isinstance(value, str):
                continue
            if any(marker in value for marker in PROHIBITED_PATH_MARKERS):
                raise ValueError(
                    f"Output row {row_number} column {column!r} contains a home path."
                )
            if column.endswith("_path") and Path(value).is_absolute():
                raise ValueError(
                    f"Output row {row_number} column {column!r} contains an absolute path."
                )


def _write_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str],
    output_path: str | Path,
) -> None:
    assert_portable_output_rows(rows)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=list(columns),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def write_scene_summary(
    rows: Sequence[Mapping[str, Any]], output_path: str | Path
) -> None:
    """Write the deterministic long-format SCL scene/window table."""

    _write_rows(rows, columns=SCENE_SUMMARY_COLUMNS, output_path=output_path)


def write_inventory_summary(
    rows: Sequence[Mapping[str, Any]], output_path: str | Path
) -> None:
    """Write the deterministic product-level L2A/SCL inventory."""

    _write_rows(rows, columns=INVENTORY_COLUMNS, output_path=output_path)
