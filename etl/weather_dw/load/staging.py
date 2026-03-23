from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from psycopg import Connection

LOG = logging.getLogger(__name__)

INSERT_STG_SQL = """
INSERT INTO stg.stg_open_meteo_hourly (
    run_id,
    city_id,
    forecast_ts_utc,
    temperature_2m,
    precipitation,
    precipitation_probability,
    weathercode,
    wind_speed_10m,
    wind_direction_10m,
    surface_pressure,
    cloud_cover
) VALUES (
    %(run_id)s,
    %(city_id)s,
    %(forecast_ts_utc)s,
    %(temperature_2m)s,
    %(precipitation)s,
    %(precipitation_probability)s,
    %(weathercode)s,
    %(wind_speed_10m)s,
    %(wind_direction_10m)s,
    %(surface_pressure)s,
    %(cloud_cover)s
);
"""


def insert_staging_rows(
    conn: Connection,
    run_id: UUID,
    rows: list[tuple[Any, ...]],
) -> int:
    """
    rows: (city_id, forecast_ts_utc, temp, precip, precip_prob, weathercode,
           wind_speed, wind_dir, pressure, cloud_cover)
    """
    count = 0
    with conn.cursor() as cur:
        for row in rows:
            (
                city_id,
                forecast_ts_utc,
                temperature_2m,
                precipitation,
                precipitation_probability,
                weathercode,
                wind_speed_10m,
                wind_direction_10m,
                surface_pressure,
                cloud_cover,
            ) = row
            cur.execute(
                INSERT_STG_SQL,
                {
                    "run_id": str(run_id),
                    "city_id": city_id,
                    "forecast_ts_utc": forecast_ts_utc,
                    "temperature_2m": temperature_2m,
                    "precipitation": precipitation,
                    "precipitation_probability": precipitation_probability,
                    "weathercode": weathercode,
                    "wind_speed_10m": wind_speed_10m,
                    "wind_direction_10m": wind_direction_10m,
                    "surface_pressure": surface_pressure,
                    "cloud_cover": cloud_cover,
                },
            )
            count += 1
    LOG.info("Loaded %s staging hourly rows for run_id=%s", count, run_id)
    return count
