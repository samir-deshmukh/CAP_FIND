"""PostgreSQL-only admin database access.

The admin workflow and public data now share one authoritative PostgreSQL
DATABASE_URL. There is intentionally no SQLite fallback: using two databases
would allow an approved import to be invisible to the public site.
"""
from __future__ import annotations

import logging
import re
import threading
import traceback
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event as sqlalchemy_event, text
from sqlalchemy.exc import TimeoutError as SQLAlchemyPoolTimeout

log = logging.getLogger("cet-cap-db")
_CHECKOUT_LOCK = threading.Lock()
_CHECKED_OUT_TRACES: dict[int, str] = {}


def _track_checkout(dbapi_connection, connection_record, connection_proxy):
    with _CHECKOUT_LOCK:
        _CHECKED_OUT_TRACES[id(connection_record)] = "".join(traceback.format_stack(limit=18))


def _track_checkin(dbapi_connection, connection_record):
    with _CHECKOUT_LOCK:
        _CHECKED_OUT_TRACES.pop(id(connection_record), None)


def _log_pool_exhaustion(engine):
    with _CHECKOUT_LOCK:
        traces = list(_CHECKED_OUT_TRACES.values())
    log.error(
        "ADMIN_DB_POOL_EXHAUSTED checked_out=%s pool=%s outstanding_checkout_traces=%s",
        engine.pool.checkedout(),
        engine.pool.status(),
        len(traces),
    )
    for index, trace in enumerate(traces, 1):
        log.error("ADMIN_DB_OUTSTANDING_CHECKOUT_%s\\n%s", index, trace)

BASE = Path(__file__).resolve().parents[2]
SCHEMA = BASE / "db" / "admin_schema_postgres.sql"
PUBLIC_SCHEMA = BASE / "db" / "schema_postgres.sql"

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    import os
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required; PostgreSQL is the only supported application database.")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+psycopg2://"):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL.")
    _ENGINE = create_engine(url, pool_pre_ping=True, future=True)
    sqlalchemy_event.listen(_ENGINE, "checkout", _track_checkout)
    sqlalchemy_event.listen(_ENGINE, "checkin", _track_checkin)
    return _ENGINE


def _convert_positional(sql: str, params: tuple[Any, ...] | list[Any] | None):
    """Convert the existing qmark SQL used by the admin code to SQLAlchemy binds."""
    params = tuple(params or ())
    i = 0
    out = []
    for ch in sql:
        if ch == "?":
            out.append(f":p{i}")
            i += 1
        else:
            out.append(ch)
    if i != len(params):
        raise ValueError(f"Expected {i} SQL parameters, received {len(params)}")
    return "".join(out), {f"p{n}": value for n, value in enumerate(params)}


class Result:
    def __init__(self, result, inserted_id=None):
        self._result = result
        self._inserted_id = inserted_id
        self.rowcount = result.rowcount

    @property
    def lastrowid(self):
        return self._inserted_id

    def fetchone(self):
        row = self._result.fetchone()
        return dict(row._mapping) if row is not None else None

    def fetchall(self):
        return [dict(r._mapping) for r in self._result.fetchall()]

    def __iter__(self):
        for row in self._result:
            yield dict(row._mapping)


