"""Tests for the admin database-storage endpoint and its read-only relation-size reporting."""

from starlette.requests import Request

from backend import main


def test_database_storage_reports_relation_sizes_without_mutating(monkeypatch):
    queries = []

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=()):
            queries.append(query)
            if "pg_database_size" in query:
                return Result([{"bytes": 1024}])
            return Result([{
                "schemaname": "public", "relname": "import_staging_records",
                "table_bytes": 400, "index_bytes": 100, "total_bytes": 700,
            }])

    monkeypatch.setattr(main, "connect", Connection)
    monkeypatch.setattr(main, "require", lambda *args, **kwargs: None)
    request = Request({"type": "http", "method": "GET", "path": "/admin/api/database-storage",
                       "query_string": b"", "headers": []})

    result = main.database_storage(request)

    assert result["database_bytes"] == 1024
    assert result["relations"][0] == {
        "schema": "public", "table": "import_staging_records",
        "table_bytes": 400, "index_bytes": 100, "total_bytes": 700,
    }
    assert all(query.lstrip().upper().startswith("SELECT") for query in queries)
