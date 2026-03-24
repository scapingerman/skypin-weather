-- Wind gusts (km/h, Open-Meteo) for polygon snapshot — run once on existing DBs
ALTER TABLE api.area_selection_hourly
    ADD COLUMN IF NOT EXISTS wind_gusts_10m DOUBLE PRECISION;
