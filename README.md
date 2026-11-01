# CETFind

CETFind is a Maharashtra CET CAP decision-support application. It helps candidates explore college cutoffs, college details, trends and seat information using approved CAP data.

## Current architecture

The production application has three main parts:

- **Frontend — site/:** static HTML, CSS and JavaScript served to candidates.
- **Backend — backend/:** FastAPI application serving the public API and protected admin interface.
- **Database — PostgreSQL:** authoritative storage for cutoff, seat-matrix, import, review and release data.

The browser communicates with FastAPI over HTTPS. PostgreSQL credentials and the master dataset remain server-side. The browser receives bounded JSON responses from the API. The backend uses indexed and derived PostgreSQL tables where appropriate; it does not publish the master dataset as static files.

The import pipeline is:

PDF upload → extraction → normalization and validation → staging → review → approval → publish

An import is not made public merely because a file was uploaded or extracted.

For the detailed request flow, security boundaries and deployment model, read [Current architecture](docs/ARCHITECTURE_CURRENT.md).

## Repository map

| Path | Purpose |
|---|---|
| site/ | Candidate-facing static website and generated public pages |
| backend/ | FastAPI application, public API and admin workflows |
| db/ | PostgreSQL schema and database-related definitions |
| scripts/ | Extraction, validation, ingestion, database maintenance and SEO utilities |
| src/ | Shared Python modules |
| data/reference/ | Required reference mappings and validation whitelists |
| tests/ | Unit, API, security and regression tests |
| docs/ | Current engineering, product and operational documentation |

Do not delete data/reference/: validation, ingestion and resolver code reads these files. Do not commit credentials, private source PDFs, local import artifacts or production database data.

## Local development

Use the Docker Compose configuration and the local environment file documented for this repository. If .env.docker-local does not exist, copy .env.docker-local.example to .env.docker-local and replace the placeholders. Never commit the real environment file. The Compose setup starts PostgreSQL and the FastAPI backend.

~~~bash
docker compose --env-file .env.docker-local -f compose.yaml -f compose.local.yaml up -d --build
~~~

The backend is exposed locally at http://127.0.0.1:8000. Its liveness endpoint is /healthz.

Required environment variables include the local PostgreSQL connection settings and CET_ADMIN_SESSION_SECRET. Keep real values in local environment files; never paste them into source files or commit them.


## Tests

Development dependencies are listed in requirements-dev.txt.

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
~~~

PostgreSQL integration tests require a dedicated isolated TEST_DATABASE_URL. The ingestion integration tests also require local source CSVs under data/raw/ and data/raw/seats/; those raw datasets are not included in the repository. Never point tests at the production database. See [Testing guidance](docs/TESTING.md) and [Engineering instructions](docs/AGENTS.md).

## Documentation

Start with [the documentation index](docs/README.md). It identifies current guidance and separates historical design documents from instructions for the deployed application.
