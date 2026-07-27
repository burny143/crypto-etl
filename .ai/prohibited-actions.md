# Prohibited Actions

The following actions are **strictly forbidden** in this repository:

## Repository Integrity
- ❌ Modifying any file inside `vibe-trading/` for any reason
- ❌ Creating runtime imports, package dependencies, symlinks, or build dependencies from `crypto-etl/` to `vibe-trading/`
- ❌ Copying files from `vibe-trading/` into `crypto-etl/`
- ❌ Force-pushing or rewriting git history (unless explicitly requested by the user)
- ❌ Removing or overwriting uncommitted user work without confirmation

## Security & Credentials
- ❌ Embedding the Supabase service_role key in frontend code
- ❌ Hardcoding Supabase URLs or keys in production code
- ❌ Committing `.env` files, secrets, tokens, or credentials to version control
- ❌ Disabling or bypassing RLS policies
- ❌ Exposing credentials in logs, error messages, or debug output

## Financial Safety
- ❌ Live trading, broker execution, or real exchange API integration
- ❌ Representing paper trading results as actual trading performance
- ❌ Fabricating backtest results, metrics, or validation splits
- ❌ Claiming that technical indicator values or signal outputs are profit guarantees

## Code & Architecture
- ❌ Full rewrites of `index.html` (incremental changes only)
- ❌ React or FastAPI feature development (those components are abandoned)
- ❌ Adding features that do not serve the research workflow
- ❌ ML/RL strategy implementation (all strategies must be transparent rule-based systems)
- ❌ LangGraph, MCP, agent swarms, or new LLM provider integration

## Documentation & Process
- ❌ Claiming tests or validation ran unless they actually ran
- ❌ Creating contradictory or duplicate rules across governance files
- ❌ Modifying runtime source code, workflows, dependencies, SQL migrations, or environment files during documentation-only tasks
- ❌ Restructuring unrelated code when making targeted fixes
