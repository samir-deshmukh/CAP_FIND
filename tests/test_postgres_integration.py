"""PostgreSQL end-to-end contract tests.

Run with TEST_DATABASE_URL pointing at an isolated PostgreSQL database.
These tests intentionally never create or use a file database.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required",
)
ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def db():
    from src.cet_cap.db import get_engine
    return get_engine(os.environ["TEST_DATABASE_URL"])


def test_schema_seed_cutoff_ingest_is_idempotent():
    from scripts.db_bootstrap import bootstrap_schema

    engine = db()
    bootstrap_schema(engine)
    run(
        "scripts/seed_reference_tables.py",
        "--db-url", os.environ["TEST_DATABASE_URL"],
        "--raw-dir", "data/raw",
        "--ref-dir", "data/reference",
    )
    first = run(
        "scripts/ingest.py", "data/raw",
        "--db-url", os.environ["TEST_DATABASE_URL"],
        "--ref-dir", "data/reference",
    )
    assert "failed=0" in first.stdout
    with engine.connect() as conn:
        first_count = conn.execute(text("SELECT count(*) FROM cutoffs")).scalar_one()
    assert first_count > 0

    second = run(
        "scripts/ingest.py", "data/raw",
        "--db-url", os.environ["TEST_DATABASE_URL"],
        "--ref-dir", "data/reference",
    )
    assert "failed=0" in second.stdout and "duplicate=" in second.stdout
    with engine.connect() as conn:
        second_count = conn.execute(text("SELECT count(*) FROM cutoffs")).scalar_one()
    assert second_count == first_count


def test_seat_ingest_populates_authoritative_postgres_table():
    from scripts.db_bootstrap import bootstrap_schema

    engine = db()
    bootstrap_schema(engine)
    run("scripts/seed_reference_tables.py", "--db-url", os.environ["TEST_DATABASE_URL"])
    run(
        "scripts/ingest_seats.py", "data/raw/seats",
        "--year", "2026",
        "--db-url", os.environ["TEST_DATABASE_URL"],
    )
    with engine.connect() as conn:
        seat_rows = conn.execute(text("SELECT count(*) FROM seats")).scalar_one()
    assert seat_rows > 0


def test_institute_enrichment_updates_postgres_records():
    from scripts.db_bootstrap import bootstrap_schema

    engine = db()
    bootstrap_schema(engine)
    run("scripts/seed_reference_tables.py", "--db-url", os.environ["TEST_DATABASE_URL"])
    run(
        "scripts/ingest.py", "data/raw",
        "--db-url", os.environ["TEST_DATABASE_URL"],
    )
    run(
        "scripts/enrich_institutes.py", "data/reference/institute_contacts.csv",
        "--db-url", os.environ["TEST_DATABASE_URL"],
    )
    with engine.connect() as conn:
        enriched = conn.execute(text(
            "SELECT count(*) FROM institutes "
            "WHERE website IS NOT NULL AND btrim(website) <> ''"
        )).scalar_one()
    assert enriched > 0


def test_public_search_returns_matching_college_from_postgres(monkeypatch):
    """Exercise the public search handler and SQL against an isolated PostgreSQL fixture."""
    import uuid
    from starlette.requests import Request
    import backend.api as api
    from scripts.db_bootstrap import bootstrap_schema

    engine = db()
    bootstrap_schema(engine)
    suffix = uuid.uuid4().hex[:10].upper()
    family = f"E2E{suffix}"
    code = f"E{suffix}"
    name = f"Search Fixture College {suffix}"
    program_id = None
    api._request_history.clear()
    api._PUBLIC_CACHE.clear()
    api._SEARCH_METADATA_CACHE.clear()
    monkeypatch.setattr(api, "get_active_engine", lambda: engine)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO institutes(institution_code,institution_name,city) VALUES (:code,:name,'Amravati')"), {"code": code, "name": name})
            program_id = conn.execute(text("INSERT INTO programs(program_family,program_name_raw) VALUES (:family,:name) RETURNING program_id"), {"family": family, "name": family}).scalar_one()
            conn.execute(text("INSERT INTO base_categories(base_code) VALUES (:category) ON CONFLICT DO NOTHING"), {"category": f"T{suffix}"})
            conn.execute(text("INSERT INTO sections(section_code,section_full) VALUES (:section,'Fixture') ON CONFLICT DO NOTHING"), {"section": f"S{suffix}"})
            conn.execute(text("INSERT INTO stages(stage_code) VALUES (:stage) ON CONFLICT DO NOTHING"), {"stage": f"ST{suffix}"})
            conn.execute(text("""INSERT INTO cutoffs(year,round,institution_code,program_id,base_category,is_ladies,section_code,stage_code,rank_number,percentile,raw_category,raw_program_name,source_pdf)
                VALUES (2025,1,:code,:program_id,:category,FALSE,:section,:stage,1234,75.5,:raw_category,:family,'fixture.pdf')"""), {
                "code": code, "program_id": program_id, "category": f"T{suffix}",
                "section": f"S{suffix}", "stage": f"ST{suffix}",
                "raw_category": f"G{suffix}", "family": family,
            })
            conn.execute(text("""INSERT INTO cutoff_college_year_summary(program_family,institution_code,year,low_percentile,high_percentile,low_rank)
                VALUES (:family,:code,2025,75.5,75.5,1234)"""), {"family": family, "code": code})

        request = Request({"type": "http", "method": "GET", "path": "/api/search",
                           "query_string": b"", "headers": [],
                           "client": ("127.0.0.1", 12345), "scheme": "http"})
        result = api.search_colleges(request, course=family, percentile=80.0,
                                     city="Amravati", sort="comp", page=1, page_size=50)

        assert result.total == 1
        assert len(result.results) == 1
        card = result.results[0]
        assert card.institution_code == code
        assert card.name == name
        assert card.city == "Amravati"
        assert card.highest_cutoff == 75.5
        assert card.history == [{"year": 2025, "percentile": 75.5, "low": 75.5, "high": 75.5, "rank": 1234}]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cutoff_college_year_summary WHERE institution_code=:code"), {"code": code})
            conn.execute(text("DELETE FROM cutoffs WHERE institution_code=:code"), {"code": code})
            if program_id is not None:
                conn.execute(text("DELETE FROM programs WHERE program_id=:program_id"), {"program_id": program_id})
            conn.execute(text("DELETE FROM institutes WHERE institution_code=:code"), {"code": code})
            conn.execute(text("DELETE FROM base_categories WHERE base_code=:category"), {"category": f"T{suffix}"})
            conn.execute(text("DELETE FROM sections WHERE section_code=:section"), {"section": f"S{suffix}"})
            conn.execute(text("DELETE FROM stages WHERE stage_code=:stage"), {"stage": f"ST{suffix}"})
        api.invalidate_public_caches()


def test_engineering_coverage_does_not_compare_cutoffs_to_another_years_seat_matrix():
    """Historical cutoffs without same-year seats are not false code mismatches."""
    import uuid
    from scripts.db_bootstrap import bootstrap_schema
    from scripts.refresh_derived_data import _engineering_cutoff_seat_coverage

    engine = db()
    bootstrap_schema(engine)
    suffix = uuid.uuid4().hex[:10].upper()
    institution = f"T{suffix}"
    category = f"C{suffix}"
    section = f"S{suffix}"
    stage = f"G{suffix}"
    lane = f"L{suffix}"
    program_name = f"Engineering coverage fixture {suffix}"
    historic_code = f"H{suffix}"
    missing_code = f"M{suffix}"
    matched_code = f"X{suffix}"
    program_id = None

    try:
        with engine.begin() as conn:
            before = _engineering_cutoff_seat_coverage(conn)
            conn.execute(text("INSERT INTO institutes(institution_code,institution_name) VALUES (:code,:name)"),
                         {"code": institution, "name": f"Coverage Fixture {suffix}"})
            program_id = conn.execute(
                text("INSERT INTO programs(program_family,program_name_raw) VALUES ('BE',:name) RETURNING program_id"),
                {"name": program_name},
            ).scalar_one()
            conn.execute(text("INSERT INTO base_categories(base_code) VALUES (:code)"), {"code": category})
            conn.execute(text("INSERT INTO sections(section_code,section_full) VALUES (:code,'Fixture')"), {"code": section})
            conn.execute(text("INSERT INTO stages(stage_code) VALUES (:code)"), {"code": stage})
            conn.execute(text("INSERT INTO allocation_lanes(lane_code,lane_full) VALUES (:code,'Fixture')"), {"code": lane})

            for year, code, rank in ((2025, historic_code, 101), (2026, missing_code, 102), (2026, matched_code, 103)):
                conn.execute(text("""
                    INSERT INTO cutoffs(
                        year,round,institution_code,program_id,program_code,base_category,
                        is_ladies,section_code,stage_code,rank_number,percentile,raw_category,
                        raw_program_name,source_pdf
                    ) VALUES (:year,1,:institution,:program_id,:code,:category,FALSE,
                             :section,:stage,:rank,75.0,'OPEN',:program_name,'fixture.pdf')
                """), {
                    "year": year, "institution": institution, "program_id": program_id,
                    "code": code, "category": category, "section": section,
                    "stage": stage, "rank": rank, "program_name": program_name,
                })

            conn.execute(text("""
                INSERT INTO seats(
                    capture_year,program_family,institution_code,choice_code,allocation_lane,
                    base_category,is_total,is_ladies,seats,raw_category,raw_allocation_type,
                    raw_gender,source_pdf
                ) VALUES (2026,'BE',:institution,:code,:lane,:category,FALSE,FALSE,10,
                         'OPEN','Fixture','G','fixture.pdf')
            """), {"institution": institution, "code": matched_code, "lane": lane, "category": category})

            after = _engineering_cutoff_seat_coverage(conn)
            assert after["unmatched_same_year"] - before["unmatched_same_year"] == 1
            assert after["no_same_year_matrix"] - before["no_same_year_matrix"] == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM seats WHERE institution_code=:institution"), {"institution": institution})
            conn.execute(text("DELETE FROM cutoffs WHERE institution_code=:institution"), {"institution": institution})
            if program_id is not None:
                conn.execute(text("DELETE FROM programs WHERE program_id=:program_id"), {"program_id": program_id})
            conn.execute(text("DELETE FROM institutes WHERE institution_code=:institution"), {"institution": institution})
            conn.execute(text("DELETE FROM base_categories WHERE base_code=:code"), {"code": category})
            conn.execute(text("DELETE FROM sections WHERE section_code=:code"), {"code": section})
            conn.execute(text("DELETE FROM stages WHERE stage_code=:code"), {"code": stage})
            conn.execute(text("DELETE FROM allocation_lanes WHERE lane_code=:code"), {"code": lane})
