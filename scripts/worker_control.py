"""Cooperative pause/cancel checkpoints for CAPFind PDF extraction.

When CAPFIND_JOB_ID is supplied, PostgreSQL job state is authoritative so an
admin request routed to another backend instance still controls the worker.
Local marker files remain a fallback for local tests and legacy tooling.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_DB_CONN = None
_DB_LAST_POLL = 0.0
_DB_LAST_WRITE = 0.0
_DB_STATUS = None


def _write_progress(directory: Path, payload: dict) -> None:
    temp = directory / "progress.json.tmp"
    temp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temp.replace(directory / "progress.json")


def _db_connection():
    global _DB_CONN
    if _DB_CONN is not None and not getattr(_DB_CONN, "closed", True):
        return _DB_CONN
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = "postgresql://" + database_url[len("postgresql+psycopg2://"):]
    import psycopg2
    _DB_CONN = psycopg2.connect(database_url, connect_timeout=3)
    _DB_CONN.autocommit = True
    return _DB_CONN


def _db_status(force: bool = False):
    global _DB_LAST_POLL, _DB_STATUS, _DB_CONN
    job_id = os.environ.get("CAPFIND_JOB_ID", "").strip()
    if not job_id or not os.environ.get("DATABASE_URL", "").strip():
        return None
    now = time.monotonic()
    if not force and now - _DB_LAST_POLL < 0.5:
        return _DB_STATUS
    try:
        conn = _db_connection()
        if conn is None:
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM import_jobs WHERE id=%s", (int(job_id),))
            row = cur.fetchone()
        _DB_STATUS = str(row[0]).upper() if row else None
        _DB_LAST_POLL = now
        return _DB_STATUS
    except Exception:
        try:
            if _DB_CONN is not None:
                _DB_CONN.close()
        except Exception:
            pass
        _DB_CONN = None
        _DB_LAST_POLL = now
        return _DB_STATUS


def _write_db_progress(page: int, total: int) -> None:
    global _DB_LAST_WRITE, _DB_CONN
    job_id = os.environ.get("CAPFIND_JOB_ID", "").strip()
    worker_id = os.environ.get("CAPFIND_WORKER_ID", "").strip()
    if not job_id or not worker_id or not os.environ.get("DATABASE_URL", "").strip():
        return
    now = time.monotonic()
    if now - _DB_LAST_WRITE < 0.5:
        return
    try:
        conn = _db_connection()
        if conn is None:
            return
        current_chunk = int(os.environ.get("CAPFIND_CHUNK_INDEX", "0") or 0)
        total_chunks = int(os.environ.get("CAPFIND_TOTAL_CHUNKS", "0") or 0)
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE import_jobs
                   SET current_page=%s,total_pages=%s,current_chunk=%s,total_chunks=%s
                   WHERE id=%s AND worker_id=%s""",
                (int(page), int(total), current_chunk, total_chunks, int(job_id), worker_id),
            )
        _DB_LAST_WRITE = now
    except Exception:
        try:
            if _DB_CONN is not None:
                _DB_CONN.close()
        except Exception:
            pass
        _DB_CONN = None


def checkpoint(page: int, total: int) -> None:
    raw_dir = os.environ.get("CAPFIND_JOB_CONTROL_DIR", "").strip()
    if not raw_dir and not os.environ.get("CAPFIND_JOB_ID", "").strip():
        return
    directory = Path(raw_dir) if raw_dir else None
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
    cancel = directory / "CANCEL" if directory else None
    pause = directory / "PAUSE" if directory else None
    page_offset = int(os.environ.get("CAPFIND_PAGE_OFFSET", "0") or 0)
    global_total = int(os.environ.get("CAPFIND_TOTAL_PAGES", str(total)) or total)
    global_page = int(page) + page_offset

    def cancelled() -> bool:
        return bool(cancel and cancel.exists()) or _db_status() == "CANCELLED"

    def paused() -> bool:
        return bool(pause and pause.exists()) or _db_status() == "PAUSED"

    if cancelled():
        raise RuntimeError("CAPFIND_WORKER_CANCELLED")
    payload = {
        "page": global_page, "part_page": int(page), "total": global_total,
        "part_total": int(total), "state": "RUNNING", "updated_at": time.time(),
    }
    if directory is not None:
        _write_progress(directory, payload)
    _write_db_progress(global_page, global_total)

    while paused():
        if cancelled():
            raise RuntimeError("CAPFIND_WORKER_CANCELLED")
        payload["state"] = "PAUSED"
        payload["updated_at"] = time.time()
        if directory is not None:
            _write_progress(directory, payload)
        _write_db_progress(global_page, global_total)
        time.sleep(0.5)

    payload["state"] = "RUNNING"
    payload["updated_at"] = time.time()
    if directory is not None:
        _write_progress(directory, payload)
    _write_db_progress(global_page, global_total)
