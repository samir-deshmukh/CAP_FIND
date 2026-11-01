# CETFind repository inventory

This document describes the cleaned working copy's current structure. Use it with ARCHITECTURE_CURRENT.md; verify implementation details against the source before making changes.

## Application architecture

| Area | Responsibility |
|---|---|
| site/ | Candidate-facing static HTML, CSS and JavaScript |
| backend/main.py | FastAPI application, admin routes, startup and publishing workflows |
| backend/api.py | Public options, search, college details, cutoff-year and seat-matrix APIs |
| backend/admin/ | Authentication, import processing, validation, staging, review, resolver and publishing |
| backend/admin_ui.py | Admin interface served by FastAPI |
| backend/local_worker.py | Local/remote PDF extraction worker |
| db/ | PostgreSQL schemas |
| src/cet_cap/ | Shared PostgreSQL connection, query and DataFrame search helpers |
| data/reference/ | Required canonical CSV mappings and validation whitelists |
| scripts/ | Extraction, validation, ingestion, worker and maintenance commands |
| tests/ | Unit, API, security, extraction and PostgreSQL integration tests |
| docs/ | Current engineering and operational documentation |

## Current public data path

The browser calls FastAPI endpoints:

- /api/options — supported cities and courses
- /api/search — bounded, paginated college search
- /api/colleges/{institution_code}/trend-options — available trend filters
- /api/colleges/{institution_code}/year/{year} — one college's cutoff rows for one year
- /api/colleges/{institution_code}/seats — latest seat rows and source-PDF metadata

FastAPI reads PostgreSQL. The production frontend does not require course-wide static cutoff or seat JSON exports. An administrator can request a separate derived-data rebuild through the CET Data Calculator; the backend runs scripts/refresh_derived_data.py to rebuild indexed/derived PostgreSQL summary tables.

## Script groups

**Extraction and worker control**
- cutoff_extractor.py, chunked_cutoff_extractor.py
- seat_matrix_extractor.py, fitz_pdfium.py
- local_folder_extract.py, worker_control.py
- resolver_worker.py

**Validation and ingestion**
- category_codes.py, clean_data.py
- validate_data.py, validate_seats.py
- db_bootstrap.py, seed_reference_tables.py
- ingest.py, ingest_seats.py
- enrich_institutes.py, refresh_derived_data.py

**Public discoverability and security**
- generate_public_landing_pages.py — generates crawlable college/city/course pages under site/seo/
- generate_public_seo.py — generates robots.txt and sitemap.xml for a supplied HTTPS domain
- check_repo_secrets.py — local source-tree secret-pattern check

These scripts are not interchangeable. Check their inputs, outputs and callers before moving or deleting one.

## Files that must be retained

- data/reference/*.csv: consumed by import, validation and normalization code.
- tests/: regression and security protection; test files are not production runtime code.
- site/seo/: generated public pages and manifest; these are deployed website content, not disposable cache files.
- Dockerfile, compose.yaml, compose.local.yaml, .dockerignore: local development and container configuration.
- requirements.txt and requirements-dev.txt: runtime and development dependencies.

## Legacy and historical material

- Streamlit-era documentation is retained for historical context under docs/archive/streamlit-era/. The legacy application source and its dependencies were removed from this cleaned copy because they had no production callers. Shared query/search helpers remain because the FastAPI API imports them.
- Superseded architecture and widget-delivery notes are in docs/archive/streamlit-era/.
- Historical audit, validation and code-quality snapshots are in docs/archive/reports/.
- Old static JSON/JavaScript runtime exporters were removed from this cleaned copy because the current frontend requests data from the API. Historical decisions mentioning those exporters remain in docs/DECISIONS.md.

## Safety rules for future cleanup

1. Do not remove reference CSVs based only on filenames; inspect every reader.
2. Do not remove tests because they are not imported by production code.
3. Do not delete SEO pages without verifying the generator, manifest, deployment and current URLs.
4. Do not remove scripts until checking Python imports, subprocess calls, CI, docs and manual operational workflows.
5. Never use production DATABASE_URL for tests. PostgreSQL integration tests require a dedicated isolated TEST_DATABASE_URL.
