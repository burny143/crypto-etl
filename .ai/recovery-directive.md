# PROJECT RECOVERY — State Reconstruction & AI Governance Directive

**Prepared for:** Fredrick Mahinay  
**Purpose:** Stabilize a mid-development repository after an AI session introduced hallucinated assumptions, incomplete work, documentation drift, or architectural inconsistency.  
**Usage:** Paste this directive from the repository root into Claude Code, OpenCode, Qwen, or another coding agent. The first run is an audit and documentation pass — not a broad implementation pass.

---

## Full Directive Text

```
PROJECT RECOVERY, STATE RECONSTRUCTION, AND AI GOVERNANCE DIRECTIVE

You are acting as the senior software architect, repository forensic analyst, quality engineer, documentation maintainer, and implementation assistant for this existing project.
This project is already in progress. Previous AI-assisted development may have introduced hallucinated assumptions, incomplete implementations, incorrect relationships, undocumented architecture changes, duplicate logic, dead code, broken tests, schema mismatches, configuration drift, disconnected features, unsafe financial calculations, or documentation that no longer matches physical reality.
Your first responsibility is NOT to continue implementing features. Your first responsibility is to reconstruct the current state from repository evidence and establish a reliable, persistent project-memory system.

Governing Principle
The repository is the source of truth. Chat history, previous AI claims, old plans, comments, and documentation are context only until validated against current code, tests, contracts, configuration, and Git history.
```

### 1. Primary Objective
1. Determine the actual current state of the project.
2. Identify what is complete, partial, broken, missing, duplicated, obsolete, disconnected, or uncertain.
3. Reconstruct the implemented architecture and data flow from code evidence.
4. Determine the status of the feature currently in progress.
5. Create or update persistent AI state files that survive context resets.
6. Document conflicts among plans, documentation, tests, contracts, and implementation.
7. Establish guardrails that prevent future hallucination and scope drift.
8. Produce the smallest safe recovery plan and stop for human review.
9. Make the repository self-documenting and resumable by a fresh AI session.

### 2. Non-Negotiable Operating Rules
- **2.1 Source-of-Truth Hierarchy:** Tests > Schemas > Code > Manifests > ADRs > Docs > AI state > Comments/Chat
- **2.2 No Guessing:** Label claims UNVERIFIED / BLOCKED / AMBIGUOUS / CONFLICTING / VERIFIED
- **2.3 Inspect Before Editing**
- **2.4 Minimal and Reversible Changes**
- **2.5 Protected Paths:** `vibe-trading/` is read-only
- **2.6 Human-Controlled Actions:** No merge, push, force-push, rebase, deploy, or live trading
- **2.7 Stop Conditions:** 10 defined conditions requiring human review

### 3. Execution Modes
`RECOVERY AUDIT` → `STATE RECONSTRUCTION` → `PLANNING` → `AUTHORIZED IMPLEMENTATION` → `VALIDATION` → `DOCUMENTATION SYNC` → `BLOCKED` → `COMPLETE`

### 4. Phase A — Pre-Flight Safety Check (read-only environment checks)

### 5. Phase B — Discover Existing AI Instructions (recursive search, precedence map)

### 6. Phase C — Complete Repository Inventory (all components, status, tests, docs)

### 7. Phase D — Reconstruct Actual Architecture (critical flows end to end)

### 8. Phase E — Determine Current Feature and Milestone (feature matrix with evidence)

### 9. Phase F — Safe Git Backtracking (forensic analysis, recovery options)

### 10. Phase G — Safe Validation (repository-defined commands, exact results)

### 11. Financial and Trading Safety Rules
- 11.1 Precision and Units: Decimal for money, identify all units
- 11.2 Determinism and Time: UTC only, no look-ahead, completed candles only
- 11.3 Environment Separation: Research/paper/live boundaries
- 11.4 Order and Position Integrity: Idempotency, partial fills, stale data, P&L

### 12. Data Contracts
Locate/establish `docs/data-contracts/` with full field specs and examples.

### 13. Security and Secret Handling
Inspect hardcoded credentials, tokens, keys. Redact, don't reproduce.

### 14. Persistent Project Memory System
```
AGENTS.md or CLAUDE.md
.ai/
  current-state.md
  current-milestone.md
  recovery-report.md
  session-handoff.md
  decisions-pending.md
  known-issues.md
  validation-status.md
docs/
  ARCHITECTURE.md
  data-contracts/
  decisions/
  runbooks/
  feature-status/
```

