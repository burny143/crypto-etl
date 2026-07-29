# Data Contract: Paper Portfolio

## Purpose

Define the schema for paper trading state: orders, positions, portfolio equity, and cash ledger.

## Status

**DRAFT** — Partially implemented. Tables exist in Supabase (`paper_orders`, `paper_positions`, `paper_equity_curve`) but some fields are proposed additions.

---

## Current Implementation

### `paper_orders` Table

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| `id` | UUID | ✅ | Primary key |
| `symbol` | TEXT | ✅ | Trading pair |
| `side` | TEXT | ✅ | "long" or "short" |
| `order_type` | TEXT | ✅ | "market" |
| `quantity` | FLOAT | ✅ | Order quantity |
| `price` | FLOAT | ✅ | Fill price |
| `status` | TEXT | ✅ | "filled" |
| `pnl` | FLOAT | ✅ | Realized P&L for this order |
| `notes` | TEXT | ✅ | Human-readable notes |
| `signal_id` | UUID | ❌ | Proposed: link to signal_events.signal_id |
| `opened_at` | TIMESTAMPTZ | ✅ | Order creation time |
| `filled_at` | TIMESTAMPTZ | ✅ | Order fill time |

### `paper_positions` Table

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| `id` | UUID | ✅ | Primary key |
| `symbol` | TEXT | ✅ | Trading pair |
| `side` | TEXT | ✅ | "long" or "short" |
| `quantity` | FLOAT | ✅ | Current position size |
| `entry_price` | FLOAT | ✅ | Average entry price |
| `current_price` | FLOAT | ✅ | Latest known price |
| `unrealized_pnl` | FLOAT | ✅ | Current unrealized P&L |
| `signal_id` | UUID | ❌ | Proposed: link to originating signal event |
| `strategy_id` | TEXT | ❌ | Proposed: owning strategy identifier |
| `status` | TEXT | ✅ | "open" or "closed" (added in V8 migration) |
| `opened_at` | TIMESTAMPTZ | ✅ | Position open time |
| `updated_at` | TIMESTAMPTZ | ✅ | Last update time |

### `paper_equity_curve` Table

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| `id` | UUID | ✅ | Primary key |
| `total_equity` | FLOAT | ✅ | Cash + unrealized P&L |
| `cash_balance` | FLOAT | ✅ | Available cash |
| `timestamp` | TIMESTAMPTZ | ✅ | Snapshot time |

---

## Gaps

1. **No cash ledger** — cash movements are not auditable. `tradeCash` is an in-memory variable that resets on page reload.
2. **No `signal_id`** — orders and positions cannot be linked back to the research or signal that motivated the trade.
3. **Equity curve is populated but not consistently** — the refresh patterns may miss snapshots during active trading.
4. **No portfolio abstraction** — the current code treats all positions as a single portfolio with one cash balance. No named portfolio or multi-strategy allocation.

## Proposed Additions

### `cash_ledger` Table (Future)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | UUID | ✅ | Primary key |
| `portfolio_id` | UUID | ✅ | References paper_portfolios.id |
| `timestamp` | TIMESTAMPTZ | ✅ | When the cash movement occurred |
| `amount` | FLOAT | ✅ | Positive = deposit/realized profit, negative = withdrawal/realized loss |
| `balance_after` | FLOAT | ✅ | Cash balance after this movement |
| `reason` | TEXT | ✅ | One of: `initial_capital`, `order_fill`, `close_position`, `fee`, `reset` |
| `order_id` | UUID | ❌ | References paper_orders.id if related to an order |

### `paper_portfolios` Table (Future)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | UUID | ✅ | Primary key |
| `name` | TEXT | ✅ | Human-readable portfolio name |
| `initial_capital` | FLOAT | ✅ | Starting capital |
| `cash_balance` | FLOAT | ✅ | Current cash balance |
| `created_at` | TIMESTAMPTZ | ✅ | When the portfolio was created |
| `is_active` | BOOLEAN | ✅ | Whether this portfolio is currently active |

## Position Netting Rules

The current paper trading implementation uses **netting accounting**:
- Only one position per symbol (either long or short, never both)
- Opposite-side orders reduce or close the existing position
- If the incoming order exceeds the opposite position, the excess opens a new same-side position
- Entry price is not recalculated on partial reduction (bug fix applied 2026-07-27)

This is documented here because it differs from **hedged accounting** (both long and short positions can coexist on the same symbol) which some traders may expect.
