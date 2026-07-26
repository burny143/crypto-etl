# crypto-etl — Unified Crypto Research + Trading Frontend (Pure JS)

## Critical Rules
- `vibe-trading/` is **READ-ONLY**. Never create, edit, delete, or modify any file inside that folder.
- All new code, frontend, database changes, schema improvements, paper-trading logic, and integrations go into `crypto-etl/` only.

## Project Structure
```
crypto-etl/
├── AGENTS.md              ← this file
├── frontend/              ← React + Vite + TypeScript SPA (secondary/defunct)
├── backend/               ← Python FastAPI service (abandoned — all logic ported to JS)
├── migrations/            ← SQL schema migrations
├── etl.py                 ← Current price snapshot ETL (existing)
├── historical_etl.py      ← Historical OHLCV ETL (existing)
├── index.html             ← **Primary UI** (vanilla HTML/JS, all-in-one)
├── setup.ps1              ← Supabase setup script (existing)
├── supabase_migration.sql ← Original migration (existing)
├── .backups/              ← Edit backups (gitignored)
└── README.md              ← Project documentation
```

## Database Schema (Supabase on project ymnlqggxeeyqvrojsrzh)

### Tables used by index.html:
- `crypto_historical` — OHLCV bars (symbol, timeframe, datetime, open, high, low, close, volume). Data source for chart + all indicator computation.
- `crypto_research` — AI research entries (id PK, symbol, report_type, title, summary, details JSONB, sentiment, confidence, source, created_at). Written by client-side JS after local analysis.
- `crypto_data` — Current price snapshots (etl.py populates this).
- `paper_orders` — Paper trading orders. Written by client-side JS on trade/close.
- `paper_positions` — Open positions. Upsert on trade, delete on close.
- `paper_equity_curve` — Equity snapshots (wired for writes, not yet populated from frontend).

### Unused tables (from old migration, not currently queried):
- `indicators`, `etl_metadata`

## Paper Trading (Live)
- Paper trading panel added to right sidebar below AI Insights.
- **Trade form**: quantity input + long/short select + "Trade" button. Market orders fill instantly.
- **Positions list**: shows open positions with entry price, live P&L (updated via `refreshTradingUI` every 15s), and "Close" button.
- **Order history**: last 10 orders displayed below positions.
- **Equity**: starts at $10,000 cash. Displayed next to "Paper Trading" header. Updates with unrealized P&L.
- **Flow**: `placeOrder()` → inserts into `paper_orders` (status='filled') → upserts into `paper_positions` (weighted avg entry). `closePosition(id)` → records closing order with realized P&L → deletes position.
- **Refresh**: trading UI refreshes on chart data load, pair change, and every 15s via `setInterval`.
- Requires V4 RLS policies (anon INSERT/UPDATE/DELETE on `paper_orders`, `paper_positions`, `paper_equity_curve`) to be applied. See `migrations/V2__enhanced_schema.sql` + `migrations/V4__paper_trading_rls.sql`.

## How to Run

### Primary (index.html — no server needed)
```powershell
# Just open the file in a browser, or serve with any static file server:
cd crypto-etl
python -m http.server 8080
# Then open http://localhost:8080 in a browser
```
All data loads from Supabase via anon key. All indicators compute client-side in JS. No backend needed.

### ETL Scripts (populate Supabase with data first)
```powershell
# Current price snapshot
cd crypto-etl
python etl.py

# Historical data download (10+ minutes for full backfill)
python historical_etl.py
```

## Indicator Computation (all client-side JS in index.html)
- **12 indicators**: SMA, EMA, RSI, MACD, BB, VWAP, ADX, ATR, OBV, StochRSI, Vol Ratio, Keltner Channels
- **Dispatch**: `INDICATOR_COMPUTERS_JS` maps indicator name → JS function
- **`computeIndicator(name, params)`** — generic entry point, calls the right function
- Signal engine (`runSignal`) and research generation (`generateResearch`) also run client-side — no server calls.

## Design Principle
**Fewer, well-executed features over many half-finished ones.** Every UI element must justify its presence in a research workflow. If it doesn't serve the goal of finding edge, it doesn't belong.

## UI Rules
- **Landing page first** — clean intro with app explanation and "Launch Terminal" button.
- **Chart is the hero** — occupies 60-75% of the screen. Right panel (research + trading) is secondary and collapsible.
- **Max 3 indicators visible on chart at once**, but support as many indicator types in the system as possible (research goal).
- Dark theme, consistent spacing, loading/empty/error states handled everywhere.

## Key Design Decisions
1. **Charting**: TradingView Lightweight Charts — canvas-based, handles large datasets efficiently.
2. **Indicators**: All computed client-side in vanilla JS (no pandas, no numpy, no server). The 12 indicators cover SMA, EMA, RSI, MACD, BB, VWAP, ADX, ATR, OBV, StochRSI, Vol Ratio, Keltner Channels.
3. **Data Loading**: Single query from `crypto_historical` via Supabase JS client (anon key). Not yet paginated — loads all available bars for current symbol/timeframe.
4. **Research Generation**: Client-side JS computes indicators → determines sentiment/confidence → builds structured insight → attempts INSERT to `crypto_research` (may need RLS policy for anon INSERT).
5. **Signal Engine**: Client-side JS — define conditions (indicator + operator + threshold), evaluate against loaded OHLCV data, render buy/sell markers on chart.
6. **Paper Trading**: Implemented client-side in JS. Market orders insert into `paper_orders` and upsert into `paper_positions` via Supabase anon key. No Edge Function or backend needed. Weighted avg entry price on add-to-position. Close position records realized P&L and deletes row. No persistence for cash balance yet (resets to $10k on page reload).
7. **Max 3 on chart**: Limit applies to overlays on the chart canvas only. The indicator catalog should grow — more indicator types = better research capability.

## File Editing Rules
- **Backup before every edit.** Before modifying any file, copy it to `.backups/` with the pattern `{original-path-underscored}.{timestamp}.bak`.
- The `.backups/` directory is gitignored scratch space — you can always revert by restoring a `.bak` file.

## Notes
- Supabase anon key has SELECT + INSERT RLS policies on `crypto_research` (V3 migration). Research entries written by client-side JS persist.
- Service role key is in `setup.ps1` line 35 — never embed in frontend code. Only needed if paper trading endpoints are re-implemented.
- The Supabase project URL and anon key are also in `setup.ps1`.
- The Python backend (`backend/`) is kept for reference but no longer invoked. The JS functions are standalone ports of the pandas/numpy logic.

## RLS Policies
- `crypto_research`: Allow public read (SELECT), Allow public insert (INSERT for anon) — applied via `supabase_migration.sql` + `migrations/V3__research_insert_policy.sql`
- `paper_orders`, `paper_positions`, `paper_equity_curve`: Allow public read (SELECT), Allow anon INSERT/UPDATE/DELETE — applied via `migrations/V2__enhanced_schema.sql` + `migrations/V4__paper_trading_rls.sql`
