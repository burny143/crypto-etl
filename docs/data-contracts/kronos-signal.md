# Data Contract: Kronos + Trend Composite Signal

## Purpose

Define the schema and semantics for the **precomputed Kronos + Trend**
predictions and composite buy/sell signals stored in Supabase and rendered
through the existing chart indicator/marker pipeline.

This is a **research overlay**, not a black-box strategy: the composite rule
(close > SMA(50) AND ensemble vote > 0) is transparent, the walk-forward
metrics live on every row, and the UI displays them alongside the signals —
including when they show *no* edge.

## Status

**DRAFT** — Migration `V9__kronos_signals.sql` written but not yet applied;
frontend wiring not yet done.

## Producer

`kronos_signal_etl.py` (scheduled via `.github/workflows/kronos_signals.yml`,
service_role writes). Read path: browser via anon key + RLS SELECT policies.

## Tables

### 1. `kronos_predictions` — one row per (symbol, timeframe, bar_timestamp)

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Primary key |
| `symbol` | TEXT | Pair, e.g. `BTC-USDT` |
| `timeframe` | TEXT | `1h`, `4h`, `1d` |
| `bar_timestamp` | TIMESTAMPTZ | Bar open time |
| `predicted_close` | DOUBLE PRECISION | Kronos 1-bar-ahead walk-forward prediction (no lookahead) |
| `sma50` | DOUBLE PRECISION | 50-bar simple moving average (may be NULL during warm-up) |
| `ensemble_vote` | DOUBLE PRECISION | `sign(kronos_sign + linear_sign)`; `0` = tie (no fabricated vote) |
| `model_used` | TEXT | Model + tokenizer id |
| `created_at` | TIMESTAMPTZ | Row creation time |

**Unique:** `(symbol, timeframe, bar_timestamp)` — upsert key.

### 2. `kronos_signals` — one row per (symbol, timeframe, bar_timestamp)

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Primary key |
| `symbol` | TEXT | Pair |
| `timeframe` | TEXT | Interval |
| `bar_timestamp` | TIMESTAMPTZ | Bar open time |
| `signal` | TEXT | `buy` / `sell` / `flat` (transition-triggered) |
| `reason` | TEXT | Machine-readable trigger (see below) |
| `model_used` | TEXT | Model + tokenizer id |
| `net_return_pct` | DOUBLE PRECISION | Long/flat walk-forward equity, 0.1% fee/side |
| `buy_hold_pct` | DOUBLE PRECISION | Buy-and-hold over the same bars |
| `directional_accuracy_pct` | DOUBLE PRECISION | Share of bars where `sign(vote) == sign(actual move)` |
| `evaluated_from` / `evaluated_to` | TIMESTAMPTZ | First/last evaluated bar |
| `evaluated_bars` | INTEGER | Bars actually evaluated (compound growth range) |
| `created_at` | TIMESTAMPTZ | Row creation time |

**Unique:** `(symbol, timeframe, bar_timestamp)` — upsert key.

> Metrics repeat on every row of a series (they describe the whole evaluated
> window). The UI should read them from the newest row.

## Signal Rule (source of truth: `derive_composite_signals`)

```
LONG  when  close(i-1) > SMA50(i-1)  AND  ensemble_vote(i) > 0
FLAT  otherwise (exit when either condition fails)
```

- Signals are **transition-triggered**: `buy` on 0→1, `sell` on 1→0, else
  `flat`. `position` (1/0) is the per-bar long/flat state.
- The signal for bar `i` is decided from data available at the close of bar
  `i-1` (matches the walk-forward convention; no lookahead).

### `reason` values

| Reason | Meaning |
|--------|---------|
| `close_above_sma50_and_vote_gt_0` | Entry (both conditions met) |
| `close_below_or_equal_sma50` | Exit (trend filter failed) |
| `vote_le_0` | Exit (ensemble vote non-positive) |
| `flat` | No transition |

## Honesty Requirements (do not "fix")

1. **Raw Kronos direction has NO validated edge** (~40–49% sign accuracy on
   BTC/ETH at daily/4h per the KRONOS findings). The composite overlay is
   presented as research, and `directional_accuracy_pct` must be shown so the
   lack of edge remains visible.
2. **Directional accuracy compares predicted close vs the LAST ACTUAL close** —
   never `pct_change()` of the prediction series.
3. **No lookahead** — predictions and votes use only bars up to `i-1`.
4. **Ties are honest** — `ensemble_vote = 0` stays `0` (`sign(0) = 0`); the
   signal never fabricates a direction from a tie.

## Frontend Contract

- Browser queries with anon key: `.from('kronos_predictions')` and
  `.from('kronos_signals')` filtered by `symbol` + `timeframe`, ordered by
  `bar_timestamp` ascending.
- Chart markers: `buy` → arrowUp below bar (green), `sell` → arrowDown above
  bar (red). Optionally render `sma50` as a line overlay (indicator catalog)
  and `predicted_close` as a dashed overlay.
- UI should surface the honesty metrics (from the newest row) in the
  Kronos overlay panel, e.g. `dir-acc 48% · net +2.1% vs buy&hold +11.4%`.

## Example rows

```json
{
  "symbol": "BTC-USDT", "timeframe": "1d",
  "bar_timestamp": "2026-08-19T00:00:00Z",
  "predicted_close": 61245.13,
  "sma50": 59810.02,
  "ensemble_vote": 1,
  "model_used": "NeoQuasar/Kronos-mini"
}
```

```json
{
  "symbol": "BTC-USDT", "timeframe": "1d",
  "bar_timestamp": "2026-08-19T00:00:00Z",
  "signal": "buy",
  "reason": "close_above_sma50_and_vote_gt_0",
  "net_return_pct": 2.1,
  "buy_hold_pct": 11.4,
  "directional_accuracy_pct": 48.2,
  "evaluated_from": "2026-01-01T00:00:00Z",
  "evaluated_to": "2026-08-19T00:00:00Z",
  "evaluated_bars": 190
}
```

## Related

- ADR-0007 (why precompute instead of live in-browser inference)
- ADR-0005 (transparent strategies first; this overlay ships with honest metrics,
  not an implied edge)
- `migrations/V9__kronos_signals.sql`