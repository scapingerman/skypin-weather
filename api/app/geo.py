from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon, shape


def geojson_polygon_to_shapely(geometry: dict[str, Any]) -> Polygon:
    g = shape(geometry)
    if not isinstance(g, Polygon):
        raise ValueError("Geometry must be a Polygon")
    if not g.is_valid:
        g = g.buffer(0)
    if g.is_empty:
        raise ValueError("Polygon is empty")
    return g


def bbox_too_large(poly: Polygon, max_span_deg: float = 6.0) -> bool:
    minx, miny, maxx, maxy = poly.bounds
    return (maxx - minx) > max_span_deg or (maxy - miny) > max_span_deg
