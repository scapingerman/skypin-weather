# Weather mini data warehouse + Grafana

ETL de referencia: **Open-Meteo** (forecast horario) + **CSV de umbrales** (sustituto de hoja manual) → **PostgreSQL** en capas (`meta` / `stg` / `dim` / `fact` / `mart`) → **Grafana**.

Roadmap técnico por fases: [ROADMAP.md](./ROADMAP.md).

## Requisitos

- Docker Desktop (Compose v2)
- Puerto **5432** y **3000** libres (o cambiarlos en `.env`)

## Arranque rápido

```bash
copy .env.example .env
docker compose up -d postgres grafana
docker compose run --rm etl
```

- Grafana: http://localhost:3000 (usuario/contraseña por defecto `admin` / `admin`, definibles en `.env`)
- Postgres: `localhost:5432`, base `weather_dw`, usuario `weather` / `weather`

Datasource Postgres en Grafana: **WeatherDW** (provisionado), usuario **`grafana_ro`** / `grafana` (solo lectura en `mart`, `dim`, `meta`).

## Consulta útil para paneles (última corrida OK)

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

## Estructura del repo

| Ruta | Rol |
|------|-----|
| `docker-compose.yml` | Postgres, Grafana, job `etl` |
| `postgres/init/` | DDL inicial (schemas + tablas + rol Grafana) |
| `data/targets/city_targets.csv` | Umbrales por ciudad (spreadsheet versionado) |
| `etl/weather_dw/` | Paquete Python: extract → load `stg` + `dim` → SQL transform |
| `grafana/provisioning/` | Datasource Postgres |

## Diagrama

Ver flujo en Mermaid en [ROADMAP.md](./ROADMAP.md).

## Desarrollo local del ETL (sin reconstruir imagen)

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

## Notas

- Si cambiás `POSTGRES_DB`, actualizá también `grafana/provisioning/datasources/datasources.yml` (`jsonData.database`).
- Open-Meteo no requiere API key para el uso básico; respetá límites razonables de frecuencia en orquestación.
