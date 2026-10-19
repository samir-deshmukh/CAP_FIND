# CAP_FIND

CAP_FIND is the clean rebuild of CETFind: a Maharashtra CAP college-data finder designed around trustworthy source data, auditable imports, and reliable candidate search.

## Project status

**Phase:** Requirements and architecture discovery  
**Release status:** Not production-ready  
**Implementation status:** Not started in this repository

This repository is intentionally being established with engineering controls before application code is added. Do not treat the existing CETFind deployment as a test environment or assume that every legacy behavior is correct.

## Product goals

- Help candidates explore Maharashtra CAP cutoff and seat-matrix information by supported course, year, round, college, category, and other verified filters.
- Preserve source provenance and make imported data auditable.
- Separate extraction, validation, staging, review, approval, and publication.
- Keep public queries bounded and avoid sending the entire master dataset to the browser.
- Remain compatible with a no-paid-add-ons budget unless the owner explicitly approves a cost.

## Engineering principles

1. **Evidence before implementation:** document verified behavior and label assumptions.
2. **One logical change per commit:** small diffs, focused tests, descriptive commit messages.
3. **Data integrity over speed:** never silently drop, fabricate, or merge incompatible records.
4. **Safe boundaries:** tests use synthetic fixtures or a dedicated test database, never production.
5. **Measured performance:** profile realistic inputs before optimizing large PDF processing.
6. **Security by default:** secrets stay out of Git; admin and import artifacts are not public.
7. **Reproducibility:** setup, tests, builds, migrations, and release steps must be documented.
8. **No silent release:** a source commit does not authorize a production deployment or production-data mutation.

## How work is tracked

- **GitHub Issues:** one issue per bug, feature, investigation, or technical-debt item. Include evidence, acceptance criteria, and risk.
- **GitHub Projects:** prioritized backlog and status tracking (Backlog → Ready → In progress → In review → Done).
- **Pull requests:** reviewable changes with scope, tests, risks, and rollback notes.
- **Architecture Decision Records (ADRs):** durable reasons for important technical choices and alternatives rejected.
- **Automated CI:** run the same repeatable checks on each pull request before merge.
- **Engineering docs:** architecture, data lineage, import state machine, test strategy, operations, and change log.
- **Commit history:** each commit should represent one coherent, validated change.

## Expected repository layout

```text
CAP_FIND/
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── DATA_LINEAGE.md
│   ├── IMPORT_STATE_MACHINE.md
│   ├── TESTING.md
│   ├── OPERATIONS_RUNBOOK.md
│   ├── DECISIONS.md
│   └── CHANGELOG_ENGINEERING.md
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
└── application code (added only after stack and requirements are verified)
```

This is a target layout, not a claim that the application has already been implemented.

## Current rule

Before choosing frameworks or creating runtime code, record requirements and constraints, compare implementation options, decide the architecture, and establish a safe test strategy. Do not copy legacy code blindly; preserve verified business rules and add regression fixtures for them.
