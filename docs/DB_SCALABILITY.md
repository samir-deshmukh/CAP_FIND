# CETFind Database Scalability Plan

## Goal

Keep public search predictable as CAP data grows from the current dataset toward 10x–50x its current size, without exposing PostgreSQL or adding infrastructure prematurely.

## Current architecture

- `cutoffs` and `seats` are authoritative historical/source tables.
- `programs` and `institutes` provide normalized metadata.
- `cutoff_trend_points`, `cutoff_college_year_summary`, `cutoff_filter_options`, and `seat_matrix_runtime` are serving/derived tables.
- Public search performs aggregation and pagination in PostgreSQL and only returns the requested page.
- Metadata is cached in the API process.

## Target architecture

```text
CAP PDFs
   |
   v
validated staging/import
   |
   v
authoritative raw tables
   |
   +--> derived-data build --> serving tables
   |                              |
   |                              v
   +--> validation  ----------> publish
                                  |
                                  v
                              public API
                                  |
                                  v
                                users
```

Raw tables remain the source of truth. Public requests should increasingly use purpose-built serving tables rather than recomputing historical aggregates.

## Phase 1 — current / immediate

1. Keep the database private.
2. Keep PostgreSQL-side aggregation and bounded pagination.
3. Keep the 30-second metadata cache.
4. Run `ANALYZE` after successful derived-data rebuilds so planner statistics reflect the new dataset.
5. Measure representative production queries with `EXPLAIN (ANALYZE, BUFFERS)` from inside the private backend network.

### Storage diagnosis

Use the authenticated, read-only `GET /admin/api/database-storage` endpoint to inspect the current database size and the 30 largest application relations. It reports heap, index, and total relation bytes; PostgreSQL TOAST data is included in the total. Capture this before removing data or changing indexes so the actual storage consumer is known. The endpoint does not scan table contents or mutate database state.

Deleting rows does not necessarily return disk space to the hosting provider. PostgreSQL can reuse freed pages inside a relation; a table rewrite such as `VACUUM FULL` requires extra free disk and can fail on a full database. Do not run a rewrite or remove indexes based on estimates alone.

### Import/release storage

- Staging keeps the original row in `raw_json`. When normalization makes no change, `normalized_json` is NULL and readers use `COALESCE(normalized_json, raw_json)`. Rows changed by continuation-cell normalization retain both versions.
- New release ledger entries retain only `institution_code` and `program_id` in their rollback metadata. The authoritative fact row and staged source evidence remain intact. Rollback continues to use the ledger row IDs, while permanent release deletion removes the release ledger and its linked staging evidence as before.
- Existing ledger rows are not rewritten automatically. A mass rewrite on a full database risks exhausting disk and PostgreSQL table rewrites need additional space. Measure current relation sizes first.

## Phase 2 — when raw search becomes the bottleneck

Do not add indexes blindly. Compare the execution plan first.

Candidate serving-table evolution:

- `college_search_summary`: one row per `(program_family, institution_code)` for stable institution metadata and precomputed counts.
- `college_cutoff_points`: compact, query-oriented cutoff points for eligibility lookup when raw `cutoffs` becomes too large.
- Keep trend/seat tables specialized for their existing UI workloads.

The exact columns and indexes for these tables must be derived from real query plans and data cardinalities.

## Phase 3 — indexing

Prefer a small number of indexes that match the real workload. The current `(program_id, percentile, institution_code)` index is a baseline, not a guarantee that it remains optimal at 10x–50x scale.

Every new index must answer:

- Which query uses it?
- How selective is the leading column?
- Does it reduce scanned rows or sorting?
- What storage/write cost does it add?

## Phase 4 — growth testing

Benchmark at approximately:

- 1x current data
- 2x
- 5x
- 10x
- 25x
- 50x

For each level record p50/p95/p99, database execution time, rows scanned/returned, buffer hits/reads, and connection wait.

Representative workloads:

- BBA at percentile 50/80/95
- all cities and a major city
- page 1 and a later page
- each supported course family

## Phase 5 — partitioning

Partitioning is a conditional optimization, not a default. A future `cutoffs` partitioning scheme should only be introduced if query plans and data volume show clear partition-pruning benefits. A year-only partition is not automatically useful because the main public search does not filter by year.

## Phase 6 — infrastructure

Only after query/serving-layer optimization is exhausted:

```text
load balancer
   |
   +-- API instance
   +-- API instance
   +-- API instance
            |
            v
       PostgreSQL
```

On the current free deployment, keep expectations realistic: one API instance is not a multi-instance production cluster.

## Non-negotiable rules

- Never expose PostgreSQL just to obtain an execution plan.
- Never disable public rate limiting for load tests.
- Never create an index solely because a column appears in a WHERE clause.
- Never partition solely because row count increased.
- Never replace authoritative data with a derived table without validation and rollback.
- Benchmark before and after every performance change.
