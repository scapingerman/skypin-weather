"""Map OSM place names + coordinates to canonical dim.dim_city.city_name for Grafana URLs."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

import asyncpg

R_EARTH_KM = 6371.0


def _fold(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s.strip())
    ascii_like = "".join(c for c in nk if not unicodedata.combining(c))
    return ascii_like.lower()


@dataclass(frozen=True)
class DimCity:
    city_name: str
    lat: float
    lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 2 * R_EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


async def load_dim_cities(conn: asyncpg.Connection) -> list[DimCity]:
    rows = await conn.fetch(
        "SELECT city_name, latitude, longitude FROM dim.dim_city ORDER BY city_id"
    )
    return [DimCity(r["city_name"], float(r["latitude"]), float(r["longitude"])) for r in rows]


def match_places_to_warehouse_names(
    places: list[tuple[str, float, float]],
    dim: list[DimCity],
    *,
    max_km: float = 45.0,
) -> list[str]:
    """
    Return unique dim city_name values for Grafana ?var-city_name=…
    Order follows first-seen place order.
    """
    by_fold: dict[str, str] = {}
    for d in dim:
        k = _fold(d.city_name)
        if k not in by_fold:
            by_fold[k] = d.city_name

    out: list[str] = []
    seen: set[str] = set()
    for name, lat, lon in places:
        fk = _fold(name)
        if fk in by_fold:
            cn = by_fold[fk]
            if cn not in seen:
                seen.add(cn)
                out.append(cn)
            continue
        best: str | None = None
        best_km = max_km + 1.0
        for d in dim:
            km = haversine_km(lat, lon, d.lat, d.lon)
            if km < best_km:
                best_km = km
                best = d.city_name
        if best is not None and best_km <= max_km and best not in seen:
            seen.add(best)
            out.append(best)
    return out
