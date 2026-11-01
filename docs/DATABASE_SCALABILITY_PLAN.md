# CETFind Database Scalability Plan

## Goal

Keep public search fast as CAP data grows by 10x–50x without exposing PostgreSQL publicly or adding infrastructure before the workload requires it.

## Current architecture

`cutoffs` and `seats` are authoritative source tables. Public search currently aggregates `cutoffs` in PostgreSQL and joins `institutes`, `programs`, and `cutoff_college_year_summary`. Runtime detail data is already precomputed into:

- `cutoff_trend_points`
- `cutoff_college_year_summary`
- `cutoff_filter_options`
- `seat_matrix_runtime`

This is the correct general direction: raw data remains authoritative; serving data is optimized for reads.

## Target architecture

```text
Official CAP PDFs
      |
      v
validated staging
      |
      v
raw authoritative tables
  cutoffs / seats
      |
      +----> ANALYZE / statistics
      |
      v
controlled derived-data build
      |
      +--> search serving data
      +--> trend serving data
      +--> seat serving data
      |
      v
PostgreSQL
      |
      v
FastAPI public API
      |
      v
CETFind frontend
```

## Phase 1 — do now

1. Keep PostgreSQL private.
2. Keep server-side pagination and projection.
3. Keep the 30-second metadata caches.
4. Treat derived runtime tables as the public serving layer.
5. Run `ANALYZE` after large/bulk imports and derived-data rebuilds so PostgreSQL has current statistics.
6. Capture representative search latency at p50/p95/p99.
7. Obtain `EXPLAIN (ANALYZE, BUFFERS)` from inside the private backend network before changing production indexes.

## Phase 2 — when raw cutoffs become materially larger

Do not blindly add indexes. Test candidate indexes against the real plan.

Primary candidates to evaluate:

```sql
-- Existing and important
(program_id, percentile, institution_code)

-- Candidate only after EXPLAIN proves it useful
(program_id, percentile, institution_code) INCLUDE (rank_number)
```

A covering index may reduce heap access for a read-mostly query, but it also increases index size. It must therefore be benchmarked rather than assumed to be an improvement.

City filtering should be evaluated separately. The current `%city%` predicate is not naturally served by a normal B-tree prefix index. If city search becomes a measured bottleneck, first consider normalizing city to a canonical lookup key and using equality; only then consider a specialized text-search index if the product actually needs substring search.

## Phase 3 — create a dedicated search serving table if raw aggregation becomes the bottleneck

Preferred design:

```text
college_search_runtime
----------------------
program_family
institution_code
percentile
lowest_rank
```

Optionally add only fields proven necessary for the public search response.

The table would collapse repeated category/round/section rows from `cutoffs` into the smallest representation required to answer the public search. It should be rebuilt transactionally from the authoritative tables during publication.

The public search would then perform a bounded indexed lookup against this serving table instead of repeatedly aggregating the full raw fact table.

Important: this table must preserve exact percentile semantics. Do not bucket percentiles unless the UI explicitly accepts approximate results.

## Phase 4 — partitioning

Do **not** partition `cutoffs` now.

Partitioning becomes a candidate only when measurements show that the raw table/indexes are large enough that a single relation is materially hurting cache locality, maintenance, or query execution.

If partitioning is eventually justified, the partition key must match the real workload. A year-only partition is not automatically useful because the primary public search does not currently filter by year.

Potential future designs to benchmark:

```text
RANGE(year)
HASH(program_family)
RANGE(year) + HASH(program_family)
```

Choose only after workload simulation. PostgreSQL's own guidance emphasizes partition pruning and warns that excessive or poorly chosen partitions can increase planning time and memory use.

## Phase 5 — database maintenance

After bulk publication:

```sql
ANALYZE cutoffs;
ANALYZE seats;
ANALYZE cutoff_trend_points;
ANALYZE cutoff_college_year_summary;
ANALYZE cutoff_filter_options;
ANALYZE seat_matrix_runtime;
```

Use targeted column statistics later only if `EXPLAIN` shows poor cardinality estimates.

## Benchmark matrix

Before each major schema change, test:

- 1x current data
- 2x
- 5x
- 10x
- 25x
- 50x synthetic scale

Workloads:

- percentile 50 / 80 / 95
- all cities
- common city
- uncommon city
- page 1
- deep page
- alpha / city / rank / competitiveness sort
- 1 / 3 / 5 concurrent requests

Record:

- p50 / p95 / p99
- DB query time
- connection acquisition time
- rows examined/returned
- shared buffers hit/read
- execution plan

## Decision gates

### Green
p95 remains stable as data grows. Make no schema change.

### Yellow
DB execution time rises materially while API/connection time stays low. Investigate query plan, statistics, and serving-table/index design.

### Orange
A serving-table redesign gives a repeatable improvement in a production-like benchmark. Implement it behind the existing derived-data publication process.

### Red
Single-table/index architecture no longer fits the database size or maintenance window. Benchmark partitioning and/or infrastructure scaling.

## Non-goals

- Do not expose PostgreSQL to the internet for diagnostics.
- Do not disable public rate limiting for capacity tests.
- Do not claim a maximum user count from one-client burst tests.
- Do not add indexes solely because they sound faster.
- Do not partition merely because the row count increased.

## Current recommendation

No production schema rewrite yet. The next high-value engineering task is to add a reliable private `EXPLAIN` workflow and benchmark a synthetic 10x dataset. That gives evidence for whether the existing `cutoffs` query, a dedicated `college_search_runtime` table, or a new index should be the next change.
