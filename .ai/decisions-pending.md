# Pending Decisions

**Last updated:** 2026-07-28  
**Source:** Recovery Audit  

---

## Decisions from Recovery Audit

### D-001: What to do with overwritten `current-data-flow.md`
- **Question:** Keep the Phase 6 summary content, or restore the original technical architecture from `git show HEAD:docs/architecture/current-data-flow.md`?
- **Context:** The file was overwritten (311 lines changed) with a Phase 6 documentation summary. The original content contained detailed technical architecture.
- **Options:**
  - A: Restore original from git; create new file for Phase 6 summary
  - B: Keep new content; original is recoverable from git history
  - C: Split — restore original, move Phase 6 summary to separate file
- **Evidence:** `git diff --stat` shows 311 lines changed in that single file
- **Risks:** Option B permanently loses original architecture doc from working tree
- **Recommended:** Option C — restore original, move Phase 6 summary to `docs/architecture/phase-6-summary.md`
- **Status:** ✅ DONE — original restored, Phase 6 summary saved to `docs/architecture/phase-6-summary.md`, committed at `f727f55`

### D-002: Commit QA bug fixes
- **Question:** Should the 7 uncommitted QA fix files be committed as-is, or separated from doc changes?
- **Context:** Files modified: `cli.py`, `validation.py`, `models.py`, `engine.py`, `portfolio/service.py`, `rsi.py`, `current-data-flow.md`
- **Options:**
  - A: Commit all together (mix of code fixes + doc overwrite)
  - B: Commit code fixes first, then handle doc overwrite separately
  - C: Separate into multiple focused commits (code fixes, formatting, docs)
- **Evidence:** All 150 tests pass with the changes; ruff/black clean
- **Risks:** Option A makes the doc overwrite permanent
- **Recommended:** Option B — commit code fixes first, resolve D-001 before committing doc changes
- **Status:** ✅ DONE — 7 files committed at `f727f55` with QA fixes + format cleanup + doc restore

### D-003: Update parent gitlink
- **Question:** Update the parent repo's crypto-etl gitlink to point to `548db1e`?
- **Context:** Parent pinned at `72d3d00`; actual nested HEAD is `f727f55` (13 commits ahead)
- **Options:**
  - A: Update after QA fixes are committed (most accurate)
  - B: Update now to current HEAD, commit again after fixes
  - C: Leave stale (manual checkout risk)
- **Risks:** Stale gitlink means parent checkout restores older version
- **Recommended:** Option A — update after committing fixes
- **Status:** ✅ DONE — parent gitlink updated to `f727f55`, committed at `0f039cc`

### D-004: Next phase definition
- **Question:** What is the actual next development phase?
- **Context:** ROADMAP says Phase 3 (stale). ARCHITECTURE.md planned Phase 6 as `phase/6-multi-strategy`. Nested repo has Phase 1-5 completed.
- **Options:**
  - A: Phase 6 per ARCHITECTURE.md — multi-strategy support
  - B: Phase 4 per ROADMAP — validation & persistence (walk-forward in UI, cash persistence)
  - C: Phase defined by a new external directive
  - D: Continue current trajectory (bot refinements, QA fixes, supabase testing)
- **Status:** ⏳ AWAITING HUMAN DECISION

---

## Open Questions from ARCHITECTURE.md (Phase 0)

### Q-001: `session_id` vs `strategy_id` ownership
- **Question:** How to reconcile the frontend's `session_id`-scoped positions with the bot's multi-strategy `strategy_id` ownership?
- **Context:** ARCHITECTURE.md Section 17, Open Question #1
- **Status:** ⏳ NOT RESOLVED

### Q-002: `UNIQUE(symbol, side)` constraint for multi-strategy
- **Question:** The V2 schema enforces one position per symbol per side. Multi-strategy requires independent positions by strategy.
- **Proposed:** Change to `UNIQUE(symbol, side, strategy_id)`
- **Status:** ⏳ NOT RESOLVED

### Q-003: `paper_orders` additional status values
- **Question:** The bot may use `'open'`, `'cancelled'`, `'rejected'` statuses in addition to the frontend's `'filled'`.
- **Status:** ⏳ NOT RESOLVED (low priority — no conflict expected)

### Q-004: No `signal_id` in paper tables
- **Question:** Add `signal_id` to `paper_orders` and `paper_positions` for traceability.
- **Status:** ⏳ NOT RESOLVED (Phase 3b per target-data-flow.md)

### Q-005: `DOUBLE PRECISION` vs `Decimal` boundary
- **Question:** The bot uses Python `Decimal` internally but writes `float` to Supabase.
- **Decision:** Accepted — sub-cent precision loss on typical crypto prices.
- **Status:** ✅ ACCEPTED (documented in ARCHITECTURE.md Section 10)

### Q-006: Stale price cache invalidation
- **Question:** Frontend `symbolPriceCache` is never evicted.
- **Context:** Bot handles this via `price_max_age_seconds` config.
- **Status:** ✅ RESOLVED FOR BOT (frontend still needs fix)

### Q-007: `tradeCash` initialization
- **Question:** Bot needs independent cash tracking from frontend's localStorage pattern.
- **Status:** ✅ RESOLVED — bot uses `starting_balance` from `config.yaml`

### Q-008: Python version mismatch
- **Question:** CI targets 3.10 but local is 3.13.
- **Context:** pyproject.toml requires `>=3.10`. CI should be upgraded.
- **Status:** ⏳ NOT RESOLVED (CI upgrade needed)

### Q-009: Root dependency management
- **Question:** No `requirements.txt` or `pyproject.toml` at crypto-etl root.
- **Status:** ✅ RESOLVED — bot has its own `pyproject.toml`; ETL scripts use GitHub Actions `pip install`

### Q-010: Existing test infrastructure
- **Question:** Minimum coverage targets.
- **Status:** ✅ RESOLVED — 88.79% coverage achieved, exceeding 75% floor

---

## Legend
- ⏳ AWAITING HUMAN DECISION — requires user input
- ⏳ NOT RESOLVED — acknowledged but no decision made
- ✅ ACCEPTED — decision made and documented
- ✅ RESOLVED — fully addressed
