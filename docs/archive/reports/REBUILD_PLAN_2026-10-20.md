# CETFind Engineering Rebuild Plan

**Status:** Baseline and discovery phase
**Branch:** `rebuild/cetfind-engineering-baseline`
**Baseline:** `main` at `905ad947c73062fe77671bd35c7d6263a1786b57`
**Purpose:** Establish a verifiable engineering baseline before making implementation changes.

This document is a working source of truth for the rebuild. Update it in a dedicated commit whenever verified architecture, constraints, risks, or acceptance criteria change. Distinguish observed facts from assumptions; do not document an unverified hypothesis as a root cause.

## 1. Product intent

CETFind helps Maharashtra State CET candidates explore official CAP cutoff and seat-matrix data across supported course families, years, and rounds. The public experience includes eligibility search, college details, and historical trends. An administrator imports source documents, reviews normalized records, explicitly approves them, and publishes derived public data.

Preserve the existing candidate-facing interface and working behavior unless a separately scoped change has an explicit requirement and regression coverage.

## 2. Verified starting point

The following was verified by reading repository files on the baseline commit; it is not a claim that every path or runtime behavior has been audited.

- The repository is `samir-deshmukh/SAM`; the application is under `cet/`.
- The latest known `main` commit is `905ad947c73062fe77671bd35c7d6263a1786b57`, titled “Test fixed ten-page extraction chunk limit”.
- The current architecture document describes a static HTML/CSS/JavaScript frontend in `site/`, a FastAPI/Uvicorn backend in `backend/`, and PostgreSQL as the authoritative production database.
- Public search is intended to use bounded SQL queries and pagination; the browser must not receive the master dataset.
- The import flow is intended to separate upload/preflight, extraction and normalization, staging, review, explicit approval, publishing, and rollback.
- Cutoff and seat-matrix data have separate extraction/validation paths. Existing validation and normalization rules must be reused or deliberately migrated with parity tests, not casually reimplemented.
- Runtime JSON/JavaScript artifacts are derived build products; approved PostgreSQL data is the source of truth.
- The repository contains older Streamlit-era documentation alongside newer FastAPI/static-site documentation. Treat `docs/ARCHITECTURE_CURRENT.md` and the current implementation as the starting reference, then verify both against code and deployment.
- The current dependency file includes PDF parsers, pandas, SQLAlchemy, PostgreSQL driver, FastAPI, Uvicorn, image/OCR libraries, Streamlit, Plotly, and boto3. Actual imports and deployed requirements must be audited before removing or upgrading dependencies.

## 3. Production stability finding to investigate

Render previously reported repeated backend out-of-memory kills at approximately the 512 MiB instance limit. A recent import request returned HTTP 202 before one recorded OOM event. This temporal relationship makes import processing a plausible cause, but it does **not** prove which allocation or code path exhausted memory.

The latest baseline commit adds a source-text assertion that a cutoff extraction chunk limit is ten pages. That assertion alone does not prove that every parser, intermediate buffer, validation stage, or downstream transformation respects a bounded-memory contract.

Required investigation:
1. Trace the full import lifecycle from upload through extraction, staging, approval, and publishing.
2. Identify all whole-file reads, page/row accumulation, duplicate copies, subprocesses, and retained temporary artifacts.
3. Measure peak memory and wall-clock time with representative fixtures and a safe local/test environment.
4. Verify exact row reconciliation and restart/retry behavior before and after each proposed optimization.
5. Do not change production settings, run experiments against production data, or deploy a performance change without explicit approval.

## 4. Non-negotiable engineering constraints

### Data integrity
- PostgreSQL is the production source of truth; never silently substitute SQLite or a local database.
- No test or benchmark may connect to the production database.
- Preserve the staging/review/approval boundary. Extraction and staging must not mutate production cutoff/seat facts.
- Every source record must be accounted for as accepted, rejected/quarantined, or explicitly unresolved. Never silently drop rows.
- Import operations and retries must be idempotent where applicable and leave an auditable result.
- Rollback must affect only records attributable to the release being rolled back.
- Do not commit source PDFs, raw datasets, generated master datasets, secrets, or credentials.

### Stability and performance
- Bound memory, CPU concurrency, file size, page batches, database batches, and temporary disk usage explicitly.
- A page chunk limit is not, by itself, proof of a memory bound.
- Keep long-running extraction off latency-sensitive HTTP request paths where the architecture allows.
- Persist job state and checkpoints so process restarts do not imply approval or loss of staged data.
- Do not trade correctness for throughput. Report measured peak memory, elapsed time, processed pages, row counts, and failures for performance work.

### Security and privacy
- Parameterize SQL and validate input at API boundaries.
- Keep secrets server-side and out of Git history.
- Preserve authentication, authorization, CSRF protections, secure cookie settings, CORS restrictions, rate limiting, and security headers unless a reviewed change demonstrates why a change is necessary.
- Do not log sensitive candidate filter values or credentials.
- Do not expose private import artifacts or master datasets from public static paths.

### User experience
- Preserve the existing CETFind visual layout and established workflows by default.
- UI changes require a specific problem statement and a regression check at mobile and desktop sizes.
- Admin status must distinguish queued, running, paused (if supported), failed, review-required, approved, published, and rolled-back states accurately; never show a false success.

