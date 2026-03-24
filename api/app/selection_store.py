"""Persist polygon area hourly risk into api.area_selection_hourly for Grafana."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from .risk import hourly_risk_series

_INSERT_SQL = """
INSERT INTO api.area_selection_hourly (
    selection_id,
    place_key,
    place_name,
    osm_place,
    lat,
    lon,
    forecast_ts_utc,
    temperature_2m,
    precipitation,
    precipitation_probability,
    weathercode,
    wind_speed_10m,
    wind_gusts_10m,
    wind_direction_10m,
    surface_pressure,
    cloud_cover,
    storm_risk_flag,
    risk_score,
    alert_rain_mm_h
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
)
"""


def _place_key(row: dict[str, Any]) -> str:
    return f"{row['name']}|{float(row['lat']):.5f}|{float(row['lon']):.5f}"


async def persist_area_selection(
    conn: asyncpg.Connection,
    selection_id: uuid.UUID,
    osm_rows_with_hourly: list[tuple[dict[str, Any], dict[str, Any]]],
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> int:
    batch: list[tuple[Any, ...]] = []
    for osm_row, hourly in osm_rows_with_hourly:
        pk = _place_key(osm_row)
        series = hourly_risk_series(hourly, alert_rain_mm_h, min_precip_prob_pct)
        for pt in series:
            batch.append(
                (
                    selection_id,
                    pk,
                    str(osm_row["name"]),
                    str(osm_row["place"]),
                    float(osm_row["lat"]),
                    float(osm_row["lon"]),
                    pt["forecast_ts_utc"],
                    pt["temperature_2m"],
                    pt["precipitation"],
                    pt["precipitation_probability"],
                    pt["weathercode"],
                    pt["wind_speed_10m"],
                    pt["wind_gusts_10m"],
                    pt["wind_direction_10m"],
                    pt["surface_pressure"],
                    pt["cloud_cover"],
                    pt["storm_risk_flag"],
                    float(pt["risk_score"]),
                    float(alert_rain_mm_h),
                )
            )
    if not batch:
        return 0
    async with conn.transaction():
        await conn.executemany(_INSERT_SQL, batch)
    return len(batch)
