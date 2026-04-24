import math
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from shapely.geometry import shape
from shapely.ops import transform
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import (
    count_zones,
    create_zone as db_create_zone,
    delete_zone as db_delete_zone,
    get_session,
    get_zone as db_get_zone,
    list_zones as db_list_zones,
)
from ..models import Zone, ZoneCreate

router = APIRouter(prefix="/api/v1/zones", tags=["zones"])


def _tenant(x_tenant_id: Optional[str]) -> str:
    return x_tenant_id or "demo"


def _area_ha(geom_dict: dict) -> float:
    """Aproxima hectáreas de un polígono lon/lat con proyección local equirectangular."""
    geom = shape(geom_dict)
    centroid = geom.centroid
    m_per_deg_lat = 111_320
    m_per_deg_lon = 111_320 * math.cos(math.radians(centroid.y))
    scaled = transform(
        lambda x, y, z=None: (x * m_per_deg_lon, y * m_per_deg_lat),
        geom,
    )
    return round(scaled.area / 10_000, 2)  # m² → ha


@router.get("", response_model=List[Zone])
async def list_zones(
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await db_list_zones(session, _tenant(x_tenant_id))


@router.post("", response_model=Zone, status_code=201)
async def create_zone(
    payload: ZoneCreate,
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    t = _tenant(x_tenant_id)
    geom_dict = payload.geometry.model_dump()
    try:
        geom = shape(geom_dict)
        if not geom.is_valid:
            raise ValueError("geometry not valid")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid geometry: {e}")

    zid = uuid.uuid4().hex[:10]
    return await db_create_zone(
        session,
        zone_id=zid,
        tenant_id=t,
        name=payload.name,
        geometry=geom_dict,
        area_ha=_area_ha(geom_dict),
        centroid_lon=round(geom.centroid.x, 5),
        centroid_lat=round(geom.centroid.y, 5),
    )


@router.get("/{zone_id}", response_model=Zone)
async def get_zone(
    zone_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    z = await db_get_zone(session, _tenant(x_tenant_id), zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    return z


@router.delete("/{zone_id}", status_code=204)
async def delete_zone(
    zone_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    ok = await db_delete_zone(session, _tenant(x_tenant_id), zone_id)
    if not ok:
        raise HTTPException(404, "Zone not found")
    return None
