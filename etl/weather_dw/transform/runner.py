from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from psycopg import Connection

LOG = logging.getLogger(__name__)

_SQL_PATH = Path(__file__).resolve().parent / "sql" / "refresh_downstream.sql"


def _sql_batches(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.splitlines():
        if line.lstrip().startswith("--"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    parts: list[str] = []
    for chunk in text.split(";"):
        stmt = chunk.strip()
        if stmt:
            parts.append(stmt)
    return parts


def run_downstream_sql(conn: Connection, run_id: UUID) -> None:
    params = {"run_id": str(run_id)}
    batches = _sql_batches(_SQL_PATH.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for stmt in batches:
            cur.execute(stmt, params)
    LOG.info("Transform SQL applied (%s statements) run_id=%s", len(batches), run_id)
