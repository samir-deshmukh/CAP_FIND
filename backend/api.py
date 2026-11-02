"""
backend/api.py — Public dynamic API for CET CAP portal.

Features:
- Dynamic PostgreSQL-backed queries (no static data files shipped to client)
- Strict input validation (Pydantic / type constraints)
- Parameterized SQL execution (SQL-injection proof)
- In-memory rate limiting to prevent automated scraping
- Server-side pagination & projection (only requested fields, bounded limit)
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from collections import defaultdict
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

# Ensure src/ is importable
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

from cet_cap.db import get_engine
from cet_cap.queries import (
    available_program_families,
    available_years,
    search_college_summary,
    search_college_summary_page,
    search_cutoffs_for_course,
    seat_matrix_for_institute,
)
from cet_cap.search import filter_by_city, summarize_colleges
from .admin.network import client_ip

router = APIRouter(prefix="/api", tags=["Public Portal API"])

# Rate limiting state: client_ip -> list of monotonic timestamps
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_MAX_KEYS = 5000
_request_history: dict[str, list[float]] = {}

# Public course families are data-driven. The database is authoritative;
# never hard-code a single course here because the portal supports the full
# imported CAP dataset.
PUBLIC_COURSES = None
_PUBLIC_COURSES_AT = 0.0
_PUBLIC_COURSES_TTL = 30.0
_SEARCH_METADATA_CACHE: dict[str, tuple[float, dict[str, dict], dict[str, dict], set]] = {}
_SEARCH_METADATA_TTL = 30.0

class _TTLCache:
    """Small thread-safe TTL cache with single-flight computation.

    Public data only changes when an admin publishes a release, so identical
    requests (page-load options/stats, popular searches) can be answered from
    memory. Concurrent misses for the same key compute once instead of
    stampeding the database on the small free-tier instance. Exceptions are
    never cached.
    """

    def __init__(self, max_items: int = 256):
        """Initialize the cache size and locks used to coordinate concurrent requests.

        Connections: Public endpoint handlers share this cache so repeated queries can reuse recent database results.

        """

        self._max = max_items
        self._data: dict = {}
        self._locks: dict = {}
        self._guard = threading.Lock()

    def get_or_set(self, key, ttl: float, factory):
        """Return a cached value or compute and cache it once for the requested key.

        Connections: Endpoint handlers provide the database-backed builder; the per-key lock prevents concurrent cache misses from stampeding PostgreSQL.

        """

        now = time.monotonic()
        hit = self._data.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        try:
            with lock:
                hit = self._data.get(key)
                if hit and time.monotonic() - hit[0] < ttl:
                    return hit[1]
                value = factory()
                with self._guard:
                    if len(self._data) >= self._max:
                        oldest = min(self._data, key=lambda k: self._data[k][0])
                        self._data.pop(oldest, None)
                    self._data[key] = (time.monotonic(), value)
                return value
        finally:
            # Never keep a lock per distinct key forever (keys include user
            # input such as city or an invalid course). Dropping it can at
            # worst let two racing misses compute twice; it cannot return
            # wrong data.
            with self._guard:
                self._locks.pop(key, None)

    def clear(self):
        """Remove all cached public responses.

        Connections: The cache invalidation helper calls this after data publication or rollback.

        """

        with self._guard:
            self._data.clear()


_PUBLIC_CACHE = _TTLCache()


def invalidate_public_caches() -> None:
    """Clear public response and search-metadata caches after production data changes.

    Connections: The admin publishing/rollback workflow calls this so the next candidate API request reads updated PostgreSQL data.

    """

    global PUBLIC_COURSES, _PUBLIC_COURSES_AT
    _PUBLIC_CACHE.clear()
    _SEARCH_METADATA_CACHE.clear()
    PUBLIC_COURSES = None
    _PUBLIC_COURSES_AT = 0.0
_OPTIONS_TTL = 300.0
_STATS_TTL = 300.0
_SEARCH_TTL = 60.0


def available_public_courses(engine) -> list[str]:
    """Return the course families currently present in PostgreSQL, refreshing the short-lived cache when needed.

    Connections: Public search and option builders use this database-backed list instead of maintaining a hard-coded course whitelist.

    """

    global PUBLIC_COURSES, _PUBLIC_COURSES_AT
    now = time.monotonic()
    if PUBLIC_COURSES is not None and now - _PUBLIC_COURSES_AT < _PUBLIC_COURSES_TTL:
        return list(PUBLIC_COURSES)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT p.program_family
            FROM programs p
            WHERE p.program_family IS NOT NULL AND btrim(p.program_family) <> ''
            ORDER BY p.program_family
        """))
        PUBLIC_COURSES = [str(r[0]) for r in rows]
        _PUBLIC_COURSES_AT = now
    return list(PUBLIC_COURSES)

