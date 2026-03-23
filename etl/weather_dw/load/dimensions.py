from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from weather_dw.extract.targets import CityTarget

if TYPE_CHECKING:
    from psycopg import Connection

LOG = logging.getLogger(__name__)

UPSERT_DIM_SQL = """
INSERT INTO dim.dim_city (
    city_id,
    city_name,
    country_code,
    latitude,
    longitude,
    alert_rain_mm_h,
    min_precip_prob_pct,
    updated_at
) VALUES (
    %(city_id)s,
    %(city_name)s,
    %(country_code)s,
    %(latitude)s,
    %(longitude)s,
    %(alert_rain_mm_h)s,
    %(min_precip_prob_pct)s,
    now()
)
ON CONFLICT (city_id) DO UPDATE SET
    city_name = EXCLUDED.city_name,
    country_code = EXCLUDED.country_code,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    alert_rain_mm_h = EXCLUDED.alert_rain_mm_h,
    min_precip_prob_pct = EXCLUDED.min_precip_prob_pct,
    updated_at = now();
"""


def sync_dim_cities(conn: Connection, cities: list[CityTarget]) -> None:
    with conn.cursor() as cur:
        for c in cities:
            cur.execute(
                UPSERT_DIM_SQL,
                {
                    "city_id": c.city_id,
                    "city_name": c.city_name,
                    "country_code": c.country_code,
                    "latitude": c.latitude,
                    "longitude": c.longitude,
                    "alert_rain_mm_h": c.alert_rain_mm_h,
                    "min_precip_prob_pct": c.min_precip_prob_pct,
                },
            )
    LOG.info("Synced %s cities into dim.dim_city", len(cities))
