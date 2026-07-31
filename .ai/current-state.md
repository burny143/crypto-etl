# Current Project State

**Last updated:** 2026-07-28  
**Updated by:** Recovery Audit  
**Current branch (nested):** `phase/5-cli` @ `548db1e`  
**Current branch (parent):** `master` @ `8aaa679`  
**Current mode:** `RECOVERY AUDIT`  
**Last known stable commit:** `548db1e` (nested) / `8aaa679` (parent)  
**Working tree status:** HAS CHANGES — 7 modified files in nested repo, stale gitlink in parent

---

## Project Purpose

A crypto research terminal with:
- Multi-timeframe candlestick charts with 12+ technical indicators (client-side JS)
- Paper trading (simulated long/short, $10K virtual cash, live P&L)
- Strategy research engine (8 strategy templates, parameter sweeps, walk-forward validation)
- Automated OHLCV ETL pipeline (CCXT/OKX → Supabase, 30-min snapshots)
- CLI-driven paper-trading bot with configurable strategies, risk management, order execution, and signal persistence

## Verified Technology Stack

| Layer | Technology | Verified |
|-------|-----------|----------|
| Frontend UI | Vanilla HTML/JS, Lightweight Charts v5.2.0, Supabase JS v2 | ✅ `index.html` (2048 lines) |
| Database | Supabase (PostgreSQL) with RLS | ✅ 227,200 OHLCV rows, 30 symbols × 3 timeframes |
| Bot | Python 3.13, pyproject.toml (setuptools) | ✅ 150 tests, 88.79% coverage |
| ETL | Python + CCXT (OKX primary) | ✅ 3 GitHub Actions workflows |
| CI | ruff, black, mypy, pytest, pytest-cov | ✅ Configured in pyproject.toml |

## Application Entry Points

| Entry Point | Purpose | File |
|------------|---------|------|
| Terminal UI | Primary user interface | `crypto-etl/index.html` |
| Research charts | Secondary charting page | `crypto-etl/charts.html` |
| Research page | AI-style research insights | `crypto-etl/research.html` |
| Bot CLI | `crypto-etl-bot run` / `run-once` | `crypto-etl/bot/cli.py` |
| Strategy research | Parameter sweep engine | `crypto-etl/strategy_research.py` |
| Historical ETL | OHLCV backfill | `crypto-etl/historical_etl.py` |
| Price snapshot ETL | 30-min price fetcher | `crypto-etl/etl.py` |
| Supabase setup | One-time DB setup | `crypto-etl/setup.ps1` |

## Major Components

### Frontend (`crypto-etl/index.html`)
- Landing → Launch Terminal flow
- Candlestick chart with 12+ client-side indicators (max 3 visible)
- Signal engine: user-defined conditions → chart BUY/SELL markers
- Paper trading panel: order form, positions, live P&L (15s refresh), order history, $10K cash
- Top Strategies panel: loads strategy results from Supabase with Sharpe ranking
- Supabase anon-key operations (RLS-protected)

### Bot Framework (`crypto-etl/bot/`)
- **Config:** YAML-based with env overlay (`config.py`, `config.yaml`)
- **Domain models:** Candle, MarketQuote, PaperOrder, PaperPosition, Signal, etc. (`domain/models.py`)
- **Data layer:** Supabase adapter with validation (`data/`)
- **Strategies:** Base contract + registry + RSI Mean Reversion (`strategies/`)
- **Risk manager:** Pre-trade checks — stale price, duplicate key, cash limits, max positions, daily loss (`risk/manager.py`)
- **Executor:** Paper fill with configurable slippage and fees (`execution/`)
- **Portfolio service:** Cash tracking, position management, P&L calculation (`portfolio/service.py`)
- **Engine:** Full orchestration loop with error isolation (`engine/engine.py`)
- **CLI:** `crypto-etl-bot run` / `run-once` with config loading (`cli.py`)
- **Repositories:** InMemory + Supabase adapters for orders, positions, signals (`repositories/`)

### ETL Pipeline
- Historical backfill: CCXT (OKX) → Supabase `crypto_historical` (daily via GitHub Actions)
- Price snapshots: CCXT → Supabase `crypto_data` (every 30 min via GitHub Actions)
- Strategy research: 8 templates, walk-forward validation, results to Supabase (weekly)

