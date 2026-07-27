# Trader's Lab

Crypto research, charting, and paper trading terminal — entirely client-side vanilla HTML/JS, backed by Supabase + a Python research engine.

## Quick Start

```powershell
cd crypto-etl
python -m http.server 8080
# Open http://localhost:8080
```

No build step, no npm install, no backend server. Just serve the static files.

## Pages

| Page | File | What it does |
|------|------|-------------|
| **Landing** | `index.html` | Entry point with links to Charts and Research |
| **Charts** | `charts.html` | Candlestick chart (Lightweight Charts), 12+ indicators, signal builder with buy/sell markers, paper trading panel (long/short, positions, P&L, order history) |
| **Research** | `research.html` | Cross-pair sentiment consensus, best strategies per symbol, research history, sortable table with expandable detail rows |

## Data Pipeline

```
CCXT (OKX)  →  historical_etl.py  →  Supabase (crypto_historical)
CCXT (OKX)  →  etl.py             →  Supabase (crypto_data)            ← GitHub Actions every 30 min
              strategy_research.py →  Supabase (strategy_results)        ← GitHub Actions weekly
```

All frontend reads use the **anon key** with Row Level Security (SELECT only). Writes (paper trading, research entries) use the anon key with RLS policies allowing INSERT/UPDATE/DELETE for the appropriate session scope.

## Strategy Research Engine

`strategy_research.py` — 8 strategies with walk-forward validation:

| Strategy | Logic |
|----------|-------|
| RSI Reversion | Oversold/overbought mean reversion |
| MACD Crossover | Signal line cross + histogram confirmation |
| Bollinger Bands Reversion | Touch of lower/upper band |
| EMA Crossover | Fast/slow EMA cross |
| Stochastic RSI | K/D cross with overbought/oversold zones |
| Keltner Channel Breakout | Close above/below KC + volume confirmation |
| RSI + ADX Combo | Trend strength filter + RSI entries |
| RSI + Volume Combo | Volume-weighted RSI extremes |

```powershell
# Quick run (smaller param grid)
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"
python strategy_research.py --quick

# Full sweep (all 30 symbols × 3 timeframes, takes hours)
python strategy_research.py
```

Results export to `strategy_results.csv` and Supabase `strategy_results` table under a `research_runs` run_id.

## Database

Supabase project `ymnlqggxeeyqvrojsrzh` — all migrations in `migrations/`:

| Table | Rows | Purpose |
|-------|------|---------|
| `crypto_historical` | ~227k | OHLCV bars (30 symbols × 3 timeframes) |
| `crypto_data` | ~30 | Current price snapshots (30 min refresh) |
| `crypto_research` | varies | AI research entries (generated client-side) |
| `research_runs` | per run | Strategy run metadata |
| `strategy_results` | per run | Per-variant backtest metrics |
| `paper_orders` | per trade | Paper trading order history |
| `paper_positions` | per position | Open positions, live P&L |
| `paper_equity_curve` | per snapshot | Portfolio value over time |

## Running ETL

```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"

# Current price snapshot (fast)
python etl.py

# Historical data (slow — years of OHLCV per symbol)
python historical_etl.py
```

## Key Design Decisions

1. **Vanilla HTML/JS** — no build step, no npm, no framework churn. Just serve and go.
2. **TradingView Lightweight Charts** — canvas-based, handles thousands of bars smoothly.
3. **All indicators client-side** — 12 types in vanilla JS. No server dependency, instant response.
4. **Supabase anon key** — safe with RLS. Service role key is server/script only.
5. **Run_id scoping** — strategy results are scoped to the latest research run to avoid stale/duplicate displays.
6. **Paper trading is persistent** — positions and orders survive page reload (stored in Supabase).
7. **Lookahead bias eliminated** — backtest signals are shifted 1 bar forward so bar `i`'s signal uses bar `i-1`'s close, executable at bar `i`'s open.

## Architecture

The `backend/` (FastAPI) and `frontend/` (React/Vite) directories are **abandoned**. All active development is in the root HTML/JS files and Python ETL scripts.

```
crypto-etl/
├── index.html              # Landing page
├── charts.html             # Charting terminal (primary UI)
├── research.html           # Research dashboard
├── strategy_research.py    # Strategy engine (8 strategies, walk-forward)
├── etl.py                  # Current price snapshots
├── historical_etl.py       # Historical OHLCV fetch (CCXT)
├── setup.ps1               # Supabase project setup
├── migrations/             # SQL migrations (V2–V7)
│   ├── V2__enhanced_schema.sql
│   ├── V3__crypto_research.sql
│   ├── V4__paper_trading.sql
│   ├── V5__strategy_results.sql
│   ├── V6__walk_forward.sql
│   └── V7__paper_trading_session_id.sql
├── strategy_results.csv    # Latest engine output
├── AGENTS.md               # AI agent project conventions
├── .env.example
└── docs/
    ├── architecture/       # Data flow diagrams
    ├── data-contracts/     # Research, strategy, signal contracts
    ├── decisions/          # Architecture Decision Records
    └── research/           # Strategy methodology
```

## Supabase Key Rules

| Key | Type | Where used |
|-----|------|------------|
| `SUPABASE_URL` | Public URL | Everywhere |
| Anon key | Publishable | Frontend HTML (RLS-protected) |
| Service role key | Secret | Python scripts only (ETL, research engine) |

Never hard-code the service role key in frontend code. Never log or print it.
