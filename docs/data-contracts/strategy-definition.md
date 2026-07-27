# Data Contract: Strategy Definition

## Purpose

Define the schema and lifecycle for a trading strategy that can be researched, validated, and executed as signals on the chart.

## Status

**DRAFT** — Not yet implemented in Supabase. Currently, strategy definitions are implicit in `strategy_results.params` (JSONB column) and the strategy names in `strategy_research.py`.

---

## Schema (Proposed)

### `strategy_definitions` Table

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | UUID | ✅ | Primary key, immutable |
| `name` | TEXT | ✅ | Human-readable name (e.g., "RSI Mean Reversion") |
| `version` | INTEGER | ✅ | Version number, increments with each change |
| `indicator` | TEXT | ✅ | Primary indicator name (e.g., "rsi", "macd") |
| `parameters` | JSONB | ✅ | Strategy parameters (e.g., `{"period": 14, "oversold": 30, "overbought": 70}`) |
| `direction` | TEXT | ✅ | `long`, `short`, or `both` |
| `filters` | JSONB | ❌ | Optional filter conditions (e.g., `{"min_volume": 1000000}`) |
| `description` | TEXT | ❌ | Human-readable description of strategy logic |
| `superseded_by` | UUID | ❌ | Pointer to newer version (null if current) |
| `created_at` | TIMESTAMPTZ | ✅ | When this version was created |
| `deprecated_at` | TIMESTAMPTZ | ❌ | When this version was deprecated |

### Constraints

- `(name, version)` must be unique (one version per name)
- `parameters` must be a JSON object matching the indicator's parameter schema
- `superseded_by` must reference a different version of the same strategy name, or be null

### Example

```json
{
  "id": "a1b2c3d4-...",
  "name": "RSI Mean Reversion",
  "version": 2,
  "indicator": "rsi",
  "parameters": {
    "period": 14,
    "oversold": 30,
    "overbought": 70,
    "smoothing": "ema"
  },
  "direction": "both",
  "filters": null,
  "description": "Buy when RSI crosses below oversold and recovers above it. Sell when RSI crosses above overbought and falls below it.",
  "superseded_by": null,
  "created_at": "2026-07-27T00:00:00Z",
  "deprecated_at": null
}
```

### `strategy_approvals` Table (Future)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | UUID | ✅ | Primary key |
| `strategy_id` | UUID | ✅ | References `strategy_definitions.id` |
| `status` | TEXT | ✅ | One of: `DRAFT`, `RESEARCHING`, `CANDIDATE`, `PAPER_APPROVED`, `ACTIVE_PAPER`, `PAUSED`, `RETIRED`, `REJECTED` |
| `notes` | TEXT | ❌ | Approval or rejection notes |
| `approved_by` | TEXT | ❌ | Who approved (user identifier for multi-user future) |
| `created_at` | TIMESTAMPTZ | ✅ | When this status was set |

---

## Current State (Before Implementation)

Strategy definitions are **implicit** in the current codebase:

- **`strategy_research.py`** — each strategy is a function that takes parameters and returns signals. Strategy templates have hard-coded parameter ranges.
- **`strategy_results.params`** (JSONB) — stores the specific parameters used in each research run. This is the closest thing to a strategy definition today.
- **`index.html`** — `applyStrategySignals()` uses strategy parameters from the clicked card's `data-params` attribute to recompute signals. The logic is duplicated from the Python implementation.

### Traceability Gap

There is no `strategy_id` or `strategy_version` in `strategy_results` — only `strategy_name`. If a strategy's definition changes between research runs, there is no way to tell which version of the strategy produced which set of results.
