# ADR-0006: Incremental index.html Modularization

## Status

**Accepted** (2026) — Planned for future implementation, not yet started

## Context

`index.html` has grown to ~2,050 lines of inline JavaScript containing:
- Supabase client initialization
- 12 indicator computation functions
- Chart initialization and management
- Data loading and transformation
- Signal engine
- AI research panel
- Paper trading (order placement, position management, P&L tracking)
- Strategy results panel
- UI event handlers
- Boot sequence

This monolithic structure is becoming difficult to navigate and test. However, a full rewrite (React or modular JS) would be risky and is explicitly out of scope.

## Decision

When the monolithic file becomes a bottleneck, modularize **incrementally** by extracting independent modules into separate JS files, one at a time, without restructuring the remaining code.

Proposed extraction order:
1. **Indicator math functions** — pure computation, no DOM or Supabase dependency
2. **Supabase client and data access** — all `.from()` calls wrapped in named functions
3. **Paper trading logic** — `placeOrder()`, `closePosition()`, order/position rendering
4. **Signal engine** — condition evaluation and marker generation
5. **UI event handlers** — separate from business logic

## Consequences

**Positive:**
- Low risk — each extraction is a targeted change
- No rewrite overhead
- Gradual improvement in maintainability
- Enables unit testing of extracted modules

**Negative:**
- Mixed architecture during transition (some modules extracted, some inline)
- Must maintain backward compatibility with existing Supabase queries and DOM structure
- HTML/DOM event bindings may be harder to extract cleanly

## Rules for Extraction

1. Each extraction must produce a **standalone JS module** with a clean API
2. No new build step — use ES6 modules (`type="module"`) or script tags as appropriate
3. The extracted module must work correctly when `index.html` is opened directly from the filesystem or via `python -m http.server`
4. Backup before every extraction
5. Verify that all existing features work after each extraction
