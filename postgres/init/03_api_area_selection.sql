-- Snapshot of map-polygon Open-Meteo risk (hourly) for Grafana ?var-selection_id=
-- Existing volumes: 03, 04, 05 (wind gust column): postgres/init/04_*.sql, 05_api_wind_gust_column.sql

CREATE SCHEMA IF NOT EXISTS api;

CREATE TABLE IF NOT EXISTS api.area_selection_hourly (
    selection_id UUID NOT NULL,
    place_key TEXT NOT NULL,
    place_name TEXT NOT NULL,
    osm_place TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    forecast_ts_utc TIMESTAMPTZ NOT NULL,
    temperature_2m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    precipitation_probability INTEGER,
    weathercode INTEGER,
    wind_speed_10m DOUBLE PRECISION,
    wind_gusts_10m DOUBLE PRECISION,
    wind_direction_10m INTEGER,
    surface_pressure DOUBLE PRECISION,
    cloud_cover INTEGER,
    storm_risk_flag BOOLEAN NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    alert_rain_mm_h DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (selection_id, place_key, forecast_ts_utc)
);

CREATE INDEX IF NOT EXISTS idx_area_sel_selection
    ON api.area_selection_hourly (selection_id);

CREATE INDEX IF NOT EXISTS idx_area_sel_time
    ON api.area_selection_hourly (selection_id, forecast_ts_utc);

GRANT USAGE ON SCHEMA api TO weather;
GRANT INSERT, SELECT, DELETE ON api.area_selection_hourly TO weather;

GRANT USAGE ON SCHEMA api TO grafana_ro;
GRANT SELECT ON api.area_selection_hourly TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO grafana_ro;
