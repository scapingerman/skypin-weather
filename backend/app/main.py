import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .db import DB_PATH, init_db
from .routers import indices, risk, zones
from .sentinel_client import cache_stats as sentinel_cache_stats
from .weather_client import cache_stats as weather_cache_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("skyping")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_db()
    log.info("Skyping Weather API ready")
    yield
    # shutdown — nada por ahora


app = FastAPI(
    title="Skyping Weather API",
    version="0.2.0",
    description="MVP backend: zones (SQLite), NDVI, soil moisture, weather, risk.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    dt = (time.perf_counter() - t0) * 1000
    log.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        dt,
    )
    response.headers["X-Response-Time-ms"] = f"{dt:.1f}"
    return response


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "service": "skyping-weather-api",
        "db_path": DB_PATH,
        "weather_cache": weather_cache_stats(),
        "sentinel_cache": sentinel_cache_stats(),
    }


@app.get("/", tags=["meta"])
def root():
    return {"name": "Skyping Weather API", "docs": "/docs"}


app.include_router(zones.router)
app.include_router(indices.router)
app.include_router(risk.router)