### Cost and operations
- Prefer free and open-source tools; do not add paid services or paid add-ons without explicit approval.
- Verify actual free-tier storage, memory, CPU, database, and worker limits rather than assuming a service can handle large PDFs.
- Production deployment is a separate release decision. A code commit does not authorize a deployment or a production data mutation.

## 5. Commit and change protocol

- Work on `rebuild/cetfind-engineering-baseline`, not directly on `main`.
- One logical, reviewable change per commit. Do not batch unrelated work into a single commit.
- Before editing, inspect the current implementation and the tests that cover it.
- For each change: state the hypothesis/requirement, make the smallest patch, add or update focused tests, run them, inspect the diff, and commit only the verified scope.
- If a test cannot run, record the exact reason and do not describe it as passing.
- If a change fails tests, do not stack more changes on top; diagnose or revert that isolated change.
- Use descriptive commit messages explaining the intent.
- Add comments for non-obvious invariants, safety guards, resource bounds, idempotency, retry/recovery logic, and surprising compatibility behavior. Comments must explain why the rule exists and what could break if removed; do not narrate obvious code.
- Keep a short change log with commit SHA, files, tests, outcome, and residual risk.
- No force-push, destructive history rewrite, production deployment, or production data mutation without an explicit decision.

## 6. Discovery sequence

### Phase 0 — Baseline and repository inventory
- Confirm branch/head and working baseline.
- Inventory files, entry points, scripts, migrations/schema, tests, workflows, runtime artifacts, and dependency declarations.
- Check for accidentally tracked data/secrets and duplicate or obsolete implementations.
- Reconcile current code with the architecture and runbook documents.
- Establish commands and baseline results without connecting to production.

### Phase 1 — Architecture and data lineage
- Trace public search from browser request through API and SQL to response.
- Trace college detail/trends and all derived-data exports.
- Trace PDF upload, preflight, storage, extraction, normalization, validation, staging, review, approval, publication, failure, retry, and rollback.
- Map important database tables, foreign keys, indexes, unique constraints, transactions, and ownership of each data field.
- Record state transitions and invariants.

### Phase 2 — Reproducible local verification
- Document a clean local setup using synthetic/test data.
- Separate unit, integration, API, browser, and performance tests.
- Ensure tests fail clearly when required test services are missing and never fall back to production.
- Establish a baseline test report before refactoring.

### Phase 3 — Risk-first engineering
Fix one verified risk at a time, prioritizing data loss/corruption, security boundary failures, import recovery, resource exhaustion, and incorrect public results. Each fix requires a regression test and an isolated commit.

### Phase 4 — Controlled redesign, only where justified
Consider module boundaries, durable background processing, schema migrations, and dependency reduction only after the current behavior and invariants are understood. Avoid a big-bang rewrite that discards validated data rules or working UI behavior.

### Phase 5 — Release readiness
Require passing tests, reproducible build, migration/rollback review, security review, data reconciliation, bounded-resource evidence, and a documented release/rollback plan. Deployment remains a separate explicit approval.

## 7. Required project documentation

Maintain and keep aligned:
- `PROJECT_OVERVIEW.md` — purpose, users, features, constraints, and non-goals.
- `ARCHITECTURE_CURRENT.md` — verified current components and request/data flows.
- `DATA_LINEAGE.md` — official source to normalized records to published artifacts.
- `IMPORT_STATE_MACHINE.md` — states, legal transitions, recovery, retries, and invariants.
- `DATABASE_GUIDE.md` — table ownership, keys, indexes, transactions, and migrations.
- `TESTING.md` — exact safe commands, fixture strategy, test layers, and known skips.
- `OPERATIONS_RUNBOOK.md` — deployment, health checks, monitoring, recovery, and rollback.
- `DECISIONS.md` — dated decisions, evidence, alternatives, and consequences.
- `CHANGELOG_ENGINEERING.md` — one entry per verified change/commit.

Do not create empty documents merely to satisfy this list. Add or reconcile each document when its subject has been inspected.

## 8. Definition of done for each change

A change is complete only when:
1. Scope and expected behavior are explicit.
2. Existing invariants are preserved or intentionally changed with documented rationale.
3. Focused regression tests pass.
4. Relevant broader tests pass, or limitations are clearly reported.
5. Diff contains only the intended logical change.
6. Comments and documentation explain non-obvious decisions.
7. No secret, raw source data, or generated master dataset is included.
8. A dedicated commit exists and its SHA is recorded.
9. Production remains untouched unless a separately approved release says otherwise.

## 9. Open questions — do not guess

- Which code paths account for the observed OOM events and what is their measured peak memory?
- Does every extraction, normalization, validation, staging, and publish step operate in bounded batches?
- Which files and dependencies are actually used in the deployed FastAPI/static-site architecture?
- Do current tests cover data reconciliation, restart recovery, duplicate retries, approval transaction rollback, and publication consistency?
- Which deployment environment variables, persistent-storage settings, database limits, and build commands are currently active? Verify these without exposing secret values.
- Are any existing documentation claims inconsistent with the code or live system? Track each discrepancy with evidence.

## 10. Current status

Only repository documentation and a rebuild branch have been established so far. No application code, database schema, production data, Render configuration, or production deployment has been changed by this rebuild plan. The project is not yet certified as fully understood or release-ready.
