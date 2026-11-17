"""簡單幾何計算（路線距離），不依賴 PostGIS，小範圍用等距投影已足夠精確。"""
from __future__ import annotations

import math
from collections import defaultdict

EARTH_R = 6371000.0


def project(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """經緯度 → 以公尺為單位的平面座標（等距圓柱投影）。"""
    x = math.radians(lon) * EARTH_R * math.cos(math.radians(lat0))
    y = math.radians(lat) * EARTH_R
    return x, y


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    latitude1, latitude2 = math.radians(lat1), math.radians(lat2)
    latitude_change, longitude_change = latitude2 - latitude1, math.radians(lon2 - lon1)
    distance_factor = (
        math.sin(latitude_change / 2) ** 2
        + math.cos(latitude1) * math.cos(latitude2) * math.sin(longitude_change / 2) ** 2
    )
    return 2 * EARTH_R * math.asin(math.sqrt(distance_factor))


class RouteIndex:
    """先把路段放進格網，查詢時只比對附近格子的路段。"""

    def __init__(self, route: list[tuple[float, float]], cell_m: float = 250.0):
        self.lat0 = sum(point[0] for point in route) / len(route)
        self.pts = []
        for latitude, longitude in route:
            self.pts.append(project(latitude, longitude, self.lat0))
        self.cum = [0.0]
        for (x1, y1), (x2, y2) in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(x2 - x1, y2 - y1))
        self.cell = cell_m
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for segment_index, ((x1, y1), (x2, y2)) in enumerate(zip(self.pts, self.pts[1:])):
            for grid_x in range(int(min(x1, x2) // cell_m), int(max(x1, x2) // cell_m) + 1):
                for grid_y in range(int(min(y1, y2) // cell_m), int(max(y1, y2) // cell_m) + 1):
                    self.grid[(grid_x, grid_y)].append(segment_index)

    @property
    def length(self) -> float:
        return self.cum[-1]

    def locate(self, lat: float, lon: float, max_d: float) -> tuple[float, float] | None:
        """回傳 (點到路線最短距離 m, 沿路線從起點算起的距離 m)；超過 max_d 回傳 None。"""
        point_x, point_y = project(lat, lon, self.lat0)
        search_cells = int(max_d // self.cell) + 1
        grid_x, grid_y = int(point_x // self.cell), int(point_y // self.cell)
        nearby_segments = set()
        for dx in range(-search_cells, search_cells + 1):
            for dy in range(-search_cells, search_cells + 1):
                nearby_segments.update(self.grid.get((grid_x + dx, grid_y + dy), ()))

        closest: tuple[float, float] | None = None
        for segment_index in nearby_segments:
            (x1, y1), (x2, y2) = self.pts[segment_index], self.pts[segment_index + 1]
            dx, dy = x2 - x1, y2 - y1
            segment_length_squared = dx * dx + dy * dy

            # 投影比例限制在 0～1，最近點才會落在線段內，而不是延長線上。
            if segment_length_squared == 0:
                ratio = 0.0
            else:
                ratio = ((point_x - x1) * dx + (point_y - y1) * dy) / segment_length_squared
                ratio = max(0.0, min(1.0, ratio))

            distance = math.hypot(point_x - (x1 + ratio * dx), point_y - (y1 + ratio * dy))
            if distance <= max_d and (closest is None or distance < closest[0]):
                along_route = self.cum[segment_index] + ratio * math.sqrt(segment_length_squared)
                closest = (distance, along_route)
        return closest


def locate_on_route(route: list[tuple[float, float]], lat: float, lon: float) -> tuple[float, float]:
    """回傳 (點到路線的最短距離 m, 沿路線距離 m)。單點查詢用；大量查詢請用 RouteIndex。"""
    hit = RouteIndex(route).locate(lat, lon, 1e9)
    assert hit is not None
    return hit


def route_length(route: list[tuple[float, float]]) -> float:
    total = 0
    for start, end in zip(route, route[1:]):
        total += haversine(start[0], start[1], end[0], end[1])
    return total
