# PLAN: MockBank MVP Phases

## Goal
Establish a reliable local testing node that mimics core banking systems, providing transaction history and product details to the CareBank Intelligence and Deterministic Cores.

## Constraints & Rules
- Fast, stateless, and lightweight (Mockoon + Redis preferred).
- Must provide realistic data for Prophet and K-Means.

---

## Phase 1: Initial Mock Data Setup
*(Completed)*
- Standalone Mockoon API for `/transactions`, `/balances`, `/products`.
- Redis Pub/Sub established for simulated incoming transactions.

## Phase 5: Dynamic Simulation & Scale
*(Parallel with Backend Phase 5 Integration)*

**Branch:** `feature/dynamic-mock-data`
- **Task 1: Temporal Data Generation Script**
  - Create a payload generator that sends realistic transactions over Redis reflecting the 4 defined Personas (Cautious Saver, Impulse Buyer, etc.).
  - Schedule script to inject past 90-days of history to hydrate the backend Postgres DB instantly upon request.
- **Task 2: Edge Case Scenarios**
  - Seed "Anomalous" transactions (e.g., a $5,000 charge for a Cautious Saver).
  - Seed "Subscription" data streams (e.g., Spotify, Netflix every 30 days) for the Opportunity Agent.
- **Task 3: Webhook Integrations**
  - Listen for approval webhooks from backend (e.g., user approved auto-savings) and adjust the mock balance endpoint dynamically if state relies on an external system (or just verify backend captures it).

## Phase 6: Load Testing Prep
*(Parallel with Backend Phase 6)*

**Branch:** `feature/demo-readiness`
- **Task 1: Scripted Demo Profile**
  - Create a hardcoded "Demo User" profile (`user_abc123`) that guarantees a medium health score and triggers the exact What-If product up-sells needed for the presentation.
- **Task 2: Stress Verification**
  - Ensure MockBank can handle rapid-fire requests from the Backend Coordinator during E2E integration without timeouts.

---

## Verification Plan
1. **Health Verification:** Test `/transactions` endpoint returns >100 entries instantly.
2. **Pub/Sub Test:** Send a message via redis-cli and verify Backend catches it and creates an AuditLog.
3. **Demo User Assertions:** Validate `user_abc123` correctly formats data to trigger the expected frontend demo state.
