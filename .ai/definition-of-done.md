# Definition of Done

A task is **done** only when ALL of the following are true:

## For Code Changes

1. **Smallest safe change** — the change does exactly what was requested, no more, no less. No scope creep, no unrelated refactoring.
2. **Backup created** — the original file was backed up to `crypto-etl/.backups/` before any edit.
3. **Tests pass** — relevant tests, linter, or build step was run and passes. If no test suite exists for the changed code, this is explicitly noted.
4. **No secrets exposed** — git diff reviewed for accidental secrets, tokens, or credentials.
5. **Diff reviewed** — the final diff is reviewed for correctness, completeness, and absence of unintended changes.
6. **PROJECT_STATUS.md updated** — if the change alters the project's capabilities, status, or roadmap items.

## For Documentation Changes

1. **No runtime code modified** — no source files, workflows, dependencies, SQL migrations, or environment files were changed.
2. **No vibe-trading/ files modified** — verified by checking the git diff or file listing.
3. **Links validated** — relative documentation links point to existing files where practical.
4. **No secrets** — documentation does not contain credentials, tokens, or sensitive configuration values.
5. **No contradictory rules** — new governance content is consistent with existing documentation. Conflicts are flagged explicitly with a proposed resolution.
6. **Repository remains runnable** — the exact same commands that worked before the documentation task still work after.

## For All Changes

1. **Scope respected** — the change stays within the boundaries defined in `.ai/scope.md` and `.ai/prohibited-actions.md`.
2. **Data contracts considered** — if the change touches data shape or data flow, the relevant data contract in `crypto-etl/docs/data-contracts/` was read and, if necessary, updated.
3. **ADRs considered** — if the change touches architecture, the relevant ADR in `crypto-etl/docs/decisions/` was read.
