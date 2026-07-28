# Paper-Trading Bot — Architecture Document

## Status

**Phase 0 — Repository Discovery, Contracts, and Plan.**  
This document records all verified schemas, constraints, and design decisions
that subsequent phases must obey.

---

## 1. Verified Schemas

### 1.1 `crypto_historical` — OHLCV bars

Source: `supabase_migration.sql`, `charts.html:loadChartData()`, `strategy_research.py:load_ohlcv()`, `historical_etl.py`.

| Column     | Type           | Required | Notes |
|------------|----------------|----------|-------|
| `id`       | BIGSERIAL      | ✅ Primary | Architecture not exposed; query results are field-only. |
| `symbol`   | TEXT           | ✅ | `"BTC-USDT"` (30 symbols, dash-separated). |
| `timeframe`| TEXT           | ✅ | `"1h"`, `"4h"`, `"1d"`. |
| `datetime` | TIMESTAMPTZ    | ✅ | Bar open time. UTC. Frontend converts to Unix epoch seconds (intraday) or `"YYYY-MM-DD"` (daily). |
| `open`     | DOUBLE PRECISION | ✅ | |
| `high`     | DOUBLE PRECISION | ✅ | |
| `low`      | DOUBLE PRECISION | ✅ | |
| `close`    | DOUBLE PRECISION | ✅ | |
| `volume`   | DOUBLE PRECISION | ✅ | |

**Indexes:** `(symbol, timeframe, datetime)`.  
**Populated by:** `historical_etl.py` via CCXT (OKX).  
**227,200 rows total** (30 symbols × 3 timeframes).  
**Frontend query:** `.select('*').eq('symbol', stratSymbol).eq('timeframe', currentTimeframe).order('datetime', { ascending: true })`.  

**Known:** Table uses `DOUBLE PRECISION` (64-bit float) internally. Python research
engine casts to `float64` via `pd.to_numeric()`. Frontend normalizes via `Number()`.

### 1.2 `crypto_data` — Current price snapshots

Source: `etl.py`, `charts.html:loadWatchlist()`.