def check_rate_limit(request: Request):
    """Enforce the bounded per-process request limit for the calling client.

    Connections: Every public API route calls this before its database query; client_ip() supplies the normalized client address.

    """

    ip = client_ip(request)
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    # Bound memory when requests arrive from many distinct source addresses.
    if len(_request_history) >= RATE_LIMIT_MAX_KEYS and ip not in _request_history:
        for key in list(_request_history):
            fresh = [stamp for stamp in _request_history[key] if stamp > cutoff]
            if fresh:
                _request_history[key] = fresh
            else:
                del _request_history[key]
        # Sustained high-cardinality traffic may keep every key active.
        # Eviction can weaken throttling for that key but keeps memory bounded.
        while len(_request_history) >= RATE_LIMIT_MAX_KEYS and _request_history:
            _request_history.pop(next(iter(_request_history)))

    timestamps = [stamp for stamp in _request_history.get(ip, []) if stamp > cutoff]
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        _request_history[ip] = timestamps
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Scraping protection active. Please try again shortly.",
        )

    timestamps.append(now)
    _request_history[ip] = timestamps


_engine_cache = None


def get_active_engine():
    """Return the shared SQLAlchemy engine configured for the public API.

    Connections: The engine comes from src/cet_cap/db.py and is reused by query helpers instead of creating a new pool per request.

    """

    global _engine_cache
    if _engine_cache is None:
        _engine_cache = get_engine()
    return _engine_cache


def _db_available(engine) -> bool:
    """Check whether the configured PostgreSQL engine can execute a lightweight query.

    Connections: Public endpoints use this check before returning database-dependent college data.

    """

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _require_public_course(course: str, engine=None) -> None:
    """Reject a course family that is not present in the current database dataset.

    Connections: Uses available_public_courses() so public API routes validate against imported data rather than a fixed list.

    """

    if engine is None:
        engine = get_active_engine()
    if course not in available_public_courses(engine):
        raise HTTPException(status_code=400, detail="Course is not available in the current database dataset.")


@router.get("/options")
def public_options(request: Request, response: Response):
    """Return the city and course options needed to initialize the candidate search form.

    Connections: The frontend calls GET /api/options; the cached builder reads the available values from PostgreSQL.
    """

    check_rate_limit(request)
    response.headers["Cache-Control"] = "public, max-age=60"
    return _PUBLIC_CACHE.get_or_set("options", _OPTIONS_TTL, _build_public_options)


def _build_public_options():
    """Build the public search-form options from current PostgreSQL records.

    Connections: Called through the options cache; uses the shared engine and the database-driven course-family list.

    """

    try:
        engine = get_active_engine()
    except Exception:
        raise HTTPException(status_code=503, detail="Public PostgreSQL data service is unavailable.")
    try:
        with engine.connect() as conn:
            city_rows = conn.execute(text("""
                SELECT DISTINCT i.city
                FROM institutes i
                WHERE i.city IS NOT NULL
                  AND btrim(i.city) <> ''
                  AND EXISTS (
                      SELECT 1
                      FROM cutoffs c
                      JOIN programs p ON p.program_id = c.program_id
                      WHERE c.institution_code = i.institution_code
                        AND EXISTS (SELECT 1 FROM programs p2 WHERE p2.program_id = c.program_id)
                  )
                ORDER BY i.city
            """))
            cities = [str(r[0]) for r in city_rows]
        return {"cities": cities, "courses": available_public_courses(engine)}
    except Exception:
        raise HTTPException(status_code=503, detail="Public PostgreSQL data service is unavailable.")

