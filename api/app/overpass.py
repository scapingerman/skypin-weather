from __future__ import annotations

import logging
from typing import Any

import httpx

LOG = logging.getLogger(__name__)


async def fetch_places_in_bbox(
    client: httpx.AsyncClient,
    *,
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str,
) -> list[dict[str, Any]]:
    """
    Query OSM for city/town/village nodes and ways inside bbox.
    Returns dicts with name, lat, lon, place (type).
    """
    # Overpass bbox: (south,west,north,east)
    query = f"""
    [out:json][timeout:60];
    (
      node["place"~"^(city|town|village|hamlet)$"]({south},{west},{north},{east});
      way["place"~"^(city|town|village|hamlet)$"]({south},{west},{north},{east});
    );
    out center tags;
    """
    r = await client.post(
        overpass_url,
        content=query,
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    r.raise_for_status()
    data = r.json()
    out: list[dict[str, Any]] = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:es") or tags.get("name:en")
        if not name:
            continue
        place = tags.get("place") or ""
        lat: float | None
        lon: float | None
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            c = el.get("center") or {}
            lat = c.get("lat")
            lon = c.get("lon")
        if lat is None or lon is None:
            continue
        out.append(
            {
                "name": str(name),
                "lat": float(lat),
                "lon": float(lon),
                "place": str(place),
            }
        )
    LOG.info("Overpass returned %s raw elements (with name+coords)", len(out))
    return out
