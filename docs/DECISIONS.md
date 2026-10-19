# Architecture Decision Records (ADR) Index

Use this file as an index. Each consequential decision should be recorded in a separate `ADR-NNN-short-title.md` document with context, constraints, options considered, decision, evidence, consequences, and revisit criteria.

## Decision log

| ID | Decision | Status | Evidence / revisit trigger |
|---|---|---|---|
| ADR-000 | Establish project tracking before implementation | Accepted | Repository is new and application requirements/stack are not yet verified. Revisit after Phase 0 requirements are complete. |

## ADR-000 — Establish project tracking before implementation

**Status:** Accepted  
**Date:** 2026-10-20

### Context

CAP_FIND is a new repository intended to rebuild CETFind. The legacy project has a running application, data rules, production constraints, and prior operational failures. Copying code before mapping requirements and data invariants risks carrying forward defects or losing important behavior.

### Options considered

1. Copy the legacy project wholesale and repair it afterward.
2. Start writing a new app immediately with a preferred framework.
3. Establish requirements, data contracts, test strategy, and engineering controls first; then build verified vertical slices.

### Decision

Choose option 3. Create the project plan, review template, and structured issue intake before application code. Do not lock the stack until requirements and free-tier constraints have been evaluated.

### Consequences

- Initial progress is documentation and engineering workflow rather than visible application features.
- Each implementation choice will have a traceable rationale.
- The team must avoid using documentation as a substitute for tests or working software.
- The plan should be revised if verified requirements show a simpler, safer approach.

### Revisit when

Phase 0 requirements and Phase 1 data-contract discovery are complete.
