# Weather mini data warehouse + Grafana

Reference ETL: **Open-Meteo** (hourly forecast) + **threshold CSV** (manual spreadsheet substitute) → layered **PostgreSQL** (`meta` / `stg` / `dim` / `fact` / `mart`) → **Grafana**.

Technical roadmap by phase: [ROADMAP.md](./ROADMAP.md).

## Requirements

- Docker Desktop (Compose v2)
- Ports **5432** and **3000** free (or override in `.env`)

## Quick start

```bash
copy .env.example .env
docker compose up -d postgres grafana
docker compose run --rm etl
```

- Grafana: http://localhost:3000 (default user/password `admin` / `admin`, configurable via `.env`)
- Postgres: `localhost:5432`, database `weather_dw`, user `weather` / `weather`

Postgres datasource in Grafana: **WeatherDW** (provisioned), user **`grafana_ro`** / `grafana` (read-only on `mart`, `dim`, `meta`).

## Sample query for panels (latest successful run)

```sql
WITH latest AS (
  SELECT run_id
  FROM meta.etl_runs
  WHERE status = 'success'
  ORDER BY finished_at DESC NULLS LAST
  LIMIT 1
)
SELECT m.*
FROM mart.mart_city_hourly_risk m
JOIN latest l ON m.run_id = l.run_id
ORDER BY m.storm_risk_flag DESC, m.risk_score DESC, m.forecast_ts_utc;
```

## Repository layout

| Path | Role |
|------|------|
| `docker-compose.yml` | Postgres, Grafana, `etl` batch job |
| `postgres/init/` | Initial DDL (schemas + tables + Grafana role) |
| `data/targets/city_targets.csv` | Per-city thresholds (versioned spreadsheet) |
| `etl/weather_dw/` | Python package: extract → load `stg` + `dim` → SQL transform |
| `grafana/provisioning/` | Datasources and dashboards |

## Diagram

See the Mermaid flow in [ROADMAP.md](./ROADMAP.md).

## Local ETL development (without rebuilding the image)

```bash
cd etl
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set POSTGRES_HOST=localhost
set POSTGRES_USER=weather
set POSTGRES_PASSWORD=weather
set POSTGRES_DB=weather_dw
set TARGETS_CSV_PATH=..\data\targets\city_targets.csv
python -m weather_dw
```

## Notes

- If you change `POSTGRES_DB`, update `grafana/provisioning/datasources/datasources.yml` (`jsonData.database`) as well.
- Open-Meteo does not require an API key for basic use; keep reasonable request rates when scheduling runs.
