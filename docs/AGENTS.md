# CETFind Engineering Instructions

These instructions apply to work under `cet/`. The current implementation and `docs/ARCHITECTURE_CURRENT.md` are the starting references. Older Streamlit-era docs are historical unless code inspection proves a particular detail is still current.

## Product and architecture

CETFind processes official Maharashtra State CET CAP cutoff and seat-matrix source data and presents candidate-facing search, college details, and historical trends.

Current intended runtime:
- site/: static HTML/CSS/JavaScript frontend and generated SEO landing pages; candidate cutoff/seat data is fetched from the API.
- `backend/main.py`: FastAPI application and background import queue lifecycle.
- `backend/api.py`: public candidate API and query orchestration.
- `backend/admin/`: authentication, import processing/state, staging, review/approval, publishing, rollback, resolver and admin UI.
- scripts/: PDF/CSV extraction, normalization, validation, ingestion, PostgreSQL summary refresh and SEO generation.
- `db/schema_postgres.sql` and admin schema/migration code: database structure.
- `data/reference/`: canonical whitelists and mappings.
- `tests/`: unit, fixture, API and extraction regression tests.
- `docs/`: product, architecture, data decisions, testing and operational documentation.

PostgreSQL is the authoritative application database. Do not introduce SQLite fallback or a second authoritative data store. The public browser must not receive the master cutoff/seat dataset. Public college data is returned through bounded API responses; do not publish master data as static files.

## Read before changing a subsystem

- Architecture or deployment: `docs/ARCHITECTURE_CURRENT.md`. Earlier rebuild planning is archived under docs/archive/reports/.
- Import/extraction/validation/staging: `docs/REPOSITORY_INVENTORY.md`, `docs/DECISIONS.md`, `docs/TESTING.md`, then the implementation and tests.
- Database/schema: `db/schema_postgres.sql`, admin schema, migration code, and the corresponding data-flow code.
- Publishing/rollback: inspect the complete approval, publishing and rollback transaction path before editing.
- Security: inspect the relevant authentication, authorization, CSRF, CORS, rate-limiting and file-handling guards before changing behavior.

If documentation conflicts with current code, do not silently pick whichever is convenient. Verify behavior, update the relevant documentation in a separate logical commit, and record unresolved uncertainty.

## Development and tests

Use Python 3.13 for CI parity unless a dependency or deployment constraint is deliberately changed and documented.

From the `cet/` directory:

```bash
python -m venv .venv
# Activate .venv for the current shell.
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The default pytest.ini adds coverage options and a 30% minimum coverage gate. The GitHub Actions workflow runs pytest -q, so it applies those configured options. Do not claim tests pass unless they were actually run and the result was observed. If required services are unavailable, state the exact skipped/unrun checks rather than substituting production.

Never point tests, scripts, migrations, benchmarks or local development at the production DATABASE_URL. Use a dedicated disposable TEST_DATABASE_URL or synthetic fixtures. The ingestion integration tests additionally require local source CSVs under data/raw/ and data/raw/seats/; these git-ignored source datasets are not included in the repository. A local test must fail safely when its required test database is missing; it must not fall back to production.

## Code conventions

- Use type hints and keep modules focused on one responsibility.
- Parameterize SQL. Prefer explicit SQLAlchemy binds and preserve existing database semantics.
- Do not silently swallow exceptions. Report actionable context without leaking secrets or sensitive candidate values.
- Add regression tests for bug fixes and tests for each non-trivial parser/normalization rule.
- Comments must explain non-obvious invariants, safety guards, resource bounds, idempotency, retries, recovery, or compatibility decisions. Do not add comments that merely restate syntax.
- Keep dependencies pinned or bounded deliberately; justify dependency changes in `docs/DECISIONS.md`.
- Do not perform unrelated formatting or refactoring in a bug-fix commit.

## Import and data-integrity invariants

- Preserve the sequence: preflight/security checks → extraction/normalization → validation → staging/review → explicit approval → production commit → publication/verification.
- Extraction and staging must not mutate production fact tables.
- A restart must never imply approval.
- Never silently drop records. Reconcile input records into accepted, quarantined/rejected, or explicitly unresolved outcomes.
- Preserve source PDF, source page, file fingerprint and other available provenance through extraction and staging.
- Retried work must not duplicate rows or mix outputs from different source files/manifests.
- Approval must reject validation findings unless an explicitly reviewed, narrowly scoped repair path is applicable.
- Rollback must affect only rows attributable to the target release.
- Do not change category/program/section whitelists without inspecting representative source rows and adding regression coverage. Extraction artifacts must not be accepted as real data.

## Reliability and performance

- Large PDFs are a resource-risk. Bound memory, page batches, DB batches, CPU concurrency, subprocess duration and temporary disk use where applicable.
- A page-count chunk limit alone does not prove bounded memory: inspect buffers, DataFrames, sets, JSON/audit accumulation, subprocesses and intermediate copies.
- Preserve page coverage, row reconciliation and resumability when optimizing.
- Measure peak memory, elapsed time, pages/chunks processed, and accepted/quarantined row counts using safe representative fixtures.
- Keep long-running processing off the HTTP request path when feasible and preserve durable job state/leases.
- Never weaken validation or discard data to improve throughput.

## Security and privacy

- Never commit secrets, credentials, private source PDFs, raw datasets, or generated master data.
- Use parameterized SQL and validate external inputs.
- Preserve authentication/authorization, secure cookies, CSRF protections, CORS restrictions, rate limits and security headers unless a reviewed change proves a safer replacement.
- Never log credentials or sensitive candidate filter values.
- Do not expose private import artifacts or master data through public static paths.
- Do not test production capacity by bypassing production rate limits or altering production configuration.

## Git, commits, and releases

- Work on the isolated rebuild branch unless explicitly instructed otherwise; do not commit directly to `main`.
- Make one logical, reviewable change per commit. Do not accumulate unrelated changes.
- Before each change, inspect relevant implementation and tests. Add/update tests, run the focused suite, inspect the diff, and commit only the verified scope.
- Use a descriptive commit message. Record the commit, tests, result, and remaining risk in `docs/CHANGELOG_ENGINEERING.md`.
- If tests fail, stop and diagnose or revert the isolated change before continuing.
- Do not force-push or rewrite history.
- A commit is not deployment approval. No production deploy, production data mutation, schema migration on production, or infrastructure change without explicit release approval.
- Prefer free/open-source solutions. Do not introduce paid services or paid add-ons without explicit approval.

## Before every commit

- Confirm the diff contains only the intended logical change.
- Run focused regression tests and relevant broader tests, or explicitly record why they could not run.
- Check for secrets, credentials, raw source data and generated master datasets.
- Verify no production database or deployment was touched.
- Update documentation if behavior, architecture, operational steps, or known risks changed.
- Record the change and test outcome in the engineering changelog.
