# College Website Resolver

Admin-only college-level website enrichment. Course family is ignored.

Flow: seed existing reference mappings -> verify candidate URL -> Gemini + Google Search only for unresolved selections -> verify again -> permanently store URL, source, status and timestamps.

Set `GEMINI_API_KEY` only on the admin backend. Optional `GEMINI_RESOLVER_MODEL` defaults to `gemini-2.5-flash`. A resolver request is capped at 25 colleges.
