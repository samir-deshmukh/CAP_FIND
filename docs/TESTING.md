# Testing and verification

## Test layers

The current test suite covers:

- Parser and extraction rules for cutoff and seat-matrix PDFs.
- Category, program, stage, section and filename normalization.
- Import staging, duplicate detection, recovery and validation behavior.
- FastAPI public API behavior, response caching and bounded search.
- Authentication, session security, rate limits, network validation and source storage.
- Worker pause/cancel controls and remote-worker security.
- PostgreSQL schema, ingestion and data-integrity contracts.

Tests are under tests/ and are not production runtime code.

## Install and run

Use Python 3.13 to match the GitHub Actions code-quality workflow.

~~~bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
~~~

The default pytest.ini enables coverage reporting and a 30% minimum coverage gate. The CI workflow also runs Ruff formatting/lint checks on selected core modules.

## PostgreSQL integration tests

Database tests require a dedicated, disposable TEST_DATABASE_URL. Never use the production DATABASE_URL. Tests must not fall back to production if the test database is missing.

The PostgreSQL integration tests are skipped when TEST_DATABASE_URL is not set. Some tests in test_postgres_integration.py exercise ingestion using local CSV input under data/raw/ and data/raw/seats/. These source datasets are intentionally git-ignored and are not included in the repository. Provide the required local test data before running those ingestion tests with TEST_DATABASE_URL.

The PostgreSQL contract tests and API integration tests also include synthetic rows created and cleaned up within the isolated test database.

## Local development services

The Docker Compose configuration starts PostgreSQL and the FastAPI backend. The static frontend is in site/ and calls the backend API. For local testing, use the local Compose environment and a disposable database; do not connect a test run to production.

## Safety rules

- Never run integration tests against production.
- Never commit real CAP source PDFs, raw imported datasets, private database exports or credentials.
- Preserve the source data and provenance in parser tests; do not replace real values with guessed mappings.
- When a test cannot run because a service or local input dataset is unavailable, report that exact limitation rather than claiming success.
- Add regression tests for bug fixes and non-trivial parser/normalization rules.
