# Engineering Change Log

This log records verified changes made during the CETFind engineering rebuild. Keep entries short and auditable; link each entry to its exact commit. A commit records a source change, not production deployment or release approval.

## 2026-10-20

### Reduce duplicate import and release payload storage
- **Commit:** `4c1a68c`
- **Scope:** Store normalized staging JSON only when it differs from the original source JSON; preserve fallback reads for current and historical rows. Store only institution/program identifiers in new release rollback metadata. Page release ledger reads during rollback and permanent deletion. Add an authenticated read-only endpoint reporting database and largest relation sizes.
- **Purpose:** Reduce avoidable future PostgreSQL growth while preserving source rows, production facts, review, and rollback until the user permanently deletes the release; provide the measurements needed to identify existing storage consumers safely.
- **Validation:** Focused staging, rollback-ledger paging, resolver fallback, and database-storage endpoint tests: 22 passed. Full CET suite: 203 passed, 5 skipped because `TEST_DATABASE_URL` is not configured. Python compileall and `git diff --check` passed. Tests used Python 3.12; CI targets 3.13.
- **Production impact:** None. Existing data is not rewritten or deleted; no production database or deployment was accessed.
- **Limitation:** This prevents duplicate growth for new imports/releases but does not reclaim the already-used 1 GB. The new endpoint must be deployed before the production relation-size breakdown is available.

### Verify the candidate college search path end to end
- **Commit:** pending
- **Scope:** Add a PostgreSQL-backed regression test for the public `/api/search` handler and verify the production frontend page against a disposable PostgreSQL instance using a synthetic college.
- **Validation:** New PostgreSQL integration test: 1 passed. Headless Chrome loaded city/course options, searched Amravati/BBA at percentile 90, and rendered the expected fixture college, cutoff, and percentile from the API/database. Standard suite: 203 passed, 6 skipped because `TEST_DATABASE_URL` was not configured. Running the broader DB-marked suite against the disposable DB produced 3 unrelated fixture failures because `cet/data/raw` is absent; the new search integration test passed independently. No production DB was used.
- **Production impact:** None. All data used was synthetic and stored in a temporary local PostgreSQL container.

### Clean temporary PDF upload copies
- **Commit:** `7e1c965`
- **Scope:** Always remove request-local PDF `.upload` scratch files after upload and clear abandoned root-level upload temps at startup. This applies to the legacy direct PDF endpoint when S3 stores a separate durable copy.
- **Purpose:** Prevent temporary local upload copies from consuming Render disk after failed or deleted imports.
- **Validation:** Full CET suite: 197 passed, 5 skipped because `TEST_DATABASE_URL` was not configured. Focused upload/storage tests: 12 passed. Python compileall and `git diff --check` passed.
- **Production impact:** None. No production files or storage settings were changed.

### Serialize PDF imports through staging and release worker copies
- **Commit:** `6bd24e48c3a4bf74fc6d8cc9b66a081d2ebdf321`
- **Scope:** Keep the single worker queue occupied until CAPFind finishes validating and staging each uploaded extraction. Remove extractor intermediates after upload and, in remote-worker mode, remove the worker's duplicate source PDF and CSV after successful staging.
- **Purpose:** Prevent multiple large extraction/staging jobs from overlapping on the worker PC and bound temporary disk usage while preserving retry data and durable source PDFs.
- **Validation:** Full CET suite: 196 passed, 5 skipped because `TEST_DATABASE_URL` was not configured. Python compileall and `git diff --check` passed.
- **Production impact:** None. This change does not configure storage, deploy code, or delete production data.

### Queue PDF extraction for remote admin-panel access
- **Commit:** `28e5c446556ff66b76710b3b0b58de55f00cbf9c`
- **Scope:** Changed PDF uploads to use private durable S3-compatible storage and an authenticated outbound worker-polling queue. Added server-side worker status/control, lease renewal and recovery, bounded S3 streaming, and a managed Linux user-service installer. Same-PC browser-local uploads remain available until remote mode is configured.
- **Purpose:** Allow an admin to upload, monitor, pause, resume, retry, and cancel PDF imports from another device without exposing the home PC worker to inbound network traffic or doing PDF extraction on Render's 100 MiB web instance.
- **Validation:** Full CET suite: 192 passed, 5 skipped because `TEST_DATABASE_URL` was not configured. Python compileall, shell syntax checks, generated Import Center JavaScript `node --check`, and `git diff --check` passed. Tests ran under Python 3.12 because no Python 3.13 runtime was available locally.
- **Production impact:** None. No Render environment variables, storage bucket, deployment, database, or production data were changed.
- **Rollout requirement:** Remote mode stays unavailable until a private durable S3-compatible bucket and matching `CAPFIND_REMOTE_WORKER_TOKEN` are configured on Render and on the worker PC. This is fail-closed because Render's default filesystem is ephemeral.

