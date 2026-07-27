# ADR-0001: Vanilla JavaScript Frontend

## Status

**Accepted** (2026) — supersedes the React/TypeScript SPA

## Context

The project initially had a React 19 + Vite + TypeScript frontend (`crypto-etl/frontend/`). It required a build step, npm dependencies, and a development server. The vanilla HTML/JS `index.html` was originally a prototype or reference UI.

Over time, all features were ported to `index.html` because:
- No build step — open in browser or serve with `python -m http.server`
- Faster iteration — edit and reload, no compilation
- Smaller footprint — single HTML file vs React bundle
- Sufficient complexity — the research terminal does not require React's component model

## Decision

`index.html` is the primary UI. The React SPA in `crypto-etl/frontend/` is **abandoned**. No new features or fixes should be applied to the React frontend.

## Consequences

**Positive:**
- Zero build dependencies for the UI
- Fast development cycle
- Single-file deployment (plus CDN dependencies)

**Negative:**
- No type checking or compile-time error detection
- No component tree or state management library
- All logic is procedural/declarative JS — harder to test at scale
- Risk of monolithic file growth as features are added

## Mitigation

- ADR-0006 explores incremental modularization of `index.html` into separate JS modules without rewriting it.
- TypeScript compilation can be added incrementally once modules exist.
