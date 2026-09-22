"""Fixed Vombsjon pelagic field-sampling polygon and its raster support.

The v1.1 pre-performance amendment replaces the per-date actual-GPS 3x3 window
(with a nominal-point fallback) as the *primary* field-validation support. In
its place one fixed pelagic sampling-area polygon is used identically for every
field date.

The polygon is derived deterministically from the committed field source alone:

* only rows with ``coordinate_source_for_matchup == measured_GPS`` **and**
  ``coordinate_qc == ok`` contribute coordinates;
* the two unresolved 2020 longitude flags are excluded from construction and
  the reason is recorded;
* the paper nominal station is added as an anchor point;
* the accepted coordinates are projected to a metric CRS and their convex hull
  is taken, with **no buffer**; and
* the result is stored in both the metric CRS and WGS84.

Nothing here is tuned. No satellite value, no field Chl-a value and no
performance result of any kind enters the construction.

This module contains only geometry and grid arithmetic. It reads no raster and
applies no QA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from pyproj import CRS, Transformer


class FieldPolygonError(ValueError):
    """Raised when the fixed sampling polygon cannot be built without guessing."""


# A pixel centre is counted as inside when it is strictly inside the polygon or
# lies on an edge to within this distance. It is a numerical guard against
# floating-point round-off on an exact edge hit, not a buffer: at 1 nanometre it
# can never add a pixel whose centre is meaningfully outside the hull.
EDGE_TOLERANCE_M = 1e-9


# ---------------------------------------------------------------------------
# Planar geometry primitives
# ---------------------------------------------------------------------------


def _cross(
    origin: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (
        first[1] - origin[1]
    ) * (second[0] - origin[0])


def convex_hull(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Return the counter-clockwise convex hull of planar points.

    Andrew's monotone chain on lexicographically sorted unique coordinates.
    Collinear points are dropped, so the result is the minimal vertex set and
    is reproducible byte for byte from the same inputs. No external hull
    library is used, so the vertex order does not depend on a solver's
    tie-breaking.
    """

    unique = sorted({(float(x), float(y)) for x, y in points})
    if len(unique) < 3:
        raise FieldPolygonError(
            f"A convex hull needs at least three distinct coordinates; got "
            f"{len(unique)}."
        )

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = tuple(lower[:-1] + upper[:-1])
    if len(hull) < 3:
        raise FieldPolygonError(
            "The accepted coordinates are collinear and enclose no area."
        )
    return hull


