# Known Issues

**Last updated:** 2026-07-28  
**Source:** Recovery Audit at HEAD `548db1e` (nested) / `8aaa679` (parent)  

---

## Active Issues

### I-001: Paper trading cash resets on page reload
- **Severity:** HIGH
- **Affected:** `index.html` frontend
- **Evidence:** `tradeCash` initialized in-memory; `localStorage` backup is unreliable; `paper_equity_curve` only written on `persistCash()` calls
- **Reproduction:** Open terminal → paper trade → reload page → cash resets to $10,000
- **Workaround:** None
- **Proposed resolution:** Persist cash balance to Supabase `paper_equity_curve` consistently on every trade
- **Milestone:** Phase 4 (ROADMAP)

### I-002: Strategy results → chart markers traceability gap
- **Severity:** HIGH
- **Affected:** `strategy_results` ↔ `index.html` signal markers
- **Evidence:** `strategy_results` has no `strategy_id` or `strategy_version`; chart markers are client-side only (no `signal_id`)
- **Impact:** Cannot determine which strategy version produced which chart markers
- **Workaround:** Manual comparison
- **Proposed resolution:** Add `strategy_id`/`strategy_version` to `strategy_results`; add `signal_events` table
- **Milestone:** Phase 3 (ROADMAP) / Phase 3b (target-data-flow.md)

### I-003: Supabase repository adapters untested in CI
- **Severity:** MEDIUM
- **Affected:** `repositories/supabase_repos.py`
- **Evidence:** 55% coverage; requires `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
- **Impact:** Supabase integration paths are unverified in CI
- **Workaround:** Integration tests pass manually with credentials
- **Proposed resolution:** Add `--integration` marker tests with documented credential setup
- **Milestone:** Phase 1.5 follow-up

### I-004: Parent gitlink stale
- **Severity:** LOW (developer inconvenience)
- **Affected:** Parent repo (`trading-research`) → nested repo (`crypto-etl`)
- **Evidence:** Parent pinned at `72d3d00`; nested HEAD is `548db1e` (12 commits ahead)
- **Impact:** `git checkout` in parent restores older crypto-etl
- **Proposed resolution:** `git add crypto-etl && git commit` in parent to update gitlink
- **Milestone:** Next commit

### I-005: Mypy pre-existing errors
- **Severity:** LOW
- **Affected:** `domain/utc.py:84`, `domain/models.py:93,100`, `repositories/supabase_repos.py`, `tests/`
- **Evidence:** 12 errors — all pre-existing, none introduced by current changes
- **Impact:** Type checking is unreliable
- **Workaround:** None needed (mypy is optional in CI)
- **Proposed resolution:** Fix in a dedicated cleanup pass

### I-006: Phase numbering inconsistency across docs
- **Severity:** MEDIUM
- **Affected:** `ROADMAP.md` (says Phase 3), `PROJECT_STATUS.md` (says Phase 3), nested repo (Phase 5+ completed)
- **Evidence:** Cross-document comparison
- **Impact:** Fresh sessions get confused about current state
- **Proposed resolution:** Align all docs to match actual phase numbering from nested repo
- **Milestone:** Documentation sync

### I-007: `current-data-flow.md` overwritten
- **Severity:** HIGH
- **Affected:** `docs/architecture/current-data-flow.md`
- **Evidence:** 311 lines changed; file now contains Phase 6 summary doc, likely replacing detailed technical architecture
- **Impact:** Original architecture documentation may be lost
- **Workaround:** Recoverable via `git show HEAD:docs/architecture/current-data-flow.md`
- **Proposed resolution:** Decide: restore original or split into two files

---

## Pre-existing Documentation-Known Issues

From `PROJECT_STATUS.md` — still valid:

| Issue | Status | Notes |
|-------|--------|-------|
| Duplicated strategy logic (Python vs JS) | Documented | Intentional — independence preferred over shared code |
| Frontend (React) abandoned | Permanent | All features ported to index.html |
| Backend (FastAPI) abandoned | Permanent | All logic ported to client-side JS |
| No paginated data loading | Unresolved | All bars loaded at once |
| No walk-forward validation in UI | Unresolved | Currently only shows OOS/IS labels |

---

## Risk / Observation Issues

### O-001: `check-vibe-boundary.py` uses `except SyntaxError: pass`
- **Risk:** LOW — Legal since the script is validating that no syntax errors exist in file reads. `pass` is acceptable here as the file-iteration loop continues.
- **File:** `bot/scripts/check-vibe-boundary.py:32`

### O-002: `UNIQUE(symbol, side)` constraint blocks multi-strategy
- **Risk:** MEDIUM — Future Phase 6 (multi-strategy) requires `strategy_id` in the unique constraint
- **DB:** `migrations/V2__enhanced_schema.sql`
- **Noted in:** ARCHITECTURE.md Section 17 Open Question #2

### O-003: `DOUBLE PRECISION` in Supabase vs `Decimal` in Python
- **Risk:** LOW (accepted) — Sub-cent precision loss on typical crypto prices
- **Documented:** ARCHITECTURE.md Section 10 + Open Question #5
