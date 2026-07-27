# Project Status

*Last updated: 2026-07-27*

## Overall State

**Phase:** 3 — Research-to-Chart Traceability (documentation & preparation)

## Working Features

### Data Pipeline
- ✅ Historical OHLCV ETL: CCXT → Supabase `crypto_historical` (227,200 rows, 30 symbols × 3 timeframes)
- ✅ Price snapshot ETL: GitHub Actions every 30 min → Supabase `crypto_data`
- ✅ Strategy research: 8 strategies, 9,437 variants, walk-forward validated
- ✅ GitHub Actions CI/CD for all pipelines

### Frontend (`index.html`)
- ✅ Landing page → Launch Terminal flow
- ✅ Candlestick chart (Lightweight Charts v5.2.0)
- ✅ 12+ technical indicators (client-side JS, max 3 visible)
- ✅ Symbol selector (30 pairs) + timeframe selector (1h/4h/1d)
- ✅ Signal engine (user-defined conditions → chart BUY/SELL markers)
- ✅ AI-style research panel
- ✅ Paper trading panel (order form, positions, live P&L, order history, $10K cash)
- ✅ Top Strategies panel (loads strategy results from Supabase)

### Database (Supabase)
- ✅ `crypto_historical` — OHLCV bars
- ✅ `crypto_data` — Current prices
- ✅ `crypto_research` — AI research entries
- ✅ `paper_orders` / `paper_positions` / `paper_equity_curve` — Paper trading
- ✅ `strategy_results` / `research_runs` — Strategy research
- ✅ RLS policies for anon key access on all client-facing tables

## Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| Paper trading cash resets on page reload | Unresolved | No persistence to equity curve |
| Strategy results → chart markers traceability gap | Unresolved | No signal_id linking research to chart markers |
| Duplicated strategy/indicator logic in Python vs JS | Documented | Not changed — intentional for independence |
| Frontend (React) abandoned | Permanent | All features ported to index.html |
| Backend (FastAPI) abandoned | Permanent | All logic ported to client-side JS |
| No paginated data loading | Unresolved | All bars loaded at once |
| No walk-forward validation in UI | Unresolved | Currently only shows OOS/IS labels |

## Current Milestone

**Research-to-Chart Vertical Slice** — see `.ai/current-milestone.md` for details.

Status: Preparing documentation and data contracts. No runtime code changes in this phase.

## Recent Changes

- **2026-07-27**: Bug fixes — removed duplicate boot-time strategy load, fixed alt-timeframe fallback filtering, fixed position netting quantity sizing, fixed cost basis on partial reduction, replaced floating-point equality with epsilon comparison
- **2026-07-27**: Governance documentation layer established — AGENTS.md, CLAUDE.md, PROJECT_STATUS.md, ROADMAP.md, .ai/ directory, crypto-etl/docs/ directory
- **2026-07-26**: VIBE_TRADING_REFERENCE.md created — reference summary of vibe-trading patterns
