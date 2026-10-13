# Preparación entrevista — Data Engineer

Documento basado **solo** en lo que existe en este repositorio (código, SQL, Docker, docs).  
Si algo no se puede afirmar desde el repo, se marca **No surge del repo**.

## Alcance del repo (importante)

Este GitHub contiene **dos historias de git sin ancestro común**:

| Rama | Qué es | Relevancia DE |
|------|--------|----------------|
| **`main`** | Mini data warehouse meteorológico: ETL Python → PostgreSQL (`meta`/`stg`/`dim`/`fact`/`mart`) → Grafana + API de mapa | **Proyecto principal para entrevista DE** |
| **`master`** | MVP “Skyping Weather”: zonas agrícolas en mapa, NDVI/clima/riesgo vía FastAPI + React | App de producto; no es un lakehouse ni un batch ETL |

**No hay telemetría industrial** (PLC, SCADA, sensores de planta, IoT OT) en ninguna rama.  
Los “datos de series temporales” del proyecto DE son **pronósticos horarios de clima** (Open-Meteo) y umbrales por ciudad en CSV.

---

## 1. ¿Qué hace el sistema, en una frase?

**Implementado (`main`):** un ETL batch que baja el forecast horario de Open-Meteo para ciudades del CSV, lo aterriza en PostgreSQL por capas y calcula un mart de riesgo de tormenta/lluvia para Grafana (`README.md`; `etl/weather_dw/pipeline.py` → `run_pipeline`).  
Hay además una API FastAPI (`api/app/main.py` → `area_risk`) que, al dibujar un polígono, consulta Overpass (lugares OSM) + Open-Meteo y aplica las mismas reglas de riesgo.  
**No implementado:** lakehouse (S3/Glue/Athena/Iceberg), telemetría industrial, orquestador programado en producción.

---

## 2. ¿De dónde salen los datos y cada cuánto se procesan?

**Fuentes implementadas (`main`):**
- **CSV de umbrales/ciudades:** `data/targets/city_targets.csv`, leído por `load_city_targets` en `etl/weather_dw/extract/targets.py`.
- **Open-Meteo Forecast API:** `fetch_hourly_forecast_rows` en `etl/weather_dw/extract/open_meteo.py` (campos horarios: temp, precip, weathercode, viento, etc.).
- **API de área:** Overpass OSM (`api/app/overpass.py` → `fetch_places_in_bbox`) + Open-Meteo on-demand (`api/app/main.py`).

**Frecuencia:** el ETL se ejecuta **bajo demanda** con `docker compose run --rm etl` (`README.md`).  
**No surge del repo** un cron/scheduler activo: el `ROADMAP.md` (Fase 3) propone cron/Prefect/Dagster como futuro, no como código presente.  
Para saber la cadencia real en tu entorno: mirá historial de `meta.etl_runs` o cómo lo corriste vos (manual vs script externo).

---

## 3. ¿Qué volumen de datos maneja (filas, archivos, tamaño)?

**Lo que sí se ve en el repo:**
- **4 ciudades** en `data/targets/city_targets.csv` (Córdoba, Buenos Aires, Rosario, Mendoza).
- Horizon por defecto **`OPEN_METEO_FORECAST_DAYS=3`** (`.env.example`, `etl/weather_dw/config.py` → `forecast_days`).
- Orden de magnitud **por corrida ETL:** ~4 ciudades × 3 días × 24 h ≈ **~288 filas** en `stg`/`fact`/`mart` (derivado del CSV + config; no hay dumps medidos en el repo).
- PK de staging: `(run_id, city_id, forecast_ts_utc)` en `postgres/init/01_schema.sql` → cada corrida **agrega** historia en `stg`.

**No surge del repo:** tamaño en GB, filas históricas acumuladas, QPS, ni volumen de selecciones de mapa en `api.area_selection_hourly`.  
Cómo averiguarlo: `SELECT count(*) FROM stg.stg_open_meteo_hourly;`, `SELECT * FROM meta.etl_runs;`, `pg_total_relation_size(...)`.

---

## 4. ¿Cómo está organizado el almacenamiento (formato, carpetas, particiones)?

