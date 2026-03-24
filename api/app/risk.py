"""Risk rules aligned with mart.mart_city_hourly_risk (refresh_downstream.sql)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STORM_CODES = frozenset({95, 96, 99})

# Open-Meteo documents wind_speed_10m / wind_gusts_10m in km/h for the forecast API.
_GUST_MODERATE_KMH = 50.0
_GUST_HIGH_KMH = 70.0
_GUST_SEVERE_KMH = 90.0


def max_wind_gust_kmh(hourly: dict[str, Any]) -> float:
    """Peak hourly gust in the forecast payload (km/h per Open-Meteo)."""
    g = hourly.get("wind_gusts_10m") or []
    vals = [float(x) for x in g if x is not None]
    if not vals:
        return 0.0
    return round(max(vals), 1)


def gust_tier_kmh(kmh: float) -> str:
    if kmh < _GUST_MODERATE_KMH:
        return "low"
    if kmh < _GUST_HIGH_KMH:
        return "moderate"
    if kmh < _GUST_SEVERE_KMH:
        return "high"
    return "severe"


def hourly_risk(
    precipitation: float | None,
    precipitation_probability: int | None,
    weathercode: int | None,
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> tuple[bool, float]:
    p = float(precipitation or 0.0)
    prob = int(precipitation_probability or 0)
    code = int(weathercode or 0)
    storm = code in STORM_CODES
    storm_risk_flag = storm or (
        p >= alert_rain_mm_h and prob >= min_precip_prob_pct
    )
    risk_score = min(
        100.0,
        (70.0 if storm else 0.0)
        + min(35.0, p * 6.0)
        + min(25.0, prob * 0.25),
    )
    return storm_risk_flag, risk_score


def _parse_open_meteo_time(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hourly_risk_series(
    hourly: dict[str, Any],
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> list[dict[str, Any]]:
    """
    One dict per forecast hour for persistence / Grafana.
    Keys: forecast_ts_utc, temperature_2m, precipitation, precipitation_probability,
    weathercode, wind_speed_10m, wind_gusts_10m, wind_direction_10m, surface_pressure,
    cloud_cover, storm_risk_flag, risk_score.
    """
    h = hourly or {}
    times = h.get("time") or []
    if not times:
        return []

    precip_s = h.get("precipitation") or []
    prob_s = h.get("precipitation_probability") or []
    code_s = h.get("weathercode") or []
    temp_s = h.get("temperature_2m") or []
    wind_s = h.get("wind_speed_10m") or []
    gust_s = h.get("wind_gusts_10m") or []
    wdir_s = h.get("wind_direction_10m") or []
    pres_s = h.get("surface_pressure") or []
    cloud_s = h.get("cloud_cover") or []

    out: list[dict[str, Any]] = []
    for i in range(len(times)):
        precip = precip_s[i] if i < len(precip_s) else None
        prob = prob_s[i] if i < len(prob_s) else None
        wc = code_s[i] if i < len(code_s) else None
        temp = temp_s[i] if i < len(temp_s) else None
        wind = wind_s[i] if i < len(wind_s) else None
        gust = gust_s[i] if i < len(gust_s) else None
        wdir = wdir_s[i] if i < len(wdir_s) else None
        pres = pres_s[i] if i < len(pres_s) else None
        cld = cloud_s[i] if i < len(cloud_s) else None
        flag, score = hourly_risk(
            float(precip) if precip is not None else None,
            int(prob) if prob is not None else None,
            int(wc) if wc is not None else None,
            alert_rain_mm_h,
            min_precip_prob_pct,
        )
        out.append(
            {
                "forecast_ts_utc": _parse_open_meteo_time(str(times[i])),
                "temperature_2m": float(temp) if temp is not None else None,
                "precipitation": float(precip) if precip is not None else None,
                "precipitation_probability": int(prob) if prob is not None else None,
                "weathercode": int(wc) if wc is not None else None,
                "wind_speed_10m": float(wind) if wind is not None else None,
                "wind_gusts_10m": float(gust) if gust is not None else None,
                "wind_direction_10m": int(wdir) if wdir is not None else None,
                "surface_pressure": float(pres) if pres is not None else None,
                "cloud_cover": int(cld) if cld is not None else None,
                "storm_risk_flag": flag,
                "risk_score": score,
            }
        )
    return out


def aggregate_forecast_risk(
    hourly: dict,
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> tuple[float, int]:
    """
    Returns (max_risk_score, count of hours with storm_risk_flag True).
    """
    series = hourly_risk_series(hourly, alert_rain_mm_h, min_precip_prob_pct)
    if not series:
        return 0.0, 0
    max_score = max(s["risk_score"] for s in series)
    alert_hours = sum(1 for s in series if s["storm_risk_flag"])
    return max_score, alert_hours
