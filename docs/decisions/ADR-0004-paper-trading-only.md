# ADR-0004: Paper Trading Only

## Status

**Accepted** (2026)

## Context

The project includes a fully functional trading panel that can place buy/sell orders and track P&L. By design, this is a research tool, not a trading platform.

## Decision

**No live trading.** The project remains paper-only indefinitely. This means:
- No real exchange API keys are stored or used
- No orders are routed to real exchanges
- All P&L, cash balances, and portfolio values are simulated
- Paper trading results are never represented as actual trading performance

## Consequences

**Positive:**
- No regulatory requirements
- No financial risk
- No exchange API key management
- No slippage or execution quality concerns
- Clean sandbox for strategy research

**Negative:**
- Paper trading results may not reflect live trading performance (slippage, liquidity, psychological factors)
- User must manually execute any trades they want to mirror in a real account
- No integration with broker APIs (a common feature request for research platforms)

## Open Questions

- Should a "paper → real" export feature be added? Proposed: no — that crosses the line into live trading tooling.
- Should paper trading P&L be persisted to a cash ledger? Proposed: yes — in Phase 4, to prevent reset on page reload.
