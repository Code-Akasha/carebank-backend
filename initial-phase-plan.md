# CareBank Initial Phase (Hours 0-6)
> 🤖 **Applying knowledge of `@[project-planner]`...** 

## Goal
Set up the core infrastructure, Mock Banking API, and PostgreSQL database with pgvector, as specified in the "Hours 0-6" timeline of the `SOLUTION.md`.

## Tasks

### Backend (`carebank-backend`)
- [x] Task 1: Setup FastAPI project structure and dependencies (FastAPI, SQLAlchemy, pgvector, pydantic, redis) → Verify: `uvicorn main:app` runs without errors
- [x] Task 2: Configure PostgreSQL + pgvector connection via Docker Compose (or local setup) → Verify: Docker container starts, backend connects to DB
- [x] Task 3: Create schema for Transactions, Balances, and Product Catalog → Verify: `schema_validator.py` or successful migration script execution
- [x] Task 4: Implement Deterministic Core functions (budget, forecast impact, eligibility shell) in pure Python → Verify: Unit tests pass for deterministic functions

### Mock API (`carebank-mockbank`)
- [x] Task 5: Initialize hybrid Mock API using Mockoon for `/transactions`, `/balances`, and `/products` endpoints → Verify: Mockoon CLI runs and serves static responses over HTTP
- [x] Task 6: Setup Redis for event triggering (Pub/Sub) and hybrid state management → Verify: Redis is accessible and can publish/subscribe to transaction events

### Frontend (`carebank-frontend`)
- [x] Task 7: Clean up Vite/React template and install TailwindCSS + UI dependencies → Verify: `npm run dev` loads empty app with Tailwind applied
- [x] Task 8: Setup basic routing (Dashboard, Simulator, Products) → Verify: Navigation between empty pages works in browser
- [x] Task 9: Create the "Financial Health Score" meter component UI → Verify: Component renders visually with a static test prop value

## Done When
- [ ] Database is running and accepting connections
- [ ] Deterministic core calculations are unit-tested and correct
- [ ] Mock API serves data to `/transactions`, `/balances`, and `/products`
- [ ] Frontend shell is running with Tailwind and basic routing
- [ ] Health Score meter component is complete

## Notes
- Do not touch LLMs or Agents yet. This phase is purely about infrastructure and deterministic features.
- Keep the Mock API responses simple but aligned with the data structure needed for Prophet (timestamps, amounts, categories).
- **Rule Check**: Read `@[skills/plan-writing]` guidelines. Kept to 8 specific tasks. No LLM integration until next phase.
