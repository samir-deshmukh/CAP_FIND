#!/usr/bin/env python3
"""Run one bounded website-resolver step outside the FastAPI web process."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from backend.admin.db import connect
from backend.admin.resolver import resolve_import_job

log = logging.getLogger("resolver_worker")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

LOCK_KEY = 73829104


def acquire_lock(conn):
    # PostgreSQL advisory locks serialize resolver children on the single
    # low-memory Render instance. Fail closed if lock state cannot be checked.
    try:
        row = conn.execute("SELECT pg_try_advisory_lock(?) AS locked", (LOCK_KEY,)).fetchone()
        return bool(row and row["locked"])
    except Exception:
        log.exception("could not acquire resolver advisory lock")
        conn.rollback()
        return False


def release_lock(conn):
    try:
        conn.execute("SELECT pg_advisory_unlock(?)", (LOCK_KEY,))
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=int, nargs="?")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--resolver-scan", action="store_true")
    parser.add_argument("--status")
    parser.add_argument("--institution-code")
    parser.add_argument("--exclude-code", action="append", default=[])
    args = parser.parse_args()
    if not args.resolver_scan and args.job_id is None:
        parser.error("job_id is required unless --resolver-scan is used")
    with connect() as lock_conn:
        if not acquire_lock(lock_conn):
            result = {"ok": True, "busy": True,
                      "reason": "Another resolver step is already running; waiting safely."}
            if args.resolver_scan:
                print("CAPFIND_RESOLVER_RESULT=" + json.dumps(result), flush=True)
                return 0
            log.info("resolver already running; deferring job %s", args.job_id)
            return 0
        try:
            if args.resolver_scan:
                result = resolve_import_job(
                    None, limit=1, status_filter=args.status,
                    exclude_codes=args.exclude_code,
                    institution_code=args.institution_code,
                )
            else:
                result = resolve_import_job(args.job_id, limit=max(1, min(args.limit, 1)))
            print("CAPFIND_RESOLVER_RESULT=" + json.dumps(result), flush=True)
            return 0 if result.get("ok") else 1
        except Exception:
            log.exception("resolver worker failed for job %s", args.job_id)
            return 1
        finally:
            try:
                release_lock(lock_conn)
                lock_conn.commit()
            except Exception:
                log.exception("could not release resolver advisory lock cleanly")
                lock_conn.rollback()


if __name__ == "__main__":
    raise SystemExit(main())
