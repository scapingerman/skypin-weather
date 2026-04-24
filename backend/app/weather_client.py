"""
Open-Meteo client (free, no API key).

Docs: https://open-meteo.com/en/docs
License: CC-BY 4.0. Attribution: "Weather data by Open-Meteo.com".

Returns real current weather + 7-day past precipitation.
Falls back to None on any error → caller must use mock.
"""
import logging
import threading
import time
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("skyping.weather")

_URL = "https://api.open-meteo.com/v1/forecast"
_TTL_S = 3600  # 1 hour cache TTL
_TIMEOUT_S = 5.0
_ROUND = 1  # ~11 km cache bucket, plenty for MVP

# Thread-safe in-memory cache: {(lat_round, lon_round): (timestamp, payload)}
_CACHE: Dict[tuple, tuple] = {}
_LOCK = threading.Lock()


def _cache_key(lat: float, lon: float) -> tuple:
    return (round(lat, _ROUND), round(lon, _ROUND))


def fetch_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Live weather for a point. Cached 1h per ~11km bucket.

    Returns:
        {
          "temperature_c": float,      # current 2m air temp
          "wind_kmh": float,           # current 10m wind
          "precip_7d_mm": float,       # sum of last 7 days
          "source": "open-meteo",
          "fetched_at": epoch_seconds,
        }
        or None if request failed.
    """
    key = _cache_key(lat, lon)
    now = time.time()

    with _LOCK:
        cached = _CACHE.get(key)
        if cached and (now - cached[0]) < _TTL_S:
            return cached[1]

    try:
        r = httpx.get(
            _URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m",
                "daily": "precipitation_sum",
                "past_days": 7,
                "forecast_days": 1,
                "wind_speed_unit": "kmh",
                "timezone": "UTC",
            },
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()

        current = data.get("current") or {}
        daily = data.get("daily") or {}

        temp = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")
        precip_list = daily.get("precipitation_sum") or []
        precip_7d = sum(float(v) for v in precip_list[:7] if v is not None)

        if temp is None or wind is None:
            raise ValueError("Open-Meteo returned null current values")

        result = {
            "temperature_c": round(float(temp), 1),
            "wind_kmh": round(float(wind), 1),
            "precip_7d_mm": round(precip_7d, 1),
            "source": "open-meteo",
            "fetched_at": now,
        }
        with _LOCK:
            _CACHE[key] = (now, result)
        log.info("open-meteo OK lat=%.3f lon=%.3f t=%s wind=%s precip7d=%s",
                 lat, lon, result["temperature_c"], result["wind_kmh"], result["precip_7d_mm"])
        return result
    except Exception as e:
        log.warning("open-meteo FAIL lat=%.3f lon=%.3f err=%s", lat, lon, e)
        return None


_SM_CACHE: Dict[tuple, tuple] = {}
_SM_TTL_S = 3 * 3600  # 3h: humedad cambia lento

# Pesos por espesor (cm) de cada capa: media ponderada 0-27 cm (raíces).
_SM_LAYERS = [
    ("soil_moisture_0_to_1cm", 1),
    ("soil_moisture_1_to_3cm", 2),
    ("soil_moisture_3_to_9cm", 6),
    ("soil_moisture_9_to_27cm", 18),
]


def fetch_soil_moisture(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Humedad de suelo volumétrica (%) para un punto.

    Returns:
        {
          "current_pct": float,         # % volumétrico, media ponderada 0-27cm
          "trend": [{"date": "YYYY-MM-DD", "value": float}, ...],  # 30 días
          "source": "era5-land",
          "fetched_at": epoch,
        }
        o None si falló la llamada / datos insuficientes.
    """
    key = _cache_key(lat, lon)
    now = time.time()

    with _LOCK:
        cached = _SM_CACHE.get(key)
        if cached and (now - cached[0]) < _SM_TTL_S:
            return cached[1]

    try:
        r = httpx.get(
            _URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(name for name, _ in _SM_LAYERS),
                "past_days": 30,
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise ValueError("No hourly data returned")

        # Media ponderada por hora (m³/m³ → %)
        total_thickness = sum(t for _, t in _SM_LAYERS)
        hourly_pct: list = []
        for i in range(len(times)):
            num = 0.0
            denom = 0.0
            for name, thick in _SM_LAYERS:
                series = hourly.get(name) or []
                if i < len(series) and series[i] is not None:
                    num += float(series[i]) * thick
                    denom += thick
            if denom > 0:
                hourly_pct.append(num / denom * 100.0)  # volumetric %
            else:
                hourly_pct.append(None)

        # Valor actual = última hora no-null
        current = next((v for v in reversed(hourly_pct) if v is not None), None)
        if current is None:
            raise ValueError("All hourly soil-moisture values are null")

        # Serie diaria (promedio por día)
        from collections import OrderedDict
        by_day: "OrderedDict[str, list]" = OrderedDict()
        for t, v in zip(times, hourly_pct):
            if v is None:
                continue
            day = t[:10]
            by_day.setdefault(day, []).append(v)

        trend = [
            {"date": d, "value": round(sum(vs) / len(vs), 2)}
            for d, vs in by_day.items()
        ][-30:]

        result = {
            "current_pct": round(current, 2),
            "trend": trend,
            "source": "era5-land",
            "fetched_at": now,
        }
        with _LOCK:
            _SM_CACHE[key] = (now, result)
        log.info(
            "era5-land soil-moisture OK lat=%.3f lon=%.3f sm=%.1f%% trend_days=%d",
            lat, lon, result["current_pct"], len(trend),
        )
        return result
    except Exception as e:
        log.warning("era5-land soil-moisture FAIL lat=%.3f lon=%.3f err=%s", lat, lon, e)
        return None


def cache_stats() -> Dict[str, Any]:
    with _LOCK:
        return {
            "weather_entries": len(_CACHE),
            "soil_moisture_entries": len(_SM_CACHE),
            "weather_ttl_s": _TTL_S,
            "soil_moisture_ttl_s": _SM_TTL_S,
        }
