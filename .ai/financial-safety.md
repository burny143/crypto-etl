# Financial Safety Rules

## Hard Rules

1. **No live trading.** This project is paper trading only. Never route orders to a real exchange, broker, or external trading platform.
2. **No real API keys.** Never store, commit, or expose exchange API keys, secrets, or tokens. The only credentials in the codebase are the Supabase anon key (safe, RLS-restricted) and the Supabase service_role key (backend-only, never in frontend code).
3. **No real money.** All P&L figures, cash balances, and portfolio values are simulated. Never represent paper trading results as actual trading performance.
4. **No financial advice.** The research insights and signal markers are technical analysis outputs only. They do not constitute investment advice, recommendations, or guarantees of future performance.
5. **No fabricated results.** Strategy backtest results must be derived from actual historical data and documented methodology. Never fabricate Sharpe ratios, returns, or other metrics.
6. **Risk disclosure.** The numeric signal value in signal events is a derived technical indicator output, not a guaranteed probability of profit. All data contracts must include this disclaimer.

## Supabase Credential Rules

- **Anon key** — embedded in `index.html`. Safe because RLS policies restrict operations to SELECT and INSERT on specific tables. Never grant additional permissions to the anon role.
- **Service role key** — stored in `setup.ps1` and GitHub Secrets. Never embed in frontend code, never commit to version control in plain text.
- **Environment variables** — Supabase URL and keys must use environment variables or GitHub Secrets. Never hardcode in production code.

## Data Integrity

- Strategy results must include the `_validation` flag (`in_sample` / `out_of_sample`) in the params JSONB field to distinguish walk-forward periods.
- Paper trading positions and orders must be auditable through the `paper_orders` and `paper_positions` tables.
- Any bug affecting position sizing, P&L calculation, or order routing must be documented with before/after analysis.
