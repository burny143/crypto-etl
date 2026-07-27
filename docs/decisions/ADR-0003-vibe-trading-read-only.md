# ADR-0003: vibe-trading as Read-Only Reference

## Status

**Accepted** (2026)

## Context

The monorepo contains `vibe-trading/`, an open-source AI quantitative research platform (HKUDS/vibe-trading). It includes 88 skills, 462 alphas, 8 backtest engines, and agent orchestration — far more than this project needs.

## Decision

`vibe-trading/` is **read-only reference material**. Never modify, copy from, or create dependencies to it. Patterns may be independently adapted only when they solve a documented `crypto-etl` requirement.

## Consequences

**Positive:**
- No maintenance burden from the upstream project
- No licensing ambiguity (MIT, but no code copied)
- Targeted adoption of only the patterns that serve our research workflow
- Clean separation between our active code and reference material

**Negative:**
- Cannot directly use vibe-trading's backtest engines or data loaders
- Must independently implement any adopted patterns
- Occasional need to re-read reference files for pattern inspiration

## Adopted Patterns

See `.ai/reference-policy.md` for the current list of adopted patterns and explicit non-adoptions.