**Implementado (`main`) — warehouse relacional, no object storage:**
- Schemas: `meta`, `stg`, `dim`, `fact`, `mart` (`postgres/init/01_schema.sql`).
- Tablas clave: `meta.etl_runs`, `stg.stg_open_meteo_hourly`, `dim.dim_city`, `fact.fact_weather_hourly_forecast`, `mart.mart_city_hourly_risk`.
- Persistencia: volumen Docker `pg_data` (`docker-compose.yml`).
- “Particionado” de negocio: por **`run_id`** (cada extracción) + timestamp `forecast_ts_utc`; índices por `run_id` / ciudad / riesgo (`01_schema.sql`).
- Capa API opcional: `api.area_selection_hourly` (`postgres/init/03_api_area_selection.sql`).

**No existe en el repo:** Parquet, Iceberg, particiones Hive-style `yyyy/mm/dd` en S3, ni data lake.

**Rama `master` (otro producto):** zonas en **SQLite** (`backend/app/db.py` → `ZoneORM`, path `SKYPING_DB_PATH`); métricas/series **no se persisten** como tablas de hechos (se calculan/cachean en memoria al request).

---

## 5. ¿Qué transformaciones y validaciones se aplican?

**ETL (`main`):**
1. Extract Open-Meteo → filas tipadas (`fetch_hourly_forecast_rows`).
2. Upsert dimensiones ciudad SCD0 (`sync_dim_cities` / `ON CONFLICT` en `etl/weather_dw/load/dimensions.py`).
3. Insert append a staging (`insert_staging_rows` en `etl/weather_dw/load/staging.py`).
4. SQL versionado `refresh_downstream.sql` vía `run_downstream_sql`:
   - `DELETE`+`INSERT` fact filtrando `run_id` y join a `dim.dim_city`.
   - Mart: `storm_risk_flag` (weathercodes 95/96/99 **o** lluvia ≥ umbral CSV **y** prob ≥ umbral) + `risk_score` acotado a 100.

**Validaciones explícitas:**
- CSV vacío / ausente → error (`load_city_targets`).
- HTTP Open-Meteo: `raise_for_status` (falla el run).
- Geometría polígono inválida / bbox demasiado grande en API (`area_risk` en `api/app/main.py`).
- Checks de status en `meta.etl_runs` (`running|success|failed`).

**No implementado (roadmap Fase 2):** checks de “filas esperadas por ciudad”, nulls críticos sistemáticos, etc.

---

## 6. ¿Qué pasa si el proceso falla? ¿Hay reintentos, logs o alertas?

**ETL (`pipeline.py` → `run_pipeline`):**
- Registra `meta.etl_runs` en `running`; ante excepción → `failed` + `error_message` (`_finalize_failure`) y re-lanza.
- Transacción única alrededor de dim + staging + transform (`connection_ctx` + `conn.transaction()`): si falla a mitad, no deja fact/mart de ese run inconsistente *dentro de esa transacción*.
- Logs stdout vía `logging` (`logging_conf.py`, `LOG.exception` en fallo).
- **No hay reintentos HTTP** en el cliente ETL Open-Meteo (`extract/open_meteo.py`).
- **No hay alertas** (email/Slack/PagerDuty/Grafana Alerting): Fase 4 del `ROADMAP.md`, no código.

**API (`main.py`):**
- Open-Meteo: hasta **3 intentos** ante connect/timeout (`_fetch_hourly` loop `range(3)`).
- Overpass: prueba **varios mirrors** ante 429/502/503/504.
- Persistencia de selección: si falla, se loguea y no tumba toda la respuesta (bloque `except` al persistir).

---

## 7. ¿Cómo se evita procesar dos veces lo mismo o duplicar filas?

**Implementado:**
- Cada corrida genera un **`run_id` UUID nuevo** (`uuid4` en `run_pipeline`); staging/fact/mart van etiquetados por run.
- PK `(run_id, city_id, forecast_ts_utc)` en `stg` y `fact` evita duplicar la misma hora **dentro del mismo run**.
- Transform hace `DELETE ... WHERE run_id = %(run_id)s` antes del `INSERT` (idempotencia **del transform de ese run**, no del histórico).
- Consumo Grafana típico: join al **último `meta.etl_runs` con `status = 'success'`** (`README.md` sample query) → re-correr el ETL no “pisa” el mart anterior; agrega otro run.
- `dim.dim_city`: upsert por `city_id` (no duplica ciudades).

**No implementado:** deduplicación cross-run de forecast “igual”, exactly-once con cola, ni watermarks de late data.

---

## 8. ¿Cómo se ejecuta y se despliega (Docker, programado, manual, CI)?

