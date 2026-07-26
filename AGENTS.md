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

### Unused tables (from old migration, not currently queried):
- `indicators`, `paper_orders`, `paper_positions`, `paper_equity_curve`, `etl_metadata`

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
6. **Paper Trading**: Not yet implemented. No backend to handle order/position state. Would need a Supabase Edge Function or restored Python backend.
7. **Max 3 on chart**: Limit applies to overlays on the chart canvas only. The indicator catalog should grow — more indicator types = better research capability.

## File Editing Rules
- **Backup before every edit.** Before modifying any file, copy it to `.backups/` with the pattern `{original-path-underscored}.{timestamp}.bak`.
- The `.backups/` directory is gitignored scratch space — you can always revert by restoring a `.bak` file.

## Notes
- Supabase anon key is embedded in `index.html`. For research INSERT to work, an RLS INSERT policy may need to be added to `crypto_research` (anon currently has SELECT only).
- Service role key is in `setup.ps1` line 35 — never embed in frontend code. Only needed if paper trading endpoints are re-implemented.
- The Supabase project URL and anon key are also in `setup.ps1`.
- The Python backend (`backend/`) is kept for reference but no longer invoked. The JS functions are standalone ports of the pandas/numpy logic.