| Column           | Type           | Required | Notes |
|------------------|----------------|----------|-------|
| `symbol`         | TEXT           | ✅ Unique key | `"BTC-USDT"`. |
| `current_price`  | DOUBLE PRECISION | ✅ | Latest ticker price from CCXT. |
| `previous_close` | DOUBLE PRECISION | ❌ | Ticker open (used as proxy for previous close). |
| `market_cap`     | DOUBLE PRECISION | ❌ | Always `NULL` (CCXT doesn't provide). |
| `name`           | TEXT           | ❌ | Human-friendly (`"BTC/USDT"`). |
| `updated_at`     | TIMESTAMPTZ    | ✅ | Previously `TIMESTAMP` in V2, but `etl.py` writes ISO 8601 UTC string. |

**Upsert key:** `symbol` (the unique constraint).  
**Populated by:** `etl.py` via CCXT with fallback chain (OKX → Binance → scan), runs every 30 min via GitHub Actions.  
**Frontend usage:** `crypto_data` is loaded at page boot into a `watchlistData` array. Also queried on-demand for position P&L calculation via `refreshPriceCacheForPositions()`.

### 1.3 `paper_orders` — Paper trade orders

Source: `migrations/V2__enhanced_schema.sql`, `migrations/V7__paper_trading_session_id.sql`, `charts.html:placeOrder()`, `charts.html:closePosition()`.

| Column       | Type              | Required | Notes |
|--------------|-------------------|----------|-------|
| `id`         | BIGSERIAL          | ✅ PK | |
| `symbol`     | TEXT               | ✅ | `"BTC-USDT"`. |
| `side`       | TEXT               | ✅ | `CHECK (side IN ('long', 'short'))`. |
| `order_type` | TEXT               | ✅ | Default `'market'`. `CHECK IN ('market', 'limit', 'stop')`. |
| `quantity`   | DOUBLE PRECISION   | ✅ | |
| `price`      | DOUBLE PRECISION   | ❌ | `NULL` for pending orders. |
| `stop_price` | DOUBLE PRECISION   | ❌ | For stop orders. |
| `status`     | TEXT               | ✅ | `CHECK IN ('pending', 'open', 'filled', 'cancelled', 'rejected')`. |
| `reason`     | TEXT               | ❌ | Rejection reason if any. |
| `opened_at`  | TIMESTAMPTZ        | ✅ | `DEFAULT NOW()`. |
| `filled_at`  | TIMESTAMPTZ        | ❌ | |
| `closed_at`  | TIMESTAMPTZ        | ❌ | |
| `pnl`        | DOUBLE PRECISION   | ❌ | Realized P&L when closed. |
| `notes`      | TEXT               | ❌ | |
| `metadata`   | JSONB              | ❌ | Default `'{}'`. |
| `session_id` | TEXT               | ❌ | Added by V7 migration. Used for per-browser scoping. |

**Current frontend usage:** Orders always `status='filled'`. `session_id` is a random UUID generated once per page load.

### 1.4 `paper_positions` — Open paper positions

Source: `migrations/V2__enhanced_schema.sql`, `V7`, `charts.html`.

| Column          | Type              | Required | Notes |
|-----------------|-------------------|----------|-------|
| `id`            | BIGSERIAL          | ✅ PK | |
| `symbol`        | TEXT               | ✅ | `"BTC-USDT"`. |
| `side`          | TEXT               | ✅ | `CHECK IN ('long', 'short')`. |
| `quantity`      | DOUBLE PRECISION   | ✅ | |
| `entry_price`   | DOUBLE PRECISION   | ✅ | Average entry. |
| `current_price` | DOUBLE PRECISION   | ❌ | Last refreshed price. |
| `unrealized_pnl`| DOUBLE PRECISION   | ❌ | |
| `realized_pnl`  | DOUBLE PRECISION   | ❌ | Default `0`. |
| `opened_at`     | TIMESTAMPTZ        | ✅ | `DEFAULT NOW()`. |
| `updated_at`    | TIMESTAMPTZ        | ✅ | `DEFAULT NOW()`. |
| `metadata`      | JSONB              | ❌ | Default `'{}'`. |
| `session_id`    | TEXT               | ❌ | Added by V7. |

**Constraint:** `UNIQUE(symbol, side)` — one position per symbol per side.  
**Netting:** Opposite-side orders reduce or close the existing position rather than creating a second position. Three branches: partial reduce, exact close (EPS = 1e-8), exceed-and-reverse.

### 1.5 `paper_equity_curve` — Portfolio snapshots

Source: `V2`.

| Column       | Type              | Required | Notes |
|--------------|-------------------|----------|-------|
| `id`         | BIGSERIAL          | ✅ PK | |
| `timestamp`  | TIMESTAMPTZ        | ✅ | `DEFAULT NOW()`. |
| `equity`     | DOUBLE PRECISION   | ✅ | Total portfolio value (cash + unrealized). |
| `cash`       | DOUBLE PRECISION   | ❌ | Default `0`. |
| `margin_used`| DOUBLE PRECISION   | ❌ | Default `0`. |

**Current frontend writes to this table but the equity curve is populated inconsistently** (only on `persistCash()` calls).

### 1.6 `crypto_research` — AI-generated research

Source: `supabase_migration.sql`, `charts.html`.

| Column       | Type           | Required | Notes |
|--------------|----------------|----------|-------|
| `id`         | BIGSERIAL       | ✅ PK | |
| `symbol`     | TEXT            | ✅ | |
| `report_type`| TEXT            | ✅ | `'market_analysis'`, `'backtest_result'`, `'signal'`, `'factor_score'`, `'news_summary'`. |
| `title`      | TEXT            | ✅ | |
| `summary`    | TEXT            | ✅ | |
| `details`    | JSONB           | ❌ | Default `'{}'`. |
| `sentiment`  | TEXT            | ❌ | `'bullish'`, `'bearish'`, `'neutral'`. |
| `confidence` | REAL            | ❌ | 0.0 to 1.0. |
| `source`     | TEXT            | ❌ | Default `'vibe-trading'`. |
| `created_at` | TIMESTAMPTZ     | ❌ | `DEFAULT NOW()`. |

### 1.7 Research infrastructure tables (V5/V6)

- **`research_runs`**: `run_id` (UUID PK), `run_timestamp` (TIMESTAMPTZ), `symbols` (TEXT[]), `timeframes` (TEXT[]), `total_variants` (INTEGER), `duration_seconds` (DOUBLE PRECISION), `status` (TEXT, CHECK running/completed/failed), `notes` (TEXT). RLS: public SELECT, service_role ALL.
- **`strategy_results`**: `id` (BIGSERIAL PK), `run_id` (UUID FK to research_runs), `strategy_name` (TEXT), `symbol` (TEXT), `timeframe` (TEXT), `params` (JSONB), `total_return_pct`/`sharpe_ratio`/`max_drawdown_pct`/`win_rate`/`profit_factor`/`trade_count`/`avg_bars_held`/`calmar_ratio` (DOUBLE PRECISION), `data_start_date`/`data_end_date` (DATE), `data_bar_count` (INTEGER), `created_at` (TIMESTAMPTZ). V6 added: `validation` (TEXT, CHECK 'in_sample'/'out_of_sample'), `train_start_date`/`train_end_date`/`test_start_date`/`test_end_date` (DATE). RLS: public SELECT, service_role ALL.

### 1.8 ETL support tables (V2)

- **`indicators`**: Pre-computed indicator cache. `(symbol, timeframe, datetime, indicator_name, md5(parameters::text))` unique index. Not currently used by frontend.
- **`etl_metadata`**: `symbol`, `timeframe`, `source`, `earliest_bar`, `latest_bar`, `total_bars`, `last_run_at`, `status`, `error_message`. UNIQUE(symbol, timeframe, source).
- **`symbols`**: Registry of 30 trading pairs with display metadata.

---

## 2. Symbol Formats

All symbols use uppercase dash-separated `BASE-QUOTE` format: `"BTC-USDT"`.

**30 tracked symbols** (from `etl.py`, `strategy_research.py`, `historical_etl.py`, `charts.html`):

```
BTC-USDT, ETH-USDT, XRP-USDT, SOL-USDT, BNB-USDT, ADA-USDT, DOGE-USDT,
AVAX-USDT, DOT-USDT, LINK-USDT, UNI-USDT, SHIB-USDT, LTC-USDT, BCH-USDT,
ATOM-USDT, ETC-USDT, XLM-USDT, FIL-USDT, TRX-USDT, NEAR-USDT, APT-USDT,
ARB-USDT, OP-USDT, SUI-USDT, PEPE-USDT, INJ-USDT, TIA-USDT, POL-USDT,
SEI-USDT, STRK-USDT
```

---

## 3. Timeframes

Three supported bar intervals: `"1h"`, `"4h"`, `"1d"`.

---

## 4. UI Balance / Position / PnL Behavior

### Cash Balance (`tradeCash`)

- Initialized as `$10,000 + sum(realized PnL from paper_orders for current session_id)`.
- Also persisted in `localStorage` under key `'paperTradeCash'`.
- Updated on every order: `tradeCash += realizedPnl` on partial closes, full closes, and position reductions.
- **Resets on page reload** if no realized PnL history exists for the session_id. This is known: AGENTS.md lists "Paper trading resets on page reload (no persistent cash balance)" as a limitation.

### PnL Calculation

```
PnL (long)  = (current_price - entry_price) × quantity
PnL (short) = (entry_price - current_price) × quantity
```

### Current Price for PnL

Priority chain:
1. `symbolPriceCache[symbol]` — populated from most recent `crypto_historical.close` at chart load time.
2. `watchlistData[x].current_price` — from `crypto_data` at page boot.
3. `historicalData[last].close` — only for the currently charted symbol (fallback, `live: false`).

### Price Staleness Detection

In `placeOrder()`: if `getCurrentPrice()` returns `{ live: false }`, the order is rejected with "Price data is stale."
In `closePosition()`: if stale, user is prompted anyway.

---

## 5. Repository Constraints

1. **`vibe-trading/` is read-only.** Never modify, copy from, or create dependencies to it. This is enforced by `crypto-etl/AGENTS.md`, `.ai/prohibited-actions.md`, `.ai/reference-policy.md`, and ADR-0003.

2. **Supabase anon key in frontend.** The `SUPABASE_ANON_KEY` is hardcoded in `charts.html` and `research.html`. Safe because RLS restricts to SELECT/INSERT on specific tables. The `service_role` key is backend-only.

3. **No live trading.** ADR-0004, `.ai/scope.md`, `.ai/financial-safety.md`.

4. **No ML/RL.** All strategies are transparent rule-based systems. (`.ai/scope.md`, `.ai/prohibited-actions.md`)

5. **No full rewrites of index.html/charts.html.** Incremental changes only.

6. **Supabase `UNIQUE(symbol, side)` on `paper_positions`.** Prevents duplicate long or short positions per symbol.

---

## 6. Module Boundaries

Target tree for `crypto-etl/bot/` (from the Master Project Directive):

```
bot/
├── __init__.py
├── engine.py            # Main loop (Phase 5)
├── cli.py               # CLI commands (Phase 1)
├── config.py            # YAML + env loading (Phase 1)
├── config.yaml          # User-facing config
├── domain/              # Enums, models, events, exceptions
├── data/                # Market data interface, Supabase adapter, validation
├── strategies/          # Strategy contract + registry + RSI (Phase 2)
├── risk/                # Pre-trade risk checks (Phase 3)
├── execution/           # Order models, paper executor (Phase 3)
├── portfolio/           # Accounting, portfolio service (Phase 3)
├── repositories/        # Supabase persistence adapters
├── backtesting/         # Clock, feed, fill model, engine, metrics (Phase 4)
├── monitoring/          # Logging, health, heartbeat (Phase 7)
├── logs/.gitkeep
└── tests/               # Unit + integration + contract fixtures
```

**Key interface rules:**

- **Strategies are pure** — they compute signals from OHLCV and return structured `Signal`. No database, execution, or portfolio side effects.
- **Risk precedes execution** — RiskDecision approves or rejects OrderIntent. PaperExecutor accepts risk-approved orders only.
- **Persistence behind repositories** — Supabase query shapes are hidden behind repository adapters.
- **Decision keys are deterministic** — Every order has an idempotent `client_order_id` derived from stable fields (strategy_id, symbol, timeframe, candle_timestamp).

---

## 7. Data Flow

```
Historical OHLCV (crypto_historical)
    │  SELECT * WHERE symbol=? AND timeframe=? ORDER BY datetime ASC
    ▼
Data Adapter (bot/data/)
    │  Validates: required fields, OHLC consistency, sort order,
    │  no duplicates, no future timestamps, sufficient warm-up
    ▼
Strategy.evaluate(ohlcv)
    │  Pure function → Signal { classification, params, decision_key, ... }
    │  Uses **completed candles only** (latest candle is T-1 or earlier)
    ▼
OrderIntent (bot/risk/)
    │  Pre-trade checks: max notional, stale price, duplicate key,
    │  sufficient cash, open position limits, daily loss, drawdown
    ▼
RiskDecision (APPROVED / REJECTED with reason)
    ▼
PaperExecutor (bot/execution/)
    │  Apply fees, slippage → PaperFill
    │  Write to paper_orders + paper_positions via repositories
    ▼
PortfolioService (bot/portfolio/)
    │  Update cash, realized/unrealized PnL, equity
    │  Persist equity snapshot
    ▼
Logging / Monitoring
```

---

## 8. Idempotency

Every order receives a deterministic `client_order_id` computed from:
`sha256(strategy_id + "|" + symbol + "|" + timeframe + "|" + candle_timestamp.isoformat())`.

The repository layer checks for existing orders with this key before inserting.
Repeated polling of the same candle never produces a duplicate trade.

---

## 9. Completed-Candle and Stale-Price Rules

### Completed Candle Rule

- Only candles whose close time is in the past are eligible for evaluation.
- If the current UTC time is `T` and the bar interval is 1h, the most recent eligible
  candle is the one whose open time ≤ `T - 1h`.
- A grace window (configurable, default 30 s) allows for data propagation delay.
- Never evaluate a forming (in-progress) candle.

### Stale Price Rule

- A "fresh" current price is one whose `updated_at` is within `max_age` seconds (configurable, default 120 s).
- If no fresh price is available, the engine skips execution for that symbol (logs a SKIP) rather than using stale data.
- Strategy `evaluate()` uses completed-candle close for signal generation.
- The fresh price is used **only** for fill price modeling during execution,
  never for signal computation.

---

## 10. Decimal / UTC Policy

- **Monetary values:** Use `Decimal` for all money, quantity, fees, balances, and PnL in the Python bot. Supabase stores `DOUBLE PRECISION` — convert at the repository boundary.
- **Timestamps:** All internal timestamps are `datetime` with `timezone.utc`. Supabase stores `TIMESTAMPTZ`. The frontend uses ISO 8601 UTC strings.
- **Percentages:** Stored as `float` (e.g., `12.5` for 12.5%).

---

## 11. Access Patterns / Authentication

| Credential | Where Used | Mechanism |
|-----------|-----------|-----------|
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` | Frontend (`charts.html`) | `createClient()` with anon key, RLS restricts operations |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | Python scripts (`etl.py`, `strategy_research.py`, `historical_etl.py`) | `create_client()` with service_role key; environment variables only |
| N/A | Bot (`bot/`) | Same pattern: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` from environment variables |

**Authentication architecture is intentionally not expanded** (per scope decision in the PDF guide).

---

## 12. Strategy Research Engine (Existing)

Located in `strategy_research.py` (1019 lines). Key details verified:

- **8 strategy templates:** RSI Mean Reversion, MACD Crossover, Bollinger Bands Reversion, EMA Crossover, StochRSI, Keltner Breakout, RSI+ADX Combo, RSI+Volume Combo.
- **Walk-forward:** 70% train / 30% temporal split. Parameter sweep on train → test top 5 on test.
- **RSI calculation:** Uses SMA of gains/losses (Wilder's smoothing style, but via `rolling().mean()`, not EMA).
- **Backtest:** Signal shifted by 1 bar (`shift(1)`) to prevent look-ahead. Entry at next bar's open. No leverage, no fees.
- **Minimum trades:** 30 for a valid result.
- **Frontend indicators in JS** independently implement the same calculations. Not cross-tested.
- **`strategy_results.csv`:** 9,437 variants. Last full sweep output.

---

## 13. RSI Calculation Semantics

Current Python implementation (`_rsi`):
```python
delta = close.diff()
gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
rs = gain / loss.replace(0, np.nan)
return 100 - (100 / (1 + rs))
```

This uses simple moving average of gains/losses (not Wilder's smoothed EMA).
The bot's RSI strategy (Phase 2) must match this calculation for consistency
with existing research results.

---

## 14. Test Strategy

### Scope

- **Unit tests:** Pure functions (strategy evaluation, signal generation, domain models, validation).
- **Contract tests:** Repository adapters against known Supabase rows.
- **Integration tests:** Explicitly opt-in (needs credentials). Never run in default CI.
- **Forbidden boundary checks:** Test that bot/ never imports from vibe-trading/.

### Naming Convention

`test_<module>_<scenario>.py` per standard pytest convention.

### Fixtures

- `tests/fixtures/ohlcv_sample.json` — 500 bars of pre-loaded OHLCV.
- `tests/fixtures/ohlcv_malformed.json` — edge cases (missing fields, OHLC inconsistencies, duplicates, future timestamps).
- `tests/fixtures/config_valid.yaml` / `config_invalid.yaml` — for config validation.

### Minimum Coverage

Phase 1.5 targets 75% coverage floor. No meaningless tests added to inflate coverage.

### Offline-Safe

Default CI must not require credentials, write to Supabase, or make network calls.
Integration tests are optionally gated behind a marker (`@pytest.mark.integration`).

---

## 15. CI Plan

| Gate | Tool | Phase | Notes |
|------|------|-------|-------|
| Formatter | `black` | 1.5 | Target `py311` compatible. |
| Linter | `ruff` | 1.5 | Based on project convention (no ruff config currently in crypto-etl, but vibe-trading uses it). |
| Type checker | `mypy` (optional) | 1.5 | Minimum on bot/ for Phase 1.5. |
| Unit tests | `pytest` | 1.5 | Offline-safe by default. |
| Contract tests | `pytest` | 1.5 | Opt-in (`--integration`). |
| Secret scanning | `gitleaks` or script | 1.5 | Scan for accidental credential commits. |
| Vibe-trading boundary | Script | 1.5 | Verify no imports/symlinks/deps from crypto-etl/ to vibe-trading/. |
| Coverage | `pytest-cov` | 1.5 | 75% floor on bot/. |

---

## 16. Git Checkpoints

| Checkpoint | Branch | Created At |
|-----------|--------|-----------|
| Baseline (Phase 0 start) | `main` (crypto-etl HEAD `dbd12cf`) | Before any changes |
| Discovery complete | `phase/0-discovery` | Current branch |

**After human approval:** Create annotated tag `bot-phase-0-approved`.

**Phase branches:**

| Phase | Branch | Depends On |
|-------|--------|-----------|
| 1 | `phase/1-market-data` | Phase 0 approved |
| 1.5 | `phase/1-5-ci` | Phase 1 approved |
| 2 | `phase/2-rsi-strategy` | Phase 1.5 approved |
| 3 | `phase/3-paper-execution` | Phase 2 approved |
| 4 | `phase/4-backtesting` | Phase 3 approved |
| 4.5 | `phase/4-5-execution-calibration` | Phase 4 approved |
| 5 | `phase/5-forward-paper` | Phase 4.5 approved |
| 6 | `phase/6-multi-strategy` | Phase 5 approved |
| 7 | `phase/7-monitoring` | Phase 6 approved |

---

## 17. Open Questions

1. **`session_id` vs strategy-owned positions.** The current paper trading UI uses `session_id` (a random browser UUID) to scope positions. The bot's multi-strategy model (Phase 6) requires `strategy_id` ownership. How to reconcile? Proposed: add `strategy_id` to `paper_positions` and `paper_orders` (non-breaking). Remove `session_id` scoping from the bot (bot has a single fixed constant run_id).

2. **`UNIQUE(symbol, side)` constraint.** The V2 schema enforces one position per symbol per side. The bot's multi-strategy phase requires independent positions by strategy. This constraint will need to be relaxed or replaced with `UNIQUE(symbol, side, strategy_id)`.

3. **`paper_orders` status values.** The V2 schema defines `CHECK IN ('pending', 'open', 'filled', 'cancelled', 'rejected')`. The frontend only uses `'filled'`. The bot will use additional statuses (`'open'`, `'cancelled'`, `'rejected'`). No conflict expected.

4. **No `signal_id` or `strategy_id` in paper tables.** The existing frontend never links orders to signals or strategies. The bot will add these columns (a future migration).

5. **`DOUBLE PRECISION` vs `Decimal` in Supabase.** The bot uses Python `Decimal` internally but writes `float` to Supabase. Precision loss at the boundary is acceptable for paper trading (sub-cent on typical crypto prices).

6. **Cache invalidation for stale prices.** The frontend `symbolPriceCache` is never evicted. The bot must set `updated_at` thresholds and reject stale prices rather than caching indefinitely.

7. **`tradeCash` initialization.** Deriving cash from realized PnL history works only if the session is the same. The bot will own its cash tracking independently — starting from a configurable base and maintaining its own serialized state.

8. **No existing test infrastructure.** `bot/tests/` is the first test directory in crypto-etl. The 75% coverage floor will require evaluating what's pragmatic to test (pure strategy logic vs. Supabase I/O).

9. **Python version mismatch.** CI uses 3.10 (`actions/setup-python@v5` with `python-version: '3.10'`), but local development runs 3.13. The bot must target 3.10+ compatibility. Note: 3.10 is EOL per https://endoflife.date/python (2026-10). Recommend upgrading CI to 3.11+.

10. **No existing pyproject.toml or requirements.txt at crypto-etl root.** Only the abandoned `backend/requirements.txt` exists. The bot needs its own dependency management.

---

## 18. Contract Conflicts

| Contract | Conflict | Resolution |
|----------|----------|-----------|
| `paper_orders` CHECK on `order_type` limits to `market/limit/stop` | The frontend only uses `market` | No conflict — bot will use `market` primarily. |
| `paper_positions` UNIQUE(symbol, side) | Proposed in paper-portfolio.md: "Only one position per symbol (either long or short, never both)" | Phase 6 multi-strategy requires per-strategy positions. Add `strategy_id` to unique constraint. |
| `paper_orders` has no `signal_id` | signal-event.md proposes adding it | Phase 3 migration. |
| V6 `validation` column may not exist | `strategy_research.py` uses `params._validation` as fallback | Bot should accept both. |

---

## 19. vibe-trading / crypto-etl Boundary Verification

- **`vibe-trading/` is read-only.** This repository has been inspected only at a high architectural level for patterns.
- **No files** have been modified, created, or copied in `vibe-trading/`.
- **No imports, symlinks, paths, or runtime dependencies** exist from `crypto-etl/bot/` to `vibe-trading/`.
- **No implementation code** has been copied from `vibe-trading/` into `crypto-etl/bot/`.
- The patterns independently adapted (see `.ai/reference-policy.md` verified):
  - Strategy interface with `evaluate(ohlcv) -> Signal` (inspired by SignalEngine contract)
  - Walk-forward validation pattern
  - Pure pandas/numpy signals
