# ADR-0005: Transparent Rule-Based Strategies First

## Status

**Accepted** (2026)

## Context

The strategy research engine (`strategy_research.py`) currently implements 8 strategy templates, all based on transparent technical indicators (EMA crossovers, RSI thresholds, Bollinger Band breaks, etc.). This is a deliberate architectural choice.

## Decision

All strategies must be **transparent, rule-based systems** with:
- Documented entry/exit conditions
- Configurable parameters (period, threshold, multiplier)
- Deterministic computation (same inputs → same outputs)
- No machine learning, reinforcement learning, or black-box models

## Consequences

**Positive:**
- Results are auditable and reproducible
- Users can understand why a signal was generated
- Parameter sweeps are computationally cheap
- No overfitting risk from ML models
- Strategy logic can be independently implemented in Python (research) and JavaScript (frontend markers)

**Negative:**
- Cannot capture complex non-linear patterns
- May miss relationships that ML would detect
- Parameter optimization may still overfit (mitigated by walk-forward validation)

## Future Consideration

If ML strategies are ever considered, they must be evaluated against transparent baselines and pass the same walk-forward validation rigour. This is not currently planned (see `.ai/scope.md`).
