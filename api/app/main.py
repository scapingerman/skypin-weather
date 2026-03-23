from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import Point

from .dim_match import load_dim_cities, match_places_to_warehouse_names
from .geo import bbox_too_large, geojson_polygon_to_shapely
from .overpass import fetch_places_in_bbox
from .risk import aggregate_forecast_risk
from .selection_store import persist_area_selection

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
    grafana_city_names: list[str] | None = None
    selection_id: str | None = Field(
        default=None,
        description="UUID for Grafana map-polygon dashboard (api.area_selection_hourly).",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = None
    host = os.environ.get("POSTGRES_HOST", "").strip()
    if host:
        import asyncpg

        pool = await asyncpg.create_pool(
            host=host,
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            user=os.environ.get("POSTGRES_USER", "weather"),
            password=os.environ.get("POSTGRES_PASSWORD", "weather"),
            database=os.environ.get("POSTGRES_DB", "weather_dw"),
            min_size=1,
            max_size=4,
        )
    app.state.pg_pool = pool
    async with httpx.AsyncClient(timeout=120.0) as client:
        app.state.http = client
        yield
    if pool is not None:
        await pool.close()


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


def _persist_enabled() -> bool:
    return os.environ.get("API_PERSIST_SELECTION", "true").lower() in (
        "1",
        "true",
        "yes",
    )


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
                LOG.warning(
                    "Overpass %s returned %s, trying next mirror", overpass_url, code
                )
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

    async def one_place(
        row: dict[str, Any],
    ) -> tuple[PlaceRisk, dict[str, Any], dict[str, Any]]:
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
        pr = PlaceRisk(
            name=row["name"],
            place=row["place"],
            lat=row["lat"],
            lon=row["lon"],
            max_risk_score=round(mx, 2),
            alert_hours=ah,
        )
        return pr, row, hourly

    raw_results = await asyncio.gather(*[one_place(r) for r in inside])
    places = sorted(
        [t[0] for t in raw_results],
        key=lambda p: p.max_risk_score,
        reverse=True,
    )

    msg = None
    if total == 0:
        msg = "No OSM city/town/village found inside the polygon. Try a denser area."
    elif truncated:
        msg = f"Showing top {body.max_places} by processing order; {total} places matched."

    grafana_city_names: list[str] | None = None
    selection_id_str: str | None = None
    pg_pool = getattr(app.state, "pg_pool", None)

    if pg_pool is not None and inside:
        try:
            async with pg_pool.acquire() as conn:
                dim_rows = await load_dim_cities(conn)
            keys = [(r["name"], float(r["lat"]), float(r["lon"])) for r in inside]
            matched = match_places_to_warehouse_names(keys, dim_rows)
            if matched:
                grafana_city_names = matched
        except Exception:
            LOG.exception(
                "Warehouse city match failed; embedded Grafana will show all cities."
            )
            grafana_city_names = None

        if _persist_enabled():
            try:
                sid = uuid.uuid4()
                payloads = [(t[1], t[2]) for t in raw_results]
                async with pg_pool.acquire() as conn:
                    n = await persist_area_selection(
                        conn,
                        sid,
                        payloads,
                        body.alert_rain_mm_h,
                        body.min_precip_prob_pct,
                    )
                if n > 0:
                    selection_id_str = str(sid)
            except Exception:
                LOG.exception("Persisting area selection to Postgres failed.")

    return AreaRiskResponse(
        places=list(places),
        total_in_polygon=total,
        truncated=truncated,
        message=msg,
        grafana_city_names=grafana_city_names,
        selection_id=selection_id_str,
    )
