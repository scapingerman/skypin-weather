from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session, get_zone as db_get_zone
from ..mock_data import (
    generate_ndvi,
    generate_precip_7d,
    generate_soil_moisture,
    generate_temperature,
    generate_trend,
    generate_wind,
)
from ..models import MetricPoint, ZoneMetrics
from ..sentinel_client import fetch_ndvi
from ..weather_client import fetch_soil_moisture, fetch_weather
from .zones import _tenant

router = APIRouter(prefix="/api/v1/indices", tags=["indices"])


def _metrics_for_centroid(
    zone_id: str,
    lon: float,
    lat: float,
    geometry: Optional[dict] = None,
) -> ZoneMetrics:
    sources: dict[str, str] = {}

    # --- NDVI: Sentinel-2 real si hay geometría, fallback a mock ---
    ndvi_live = fetch_ndvi(geometry) if geometry else None
    if ndvi_live:
        ndvi = ndvi_live["current"]
        ndvi_trend = [MetricPoint(**p) for p in ndvi_live["trend"]]
        sources["ndvi"] = ndvi_live["source"]  # "sentinel-2"
    else:
        ndvi = generate_ndvi(lat, lon)
        ndvi_trend = generate_trend(lat, lon, "ndvi", 30)
        sources["ndvi"] = "mock"

    # --- Humedad de suelo: ERA5-Land (Open-Meteo) con fallback a mock ---
    sm_live = fetch_soil_moisture(lat, lon)
    if sm_live:
        sm = sm_live["current_pct"]
        sm_trend = [MetricPoint(**p) for p in sm_live["trend"]]
        sources["soil_moisture"] = sm_live["source"]
    else:
        sm = generate_soil_moisture(lat, lon)
        sm_trend = generate_trend(lat, lon, "soil_moisture", 30)
        sources["soil_moisture"] = "mock"

    # --- Clima actual: Open-Meteo real con fallback a mock ---
    live = fetch_weather(lat, lon)
    if live:
        temp = live["temperature_c"]
        wind = live["wind_kmh"]
        precip = live["precip_7d_mm"]
        sources["temperature"] = live["source"]
        sources["wind"] = live["source"]
        sources["precipitation"] = live["source"]
    else:
        temp = generate_temperature(lat, lon)
        wind = generate_wind(lat, lon)
        precip = generate_precip_7d(lat, lon)
        sources["temperature"] = "mock"
        sources["wind"] = "mock"
        sources["precipitation"] = "mock"

    return ZoneMetrics(
        zone_id=zone_id,
        ndvi=ndvi,
        ndvi_trend=ndvi_trend,
        soil_moisture=sm,
        soil_moisture_trend=sm_trend,
        precipitation_mm_7d=precip,
        temperature_c=temp,
        wind_kmh=wind,
        updated_at=datetime.utcnow(),
        sources=sources,
    )


@router.get("/{zone_id}", response_model=ZoneMetrics)
async def metrics_for_zone(
    zone_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    z = await db_get_zone(session, _tenant(x_tenant_id), zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    lon, lat = z.centroid
    return _metrics_for_centroid(
        zone_id, lon, lat, geometry=z.geometry.model_dump()
    )


@router.get("/point/preview", response_model=ZoneMetrics)
async def metrics_for_point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """Preview por punto: NDVI queda como mock (no hay polígono)."""
    return _metrics_for_centroid("preview", lon, lat, geometry=None)