### 15. Hallucination and Drift Detection
Search for nonexistent imports, placeholder behavior, mock-only tests, duplicate services, dead code, hardcoded sample data, schema mismatches, undocumented env vars, unsafe numeric types.

### 16. Phased Recovery Plan
- **R0** — Preserve and Observe
- **R1** — Reconstruct State
- **R2** — Restore Baseline Health
- **R3** — Repair Current Feature
- **R4** — Strengthen Guardrails
- **R5** — Validate and Handoff

### 17. CI and Automatic Guardrails
Prefer existing tooling. Custom checks must be local, actionable, low false-positive.

### 18. Mandatory Future AI Workflow
9-step workflow: reload context → restate scope → inspect → plan → implement → validate → sync → DoD → stop.

### 19. Context Reload Protocol
When confused: stop editing → re-read state files → inspect git → compare → update → checkpoint.

### 20. Required Initial Output
A `PROJECT RECOVERY CHECKPOINT` with 18 required sections, ending with:
```
RECOVERY CHECKPOINT COMPLETE — WAITING FOR HUMAN REVIEW. NO MERGE, PUSH, DEPLOYMENT, OR NEXT-PHASE WORK WAS PERFORMED.
```

### 21. Documentation Quality Requirements
Evidence-based, concise, path-aware, no secrets, terminology-consistent, synchronized with reality.

### 22. Change-Control Rules
Define scope → record git status → focused changes → review diff → protect paths → validate → sync docs → DoD → stop.

### 23. Definition of Done Policy
Feature complete only when: requirements explicit, end-to-end connected, inputs/errors handled, contracts respected, tests pass, lint/type/build pass, security reviewed, docs synced, no path violations, diff focused, limitations recorded.

### 24. Start Now
Begin in `MODE: RECOVERY AUDIT`. Do not immediately repair.

---

## Recovery Session Context

### Current Mode
`RECOVERY AUDIT`

### Repository Identity
| Field | Value |
|-------|-------|
| Root | `C:\__Projects\AI Projects\trading-research` |
| Type | Monorepo with **nested Git repository** |
| Parent branch | `master` @ `8aaa679` |
| Nested branch | `crypto-etl` on `phase/5-cli` @ `548db1e` |
| Parent pinned commit | `72d3d00` (stale — 12 commits behind nested HEAD) |
| Working tree | HAS CHANGES (both repos) |

### Git State
- **Parent repo:** `M crypto-etl` (stale gitlink), `? vibe-trading/` (untracked, protected), `?? .playwright-mcp/` (untracked)
- **Nested repo:** 7 modified files (QA fixes — uncommitted), `?? .coverage` (untracked)

### Validation Results
| Check | Result |
|-------|--------|
| 150 unit tests | ✅ PASS (0.69s) |
| Ruff lint | ✅ PASS |
| Black format | ✅ PASS |
| Coverage 88.79% | ✅ Above 75% floor |
| Mypy | ⚠️ 12 pre-existing errors |
| Vibe boundary | ✅ PASS |
| Stale gitlink | ⚠️ Parent pinned 12 commits behind |

### Completed Phases (actual nested repo)
- Phase 1 — Bot scaffolding ✅
- Phase 1.5 — CI tooling ✅
- Phase 2 — RSI Strategy ✅
- Phase 3 — Paper execution ✅
- Phase 4 — Orchestrator ✅
- Phase 5 — CLI + signal persistence ✅
- Phase 6 — Documentation (data contracts, lifecycle, gap analysis) ✅
- QA bug fixes (current uncommitted work) ✅ Applied

### Pending Human Decisions
1. `current-data-flow.md` overwrite — keep new content or restore from git?
2. Commit QA fixes or separate from doc changes?
3. Update parent gitlink to point to current nested HEAD?
4. Next phase — Phase 6 multi-strategy per ARCHITECTURE.md, or something else?
5. Resolve 10 open questions from Phase 0 ARCHITECTURE.md

### Key Files for Next Session
- `crypto-etl/AGENTS.md` — project-specific commands and pitfalls
- `crypto-etl/bot/ARCHITECTURE.md` — 474-line Phase 0 plan with open questions
- `crypto-etl/docs/architecture/current-data-flow.md` — overwritten, needs review
- `crypto-etl/bot/engine/engine.py` — core engine (QA fixes applied)
- `crypto-etl/bot/portfolio/service.py` — portfolio accounting (QA fixes applied)
- `.ai/recovery-directive.md` — this file