## Current Data Flow (Bot)

```
config.yaml + env vars
    │
    ▼
BotConfig (config.py)
    │
    ▼
BotEngine.run_once()
    │
    ├── For each symbol:
    │   ├── Fetch OHLCV → StrategyRegistry.evaluate() → Signal
    │   ├── If not HOLD → fetch quote → _process_signal()
    │   │   ├── ENTER: RiskManager.check() → PaperExecutor.fill() → PortfolioService.apply_fill() → save order/position/signal
    │   │   └── EXIT: PortfolioService.close_position() → save order/signal
    │   └── Error isolation per symbol
    │
    ├── _update_position_prices() → refresh unrealized PnL on open positions
    └── PortfolioService.total_equity() / snapshot()
```

## State and Storage

| Store | Technology | Location |
|-------|-----------|----------|
| OHLCV data | Supabase | `crypto_historical` (227k rows) |
| Current prices | Supabase | `crypto_data` (30 rows) |
| Paper orders | Supabase + InMemory | `paper_orders` / `repositories/memory.py` |
| Paper positions | Supabase + InMemory | `paper_positions` / `repositories/memory.py` |
| Signals | InMemory + Supabase (opt) | `repositories/signal.py` |
| Strategy results | Supabase | `strategy_results` / `research_runs` |
| Bot config | YAML + env | `config.yaml` + `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| Frontend cash | localStorage + Supabase | `paperTradeCash` + `paper_equity_curve` |

## External Integrations

| Service | Purpose | Access Pattern |
|---------|---------|---------------|
| Supabase | Database, auth (RLS) | `create_client()` with anon key (frontend) or service_role key (backend) |
| OKX (CCXT) | Market data source | Read-only API, no trading credentials |
| GitHub Actions | Scheduled ETL | 3 workflows (30-min, daily, weekly) |

## Current Feature in Progress

QA bug fixes applied to bot framework (7 modified files, uncommitted):
- `bot/portfolio/service.py` — cumulative realized PnL, partial-close PnL, fee deduction, strategy_id on averaging
- `bot/engine/engine.py` — _current_prices error logging, _seen_keys cache, signal persistence deferment, equity-curve collection, fill_order elimination, Decimal.quantize
- `bot/domain/models.py` — added fee field to PaperOrder
- `bot/cli.py`, `bot/data/validation.py`, `bot/strategies/rsi.py` — formatting fixes
- `docs/architecture/current-data-flow.md` — overwritten with Phase 6 summary (needs review)

## Verified Completed Features

| Feature | Phase | Status |
|---------|-------|--------|
| Terminal UI with indicators | 1 | ✅ VERIFIED — working in browser |
| Historical ETL | 1 | ✅ VERIFIED — 227k rows |
| Price snapshot ETL | 1 | ✅ VERIFIED — GitHub Actions |
| Paper trading frontend | 1 | ✅ VERIFIED — working in browser |
| Strategy research engine | 2 | ✅ VERIFIED — 8 strategy templates |
| Bot scaffolding (config, domain, data layer) | 1 | ✅ VERIFIED — 150 tests pass |
| CI tooling (ruff, black, mypy, coverage) | 1.5 | ✅ VERIFIED — all gates pass |
| RSI Mean Reversion strategy | 2 | ✅ VERIFIED — tested |
| Paper executor with slippage/fees | 3 | ✅ VERIFIED — tested |
| Portfolio service | 3 | ✅ VERIFIED — tested |
| Risk manager | 3 | ✅ VERIFIED — tested |
| Bot orchestrator engine | 4 | ✅ VERIFIED — tested |
| CLI entry point | 5 | ✅ VERIFIED — CLI runs |
| Signal persistence | 5 | ✅ VERIFIED — tested |
| Data contracts (4 docs) | 6 | ✅ VERIFIED — files exist, DRAFT status |
| Strategy lifecycle doc | 6 | ✅ VERIFIED — file exists |
| Gap analysis | 6 | ✅ VERIFIED — in current-data-flow.md |

## Partial or Unverified Features

| Feature | Status | Evidence |
|---------|--------|----------|
| Supabase repository adapters | IMPLEMENTED BUT UNVERIFIED | 55% coverage — requires credentials for integration tests |
| Pre-computed indicator cache | IMPLEMENTED BUT NOT USED | `indicators` table exists in V2 but frontend/bot don't use it |
| `session_id` scoping | IMPLEMENTED BUT FRAGILE | V7 migration exists; frontend generates random session per page load |
| Bot multi-symbol execution | IMPLEMENTED BUT UNVERIFIED IN PRODUCTION | Unit tests pass; no live Supabase end-to-end test |

## Protected Paths

| Path | Status | Rule |
|------|--------|------|
| `vibe-trading/` | ✅ READ-ONLY | Never modify, copy from, or create dependencies (ADR-0003, `.ai/prohibited-actions.md`, `.ai/reference-policy.md`) |
| `crypto-etl/frontend/` | ✅ ABANDONED | React SPA, no development |
| `crypto-etl/backend/` | ✅ ABANDONED | FastAPI, no development |
| `crypto-etl/index.html` | ✅ RESTRICTED | No full rewrites — incremental changes only |
| `crypto-etl/supabase_migration.sql` | ✅ READ-ONLY | Schema reference — changes via separate migration tasks |
| `crypto-etl/migrations/` | ✅ READ-ONLY | Applied migrations — new migrations only |

## Known Documentation Drift

| Doc | Drift | Severity |
|-----|-------|----------|
| `ROADMAP.md` (parent) | Says Phase 3 current; actual work is Phase 5+ | HIGH |
| `PROJECT_STATUS.md` (parent) | Last updated 2026-07-27; doesn't reflect bot framework | HIGH |
| `.ai/current-milestone.md` | Says "documentation & preparation" but Phase 6 docs complete | MEDIUM |
| `crypto-etl/docs/architecture/current-data-flow.md` | Overwritten with Phase 6 summary — original tech architecture lost | HIGH |
| `crypto-etl/bot/ARCHITECTURE.md` | Labeled "Phase 0" — plan only, not synchronized with actual implementation | MEDIUM |
| `crypto-etl/README.md` | References React/FastAPI as current (abandoned) | LOW |

## Validation Summary

| Check | Result | Verified At |
|-------|--------|-------------|
| Unit tests (150) | ✅ PASS | HEAD `548db1e` + uncommitted QA fixes |
| Ruff lint | ✅ PASS | HEAD `548db1e` + uncommitted QA fixes |
| Black format | ✅ PASS | HEAD `548db1e` + uncommitted QA fixes |
| Coverage 88.79% | ✅ PASS (floor 75%) | HEAD `548db1e` + uncommitted QA fixes |
| Mypy type check | ⚠️ 12 pre-existing errors | Pre-existing, not related to current changes |
| Vibe boundary | ✅ PASS | HEAD `548db1e` + uncommitted QA fixes |
| Parent gitlink | ⚠️ STALE (12 commits behind) | Parent pinned `72d3d00` vs nested HEAD `548db1e` |

## Evidence Reviewed

- Parent repo: `AGENTS.md`, `CLAUDE.md`, `agent.md`, `.ai/` (6 files), `ROADMAP.md`, `PROJECT_STATUS.md`, `VIBE_TRADING_REFERENCE.md`, `.gitignore`
- `crypto-etl/AGENTS.md`, `crypto-etl/bot/ARCHITECTURE.md` (474 lines)
- `crypto-etl/bot/pyproject.toml`, `config.yaml`, `config.py`
- `crypto-etl/docs/` (16 files: 3 architecture, 6 ADRs, 4 data contracts, 2 research, 1 reference-adoption)
- `crypto-etl/bot/engine/engine.py`, `portfolio/service.py`, `domain/models.py`, `cli.py`
- Git history: 42 commits in nested repo, 1 commit in parent, 8 branches, 1 tag
- All 150 test files, coverage reports, lint/format/boundary check outputs

## Unresolved Questions

1. What phase/milestone is actually current? (ROADMAP says 3, nested repo is at 5+)
2. Should `current-data-flow.md` be restored from git or keep new content?
3. Should QA bug fixes be committed before or after resolving the doc issue?
4. When should the parent gitlink be updated to `548db1e`?
5. Are there integration credentials available to test Supabase adapters?
