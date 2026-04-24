import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("skyping.risk")

from ..db import (
    get_session,
    get_zone as db_get_zone,
    list_zones as db_list_zones,
)
from ..mock_data import (
    compute_risk,
    generate_ndvi,
    generate_precip_7d,
    generate_soil_moisture,
    generate_temperature,
    generate_wind,
)
from ..models import RiskScore, ZoneMetrics, ZoneSummary
from ..sentinel_client import fetch_ndvi
from ..weather_client import fetch_soil_moisture, fetch_weather
from .indices import _metrics_for_centroid
from .zones import _tenant

router = APIRouter(prefix="/api/v1", tags=["risk"])


def _risk_from_metrics(m: ZoneMetrics) -> RiskScore:
    """Deriva el riesgo directamente de métricas ya calculadas (sin re-fetch)."""
    r = compute_risk(
        m.ndvi,
        m.soil_moisture,
        m.precipitation_mm_7d,
        m.temperature_c,
        m.wind_kmh,
    )
    return RiskScore(
        zone_id=m.zone_id,
        score=r["score"],
        level=r["level"],
        drivers=r["drivers"],
        recommendation=r["recommendation"],
        updated_at=datetime.utcnow(),
    )


def _risk_for_centroid(
    zone_id: str,
    lon: float,
    lat: float,
    geometry: Optional[dict] = None,
) -> RiskScore:
    # Versión standalone (para el endpoint /risk/{id}): calcula métricas
    # y deriva el riesgo. El cache evita re-fetch si ya se pidieron métricas
    # de esta zona recientemente.
    m = _metrics_for_centroid(zone_id, lon, lat, geometry=geometry)
    return _risk_from_metrics(m)


@router.get("/risk/{zone_id}", response_model=RiskScore)
async def risk_for_zone(
    zone_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    z = await db_get_zone(session, _tenant(x_tenant_id), zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    lon, lat = z.centroid
    return _risk_for_centroid(
        zone_id, lon, lat, geometry=z.geometry.model_dump()
    )


@router.get("/summary", response_model=List[ZoneSummary])
async def summary_all_zones(
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Dashboard endpoint: todas las zonas con métricas + riesgo.

    Procesa cada zona en paralelo (asyncio.to_thread) porque los clientes
    Sentinel/Open-Meteo son HTTPX sync. Y calcula métricas UNA sola vez
    por zona (el riesgo se deriva de las métricas ya computadas).
    """
    zones = await db_list_zones(session, _tenant(x_tenant_id))
    if not zones:
        return []

    def _compute_one(z) -> ZoneSummary:
        lon, lat = z.centroid
        geom = z.geometry.model_dump()
        metrics = _metrics_for_centroid(z.id, lon, lat, geometry=geom)
        risk = _risk_from_metrics(metrics)
        return ZoneSummary(zone=z, metrics=metrics, risk=risk)

    # return_exceptions=True → si una zona explota, no matamos las demás.
    raw = await asyncio.gather(
        *(asyncio.to_thread(_compute_one, z) for z in zones),
        return_exceptions=True,
    )
    out: List[ZoneSummary] = []
    for z, r in zip(zones, raw):
        if isinstance(r, Exception):
            log.exception(
                "summary: fallo al computar zona %s (%s): %s",
                z.id, z.name, r,
            )
            continue
        out.append(r)
    return out