def polygon_area(vertices: Sequence[tuple[float, float]]) -> float:
    """Return the absolute shoelace area of a simple polygon, in CRS units."""

    total = 0.0
    count = len(vertices)
    for index in range(count):
        x1, y1 = vertices[index]
        x2, y2 = vertices[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_centroid(
    vertices: Sequence[tuple[float, float]]
) -> tuple[float, float]:
    """Return the area centroid of a simple polygon, in CRS units."""

    signed = 0.0
    cx = 0.0
    cy = 0.0
    count = len(vertices)
    for index in range(count):
        x1, y1 = vertices[index]
        x2, y2 = vertices[(index + 1) % count]
        step = x1 * y2 - x2 * y1
        signed += step
        cx += (x1 + x2) * step
        cy += (y1 + y2) * step
    signed /= 2.0
    if signed == 0:
        raise FieldPolygonError("Polygon centroid is undefined for zero area.")
    return cx / (6.0 * signed), cy / (6.0 * signed)


def points_in_polygon(
    x: np.ndarray,
    y: np.ndarray,
    vertices: Sequence[tuple[float, float]],
    *,
    edge_tolerance: float = EDGE_TOLERANCE_M,
) -> np.ndarray:
    """Return which planar points lie inside a simple polygon.

    Crossing-number test with a half-open rule in ``y``, so a point level with a
    vertex is counted exactly once, plus an explicit on-edge test. Both are
    deterministic: the same coordinates always give the same answer.
    """

    xs = np.asarray(x, dtype="float64")
    ys = np.asarray(y, dtype="float64")
    if xs.shape != ys.shape:
        raise FieldPolygonError(
            f"Point coordinate arrays must share one shape; got {xs.shape} and "
            f"{ys.shape}."
        )
    inside = np.zeros(xs.shape, dtype=bool)
    on_edge = np.zeros(xs.shape, dtype=bool)
    count = len(vertices)
    tolerance_squared = float(edge_tolerance) ** 2

    for index in range(count):
        x1, y1 = (float(value) for value in vertices[index])
        x2, y2 = (float(value) for value in vertices[(index + 1) % count])

        straddles = (y1 > ys) != (y2 > ys)
        if y2 != y1:
            with np.errstate(divide="ignore", invalid="ignore"):
                x_at_y = x1 + (ys - y1) * (x2 - x1) / (y2 - y1)
            inside ^= straddles & (xs < x_at_y)

        edge_x = x2 - x1
        edge_y = y2 - y1
        length_squared = edge_x * edge_x + edge_y * edge_y
        if length_squared > 0:
            offset_x = xs - x1
            offset_y = ys - y1
            projection = np.clip(
                (offset_x * edge_x + offset_y * edge_y) / length_squared, 0.0, 1.0
            )
            gap_x = offset_x - projection * edge_x
            gap_y = offset_y - projection * edge_y
            on_edge |= (gap_x * gap_x + gap_y * gap_y) <= tolerance_squared

    return inside | on_edge


def utm_epsg_for(longitude: float, latitude: float) -> str:
    """Return the WGS84 UTM EPSG code containing one coordinate."""

    zone = int(math.floor((float(longitude) + 180.0) / 6.0)) + 1
    if not 1 <= zone <= 60:
        raise FieldPolygonError(f"Longitude {longitude} is outside the UTM domain.")
    return f"EPSG:{32600 + zone}" if float(latitude) >= 0 else f"EPSG:{32700 + zone}"


# ---------------------------------------------------------------------------
# Polygon construction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolygonSourcePoint:
    """One coordinate offered to polygon construction, accepted or not."""

    label: str
    role: str
    latitude: float | None
    longitude: float | None
    accepted: bool
    reason: str
    coordinate_source: str | None = None
    coordinate_qc: str | None = None


@dataclass(frozen=True)
class FieldSamplingArea:
    """The fixed Vombsjon pelagic sampling polygon and its provenance."""

    rule_id: str
    metric_crs: str
    geographic_crs: str
    vertices_metric: tuple[tuple[float, float], ...]
    vertices_wgs84: tuple[tuple[float, float], ...]
    centroid_metric: tuple[float, float]
    centroid_wgs84: tuple[float, float]
    area_m2: float
    source_points: tuple[PolygonSourcePoint, ...]
    buffer_m: float
    clipped_to_geometry: str | None
    nominal_anchor: tuple[float, float]
    nominal_is_vertex: bool
    nominal_inside: bool
    field_source_relative_path: str
    field_source_sha256: str

    @property
    def vertex_count(self) -> int:
        return len(self.vertices_metric)

    @property
    def area_km2(self) -> float:
        return self.area_m2 / 1.0e6

    @property
    def accepted_points(self) -> tuple[PolygonSourcePoint, ...]:
        return tuple(point for point in self.source_points if point.accepted)

    @property
    def excluded_points(self) -> tuple[PolygonSourcePoint, ...]:
        return tuple(point for point in self.source_points if not point.accepted)


def build_field_sampling_area(
    offered: Sequence[PolygonSourcePoint],
    *,
    rule_id: str,
    metric_crs: str,
    geographic_crs: str = "EPSG:4326",
    nominal_latitude: float,
    nominal_longitude: float,
    buffer_m: float = 0.0,
    clip_geometry: Sequence[tuple[float, float]] | None = None,
    clip_geometry_identity: str | None = None,
    field_source_relative_path: str,
    field_source_sha256: str,
) -> FieldSamplingArea:
    """Build the fixed pelagic polygon from already-filtered source points.

    ``offered`` carries every coordinate that was considered, with its accept
    or reject reason, so the exclusions are part of the output rather than an
    invisible filter. ``buffer_m`` must remain zero for the primary polygon:
    any non-zero value would be an untuned-but-arbitrary size choice, which the
    amendment forbids.
    """

    if buffer_m != 0.0:
        raise FieldPolygonError(
            "The primary Vombsjon sampling polygon is the unbuffered convex "
            f"hull; a {buffer_m} m buffer would be an arbitrary size choice."
        )
    if clip_geometry is not None and not clip_geometry_identity:
        raise FieldPolygonError(
            "Clipping the hull requires an unambiguous identity and provenance "
            "for the clipping geometry."
        )

    accepted = [point for point in offered if point.accepted]
    if len(accepted) < 3:
        raise FieldPolygonError(
            f"Only {len(accepted)} coordinate(s) were accepted for polygon "
            "construction; at least three are required."
        )

    derived_epsg = utm_epsg_for(nominal_longitude, nominal_latitude)
    if CRS.from_user_input(metric_crs) != CRS.from_user_input(derived_epsg):
        raise FieldPolygonError(
            f"Configured metric CRS {metric_crs!r} is not the UTM zone that "
            f"contains the nominal station ({derived_epsg}); the audit does not "
            "silently project into a different zone."
        )

    to_metric = Transformer.from_crs(
        CRS.from_user_input(geographic_crs),
        CRS.from_user_input(metric_crs),
        always_xy=True,
    )
    to_geographic = Transformer.from_crs(
        CRS.from_user_input(metric_crs),
        CRS.from_user_input(geographic_crs),
        always_xy=True,
    )

    projected: list[tuple[float, float]] = []
    for point in accepted:
        if point.latitude is None or point.longitude is None:
            raise FieldPolygonError(
                f"Accepted polygon point {point.label!r} has no coordinate."
            )
        x, y = to_metric.transform(float(point.longitude), float(point.latitude))
        if not (math.isfinite(x) and math.isfinite(y)):
            raise FieldPolygonError(
                f"Projecting polygon point {point.label!r} gave a non-finite "
                "coordinate."
            )
        projected.append((float(x), float(y)))

    hull = convex_hull(projected)
    if clip_geometry is not None:
        raise FieldPolygonError(
            "Clipping to an external lake geometry is not implemented; this "
            "repository holds no authoritative Vombsjon open-water polygon and "
            "the audit does not invent one."
        )

    centroid_metric = polygon_centroid(hull)
    area = polygon_area(hull)

    vertices_wgs84: list[tuple[float, float]] = []
    for x, y in hull:
        longitude, latitude = to_geographic.transform(x, y)
        vertices_wgs84.append((float(longitude), float(latitude)))
    centroid_longitude, centroid_latitude = to_geographic.transform(
        centroid_metric[0], centroid_metric[1]
    )

    nominal_x, nominal_y = to_metric.transform(
        float(nominal_longitude), float(nominal_latitude)
    )
    nominal_is_vertex = any(
        math.isclose(nominal_x, vx, abs_tol=1e-6)
        and math.isclose(nominal_y, vy, abs_tol=1e-6)
        for vx, vy in hull
    )
    nominal_inside = bool(
        points_in_polygon(
            np.array([nominal_x]), np.array([nominal_y]), hull
        )[0]
    )

    return FieldSamplingArea(
        rule_id=str(rule_id),
        metric_crs=str(metric_crs),
        geographic_crs=str(geographic_crs),
        vertices_metric=hull,
        vertices_wgs84=tuple(vertices_wgs84),
        centroid_metric=(float(centroid_metric[0]), float(centroid_metric[1])),
        centroid_wgs84=(float(centroid_longitude), float(centroid_latitude)),
        area_m2=float(area),
        source_points=tuple(offered),
        buffer_m=0.0,
        clipped_to_geometry=clip_geometry_identity,
        nominal_anchor=(float(nominal_longitude), float(nominal_latitude)),
        nominal_is_vertex=nominal_is_vertex,
        nominal_inside=nominal_inside,
        field_source_relative_path=str(field_source_relative_path),
        field_source_sha256=str(field_source_sha256),
    )


# ---------------------------------------------------------------------------
# Raster support on the common 20 m target grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolygonGridSupport:
    """The target-grid pixels of the polygon, and the square window holding them.

    The polygon is read through the smallest odd, centre-anchored square window
    that fully contains it, so the existing station-centred readers are reused
    unchanged. ``mask`` selects, inside that square, exactly the pixels whose
    centre lies in the polygon.
    """

    centre_row: int
    centre_col: int
    window_size: int
    mask: np.ndarray
    total_pixel_count: int
    bbox_row_min: int
    bbox_row_max: int
    bbox_col_min: int
    bbox_col_max: int
    vertices_raster_crs: tuple[tuple[float, float], ...]
    coordinate_path: str

    @property
    def window_pixel_count(self) -> int:
        return self.window_size * self.window_size


def polygon_grid_support(
    area: FieldSamplingArea,
    *,
    transform: Any,
    raster_crs: str,
    raster_width: int,
    raster_height: int,
) -> PolygonGridSupport:
    """Resolve the polygon onto one raster's target grid, deterministically.

    Pixel inclusion is by pixel-centre containment. The pixel count this
    returns is the denominator of the frozen fractional support rule, so it is
    derived from the grid geometry alone and never from the data values.
    """

    if CRS.from_user_input(raster_crs) == CRS.from_user_input(area.metric_crs):
        vertices = area.vertices_metric
        coordinate_path = "polygon_metric_crs_matches_raster_crs"
    else:
        transformer = Transformer.from_crs(
            CRS.from_user_input(area.geographic_crs),
            CRS.from_user_input(raster_crs),
            always_xy=True,
        )
        projected: list[tuple[float, float]] = []
        for longitude, latitude in area.vertices_wgs84:
            x, y = transformer.transform(longitude, latitude)
            if not (math.isfinite(x) and math.isfinite(y)):
                raise FieldPolygonError(
                    "Projecting a polygon vertex into the raster CRS gave a "
                    "non-finite coordinate."
                )
            projected.append((float(x), float(y)))
        vertices = tuple(projected)
        coordinate_path = "polygon_wgs84_reprojected_to_raster_crs"

    pixel_x = float(transform.a)
    pixel_y = float(transform.e)
    origin_x = float(transform.c)
    origin_y = float(transform.f)
    if pixel_x == 0 or pixel_y == 0:
        raise FieldPolygonError("Raster transform has a zero pixel size.")
    if abs(float(transform.b)) > 0 or abs(float(transform.d)) > 0:
        raise FieldPolygonError(
            "Polygon support requires an axis-aligned raster transform."
        )

    xs = [x for x, _ in vertices]
    ys = [y for _, y in vertices]
    corner_cols = [(value - origin_x) / pixel_x for value in (min(xs), max(xs))]
    corner_rows = [(value - origin_y) / pixel_y for value in (min(ys), max(ys))]
    # One pixel of margin so a centre just inside the boundary is never missed.
    col_min = int(math.floor(min(corner_cols))) - 1
    col_max = int(math.ceil(max(corner_cols))) + 1
    row_min = int(math.floor(min(corner_rows))) - 1
    row_max = int(math.ceil(max(corner_rows))) + 1

    rows = np.arange(row_min, row_max + 1)
    cols = np.arange(col_min, col_max + 1)
    if rows.size == 0 or cols.size == 0:
        raise FieldPolygonError("Polygon bounding box covers no target pixel.")
    col_grid, row_grid = np.meshgrid(cols, rows)
    centre_x = origin_x + (col_grid + 0.5) * pixel_x
    centre_y = origin_y + (row_grid + 0.5) * pixel_y
    inside = points_in_polygon(centre_x, centre_y, vertices)
    if not inside.any():
        raise FieldPolygonError(
            "No target-grid pixel centre falls inside the fixed sampling "
            "polygon; the polygon and the raster grid do not overlap."
        )

    inside_rows = row_grid[inside]
    inside_cols = col_grid[inside]
    bbox_row_min = int(inside_rows.min())
    bbox_row_max = int(inside_rows.max())
    bbox_col_min = int(inside_cols.min())
    bbox_col_max = int(inside_cols.max())
    if (
        bbox_row_max < 0
        or bbox_col_max < 0
        or bbox_row_min >= int(raster_height)
        or bbox_col_min >= int(raster_width)
    ):
        raise FieldPolygonError(
            f"The fixed sampling polygon covers rows {bbox_row_min}..{bbox_row_max} "
            f"and columns {bbox_col_min}..{bbox_col_max}, which lie entirely "
            f"outside the {raster_height}x{raster_width} raster."
        )

    centre_row = (bbox_row_min + bbox_row_max) // 2
    centre_col = (bbox_col_min + bbox_col_max) // 2
    half = max(
        centre_row - bbox_row_min,
        bbox_row_max - centre_row,
        centre_col - bbox_col_min,
        bbox_col_max - centre_col,
    )
    window_size = 2 * half + 1

    window_rows = np.arange(centre_row - half, centre_row + half + 1)
    window_cols = np.arange(centre_col - half, centre_col + half + 1)
    window_col_grid, window_row_grid = np.meshgrid(window_cols, window_rows)
    window_centre_x = origin_x + (window_col_grid + 0.5) * pixel_x
    window_centre_y = origin_y + (window_row_grid + 0.5) * pixel_y
    mask = points_in_polygon(window_centre_x, window_centre_y, vertices)
    total = int(np.count_nonzero(mask))
    if total != int(np.count_nonzero(inside)):
        raise FieldPolygonError(
            "The enclosing square window does not contain every polygon pixel "
            f"({total} of {int(np.count_nonzero(inside))}); the audit refuses "
            "to summarize a truncated polygon."
        )

    return PolygonGridSupport(
        centre_row=centre_row,
        centre_col=centre_col,
        window_size=window_size,
        mask=mask,
        total_pixel_count=total,
        bbox_row_min=bbox_row_min,
        bbox_row_max=bbox_row_max,
        bbox_col_min=bbox_col_min,
        bbox_col_max=bbox_col_max,
        vertices_raster_crs=tuple(vertices),
        coordinate_path=coordinate_path,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def geojson_feature_collection(area: FieldSamplingArea) -> dict[str, Any]:
    """Return the polygon as a WGS84 GeoJSON FeatureCollection."""

    ring = [list(vertex) for vertex in area.vertices_wgs84]
    ring.append(list(area.vertices_wgs84[0]))
    return {
        "type": "FeatureCollection",
        "name": "vombsjon_field_sampling_area",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "rule_id": area.rule_id,
                    "role": "primary_field_validation_support",
                    "construction": (
                        "unbuffered_convex_hull_of_accepted_measured_gps_plus_"
                        "nominal_anchor"
                    ),
                    "metric_crs": area.metric_crs,
                    "geographic_crs": area.geographic_crs,
                    "buffer_m": area.buffer_m,
                    "clipped_to_geometry": area.clipped_to_geometry,
                    "vertex_count": area.vertex_count,
                    "area_m2": area.area_m2,
                    "area_km2": area.area_km2,
                    "centroid_longitude": area.centroid_wgs84[0],
                    "centroid_latitude": area.centroid_wgs84[1],
                    "accepted_point_count": len(area.accepted_points),
                    "excluded_point_count": len(area.excluded_points),
                    "nominal_anchor_longitude": area.nominal_anchor[0],
                    "nominal_anchor_latitude": area.nominal_anchor[1],
                    "nominal_is_vertex": area.nominal_is_vertex,
                    "nominal_inside": area.nominal_inside,
                    "field_source_relative_path": area.field_source_relative_path,
                    "field_source_sha256": area.field_source_sha256,
                    "tuned_from_performance": False,
                },
            }
        ],
    }


