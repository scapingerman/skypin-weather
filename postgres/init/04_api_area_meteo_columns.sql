-- Extra Open-Meteo hourly fields for polygon Grafana (existing DBs: run once)
ALTER TABLE api.area_selection_hourly
    ADD COLUMN IF NOT EXISTS wind_direction_10m INTEGER,
    ADD COLUMN IF NOT EXISTS surface_pressure DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS cloud_cover INTEGER;
