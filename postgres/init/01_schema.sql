-- Layered warehouse: meta, stg, dim, fact, mart
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dim;
CREATE SCHEMA IF NOT EXISTS fact;
CREATE SCHEMA IF NOT EXISTS mart;

-- ETL run registry
CREATE TABLE meta.etl_runs (
    run_id          UUID PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error_message   TEXT,
    rows_staged     INTEGER,
    source_system   TEXT NOT NULL DEFAULT 'open_meteo'
);

CREATE INDEX idx_etl_runs_started ON meta.etl_runs (started_at DESC);

-- Manual / spreadsheet-like targets per city
CREATE TABLE dim.dim_city (
    city_id              INTEGER PRIMARY KEY,
    city_name            TEXT NOT NULL,
    country_code         TEXT NOT NULL DEFAULT 'AR',
    latitude             DOUBLE PRECISION NOT NULL,
    longitude            DOUBLE PRECISION NOT NULL,
    alert_rain_mm_h      DOUBLE PRECISION NOT NULL DEFAULT 3.0,
    min_precip_prob_pct  INTEGER NOT NULL DEFAULT 40,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Raw hourly forecast rows per extraction run
CREATE TABLE stg.stg_open_meteo_hourly (
    run_id                   UUID NOT NULL REFERENCES meta.etl_runs (run_id) ON DELETE CASCADE,
    city_id                  INTEGER NOT NULL REFERENCES dim.dim_city (city_id),
    forecast_ts_utc          TIMESTAMPTZ NOT NULL,
    temperature_2m           DOUBLE PRECISION,
    precipitation            DOUBLE PRECISION,
    precipitation_probability INTEGER,
    weathercode              INTEGER,
    wind_speed_10m           DOUBLE PRECISION,
    wind_direction_10m       INTEGER,
    surface_pressure         DOUBLE PRECISION,
    cloud_cover              INTEGER,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, city_id, forecast_ts_utc)
);

CREATE INDEX idx_stg_open_meteo_run ON stg.stg_open_meteo_hourly (run_id);

-- Validated business-grain copy (per run)
CREATE TABLE fact.fact_weather_hourly_forecast (
    run_id                   UUID NOT NULL,
    city_id                  INTEGER NOT NULL REFERENCES dim.dim_city (city_id),
    forecast_ts_utc          TIMESTAMPTZ NOT NULL,
    temperature_2m           DOUBLE PRECISION,
    precipitation            DOUBLE PRECISION,
    precipitation_probability INTEGER,
    weathercode              INTEGER,
    wind_speed_10m           DOUBLE PRECISION,
    wind_direction_10m       INTEGER,
    surface_pressure         DOUBLE PRECISION,
    cloud_cover              INTEGER,
    PRIMARY KEY (run_id, city_id, forecast_ts_utc),
    CONSTRAINT fk_fact_run FOREIGN KEY (run_id) REFERENCES meta.etl_runs (run_id) ON DELETE CASCADE
);

CREATE INDEX idx_fact_run ON fact.fact_weather_hourly_forecast (run_id);

-- Consumption layer for Grafana / BI
CREATE TABLE mart.mart_city_hourly_risk (
    run_id                   UUID NOT NULL,
    city_id                  INTEGER NOT NULL,
    city_name                TEXT NOT NULL,
    forecast_ts_utc          TIMESTAMPTZ NOT NULL,
    temperature_2m           DOUBLE PRECISION,
    precipitation            DOUBLE PRECISION,
    precipitation_probability INTEGER,
    weathercode              INTEGER,
    wind_speed_10m           DOUBLE PRECISION,
    storm_risk_flag          BOOLEAN NOT NULL,
    risk_score               DOUBLE PRECISION NOT NULL,
    alert_rain_mm_h          DOUBLE PRECISION NOT NULL
);

CREATE INDEX idx_mart_run_time ON mart.mart_city_hourly_risk (run_id, forecast_ts_utc);
CREATE INDEX idx_mart_city_time ON mart.mart_city_hourly_risk (city_id, forecast_ts_utc);
CREATE INDEX idx_mart_risk ON mart.mart_city_hourly_risk (storm_risk_flag) WHERE storm_risk_flag = true;

COMMENT ON SCHEMA stg IS 'Landed and lightly typed data per extraction run';
COMMENT ON SCHEMA mart IS 'Curated metrics and business flags for dashboards';
