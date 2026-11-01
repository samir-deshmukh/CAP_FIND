# Code quality and test coverage

This pass keeps the existing candidate-facing UI unchanged and focuses on source readability, automated tests, and regression coverage.

## Current results

- 71 tests passed.
- 5 PostgreSQL integration tests are skipped when `TEST_DATABASE_URL` is not configured.
- Core automated coverage is 40.5% across the modules included in the coverage gate.
- The coverage gate is 30%.
- Test suite size is 868 lines across the current test modules.
- Python source under `backend/`, `src/`, and `scripts/` is about 6,000 lines, so the remaining coverage is intentionally tracked rather than hidden.

## Readability changes

The worst minified Python sections were expanded into normal 4-space Python formatting, including:

- `backend/admin/security.py`
- `backend/admin/pipeline.py`
- `backend/admin/state.py`
- `backend/admin/create_admin.py`
- the authentication/import/resolver sections of `backend/main.py`
- `scripts/pg_runtime.py`

A Ruff configuration and development dependency file are included so future changes can be formatted and linted consistently.

## Regression discovered by the new tests

The public search endpoint referenced `_drawer_metadata()` but the helper was missing from `backend/api.py`. This path had not been exercised because the live PostgreSQL tests were skipped. The helper is now implemented as a bounded, parameterized PostgreSQL query and has a regression test.

## Security regression discovered by tests

The resolver URL parser previously transformed an explicit unsupported scheme such as `ftp://...` into a malformed HTTPS URL. It now rejects unsupported explicit schemes before normalization.

## Remaining integration boundary

The full import/publish flow still requires an isolated PostgreSQL database to execute end-to-end. The five existing PostgreSQL integration tests remain the authoritative test boundary for that part of the system.
