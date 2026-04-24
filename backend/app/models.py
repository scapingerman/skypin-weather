from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: List[Any]


class ZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    geometry: GeoJSONGeometry
    tenant_id: str = "demo"


class Zone(BaseModel):
    id: str
    name: str
    geometry: GeoJSONGeometry
    area_ha: float
    centroid: List[float]
    created_at: datetime
    tenant_id: str = "demo"


class MetricPoint(BaseModel):
    date: str
    value: float


class ZoneMetrics(BaseModel):
    zone_id: str
    ndvi: float
    ndvi_trend: List[MetricPoint]
    soil_moisture: float
    soil_moisture_trend: List[MetricPoint]
    precipitation_mm_7d: float
    temperature_c: float
    wind_kmh: float
    updated_at: datetime
    # metric_name -> "mock" | "open-meteo" | "sentinel" | "smap" ...
    sources: Dict[str, str] = Field(default_factory=dict)


class RiskScore(BaseModel):
    zone_id: str
    score: float  # 0-100
    level: str   # "low" | "medium" | "high" | "critical"
    drivers: List[Dict[str, Any]]
    recommendation: str
    updated_at: datetime


class ZoneSummary(BaseModel):
    zone: Zone
    metrics: ZoneMetrics
    risk: RiskScore