@router.get("/stats")
def public_stats(request: Request, response: Response):
    """Return aggregate dataset totals for the candidate website.

    Connections: The frontend calls GET /api/stats; the cached builder reads counts from PostgreSQL.
    """

    check_rate_limit(request)
    response.headers["Cache-Control"] = "public, max-age=60"
    return _PUBLIC_CACHE.get_or_set("stats", _STATS_TTL, _build_public_stats)


def _build_public_stats():
    """Calculate the public dataset totals from PostgreSQL.

    Connections: Called by the stats cache and returns the counts used by the candidate-facing summary UI.

    """

    try:
        engine = get_active_engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT COUNT(DISTINCT c.institution_code) AS colleges,
                       COUNT(*) AS cutoff_records,
                       COUNT(DISTINCT c.round) AS cap_rounds,
                       MAX(c.year) AS latest_year
                FROM cutoffs c
                JOIN programs p ON p.program_id = c.program_id
                WHERE p.program_family IS NOT NULL
            """)).mappings().one()
        return {
            "colleges": int(row["colleges"] or 0),
            "cutoff_records": int(row["cutoff_records"] or 0),
            "cap_rounds": int(row["cap_rounds"] or 0),
            "latest_year": int(row["latest_year"] or 0),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Public database statistics are unavailable.")

class CollegeCard(BaseModel):
    id: str
    institution_code: str
    name: str
    city: Optional[str] = None
    website: Optional[str] = None
    course: str
    cutoff: int
    percentile: float
    highest_cutoff: float
    status: str
    years_on_record: int
    history: list[dict] = []
    graph_history: list[dict] = []
    has_cutoff: bool = True
    has_trend: bool = False
    has_seat_matrix: bool = False
    has_website: bool = False
    drawer: Optional[dict] = None

class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[CollegeCard]

def _search_metadata(engine, course: str, institution_codes: list[str]) -> tuple[dict[str, dict], dict[str, dict], dict[str, bool]]:
    """Fetch the extra college-card and drawer metadata for only the requested result-page institutions.

    Connections: The search handler calls this after SQL pagination so metadata work stays bounded to the visible page.

    """

    if not institution_codes:
        return {}, {}, {}

    now = time.monotonic()
    cached = _SEARCH_METADATA_CACHE.get(course)
    if cached and now - cached[0] < _SEARCH_METADATA_TTL:
        cache_at, cached_legacy, cached_seat, queried = cached
        to_query = [code for code in institution_codes if code not in queried]
        if not to_query:
            return (
                {},
                {code: cached_legacy[code] for code in institution_codes if code in cached_legacy},
                {code: cached_seat.get(code, False) for code in institution_codes},
            )
    else:
        cache_at, cached_legacy, cached_seat, queried = now, {}, {}, set()
        to_query = list(institution_codes)

    params = {"course": course}
    placeholders = []
    for index, code in enumerate(to_query):
        key = f"code_{index}"
        placeholders.append(f":{key}")
        params[key] = code
    code_sql = ", ".join(placeholders)

    query = text(
        f"""
        WITH legacy AS (
            SELECT institution_code,
                   jsonb_agg(
                       jsonb_build_object(
                           'year', year,
                           'low', low_percentile,
                           'high', high_percentile,
                           'rank', low_rank
                       )
                       ORDER BY year
                   ) AS rows
            FROM cutoff_college_year_summary
            WHERE program_family = :course
              AND institution_code IN ({code_sql})
            GROUP BY institution_code
        )
        SELECT l.institution_code,
               l.rows AS legacy_rows,
               EXISTS (
                   SELECT 1 FROM seat_matrix_runtime sm
                   WHERE sm.program_family = :course
                     AND sm.institution_code = l.institution_code
               ) AS has_seat_matrix
        FROM legacy l
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()

    drawer_meta = {}
    legacy_meta = {}
    seat_meta = {}
    for row in rows:
        code = str(row[0])
        legacy_rows = row[1] or []
        seat_meta[code] = bool(row[2])

        if legacy_rows:
            history = [
                {
                    "year": int(item["year"]),
                    "percentile": float(item["low"]),
                    "low": float(item["low"]),
                    "high": float(item["high"]),
                    "rank": int(item["rank"]) if item["rank"] is not None else 0,
                }
                for item in legacy_rows
            ]
            item = {
                "history": history,
                "graph_history": [
                    {"year": h["year"], "low": h["low"], "high": h["high"]}
                    for h in history
                ],
            }
            best = min(history, key=lambda h: h["percentile"])
            item["percentile"] = best["percentile"]
            item["cutoff"] = best["rank"]
            legacy_meta[code] = item

    # Merge into the per-course cache so later pages/filters (different
    # institution codes) are served correctly instead of from a snapshot that
    # only contained the first request's colleges.
    cached_legacy.update(legacy_meta)
    cached_seat.update(seat_meta)
    queried.update(to_query)
    _SEARCH_METADATA_CACHE[course] = (cache_at, cached_legacy, cached_seat, queried)
    return (
        drawer_meta,
        {code: cached_legacy[code] for code in institution_codes if code in cached_legacy},
        {code: cached_seat.get(code, False) for code in institution_codes},
    )

