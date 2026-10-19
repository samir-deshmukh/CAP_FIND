## Summary

Describe the single logical change and why it is needed.

## Related issue

Closes #

## Scope

- [ ] This PR addresses one coherent change.
- [ ] Unrelated refactoring and formatting are excluded.
- [ ] Documentation is updated where behavior or operations changed.

## Evidence and design

- Current behavior / failure evidence:
- Root cause or hypothesis:
- Alternatives considered:
- Why this change is safe:

## Data integrity and security

- [ ] No production database or production data was used for testing.
- [ ] No secrets, credentials, raw source PDFs, or generated master datasets are included.
- [ ] Source provenance and row reconciliation are preserved where applicable.
- [ ] Import staging/review/approval boundaries are preserved.
- [ ] Authorization, input validation, and privacy protections are preserved.
- [ ] Migration and rollback behavior is documented where applicable.

## Verification

List exact commands and observed outcomes. Do not mark a check as passed unless it was run.

- [ ] Focused regression tests
- [ ] Relevant broader test suite
- [ ] Lint/type/static checks (if configured)
- [ ] Build or migration validation (if applicable)
- [ ] Resource/performance measurements (if relevant)

Results:
- Commands:
- Outcome:
- Checks not run and why:

## Risk and recovery

- Remaining risks:
- Rollback/recovery steps:
- Production impact: none / describe (production changes require separate approval)

## Review checklist

- [ ] Diff inspected; only intended files changed.
- [ ] Comments explain non-obvious invariants/guards/resource bounds, not obvious syntax.
- [ ] Commit messages are descriptive and commits are logically scoped.
- [ ] No deployment is implied by merge.
