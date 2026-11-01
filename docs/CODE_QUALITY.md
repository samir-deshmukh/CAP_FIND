# Code quality and verification

This document records checks run against the cleaned working copy. The local test run used Python 3.12.3; GitHub Actions is configured for Python 3.13.

## Current verification

- 77 Python source files parsed successfully with zero syntax errors.
- Both inline JavaScript blocks in site/index.html passed Node.js syntax checking.
- Docker Compose configuration passed validation using the local environment file.
- 21 relative Markdown links were checked; none were broken.
- The local secret-pattern guard passed.
- Ruff formatting and lint checks passed for the four modules checked by CI.
- pytest: 201 passed, 7 skipped, 7 warnings.
- Total test coverage: 45.10%, above the configured 30% minimum.
- The 7 skipped tests are PostgreSQL integration tests gated by TEST_DATABASE_URL.
- No production database was used. TEST_DATABASE_URL was not set for the local run.
- The original cet/ directory was not modified.

## Reproduce checks

Use Python 3.13 to match the GitHub Actions workflow.

~~~bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
ruff format --check backend/admin/security.py backend/admin/pipeline.py backend/admin/state.py backend/admin/create_admin.py
ruff check backend/admin/security.py backend/admin/pipeline.py backend/admin/state.py backend/admin/create_admin.py
python -m pytest -q
~~~

PostgreSQL integration tests require a dedicated isolated TEST_DATABASE_URL. Some ingestion tests also require local source CSVs under data/raw/ and data/raw/seats/. Those datasets are git-ignored and are not included in the repository. Never point tests at the production database.

## Dependency audit

| Dependency | Why it remains |
|---|---|
| pandas | Bounded public result handling and import/validation processing |
| pdfplumber | Seat-matrix PDF text/table extraction |
| pdfminer.six | Explicitly pinned PDF parsing dependency used by pdfplumber |
| SQLAlchemy | PostgreSQL engine, queries and transactions |
| psycopg2-binary | PostgreSQL driver used by SQLAlchemy and worker checkpoints |
| requests | HTTPS communication from the remote extraction worker |
| fastapi | Public API, admin routes and local worker HTTP service |
| uvicorn | ASGI server used to run the backend and worker |
| python-multipart | FastAPI file-upload and form endpoints |
| itsdangerous | Signed/timed admin session tokens |
| pytesseract | Python OCR wrapper; the Tesseract OS executable is separately required |
| Pillow | Image processing for extraction/OCR paths |
| PyMuPDF | PDF page handling and chunk splitting |
| pypdfium2 | PDFium-backed extraction adapter |
| boto3 | Optional S3-compatible private PDF storage |
| pytest, pytest-cov, Ruff | Development and CI verification |

Two packages were removed from the runtime manifest after checking the repository: openpyxl (no spreadsheet read/write path found) and python-dotenv (no direct import or load_dotenv usage found). The missing direct runtime dependency requests was added. pdfminer.six remains explicitly pinned because it is part of the PDF text-extraction dependency chain. Camelot remains an optional import guarded by ImportError; it is not installed as a required dependency.

The unused Streamlit/Plotly application and its UI-only tests were removed from this cleaned copy. Shared PostgreSQL query and DataFrame search helpers remain because backend/api.py imports them. Superseded design documentation remains archived.

## CI scope

The GitHub Actions code-quality workflow installs requirements-dev.txt, checks formatting and linting for selected core modules, then runs pytest. It does not currently lint every Python file in the repository.

## Dependency policy

- requirements.txt contains packages needed by the current backend, extraction pipeline and worker.
- requirements-dev.txt adds pytest, coverage and Ruff.
- Keep optional OCR and PDF libraries only when their call sites or fallback behavior are understood.
- Do not remove transitive pins without checking the dependency that requires them.

Historical test counts and coverage figures are retained in docs/archive/reports/CODE_QUALITY_HISTORICAL.md; these are snapshots from an earlier checkout, not current verification results.
