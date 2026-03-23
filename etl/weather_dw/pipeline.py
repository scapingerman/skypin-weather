from __future__ import annotations

import logging
from uuid import UUID, uuid4

import httpx

from weather_dw.config import load_settings
from weather_dw.db import connection_ctx
from weather_dw.extract.open_meteo import fetch_hourly_forecast_rows
from weather_dw.extract.targets import load_city_targets
from weather_dw.load.dimensions import sync_dim_cities
from weather_dw.load.staging import insert_staging_rows
from weather_dw.transform.runner import run_downstream_sql

LOG = logging.getLogger(__name__)


def _register_run_start(run_id: UUID) -> None:
    settings = load_settings()
    with connection_ctx(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.etl_runs (run_id, status)
                VALUES (%s, 'running')
                """,
                (str(run_id),),
            )
        conn.commit()


def _finalize_success(run_id: UUID, rows_staged: int) -> None:
    settings = load_settings()
    with connection_ctx(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE meta.etl_runs
                SET status = 'success',
                    finished_at = now(),
                    rows_staged = %s
                WHERE run_id = %s
                """,
                (rows_staged, str(run_id)),
            )
        conn.commit()


def _finalize_failure(run_id: UUID, message: str) -> None:
    settings = load_settings()
    with connection_ctx(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE meta.etl_runs
                SET status = 'failed',
                    finished_at = now(),
                    error_message = %s
                WHERE run_id = %s
                """,
                (message[:4000], str(run_id)),
            )
        conn.commit()


def run_pipeline() -> UUID:
    settings = load_settings()
    run_id = uuid4()
    LOG.info("Starting ETL run_id=%s", run_id)
    _register_run_start(run_id)

    try:
        cities = load_city_targets(settings.targets_csv_path)
        total_staged = 0
        with connection_ctx(settings) as conn:
            with conn.transaction():
                sync_dim_cities(conn, cities)
                with httpx.Client() as client:
                    for city in cities:
                        rows = fetch_hourly_forecast_rows(
                            client,
                            settings,
                            city.city_id,
                            city.latitude,
                            city.longitude,
                        )
                        total_staged += insert_staging_rows(conn, run_id, rows)
                run_downstream_sql(conn, run_id)
        _finalize_success(run_id, total_staged)
    except Exception as exc:
        LOG.exception("ETL run failed run_id=%s", run_id)
        _finalize_failure(run_id, str(exc))
        raise

    LOG.info("ETL success run_id=%s rows_staged=%s", run_id, total_staged)
    return run_id
