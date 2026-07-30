# Current Milestone: Phase 4 — Bot Backtesting

**Status:** Active development — backtesting engine, CLI command, and chart integration complete.

## Context

The "Bot Hardening & Contract Alignment" milestone is complete (all findings resolved, guardian ALIGNED). Phase 4 backtesting has been implemented:

- `bot/backtesting/backtester.py` — Bar-by-bar engine reusing the bot's strategies, risk, executor, and portfolio
- `bot/backtesting/metrics.py` — Sharpe, drawdown, win rate, profit factor (pure Python, no pandas)
- CLI: `python -m bot.cli backtest --symbol BTC-USDT --timeframe 1h --strategy rsi_reversion`
- Chart integration: Load backtest JSON via "Backtest Results" panel → trade markers + metrics display
- 18 new tests (189 total), 95% backtesting coverage

## Scope

### Done

1. Backtest engine (`BacktestEngine.run()`) — walks historical candles, evaluates strategies, simulates fills
2. Metrics computation — Sharpe, max drawdown, win rate, profit factor, avg holding, avg trade P&L
3. CLI subcommand — `python -m bot.cli backtest` with symbol, timeframe, strategy, date range, JSON output
4. Stale price fix — `MarketQuote.is_live=False` bypasses staleness check in risk manager (needed for backtesting)
5. Chart integration — "Backtest Results" panel in right sidebar, trade markers on chart, metrics grid

### Not Doing

- Walk-forward validation (handled by `strategy_research.py`)
- Parameter optimization (handled by `strategy_research.py`)
- Multi-symbol portfolio backtesting (future phase)
- Supabase persistence of backtest results (local JSON output first)

## How to Use

### CLI
```powershell
cd crypto-etl/bot
# Set Supabase credentials
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"

# Run backtest with RSI strategy
python -m bot.cli backtest --symbol BTC-USDT --timeframe 1h --strategy rsi_reversion --output results.json

# With date range
python -m bot.cli backtest --symbol BTC-USDT --timeframe 1d --strategy breakout_hunter --from 2025-01-01 --to 2025-06-01
```

### Chart UI
1. Open `charts.html`
2. Scroll to "Backtest Results" panel in right sidebar
3. Click "Load" and select the `results.json` file
4. Trade markers render on the chart (green arrows for entries, red/green for exits)
5. Metrics grid shows return, Sharpe, drawdown, win rate
