# CETFind documentation index

Use the current documents below when learning, maintaining or presenting the deployed application.

## Start here

1. [Current system architecture](ARCHITECTURE_CURRENT.md) — frontend, API, database, import and publishing flow.
2. [Repository inventory](REPOSITORY_INVENTORY.md) — codebase structure and subsystem responsibilities.
3. [Engineering instructions](AGENTS.md) — rules for safe changes, verification and tests.
4. [Testing strategy](TESTING.md) — unit and integration test expectations.
5. [Engineering decisions](DECISIONS.md) — why important implementation choices were made.

## Subsystem and operations guides

- [CSV import](CSV_IMPORT.md)
- [Admin review and publishing](ADMIN_PART3.md)
- [College website resolver](COLLEGE_WEBSITE_RESOLVER.md)
- [Security hardening](SECURITY_HARDENING.md)
- [Code quality](CODE_QUALITY.md)
- [Runtime architecture](FAST_RUNTIME_ARCHITECTURE.md)
- [Database scalability plan](DATABASE_SCALABILITY_PLAN.md)
- [Database storage and release notes](DB_SCALABILITY.md)
- [Local extraction worker](LOCAL_EXTRACTION_WORKER.md)
- [Server extraction](CAPFIND_SERVER_EXTRACTION.md)

Other focused specifications and implementation notes remain in this directory. Check their dates and verify claims against the current code before treating them as current behavior.

## Historical documents

The archive contains superseded Streamlit-era design notes, an earlier rebuild-plan snapshot and historical audit records. They are retained for traceability, not as instructions for the current deployed application.

- [Streamlit-era documents](archive/streamlit-era/)
- [Historical audit and validation reports](archive/reports/)

The current architecture document is the source of truth for the deployed frontend + FastAPI + PostgreSQL system.
