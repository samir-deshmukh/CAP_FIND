"""Shared PostgreSQL bootstrap helpers for CLI ingestion tools."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text

from src.cet_cap.db import get_engine

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'db' / 'schema_postgres.sql'


def engine_for(db_url: str | None = None):
    return get_engine(db_url)


def bootstrap_schema(engine) -> None:
    """Create the authoritative schema idempotently.

    schema_postgres.sql currently contains standalone CREATE statements, so
    executing each non-comment statement is sufficient and avoids depending
    on psql being installed in the application container.
    """
    raw = SCHEMA.read_text(encoding='utf-8')
    statements = []
    for stmt in raw.split(';'):
        stmt = re.sub(r'--[^\n]*', '', stmt).strip()
        if stmt:
            statements.append(stmt)
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
