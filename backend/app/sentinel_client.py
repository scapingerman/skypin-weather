"""
Sentinel Hub Statistical API client.

Flow:
  1. OAuth client_credentials → bearer token (cached until expiry).
  2. POST /api/v1/statistics con un polígono GeoJSON + evalscript que:
     - calcula NDVI = (B08 - B04) / (B08 + B04)
     - descarta píxeles nubosos / sombra / nieve usando la banda SCL
  3. Devuelve la serie diaria de NDVI medio sobre el polígono, últimos 30 días.

Notas:
  - Sentinel-2 revisita cada ~5 días → típicamente 4-8 observaciones válidas/mes.
  - Cache en memoria por hash del polígono (TTL 6h).
  - Si falta cualquier credencial → return None (fallback a mock).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("skyping.sentinel")

CLIENT_ID = (os.environ.get("SENTINEL_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.environ.get("SENTINEL_CLIENT_SECRET") or "").strip()

TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
STATS_URL = "https://services.sentinel-hub.com/api/v1/statistics"

_TTL_S = 6 * 3600          # 6h: Sentinel-2 no va a tener datos nuevos antes
_TIMEOUT_S = 30.0

_CACHE: Dict[str, tuple] = {}
_LOCK = threading.Lock()

_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}
_token_lock = threading.Lock()


# Evalscript: NDVI con filtro SCL per-pixel.
# SCL (Scene Classification Layer):
#   0 NO_DATA, 1 SATURATED, 3 SHADOW,
#   8 CLOUD_MEDIUM, 9 CLOUD_HIGH, 10 THIN_CIRRUS, 11 SNOW_ICE
_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  var invalid = [0, 1, 3, 8, 9, 10, 11];
  var valid = s.dataMask === 1 && invalid.indexOf(s.SCL) === -1;
  var ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-6);
  return { ndvi: [ndvi], dataMask: [valid ? 1 : 0] };
}
"""


def auth_ready() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def _get_token() -> Optional[str]:
    if not auth_ready():
        return None
    now = time.time()
    with _token_lock:
        if _token_cache["token"] and _token_cache["expires_at"] - 60 > now:
            return _token_cache["token"]

    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        with _token_lock:
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + expires_in
        log.info("sentinel OAuth OK (expires in %ds)", expires_in)
        return token
    except httpx.HTTPStatusError as e:
        log.error(
            "sentinel OAuth FAIL %s body=%s",
            e.response.status_code, e.response.text[:300],
        )
        return None
    except Exception as e:
        log.error("sentinel OAuth FAIL: %s", e)
        return None


def _cache_key(geometry: dict) -> str:
    return hashlib.md5(
        json.dumps(geometry, sort_keys=True).encode()
    ).hexdigest()


def _pick_resolution(geometry: dict) -> tuple[float, float, int]:
    """
    Elige (resx, resy) en GRADOS (unidades de CRS84) equivalentes a una
    resolución agronómicamente razonable en metros según el tamaño del polígono.

    Devuelve (resx_deg, resy_deg, res_m_equivalente).

    Consideraciones:
      - Sentinel-2 nativo: 10 m (B04/B08). No tiene sentido pedir menos.
      - Statistical API de Sentinel Hub rechaza >1500 m/pixel para S2L2A.
      - Cap de ~1000 píxeles por lado para controlar consumo de PU.
    """
    try:
        coords = geometry["coordinates"]
        ring = coords[0] if geometry["type"] == "Polygon" else coords[0][0]
        xs = [c[0] for c in ring]
        ys = [c[1] for c in ring]
        mid_lat = (max(ys) + min(ys)) / 2
        m_per_deg_lon = max(1.0, 111_320.0 * math.cos(math.radians(mid_lat)))
        m_per_deg_lat = 111_320.0
        width_m = (max(xs) - min(xs)) * m_per_deg_lon
        height_m = (max(ys) - min(ys)) * m_per_deg_lat
        area_ha = (width_m * height_m) / 10_000

        # Resolución base según tamaño
        if area_ha < 50:       res_m = 10.0
        elif area_ha < 500:    res_m = 20.0
        elif area_ha < 5_000:  res_m = 60.0
        elif area_ha < 50_000: res_m = 100.0
        else:                  res_m = 250.0

        # Cap por grid máximo (~1000 px/lado)
        max_side_m = max(width_m, height_m, 1.0)
        min_res_for_cap = max_side_m / 1000.0
        res_m = max(res_m, min_res_for_cap)

        # Límites duros de la API
        res_m = min(res_m, 1500.0)   # S2L2A hard limit
        res_m = max(res_m, 10.0)     # S2 native

        resx_deg = res_m / m_per_deg_lon
        resy_deg = res_m / m_per_deg_lat
        return (resx_deg, resy_deg, int(round(res_m)))
    except Exception:
        # Fallback: ~20 m equivalentes en el ecuador
        return (20.0 / 111_320.0, 20.0 / 111_320.0, 20)


