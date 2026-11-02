"""Tests public API validation, rate limiting, cache behavior and response shaping without requiring a live database."""

from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

import backend.api as api


def request_for(ip="127.0.0.1"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": b"",
            "headers": [],
            "client": (ip, 12345),
            "scheme": "http",
        }
    )


def test_rate_limit_blocks_after_configured_threshold(monkeypatch):
    api._request_history.clear()
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 2)
    request = request_for("10.0.0.1")

    api.check_rate_limit(request)
    api.check_rate_limit(request)
    with pytest.raises(HTTPException) as exc:
        api.check_rate_limit(request)

    assert exc.value.status_code == 429
    api._request_history.clear()


def test_public_rate_limiter_bounds_high_cardinality_keys(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(api.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(api, "client_ip", lambda request: request.scope["client"][0])
    monkeypatch.setattr(api, "_request_history", {"first": [100.0], "second": [100.0]})
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_KEYS", 2)

    api.check_rate_limit(request_for("third"))

    assert len(api._request_history) <= 2
    assert "third" in api._request_history


def test_public_rate_limiter_expires_old_keys(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(api.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(api, "client_ip", lambda request: request.scope["client"][0])
    monkeypatch.setattr(api, "_request_history", {"old": [1.0]})
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_KEYS", 1)

    api.check_rate_limit(request_for("new"))

    assert api._request_history == {"new": [100.0]}


def test_db_available_reports_connection_failure():
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("connection failed")

    assert not api._db_available(BrokenEngine())


def test_public_options_uses_database_values(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            return [("Amravati",), ("Pune",)]

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(api, "get_active_engine", lambda: Engine())
    monkeypatch.setattr(api, "_db_available", lambda engine: True)
    monkeypatch.setattr(api, "available_public_courses", lambda engine: ["BBA"])
    api._request_history.clear()
    api._PUBLIC_CACHE.clear()

    result = api.public_options(request_for("10.0.0.2"), Response())

    assert result == {"cities": ["Amravati", "Pune"], "courses": ["BBA"]}


def test_search_colleges_builds_bounded_cards(monkeypatch):
    class Engine:
        pass

    raw = pd.DataFrame(
        [
            {
                "institution_code": "01102",
                "institution_name": "Example College",
                "city": "Amravati",
                "website": "https://example.edu",
                "cutoff_percentile": 80.0,
                "cutoff_rank": 1200,
                "year": 2026,
            },
            {
                "institution_code": "01102",
                "institution_name": "Example College",
                "city": "Amravati",
                "website": "https://example.edu",
                "cutoff_percentile": 75.0,
                "cutoff_rank": 1500,
                "year": 2025,
            },
        ]
    )
    monkeypatch.setattr(api, "get_active_engine", lambda: Engine())
    monkeypatch.setattr(api, "_db_available", lambda engine: True)
    monkeypatch.setattr(api, "available_public_courses", lambda engine: ["BBA"])
    api._PUBLIC_CACHE.clear()
    summary = pd.DataFrame([{
        "institution_code": "01102",
        "institution_name": "Example College",
        "city": "Amravati",
        "website": "https://example.edu",
        "highest_cutoff": 80.0,
        "years_on_record": 2,
        "matching_rows": 2,
        "lowest_rank": 1500,
    }])
    monkeypatch.setattr(api, "search_college_summary_page", lambda *args, **kwargs: (summary, 1))
    monkeypatch.setattr(api, "_search_metadata", lambda *args: ({}, {"01102": {"cutoff": 1200, "percentile": 75.0, "history": [], "graph_history": []}}, {"01102": False}))
    api._request_history.clear()

    result = api.search_colleges(
        request_for("10.0.0.3"),
        course="BBA",
        percentile=82.0,
        city=None,
        sort="comp",
        page=1,
        page_size=25,
    )

    assert result.total == 1
    assert result.results[0].institution_code == "01102"
    assert result.results[0].highest_cutoff == 80.0
    assert result.results[0].status == "safe"


def test_search_rejects_unknown_course(monkeypatch):
    class Engine:
        pass

    monkeypatch.setattr(api, "get_active_engine", lambda: Engine())
    monkeypatch.setattr(api, "_db_available", lambda engine: True)
    monkeypatch.setattr(api, "available_public_courses", lambda engine: ["BCA"])
    api._request_history.clear()
    api._PUBLIC_CACHE.clear()

    with pytest.raises(HTTPException) as exc:
        api.search_colleges(
            request_for("10.0.0.4"),
            course="NOT_REAL",
            percentile=80.0,
            city=None,
            sort="comp",
            page=1,
            page_size=25,
        )

    assert exc.value.status_code == 400


def test_search_metadata_is_compact_and_bounded():
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            assert params["course"] == "BCA"
            assert "code_0" in params and "code_1" in params

            class Result:
                def fetchall(self):
                    return [
                        (
                            "01102",
                            [
                                {"year": 2026, "low": 80.0, "high": 90.0, "rank": 1200},
                                {"year": 2025, "low": 75.0, "high": 88.0, "rank": 1500},
                            ],
                            True,
                        )
                    ]

            return Result()

    class Engine:
        def connect(self):
            return Connection()

    api._SEARCH_METADATA_CACHE.clear()
    drawer, legacy, seat = api._search_metadata(Engine(), "BCA", ["01102", "01103"])

    # Drawer filter options are loaded lazily by /trend-options.
    assert drawer == {}
    assert legacy["01102"]["cutoff"] == 1500
    assert legacy["01102"]["percentile"] == 75.0
    assert "01103" not in legacy
    assert seat == {"01102": True, "01103": False}


def test_ttl_cache_computes_once_and_does_not_cache_errors():
    cache = api._TTLCache()
    calls = []

    def factory():
        calls.append(1)
        return {"ok": True}

    assert cache.get_or_set("k", 60, factory) == {"ok": True}
    assert cache.get_or_set("k", 60, factory) == {"ok": True}
    assert len(calls) == 1

    def boom():
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        cache.get_or_set("bad", 60, boom)
    assert cache.get_or_set("bad", 60, lambda: 5) == 5


def test_ttl_cache_expires_entries():
    cache = api._TTLCache()
    calls = []
    cache.get_or_set("k", 0, lambda: calls.append(1) or 1)
    cache.get_or_set("k", 0, lambda: calls.append(1) or 1)
    assert len(calls) == 2


def test_search_metadata_cache_serves_every_college_not_just_the_first_page():
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            codes = [v for k, v in params.items() if k.startswith("code_")]

            class Result:
                def fetchall(self_inner):
                    return [
                        (c, [{"year": 2026, "low": 70.0, "high": 80.0, "rank": 100}], True)
                        for c in codes
                    ]

            return Result()

    class Engine:
        def connect(self):
            return Connection()

    api._SEARCH_METADATA_CACHE.clear()
    _, legacy1, seat1 = api._search_metadata(Engine(), "BCA", ["A1"])
    _, legacy2, seat2 = api._search_metadata(Engine(), "BCA", ["B2", "A1"])
    assert set(legacy1) == {"A1"}
    assert set(legacy2) == {"A1", "B2"}
    assert seat2 == {"B2": True, "A1": True}


def test_db_pool_defaults_are_bounded(monkeypatch):
    from src.cet_cap import db
    for key in ("CET_DB_POOL_SIZE", "CET_DB_MAX_OVERFLOW", "CET_DB_POOL_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)
    engine = db.get_engine("postgresql+psycopg2://user:pass@localhost/db")
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 5
    assert engine.pool._timeout == 5.0
    engine.dispose()


def test_db_pool_settings_are_configurable(monkeypatch):
    from src.cet_cap import db
    monkeypatch.setenv("CET_DB_POOL_SIZE", "2")
    monkeypatch.setenv("CET_DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("CET_DB_POOL_TIMEOUT", "7")
    engine = db.get_engine("postgresql+psycopg2://user:pass@localhost/db")
    assert engine.pool.size() == 2
    assert engine.pool._max_overflow == 3
    assert engine.pool._timeout == 7.0
    engine.dispose()


def test_seat_matrix_api_preserves_source_order_and_pdf_metadata(monkeypatch):
    class Result:
        def __init__(self, rows=None, scalar=None):
            self.rows = rows or []
            self.scalar = scalar

        def scalar_one_or_none(self):
            return self.scalar

        def fetchall(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            sql = str(query)
            if "SELECT MAX(capture_year)" in sql:
                return Result(scalar=2026)
            if "FROM seat_matrix_courses" in sql:
                return Result(rows=[(
                    "0100219110",
                    {"course_name": "Civil Engineering", "summary_fields": {"SI": 60}},
                    "2026_fe_seatmatrix_V1.pdf",
                    1,
                )])
            if "FROM seats" in sql:
                return Result(rows=[
                    (1, "0100219110", "State Level", "SC", "G", 6),
                    (2, "0100219110", "State Level", "OPEN", "G", 16),
                    (3, "0100219110", "PWD", "SC", "", 1),
                ])
            raise AssertionError(f"Unexpected SQL: {sql}")

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(api, "get_active_engine", lambda: Engine())
    monkeypatch.setattr(api, "_require_public_course", lambda course, engine: None)
    api._request_history.clear()

    result = api.get_college_seats(request_for("10.0.0.10"), "01002", "BE")

    assert result["source_order_preserved"] is True
    assert result["course_metadata"]["0100219110"]["summary_fields"] == {"SI": 60}
    assert result["course_metadata"]["0100219110"]["source_pdf"] == "2026_fe_seatmatrix_V1.pdf"
    assert [r["category"] for r in result["data"]["0100219110"]["State Level"]] == ["SC", "OPEN"]
    assert result["data"]["0100219110"]["State Level"][0]["G"] == 6
    assert result["data"]["0100219110"]["PWD"][0]["total"] == 1