class Connection:
    def __init__(self):
        engine = _engine()
        try:
            self._conn = engine.connect()
        except SQLAlchemyPoolTimeout:
            _log_pool_exhaustion(engine)
            raise
        self._tx = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Always return the SQLAlchemy connection to the pool, even when
        # commit/rollback itself raises (for example during a DB outage).
        try:
            if exc_type:
                self.rollback()
            else:
                self.commit()
        finally:
            self._conn.close()

    def execute(self, sql: str, params=()):
        sql = sql.replace("BEGIN IMMEDIATE", "BEGIN")
        # Support legacy caller SQL safely: INSERT OR IGNORE is translated to
        # PostgreSQL ON CONFLICT DO NOTHING. New PostgreSQL code should use
        # ON CONFLICT explicitly.
        had_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, flags=re.I))
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.I)
        if had_ignore and re.search(r"ON\s+CONFLICT", sql, flags=re.I) is None:
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        if re.search(r"INSERT\s+INTO", sql, flags=re.I) and re.search(r"ON\s+CONFLICT", sql, flags=re.I) is None:
            table_match = re.search(r"INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.I)
            table = table_match.group(1).lower() if table_match else ""
            # Resolver and local-worker bookkeeping tables use natural/composite
            # primary keys and have no integer id column to return.
            no_surrogate_id = {"college_website_resolver", "local_worker_tokens", "local_worker_receipts"}
            if table not in no_surrogate_id and "RETURNING" not in sql.upper() and "ON CONFLICT DO NOTHING" not in sql.upper():
                sql = sql.rstrip().rstrip(";") + " RETURNING id"
        # INSERT ... ON CONFLICT statements can target tables whose primary
        # key is not named "id" (for example programs.program_id), so do not
        # inject RETURNING id into them.

        converted, values = _convert_positional(sql, params)
        result = self._conn.execute(text(converted), values)
        inserted_id = None
        if "RETURNING id" in converted.upper():
            row = result.fetchone()
            if row is not None:
                inserted_id = row[0]
        return Result(result, inserted_id)

    def execute_many_values(self, sql: str, params=()):
        """Execute one explicitly multi-row SQL statement without RETURNING ids."""
        converted, values = _convert_positional(sql, params)
        result = self._conn.execute(text(converted), values)
        return Result(result)

    def executescript(self, sql: str):
        # PostgreSQL accepts the schema statements individually; comments and
        # blank statements are harmless after splitting on semicolons here.
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                self._conn.exec_driver_sql(statement)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def connect():
    return Connection()


def init_admin_schema():
    with connect() as c:
        # Migrate this column before running PUBLIC_SCHEMA: on an existing
        # database CREATE TABLE IF NOT EXISTS does not add new columns, while
        # the schema's index declaration references program_code immediately.
        # ALTER TABLE IF EXISTS also safely no-ops on a fresh database where
        # the cutoffs table has not been created yet.
        c.execute("ALTER TABLE IF EXISTS cutoffs ADD COLUMN IF NOT EXISTS program_code TEXT")
        # Both public fact tables and admin workflow tables live in the same
        # PostgreSQL database. This prevents an approved import from landing
        # in one store while the public API reads another.
        c.executescript(PUBLIC_SCHEMA.read_text(encoding="utf-8"))
        c.executescript(SCHEMA.read_text(encoding="utf-8"))
        # Forward-compatible migrations for databases created before institute
        # enrichment was expanded to city/address provenance.
        c.execute("""
            CREATE TABLE IF NOT EXISTS import_commit_progress (
                job_id BIGINT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'IDLE',
                stage TEXT NOT NULL DEFAULT 'Waiting',
                processed BIGINT NOT NULL DEFAULT 0,
                total BIGINT NOT NULL DEFAULT 0,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for statement in (
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS district TEXT",
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS address TEXT",
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS city_source TEXT",
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS website_source TEXT",
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS address_source TEXT",
            "ALTER TABLE institutes ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP",
            "ALTER TABLE college_website_resolver ADD COLUMN IF NOT EXISTS address TEXT",
            "ALTER TABLE college_website_resolver ADD COLUMN IF NOT EXISTS city_source TEXT",
            "ALTER TABLE college_website_resolver ADD COLUMN IF NOT EXISTS website_source TEXT",
            "ALTER TABLE college_website_resolver ADD COLUMN IF NOT EXISTS address_source TEXT",
        ):
            c.execute(statement)


def event(c, job_id, event_type, message, progress=None):
    c.execute(
        "INSERT INTO import_events(job_id,event_type,message,progress) VALUES (?,?,?,?)",
        (job_id, event_type, message, progress),
    )


def update_status(c, job_id, status, message=None):
    c.execute("UPDATE import_jobs SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, job_id))
    if message:
        event(c, job_id, "STATUS", message)