@router.get("/colleges/{institution_code}/trend-options")
def college_trend_options(
    request: Request,
    institution_code: str,
    course: str = Query(...),
):
    """Return the available year, category and quota filters for one college.

    Connections: The college-details frontend calls this endpoint; it reads the precomputed cutoff_filter_options table in PostgreSQL.
    """

    check_rate_limit(request)
    engine = get_active_engine()
    _require_public_course(course, engine)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT is_ladies, year, base_category, section_code
            FROM cutoff_filter_options
            WHERE program_family = :course AND institution_code = :institution
            ORDER BY is_ladies, year, base_category, section_code
        """), {"course": course, "institution": institution_code}).fetchall()
    options = {"0": {"years": set(), "categories": {}}, "1": {"years": set(), "categories": {}}}
    for row in rows:
        key = "1" if bool(row[0]) else "0"
        options[key]["years"].add(int(row[1]))
        options[key]["categories"].setdefault(str(row[2]), set()).add(str(row[3]))
    for value in options.values():
        value["years"] = sorted(value["years"])
        value["categories"] = [
            {"value": cat, "quotas": sorted(quotas)}
            for cat, quotas in sorted(value["categories"].items())
        ]
    return {"institution_code": institution_code, "course": course, "options": options}

@router.get("/colleges/{institution_code}/trend")
def college_trend(
    request: Request,
    institution_code: str,
    course: str = Query(...),
    category: Optional[str] = Query(None),
    quota: Optional[str] = Query(None),
    ladies: bool = Query(False),
):
    """Return historical trend points for one college and selected filters.

    Connections: The frontend supplies the college, course and optional category/quota filters; PostgreSQL provides the precomputed cutoff_trend_points.
    """

    check_rate_limit(request)
    engine = get_active_engine()
    _require_public_course(course, engine)
    if not _db_available(engine):
        raise HTTPException(status_code=503, detail="Public PostgreSQL data service is unavailable.")
    sql = """
        SELECT program_id, base_category, is_ladies, section_code,
               year, round, closing_percentile, closing_rank
        FROM cutoff_trend_points
        WHERE program_family = :course
          AND institution_code = :institution
          AND is_ladies = :ladies
    """
    params = {
        "course": course,
        "institution": institution_code,
        "ladies": ladies,
    }
    if category:
        sql += " AND base_category = :category"
        params["category"] = category
    if quota:
        sql += " AND section_code = :quota"
        params["quota"] = quota
    sql += " ORDER BY program_id, base_category, section_code, year, round"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    groups = {}
    for row in rows:
        key = (int(row[0]), str(row[1]), str(row[3]))
        group = groups.setdefault(key, {
            "branch": int(row[0]),
            "college": institution_code,
            "category": str(row[1]),
            "ladies": bool(row[2]),
            "section": str(row[3]),
            "points": [],
        })
        group["points"].append({
            "year": int(row[4]),
            "round": int(row[5]),
            "percentile": round(float(row[6]), 7),
            "rank": int(row[7]) if row[7] is not None else None,
        })
    return {"course": course, "college": institution_code, "groups": list(groups.values())}

@router.get("/colleges/{institution_code}/seats")
def get_college_seats(
    request: Request,
    institution_code: str,
    course: str = Query(..., description="Course family (e.g. MBA)"),
):
    """Return the latest source-ordered seat rows and their official course/PDF metadata for one college.

    Connections: The college details UI calls this endpoint; PostgreSQL is the source, with a legacy runtime-table fallback for older imports.
    """

    check_rate_limit(request)
    engine = get_active_engine()
    _require_public_course(course, engine)
    with engine.connect() as conn:
        latest = conn.execute(text("""
            SELECT MAX(capture_year)
            FROM seats
            WHERE institution_code = :institution AND program_family = :course
        """), {"institution": institution_code, "course": course}).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="No seat matrix on file for this college.")
        capture_year = int(latest)
        source_rows = conn.execute(text("""
            SELECT id, choice_code, allocation_lane, raw_category, raw_gender, seats
            FROM seats
            WHERE institution_code = :institution
              AND program_family = :course
              AND capture_year = :year
            ORDER BY source_page NULLS LAST, source_row NULLS LAST, id
        """), {"institution": institution_code, "course": course, "year": capture_year}).fetchall()
        metadata_rows = conn.execute(text("""
            SELECT choice_code, course_metadata, source_pdf, source_page
            FROM seat_matrix_courses
            WHERE institution_code = :institution
              AND program_family = :course
              AND capture_year = :year
            ORDER BY source_page NULLS LAST, choice_code
        """), {"institution": institution_code, "course": course, "year": capture_year}).fetchall()

    if not source_rows:
        raise HTTPException(status_code=404, detail="No seat matrix on file for this college.")

    # Prefer source-order rows from the official PDF-backed records. The
    # aggregated runtime cache remains a fallback for legacy imports that do
    # not yet contain the complete course metadata payload.
    course_metadata = {}
    for row in metadata_rows:
        value = row[1]
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except (TypeError, ValueError):
                value = {}
        item = value if isinstance(value, dict) else {}
        item["source_pdf"] = str(row[2] or "")
        item["source_page"] = int(row[3]) if row[3] is not None else None
        course_metadata[str(row[0])] = item

    data = {}
    for row in source_rows:
        choice, allocation = str(row[1]), str(row[2])
        category, gender, seats = str(row[3]), str(row[4] or ""), int(row[5])
        allocation_rows = data.setdefault(choice, {}).setdefault(allocation, [])
        category_row = next((item for item in allocation_rows if item["category"] == category), None)
        if category_row is None:
            category_row = {"category": category, "G": None, "L": None, "total": None}
            allocation_rows.append(category_row)
        if gender == "G":
            category_row["G"] = seats
        elif gender == "L":
            category_row["L"] = seats
        else:
            category_row["total"] = seats

    if not course_metadata:
        # Compatibility for previously imported seat data. This path cannot
        # reproduce the original summary fields; it is intentionally used only
        # until that source is re-imported with course_metadata.
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT capture_year, choice_code, allocation_lane, base_category,
                       gender_g, gender_l, category_total, is_total
                FROM seat_matrix_runtime
                WHERE institution_code = :institution
                  AND program_family = :course
                ORDER BY choice_code, allocation_lane, base_category
            """), {"institution": institution_code, "course": course}).fetchall()
        legacy_data = {}
        for row in rows:
            choice, allocation = str(row[1]), str(row[2])
            legacy_data.setdefault(choice, {}).setdefault(allocation, []).append({
                "category": str(row[3]),
                "G": int(row[4]) if row[4] is not None else None,
                "L": int(row[5]) if row[5] is not None else None,
                "total": int(row[6]) if row[6] is not None else None,
            })
        if legacy_data:
            data = legacy_data

    return {
        "institution_code": institution_code,
        "course": course,
        "capture_year": capture_year,
        "data": data,
        "course_metadata": course_metadata,
        "source_order_preserved": bool(course_metadata),
    }

