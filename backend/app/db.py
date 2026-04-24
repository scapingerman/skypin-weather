"""
Persistencia SQLite (asíncrona) para zonas.

Diseño intencional:
- 1 tabla `zones` con geometry_geojson como TEXT (portable a Postgres trivial).
- tenant_id indexado — multi-tenant desde MVP.
- Migración futura a PostGIS: agregar columna GEOMETRY(POLYGON, 4326) y
  backfill con ST_GeomFromGeoJSON(geometry_geojson).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import AsyncGenerator, List, Optional

from sqlalchemy import DateTime, Float, Index, String, delete, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

log = logging.getLogger("skyping.db")

DB_PATH = os.environ.get("SKYPING_DB_PATH", "/app/data/skyping.db")
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DB_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class ZoneORM(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    geometry_geojson: Mapped[str] = mapped_column(String, nullable=False)
    area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_zones_tenant_id", "tenant_id"),
        Index("ix_zones_tenant_created", "tenant_id", "created_at"),
    )


async def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("DB ready at %s", DB_URL)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


# ---------- CRUD helpers usados por los routers ----------

from .models import GeoJSONGeometry, Zone  # placed here to avoid circular at import time


def orm_to_model(z: ZoneORM) -> Zone:
    return Zone(
        id=z.id,
        name=z.name,
        geometry=GeoJSONGeometry(**json.loads(z.geometry_geojson)),
        area_ha=z.area_ha,
        centroid=[z.centroid_lon, z.centroid_lat],
        created_at=z.created_at,
        tenant_id=z.tenant_id,
    )


async def list_zones(session: AsyncSession, tenant_id: str) -> List[Zone]:
    result = await session.execute(
        select(ZoneORM)
        .where(ZoneORM.tenant_id == tenant_id)
        .order_by(ZoneORM.created_at.desc())
    )
    return [orm_to_model(z) for z in result.scalars()]


async def get_zone(
    session: AsyncSession, tenant_id: str, zone_id: str
) -> Optional[Zone]:
    z = (
        await session.execute(
            select(ZoneORM).where(
                ZoneORM.id == zone_id, ZoneORM.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    return orm_to_model(z) if z else None


async def create_zone(
    session: AsyncSession,
    *,
    zone_id: str,
    tenant_id: str,
    name: str,
    geometry: dict,
    area_ha: float,
    centroid_lon: float,
    centroid_lat: float,
) -> Zone:
    z = ZoneORM(
        id=zone_id,
        tenant_id=tenant_id,
        name=name,
        geometry_geojson=json.dumps(geometry),
        area_ha=area_ha,
        centroid_lon=centroid_lon,
        centroid_lat=centroid_lat,
        created_at=datetime.utcnow(),
    )
    session.add(z)
    await session.commit()
    await session.refresh(z)
    return orm_to_model(z)


async def delete_zone(
    session: AsyncSession, tenant_id: str, zone_id: str
) -> bool:
    result = await session.execute(
        delete(ZoneORM).where(
            ZoneORM.id == zone_id, ZoneORM.tenant_id == tenant_id
        )
    )
    await session.commit()
    return result.rowcount > 0


async def count_zones(session: AsyncSession, tenant_id: str) -> int:
    from sqlalchemy import func
    r = await session.execute(
        select(func.count(ZoneORM.id)).where(ZoneORM.tenant_id == tenant_id)
    )
    return int(r.scalar_one())
