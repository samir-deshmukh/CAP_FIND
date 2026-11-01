# CETFind Repository Inventory — Initial Pass

**Inspected baseline:** `905ad947c73062fe77671bd35c7d6263a1786b57`
**Working branch:** `rebuild/cetfind-engineering-baseline`
**Inspection date:** 2026-10-20
**Confidence:** Partial code/document inspection; no local execution in this pass.

This inventory is intentionally evidence-based and incomplete. It records what was inspected, what conflicts, and which risks need measurement. It does not certify the full application or production environment.

## 1. Observed top-level application areas

The application lives under `cet/`. The inspected paths indicate these responsibilities:

| Path | Observed responsibility |
|---|---|
| `site/` | Static candidate-facing HTML/CSS/JavaScript and generated public artifacts |
| `backend/main.py` | FastAPI app, lifespan/startup maintenance, durable import queue loop, health endpoint, admin and public API wiring |
| `backend/api.py` | Candidate-facing API, public search, rate limiting and caching |
| `backend/admin/` | Admin DB wrapper, import lifecycle, validation/staging, auth/security, publishing, resolver and UI |
| `scripts/` | PDF/CSV extraction, chunk splitting, normalization/validation, ingestion and public-data export |
| `db/schema_postgres.sql` | Public data schema |
| `db/admin_schema_postgres.sql` plus migration code | Admin/import workflow schema and incremental changes |
| `data/reference/` | Canonical whitelists and mapping/reference CSVs |
| `tests/` | Unit and fixture tests for API, parsing, chunk extraction and data rules |
| `docs/` | Product requirements, architecture, data decisions, testing and operational notes |

This is a path-based first pass, not a complete directory listing. Generated/runtime directories and deployment configuration still need a complete audit.

## 2. Current intended request and data flow

### Public search
Browser → static frontend → FastAPI public API → PostgreSQL query layer → bounded result page → browser.

The current architecture document states that the browser must not receive the master cutoff dataset and that SQL applies filtering, aggregation, sorting and pagination before results are returned.

### Import
Admin uploads source PDF or canonical CSV → file preflight/security checks → durable import job → serialized background worker → extraction (for PDF) → normalization and existing validation rules → row-level staging/quarantine → comparison with current data → explicit review/approval → transactional production promotion → derived-data rebuild/publication → verification.

The inspected state machine defines states including QUEUED, EXTRACTING, PAUSED, NORMALIZING, VALIDATING, COMPARING, STAGED, REVIEW_REQUIRED, APPROVED, COMMITTING, EXPORTING, PUBLISHING, VERIFYING, COMPLETED, FAILED, CANCELLED, QUARANTINED, and ROLLED_BACK. Legal transitions must be checked against every path that changes status.

## 3. Specific code observations requiring follow-up

These are review findings and investigation targets, not yet proven production root causes.

### R1 — Whole-file DataFrame and in-memory comparison keys
In `backend/admin/processing.py`, the inspected `_compare_seats` implementation uses `pandas.read_csv(...)` to load the entire staged seat CSV and builds a Python set from the matching existing production seat rows. This may create multiple simultaneous representations of a large import. Measure peak memory and determine whether a streaming or database-side comparison can preserve exact duplicate semantics. Inspect `_compare_cutoffs` similarly before concluding that this is the only path.

### R2 — Whole-file progress pre-count
In `_stage_csv`, when a progress callback is provided, the CSV is read once to count records and then read again for staging. The counting pass is streaming, so it does not accumulate all rows, but it adds a full extra parse/read of the file. Benchmark the cost before changing progress semantics.

### R3 — Page chunk size is not a complete memory bound
The backend passes `--chunk-pages 10` to `chunked_cutoff_extractor.py`. The extractor combines chunk outputs incrementally for CSV and JSON, but the inspected implementation accumulates all page-audit objects in `audit_rows`, sorts the list, and builds a separate list of page numbers for complete-coverage validation. For very large PDFs this metadata grows with page count. Measure its real contribution before optimizing; preserve detection of missing and duplicate page coverage.

### R4 — Child extraction process timeout
The inspected `subprocess.run` call for the chunked cutoff extractor captures stdout/stderr and does not specify a timeout. A hung parser can therefore hold the serialized worker indefinitely unless a higher-level control or host termination intervenes. Review cooperative pause/cancel behavior and subprocess termination requirements before adding a timeout; ensure timeout recovery leaves a retryable job and valid manifest state.

