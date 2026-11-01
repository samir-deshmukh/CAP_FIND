# Current public data flow

PostgreSQL is the production source of truth. The candidate website does not load generated course-wide cutoff or seat-matrix files. It requests bounded JSON responses from the FastAPI backend.

## Browser-to-database flow

1. site/index.html requests supported cities and courses from /api/options.
2. Candidate searches call /api/search with course, percentile, optional city, sort order and bounded pagination.
3. Opening a college requests its trend-filter metadata from /api/colleges/{institution_code}/trend-options.
4. The selected college and year's cutoff rows are requested from /api/colleges/{institution_code}/year/{year}.
5. Seat-matrix rows and their source-PDF metadata are requested from /api/colleges/{institution_code}/seats.
6. FastAPI validates requests, applies public rate limits and reads PostgreSQL through SQLAlchemy. Responses contain only the requested college/page data.

## Derived PostgreSQL data

An administrator can request a derived-data rebuild from the CET Data Calculator. The backend runs scripts/refresh_derived_data.py as a separate maintenance job to rebuild indexed summary tables used by public search, trend summaries and seat-matrix compatibility paths. A one-time startup recovery hook also exists, but routine restarts do not trigger a rebuild. These are database tables, not public static files.

## Data integrity and security

- Raw cutoff and seat rows remain authoritative.
- Derived summaries are rebuilt from approved database rows.
- Search results are aggregated and paginated in SQL before the bounded result page reaches pandas.
- College cutoff and seat details are scoped to the requested institution and course.
- Database credentials and master datasets remain server-side.
- Do not publish database exports, private import files or runtime artifacts under site/.

## Historical implementation notes

Older decisions in docs/DECISIONS.md describe earlier static JSON/JavaScript export approaches. Those notes are retained as project history; they are not the current production data path.
