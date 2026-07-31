---
description: Run a complete alignment guardian review
agent: general
---

Perform a complete alignment review using the instructions in `.opencode/agents/alignment-guardian.md`.

Read the current sources of truth:

1. `AGENTS.md` (root and `crypto-etl/`)
2. `.ai/current-milestone.md`
3. `.ai/scope.md`
4. `.ai/prohibited-actions.md`
5. `.ai/financial-safety.md`
6. `docs/data-contracts/` (all files)
7. `bot/ARCHITECTURE.md`

Inspect the current repository state:
- Current branch and phase
- All uncommitted changes (staged, unstaged, untracked)
- The nested crypto-etl repo git status
- The vibe-trading/ forbidden boundary

Return a complete Alignment Guardian Report with Verdict, Findings, and Continuation Decision.

Do not modify any files. Do not run destructive commands. Do not expose credentials.