**`main`:**
- **Docker Compose:** servicios `postgres`, `grafana`, `etl` (job), `api` (`docker-compose.yml`).
- ETL: imagen `python:3.12-slim`, `CMD ["python", "-m", "weather_dw"]` (`etl/Dockerfile`); se lanza con `docker compose run --rm etl` (manual / one-shot).
- API y Grafana: servicios de larga duración en compose.
- **CI en `main`:** no hay `.github/workflows` en esa rama.

**`master` (Skyping):**
- `docker compose up --build` (backend FastAPI + frontend Vite).
- CI GitHub Actions: build frontend, `compileall` backend, build Docker, chequeo de secrets Sentinel presentes (valores no impresos) — `.github/workflows/ci.yml`.

**No surge del repo:** despliegue a AWS/ECS/K8s, Terraform, ni schedule productivo.

---

## 9. ¿Qué tecnologías usa y para qué cada una?

### Rama `main` (warehouse)
| Tecnología | Para qué (en este repo) | Evidencia |
|------------|-------------------------|-----------|
| Python 3.12 | Paquete ETL `weather_dw` | `etl/Dockerfile` |
| httpx | Cliente HTTP Open-Meteo / Overpass | `extract/open_meteo.py`, `api/` |
| psycopg 3 | Carga SQL a Postgres | `etl/weather_dw/db.py` |
| PostgreSQL 16 | Warehouse capas + meta runs | `docker-compose.yml`, `01_schema.sql` |
| SQL versionado | Transform fact/mart | `transform/sql/refresh_downstream.sql` |
| Grafana 11 | Dashboards sobre `mart` / `api` | `grafana/provisioning/` |
| FastAPI + Shapely | API riesgo por polígono | `api/app/main.py`, `geo.py` |
| Leaflet (web/) | Dibujar área y ver tabla de riesgo | `web/index.html` |
| Docker Compose | Orquestar Postgres/Grafana/ETL/API | `docker-compose.yml` |
| CSV | Catálogo ciudades + umbrales | `city_targets.csv` |

### Rama `master` (Skyping MVP)
| Tecnología | Para qué |
|------------|----------|
| FastAPI + SQLAlchemy async + SQLite | CRUD zonas multi-tenant |
| Sentinel Hub Statistical API | NDVI real con fallback mock (`sentinel_client.py`) |
| Open-Meteo | Clima y humedad suelo (`weather_client.py`) |
| React + Vite + Leaflet + Recharts | UI mapa y tendencias |
| GitHub Actions | CI build |

---

## 10. ¿Qué mejoraría un data engineer senior si tuviera que llevarlo a AWS (S3, Glue, Athena, Iceberg)?

Basado en **gaps reales** del código actual (no en inventar features ya hechas):

