"""即時天氣：中央氣象署開放資料（後端代查，授權碼只放伺服器 .env，App 不會拿到）。

- 即時雨量：O-A0002-001 自動雨量站（全台約 1,300 站、每 10 分鐘更新），取最近測站「過去 1 小時雨量」。
- 降雨機率：F-D0047-xxx 鄉鎮未來 3 天逐 3 小時預報（每個縣市一個資料集），取目前時段。
- 雨天模式建議：過去 1 小時雨量 ≥ 0.5 mm，或目前時段降雨機率 ≥ 60%。
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import truststore
from fastapi import APIRouter, HTTPException, Query

from ..config import settings

truststore.inject_into_ssl()

router = APIRouter(prefix="/api/weather", tags=["天氣"])

BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
SOURCE = "中央氣象署開放資料（O-A0002-001 自動雨量站、F-D0047 鄉鎮天氣預報）"
RAIN_MM = 0.5          # 過去 1 小時雨量達此值視為下雨
POP_RAIN = 60          # 降雨機率達此值建議雨天模式
MAX_STATION_KM = 15    # 最近雨量站超過此距離就不採用即時雨量
OBS_TTL = 600          # 即時雨量快取 10 分鐘（氣象署每 10 分鐘更新）
FC_TTL = 1800          # 預報快取 30 分鐘

# 鄉鎮未來 3 天逐 3 小時預報：每個縣市一個資料集（2026-10-20 逐一呼叫確認）
FORECAST_DATASET = {
    "宜蘭縣": "001", "桃園市": "005", "新竹縣": "009", "苗栗縣": "013", "彰化縣": "017", "南投縣": "021",
    "雲林縣": "025", "嘉義縣": "029", "屏東縣": "033", "臺東縣": "037", "花蓮縣": "041", "澎湖縣": "045",
    "基隆市": "049", "新竹市": "053", "嘉義市": "057", "臺北市": "061", "高雄市": "065", "新北市": "069",
    "臺中市": "073", "臺南市": "077", "連江縣": "081", "金門縣": "085",
}

_lock = threading.Lock()
_cache: dict[Any, tuple[float, Any]] = {}


def _cached(key: Any, ttl: float, fn):
    now = time.monotonic()
    with _lock:
        cached_value = _cache.get(key)
        if cached_value and now - cached_value[0] < ttl:
            return cached_value[1]
    result = fn()
    with _lock:
        _cache[key] = (now, result)
    return result


def _get(dataset: str, **params: str) -> dict[str, Any]:
    r = httpx.get(BASE + dataset, params={"Authorization": settings.cwa_api_key, "format": "JSON", **params},
                  timeout=20)
    if r.status_code in (401, 403):
        raise HTTPException(502, "氣象署授權碼無效，請檢查 .env 的 CWA_API_KEY")
    r.raise_for_status()
    data = r.json()
    if str(data.get("success")) != "true":
        raise HTTPException(502, "氣象署資料暫時無法取得")
    return data["records"]


def _num(v: Any) -> float | None:
    """氣象署以負值（如 -998、-999）表示無資料或儀器異常。"""
    try:
        number = float(v)
    except (TypeError, ValueError):
        return None
    if number >= 0 and math.isfinite(number):
        return number
    return None


def _stations() -> list[dict[str, Any]]:
    def load() -> list[dict[str, Any]]:
        records = _get("O-A0002-001", RainfallElement="Past1hr,Past3hr",
                    GeoInfo="Coordinates,CountyName,TownName")
        stations = []
        for station in records.get("Station", []):
            geography = station.get("GeoInfo", {})
            station_coordinates = None
            for coordinate in geography.get("Coordinates", []):
                if coordinate.get("CoordinateName") == "WGS84":
                    station_coordinates = coordinate
                    break
            if not station_coordinates:
                continue
            rainfall = station.get("RainfallElement", {})
            stations.append({
                "name": station.get("StationName"),
                "id": station.get("StationId"),
                "lat": float(station_coordinates["StationLatitude"]),
                "lon": float(station_coordinates["StationLongitude"]),
                "county": geography.get("CountyName"),
                "town": geography.get("TownName"),
                "obs_time": (station.get("ObsTime") or {}).get("DateTime"),
                "rain_1h": _num((rainfall.get("Past1hr") or {}).get("Precipitation")),
                "rain_3h": _num((rainfall.get("Past3hr") or {}).get("Precipitation")),
            })
        return stations
    return _cached("stations", OBS_TTL, load)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    latitude1, latitude2 = math.radians(lat1), math.radians(lat2)
    distance_factor = (
        math.sin((latitude2 - latitude1) / 2) ** 2
        + math.cos(latitude1) * math.cos(latitude2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(distance_factor))


def _forecast(county: str, town: str) -> dict[str, Any] | None:
    dataset_suffix = FORECAST_DATASET.get(county)
    if not dataset_suffix:
        return None

    def load() -> dict[str, list[dict[str, Any]]]:
        records = _get(f"F-D0047-{dataset_suffix}", LocationName=town, ElementName="3小時降雨機率,天氣現象,溫度")
        locations = (records.get("Locations") or [{}])[0].get("Location") or []
        if not locations:
            return {"periods": [], "temps": []}
        elements_by_name = {}
        for element in locations[0].get("WeatherElement", []):
            elements_by_name[element["ElementName"]] = element["Time"]

        weather_by_start = {}
        for entry in elements_by_name.get("天氣現象", []):
            weather_by_start[entry["StartTime"]] = entry["ElementValue"][0].get("Weather")

        # 降雨機率和天氣文字用起始時間配對。
        periods = []
        for entry in elements_by_name.get("3小時降雨機率", []):
            probability = entry["ElementValue"][0].get("ProbabilityOfPrecipitation")
            periods.append({
                "start": entry["StartTime"],
                "end": entry["EndTime"],
                "pop": _num(probability),
                "weather": weather_by_start.get(entry["StartTime"]),
            })

        temperatures = []
        for entry in elements_by_name.get("溫度", []):
            if entry.get("DataTime"):
                temperatures.append({
                    "time": entry.get("DataTime"),
                    "value": _num(entry["ElementValue"][0].get("Temperature")),
                })
        return {"periods": periods, "temps": temperatures}

    forecast_data = _cached(("fc", dataset_suffix, town), FC_TTL, load)
    now = datetime.now(TW)
    forecast_result: dict[str, Any] | None = None
    periods = forecast_data["periods"]
    for period_index, period in enumerate(periods):
        if _ts(period["end"]) > now:
            next_period = None
            if period_index + 1 < len(periods):
                next_period = periods[period_index + 1]
            forecast_result = {**period, "next": next_period}
            break
    # 氣溫：取時間最接近現在的預報值（每 3 小時一筆）
    temperatures = []
    for entry in forecast_data["temps"]:
        if entry["value"] is not None:
            temperatures.append(entry)
    if temperatures:
        closest_temperature = temperatures[0]
        closest_seconds = abs((_ts(closest_temperature["time"]) - now).total_seconds())
        for entry in temperatures[1:]:
            seconds = abs((_ts(entry["time"]) - now).total_seconds())
            if seconds < closest_seconds:
                closest_temperature = entry
                closest_seconds = seconds
        forecast_result = {**(forecast_result or {}), "temperature": closest_temperature["value"]}
    return forecast_result


TW = timezone(timedelta(hours=8))


def _ts(s: str) -> datetime:
    """轉換氣象署時間；沒有附時區的字串視為台灣時間。"""
    parsed_time = datetime.fromisoformat(s.replace(" ", "T"))
    if parsed_time.tzinfo:
        return parsed_time
    return parsed_time.replace(tzinfo=TW)


@router.get("/now", summary="目前位置的即時雨量與降雨機率（建議晴天／雨天模式）")
def weather_now(lat: float = Query(..., ge=21.5, le=26.5), lon: float = Query(..., ge=118, le=122.5)) -> dict[str, Any]:
    if not settings.cwa_api_key:
        return {"available": False, "reason": "伺服器未設定氣象署授權碼"}
    try:
        stations = _stations()
        closest_station = min(stations, key=lambda s: _km(lat, lon, s["lat"], s["lon"]), default=None)
        if closest_station is None:
            raise HTTPException(502, "氣象署雨量資料暫時無法取得")
        distance_km = _km(lat, lon, closest_station["lat"], closest_station["lon"])
        forecast = _forecast(closest_station["county"], closest_station["town"])
    except httpx.HTTPError as e:
        raise HTTPException(502, f"氣象署服務暫時無法使用：{e.__class__.__name__}") from e

    hourly_rain = closest_station["rain_1h"] if distance_km <= MAX_STATION_KM else None
    raining = hourly_rain is not None and hourly_rain >= RAIN_MM
    rain_probability = forecast.get("pop") if forecast else None
    if raining:
        weather_mode, reason = "rain", f"附近測站過去 1 小時雨量 {hourly_rain:g} mm"
    elif rain_probability is not None and rain_probability >= POP_RAIN:
        weather_mode, reason = "rain", f"目前時段降雨機率 {rain_probability:g}%"
    else:
        weather_mode = "clear"
        reason = "附近沒有下雨"
        if rain_probability is not None:
            reason += f"，降雨機率 {rain_probability:g}%"
    return {
        "available": True,
        "suggested_mode": weather_mode,
        "reason": reason,
        "raining": raining,
        "rain_1h_mm": hourly_rain,
        "pop_percent": rain_probability,
        "temperature": forecast.get("temperature") if forecast else None,
        "station": {
            "name": closest_station["name"],
            "id": closest_station["id"],
            "county": closest_station["county"],
            "town": closest_station["town"],
            "distance_km": round(distance_km, 1),
            "obs_time": closest_station["obs_time"],
        },
        "forecast": forecast,
        "thresholds": {"rain_mm": RAIN_MM, "pop_percent": POP_RAIN},
        "source": SOURCE,
    }
