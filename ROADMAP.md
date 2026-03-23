# Roadmap: weather mini data warehouse + Grafana

Target stack: **Python 3.12**, **PostgreSQL 16**, **Grafana**, **Docker Compose**. Pattern **staging → dimensions/facts → marts** with ETL run traceability.

**Status:** Phase 0 implemented in this repo (`docker-compose`, DDL, `weather_dw` package, target CSV, Grafana provisioning). How to run: [README.md](./README.md).

---

## Phase 0 — Foundation (current)

| Item | Detail |
|------|--------|
| Infra | `docker-compose.yml`: `postgres`, `grafana`, `etl` (batch job). Internal network, persistent volumes. |
| Schema | Schemas: `meta` (runs), `stg` (landed raw/normalized), `dim`, `fact`, `mart` (BI / alerting consumption). |
| Data contract | `data/targets/city_targets.csv` = substitute for “Google Sheets” (per-city thresholds). |
| API | Open-Meteo Forecast (+ optional geocoding; no API key for basic use). |
| ETL | `weather_dw` package: env-based config, structured logging, transactions, `run_id` idempotency. |
| Transform | Versioned SQL in repo executed from Python (`transform/runner.py`). |
| Observability | `meta.etl_runs` table + stdout logs (optional JSON logs in a later phase). |

**Done when:** `docker compose run --rm etl` exits successfully; Grafana shows the Postgres datasource; queries against `mart.*` return rows.

---

## Phase 1 — Week 1 (visible MVP)

| Item | Detail |
|------|--------|
| Ingestion | Hourly forecast extraction per city (lat/lon from CSV or geocoding if coordinates missing). |
| Staging | `stg.stg_open_meteo_hourly`: append by `run_id` (history of downloaded forecasts). |
| Dimensions | `dim.dim_city` from CSV (SCD0: upsert by `city_id`). |
| Facts | `fact.fact_weather_hourly_forecast`: load from latest successful run or explicit window (documented). |
| Mart | `mart.mart_city_hourly_risk`: business rules (WMO storm codes + CSV thresholds). |
| Grafana | 3–4 panels: cities at risk table, precipitation/code time series, stat for active alerts. |
| Docs | README with Mermaid diagram and `.env` variables. |

**Done when:** dashboard reflects the latest run; README reproduces on a clean machine.

---

## Phase 2 — Week 2 (multi-source + cross KPIs)

| Item | Detail |
|------|--------|
| Second source | e.g. Open-Meteo **Archive** (1-day history) or a second endpoint (e.g. daily summary) as extra `stg`. |
| Model | Explicit joins in `mart` (anomaly vs historical climate or daily vs hourly). |
| KPIs | SQL window fields (`LEAD`/`LAG` across cities for a demo “propagation” heuristic). |
| Quality | Minimal checks: expected rows per city, critical nulls, `meta.etl_runs` = `failed` on HTTP errors. |

**Done when:** at least one Grafana panel uses a cross-metric (two sources or two granularities).

---

## Phase 3 — Orchestration (Airbyte/Fivetran-style)

| Item | Detail |
|------|--------|
| Scheduler | `cron` in a dedicated container **or** **Prefect** / **Dagster** (OSS) calling the same entrypoint. |
| Light lineage | Tags `source_system`, `entity` on `stg` tables; SQL comments. |
| Secrets | Only `.env` / Docker secrets; no credentials baked into images. |

**Done when:** pipeline runs on a schedule (e.g. every 15 min / hourly) without manual steps.

---

## Phase 4 — Alerts and hardening (“production-light” portfolio)

| Item | Detail |
|------|--------|
| Grafana Alerting | Rules on `mart` queries (`risk_score` threshold, count of cities in alert). |
| DB roles | Read-only user for Grafana on `mart` (+ `dim` if needed). |
| CI | GitHub Actions: lint (`ruff`), `docker compose config`, ETL smoke test against Postgres service. |

---

## Target flow diagram

```mermaid
flowchart LR
  subgraph sources[Sources]
    API[Open-Meteo API]
    CSV[city_targets.csv]
  end
  subgraph etl[ETL container]
    E[Extract]
    L[Load stg]
    T[Transform SQL]
    E --> L --> T
  end
  subgraph warehouse[PostgreSQL]
    STG[stg]
    DIM[dim]
    FACT[fact]
    MART[mart]
    META[meta]
    STG --> DIM
    STG --> FACT
    DIM --> MART
    FACT --> MART
    META -.-> E
  end
  API --> E
  CSV --> E
  MART --> GF[Grafana]
```

---

## Technical decisions (locked)

1. **Incremental runs:** each run has a `run_id`; `stg` keeps extraction history; `mart` is consumed for the **latest successful run** (via `meta.etl_runs` join or documented `processed_up_to_run_id`).
2. **Transforms prefer SQL** (auditable; future dbt migration without rewriting business logic).
3. **No PII:** only public weather data and a city catalog.

---

## References

- [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- [WMO Weather interpretation codes](https://open-meteo.com/en/docs) (table in docs)
- [Grafana PostgreSQL data source](https://grafana.com/docs/grafana/latest/datasources/postgres/)