@router.get("/search", response_model=SearchResponse)
def search_colleges(
    request: Request,
    course: str = Query(..., description="Program family, e.g. MBA, MCA, BBA, BCA"),
    percentile: float = Query(
        ..., ge=0.0, le=100.0, description="Candidate CET percentile between 0 and 100"
    ),
    city: Optional[str] = Query(None, description="Optional city filter (case-insensitive)"),
    sort: str = Query("comp", pattern="^(comp|alpha|city|rank)$", description="Sort criteria"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=50, description="Items per page (max 50)"),
):
    """Validate and cache a bounded candidate search request.

    Connections: The frontend sends course, percentile, optional city and page settings; the uncached helper queries PostgreSQL and returns one page of CollegeCard results.
    """

    check_rate_limit(request)
    key = ("search", course, percentile, (city or "").strip().lower(), sort, page, page_size)
    return _PUBLIC_CACHE.get_or_set(
        key, _SEARCH_TTL,
        lambda: _search_colleges_uncached(course, percentile, city, sort, page, page_size),
    )


def _search_colleges_uncached(course, percentile, city, sort, page, page_size) -> SearchResponse:
    """Run the database-backed candidate search when no valid cached response exists.

    Connections: Uses search_college_summary_page() for SQL aggregation/pagination, then _search_metadata() to enrich only the returned institution codes.

    """

    try:
        engine = get_active_engine()
    except Exception:
        raise HTTPException(status_code=503, detail="Public PostgreSQL data service is unavailable.")
    valid_courses = available_public_courses(engine)
    if course not in valid_courses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid course '{course}'. Must be one of: {valid_courses}",
        )

    # Aggregate, sort and paginate in PostgreSQL; only one page reaches pandas.
    search_started = time.perf_counter()
    paged_df, total_count = search_college_summary_page(
        engine,
        percentage=percentile,
        program_family=course,
        city=city,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    search_query_ms = (time.perf_counter() - search_started) * 1000

    if paged_df.empty:
        return SearchResponse(total=total_count, page=page, page_size=page_size, results=[])

    # 4. Page metadata is already bounded to the requested page.

    results = []
    paged_codes = [str(v) for v in paged_df["institution_code"].tolist()]
    metadata_started = time.perf_counter()
    drawer_meta, legacy_meta, seat_meta = _search_metadata(engine, course, paged_codes)
    metadata_ms = (time.perf_counter() - metadata_started) * 1000
    if os.getenv("CET_PERF_DEBUG") == "1":
        print(f"PERF search_api query_path={search_query_ms:.1f}ms metadata={metadata_ms:.1f}ms page_rows={len(paged_df)}", flush=True)
    for _, row in paged_df.iterrows():
        # Status calculation: safe if candidate percentage >= highest cutoff
        cutoff_val = float(row["highest_cutoff"])
        if percentile >= cutoff_val + 2.0:
            status_label = "safe"
        elif percentile >= cutoff_val:
            status_label = "borderline"
        else:
            status_label = "reach"

        results.append(
            CollegeCard(
                id=f"{row['institution_code']}_{course}",
                institution_code=str(row["institution_code"]),
                name=str(row["institution_name"]),
                city=str(row["city"]) if pd.notna(row["city"]) else None,
                website=str(row["website"]) if pd.notna(row["website"]) else None,
                course=course,
                cutoff=int(legacy_meta.get(str(row["institution_code"]), {}).get("cutoff", 0)),
                percentile=round(float(legacy_meta.get(str(row["institution_code"]), {}).get("percentile", cutoff_val)), 2),
                highest_cutoff=round(cutoff_val, 2),
                status=status_label,
                years_on_record=int(row["years_on_record"]),
                history=legacy_meta.get(str(row["institution_code"]), {}).get("history", []),
                graph_history=legacy_meta.get(str(row["institution_code"]), {}).get("graph_history", []),
                has_cutoff=bool(legacy_meta.get(str(row["institution_code"]), {}).get("history")),
                has_trend=bool(legacy_meta.get(str(row["institution_code"]), {}).get("history")),
                has_seat_matrix=seat_meta.get(str(row["institution_code"]), False),
                has_website=bool(pd.notna(row["website"]) and str(row["website"]).strip()),
                drawer=drawer_meta.get(str(row["institution_code"])),
            )
        )

    return SearchResponse(
        total=total_count,
        page=page,
        page_size=page_size,
        results=results,
    )


@router.get("/colleges/{institution_code}/details")
def get_college_details(
    request: Request,
    institution_code: str,
    course: str = Query(..., description="Course family (e.g. MBA)"),
):
    """Return cutoff history and category/quota breakdowns for one institution and course.

    Connections: The college drawer calls this endpoint; it queries PostgreSQL rows scoped to the requested institution rather than sending the full dataset.
    """

    check_rate_limit(request)
    engine = get_active_engine()
    if not _db_available(engine):
        raise HTTPException(status_code=503, detail="Public PostgreSQL data service is unavailable.")

    query = text("""
        SELECT
            c.year,
            c.round,
            c.base_category,
            c.is_ladies,
            c.section_code,
            c.stage_code,
            c.percentile,
            c.rank_number,
            c.raw_category,
            p.program_name_raw
        FROM cutoffs c
        JOIN programs p ON p.program_id = c.program_id
        WHERE c.institution_code = :inst_code
          AND p.program_family = :course
          AND NOT (c.rank_number = 0 AND c.percentile = 0.0)
        ORDER BY c.year DESC, c.round ASC, c.percentile DESC
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query, {"inst_code": institution_code, "course": course}
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404, detail="No cutoff history found for this college and course."
        )

    # Structure into compact response
    history_by_year = defaultdict(list)
    categories = set()
    quotas = set()
    years = set()

    for r in rows:
        year = r[0]
        round_no = r[1]
        cat = r[2]
        is_ladies = bool(r[3])
        sec = r[4]
        stage = r[5]
        pct = float(r[6])
        rank = r[7]
        raw_cat = r[8]
        branch = r[9]

        years.add(year)
        categories.add(cat)
        quotas.add(sec)

        history_by_year[year].append(
            {
                "round": round_no,
                "category": cat,
                "raw_category": raw_cat,
                "is_ladies": is_ladies,
                "section": sec,
                "stage": stage,
                "percentile": pct,
                "rank": rank,
                "branch": branch,
            }
        )

    return {
        "institution_code": institution_code,
        "course": course,
        "years": sorted(list(years), reverse=True),
        "categories": sorted(list(categories)),
        "quotas": sorted(list(quotas)),
        "history": history_by_year,
    }

@router.get("/colleges/{institution_code}/year/{year}")
def get_college_year_runtime(request: Request, institution_code: str, year: int, course: str = Query(...)):
    """Return cutoff rows for one college, course and selected year.

    Connections: The college drawer calls this endpoint after a year is selected; the query is restricted to that institution and year in PostgreSQL.
    """

    check_rate_limit(request)
    engine = get_active_engine()
    if _db_available(engine):
        q = text("""
            SELECT c.program_id, c.institution_code, c.base_category, c.raw_category,
                   c.is_ladies, c.section_code, c.stage_code, c.year, c.round,
                   c.percentile, c.rank_number, p.program_name_raw, c.program_code
            FROM cutoffs c
            JOIN programs p ON p.program_id = c.program_id
            WHERE c.institution_code = :inst
              AND p.program_family = :course
              AND c.year = :year
              AND NOT (c.rank_number = 0 AND c.percentile = 0.0)
            ORDER BY c.program_id, c.round, c.section_code, c.raw_category
        """)
        with engine.connect() as conn:
            rows = conn.execute(q, {"inst": institution_code, "course": course, "year": year}).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail='Cutoff data not found.')
        branches={}
        categories={}
        sections={}
        pdf_rows=[]
        for r in rows:
            program_id=str(r[0])
            program_code=str(r[12] or '').strip()
            branch_key=program_code or program_id
            branch=str(r[11] or program_id)
            branches[branch_key]=branch
            cat=str(r[2] or r[3] or '')
            raw_cat=str(r[3] or r[2] or cat)
            categories[cat]={'full':cat,'group':'Other'}
            sec=str(r[5] or '')
            sections[sec]=sec
            pdf_rows.append({
                'branch':branch_key,'college':institution_code,'category':cat,
                'raw_category':raw_cat,'ladies':bool(r[4]),'section':sec,
                'stage':str(r[6] or f'Round {r[8]}'),'year':int(r[7]),
                'round':int(r[8]),'percentile':float(r[9]),'rank':r[10],
                'program_code':str(r[12] or ''),
            })
        return {'course':course,'year':year,'college':institution_code,
                'branches':branches,'categories':categories,'sections':sections,
                'pdf_rows':pdf_rows}
    raise HTTPException(status_code=404, detail='Cutoff data not found.')
