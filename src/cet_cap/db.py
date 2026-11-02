"""PostgreSQL-only database engine for the CET CAP portal."""
from __future__ import annotations
import os
from sqlalchemy import Engine, create_engine


def get_engine(db_url: str | None = None) -> Engine:
    """Return the single authoritative PostgreSQL engine with a bounded pool.

    SQLite is deliberately unsupported: a second local database path could
    make admin-approved data differ from the data read by the public site.
    backend.api.get_active_engine() caches this engine for public requests.
    """
    url = (db_url or os.getenv("DATABASE_URL", "")).strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required; PostgreSQL is the only supported database.")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+psycopg2://"):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL.")
    # Keep the default connection footprint conservative for small hosted
    # instances. Larger deployments can tune these without changing code.
    pool_size = int(os.getenv("CET_DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("CET_DB_MAX_OVERFLOW", "5"))
    pool_timeout = float(os.getenv("CET_DB_POOL_TIMEOUT", "5"))
    if pool_size < 1 or max_overflow < 0 or pool_timeout <= 0:
        raise RuntimeError("CET_DB_POOL_SIZE/MAX_OVERFLOW/POOL_TIMEOUT must be positive (overflow may be zero).")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=1800,
        future=True,
    )
