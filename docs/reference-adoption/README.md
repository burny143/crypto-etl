# Reference Adoption from vibe-trading

## Purpose

This directory tracks patterns, ideas, and methodologies adopted (or considered for adoption) from the `vibe-trading/` reference project. It exists to:
1. Document why a pattern was adopted
2. Record the crypto-etl adaptation (not a copy)
3. Note any deviations from the original
4. Prevent duplicate analysis of the same reference material

## Current Adopted Patterns

| Pattern | Source | File | Status |
|---------|--------|------|--------|
| Signal value in [-1, 1] | `strategy-generate` skill | `docs/data-contracts/signal-event.md` | Documented |
| Walk-forward OOS/IS split | Strategy generation pattern | `docs/research/validation-policy.md` | Implemented in research engine |
| Post-backtest metrics | Attribution layers | `strategy_research.py` | Implemented (Sharpe, return, drawdown, win rate, profit factor) |
| Pure pandas/numpy signals | `technical-basic` skill | `strategy_research.py` | Implemented (no TA-Lib) |
| No-lookahead via .shift(1) | `strategy-generate` skill | `strategy_research.py` | Implemented |

## Patterns Reviewed and Rejected

| Pattern | Reason for Rejection |
|---------|---------------------|
| 88 skills system | Over-engineered for single research terminal |
| Multi-agent swarm | Single-user workflow, no orchestration needed |
| Persistent memory (Ebbinghaus) | Not needed for price-based research |
| Shadow account / journal parsing | No broker trade journals available |
| ML strategies | Explicitly out of scope (see .ai/scope.md) |

## Patterns Under Consideration

| Pattern | Source | Notes |
|---------|--------|-------|
| Factor decay tracking | IC/IR time series | Useful for strategy health monitoring (Phase 4) |
| Regime detection | `correlation-analysis` skill | Could improve signal filtering by market regime |
| Attribution layers | Post-backtest analysis | Trade attribution + beta regression + Monte Carlo (Phase 4) |

## How to Add a New Adoption

1. Study the pattern in `vibe-trading/` (read-only access)
2. Document the requirement in `crypto-etl` that this pattern solves
3. Design the adaptation — must differ from the original (no code copy)
4. Create an ADR if the adoption affects architecture
5. Link the ADR and data contract from this README
6. Never copy files from `vibe-trading/` into `crypto-etl/`