def provenance_rows(area: FieldSamplingArea) -> list[dict[str, Any]]:
    """Return one auditable row per offered coordinate plus the hull vertices."""

    rows: list[dict[str, Any]] = []
    for point in area.source_points:
        rows.append(
            {
                "record_type": "source_point",
                "label": point.label,
                "role": point.role,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "coordinate_source_for_matchup": point.coordinate_source,
                "coordinate_qc": point.coordinate_qc,
                "accepted_for_polygon": point.accepted,
                "reason": point.reason,
                "rule_id": area.rule_id,
                "field_source_relative_path": area.field_source_relative_path,
                "field_source_sha256": area.field_source_sha256,
            }
        )
    for index, ((x, y), (longitude, latitude)) in enumerate(
        zip(area.vertices_metric, area.vertices_wgs84)
    ):
        rows.append(
            {
                "record_type": "hull_vertex",
                "label": f"vertex_{index + 1}",
                "role": "polygon_vertex",
                "latitude": latitude,
                "longitude": longitude,
                "metric_x": x,
                "metric_y": y,
                "metric_crs": area.metric_crs,
                "accepted_for_polygon": True,
                "reason": "convex_hull_vertex",
                "rule_id": area.rule_id,
                "field_source_relative_path": area.field_source_relative_path,
                "field_source_sha256": area.field_source_sha256,
            }
        )
    rows.append(
        {
            "record_type": "polygon_summary",
            "label": "vombsjon_field_sampling_area",
            "role": "primary_field_validation_support",
            "latitude": area.centroid_wgs84[1],
            "longitude": area.centroid_wgs84[0],
            "metric_x": area.centroid_metric[0],
            "metric_y": area.centroid_metric[1],
            "metric_crs": area.metric_crs,
            "accepted_for_polygon": True,
            "reason": "unbuffered_convex_hull",
            "vertex_count": area.vertex_count,
            "area_m2": area.area_m2,
            "area_km2": area.area_km2,
            "buffer_m": area.buffer_m,
            "clipped_to_geometry": area.clipped_to_geometry,
            "accepted_point_count": len(area.accepted_points),
            "excluded_point_count": len(area.excluded_points),
            "nominal_anchor_latitude": area.nominal_anchor[1],
            "nominal_anchor_longitude": area.nominal_anchor[0],
            "nominal_is_vertex": area.nominal_is_vertex,
            "nominal_inside": area.nominal_inside,
            "rule_id": area.rule_id,
            "field_source_relative_path": area.field_source_relative_path,
            "field_source_sha256": area.field_source_sha256,
            "tuned_from_performance": False,
        }
    )
    return rows


