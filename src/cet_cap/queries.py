"""PostgreSQL query functions used by the FastAPI public API. Query definitions stay separate from connection management so their behavior can be tested independently."""

from __future__ import annotations

import os
import time
import pandas as pd
from sqlalchemy import Engine, text

ZERO_CUTOFF_ARTIFACT_FILTER = 'NOT (c.rank_number = 0 AND c.percentile = 0.0)'


def available_years(engine: Engine) -> list[int]:
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT DISTINCT year FROM cutoffs ORDER BY year DESC'))
        return [r[0] for r in rows]


def available_program_families(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT DISTINCT program_family FROM programs ORDER BY program_family'))
        return [r[0] for r in rows]


def available_categories(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT base_code FROM base_categories ORDER BY base_code'))
        return [r[0] for r in rows]


def search_cutoffs_for_course(
    engine: Engine,
    percentage: float,
    program_family: str,
) -> pd.DataFrame:
    """Legacy full-result query retained for internal compatibility. New public
    searches should use the bounded summary-page query below. Deliberately NOT filtered by
    category or city — every category/year/round/section/stage row for
    this program family that the candidate's percentage clears, for
    every institute, regardless of location. src/cet_cap/search.py then
    does city filtering and per-college summarization on this in pandas,
    for the older full-result search path.
    """
    query = text(f'''
        SELECT
            i.institution_code,
            i.institution_name,
            i.city,
            i.website,
            i.home_university,
            p.program_name_raw AS program_name,
            c.year,
            c.round,
            c.base_category,
            c.is_ladies,
            c.section_code,
            c.stage_code,
            c.percentile AS cutoff_percentile,
            c.rank_number AS cutoff_rank
        FROM cutoffs c
        JOIN institutes i ON i.institution_code = c.institution_code
        JOIN programs p ON p.program_id = c.program_id
        WHERE c.percentile <= :percentage AND p.program_family = :program_family
              AND {ZERO_CUTOFF_ARTIFACT_FILTER}
    ''')
    with engine.connect() as conn:
        return pd.read_sql_query(
            query, conn, params={'percentage': percentage, 'program_family': program_family})


def search_college_summary(
    engine: Engine,
    percentage: float,
    program_family: str,
    city: str | None = None,
) -> pd.DataFrame:
    """Return one aggregated row per eligible college directly from PostgreSQL.

    City filtering and aggregation happen in SQL so the API never loads the
    full cutoff dataset into pandas for a normal public search.
    """
    city_clause = ""
    params = {"percentage": percentage, "program_family": program_family}
    if city and city.strip():
        city_clause = " AND i.city ILIKE :city"
        params["city"] = f"%{city.strip()}%"

    query = text(f"""
        SELECT c.institution_code,
               MAX(i.institution_name) AS institution_name,
               MAX(i.city) AS city,
               MAX(i.website) AS website,
               MAX(c.percentile) AS highest_cutoff,
               COUNT(DISTINCT c.year) AS years_on_record,
               COUNT(*) AS matching_rows,
               (array_agg(c.rank_number ORDER BY c.percentile ASC NULLS LAST,
                          c.rank_number ASC NULLS LAST))[1] AS lowest_rank
        FROM cutoffs c
        JOIN institutes i ON i.institution_code = c.institution_code
        JOIN programs p ON p.program_id = c.program_id
        WHERE c.percentile <= :percentage
          AND p.program_family = :program_family
          AND {ZERO_CUTOFF_ARTIFACT_FILTER}
          {city_clause}
        GROUP BY c.institution_code
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def search_college_summary_page(
    engine: Engine,
    percentage: float,
    program_family: str,
    city: str | None = None,
    sort: str = "comp",
    page: int = 1,
    page_size: int = 25,
) -> tuple[pd.DataFrame, int]:
    """Aggregate, sort, count and paginate in PostgreSQL.

    Only the requested page reaches pandas, keeping public search CPU and
    memory bounded as the cutoff dataset grows.
    """
    city_clause = ""
    params = {"percentage": percentage, "program_family": program_family,
              "limit": page_size, "offset": (page - 1) * page_size}
    if city and city.strip():
        city_clause = " AND i.city ILIKE :city"
        params["city"] = f"%{city.strip()}%"
    order = {
        "alpha": "institution_name ASC, institution_code ASC",
        "city": "city ASC NULLS LAST, highest_cutoff DESC, institution_code ASC",
        "rank": "lowest_rank ASC NULLS LAST, institution_name ASC, institution_code ASC",
        "comp": "highest_cutoff DESC, institution_name ASC, institution_code ASC",
    }.get(sort, "highest_cutoff DESC, institution_name ASC, institution_code ASC")
    query = text(f"""
        WITH eligible AS (
            SELECT c.institution_code,
                   c.percentile,
                   c.rank_number
            FROM cutoffs c
            JOIN programs p ON p.program_id = c.program_id
            WHERE c.percentile <= :percentage
              AND p.program_family = :program_family
              AND {ZERO_CUTOFF_ARTIFACT_FILTER}
        ),
        summary AS (
            SELECT e.institution_code,
                   MAX(e.percentile) AS highest_cutoff,
                   (array_agg(e.rank_number ORDER BY e.percentile ASC NULLS LAST,
                              e.rank_number ASC NULLS LAST))[1] AS lowest_rank
            FROM eligible e
            GROUP BY e.institution_code
        ),
        years AS (
            SELECT institution_code,
                   COUNT(*) FILTER (WHERE low_percentile <= :percentage) AS years_on_record
            FROM cutoff_college_year_summary
            WHERE program_family = :program_family
            GROUP BY institution_code
        ),
        final_summary AS (
            SELECT s.institution_code,
                   i.institution_name,
                   i.city,
                   CASE
                       WHEN UPPER(COALESCE(r.status, '')) = 'VERIFIED'
                            AND NULLIF(BTRIM(r.website), '') IS NOT NULL
                       THEN r.website
                       ELSE NULL
                   END AS website,
                   s.highest_cutoff,
                   COALESCE(y.years_on_record, 0) AS years_on_record,
                   s.lowest_rank
            FROM summary s
            JOIN institutes i ON i.institution_code = s.institution_code
            LEFT JOIN college_website_resolver r ON r.institution_code = i.institution_code
            LEFT JOIN years y ON y.institution_code = s.institution_code
            WHERE 1=1
              {city_clause}
        )
        SELECT *, COUNT(*) OVER () AS total_count
        FROM final_summary
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """)
    t0 = time.perf_counter()
    with engine.connect() as conn:
        t_connect = time.perf_counter() - t0
        t1 = time.perf_counter()
        df = pd.read_sql_query(query, conn, params=params)
        t_query = time.perf_counter() - t1
    if os.getenv("CET_PERF_DEBUG") == "1":
        print(f"PERF search_college_summary_page connect={t_connect*1000:.1f}ms query_fetch={t_query*1000:.1f}ms rows={len(df)}", flush=True)
    if not df.empty:
        total = int(df["total_count"].iloc[0])
        df = df.drop(columns=["total_count"])
        return df, total

    # An out-of-range page has no rows, so COUNT(*) OVER() cannot report
    # the total. Run the bounded aggregate again only in this edge case.
    count_query = text(f"""
        SELECT COUNT(*)
        FROM (
            SELECT c.institution_code
            FROM cutoffs c
            JOIN institutes i ON i.institution_code = c.institution_code
            JOIN programs p ON p.program_id = c.program_id
            WHERE c.percentile <= :percentage
              AND p.program_family = :program_family
              AND {ZERO_CUTOFF_ARTIFACT_FILTER}
              {city_clause}
            GROUP BY c.institution_code
        ) AS summary_count
    """)
    with engine.connect() as conn:
        total = int(pd.read_sql_query(count_query, conn, params=params).iloc[0, 0])
    return df, total


def seat_matrix_for_institute(
    engine: Engine,
    institution_code: str,
    program_family: str,
) -> pd.DataFrame:
    """Seat matrix for the detail panel: one row per (allocation_lane,
    base_category, is_ladies) at the MOST RECENT capture_year on record
    for this institute/program combination — older years are dropped
    rather than summed, since summing seat counts across years would
    overstate current capacity.

    is_total rows are NOT excluded — they're returned with
    is_total=True so the UI can show the lane's actual sanctioned total
    as its own clearly-labeled row instead of either hiding it or
    silently adding it into the per-category rows (which would
    double-count capacity).
    """
    query = text('''
        SELECT allocation_lane, base_category, is_total, is_ladies, seats, capture_year
        FROM seats
        WHERE institution_code = :institution_code AND program_family = :program_family
              AND capture_year = (
                  SELECT MAX(capture_year) FROM seats
                  WHERE institution_code = :institution_code
                        AND program_family = :program_family
              )
        ORDER BY allocation_lane, is_total, base_category
    ''')
    with engine.connect() as conn:
        return pd.read_sql_query(
            query, conn,
            params={'institution_code': institution_code, 'program_family': program_family})
def find_eligible_colleges(
    engine: Engine,
    percentile: float,
    base_category: str,
    program_family: str,
    is_ladies: bool = False,
    year: int | None = None,
    round_no: int | None = None,
) -> pd.DataFrame:
    """Colleges/programs a candidate with the given percentile and
    category would qualify for, most competitive (highest cutoff) first.

    Filters to the exact (base_category, is_ladies) combination the
    candidate belongs to — this does NOT fall back to broader categories
    (e.g. a candidate in a reserved category is not shown OPEN-category
    cutoffs), since that's a distinct, more permissive eligibility rule
    a candidate would need to explicitly ask for, not a default.
    """
    where = [
        'c.percentile <= :percentile',
        'c.base_category = :base_category',
        'p.program_family = :program_family',
        'c.is_ladies = :is_ladies',
        ZERO_CUTOFF_ARTIFACT_FILTER,
    ]
    params: dict = {
        'percentile': percentile,
        'base_category': base_category,
        'program_family': program_family,
        'is_ladies': int(is_ladies),
    }

    if year is not None:
        where.append('c.year = :year')
        params['year'] = year
    if round_no is not None:
        where.append('c.round = :round_no')
        params['round_no'] = round_no

    query = text(f'''
        SELECT
            i.institution_name,
            i.institution_code,
            p.program_name_raw AS program_name,
            c.year,
            c.round,
            c.stage_code,
            c.section_code,
            c.percentile AS cutoff_percentile,
            c.rank_number AS cutoff_rank
        FROM cutoffs c
        JOIN institutes i ON i.institution_code = c.institution_code
        JOIN programs p ON p.program_id = c.program_id
        WHERE {' AND '.join(where)}
        ORDER BY c.percentile DESC, i.institution_name
    ''')
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)
