# trading-research — AI Governance Entry Point

This is the monorepo AI-agent governance layer. Before working in this repository,
read the following files in order:

1. **`AGENTS.md`** (root) — overall agent rules and repository authority
2. **`.ai/scope.md`** — what this project does and does not build
3. **`.ai/current-milestone.md`** — active milestone definition and acceptance criteria
4. **`.ai/prohibited-actions.md`** — hard boundaries, never-breach rules
5. **`crypto-etl/AGENTS.md`** — crypto-etl-specific project context, commands, and pitfalls
6. **`crypto-etl/docs/`** — architecture docs, ADRs, and data contracts before modifying relevant code

## Quick Links

| File | Purpose |
|------|---------|
| `crypto-etl/AGENTS.md` | Commands, structure, pitfall for the active product |
| `crypto-etl/docs/architecture/current-data-flow.md` | How data moves through the system today |
| `crypto-etl/docs/architecture/repository-map.md` | File-by-file map of the active product |
| `crypto-etl/docs/decisions/` | Architecture Decision Records |
| `crypto-etl/docs/data-contracts/` | Data contracts (strategy, signal, portfolio, research) |
| `.ai/current-milestone.md` | What we are building right now |
| `ROADMAP.md` | What we plan to build next |

## Repository Authority

- **`crypto-etl/`** is the only active product. All development happens here.
- **`vibe-trading/`** is read-only reference material. Never modify, copy from, or create dependencies to it.
