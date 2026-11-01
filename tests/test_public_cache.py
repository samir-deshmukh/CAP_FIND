"""Correctness tests for the public API TTL cache (options/stats/search)."""
import threading
import time

import pandas as pd
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

import backend.api as api


def req(ip="10.9.0.1"):
    return Request({"type": "http", "method": "GET", "path": "/api/search", "query_string": b"",
                    "headers": [], "client": (ip, 1), "scheme": "http"})


@pytest.fixture
def env(monkeypatch):
    """Fake DB layer that encodes its arguments into the result and counts calls."""
    calls = {"search": 0, "meta": 0}
    lock = threading.Lock()
    state = {"delay": 0.0}

    def fake_page(engine, percentage, program_family, city, sort, page, page_size):
        with lock:
            calls["search"] += 1
        time.sleep(state["delay"])
        marker = f"{program_family}|{percentage}|{city}|{sort}|{page}|{page_size}"
        df = pd.DataFrame([{"institution_code": marker, "institution_name": marker, "city": "Pune",
                            "website": None, "highest_cutoff": 50.0, "years_on_record": 1,
                            "lowest_rank": 1}])
        return df, 1

    def fake_meta(*a):
        with lock:
            calls["meta"] += 1
        return {}, {}, {}

    monkeypatch.setattr(api, "get_active_engine", lambda: object())
    monkeypatch.setattr(api, "available_public_courses", lambda e: ["BBA", "MCA"])
    monkeypatch.setattr(api, "search_college_summary_page", fake_page)
    monkeypatch.setattr(api, "_search_metadata", fake_meta)
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 10_000)
    api._request_history.clear()
    api.invalidate_public_caches()
    return calls, state


def search(course="BBA", percentile=80.0, city=None, sort="comp", page=1, page_size=25, ip="10.9.0.1"):
    return api.search_colleges(req(ip), course=course, percentile=percentile, city=city,
                               sort=sort, page=page, page_size=page_size)


def marker(res):
    return res.results[0].institution_code


def test_identical_search_hits_cache(env):
    calls, _ = env
    a, b = search(), search()
    assert marker(a) == marker(b)
    assert calls["search"] == 1


@pytest.mark.parametrize("change", [
    {"course": "MCA"}, {"percentile": 81.0}, {"city": "Nagpur"},
    {"sort": "alpha"}, {"page": 2}, {"page_size": 10},
])
def test_every_parameter_is_part_of_the_cache_key(env, change):
    calls, _ = env
    base = search(city="Pune")
    other = search(**{"city": "Pune", **change})
    assert marker(base) != marker(other)
    assert calls["search"] == 2
    # And each still returns its own result on repeat.
    assert marker(search(city="Pune")) == marker(base)
    assert marker(search(**{"city": "Pune", **change})) == marker(other)


def test_city_is_case_and_whitespace_insensitive_like_the_sql(env):
    calls, _ = env
    search(city="Pune")
    search(city="  pune ")
    assert calls["search"] == 1


def test_courses_do_not_contaminate_each_other(env):
    bba, mca = search(course="BBA"), search(course="MCA")
    assert marker(bba).startswith("BBA|") and marker(mca).startswith("MCA|")
    assert marker(search(course="BBA")).startswith("BBA|")


def test_expiry_recomputes(env, monkeypatch):
    calls, _ = env
    monkeypatch.setattr(api, "_SEARCH_TTL", 0.05)
    search()
    time.sleep(0.1)
    search()
    assert calls["search"] == 2


def test_errors_are_not_cached(env, monkeypatch):
    calls, _ = env
    boom = {"on": True}
    real = api.search_college_summary_page

    def flaky(*a, **k):
        if boom["on"]:
            raise HTTPException(status_code=503, detail="db down")
        return real(*a, **k)

    monkeypatch.setattr(api, "search_college_summary_page", flaky)
    with pytest.raises(HTTPException):
        search()
    boom["on"] = False
    assert marker(search()).startswith("BBA|")


def test_invalid_course_is_400_and_does_not_grow_locks(env):
    for i in range(50):
        with pytest.raises(HTTPException) as e:
            search(course=f"NOPE{i}")
        assert e.value.status_code == 400
    assert api._PUBLIC_CACHE._locks == {}
    assert len(api._PUBLIC_CACHE._data) == 0


def test_rate_limit_still_applies_to_cached_responses(env, monkeypatch):
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 2)
    api._request_history.clear()
    search(ip="10.9.9.9")
    search(ip="10.9.9.9")
    with pytest.raises(HTTPException) as e:
        search(ip="10.9.9.9")
    assert e.value.status_code == 429
    search(ip="10.9.9.8")  # another client is unaffected


def test_concurrent_identical_requests_collapse_to_one_db_query(env):
    calls, state = env
    state["delay"] = 0.3
    out, errs = [], []

    def worker():
        try:
            out.append(marker(search()))
        except Exception as exc:  # pragma: no cover
            errs.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errs and len(out) == 40 and len(set(out)) == 1
    assert calls["search"] == 1


def test_concurrent_different_requests_get_their_own_results(env):
    _, state = env
    state["delay"] = 0.05
    results = {}

    def worker(i):
        results[i] = marker(search(percentile=float(40 + i % 20), city=f"C{i % 7}", page=1 + i % 3))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(120)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    for i, m in results.items():
        assert m == f"BBA|{float(40 + i % 20)}|C{i % 7}|comp|{1 + i % 3}|25"


def test_invalidate_clears_search_options_stats_and_metadata(env):
    calls, _ = env
    search()
    api._SEARCH_METADATA_CACHE["BBA"] = (time.monotonic(), {}, {}, set())
    api.PUBLIC_COURSES = ["X"]
    api.invalidate_public_caches()
    assert api._SEARCH_METADATA_CACHE == {} and api.PUBLIC_COURSES is None
    search()
    assert calls["search"] == 2


def test_options_and_stats_cached_once_and_set_cache_header(monkeypatch):
    n = {"conn": 0}

    class Row(dict):
        def mappings(self):
            return self

        def one(self):
            return {"colleges": 1, "cutoff_records": 2, "cap_rounds": 3, "latest_year": 2026}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, q):
            n["conn"] += 1
            sql = str(q)
            return Row() if "COUNT" in sql else [("Pune",)]

    class Eng:
        def connect(self):
            return Conn()

    monkeypatch.setattr(api, "get_active_engine", lambda: Eng())
    monkeypatch.setattr(api, "available_public_courses", lambda e: ["BBA"])
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 10_000)
    api.invalidate_public_caches()
    r = Response()
    first = api.public_options(req(), r)
    second = api.public_options(req(), Response())
    assert first == second == {"cities": ["Pune"], "courses": ["BBA"]}
    assert r.headers["cache-control"] == "public, max-age=60"
    s1, s2 = api.public_stats(req(), Response()), api.public_stats(req(), Response())
    assert s1 == s2 and s1["colleges"] == 1
    assert n["conn"] == 2  # one DB hit for options + one for stats, not four
