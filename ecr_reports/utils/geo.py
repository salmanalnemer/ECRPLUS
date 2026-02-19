from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float


def _to_float(v) -> float:
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def point_in_polygon(point: Point, polygon: Iterable[Tuple[float, float]]) -> bool:
    """اختبار Ray Casting: هل النقطة داخل المضلع؟

    polygon: قائمة نقاط (lat, lng) مرتبة. يمكن أن تكون مغلقة أو غير مغلقة.
    """
    pts: List[Tuple[float, float]] = [(float(lat), float(lng)) for lat, lng in polygon]
    if len(pts) < 3:
        return False

    # أغلق المضلع إن لم يكن مغلقاً
    if pts[0] != pts[-1]:
        pts.append(pts[0])

    x = float(point.lng)
    y = float(point.lat)
    inside = False

    for i in range(len(pts) - 1):
        y1, x1 = pts[i][0], pts[i][1]
        y2, x2 = pts[i + 1][0], pts[i + 1][1]

        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
        )
        if intersects:
            inside = not inside

    return inside


def point_in_geojson_polygon(lat, lng, geojson: dict) -> bool:
    """يدعم GeoJSON Polygon فقط.

    الشكل المتوقع:
    {"type": "Polygon", "coordinates": [[[lng,lat],[lng,lat],...]]}
    """
    if not isinstance(geojson, dict):
        return False
    if geojson.get("type") != "Polygon":
        return False
    coords = geojson.get("coordinates")
    if not coords or not isinstance(coords, list) or not coords[0]:
        return False

    ring = coords[0]
    polygon = [(float(p[1]), float(p[0])) for p in ring if isinstance(p, list) and len(p) >= 2]
    return point_in_polygon(Point(_to_float(lat), _to_float(lng)), polygon)
