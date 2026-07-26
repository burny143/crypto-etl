# crypto-etl — Unified Crypto Research + Trading Terminal (Pure JS)

## Critical Rules
- `vibe-trading/` is **READ-ONLY**. Never create, edit, delete, or modify any file inside it.
- You may **read** any file in `vibe-trading/` to understand research logic, prompts, data shapes, or architecture.
- All new code, frontend changes, database changes, and tools go into `crypto-etl/` only.
- Treat `vibe-trading/` as a reference for research ideas only — never copy files from it.

## Project Structure
```
crypto-etl/
├── AGENTS.md                    ← this file
├── agent.md                     ← root-level pointer (project root)
├── index.html                   ← PRIMARY UI (vanilla HTML/JS, Lightweight Charts)
├── strategy_research.py         ← Research engine: 8 strategies, param sweeps, backtest
├── historical_etl.py            ← Historical OHLCV ETL via CCXT (paginated fetch)
├── etl.py                       ← Current price snapshot ETL (30 min schedule)
├── setup.ps1                    ← Supabase setup (keys, env)
├── strategy_results.csv         ← Latest full sweep output (9,437 variants)
├── supabase_migration.sql       ← Original full schema
├── README.md
├── migrations/
│   ├── V2__enhanced_schema.sql   ← paper trading tables + indicators cache
│   ├── V3__research_insert_policy.sql ← anon INSERT on crypto_research
│   ├── V4__paper_trading_rls.sql ← anon INSERT/UPDATE/DELETE on paper tables
│   └── V5__strategy_results.sql  ← research_runs + strategy_results tables
├── .github/workflows/
│   ├── schedule.yml             ← ETL every 30 min
│   ├── historical_etl.yml       ← Daily historical fetch
│   └── research.yml             ← Weekly strategy research (Monday 06:00 UTC)
├── frontend/                    ← REACT SPA (secondary/defunct — not being developed)
├── backend/                     ← Python FastAPI (abandoned — all logic ported to JS)
└── .backups/                    ← Edit backups (gitignored)
```

## Current Project State (as of Jul 2026)

### What's Working
- **`index.html`** is the primary UI — fully functional terminal with:
  - Landing page → Launch Terminal
  - Candlestick chart (Lightweight Charts v5.2.0) with 12+ indicators
  - Pair selector (30 pairs) + timeframe selector (1h/4h/1d)
  - Signal engine (client-side JS) — define conditions, render buy/sell markers
  - AI-style research panel (generates insights from computed indicators)
  - **Paper trading panel** (right sidebar): trade form (qty, long/short), positions list with live P&L (15s refresh), close button, order history, equity header ($10K cash)
  - All indicator computation runs client-side (vanilla JS — no pandas, no server)
- **EVERYTHING in index.html** — no server needed. Just open in browser or serve with `python -m http.server 8080`.

### Data Pipeline
- **`historical_etl.py`**: Fetches OHLCV from OKX via CCXT with pagination. Upserts into `crypto_historical` (symbol, timeframe, datetime unique constraint).
  - Latest run: **227,200 rows** across 30 symbols × 3 timeframes
  - `1d`: 1,095 bars/symbol (3 years) for 26/30 symbols (POL, SEI, STRK have no 1d data)
  - `1h`: 4,320 bars/symbol (180 days) for all 30 symbols
  - `4h`: 1,080 bars/symbol (resampled from 1h) for all 30 symbols
  - Pagination fix applied (was fetching only 100 candles per symbol)
- **`etl.py`**: Current price snapshots every 30 min via GitHub Actions → `crypto_data`
- **Symbols data source**: 30 pairs defined in `supabase_migration.sql` `symbols` table

### Strategy Research Engine
- **`strategy_research.py`**: Standalone Python script (pandas/numpy).
- **8 strategy templates** adapted from `vibe-trading/` research patterns:
  1. RSI Reversion
  2. MACD Crossover
  3. Bollinger Band Reversion
  4. EMA Crossover
  5. StochRSI
  6. Keltner Channel Breakout
  7. RSI + ADX Combo
  8. RSI + Volume Combo
- **Parameter sweeps**: Each strategy tests a grid of parameter combinations (variable count per strategy).
- **Backtesting**: Entry at next open on signal, exit on opposite signal or zero/flat signal.
- **Storage**: Results written to `strategy_results` table in Supabase (grouped by `research_runs.run_id`) and exported to `strategy_results.csv`.
- **Latest sweep**: 9,437 variants across 10 symbols × 2 timeframes (1d, 4h). Full data used.
  - Run ID: `5fb9e8d4`
  - Committed to repo as `strategy_results.csv`
- **Key findings from sweep**:
  - **MACD crossover**: Most consistent (Sharpe 18-25 daily, thousands of trades across all symbols). Real parameter robustness.
  - **StochRSI**: Strong performance (Sharpe 10-15, 500-1000%+ returns daily, moderate DD ~7%).
  - **EMA crossover**: Good in trending markets (Sharpe 5-11, exceptional returns).
  - **KC breakout (wide bands)**: 100% win rate but unreliable (2-11 trades/symbol — statistical noise).
  - **All reversion strategies** (RSI, BB, RSI+vol): Universally negative Sharpe — consistent with sustained 2023-2026 uptrend.