### R5 — Output buffering and intermediate copies
The cutoff path creates a canonical copy of the extracted CSV, copies reference data into an isolated work directory, invokes cleaning/validation, stages rows in the database, and retains import artifacts. Inventory every copy, subprocess, and cleanup boundary. Confirm that temporary directories are bounded and that cleanup never removes the only recoverable source/artifact.

### R6 — Existing documentation is inconsistent
The current architecture document describes the static frontend + FastAPI + PostgreSQL system. Superseded Streamlit-era architecture and product documents are retained under docs/archive/streamlit-era/; use the current architecture and code for the deployed system.

### R7 — Dependency manifest contains legacy and broad ranges
`requirements.txt` pins many backend/data libraries but also contains Streamlit/Plotly ranges and a boto3 range. `requirements-dev.txt` includes pytest-cov and Ruff with ranges. Do not remove or upgrade dependencies solely because they appear unused; first map imports, deployment install commands, scripts, tests, and any runtime storage integration.

### R8 — Test configuration and CI differ
`pytest.ini` adds coverage instrumentation and a 30% coverage threshold. The inspected GitHub Actions workflow runs `python -m pytest -o addopts='' -q`, overriding configured addopts, and its push branches are `main` and `security-hardening`; pull requests target `main`. The new rebuild branch will not run that workflow on ordinary pushes unless configuration is deliberately changed. Evaluate whether CI should run coverage and how to gate the rebuild branch without accidentally broadening unrelated workflow triggers.


### R9 — Cutoff comparison multiplies in-memory representations
Further inspection of `_compare_cutoffs` confirms that it loads the entire normalized cutoff CSV into a pandas DataFrame, loads matching existing production rows into a Python set, derives a second identity-to-values structure, and builds a set of staged keys. This is a strong memory-risk candidate for large imports because several structures can scale with the total record count. The comparison's exact-key, changed-key, and within-stage duplicate semantics must be preserved by any rewrite. Profile realistic row counts and memory before changing the algorithm.

### R10 — Approval helper materializes all staged rows
The helper `_load_staged_rows` calls `fetchall()` for all staged records for a job/result type. Inspect all callers and approval transaction logic to determine whether large imports create another full in-memory copy at commit time. If bounded iteration is introduced, preserve transaction consistency and ensure a partial approval cannot be mistaken for a completed release.

## 4. Files inspected in this pass

- `cet/README.md`
- `cet/docs/AGENTS.md`
- `cet/docs/ARCHITECTURE_CURRENT.md`
- `cet/docs/archive/streamlit-era/ARCHITECTURE.md`
- `cet/docs/archive/streamlit-era/PRD.md`
- `cet/docs/RULES.md`
- `cet/docs/TESTING.md`
- `cet/requirements.txt`
- `cet/requirements-dev.txt`
- `cet/pytest.ini`
- `cet/.gitignore`
- `cet/backend/main.py` (selected ranges)
- `cet/backend/admin/processing.py` (selected ranges)
- `cet/backend/admin/state.py`
- `cet/backend/admin/db.py` (selected range)
- `cet/scripts/chunked_cutoff_extractor.py` (selected ranges)
- `cet/tests/test_api_units.py` (selected range)
- `cet/tests/test_chunked_cutoff_extractor.py` (selected range)
- `.github/workflows/tests.yml`

## 5. Verification limitations

- No application code was changed during this inspection.
- No local test suite, linter, build, or benchmark was executed in this pass; the GitHub source connector can inspect and commit repository files but does not execute the checked-out code.
- No production database was queried.
- No Render configuration or production deployment was changed.
- The OOM root cause remains unproven until the full call graph and memory behavior are measured.

## 6. Next discovery tasks

1. Inspect all of `_compare_cutoffs`, the seat-matrix extractor, the native cutoff extractor, CSV import path, and publish/rollback transaction code.
2. Inspect schema/migrations for import-job leases, staging row counts, unique constraints, and transaction boundaries.
3. Map every status transition against `can_transition`, including crash recovery and pause/cancel behavior.
4. Inventory all tracked files and deployment build/start configuration; check for secret/raw-data exposure without printing secret values.
5. Establish a reproducible test environment and execute tests on the branch before any implementation refactor.
6. Prioritize the measured memory peak, not a guessed optimization.
