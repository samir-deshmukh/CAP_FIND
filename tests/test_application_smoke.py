"""Smoke tests for FastAPI startup imports, public API availability and production-safe app configuration."""

"""Smoke tests that verify the FastAPI application and public API can be imported and expose the expected application configuration."""

from __future__ import annotations

import importlib


def test_fastapi_application_imports():
    mod = importlib.import_module("backend.main")
    assert mod.app is not None


def test_public_api_imports_without_database_connection():
    mod = importlib.import_module("backend.api")
    assert getattr(mod, "router", None) is not None


def test_fastapi_docs_and_openapi_routes_are_disabled():
    mod = importlib.import_module("backend.main")
    assert mod.app.docs_url is None
    assert mod.app.redoc_url is None
    assert mod.app.openapi_url is None
