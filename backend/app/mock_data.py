"""
Mock data generator for NDVI / soil moisture / weather / risk.

Deterministic-but-realistic values using a seed derived from zone centroid.
Designed so real Sentinel/ERA5/SMAP endpoints can replace this module 1:1.
"""
import hashlib
import math
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .models import MetricPoint


def _seed_from_point(lat: float, lon: float) -> int:
    key = f"{lat:.4f}:{lon:.4f}".encode()
    return int(hashlib.md5(key).hexdigest()[:8], 16)


def _rng(lat: float, lon: float, salt: str = "") -> random.Random:
    return random.Random(_seed_from_point(lat, lon) ^ hash(salt))


def generate_ndvi(lat: float, lon: float) -> float:
    """Realistic NDVI range: -0.1 (bare) to 0.9 (dense veg)."""
    rng = _rng(lat, lon, "ndvi")
    # Latitude gradient: tropics greener, desert bands drier
    band = math.cos(math.radians(abs(lat))) ** 2
    base = 0.2 + 0.5 * band
    noise = rng.uniform(-0.08, 0.08)
    return round(max(-0.1, min(0.9, base + noise)), 3)


def generate_soil_moisture(lat: float, lon: float) -> float:
    """Volumetric soil moisture % (0-60)."""
    rng = _rng(lat, lon, "sm")
    base = 15 + 25 * math.cos(math.radians(abs(lat)))
    noise = rng.uniform(-5, 5)
    return round(max(1.0, min(60.0, base + noise)), 2)


def generate_precip_7d(lat: float, lon: float) -> float:
    rng = _rng(lat, lon, "precip")
    base = 8 + 40 * math.cos(math.radians(abs(lat))) ** 2
    return round(max(0.0, base + rng.uniform(-8, 12)), 1)


def generate_temperature(lat: float, lon: float) -> float:
    rng = _rng(lat, lon, "temp")
    base = 30 - 0.55 * abs(lat)
    return round(base + rng.uniform(-3, 3), 1)


def generate_wind(lat: float, lon: float) -> float:
    rng = _rng(lat, lon, "wind")
    return round(max(0.0, 6 + rng.uniform(-3, 18)), 1)


def generate_trend(
    lat: float, lon: float, kind: str, days: int = 30
) -> List[MetricPoint]:
    rng = _rng(lat, lon, f"trend:{kind}")
    today = datetime.utcnow().date()

    if kind == "ndvi":
        base = generate_ndvi(lat, lon)
        amp, low, high = 0.06, -0.1, 0.9
    elif kind == "soil_moisture":
        base = generate_soil_moisture(lat, lon)
        amp, low, high = 4.0, 0.0, 60.0
    elif kind == "temperature":
        base = generate_temperature(lat, lon)
        amp, low, high = 3.0, -40.0, 55.0
    else:
        base, amp, low, high = 1.0, 0.3, 0.0, 100.0

    points: List[MetricPoint] = []
    # soft seasonal sinusoid + drift
    drift = rng.uniform(-0.003, 0.003)
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        season = math.sin((i / days) * math.pi * 2) * amp * 0.4
        noise = rng.uniform(-amp, amp) * 0.5
        v = base + season + noise + drift * (days - i)
        v = max(low, min(high, v))
        points.append(MetricPoint(date=d.isoformat(), value=round(v, 3)))
    return points


def compute_risk(
    ndvi: float,
    soil_moisture: float,
    precip_7d: float,
    temperature: float,
    wind: float,
) -> Dict[str, Any]:
    """
    Transparent rule-based risk score (0-100).
    Higher = more concerning for agro/fire/drought.
    """
    drivers = []

    # Vegetation stress — capado a [0,100] por las dudas (zonas sobre agua
    # pueden tener NDVI muy negativo, lo que dispararía score > 100).
    ndvi_score = min(100.0, max(0.0, (0.55 - ndvi) / 0.55) * 100)
    drivers.append({
        "name": "Estrés vegetativo (NDVI)",
        "value": ndvi,
        "contribution": round(ndvi_score * 0.30, 1),
    })

    # Drought
    sm_score = min(100.0, max(0.0, (25 - soil_moisture) / 25) * 100)
    drivers.append({
        "name": "Déficit hídrico (humedad suelo)",
        "value": soil_moisture,
        "contribution": round(sm_score * 0.30, 1),
    })

    precip_score = min(100.0, max(0.0, (15 - precip_7d) / 15) * 100)
    drivers.append({
        "name": "Precipitación baja (7d)",
        "value": precip_7d,
        "contribution": round(precip_score * 0.15, 1),
    })

    # Heat & wind (fire proxy)
    temp_score = min(100.0, max(0.0, (temperature - 28) / 15) * 100)
    drivers.append({
        "name": "Temperatura alta",
        "value": temperature,
        "contribution": round(temp_score * 0.15, 1),
    })

    wind_score = min(100.0, max(0.0, (wind - 10) / 30) * 100)
    drivers.append({
        "name": "Viento",
        "value": wind,
        "contribution": round(wind_score * 0.10, 1),
    })

    score = (
        ndvi_score * 0.30
        + sm_score * 0.30
        + precip_score * 0.15
        + temp_score * 0.15
        + wind_score * 0.10
    )
    score = round(max(0.0, min(100.0, score)), 1)

    if score < 25:
        level, rec = "low", "Sin acción. Monitorear semanalmente."
    elif score < 50:
        level, rec = "medium", "Revisar riego y programar inspección."
    elif score < 75:
        level, rec = "high", "Intervención en 48-72h: riego, sombra o mitigación."
    else:
        level, rec = "critical", "Acción inmediata. Alto riesgo agronómico/fuego."

    return {
        "score": score,
        "level": level,
        "drivers": sorted(drivers, key=lambda d: -d["contribution"]),
        "recommendation": rec,
    }
