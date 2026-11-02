"""Tests for database result wrappers, institute normalization and public-tree safety checks."""

import json

from backend.admin.db import Result
from backend.admin.publishing import verify_public_tree
from scripts.enrich_institutes import norm, validate_website


class FakeResult:
    rowcount = 2

    def fetchone(self):
        return type("Row", (), {"_mapping": {"id": 1, "name": "A"}})()

    def fetchall(self):
        return [
            type("Row", (), {"_mapping": {"id": 1}})(),
            type("Row", (), {"_mapping": {"id": 2}})(),
        ]

    def __iter__(self):
        return iter(self.fetchall())


def test_result_wrapper_exposes_mapping_rows():
    result = Result(FakeResult(), inserted_id=17)
    assert result.rowcount == 2
    assert result.lastrowid == 17
    assert result.fetchone() == {"id": 1, "name": "A"}
    assert result.fetchall() == [{"id": 1}, {"id": 2}]
    assert list(result) == [{"id": 1}, {"id": 2}]


def test_institute_helpers_validate_and_normalize():
    assert validate_website("https://example.edu") == "https://example.edu/"
    assert validate_website("not a url") is None
    assert norm("Sant Gadge-Baba University") == "SANT GADGE BABA UNIVERSITY"


def test_public_tree_verification_accepts_valid_runtime(tmp_path):
    public = tmp_path / "site"
    data = public / "data"
    data.mkdir(parents=True)
    (data / "app.js").write_text("window.SEARCH = [];", encoding="utf-8")
    (data / "asset-manifest.json").write_text(json.dumps({"version": 1}), encoding="utf-8")
    (data / "small.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    result = verify_public_tree(public)

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["file_count"] == 3


def test_public_tree_verification_rejects_private_key(tmp_path):
    public = tmp_path / "site"
    data = public / "data"
    data.mkdir(parents=True)
    (data / "app.js").write_text("window.SEARCH = [];", encoding="utf-8")
    (data / "asset-manifest.json").write_text("{}", encoding="utf-8")
    marker = "-----BEGIN " + "PRIVATE KEY-----"
    (data / "bad.json").write_text(json.dumps(marker), encoding="utf-8")

    result = verify_public_tree(public)

    assert result["ok"] is False
    assert any("secret pattern" in error for error in result["errors"])
