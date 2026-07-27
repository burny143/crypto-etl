# Monorepo Agent Instructions

## Repository Authority

- **`crypto-etl/`** is the only active product. All development happens here.
- **`vibe-trading/`** is read-only reference material. Never modify, copy from, or create dependencies to it.
- **`.ai/current-milestone.md`** is the primary anti-drift control — read it before starting any work.
- Before modifying code, read the relevant **data contract** in `crypto-etl/docs/data-contracts/` and **ADR** in `crypto-etl/docs/decisions/`.
- The complete project context lives in `crypto-etl/AGENTS.md` — read that for commands, structure, and pitfalls.

## Critical Rules

- `vibe-trading/` is **READ-ONLY**. Never create, edit, delete, or modify any file inside it.
- You may **read** any file in `vibe-trading/` to understand research logic, prompts, data shapes, or architecture.
- All new code, frontend changes, database changes, and tools go into `crypto-etl/` only.
- Treat `vibe-trading/` as a reference for research ideas only — never copy files from it.
- **Backup before every edit.** Copy file to `crypto-etl/.backups/` with pattern `{path-underscored}.{timestamp}.bak`.

## Project State

- `crypto-etl/index.html` is the primary UI (vanilla HTML/JS, Lightweight Charts). The React frontend (`crypto-etl/frontend/`) and Python backend (`crypto-etl/backend/`) are abandoned.
- Supabase project `ymnlqggxeeyqvrojsrzh` — 227,200 OHLCV rows, 30 symbols × 3 timeframes.
- Strategy research engine (`crypto-etl/strategy_research.py`) — 8 strategies, 9,437 variants tested.
- Paper trading panel live in `index.html` (right sidebar).

## How to Run

```powershell
cd crypto-etl
python -m http.server 8080    # Open http://localhost:8080
```

## Design Principle

**Fewer, well-executed features over many half-finished ones.** Every UI element must justify its presence in a research workflow. If it doesn't serve the goal of finding edge, it doesn't belong.

## Common Pitfalls

- Don't modify `vibe-trading/` for any reason — read-only
- Don't add features that don't serve the research workflow
- Always read `crypto-etl/AGENTS.md` first when starting fresh
- Don't confuse "max 3 visible on chart" with limiting the indicator catalog — add as many indicator types as useful
- Never embed service_role key in frontend code
- Never hardcode Supabase URLs/keys in production code

## Mandatory Workflow

1. Read `.ai/current-milestone.md` for active milestone context
2. Read `crypto-etl/AGENTS.md` for project-specific commands/data-flow
3. Read relevant data contract(s) in `crypto-etl/docs/data-contracts/`
4. Read relevant ADR(s) in `crypto-etl/docs/decisions/`
5. Make the smallest safe change
6. Backup before every edit
7. Run tests or explicitly note absence
8. Review final diff for secrets/scope drift
9. Update `PROJECT_STATUS.md` if capabilities changed

## Detailed Rules

Detailed governance rules live in:
- `.ai/scope.md` — project boundaries
- `.ai/prohibited-actions.md` — hard never-breach rules
- `.ai/financial-safety.md` — credential and financial integrity rules
- `.ai/reference-policy.md` — vibe-trading reference usage policy
- `.ai/definition-of-done.md` — completion criteria
- `crypto-etl/docs/` — architecture, ADRs, data contracts, research methodology