### Use job-scoped paths for extracted artifacts
- **Commit:** `320e23554494f2a4fac443f0418089db74dd5213`
- **Scope:** Store server-side extracted CSVs using numeric import job IDs and use a bounded legacy lookup for artifacts created by older worker versions.
- **Purpose:** Remove user-provided PDF filenames from server filesystem path construction identified by CodeQL on PR #21.
- **Validation:** Full CET suite: 193 passed, 5 skipped because `TEST_DATABASE_URL` was not set. Python compileall and `git diff --check` passed.
- **Production impact:** None. No database, storage, or deployment changes.

### Clear retry markers with scoped directory lookup
- **Commit:** `9e74e67256f101d9d04ae81ab45e8fe5b57d3923`
- **Scope:** Remove retry-time pause/cancel markers only after locating the numeric job directory beneath the fixed import-staging root.
- **Purpose:** Address the remaining CodeQL path-flow alert without constructing a filesystem path from request-controlled data.
- **Validation:** Full CET suite: 194 passed, 5 skipped because `TEST_DATABASE_URL` was not set. Python compileall and `git diff --check` passed.
- **Production impact:** None.

### Establish rebuild baseline
- **Commit:** `ebb03f28163d147058eaa78e02cf588dec688847`
- **Scope:** Added `docs/REBUILD_PLAN.md` and created isolated branch `rebuild/cetfind-engineering-baseline` from the known `main` baseline.
- **Purpose:** Record verified architecture, non-negotiable data/security/performance constraints, commit discipline, discovery sequence, and unresolved questions before implementation changes.
- **Validation:** GitHub confirmed the branch creation and file commit. This was a documentation-only change; application tests were not run because no application code changed and this connector session cannot execute the repository's local test suite.
- **Production impact:** None. No Render settings, deployment, database, or production data were changed.
- **Known limitation:** The repository has not yet been fully inventoried or locally tested. The baseline plan explicitly treats the OOM root cause as unproven.

### Record initial repository inventory
- **Commit:** `47bcc8536d0fb11feea03394a08b0478cb3a9640`
- **Scope:** Added `docs/REPOSITORY_INVENTORY.md` based on inspected repository files.
- **Findings:** Identified high-risk memory candidates in whole-file seat comparison and page-audit accumulation, a missing child-process timeout, duplicate CSV reading for progress totals, stale Streamlit-era instructions, and a CI workflow that does not trigger on the new branch's pushes.
- **Validation:** Documentation-only change; source files and production were not modified. Findings are explicitly labeled for further review and measurement, not asserted as confirmed production root causes.
- **Production impact:** None.

### Enable CI push checks on the rebuild branch
- **Commit:** `bcb4f84b977eda63503d97764b29d9cd9aef2bc9`
- **Scope:** Added the isolated rebuild branch to the existing backend-test workflow's push trigger.
- **Purpose:** Make subsequent branch pushes eligible for the repository's existing test workflow without changing the test command or dependencies.
- **Validation:** Workflow file inspected after update. No GitHub Actions run or commit status was returned for this commit, so CI execution is **not verified**; do not treat this as a passing test run.
- **Production impact:** None.

### Align contributor instructions with current architecture
- **Commit:** `9956ca5bb97357f0299b2dd1216bca2298d02764`
- **Scope:** Replaced outdated Streamlit-first contributor instructions with current static frontend + FastAPI + PostgreSQL guidance, data-safety invariants, test commands, security rules, and one-change-per-commit requirements.
- **Validation:** Documentation reviewed against the inspected current architecture and workflow files. Application tests were not run because this was a documentation-only change.
- **Production impact:** None.

### Expand import memory-risk inventory
- **Commit:** `132d9b6056cf183522d6a99b1f679824b56deac9`
- **Scope:** Extended `docs/REPOSITORY_INVENTORY.md` after inspecting cutoff comparison and approval helper implementations.
- **Findings:** `_compare_cutoffs` materializes the normalized CSV and several record-count-scaled key structures; `_load_staged_rows` fetches all staged rows into memory. These are investigation targets; no implementation change was made.
- **Validation:** Source inspection only. No runtime profiling or test execution has yet been performed.
- **Production impact:** None.

# Accept new source-defined CAP categories
- **Commit:** `9216285`
- **Scope:** Treat category whitelist CSVs as descriptive metadata. Accept structurally valid source category codes in cutoff and seat-matrix validation/staging, and register new base codes before fact insertion. Continue rejecting malformed category text and the known extraction anomalies.
- **Purpose:** Avoid rejecting future official category codes simply because they were not anticipated in a static list.
- **Validation:** Python syntax compilation and `git diff --check` passed. The test suite was not run because test execution was not requested. No production database or deployment was touched.
- **Production impact:** None until this change is reviewed, merged, and deployed. New codes initially display their raw code because no curated label/group metadata exists.

### Align category regression tests with dynamic codes
- **Commit:** `c34cfbd15f50adda9b31c42da4eb82b2aa1f8d21`
- **Scope:** Keep `Total` and known extraction artifacts unchanged during seat-category normalization, and cover new valid cutoff and seat category codes in staging tests.
- **Validation:** Focused tests: 16 passed. Full CET suite: 196 passed, 5 skipped. Python syntax compilation and `git diff --check` passed.
- **Production impact:** None. No production database or deployment was touched.
