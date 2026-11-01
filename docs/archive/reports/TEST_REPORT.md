# CET CAP Portal v14 — Release Audit

Audit target: PostgreSQL-only release.

## Automated checks

- Python compilation: PASS
- Pytest: PASS — 26 passed, 5 PostgreSQL integration tests require `TEST_DATABASE_URL`
- Public inline JavaScript syntax (`node --check`): PASS
- Private artifact scan: PASS — no database files, SQLite files, `.env`, PEM/key files, or Python bytecode in release tree
- SQL injection static scan: PASS — no user-controlled f-string SQL execution patterns found; dynamic table names are restricted to fixed allowlists
- `shell=True` scan: PASS
- `eval()` / `exec()` scan: PASS
- PostgreSQL-only application configuration scan: PASS
- Supplied BCA 26 C1 cutoff PDF validation: PASS — 1,336 rows, 346 institute codes, zero validation issues

## PostgreSQL integration tests

The integration suite is intentionally gated by `TEST_DATABASE_URL`. It creates/uses an isolated PostgreSQL database and verifies schema creation, reference seeding, cutoff ingestion idempotency, seat ingestion, enrichment, and runtime exports.

This environment has no PostgreSQL server or client connection available, so these tests are not falsely reported as passing. PostgreSQL's `pg_isready` is the standard way to verify server readiness before running them. See PostgreSQL documentation: https://www.postgresql.org/docs/current/app-pg-isready.html.

## Architecture checks

- PostgreSQL is the only application database path.
- Public browser data is not backed by a bundled master database.
- Runtime derived data is rebuilt from approved PostgreSQL data.
- City/address/website enrichment carries source/provenance fields.
- Admin and public application paths use the same `DATABASE_URL`.
- Release packaging excludes private database/data artifacts.

## Packaging

Runtime dependencies now explicitly include Streamlit and Plotly, which are imported by `app/Home.py`.
