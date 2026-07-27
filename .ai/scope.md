# Project Scope

## In Scope

- **Crypto research terminal** — multi-timeframe candlestick charts with technical indicators, signal engine, and AI-style research insights.
- **Paper trading** — simulated long/short trading with virtual $10K cash, live P&L tracking, and order history. No real money.
- **Strategy research engine** — parameter sweeps over transparent, rule-based strategies with walk-forward validation and performance metrics.
- **Data pipeline** — automated OHLCV ETL from CCXT-connected exchanges (OKX primary) to Supabase. Price snapshots every 30 min, historical backfill on schedule.
- **Client-side indicator computation** — all 12+ technical indicators computed in pure JavaScript within `index.html`. No server required for core UI.
- **Signals from strategy results** — chart BUY/SELL markers linked to backtested research strategies.

## Explicitly Out of Scope

- **Live trading or broker execution** — no real exchange API keys, no order routing to live markets. Paper trading only.
- **Machine learning or reinforcement learning** — all strategies are transparent rule-based systems (parameterized EMA crossovers, RSI thresholds, etc.). No black-box models.
- **LangGraph, MCP, agent swarms, or new LLM providers** — the project uses a simple client-side JS pattern. No agent orchestration framework.
- **React or FastAPI development** — the React SPA (`crypto-etl/frontend/`) and FastAPI backend (`crypto-etl/backend/`) are abandoned in favor of the vanilla JS `index.html`.
- **Vibe-Trading code import or alpha libraries** — `vibe-trading/` is read-only reference material. No code, no dependencies, no symlinks.
- **Index.html rewriting** — `index.html` is the primary UI. Incremental modularization may be explored (ADR-0006) but full rewrites are forbidden.
- **Database migrations** — schema changes require a separate migration task with Supabase SQL review.
- **Authentication or multi-user features** — single-user anon-key access pattern. RLS policies are already in place.

## Design Principle

**Fewer, well-executed features over many half-finished ones.** Every UI element must justify its presence in a research workflow. If it does not serve the goal of finding edge, it does not belong.
