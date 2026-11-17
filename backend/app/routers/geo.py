"""地名搜尋與路線規劃（後端代查 OpenStreetMap 服務，App 不直接連外部服務）。

- 地名搜尋：Nominatim（OSM 官方），依使用政策：可識別的 User-Agent、每秒最多 1 次、結果快取。
- 路線：FOSSGIS 的 OSRM（routing.openstreetmap.de），支援步行／自行車／汽車。
"""
from __future__ import annotations

import math
import threading
import time
from functools import lru_cache
from typing import Any, Literal

import httpx
import truststore
from fastapi import APIRouter, HTTPException, Query

truststore.inject_into_ssl()  # 使用作業系統憑證庫（部分防毒軟體會攔截 TLS）

router = APIRouter(prefix="/api/geo", tags=["地名與路線"])

UA = "TrafficSafetyApp/0.1 (university database course project; https://github.com)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = {"foot": "https://routing.openstreetmap.de/routed-foot/route/v1/foot",
        "bike": "https://routing.openstreetmap.de/routed-bike/route/v1/bike",
        "car": "https://routing.openstreetmap.de/routed-car/route/v1/driving"}
MAX_POINTS = 1800

_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    """Nominatim 使用政策：每秒最多 1 次請求。"""
    global _last_call
    with _lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


@lru_cache(maxsize=512)
def _search(q: str, lat: float | None, lon: float | None) -> tuple[dict[str, Any], ...]:
    params: dict[str, Any] = {"q": q, "format": "jsonv2", "countrycodes": "tw", "limit": 8,
                              "accept-language": "zh-TW", "addressdetails": 1}
    if lat is not None and lon is not None:  # 偏好目前位置附近的結果
        params["viewbox"] = f"{lon - 0.5},{lat + 0.5},{lon + 0.5},{lat - 0.5}"
    _throttle()
    response = httpx.get(NOMINATIM, params=params, headers={"User-Agent": UA}, timeout=15)
    response.raise_for_status()
    places = []
    for place in response.json():
        address = place.get("address", {})
        city = address.get("city") or address.get("county") or address.get("state")
        district = address.get("suburb") or address.get("city_district") or address.get("town")
        area = "".join(part for part in (city, district) if part)
        places.append({
            "name": place.get("name") or place["display_name"].split(",")[0],
            "area": area,
            "address": place["display_name"],
            "lat": float(place["lat"]),
            "lon": float(place["lon"]),
            "kind": place.get("type"),
        })
    return tuple(places)


@router.get("/search", summary="搜尋地名（台灣）")
def search(q: str = Query(..., min_length=1, max_length=100), lat: float | None = None,
           lon: float | None = None) -> list[dict[str, Any]]:
    try:
        return list(_search(q.strip(), round(lat, 2) if lat else None, round(lon, 2) if lon else None))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"地名搜尋服務暫時無法使用：{e.__class__.__name__}") from e


def _simplify(pts: list[tuple[float, float]], tol_m: float) -> list[tuple[float, float]]:
    """Douglas–Peucker 簡化折線（公尺），長路線點數太多時使用。"""
    if len(pts) < 3:
        return pts
    lat0 = math.radians(pts[0][0])
    projected_points = []
    for latitude, longitude in pts:
        x = math.radians(longitude) * 6371000 * math.cos(lat0)
        y = math.radians(latitude) * 6371000
        projected_points.append((x, y))
    keep_point = [False] * len(pts)
    keep_point[0] = keep_point[-1] = True
    segments_to_check = [(0, len(pts) - 1)]
    while segments_to_check:
        start_index, end_index = segments_to_check.pop()
        (x1, y1), (x2, y2) = projected_points[start_index], projected_points[end_index]
        dx, dy = x2 - x1, y2 - y1
        segment_length = math.hypot(dx, dy) or 1e-9
        furthest_distance, furthest_index = 0.0, -1
        for point_index in range(start_index + 1, end_index):
            point_x, point_y = projected_points[point_index]
            distance = abs(dy * (point_x - x1) - dx * (point_y - y1)) / segment_length
            if distance > furthest_distance:
                furthest_distance, furthest_index = distance, point_index
        if furthest_distance > tol_m and furthest_index > 0:
            keep_point[furthest_index] = True
            segments_to_check += [(start_index, furthest_index), (furthest_index, end_index)]
    return [point for point, should_keep in zip(pts, keep_point) if should_keep]


@lru_cache(maxsize=256)
def _route(a: tuple[float, float], b: tuple[float, float], mode: str) -> dict[str, Any]:
    url = f"{OSRM[mode]}/{a[1]},{a[0]};{b[1]},{b[0]}"
    response = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise HTTPException(404, "找不到路線")
    route_data = data["routes"][0]
    route_points = [(round(latitude, 6), round(longitude, 6)) for longitude, latitude in route_data["geometry"]["coordinates"]]
    tolerance = 2.0
    while len(route_points) > MAX_POINTS:
        route_points = _simplify(route_points, tolerance)
        tolerance *= 2
    return {"distance_m": round(route_data["distance"]), "duration_s": round(route_data["duration"]), "points": route_points}


@router.get("/route", summary="計算路線（步行／自行車／汽車）")
def route(from_: str = Query(..., alias="from", description="起點 lat,lon"),
          to: str = Query(..., description="終點 lat,lon"),
          mode: Literal["foot", "bike", "car"] = "foot") -> dict[str, Any]:
    try:
        start_point = tuple(round(float(coordinate), 5) for coordinate in from_.split(","))
        end_point = tuple(round(float(coordinate), 5) for coordinate in to.split(","))
        assert len(start_point) == 2 and len(end_point) == 2
    except (ValueError, AssertionError) as e:
        raise HTTPException(422, "座標格式應為 lat,lon") from e
    try:
        result = _route(start_point, end_point, mode)  # type: ignore[arg-type]
    except httpx.HTTPError as e:
        raise HTTPException(502, f"路線服務暫時無法使用：{e.__class__.__name__}") from e
    return {**result, "mode": mode, "points": [list(point) for point in result["points"]]}
