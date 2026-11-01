import pytest

from backend.admin import db


def test_convert_positional_sql_to_named_parameters():
    sql, params = db._convert_positional("SELECT * FROM x WHERE a=? AND b=?", (1, "two"))
    assert sql == "SELECT * FROM x WHERE a=:p0 AND b=:p1"
    assert params == {"p0": 1, "p1": "two"}


def test_convert_positional_requires_matching_parameter_count():
    with pytest.raises(ValueError, match="Expected 2 SQL parameters"):
        db._convert_positional("SELECT ? + ?", (1,))


def test_engine_requires_postgresql(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "_ENGINE", None)

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        db._engine()


def test_engine_rejects_non_postgresql_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://example")
    monkeypatch.setattr(db, "_ENGINE", None)

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        db._engine()
