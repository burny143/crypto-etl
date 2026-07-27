# Data Contract: Research Result

## Purpose

Define the schema for a versioned research result produced by the strategy research engine, including walk-forward validation metadata and performance metrics.

## Status

**DRAFT** — Partially implemented in `strategy_results` table and `research_runs` table.

---

## Schema (Proposed — Superset of Current)

### Core Fields

| Field | Type | Required | Current Status | Description |
|-------|------|----------|----------------|-------------|
| `run_id` | UUID | ✅ | ✅ In `research_runs` | Unique identifier for the research run |
| `strategy_id` | UUID | ✅ | ❌ Missing | Links to `strategy_definitions.id` |
| `strategy_version` | INTEGER | ✅ | ❌ Missing | The version of the strategy definition used |
| `strategy_name` | TEXT | ✅ | ✅ In `strategy_results` | Human-readable name (denormalized) |
| `symbol` | TEXT | ✅ | ✅ In `strategy_results` | Trading pair (e.g., "BTC-USDT") |
| `timeframe` | TEXT | ✅ | ✅ In `strategy_results` | Bar interval ("1h", "4h", "1d") |
| `parameters` | JSONB | ✅ | ✅ In `strategy_results.params` | Strategy parameters used for this result |
| `validation` | TEXT | ✅ | ✅ In `params._validation` | "in_sample" or "out_of_sample" |
| `sharpe_ratio` | FLOAT | ✅ | ✅ In `strategy_results` | Annualized Sharpe ratio |
| `total_return_pct` | FLOAT | ✅ | ✅ In `strategy_results` | Total return percentage |
| `max_drawdown_pct` | FLOAT | ✅ | ✅ In `strategy_results` | Maximum peak-to-trough drawdown |
| `win_rate` | FLOAT | ✅ | ✅ In `strategy_results` | Percentage of winning trades |
| `profit_factor` | FLOAT | ✅ | ✅ In `strategy_results` | Gross profit / gross loss |
| `trade_count` | INTEGER | ✅ | ✅ In `strategy_results` | Number of trades executed |
| `train_start_date` | DATE | ✅ | ✅ In V6 migration | Walk-forward training start |
| `train_end_date` | DATE | ✅ | ✅ In V6 migration | Walk-forward training end |
| `test_start_date` | DATE | ✅ | ✅ In V6 migration | Walk-forward test start |
| `test_end_date` | DATE | ✅ | ✅ In V6 migration | Walk-forward test end |
| `generated_at` | TIMESTAMPTZ | ✅ | ❌ Missing | When this result was generated |

### Additional Metrics (Optional)

| Field | Type | Description |
|-------|------|-------------|
| `calmar_ratio` | FLOAT | Annualized return / max drawdown |
| `avg_holding_period` | INTEGER | Average bars per trade |
| `total_fees_paid` | FLOAT | Sum of commissions in quote currency |
| `market_correlation` | FLOAT | Correlation of strategy returns with benchmark |

---

## Current Implementation

### `strategy_results` Table

The table exists and is populated by `strategy_research.py`. The `params` JSONB column contains:
- All strategy-specific parameters (period, threshold, etc.)
- `_validation`: `"in_sample"` or `"out_of_sample"` (stored here as a fallback because the `validation` column from V6 may not exist yet)

### `research_runs` Table

Exists in Supabase (created by V5 migration). Tracks run metadata:
- `run_id` (UUID)
- `symbol`
- `timeframe`
- `created_at`
- `status`

### Gaps

1. No `strategy_id` field — results are linked to strategy names only
2. No `strategy_version` — cannot distinguish which version of a strategy produced the result
3. No `generated_at` in `strategy_results` — must join to `research_runs`
4. The `validation` column (V6 migration) may not exist yet — `_validation` is stored in `params` JSONB as a fallback
5. The frontend's `loadStrategyResults()` uses `_validation` from `params`, but the filter logic references `resultsData` (variable) vs `data` (original query) — see bug fix history

### Example Row

```json
{
  "strategy_name": "RSI Mean Reversion",
  "symbol": "BTC-USDT",
  "timeframe": "4h",
  "params": {
    "period": 14,
    "oversold": 30,
    "overbought": 70,
    "_validation": "out_of_sample"
  },
  "sharpe_ratio": 2.34,
  "total_return_pct": 45.6,
  "max_drawdown_pct": -12.3,
  "win_rate": 58.0,
  "profit_factor": 1.87,
  "trade_count": 124
}
```
