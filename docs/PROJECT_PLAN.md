# CAP_FIND Project Plan

**Status:** Discovery; no application implementation yet  
**Repository:** `samir-deshmukh/CAP_FIND`  
**Current baseline commit:** `d3b59973d13f7ca892968487694865b2606a01b1`

## Purpose

Build a maintainable and reliable Maharashtra CAP college finder from a clean repository while preserving validated product requirements and data semantics from the legacy CETFind project.

## Non-goals for the discovery phase

- Do not copy the entire legacy repository without review.
- Do not deploy or change the existing production service.
- Do not import production data into a development/test environment.
- Do not add paid services or subscriptions.
- Do not optimize PDF processing based on guesswork.
- Do not select frameworks solely because they are familiar or fashionable.

## Phase 0 — Product requirements

Deliverables:
- Define candidate-facing filters, supported course families, years and rounds.
- Define college detail, cutoff history, seat-matrix, and data freshness behavior.
- Define admin roles and the complete import/review/publish workflow.
- Document accessibility, mobile behavior, performance, privacy, and security expectations.
- Identify which legacy behaviors are required, broken, obsolete, or unknown.

Exit criteria: each core user journey has acceptance criteria; assumptions and unknowns are explicit.

## Phase 1 — Legacy evidence and data contract

Deliverables:
- Inventory the legacy repository and deployed architecture separately.
- Trace official source files to extracted, normalized, staged, approved, and published records.
- Document course/program/category mappings, uniqueness rules, and data provenance.
- Create small, sanitized regression fixtures representing known edge cases.
- Establish row reconciliation rules: accepted + rejected/quarantined + unresolved must account for all source records.

Exit criteria: critical business rules are captured in tests or explicit decision records.

## Phase 2 — Architecture and toolchain decision

Evaluate the smallest viable stack against:
- free-tier constraints and deployment limits;
- maintainability and ecosystem maturity;
- security updates and dependency support;
- background processing, durable job state, cancellation and restart recovery;
- bounded memory for large PDFs;
- PostgreSQL integrity and migration safety;
- automated testing and local reproducibility.

Deliverables: architecture diagram, ADRs for consequential choices, threat model, test strategy, and release/rollback plan.

Exit criteria: choices are evidence-based and accepted before runtime code is scaffolded.

## Phase 3 — Foundation

Deliverables:
- reproducible local environment and locked/bounded dependencies;
- configuration validation and secret handling;
- health/readiness checks and structured safe logging;
- CI for linting, type checks where appropriate, unit tests, and security/dependency checks;
- schema migrations and isolated test database setup;
- baseline tests that fail safely when required test services are unavailable.

Exit criteria: a clean checkout can be tested using documented commands without access to production.

## Phase 4 — Thin vertical slices

Implement one end-to-end user journey at a time:
1. Public search with bounded server-side filtering and pagination.
2. College details and verified cutoff/trend results.
3. Secure admin authentication and authorization.
4. Import job creation, durable state and file preflight.
5. Extraction/normalization with provenance and row reconciliation.
6. Validation, staging, review and explicit approval.
7. Transactional publication, verification and scoped rollback.

Each slice requires tests, documentation, a separate logical commit, and a reviewed pull request.

## Phase 5 — Reliability and performance

- Use representative synthetic/sanitized inputs.
- Measure wall time, peak memory, page count, row count, and disk usage.
- Test cancellation, process restart, duplicate retry, corrupt input, timeout, and partial failure.
- Prove no silent data loss and no accidental approval/publication.
- Optimize the measured bottleneck only; retain a baseline to compare.

## Phase 6 — Release readiness

Require:
- reviewed and passing CI;
- data reconciliation and migration/rollback evidence;
- security and dependency review;
- load/resource testing within actual hosting limits;
- monitoring and incident runbook;
- explicit owner approval for deployment and any production data operation.

## Work tracking conventions

- Every non-trivial task is a GitHub Issue with acceptance criteria and risk.
- Use labels such as `type:bug`, `type:feature`, `type:investigation`, `type:docs`, `area:data`, `area:security`, `area:performance`, and `priority:high`.
- Keep one logical change per commit and link commits/PRs to the issue.
- A task is not Done because code was written; it is Done when required checks and acceptance criteria pass.
- If a test could not run, record it as not run, not as passed.
- Record production deployment as a separate release event, not as a side effect of a merge.

## Immediate next steps

1. Capture and verify the product requirements.
2. Inventory legacy code and existing documentation; separate verified facts from assumptions.
3. Establish the data contract and representative fixtures.
4. Compare architecture options against free hosting and resource constraints.
5. Decide the architecture in an ADR.
6. Only then scaffold the application and add CI for its chosen stack.
