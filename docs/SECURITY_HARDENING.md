# Security hardening

## Authentication and sessions
- Login performs a dummy password-hash verification for unknown usernames to reduce timing-based username enumeration.
- Login attempts are throttled by source address without locking the target account, avoiding attacker-triggered account lockout. The in-process login limiter prunes expired keys and caps its key count to bound memory under high-cardinality traffic; it is still per worker/instance and is not a distributed control.
- Production admin session cookies use Secure, HttpOnly, and SameSite=Strict by default.
- Sessions are checked against the current database user's active state, role, and authentication version.
- Disabled users and changed roles invalidate existing sessions.
- /admin/logout clears session and CSRF cookies.

## Request provenance and rate limiting
- Rate-limit keys use the direct peer address unless CET_TRUSTED_PROXY_IPS explicitly lists trusted reverse-proxy IPs/CIDRs.
- For configured trusted proxies, the helper uses the rightmost valid X-Forwarded-For address, assuming the trusted proxy appends the observed client IP. Never trust arbitrary client-supplied forwarding headers.
- Public API and login in-process limits prune expired entries and cap key counts to bound memory under high-cardinality traffic. Eviction may weaken throttling for an evicted key; these limits remain per worker/instance, and multi-instance deployments need a shared rate-limit store.

## API documentation
- FastAPI Swagger, ReDoc, and OpenAPI routes are disabled.

## CSRF
- State-changing admin endpoints require a CSRF token.
- Login uses a synchronizer-style token delivered in the login form and CSRF cookie.
- Admin JavaScript sends CSRF tokens for state-changing operations.

## Upload and processing safety
- Failed uploads clean up temporary and renamed PDF files.
- Import processing atomically claims a review-required job before processing to prevent duplicate work.
- Client-facing processing/publishing failures do not expose raw internal exception details.

## Admin website resolver / SSRF mitigation
- Website URLs must use HTTP(S), contain no embedded credentials/control characters, and must not target localhost, local/internal suffixes, or non-global IP literals.
- DNS results are checked and requests to hostnames resolving to non-public addresses are rejected.
- Automatic redirects are disabled for URL verification so a public URL cannot redirect the checker to a private target.
- DNS validation and connection are separate operations; production-grade protection against DNS rebinding should use a network-level egress policy that blocks private, loopback, link-local, and metadata-service ranges.

## Remaining security work
- Add administrator two-factor authentication (TOTP or WebAuthn) with recovery and enrollment flows before treating MFA as implemented.
- Consider a shared rate-limit store if the API scales beyond one worker/instance.
- Re-run a complete dependency vulnerability audit after dependency resolution and test the deployed build.

## Deployment notes
- Set CET_ADMIN_SESSION_SECRET to a long random secret in production.
- Keep CET_ENV=production and do not disable CET_ADMIN_COOKIE_SECURE in production.
- Configure CET_TRUSTED_PROXY_IPS only after confirming the actual trusted proxy addresses and forwarded-header behavior for the hosting platform.
- Create the first real administrator after deployment; never ship administrator credentials in source/data artifacts.
- Validate the complete admin workflow against the target PostgreSQL schema before enabling it as the runtime database.