def fetch_ndvi(geometry: dict) -> Optional[Dict[str, Any]]:
    """
    NDVI medio sobre el polígono, últimos 30 días.

    Returns:
      {
        "current": float,
        "trend": [{"date": "YYYY-MM-DD", "value": float}, ...],
        "source": "sentinel-2",
        "fetched_at": epoch,
        "observations": int,
        "resolution_m": int
      }
      o None ante cualquier error.
    """
    if not auth_ready():
        return None

    key = _cache_key(geometry)
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and (now - cached[0]) < _TTL_S:
            return cached[1]

    token = _get_token()
    if not token:
        return None

    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=90)  # 90d → ventana amplia para zonas nubosas

    resx_deg, resy_deg, res_m = _pick_resolution(geometry)

    payload = {
        "input": {
            "bounds": {
                "geometry": geometry,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                },
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {"maxCloudCoverage": 95},
                }
            ],
        },
        "aggregation": {
            "timeRange": {
                "from": start.isoformat().replace("+00:00", "Z"),
                "to": end.isoformat().replace("+00:00", "Z"),
            },
            # Bins de 5 días ≈ ciclo de revisita de Sentinel-2. En cada bin
            # Sentinel Hub se queda con la imagen menos nubosa que pase el filtro.
            "aggregationInterval": {"of": "P5D"},
            "evalscript": _EVALSCRIPT,
            "resx": resx_deg,
            "resy": resy_deg,
        },
    }

    try:
        r = httpx.post(
            STATS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        log.warning(
            "sentinel statistical FAIL %s body=%s",
            e.response.status_code, e.response.text[:500],
        )
        return None
    except Exception as e:
        log.warning("sentinel statistical FAIL: %s", e)
        return None

    observations = []
    rejected = {"no_mean": 0, "nan": 0, "out_of_range": 0, "low_ratio": 0}
    for entry in data.get("data", []):
        iv = entry.get("interval") or {}
        date = (iv.get("from") or "")[:10]
        bands = (
            entry.get("outputs", {})
            .get("ndvi", {})
            .get("bands", {})
        )
        stats = bands.get("B0", {}).get("stats", {})
        mean = stats.get("mean")

        # Sentinel Hub devuelve NaN cuando no hay píxeles válidos (toda la pasada
        # era nube). Puede venir como float('nan') o string "NaN".
        if mean is None:
            rejected["no_mean"] += 1
            continue
        try:
            mean_f = float(mean)
        except (TypeError, ValueError):
            rejected["nan"] += 1
            continue
        if mean_f != mean_f:  # NaN
            rejected["nan"] += 1
            continue
        if not (-1.0 <= mean_f <= 1.0):  # fuera de rango
            rejected["out_of_range"] += 1
            continue

        # noDataCount vs sampleCount: si casi todos eran inválidos, descartar
        sample_count = stats.get("sampleCount", 0) or 0
        no_data = stats.get("noDataCount", 0) or 0
        valid_ratio = (sample_count - no_data) / sample_count if sample_count else 0
        if valid_ratio < 0.01:  # aflojado de 5% → 1%
            rejected["low_ratio"] += 1
            continue

        observations.append({"date": date, "value": round(mean_f, 3)})

    if not observations:
        n_intervals = len(data.get("data", []))
        sample = data.get("data", [])[:2]
        log.warning(
            "sentinel: 0 observaciones válidas en 90d (intervals=%d rejected=%s). "
            "Zona probablemente muy nubosa en esta ventana. Sample: %s",
            n_intervals,
            rejected,
            json.dumps(sample)[:800],
        )
        return None

    observations.sort(key=lambda x: x["date"])
    current = observations[-1]["value"]

    result = {
        "current": current,
        "trend": observations,
        "source": "sentinel-2",
        "fetched_at": now,
        "observations": len(observations),
        "resolution_m": res_m,
    }
    with _LOCK:
        _CACHE[key] = (now, result)
    log.info(
        "sentinel NDVI OK obs=%d current=%.3f res=%dm",
        len(observations), current, res_m,
    )
    return result


def cache_stats() -> Dict[str, Any]:
    with _LOCK:
        return {
            "ndvi_entries": len(_CACHE),
            "ttl_s": _TTL_S,
            "auth_ready": auth_ready(),
        }