1. **Landing en S3 (raw):** persistir el JSON de Open-Meteo por `run_id`/ciudad/fecha antes de tipar (hoy solo queda fila relacional en `stg`; no hay raw object store).
2. **Tabla Iceberg (o Parquet + Glue Catalog)** particionada por `forecast_date` / `city_id` / `run_date`, consultable con **Athena**, en lugar de solo Postgres local.
3. **Orquestación:** EventBridge Scheduler o Step Functions / Glue Workflow llamando al mismo entrypoint (hoy es `docker compose run` manual; roadmap Fase 3).
4. **Idempotencia y calidad:** Great Expectations/Deequ + fallar el job si faltan horas por ciudad; DLQ/reintentos en extract (el ETL hoy no reintenta HTTP).
5. **Separar compute:** Glue/Spark o EMR Serverless para el SQL de riesgo si el volumen crece; mantener reglas de `refresh_downstream.sql` auditables (el repo ya prefiere SQL versionado — `ROADMAP.md` decisión #2).
6. **Secretos y red:** Secrets Manager + IAM roles (hoy `.env` / variables Compose; defaults de desarrollo en docs).
7. **Observabilidad:** CloudWatch metrics + alarmas sobre `meta.etl_runs.status='failed'` (hoy solo tabla + logs; sin alertas).
8. **No confundir con telemetría industrial:** si la entrevista apunta a OT/IoT, este repo demuestra **patrones** (staging, run_id, mart de alertas, series temporales), pero el dominio es **clima**, no sensores de planta — habría que decirlo explícitamente.

---

## Diagrama de flujo (texto) — rama `main`

```
city_targets.csv                    Open-Meteo Forecast API
       │                                      │
       ▼                                      ▼
 load_city_targets                 fetch_hourly_forecast_rows
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
              run_pipeline (run_id UUID)
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  dim.dim_city   stg.stg_open_   meta.etl_runs
  (upsert)       meteo_hourly    (running→success|failed)
                      │
                      ▼
           refresh_downstream.sql
               │              │
               ▼              ▼
   fact.fact_weather_   mart.mart_city_
   hourly_forecast      hourly_risk
                               │
                               ▼
                            Grafana

Paralelo (on-demand, no es el batch ETL):
  Usuario dibuja polígono (web/)
       → POST /api/area/risk (FastAPI)
       → Overpass (lugares) + Open-Meteo
       → mismas reglas risk.py / SQL mart
       → (opcional) api.area_selection_hourly → Grafana
```

---

## Elevator pitch (English, ~5–6 lines)

I built a small weather data warehouse as a portfolio ETL: a Python batch job pulls hourly Open-Meteo forecasts for a CSV of cities, lands them in PostgreSQL staging keyed by a run UUID, upserts a city dimension, and runs versioned SQL to load a fact table and a risk mart used by Grafana. Failures are recorded in a meta.etl_runs table with an error message, and the transform is scoped per run so reprocessing adds a new run rather than silently merging rows. Separately, a FastAPI service applies the same storm/rain risk rules to places inside a user-drawn map polygon via Overpass and Open-Meteo. The stack is Docker Compose with Postgres and Grafana; there is no cloud lakehouse or industrial telemetry in this repo—it is a layered warehouse pattern on public weather data. Scheduling, Glue/Athena/Iceberg, and production alerting are roadmap items, not implemented features.

---

## Tres preguntas difíciles (con respuesta corta basada en el código)

### 1. “Si el ETL falla a mitad de las ciudades, ¿queda el warehouse a medias?”
**Respuesta:** Dim sync, inserts de staging y el SQL downstream corren dentro de **una sola** `conn.transaction()` en `run_pipeline` (`pipeline.py`). Si una ciudad dispara excepción en el extract, se hace rollback de ese trabajo y `_finalize_failure` marca el `run_id` como `failed`. No hay commit parcial ciudad-por-ciudad.

### 2. “¿Por qué el mart puede tener varios `run_id` y cómo elige Grafana cuál mostrar?”
**Respuesta:** Cada ejecución inserta un `run_id` nuevo; `stg`/`fact`/`mart` conservan historia por run (PK incluye `run_id`). Los paneles usan el patrón del README: CTE `latest` sobre `meta.etl_runs WHERE status = 'success' ORDER BY finished_at DESC LIMIT 1` y join a `mart.mart_city_hourly_risk`.

### 3. “Las reglas de riesgo de la API y del SQL del mart, ¿pueden divergir?”
**Respuesta:** Están **duplicadas a propósito alineadas**: SQL en `refresh_downstream.sql` (codes 95/96/99, umbrales de `dim_city`, fórmula de `risk_score`) y Python en `api/app/risk.py` → `hourly_risk` (mismo conjunto `STORM_CODES` y misma fórmula). Un senior pediría una sola fuente de verdad (p.ej. solo SQL, o tests que comparen ambos). Hoy el comentario del módulo dice que están alineadas, pero son dos implementaciones.

---

## Checklist rápido: implementado vs no existe

| Tema | ¿En el repo? |
|------|----------------|
| ETL batch Open-Meteo → Postgres capas | Sí (`main`) |
| `run_id` + `meta.etl_runs` | Sí |
| Mart de riesgo + Grafana | Sí |
| API mapa polígono + Overpass | Sí |
| Scheduler / cron productivo | No (solo roadmap) |
| Alertas Grafana / Pager | No (roadmap Fase 4) |
| CI en rama `main` | No |
| CI en rama `master` | Sí |
| S3 / Glue / Athena / Iceberg | No |
| Telemetría industrial | No |
| Volumen productivo medido | No surge del repo |

---

*Archivos ancla: `README.md`, `ROADMAP.md`, `etl/weather_dw/pipeline.py`, `postgres/init/01_schema.sql`, `etl/weather_dw/transform/sql/refresh_downstream.sql`, `docker-compose.yml` (rama `main`). Para el otro producto: `backend/app/main.py` y `README.md` en `master`.*
