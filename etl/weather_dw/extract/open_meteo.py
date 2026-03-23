from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from weather_dw.config import Settings

LOG = logging.getLogger(__name__)

HOURLY_FIELDS = (
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "weathercode",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "cloud_cover",
)


def _parse_hourly_ts(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def fetch_hourly_forecast_rows(
    client: httpx.Client,
    settings: Settings,
    city_id: int,
    latitude: float,
    longitude: float,
) -> list[tuple[Any, ...]]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_FIELDS),
        "forecast_days": settings.forecast_days,
        "timezone": "UTC",
    }
    r = client.get(settings.open_meteo_base, params=params, timeout=settings.http_timeout_s)
    r.raise_for_status()
    payload: dict[str, Any] = r.json()
    hourly = payload.get("hourly") or {}
    times: list[str] = hourly.get("time") or []
    if not times:
        LOG.warning("Open-Meteo returned no hourly rows for city_id=%s", city_id)
        return []

    series: dict[str, list[Any | None]] = {}
    for field in HOURLY_FIELDS:
        raw = hourly.get(field)
        if raw is None:
            series[field] = [None] * len(times)
        else:
            series[field] = list(raw)

    out: list[tuple[Any, ...]] = []
    for i, t in enumerate(times):
        fc_ts = _parse_hourly_ts(t)
        out.append(
            (
                city_id,
                fc_ts,
                series["temperature_2m"][i],
                series["precipitation"][i],
                series["precipitation_probability"][i],
                series["weathercode"][i],
                series["wind_speed_10m"][i],
                series["wind_direction_10m"][i],
                series["surface_pressure"][i],
                series["cloud_cover"][i],
            )
        )
    return out
