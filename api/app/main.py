from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import Point

from .geo import bbox_too_large, geojson_polygon_to_shapely
from .overpass import fetch_places_in_bbox
from .risk import aggregate_forecast_risk

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

OPEN_METEO_BASE = os.environ.get(
    "OPEN_METEO_BASE", "https://api.open-meteo.com/v1/forecast"
)
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACK = "https://overpass.kumi.systems/api/interpreter"


def _overpass_urls() -> list[str]:
    multi = os.environ.get("OVERPASS_URLS", "").strip()
    if multi:
        return [u.strip() for u in multi.split(",") if u.strip()]
    primary = os.environ.get("OVERPASS_URL", DEFAULT_OVERPASS).strip()
    return [primary, OVERPASS_FALLBACK]
HOURLY = (
    "temperature_2m,precipitation,precipitation_probability,weathercode,"
    "wind_speed_10m,wind_direction_10m,surface_pressure,cloud_cover"
)
MAX_CONCURRENT_METEO = 5


class AreaRiskRequest(BaseModel):
    geometry: dict[str, Any] = Field(
        ...,
        description="GeoJSON Polygon geometry (EPSG:4326, lon/lat)",
    )
    alert_rain_mm_h: float = Field(default=3.0, ge=0)
    min_precip_prob_pct: int = Field(default=40, ge=0, le=100)
    forecast_days: int = Field(default=3, ge=1, le=7)
    max_places: int = Field(
        default=40,
        ge=1,
        le=120,
        description="Cap Open-Meteo calls (after polygon filter)",
    )


class PlaceRisk(BaseModel):
    name: str
    place: str
    lat: float
    lon: float
    max_risk_score: float
    alert_hours: int


class AreaRiskResponse(BaseModel):
    places: list[PlaceRisk]
    total_in_polygon: int
    truncated: bool
    message: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=120.0) as client:
        app.state.http = client
        yield


app = FastAPI(title="Skypin Area Risk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _dedupe_places(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (
            r["name"].lower().strip(),
            f"{r['lat']:.4f}",
            f"{r['lon']:.4f}",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


async def _open_meteo_forecast(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    forecast_days: int,
) -> dict:
    r = await client.get(
        OPEN_METEO_BASE,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": HOURLY,
            "forecast_days": forecast_days,
            "timezone": "UTC",
        },
    )
    r.raise_for_status()
    return r.json().get("hourly") or {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/area/risk", response_model=AreaRiskResponse)
async def area_risk(body: AreaRiskRequest) -> AreaRiskResponse:
    if body.geometry.get("type") != "Polygon":
        raise HTTPException(
            status_code=400,
            detail="Only GeoJSON Polygon is supported (draw a closed shape).",
        )
    try:
        poly = geojson_polygon_to_shapely(body.geometry)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid GeoJSON polygon (need closed ring, lon/lat order): {exc}",
        ) from exc

    if bbox_too_large(poly):
        raise HTTPException(
            status_code=400,
            detail="Selection is too large (max ~6° per side). Zoom in and draw a smaller area.",
        )

    minx, miny, maxx, maxy = poly.bounds
    south, west, north, east = miny, minx, maxy, maxx

    client: httpx.AsyncClient = app.state.http
    last_exc: Exception | None = None
    raw: list[dict[str, Any]] = []
    for overpass_url in _overpass_urls():
        try:
            raw = await fetch_places_in_bbox(
                client,
                south=south,
                west=west,
                north=north,
                east=east,
                overpass_url=overpass_url,
            )
            last_exc = None
            break
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            code = exc.response.status_code if exc.response is not None else 0
            if code in (429, 502, 503, 504):
                LOG.warning("Overpass %s returned %s, trying next mirror", overpass_url, code)
                continue
            LOG.exception("Overpass failed")
            raise HTTPException(
                status_code=502,
                detail=f"Overpass/OSM query failed: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            LOG.warning("Overpass %s error: %s", overpass_url, exc)
            continue
    if last_exc is not None and not raw:
        LOG.exception("All Overpass mirrors failed")
        raise HTTPException(
            status_code=502,
            detail=f"Overpass/OSM query failed (all mirrors): {last_exc}",
        ) from last_exc

    inside: list[dict[str, Any]] = []
    for row in raw:
        pt = Point(row["lon"], row["lat"])
        if poly.contains(pt) or poly.touches(pt):
            inside.append(row)

    inside = _dedupe_places(inside)
    total = len(inside)
    truncated = total > body.max_places
    inside = inside[: body.max_places]

    sem = asyncio.Semaphore(MAX_CONCURRENT_METEO)

    async def one(row: dict[str, Any]) -> PlaceRisk:
        async with sem:
            hourly = await _open_meteo_forecast(
                client,
                row["lat"],
                row["lon"],
                body.forecast_days,
            )
        mx, ah = aggregate_forecast_risk(
            hourly,
            body.alert_rain_mm_h,
            body.min_precip_prob_pct,
        )
        return PlaceRisk(
            name=row["name"],
            place=row["place"],
            lat=row["lat"],
            lon=row["lon"],
            max_risk_score=round(mx, 2),
            alert_hours=ah,
        )

    places = await asyncio.gather(*[one(r) for r in inside])
    places = sorted(places, key=lambda p: p.max_risk_score, reverse=True)

    msg = None
    if total == 0:
        msg = "No OSM city/town/village found inside the polygon. Try a denser area."
    elif truncated:
        msg = f"Showing top {body.max_places} by processing order; {total} places matched."

    return AreaRiskResponse(
        places=list(places),
        total_in_polygon=total,
        truncated=truncated,
        message=msg,
    )
