from __future__ import annotations

# Smoke tests for FastAPI application startup and public API import configuration.

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
