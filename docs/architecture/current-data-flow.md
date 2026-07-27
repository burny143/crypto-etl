# Current Data Flow

## Overview

The system has four main data flows: historical data ingestion, price snapshot ingestion, strategy research, and client-side operations. There is no central orchestrator — each flow operates independently.

---

## Flow 1: Historical OHLCV Data

```
CCXT (OKX Exchange)
    │
    ▼
historical_etl.py
    │  Paginated fetch: 30 symbols × 3 timeframes
    │   - 1d: ~3 years
    │   - 1h: ~6 months
    │   - 4h: resampled from 1h
    │  Resampling: pandas DataFrame.resample('4h')
    │  Computed fields: bar_return, bar_change_pct, price_range
    │  Batch upsert: 500 rows at a time
    ▼
Supabase: crypto_historical
    │  Columns: symbol, timeframe, datetime, open, high, low, close, volume
    │  Indexed on: (symbol, timeframe, datetime)
    │  227,200 rows total
    ▼
index.html: loadChartData()
    │  .select('*').eq('symbol', stratSymbol).eq('timeframe', currentTimeframe)
    │  .order('datetime', { ascending: true })
    │  Transforms rows → historicalData array
    ▼
Lightweight Charts
    ── candlestick series (open, high, low, close)
    ── volume series (histogram)
    ── indicator lines (12+ types, computed client-side from historicalData)
```

## Flow 2: Current Price Snapshots

```
CCXT (OKX → Binance → fallback)
    │
    ▼
etl.py
    │  Runs every 30 min via GitHub Actions
    │  Fetches ticker for 30 symbols
    │  Upserts to Supabase
    ▼
Supabase: crypto_data
    │  Columns: symbol, current_price, previous_close, updated_at
    ▼
index.html: loadWatchlist()
    │  Fetches on page load
    │  Populates pair selector with current prices
    │  Sets currentSymbol to first symbol in watchlist
    ▼
Pair selector dropdown (top navigation)
```

## Flow 3: Strategy Research

```
Supabase: crypto_historical
    │
    ▼
strategy_research.py
    │  8 strategy templates:
    │   - RSI Mean Reversion
    │   - MACD Crossover
    │   - Bollinger Bands Reversion
    │   - EMA Crossover
    │   - StochRSI
    │   - Keltner Breakout
    │   - RSI+ADX Combo
    │   - RSI+Volume Combo
    │
    │  Walk-forward validation: 70% train / 30% test
    │  Parameter sweep over all combos on training data
    │  Test top 5 on held-out test data
    │
    │  Output metrics:
    │   - Sharpe ratio, total return %, max drawdown %
    │   - Win rate, profit factor, trade count, Calmar ratio
    │
    ▼
Supabase: strategy_results         +    strategy_results.csv
    │  Columns: strategy_name, symbol, timeframe,
    │  sharpe_ratio, total_return_pct, max_drawdown_pct,
    │  win_rate, profit_factor, trade_count, params (JSONB)
    │
    │  params JSONB includes: _validation ('in_sample' | 'out_of_sample')
    │  + all strategy-specific parameters
    │
    ▼
index.html: loadStrategyResults()
    │  Fetches top 20 results for current symbol/timeframe
    │  Falls back to alt timeframe if no results
    │  Separates OOS and IS results
    │  Renders strategy cards in #stratFeed
    │
    ▼
Strategy Cards in UI
    │  Click → applyStrategySignals()
    │  Parses params from data attribute
    │  Computes indicator values from historicalData
    │  Generates chart markers (BUY/SELL)
    │  Adds .active class to strategy card
    │
    ▼
Chart with BUY/SELL markers
```

## Flow 4: Client-Side Research

```
index.html: generateResearch()
    │  Computes technical summaries from historicalData:
    │   - Current price vs SMA(20,50,200)
    │   - RSI level and direction
    │   - MACD cross status
    │   - Volume comparison
    │   - Bollinger position
    │   - ADX trend strength
    │   - ATR volatility
    │  Generates structured research object
    ▼
Supabase: crypto_research
    │  Columns: symbol, title, summary, sentiment, confidence, details
    ▼
Research Panel (right sidebar)
    ── Title, sentiment badge, confidence bar
    ── Expandable details
```

## Flow 5: Paper Trading

```
User fills order form (index.html)
    │  symbol (current), side (long/short), quantity
    ▼
placeOrder()
    │  Checks for existing same-side position → merge/average
    │  Checks for opposite-side position → net
    │  Three netting branches:
    │   - remainingQty > EPS  → reduce opposite, keep remainder
    │   - |remainingQty| ≤ EPS → fully close opposite
    │   - remainingQty < -EPS  → close opposite, open excess as new same-side
    │  Inserts order + updates/deletes positions
    ▼
Supabase: paper_orders + paper_positions
    │
    ▼
renderPositions() [refreshes every 15s]
    │  Fetches paper_positions + current prices
    │  Computes unrealized P&L
    │  Renders position list with live values
    ▼
Trading Panel (right sidebar)
```

---

## Where Traceability Is Currently Lost

### Gap 1: Strategy Results → Chart Markers

When a user clicks a strategy card in the Top Strategies panel, `applyStrategySignals()` recomputes the indicator values from scratch using the current `historicalData` array. There is **no signal_id, strategy version, or research run identifier** attached to the resulting chart markers. If the research run is repeated with different parameters, there is no way to determine which version of a strategy produced the markers currently on the chart.

**Missing link:** `strategy_results` has no stable `strategy_id` (only `strategy_name` which can change across runs). The `research_runs` table exists but is not queried by the frontend. Chart markers are not stored in any table — they exist only in the `signalChartMarkers[]` JS array, which is destroyed on page reload.

### Gap 2: Research Results → Paper Trades

When a user places a paper trade based on a research insight or strategy signal, there is no field in `paper_orders` or `paper_positions` that links back to the research result or strategy that motivated the trade. This makes post-trade attribution impossible.

**Missing link:** No `signal_id`, `research_run_id`, or `strategy_id` column in the paper trading tables.

### Gap 3: Strategy Logic Duplication

Strategy indicator logic exists in two places:
1. **Python** (`strategy_research.py`) — uses numpy/pandas for strategy computation during research sweeps
2. **JavaScript** (`index.html`) — uses pure JS array math for `applyStrategySignals()`

These are independent implementations. There is no automated test to verify they produce equivalent results for the same inputs. A parameter change in one does not automatically propagate to the other.

---

## Data Flow Diagram (Current)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OKX (CCXT) │────▶│  historical_etl  │────▶│  crypto_historical│
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
┌─────────────┐     ┌──────────────────┐              │
│  OKX (CCXT) │────▶│      etl.py      │              │
└─────────────┘     └────────┬─────────┘              │
                             │                        │
                             ▼                        ▼
                     ┌──────────────┐     ┌───────────────────┐
                     │  crypto_data  │     │ strategy_research │
                     └──────────────┘     └─────────┬─────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │ strategy_results │
                                            └────────┬─────────┘
                                                     │
┌─────────────┐     ┌──────────────────┐              │
│   User      │────▶│   index.html     │◀─────────────┘
└─────────────┘     └──┬───────┬───────┘
                       │       │
                       ▼       ▼
              ┌──────────┐ ┌──────────┐
              │ paper_   │ │ crypto_  │
              │ orders / │ │ research │
              │ positions│ └──────────┘
              └──────────┘
```

**Key:** Solid lines = working data flow. Dotted traceability (missing) = strategy_results → chart markers has no stable identifiers.
