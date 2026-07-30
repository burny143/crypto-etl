# Current Milestone: Bot Hardening & Contract Alignment

**Status:** Active development — resolving alignment findings, hardening the paper-trading bot for continuous operation.

## Context

Phases 1–5 are implemented and committed on `crypto-etl` branch `main`:
- Phase 1: Market data adapter + config loading
- Phase 1.5: CI tools (pytest, ruff, black, mypy)
- Phase 2: RSI + Breakout Hunter strategies
- Phase 3: Paper execution (risk manager, executor, portfolio, Supabase repos)
- Phase 5: CLI, forward paper trading engine, Supabase persistence

Phase 4 (backtesting) is not yet built — it was deliberately deferred in favor of getting the forward bot running first.

## Alignment Findings to Resolve

The guardian audit (2026-07-29) identified these issues:

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| F-02 | **HIGH** | `--in-memory` mode requires Supabase credentials (violates offline-safe) | Decouple data from credentials in in-memory mode |
| F-03 | MEDIUM | AGENTS.md says nested branch is `phase/5-cli`, actual is `main` | Fix AGENTS.md |
| F-04 | MEDIUM | `paper_positions.status` column added in V8 but missing from data contract | Update `paper-portfolio.md` |
| F-05 | MEDIUM | `paper_orders.decision_key` lacks UNIQUE constraint | Add to V8 migration |
| F-06 | LOW | Root AGENTS.md rewrite uncommitted | Commit |

## Scope

### Must Do (unblocks safe operation)

1. **Fix in-memory mode** — `--in-memory` must work without Supabase credentials. Use `InMemoryMarketData` or a null data provider instead of requiring `create_client()`.
2. **Add UNIQUE constraint** on `paper_orders.decision_key` in V8 migration.
3. **Update data contracts** — `paper-portfolio.md` gains `status` column on `paper_positions`.
4. **Fix AGENTS.md** — nested branch name to `main`.

### Should Do

5. **Apply V8 migration** to Supabase if not already applied.
6. **Full test pass** — verify 171+ tests pass with the `--in-memory` fix.

### Not Doing

- Designing or implementing backtesting (Phase 4) — that's the next milestone after this one.
- Multi-strategy ownership model (Phase 6) — deferred.
- Modifying `vibe-trading/` — always read-only.
- Full rewrites of `index.html` — incremental changes only.

## Acceptance Criteria

1. `python -m bot.cli run-once --in-memory` succeeds without `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` set.
2. `paper_orders.decision_key` has a UNIQUE constraint in V8 migration.
3. `docs/data-contracts/paper-portfolio.md` documents the `status` column on `paper_positions`.
4. AGENTS.md reflects actual nested branch name.
5. 171+ tests pass with no regressions.
6. Guardian re-audit returns ALIGNED or CORRECTION REQUIRED (not BLOCKED).

## Key Documents

| Document | Purpose |
|----------|---------|
| `AGENTS.md` | Monorepo agent instructions |
| `docs/data-contracts/paper-portfolio.md` | Paper trading data contract |
| `crypto-etl/migrations/V8__paper_trading_completion.sql` | V8 schema migration |
| `crypto-etl/bot/cli.py` | Bot CLI entry point |