- **Missing from current sweep**: Only 10 of 30 symbols tested. Only 1d + 4h (1h not yet run). No walk-forward validation. Parameter grids are modest.

### Paper Trading
- Manual market orders via UI panel. No auto-trading from research results (yet).
- `placeOrder()` → inserts into `paper_orders` (status='filled') → upserts into `paper_positions` (weighted avg entry on add-to-position).
- `closePosition(id)` → records closing order with realized P&L → deletes position row.
- Equity starts at $10,000 cash. Updates with unrealized P&L. No persistence (resets on page reload).
- Refresh: on chart data load, pair change, and every 15s via `setInterval(refreshTradingUI, 15000)`.
- Requires V4 RLS policies (anon INSERT/UPDATE/DELETE on paper tables).

### Database Schema (Supabase project `ymnlqggxeeyqvrojsrzh`)

**Active tables (queried by index.html):**
- `crypto_historical` — OHLCV bars (unique on symbol, timeframe, datetime). 227,200 rows.
- `crypto_research` — AI research entries (client-side generated insights)
- `crypto_data` — Current price snapshots (from etl.py)
- `paper_orders` — Paper trading orders
- `paper_positions` — Open paper positions
- `paper_equity_curve` — Equity snapshots (wired for writes, not yet populated)
- `research_runs` — Strategy research run tracking (V5 migration)
- `strategy_results` — Per-variant backtest metrics (V5 migration)

**Unused tables**: `indicators`, `etl_metadata`

### Indicator Computation (all in `index.html` JS)
- **12 indicators**: SMA, EMA, RSI, MACD, BB, VWAP, ADX, ATR, OBV, StochRSI, Vol Ratio, Keltner Channels
- **Dispatch**: `INDICATOR_COMPUTERS_JS` maps name → JS function
- **`computeIndicator(name, params)`** — generic entry point
- Signal engine (`runSignal`) and research generation (`generateResearch`) all client-side.

### GitHub Actions Workflows
- `schedule.yml` — Runs `etl.py` every 30 min (price snapshots). Depends on `ccxt`, `supabase`.
- `historical_etl.yml` — Runs `historical_etl.py` daily. Depends on `ccxt`, `supabase`.
- `research.yml` — Runs `strategy_research.py` every Monday 06:00 UTC + manual dispatch. Depends on `pandas`, `numpy`, `supabase`. Uploads CSV artifact.

## How to Run

### Terminal UI (no server needed)
```powershell
cd crypto-etl
python -m http.server 8080
# Open http://localhost:8080
```

### ETL Scripts
```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key from setup.ps1 line 35>"

# Current price snapshot
python etl.py

# Historical data download
python historical_etl.py

# Strategy research sweep
python strategy_research.py
```

## Key Design Decisions
1. **Charting**: TradingView Lightweight Charts canvas-based. Handles large datasets efficiently.
2. **Indicators**: All client-side in vanilla JS (12 types). No server dependency.
3. **Data Loading**: Single query from `crypto_historical` — loads all bars for current symbol/timeframe (not yet paginated).
4. **Research**: Client-side JS generates insights from indicators. Python `strategy_research.py` handles bulk sweeps offline.
5. **Paper Trading**: Client-side JS → Supabase anon key INSERT/UPDATE/DELETE. No backend needed.
6. **Max 3 on chart**: Limit applies to chart overlays only. Indicator catalog should keep growing.
7. **crypto-etl is the truth**: The React frontend/backend are abandoned. All work goes into `index.html`.

## RLS Policies
- `crypto_research`: Public SELECT + anon INSERT (V3)
- `paper_orders`, `paper_positions`, `paper_equity_curve`: Public SELECT + anon INSERT/UPDATE/DELETE (V4)
- `research_runs`, `strategy_results`: Public SELECT, service_role all (V5)

## What's NOT Done (Next Moves)
1. **Widen research sweep**: Run on all 30 symbols + 1h timeframe + wider parameter grids.
2. **Walk-forward validation**: Split data into train/test periods to validate out-of-sample.
3. **Wire research into UI**: Show top strategies per symbol/timeframe, overlay signals on chart, one-click paper trade adoption.
4. **Strategy decay tracking**: Compare live paper trade performance against research predictions.
5. **Portfolio backtester**: Multi-symbol allocation across strategies.
6. **Paginated data loading**: Load bars in pages (500 at a time) for better performance with large datasets.
7. **Persist cash balance**: Store equity curve properly instead of resetting on reload.

## File Editing Rules
- **Backup before every edit.** Copy file to `.backups/` with pattern `{original-path-underscored}.{timestamp}.bak`.
- The `.backups/` directory is gitignored scratch space.

## Notes
- Supabase anon key has SELECT + INSERT RLS on `crypto_research` (V3). Research entries from client-side JS persist.
- Service role key in `setup.ps1` line 35 — never embed in frontend code.
- The Supabase project URL and anon key are in the `setup.ps1` file.
- Vibe-trading strategies were adapted by reading pattern logic and rewriting in Python/JS — no files were copied.
- Always use `git add` + `git commit` for meaningful changes. Push after commits.
