-- Parameters: %(run_id)s :: uuid
-- Promote staged hourly rows into fact and curated mart for this run.

DELETE FROM fact.fact_weather_hourly_forecast
WHERE run_id = %(run_id)s::uuid;

INSERT INTO fact.fact_weather_hourly_forecast (
    run_id,
    city_id,
    forecast_ts_utc,
    temperature_2m,
    precipitation,
    precipitation_probability,
    weathercode,
    wind_speed_10m,
    wind_direction_10m,
    surface_pressure,
    cloud_cover
)
SELECT
    s.run_id,
    s.city_id,
    s.forecast_ts_utc,
    s.temperature_2m,
    s.precipitation,
    s.precipitation_probability,
    s.weathercode,
    s.wind_speed_10m,
    s.wind_direction_10m,
    s.surface_pressure,
    s.cloud_cover
FROM stg.stg_open_meteo_hourly AS s
INNER JOIN dim.dim_city AS c ON c.city_id = s.city_id
WHERE s.run_id = %(run_id)s::uuid;

DELETE FROM mart.mart_city_hourly_risk
WHERE run_id = %(run_id)s::uuid;

INSERT INTO mart.mart_city_hourly_risk (
    run_id,
    city_id,
    city_name,
    forecast_ts_utc,
    temperature_2m,
    precipitation,
    precipitation_probability,
    weathercode,
    wind_speed_10m,
    storm_risk_flag,
    risk_score,
    alert_rain_mm_h
)
SELECT
    s.run_id,
    s.city_id,
    c.city_name,
    s.forecast_ts_utc,
    s.temperature_2m,
    s.precipitation,
    s.precipitation_probability,
    s.weathercode,
    s.wind_speed_10m,
    (
        s.weathercode IN (95, 96, 99)
        OR (
            COALESCE(s.precipitation, 0) >= c.alert_rain_mm_h
            AND COALESCE(s.precipitation_probability, 0) >= c.min_precip_prob_pct
        )
    ) AS storm_risk_flag,
    LEAST(
        100.0,
        CASE WHEN s.weathercode IN (95, 96, 99) THEN 70.0 ELSE 0.0 END
        + LEAST(35.0, COALESCE(s.precipitation, 0) * 6.0)
        + LEAST(25.0, COALESCE(s.precipitation_probability, 0) * 0.25)
    ) AS risk_score,
    c.alert_rain_mm_h
FROM stg.stg_open_meteo_hourly AS s
INNER JOIN dim.dim_city AS c ON c.city_id = s.city_id
WHERE s.run_id = %(run_id)s::uuid;
