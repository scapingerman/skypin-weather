from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from weather_dw.config import Settings


@contextmanager
def connection_ctx(settings: Settings) -> Iterator[Connection]:
    conn = psycopg.connect(settings.pg_dsn, autocommit=False)
    try:
        yield conn
    finally:
        conn.close()
