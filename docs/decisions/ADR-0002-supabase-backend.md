# ADR-0002: Supabase as Database Backend

## Status

**Accepted** (2026)

## Context

The project needs a persistent data store for OHLCV data, research results, and paper trading state. A dedicated backend server (FastAPI) was initially built but later abandoned.

Options considered:
1. **FastAPI + PostgreSQL** — full control, requires server management. Was built but abandoned.
2. **SQLite** — serverless, but problematic for GitHub Actions workflows and multi-machine access.
3. **Supabase** — hosted PostgreSQL with REST API, real-time subscriptions, and RLS. No server needed for client-side operations.

## Decision

Supabase is the database backend. The client-side `index.html` uses the Supabase JS SDK with the anon key. RLS policies restrict the anon key to SELECT and INSERT on specific tables. The FastAPI backend is abandoned.

Supabase project URL: `https://ymnlqggxeeyqvrojsrzh.supabase.co`

## Consequences

**Positive:**
- Zero server infrastructure for read/write operations
- Hosted PostgreSQL — reliable, managed
- RLS provides security without a custom auth layer
- Real-time subscriptions available for future live updates
- Anonymous key pattern works well for single-user research terminal

**Negative:**
- Supabase dependency — migration would require changing all data access code
- Anon key is client-visible (mitigated by RLS)
- No complex transaction support from client-side (single-table operations only)
- Query limitations — no server-side joins, aggregation must be client-side

## Key Credential Rules

- Anon key: embedded in `index.html` (safe with RLS)
- Service role key: backend-only, never in frontend code, stored in GitHub Secrets
- See `.ai/financial-safety.md` for full credential rules