def area_summary(area: FieldSamplingArea) -> dict[str, Any]:
    """Return the manifest-facing summary of the fixed polygon."""

    return {
        "rule_id": area.rule_id,
        "role": "primary_field_validation_support",
        "construction": (
            "unbuffered_convex_hull_of_accepted_measured_gps_plus_nominal_anchor"
        ),
        "metric_crs": area.metric_crs,
        "geographic_crs": area.geographic_crs,
        "buffer_m": area.buffer_m,
        "clipped_to_geometry": area.clipped_to_geometry,
        "vertex_count": area.vertex_count,
        "area_m2": area.area_m2,
        "area_km2": area.area_km2,
        "centroid_wgs84": {
            "longitude": area.centroid_wgs84[0],
            "latitude": area.centroid_wgs84[1],
        },
        "centroid_metric": {
            "x": area.centroid_metric[0],
            "y": area.centroid_metric[1],
        },
        "accepted_point_count": len(area.accepted_points),
        "accepted_point_labels": [point.label for point in area.accepted_points],
        "excluded_point_count": len(area.excluded_points),
        "excluded_points": [
            {"label": point.label, "reason": point.reason}
            for point in area.excluded_points
        ],
        "nominal_anchor": {
            "longitude": area.nominal_anchor[0],
            "latitude": area.nominal_anchor[1],
        },
        "nominal_is_vertex": area.nominal_is_vertex,
        "nominal_inside": area.nominal_inside,
        "vertices_wgs84": [list(vertex) for vertex in area.vertices_wgs84],
        "field_source_relative_path": area.field_source_relative_path,
        "field_source_sha256": area.field_source_sha256,
        "tuned_from_satellite_or_field_performance": False,
    }
