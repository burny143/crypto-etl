# Agent Instructions

## Critical Rules
- `vibe-trading/` is **READ-ONLY**. Never create, edit, delete, or modify any file inside it.
- You may **read** any file in `vibe-trading/` to understand research logic, prompts, data shapes, or architecture.
- All new code, frontend changes, database changes, and tools go into `crypto-etl/` only.
- Treat `vibe-trading/` as a reference for research ideas only — never copy files from it.

## Project State
- **For full up-to-date context**, read `crypto-etl/AGENTS.md` — that's the source of truth.
- `crypto-etl/index.html` is the primary UI (vanilla HTML/JS, Lightweight Charts). The React frontend in `crypto-etl/frontend/` and Python backend in `crypto-etl/backend/` are abandoned.
- Supabase project `ymnlqggxeeyqvrojsrzh` — 227,200 OHLCV rows, 30 symbols × 3 timeframes.
- Strategy research engine (`crypto-etl/strategy_research.py`) — 8 strategies, 9,437 variants tested.
- Paper trading panel live in `index.html` (right sidebar).

## Design Principle
**Fewer, well-executed features over many half-finished ones.** Every UI element must justify its presence in a research workflow. If it doesn't serve the goal of finding edge, it doesn't belong.

## How to Run
```powershell
cd crypto-etl
python -m http.server 8080    # Open http://localhost:8080
```

## File Editing Rules
- **Backup before every edit.** Copy file to `crypto-etl/.backups/` with pattern `{path-underscored}.{timestamp}.bak`.
- The `.backups/` directory is gitignored scratch space.

## Common Pitfalls
- Don't modify `vibe-trading/` for any reason — read-only
- Don't add features that don't serve the research workflow
- Always read `crypto-etl/AGENTS.md` first when starting fresh
- Don't confuse "max 3 visible on chart" with limiting the indicator catalog — add as many indicator types as useful