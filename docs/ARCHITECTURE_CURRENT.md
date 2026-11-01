# CETFind — Current System Architecture

> Current production architecture as inspected in November 2026. Older planning documents in this repository describe earlier Streamlit or static-export designs and are retained as historical records.

## 1. High-level flow

Browser
→ Render Static Site (CETFind frontend)
→ HTTPS requests to FastAPI backend
→ PostgreSQL

Admin browser
→ FastAPI /admin
→ PostgreSQL + private import/derived-data pipeline

CAP source PDFs
→ admin import/review/approval
→ normalized PostgreSQL tables
→ indexed/derived PostgreSQL tables
→ candidate API

## 2. Runtime components

### Frontend
- Static HTML/CSS/JavaScript in `site/`.
- Hosted separately from the API.
- Candidate search calls `/api/options`, `/api/search`, and college-detail endpoints.
- The browser does not receive the master cutoff dataset.

### Backend
- FastAPI application in `backend/`.
- Uvicorn/ASGI runtime.
- Public API and admin application are served by the same backend service.
- FastAPI OpenAPI, Swagger UI and ReDoc are disabled in production.
- `/healthz` is a lightweight liveness endpoint.

### Database
- PostgreSQL is the source of truth for production data.
- Public search uses SQL aggregation and pagination.
- The public search path sends only the requested result page to pandas.
- Database indexes and derived PostgreSQL summary tables support cutoff filtering, program/institution lookup and bounded public responses.

## 3. Public search request

1. User selects course, percentile, optional city and sort order.
2. Frontend sends a bounded request to `/api/search`.
3. Backend validates parameters and applies the public API rate limit.
4. PostgreSQL joins `cutoffs`, `institutes`, and `programs`.
5. SQL aggregates one summary row per institution.
6. SQL applies sorting and pagination.
7. A total count is returned with the page.
8. Backend converts the bounded result page into the API response.
9. Browser renders college cards.

This avoids the previous design where the complete matching cutoff set was loaded into pandas for every public search.

## 4. College details

A college card requests trend-filter metadata from /api/colleges/{institution_code}/trend-options. The selected college/year cutoff rows come from /api/colleges/{institution_code}/year/{year}. Queries are scoped by institution and course rather than loading the whole dataset into the browser.

Seat-matrix rows and source-PDF course metadata come from /api/colleges/{institution_code}/seats. The API reads PostgreSQL and keeps the master data server-side.

## 5. Import and publishing pipeline

1. Administrator uploads a CAP source PDF from any device.
2. The authenticated API streams it to private durable S3-compatible storage; the PDF is not held in Render memory as one complete byte buffer.
3. The worker PC claims queued jobs over outbound HTTPS, downloads and fingerprint-checks the PDF, then performs memory-heavy extraction locally.
4. The extracted artifact returns to the API for normalization/validation and staging.
5. Import is staged for review.
6. Administrator explicitly approves the import.
7. Publishing promotes the approved release.
8. An administrator can explicitly request a derived-data rebuild from the CET Data Calculator. The backend runs scripts/refresh_derived_data.py as a separate maintenance job; this is not an automatic static-file export during publication.

A restart does not implicitly approve staged imports.

## 6. Security boundaries

- Database credentials remain server-side.
- Master datasets are not mounted as public static files.
- Production API documentation endpoints are disabled.
- CORS is restricted to the canonical frontend origin.
- Admin sessions use secure cookie settings in production.
- Admin state-changing operations use CSRF protection.
- Authentication checks account status and session authentication version.
- Login attempts are throttled.
- Public feedback has a separate limiter.
- Public analytics stores anonymous event/session identifiers rather than IP addresses.
- Security headers include CSP, frame protection, MIME sniffing protection, referrer policy and permissions policy.
- Import processing is serialized because PDF processing is memory-heavy on the free instance.
- The public API rate limiter is intentionally part of production protection and must not be bypassed during capacity testing.

## 7. Scalability model

Current free deployment is a single public backend service backed by PostgreSQL. It is not evidence of a multi-instance load-balanced architecture.

For higher traffic, the logical evolution is:

CDN/static frontend
→ load balancer/reverse proxy
→ multiple FastAPI instances
→ PostgreSQL
→ optional cache/queue for workloads that justify them

Horizontal scaling requires shared state for anything currently stored in process memory, especially rate limiting and other per-process caches. Database connection limits must also be sized before increasing backend instances.

## 8. Capacity testing

Production tests must distinguish:
- protected public capacity (including the production rate limiter);
- backend/application capacity;
- database capacity.

A single client IP cannot honestly simulate hundreds of independent users against a per-IP limiter without changing the test topology. Therefore a burst that produces 429 responses is a protection-limit result, not a server-capacity result.

## 9. Important source-of-truth rule

The current implementation should be used when describing the system. Superseded Streamlit-era architecture and product documents are retained under docs/archive/streamlit-era/ and must not be presented as current.
