# PLAN: Backend Phase 5 (Final Feature Integration)

## Overview
Implement the remaining core agents (Opportunity Agent and Auto-Savings Agent) with real logic instead of static shells, and finalize the integration of the three killer features (Financial Health Score, What-If Simulator, and Auto-Micro-Savings) on the backend. This phase completes the 36-hour hackathon backend requirements before production hardening.

## Project Type
**BACKEND**

## Success Criteria
- [ ] `OpportunityAgent` analyzes transactions to detect unused subscriptions and uses deterministic rules to match products.
- [ ] `AutoSavingsAgent` calculates safe transfer amounts based on forecasts and simulates transfers.
- [ ] Ensure `CoordinatorAgent` correctly routes to these two new capabilities and `ComplianceGuard` intercepts as necessary.
- [ ] All 3 killer features can be executed successfully via `/api/chat` or dedicated endpoints.

## Tech Stack
- **FastAPI** (Routes & Logic)
- **Scikit-learn / Prophet** (via existing `intelligence` services)
- **LangGraph** (existing Orchestrator integration)
- **Pure Python** (Deterministic rule functions)

## File Structure Additions
```text
app/
├── agents/
│   ├── opportunity.py   # (Modify to implement Pattern matching)
│   └── auto_savings.py  # (Modify to implement transfer simulation)
```

## Task Breakdown

### 1. Implement Opportunity Agent Logic
- **Agent:** `backend-specialist`
- **Skills:** `python-patterns`
- **Priority:** P0
- **INPUT:** `app/agents/opportunity.py`
- **OUTPUT:** Real implementation that fetches user transactions, checks for recurring but unused subscriptions, and matches a mock banking product (e.g., Premium Savings).
- **VERIFY:** Unit tests show the Opportunity agent recommending a product when specific recurring transactions exist in the mock history.

### 2. Implement Auto-Savings Agent Logic
- **Agent:** `backend-specialist`
- **Skills:** `python-patterns`
- **Priority:** P0
- **INPUT:** `app/agents/auto_savings.py`, `app/services/forecast.py`
- **OUTPUT:** Real implementation that calls the forecasting service to predict week-end surplus, calculates a safe micro-transfer amount, and generates the approval prompt.
- **VERIFY:** Unit tests confirm that the agent only suggests transfers when `predicted_balance > safety_threshold`. 

### 3. Integrate Agents into LangGraph Coordinator
- **Agent:** `backend-specialist`
- **Priority:** P1
- **Dependencies:** Task 1, Task 2
- **INPUT:** `app/agents/coordinator.py`
- **OUTPUT:** Updates to the coordinator state and edge routing to ensure the new Opportunity and Auto-Savings agent outputs are correctly serialized and returned to the user.
- **VERIFY:** A request asking "how can I save more?" successfully passes through the Opportunity agent and returns a response.

### 4. End-to-End API Integration Testing
- **Agent:** `backend-specialist`
- **Skills:** `testing-patterns`
- **Priority:** P2
- **Dependencies:** Task 3
- **INPUT:** `tests/`
- **OUTPUT:** E2E test scripts covering the What-If Simulator path and the Auto-Savings approval path using the FastAPI test client.
- **VERIFY:** `pytest tests/` passes completely.

## Phase X: Verification
- [ ] Lint: Pass `ruff check .`
- [ ] Security: Verify no LLM calls have access to directly execute financial transfers.
- [ ] Run: `pytest` passes for all agent logic and E2E routes.
