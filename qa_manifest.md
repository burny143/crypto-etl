# QA Manifest

## Criteria for Inclusion
- Files > 300 lines of code.
- Complex calculations, math, pricing, or financial logic.
- Authentication, authorization, security, or sensitive data handling.
- Complex database queries, migrations, or heavy data transformations.
- API integrations with external services (payments, webhooks, third-party).
- Global state management that affects the entire application.

## Tracked Files
<!-- AI: Automatically add or remove files here. Format: - `file_path` | reason -->
- `crypto-etl/js/charts.js` | 2,134 lines. Charting, signal engine, 8 strategy signal functions (RSI/MACD/BB/EMA/StochRSI/Keltner/ADX combo/Volume combo), paper trading, backtest simulation, global state management (price cache, indicators, signals, positions).
- `crypto-etl/js/research.js` | 803 lines. Research dashboard: multi-pair state management, Supabase queries with pagination, cross-pair aggregation, research generation, sort/pagination.
- `crypto-etl/strategy_research.py` | 1,019 lines. 8 strategy templates with walk-forward validation, combinatorial parameter sweeps (IS/OOS split), indicator computations, Supabase persistence.
- `crypto-etl/backend/paper_trading.py` | 696 lines. Paper trading engine: order placement, position management, P&L calculation, equity curve tracking, portfolio summary. Financial logic.
- `crypto-etl/backend/indicators.py` | 488 lines. Server-side indicator computation (SMA, EMA, RSI, MACD, BB, ADX, ATR, OBV, StochRSI, Keltner) via pandas/numpy, caching layer.
- `crypto-etl/backend/research.py` | 486 lines. AI research endpoints, signal engine integration, pattern recognition, data aggregation across pairs.
- `crypto-etl/bot/backtesting/backtester.py` | 419 lines. Bar-by-bar backtesting engine: trade simulation, risk checks, portfolio management, JSON serialization.
- `crypto-etl/bot/engine/engine.py` | 366 lines. Bot orchestration: main loop with strategy eval → risk → execution → portfolio updates. Error isolation per symbol.
- `crypto-etl/bot/strategies/breakout_hunter.py` | 362 lines. Complex breakout detection: resistance/support, volume confirmation, ATR filtering, false breakout (bull/bear trap) via wick ratio analysis, dynamic leverage calculation.

## Last Updated
<!-- AI: Update this date every time you modify the list above -->
- 2026-07-30 — Initial population. 9 files added.
